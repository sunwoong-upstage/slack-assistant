from __future__ import annotations

import json

import pytest

from slack_assistant.mcp_client import MCPClientError, SlackMCPClient


class FakeInvoker:
    def __init__(
        self,
        responses: dict[str, object],
        *,
        tools: list[dict[str, object]] | None = None,
    ) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.tools = tools or []

    async def call_tool(self, name: str, arguments: dict[str, object]) -> object:
        self.calls.append((name, arguments))
        return self.responses[name]

    async def list_tools(self) -> list[dict[str, object]]:
        return self.tools


@pytest.fixture
def client() -> SlackMCPClient:
    invoker = FakeInvoker(
        {
            "search": {
                "messages": [
                    {
                        "channel": {"id": "C123"},
                        "ts": "1710.1",
                        "thread_ts": "1710.1",
                        "text": "hello",
                    }
                ]
            },
            "read": {
                "messages": [
                    {
                        "ts": "1710.1",
                        "text": "root",
                        "user": "U1",
                        "mentions": ["U123"],
                        "reactions": [{"name": "eyes", "users": ["U123"]}],
                    },
                    {"ts": "1710.2", "text": "reply", "user": "U2"},
                ],
                "permalink": "https://slack.example/thread",
            },
            "permalink": {"permalink": "https://slack.example/thread"},
        }
    )
    return SlackMCPClient(
        invoker, search_tool="search", read_tool="read", permalink_tool="permalink"
    )


@pytest.mark.asyncio
async def test_search_threads_parses_hits(client: SlackMCPClient) -> None:
    hits = await client.search_threads('"<@U123>"')

    assert len(hits) == 1
    assert hits[0].channel_id == "C123"
    assert hits[0].thread_ts == "1710.1"


@pytest.mark.asyncio
async def test_read_thread_parses_messages(client: SlackMCPClient) -> None:
    thread = await client.read_thread("C123", "1710.1")

    assert thread.permalink == "https://slack.example/thread"
    assert len(thread.messages) == 2
    assert thread.messages[0].reactions[0].name == "eyes"


@pytest.mark.asyncio
async def test_get_permalink_requires_permalink_field(client: SlackMCPClient) -> None:
    permalink = await client.get_permalink("C123", "1710.1")

    assert permalink == "https://slack.example/thread"


@pytest.mark.asyncio
async def test_get_permalink_rejects_missing_permalink() -> None:
    client = SlackMCPClient(
        FakeInvoker({"permalink": {}}),
        search_tool="search",
        read_tool="read",
        permalink_tool="permalink",
    )

    with pytest.raises(MCPClientError):
        await client.get_permalink("C123", "1710.1")


@pytest.mark.asyncio
async def test_resolves_tool_name_from_catalog_when_configured_name_missing() -> None:
    invoker = FakeInvoker(
        {
            "search_messages_v2": {
                "messages": [
                    {
                        "channel": {"id": "C123"},
                        "ts": "1710.1",
                        "thread_ts": "1710.1",
                        "text": "hello",
                    }
                ]
            }
        },
        tools=[
            {
                "name": "search_messages_v2",
                "description": "Search messages and channels in Slack",
            }
        ],
    )
    client = SlackMCPClient(
        invoker,
        search_tool="search_messages",
        read_tool="read_thread",
        permalink_tool="chat_getPermalink",
    )

    hits = await client.search_threads('"<@U123>"')

    assert len(hits) == 1
    assert invoker.calls[0][0] == "search_messages_v2"


@pytest.mark.asyncio
async def test_search_threads_parses_embedded_content_text_payload() -> None:
    invoker = FakeInvoker(
        {
            "slack_search_public_and_private": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "results": (
                                    "# Search Results\n\n"
                                    "### Result 1 of 1\n"
                                    "Channel: #tmp (ID: C123)\n"
                                    "Message_ts: 1710.1\n"
                                    "Permalink: [link](https://slack.example/p/1?thread_ts=1710.2)\n"
                                    "Text:\nhello there\n"
                                )
                            }
                        ),
                    }
                ]
            }
        },
        tools=[
            {
                "name": "slack_search_public_and_private",
                "description": "Search messages and files in all channels",
            }
        ],
    )
    client = SlackMCPClient(
        invoker,
        search_tool="search_messages",
        read_tool="read_thread",
        permalink_tool="chat_getPermalink",
    )

    hits = await client.search_threads("hello", limit=1)

    assert len(hits) == 1
    assert hits[0].channel_id == "C123"
    assert hits[0].thread_ts == "1710.2"
    assert hits[0].text == "hello there"


@pytest.mark.asyncio
async def test_read_thread_parses_embedded_content_text_payload() -> None:
    invoker = FakeInvoker(
        {
            "slack_read_thread": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "messages": (
                                    "=== THREAD PARENT MESSAGE ===\n"
                                    "From: Alice (U1)\n"
                                    "Time: 2026-03-26 10:00:00 KST\n"
                                    "Message TS: 1710.1\n"
                                    "Root text <@U123|Tony>\n"
                                    "Reactions: loading (1)\n\n"
                                    "--- Reply 1 of 1 ---\n"
                                    "From: Bob (U2)\n"
                                    "Time: 2026-03-26 10:01:00 KST\n"
                                    "Message TS: 1710.2\n"
                                    "Reply text\n"
                                    "Files: image.png\n"
                                )
                            }
                        ),
                    }
                ]
            }
        },
        tools=[
            {
                "name": "slack_read_thread",
                "description": "Read a thread from Slack",
            }
        ],
    )
    client = SlackMCPClient(
        invoker,
        search_tool="search_messages",
        read_tool="read_thread",
        permalink_tool="chat_getPermalink",
    )

    thread = await client.read_thread("C123", "1710.1")

    assert len(thread.messages) == 2
    assert thread.messages[0].user_id == "U1"
    assert thread.messages[0].mentions == ("U123",)
    assert thread.messages[0].reactions[0].name == "loading"
    assert thread.messages[1].text == "Reply text"
