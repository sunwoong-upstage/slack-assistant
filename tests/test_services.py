from __future__ import annotations

from datetime import UTC, datetime

import pytest

from slack_assistant.models import (
    DigestResult,
    DigestSchedule,
    GeneratedSummary,
    MessageReaction,
    SearchHit,
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


class FakeDigestMCPClient:
    def __init__(
        self,
        *,
        search_results: dict[str, list[SearchHit]],
        threads: dict[tuple[str, str], SlackThread],
    ) -> None:
        self._search_results = search_results
        self._threads = threads

    async def search_threads(self, query: str, *, limit: int = 20) -> list[SearchHit]:
        return self._search_results.get(query, [])[:limit]

    async def read_thread(self, channel_id: str, thread_ts: str) -> SlackThread:
        return self._threads[(channel_id, thread_ts)]

    async def get_permalink(self, channel_id: str, message_ts: str) -> str:
        return f"https://slack.example/{channel_id}/{message_ts}"


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


def test_build_discovery_queries_can_skip_aliases() -> None:
    queries = SlackAssistantService.build_discovery_queries(
        UserPreferences(user_id="U123", aliases=("team-edu",), watched_reactions=(":eyes:",)),
        include_aliases=False,
    )

    assert queries == ('"<@U123>"', '":eyes:"')


@pytest.mark.asyncio
async def test_summarize_daily_digest_dedupes_and_suppresses_aliases() -> None:
    now = datetime(2026, 3, 23, 9, 0, tzinfo=UTC)
    mention_thread = SlackThread(
        channel_id="C1",
        thread_ts="1774254600.000100",
        last_activity_ts="1774254600.000200",
        messages=(
            SlackMessage(
                channel_id="C1",
                ts="1774254600.000100",
                text="Hi <@U123>",
                user_id="U9",
                mentions=("U123",),
                reactions=(MessageReaction(name="loading", user_ids=("U123",)),),
            ),
        ),
    )
    reaction_thread = SlackThread(
        channel_id="C2",
        thread_ts="1774254000.000100",
        last_activity_ts="1774255800.000100",
        messages=(
            SlackMessage(
                channel_id="C2",
                ts="1774250000.000100",
                text="Old thread",
                user_id="U8",
                reactions=(MessageReaction(name="loading", user_ids=("U123",)),),
            ),
        ),
    )
    old_alias_thread = SlackThread(
        channel_id="C3",
        thread_ts="1774170000.000100",
        last_activity_ts="1774170000.000100",
        messages=(
            SlackMessage(
                channel_id="C3",
                ts="1774170000.000100",
                text="team-edu only",
                user_id="U7",
            ),
        ),
    )
    service = SlackAssistantService(
        mcp_client=FakeDigestMCPClient(
            search_results={
                '"<@U123>"': [
                    SearchHit(
                        channel_id="C1",
                        message_ts="1774254600.000100",
                        thread_ts="1774254600.000100",
                        text="Hi <@U123>",
                    ),
                ],
                '":loading:"': [
                    SearchHit(
                        channel_id="C1",
                        message_ts="1774254600.000100",
                        thread_ts="1774254600.000100",
                        text="Hi <@U123>",
                    ),
                    SearchHit(
                        channel_id="C2",
                        message_ts="1774250000.000100",
                        thread_ts="1774254000.000100",
                        text="Old thread",
                    ),
                    SearchHit(
                        channel_id="C3",
                        message_ts="1774170000.000100",
                        thread_ts="1774170000.000100",
                        text="team-edu only",
                    ),
                ],
            },
            threads={
                ("C1", "1774254600.000100"): mention_thread,
                ("C2", "1774254000.000100"): reaction_thread,
                ("C3", "1774170000.000100"): old_alias_thread,
            },
        ),
        upstage_client=FakeUpstageClient(),
    )

    result = await service.summarize_daily_digest(
        UserPreferences(
            user_id="U123",
            user_handle="sunwoong",
            aliases=("team-edu",),
            watched_reactions=("loading",),
        ),
        DigestSchedule(
            schedule_id="daily",
            hour=18,
            minute=0,
            timezone="UTC",
            days_of_week=(0, 1, 2, 3, 4, 5, 6),
        ),
        now=now,
    )

    assert isinstance(result, DigestResult)
    assert [summary.permalink for summary in result.thread_summaries] == [
        "https://slack.example/C1/1774254600.000100",
        "https://slack.example/C2/1774254000.000100",
    ]
    assert result.next_cursor == "1774256400.000000"
