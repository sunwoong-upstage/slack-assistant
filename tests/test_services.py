from __future__ import annotations

import pytest

from slack_assistant.models import (
    GeneratedSummary,
    MessageReaction,
    SlackMessage,
    SlackThread,
    UserPreferences,
)
from slack_assistant.services import SlackAssistantService


class FakeMCPClient:
    def __init__(self, thread: SlackThread) -> None:
        self.thread = thread
        self.permalink_calls: list[tuple[str, str]] = []

    async def read_thread(self, channel_id: str, thread_ts: str) -> SlackThread:
        return self.thread

    async def get_permalink(self, channel_id: str, message_ts: str) -> str:
        self.permalink_calls.append((channel_id, message_ts))
        return "https://slack.example/thread"


class FakeUpstageClient:
    async def summarize_thread(self, thread: SlackThread) -> GeneratedSummary:
        return GeneratedSummary(
            headline="Decision: ship Friday",
            bullets=("Docs are ready", "QA is green"),
            raw_content="{}",
            model_used="solar-pro",
        )


@pytest.fixture
def relevant_thread() -> SlackThread:
    return SlackThread(
        channel_id="C123",
        thread_ts="1710.1",
        messages=(
            SlackMessage(
                channel_id="C123",
                ts="1710.1",
                user_id="U1",
                text="Ping @sunwoong and team-edu",
                mentions=("U123",),
                reactions=(MessageReaction(name="eyes", user_ids=("U123",)),),
            ),
        ),
    )


@pytest.mark.asyncio
async def test_summarize_thread_formats_output(relevant_thread: SlackThread) -> None:
    service = SlackAssistantService(
        mcp_client=FakeMCPClient(relevant_thread),
        upstage_client=FakeUpstageClient(),
    )

    rendered = await service.summarize_thread("C123", "1710.1")

    assert "Decision: ship Friday" in rendered
    assert rendered.endswith("https://slack.example/thread")


@pytest.mark.asyncio
async def test_summarize_relevant_threads_filters_irrelevant(relevant_thread: SlackThread) -> None:
    irrelevant = SlackThread(
        channel_id="C999",
        thread_ts="1710.2",
        messages=(SlackMessage(channel_id="C999", ts="1710.2", user_id="U2", text="FYI"),),
    )
    service = SlackAssistantService(
        mcp_client=FakeMCPClient(relevant_thread),
        upstage_client=FakeUpstageClient(),
    )

    summaries = await service.summarize_relevant_threads(
        UserPreferences(
            user_id="U123",
            user_handle="sunwoong",
            aliases=("team-edu",),
            watched_reactions=("eyes",),
        ),
        [relevant_thread, irrelevant],
    )

    assert len(summaries) == 1
    assert summaries[0].headline == "Decision: ship Friday"


def test_build_discovery_queries_contains_user_alias_and_reaction() -> None:
    queries = SlackAssistantService.build_discovery_queries(
        UserPreferences(user_id="U123", aliases=("team-edu",), watched_reactions=(":eyes:",))
    )

    assert queries == ('"<@U123>"', '"team-edu"', '":eyes:"')
