from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from .formatter import format_summary
from .mcp_client import SlackMCPClient
from .models import (
    DigestResult,
    DigestSchedule,
    SearchHit,
    SlackThread,
    ThreadSummary,
    UserPreferences,
)
from .relevance import dedupe_threads, message_has_direct_mention, thread_relevance_reasons
from .upstage_client import UpstageClient


class SlackAssistantService:
    def __init__(self, *, mcp_client: SlackMCPClient, upstage_client: UpstageClient) -> None:
        self._mcp_client = mcp_client
        self._upstage_client = upstage_client

    async def summarize_thread(self, channel_id: str, thread_ts: str) -> str:
        thread = await self._mcp_client.read_thread(channel_id, thread_ts)
        permalink = thread.permalink or await self._mcp_client.get_permalink(channel_id, thread_ts)
        summary = await self._upstage_client.summarize_thread(thread)
        rendered = ThreadSummary(
            headline=summary.headline,
            bullets=summary.bullets,
            permalink=permalink,
        )
        return format_summary(rendered)

    async def summarize_relevant_threads(
        self,
        preferences: UserPreferences,
        threads: list[SlackThread],
        *,
        include_aliases: bool = True,
    ) -> list[ThreadSummary]:
        relevant_threads = [
            thread
            for thread in dedupe_threads(threads)
            if thread_relevance_reasons(thread, preferences, include_aliases=include_aliases)
        ]
        summaries: list[ThreadSummary] = []
        for thread in relevant_threads:
            permalink = thread.permalink or await self._mcp_client.get_permalink(
                thread.channel_id, thread.thread_ts
            )
            generated = await self._upstage_client.summarize_thread(thread)
            summaries.append(
                ThreadSummary(
                    headline=generated.headline,
                    bullets=generated.bullets,
                    permalink=permalink,
                )
            )
        return summaries

    async def summarize_daily_digest(
        self,
        preferences: UserPreferences,
        schedule: DigestSchedule,
        *,
        now: datetime | None = None,
        cursor: str | None = None,
    ) -> DigestResult:
        delivered_at = now or datetime.now(UTC)
        candidate_threads = await self._discover_daily_digest_threads(
            preferences,
            schedule,
            now=delivered_at,
            cursor=cursor,
        )
        summaries = await self.summarize_relevant_threads(
            preferences,
            candidate_threads,
            include_aliases=False,
        )
        return DigestResult(
            schedule=schedule,
            delivered_at=delivered_at,
            thread_summaries=tuple(summaries),
            next_cursor=_datetime_to_slack_ts(delivered_at),
        )

    @staticmethod
    def build_discovery_queries(
        preferences: UserPreferences,
        *,
        include_aliases: bool = True,
    ) -> tuple[str, ...]:
        queries: list[str] = [f'"<@{preferences.user_id}>"']
        if include_aliases:
            queries.extend(f'"{alias}"' for alias in preferences.aliases)
        queries.extend(f'":{reaction.strip(":")}:"' for reaction in preferences.watched_reactions)
        return tuple(dict.fromkeys(query for query in queries if query))

    @staticmethod
    def build_digest_discovery_queries(
        preferences: UserPreferences,
    ) -> tuple[tuple[str, str], ...]:
        queries: list[tuple[str, str]] = [("direct_mention", f'"<@{preferences.user_id}>"')]
        queries.extend(
            ("watched_reaction", f'":{reaction.strip(":")}:"')
            for reaction in preferences.watched_reactions
            if reaction.strip(":")
        )
        deduped: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for item in queries:
            if item in seen:
                continue
            seen.add(item)
            deduped.append(item)
        return tuple(deduped)

    async def _discover_daily_digest_threads(
        self,
        preferences: UserPreferences,
        schedule: DigestSchedule,
        *,
        now: datetime,
        cursor: str | None,
    ) -> list[SlackThread]:
        window_start, window_end = _local_day_window(schedule.timezone, now)
        cursor_dt = _slack_ts_to_datetime(cursor) if cursor else None

        mention_thread_keys: set[tuple[str, str]] = set()
        reaction_thread_keys: set[tuple[str, str]] = set()
        thread_candidates: dict[tuple[str, str], SearchHit] = {}

        for query_type, query in self.build_digest_discovery_queries(preferences):
            hits = await self._mcp_client.search_threads(query, limit=100)
            for hit in hits:
                key = (hit.channel_id, hit.thread_ts)
                hit_dt = _slack_ts_to_datetime(hit.message_ts)
                if query_type == "direct_mention":
                    if _is_in_window(hit_dt, window_start, window_end, cursor_dt):
                        mention_thread_keys.add(key)
                        thread_candidates.setdefault(key, hit)
                    continue

                reaction_thread_keys.add(key)
                thread_candidates.setdefault(key, hit)

        matched_threads: list[SlackThread] = []
        for key, hit in thread_candidates.items():
            thread = await self._mcp_client.read_thread(hit.channel_id, hit.thread_ts)
            reasons = set(thread_relevance_reasons(thread, preferences, include_aliases=False))
            direct_mention_matches = (
                key in mention_thread_keys
                and "direct_mention" in reasons
                and _thread_has_direct_mention_in_window(
                    thread,
                    preferences,
                    window_start,
                    window_end,
                    cursor_dt,
                )
            )
            if direct_mention_matches:
                matched_threads.append(thread)
                continue

            watched_reaction_matches = (
                key in reaction_thread_keys
                and "watched_reaction" in reasons
                and _thread_activity_in_window(thread, window_start, window_end, cursor_dt)
            )
            if watched_reaction_matches:
                matched_threads.append(thread)

        return dedupe_threads(matched_threads)


def _thread_has_direct_mention_in_window(
    thread: SlackThread,
    preferences: UserPreferences,
    window_start: datetime,
    window_end: datetime,
    cursor_dt: datetime | None,
) -> bool:
    for message in thread.messages:
        if not message_has_direct_mention(message, preferences):
            continue
        message_dt = _slack_ts_to_datetime(message.ts)
        if _is_in_window(message_dt, window_start, window_end, cursor_dt):
            return True
    return False


def _thread_activity_in_window(
    thread: SlackThread,
    window_start: datetime,
    window_end: datetime,
    cursor_dt: datetime | None,
) -> bool:
    activity_ts = thread.last_activity_ts or thread.thread_ts
    activity_dt = _slack_ts_to_datetime(activity_ts)
    return _is_in_window(activity_dt, window_start, window_end, cursor_dt)


def _local_day_window(timezone: str, now: datetime) -> tuple[datetime, datetime]:
    local_now = now.astimezone(ZoneInfo(timezone))
    local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return (local_start.astimezone(UTC), now)


def _is_in_window(
    value: datetime,
    window_start: datetime,
    window_end: datetime,
    cursor_dt: datetime | None,
) -> bool:
    if value < window_start or value > window_end:
        return False
    return not (cursor_dt is not None and value <= cursor_dt)


def _slack_ts_to_datetime(value: str) -> datetime:
    return datetime.fromtimestamp(float(value), tz=UTC)


def _datetime_to_slack_ts(value: datetime) -> str:
    return f"{value.timestamp():.6f}"
