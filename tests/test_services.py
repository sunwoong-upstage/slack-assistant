from __future__ import annotations

from datetime import UTC, datetime

import pytest

from slack_assistant.models import (
    DigestResult,
    DigestSchedule,
    GeneratedSummary,
    MessageReaction,
    SearchHit,
    SearchResultsPage,
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
        self.search_queries: list[str] = []
        self.permalink_calls: list[tuple[str, str]] = []

    async def search_threads(self, query: str, *, limit: int = 20) -> list[SearchHit]:
        self.search_queries.append(query)
        return self._search_results.get(query, [])[:limit]

    async def search_threads_page(
        self,
        query: str,
        *,
        limit: int = 20,
        cursor: str | None = None,
        sort: str = "timestamp",
        sort_dir: str = "desc",
    ) -> SearchResultsPage:
        self.search_queries.append(query)
        return SearchResultsPage(hits=tuple(self._search_results.get(query, [])[:limit]))

    async def read_thread(self, channel_id: str, thread_ts: str) -> SlackThread:
        return self._threads[(channel_id, thread_ts)]

    async def get_permalink(self, channel_id: str, message_ts: str) -> str:
        self.permalink_calls.append((channel_id, message_ts))
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
async def test_summarize_thread_follows_embedded_slack_permalink() -> None:
    wrapper_thread = SlackThread(
        channel_id="D1",
        thread_ts="1774509804.026719",
        messages=(
            SlackMessage(
                channel_id="D1",
                ts="1774509804.026719",
                user_id="U1",
                text=(
                    "please summarize "
                    "https://upstageai.slack.com/archives/C06UN27UXDL/"
                    "p1774427132706759?thread_ts=1773038895.126359&cid=C06UN27UXDL"
                ),
            ),
        ),
        permalink="https://slack.example/wrapper",
    )
    target_thread = SlackThread(
        channel_id="C06UN27UXDL",
        thread_ts="1773038895.126359",
        messages=(
            SlackMessage(
                channel_id="C06UN27UXDL",
                ts="1773038895.126359",
                user_id="U2",
                text="real target thread",
            ),
        ),
    )
    client = FakeDigestMCPClient(
        search_results={},
        threads={
            ("D1", "1774509804.026719"): wrapper_thread,
            ("C06UN27UXDL", "1773038895.126359"): target_thread,
        },
    )
    service = SlackAssistantService(mcp_client=client, upstage_client=FakeUpstageClient())

    rendered = await service.summarize_thread("D1", "1774509804.026719")

    assert rendered.endswith(
        "https://upstageai.slack.com/archives/C06UN27UXDL/"
        "p1774427132706759?thread_ts=1773038895.126359&cid=C06UN27UXDL"
    )


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

    assert queries == ('"<@U123>"', '"team-edu"', "hasmy::eyes:")


def test_build_discovery_queries_can_skip_aliases() -> None:
    queries = SlackAssistantService.build_discovery_queries(
        UserPreferences(user_id="U123", aliases=("team-edu",), watched_reactions=(":eyes:",)),
        include_aliases=False,
    )

    assert queries == ('"<@U123>"', "hasmy::eyes:")


def test_build_digest_discovery_queries_use_hasmy_reaction_search() -> None:
    queries = SlackAssistantService.build_digest_discovery_queries(
        UserPreferences(user_id="U123", watched_reactions=("loading",))
    )

    assert queries == (
        ("direct_mention", '"<@U123>"'),
        ("watched_reaction", "hasmy::loading:"),
    )


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
                        permalink="https://slack.example/C1/1774254600.000100",
                    ),
                ],
                "hasmy::loading:": [
                    SearchHit(
                        channel_id="C2",
                        message_ts="1774250000.000100",
                        thread_ts="1774254000.000100",
                        text="Old thread",
                        permalink="https://slack.example/C2/1774254000.000100",
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
    assert service._mcp_client.search_queries == ['"<@U123>"', "hasmy::loading:"]
    assert service._mcp_client.permalink_calls == []


@pytest.mark.asyncio
async def test_summarize_daily_digest_uses_whole_day_even_with_cursor() -> None:
    now = datetime(2026, 3, 23, 12, 0, tzinfo=UTC)
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
            },
            threads={
                ("C1", "1774254600.000100"): mention_thread,
            },
        ),
        upstage_client=FakeUpstageClient(),
    )

    result = await service.summarize_daily_digest(
        UserPreferences(user_id="U123"),
        DigestSchedule(
            schedule_id="daily",
            hour=21,
            minute=10,
            timezone="UTC",
            days_of_week=(0, 1, 2, 3, 4, 5, 6),
        ),
        now=now,
        cursor="1774259999.000000",
    )

    assert len(result.thread_summaries) == 1
    assert result.thread_summaries[0].permalink == "https://slack.example/C1/1774254600.000100"


