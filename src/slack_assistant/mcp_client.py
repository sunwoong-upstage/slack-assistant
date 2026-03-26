from __future__ import annotations

import json
import re
from typing import Any, Protocol, cast
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx

from .models import MessageReaction, SearchHit, SearchResultsPage, SlackMessage, SlackThread


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
        page = await self.search_threads_page(query, limit=limit)
        return list(page.hits)

    async def search_threads_page(
        self,
        query: str,
        *,
        limit: int = 20,
        cursor: str | None = None,
        sort: str = "timestamp",
        sort_dir: str = "desc",
    ) -> SearchResultsPage:
        tool_name = await self._resolve_tool_name(
            purpose="search",
            configured=self._search_tool,
            required_terms=("search",),
        )
        arguments: dict[str, Any] = {
            "query": query,
            "limit": limit,
            "sort": sort,
            "sort_dir": sort_dir,
        }
        if cursor:
            arguments["cursor"] = cursor
        raw = await self._invoker.call_tool(tool_name, arguments)
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
                        author_name=(
                            str(
                                item.get("user_name")
                                or item.get("username")
                                or item.get("name")
                                or ""
                            ).strip()
                            or None
                        ),
                        author_user_id=(
                            str(item.get("user") or item.get("user_id") or "").strip() or None
                        ),
                        permalink=item.get("permalink"),
                    )
                )
        if hits:
            return SearchResultsPage(
                hits=tuple(hits),
                next_cursor=self._extract_next_cursor(raw),
            )

        embedded = self._extract_embedded_json(raw)
        results_text = embedded.get("results") if isinstance(embedded, dict) else None
        if isinstance(results_text, str):
            return SearchResultsPage(
                hits=tuple(self._parse_search_hits_from_text(results_text)),
                next_cursor=self._extract_next_cursor(embedded),
            )
        return SearchResultsPage(hits=())

    async def read_thread(self, channel_id: str, thread_ts: str) -> SlackThread:
        tool_name = await self._resolve_tool_name(
            purpose="read",
            configured=self._read_tool,
            required_terms=("read", "thread"),
        )
        raw = await self._invoker.call_tool(
            tool_name,
            {"channel_id": channel_id, "message_ts": thread_ts},
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
                    author_name=(
                        str(
                            item.get("user_name")
                            or item.get("username")
                            or item.get("name")
                            or ""
                        ).strip()
                        or None
                    ),
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
        if parsed_messages:
            return SlackThread(
                channel_id=channel_id,
                thread_ts=thread_ts,
                messages=tuple(parsed_messages),
                permalink=data.get("permalink"),
                title=data.get("title"),
                last_activity_ts=data.get("last_activity_ts") or thread_ts,
            )

        embedded = self._extract_embedded_json(raw)
        messages_text = embedded.get("messages") if isinstance(embedded, dict) else None
        if isinstance(messages_text, str):
            return SlackThread(
                channel_id=channel_id,
                thread_ts=thread_ts,
                messages=tuple(self._parse_thread_messages_from_text(channel_id, messages_text)),
                permalink=data.get("permalink"),
                title=data.get("title"),
                last_activity_ts=data.get("last_activity_ts") or thread_ts,
            )

        return SlackThread(channel_id=channel_id, thread_ts=thread_ts, messages=())

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

        preferred_names = {
            "search": ["slack_search_public_and_private", "slack_search_public"],
            "read": ["slack_read_thread", "slack_read_channel"],
            "permalink": [self._permalink_tool],
        }
        for name in preferred_names.get(purpose, []):
            if name in available_names:
                self._resolved_tools[purpose] = name
                return name

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
    def _extract_embedded_json(payload: Any) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            return None
        content = payload.get("content")
        if not isinstance(content, list):
            return None
        for item in content:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if not isinstance(text, str):
                continue
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
        return None

    @staticmethod
    def _parse_search_hits_from_text(results_text: str) -> list[SearchHit]:
        pattern = re.compile(
            r"Channel: .*?\(ID: (?P<channel_id>[^)]+)\).*?"
            r"(?:Participants: .*?\n)?"
            r"(?:From: (?P<author_name>.*?) \(ID: (?P<author_user_id>[^)]+)\).*?)?"
            r"Message_ts: (?P<message_ts>[0-9.]+).*?"
            r"Permalink: \[link\]\((?P<permalink>[^)]+)\).*?"
            r"Text:\s*\n(?P<text>.*?)(?=\n### Result |\Z)",
            re.S,
        )
        hits: list[SearchHit] = []
        for match in pattern.finditer(results_text):
            permalink = match.group("permalink")
            parsed = urlparse(permalink)
            thread_ts = parse_qs(parsed.query).get("thread_ts", [match.group("message_ts")])[0]
            hits.append(
                SearchHit(
                    channel_id=match.group("channel_id"),
                    message_ts=match.group("message_ts"),
                    thread_ts=thread_ts,
                    text=match.group("text").strip(),
                    author_name=(match.group("author_name") or "").strip() or None,
                    author_user_id=(match.group("author_user_id") or "").strip() or None,
                    permalink=permalink,
                )
            )
        return hits

    @staticmethod
    def _parse_thread_messages_from_text(channel_id: str, messages_text: str) -> list[SlackMessage]:
        block_pattern = re.compile(
            (
                r"(?:=== THREAD PARENT MESSAGE ===|--- Reply \d+ of \d+ ---)\n"
                r"(?P<body>.*?)(?=\n(?:=== THREAD PARENT MESSAGE ===|--- Reply \d+ of \d+ ---)|\Z)"
            ),
            re.S,
        )
        messages: list[SlackMessage] = []
        for match in block_pattern.finditer(messages_text):
            body = match.group("body").strip()
            ts_match = re.search(r"Message TS: (?P<ts>[0-9.]+)", body)
            if not ts_match:
                continue
            author_match = re.search(
                r"From: (?P<author>.*?) \((?:ID: )?(?P<user_id>[A-Z0-9]+)\)",
                body,
            )
            reactions_match = re.search(r"Reactions: (?P<reactions>.+)$", body, re.M)
            text_start = body.find("Message TS:")
            text_value = body[text_start:].split("\n", 1)[1] if "\n" in body[text_start:] else ""
            if reactions_match:
                text_value = text_value.split("\nReactions:", 1)[0]
            text_value = text_value.split("\nFiles:", 1)[0]
            mention_ids = tuple(
                dict.fromkeys(re.findall(r"<@([A-Z0-9]+)(?:\|[^>]+)?>", text_value))
            )
            reactions: list[MessageReaction] = []
            if reactions_match:
                for item in reactions_match.group("reactions").split(","):
                    name = item.strip().split(" (", 1)[0]
                    if name:
                        reactions.append(MessageReaction(name=name))
            messages.append(
                SlackMessage(
                    channel_id=channel_id,
                    ts=ts_match.group("ts"),
                    text=text_value.strip(),
                    user_id=author_match.group("user_id") if author_match else None,
                    author_name=author_match.group("author").strip() if author_match else None,
                    mentions=mention_ids,
                    reactions=tuple(reactions),
                )
            )
        return messages

    @staticmethod
    def _extract_next_cursor(payload: Any) -> str | None:
        candidate_texts: list[str] = []
        if isinstance(payload, dict):
            pagination_info = payload.get("pagination_info")
            if isinstance(pagination_info, str):
                candidate_texts.append(pagination_info)
            content = payload.get("content")
            if isinstance(content, list):
                for item in content:
                    if not isinstance(item, dict):
                        continue
                    text = item.get("text")
                    if isinstance(text, str):
                        candidate_texts.append(text)
        for text in candidate_texts:
            match = re.search(r"cursor [`']([^`']+)[`']", text)
            if match:
                return match.group(1)
        return None

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
