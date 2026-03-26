from __future__ import annotations

import json
from typing import Any, Protocol, cast
from uuid import uuid4

import httpx

from .models import MessageReaction, SearchHit, SlackMessage, SlackThread


class ToolInvoker(Protocol):
    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> dict[str, Any] | list[Any] | str: ...


class ToolCatalogInvoker(ToolInvoker, Protocol):
    async def list_tools(self) -> list[dict[str, Any]]: ...


class MCPClientError(Exception):
    """Raised when Slack MCP calls fail."""


class SlackMCPHTTPTransport:
    def __init__(
        self, *, base_url: str, access_token: str, client: httpx.AsyncClient | None = None
    ) -> None:
        self._base_url = base_url
        self._access_token = access_token
        self._client = client or httpx.AsyncClient(timeout=20.0)

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> dict[str, Any] | list[Any] | str:
        payload = await self._request_rpc(
            "tools/call",
            {"name": name, "arguments": arguments},
        )
        return cast(dict[str, Any] | list[Any] | str, payload.get("result", {}))

    async def list_tools(self) -> list[dict[str, Any]]:
        payload = await self._request_rpc("tools/list", {})
        result = payload.get("result", {})
        tools = result.get("tools", []) if isinstance(result, dict) else []
        return [tool for tool in tools if isinstance(tool, dict)]

    async def _request_rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        response = await self._client.post(
            self._base_url,
            headers={
                "Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
            json={
                "jsonrpc": "2.0",
                "id": str(uuid4()),
                "method": method,
                "params": params,
            },
        )
        try:
            payload = response.json()
        except ValueError:
            response.raise_for_status()
            raise MCPClientError("Slack MCP returned a non-JSON response") from None
        if "error" in payload:
            raise MCPClientError(json.dumps(payload["error"]))
        response.raise_for_status()
        return payload


class SlackMCPClient:
    def __init__(
        self,
        invoker: ToolInvoker,
        *,
        search_tool: str,
        read_tool: str,
        permalink_tool: str,
    ) -> None:
        self._invoker = invoker
        self._search_tool = search_tool
        self._read_tool = read_tool
        self._permalink_tool = permalink_tool
        self._resolved_tools: dict[str, str] = {}

    async def search_threads(self, query: str, *, limit: int = 20) -> list[SearchHit]:
        tool_name = await self._resolve_tool_name(
            purpose="search",
            configured=self._search_tool,
            required_terms=("search", "message"),
        )
        raw = await self._invoker.call_tool(tool_name, {"query": query, "limit": limit})
        records = self._extract_records(raw, ["messages", "items", "results"])
        hits: list[SearchHit] = []
        for item in records:
            channel = item.get("channel") or {}
            channel_id = item.get("channel_id") or channel.get("id")
            message_ts = item.get("ts") or item.get("message_ts")
            thread_ts = item.get("thread_ts") or message_ts
            text = item.get("text") or item.get("body") or ""
            if channel_id and message_ts and thread_ts:
                hits.append(
                    SearchHit(
                        channel_id=channel_id,
                        message_ts=message_ts,
                        thread_ts=thread_ts,
                        text=text,
                        permalink=item.get("permalink"),
                    )
                )
        return hits

    async def read_thread(self, channel_id: str, thread_ts: str) -> SlackThread:
        tool_name = await self._resolve_tool_name(
            purpose="read",
            configured=self._read_tool,
            required_terms=("read", "thread"),
        )
        raw = await self._invoker.call_tool(
            tool_name,
            {"channel_id": channel_id, "thread_ts": thread_ts},
        )
        data = raw if isinstance(raw, dict) else {}
        messages = self._extract_records(data, ["messages", "thread", "items"])
        parsed_messages = []
        for item in messages:
            parsed_messages.append(
                SlackMessage(
                    channel_id=channel_id,
                    ts=str(item.get("ts") or item.get("message_ts")),
                    text=str(item.get("text") or item.get("body") or ""),
                    user_id=item.get("user") or item.get("user_id"),
                    mentions=tuple(item.get("mentions", [])),
                    reactions=tuple(
                        MessageReaction(
                            name=reaction.get("name", ""),
                            user_ids=tuple(reaction.get("users", [])),
                        )
                        for reaction in item.get("reactions", [])
                    ),
                    permalink=item.get("permalink"),
                )
            )
        return SlackThread(
            channel_id=channel_id,
            thread_ts=thread_ts,
            messages=tuple(parsed_messages),
            permalink=data.get("permalink"),
            title=data.get("title"),
            last_activity_ts=data.get("last_activity_ts") or thread_ts,
        )

    async def get_permalink(self, channel_id: str, message_ts: str) -> str:
        tool_name = await self._resolve_tool_name(
            purpose="permalink",
            configured=self._permalink_tool,
            required_terms=("permalink",),
        )
        raw = await self._invoker.call_tool(
            tool_name,
            {"channel_id": channel_id, "message_ts": message_ts},
        )
        if isinstance(raw, str):
            return raw
        if isinstance(raw, dict):
            permalink = raw.get("permalink") or raw.get("url")
            if permalink:
                return str(permalink)
        raise MCPClientError("Permalink response missing permalink")

    async def _resolve_tool_name(
        self,
        *,
        purpose: str,
        configured: str,
        required_terms: tuple[str, ...],
    ) -> str:
        cached = self._resolved_tools.get(purpose)
        if cached:
            return cached
        tools = await self._list_tools_if_supported()
        if not tools:
            self._resolved_tools[purpose] = configured
            return configured
        available_names = {str(tool.get("name", "")) for tool in tools}
        if configured in available_names:
            self._resolved_tools[purpose] = configured
            return configured

        best_match: str | None = None
        best_score = -1
        for tool in tools:
            name = str(tool.get("name", "")).strip()
            if not name:
                continue
            haystack = " ".join(
                str(tool.get(key, "")).lower() for key in ("name", "description", "title")
            )
            score = sum(term in haystack for term in required_terms)
            if purpose == "search" and "channel" in haystack:
                score += 1
            if score > best_score:
                best_score = score
                best_match = name

        resolved = best_match or configured
        self._resolved_tools[purpose] = resolved
        return resolved

    async def _list_tools_if_supported(self) -> list[dict[str, Any]]:
        list_tools = getattr(self._invoker, "list_tools", None)
        if not callable(list_tools):
            return []
        tools = await cast(ToolCatalogInvoker, self._invoker).list_tools()
        return [tool for tool in tools if isinstance(tool, dict)]

    @staticmethod
    def _extract_records(payload: Any, candidate_keys: list[str]) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in candidate_keys:
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
            if all(isinstance(value, dict) for value in payload.values()):
                return [value for value in payload.values() if isinstance(value, dict)]
        return []