@pytest.mark.asyncio
async def test_summarize_daily_digest_skips_previous_digest_messages() -> None:
    now = datetime(2026, 3, 23, 12, 0, tzinfo=UTC)
    digest_thread = SlackThread(
        channel_id="D1",
        thread_ts="1774254600.000100",
        last_activity_ts="1774254600.000200",
        messages=(
            SlackMessage(
                channel_id="D1",
                ts="1774254600.000100",
                text="*Slack 다이제스트 — Thu, Mar 23*\n오늘 매칭된 스레드 3개",
                user_id="B123",
            ),
        ),
    )
    service = SlackAssistantService(
        mcp_client=FakeDigestMCPClient(
            search_results={
                "hasmy::loading:": [
                    SearchHit(
                        channel_id="D1",
                        message_ts="1774254600.000100",
                        thread_ts="1774254600.000100",
                        text="digest",
                        permalink="https://slack.example/D1/1774254600.000100",
                    ),
                ],
            },
            threads={
                ("D1", "1774254600.000100"): digest_thread,
            },
        ),
        upstage_client=FakeUpstageClient(),
    )

    result = await service.summarize_daily_digest(
        UserPreferences(user_id="U123", watched_reactions=("loading",)),
        DigestSchedule(
            schedule_id="daily",
            hour=21,
            minute=10,
            timezone="UTC",
            days_of_week=(0, 1, 2, 3, 4, 5, 6),
        ),
        now=now,
    )

    assert result.thread_summaries == ()


@pytest.mark.asyncio
async def test_summarize_daily_digest_follows_embedded_slack_permalink() -> None:
    now = datetime(2026, 3, 26, 12, 0, tzinfo=UTC)
    wrapper_thread = SlackThread(
        channel_id="D1",
        thread_ts="1774509804.026719",
        messages=(
            SlackMessage(
                channel_id="D1",
                ts="1774509804.026719",
                text=(
                    "https://upstageai.slack.com/archives/C06UN27UXDL/"
                    "p1774427132706759?thread_ts=1773038895.126359&cid=C06UN27UXDL"
                ),
                user_id="U1",
            ),
        ),
        permalink="https://slack.example/wrapper",
    )
    target_thread = SlackThread(
        channel_id="C06UN27UXDL",
        thread_ts="1773038895.126359",
        messages=(
            SlackMessage(
                channel_id="C06UN27UXDL",
                ts="1773038895.126359",
                text="real target thread",
                user_id="U2",
            ),
        ),
    )
    service = SlackAssistantService(
        mcp_client=FakeDigestMCPClient(
            search_results={
                "hasmy::loading:": [
                    SearchHit(
                        channel_id="D1",
                        message_ts="1774509804.026719",
                        thread_ts="1774509804.026719",
                        text="wrapper",
                        permalink="https://slack.example/wrapper",
                    ),
                ],
            },
            threads={
                ("D1", "1774509804.026719"): wrapper_thread,
                ("C06UN27UXDL", "1773038895.126359"): target_thread,
            },
        ),
        upstage_client=FakeUpstageClient(),
    )

    result = await service.summarize_daily_digest(
        UserPreferences(user_id="U123", watched_reactions=("loading",)),
        DigestSchedule(
            schedule_id="daily",
            hour=21,
            minute=10,
            timezone="UTC",
            days_of_week=(0, 1, 2, 3, 4, 5, 6),
        ),
        now=now,
    )

    assert len(result.thread_summaries) == 1
    assert result.thread_summaries[0].permalink == (
        "https://upstageai.slack.com/archives/C06UN27UXDL/"
        "p1774427132706759?thread_ts=1773038895.126359&cid=C06UN27UXDL"
    )
