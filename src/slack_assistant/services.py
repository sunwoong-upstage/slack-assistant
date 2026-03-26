from __future__ import annotations

import logging
from dataclasses import replace
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
from .relevance import dedupe_threads, thread_relevance_reasons
from .upstage_client import UpstageClient

logger = logging.getLogger(__name__)


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
        return await self._summarize_threads(relevant_threads)

    async def _summarize_threads(self, threads: list[SlackThread]) -> list[ThreadSummary]:
        summaries: list[ThreadSummary] = []
        for thread in dedupe_threads(threads):
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
        cursor_dt = _slack_ts_to_datetime(cursor) if cursor else None
        logger.info(
            "[digest] start user=%s schedule=%s timezone=%s "
            "now=%s cursor=%s cursor_dt=%s watched=%s",
            preferences.user_id,
            schedule.schedule_id,
            schedule.timezone,
            delivered_at.isoformat(),
            cursor,
            cursor_dt.isoformat() if cursor_dt else None,
            preferences.watched_reactions,
        )
        candidate_threads = await self._discover_daily_digest_threads(
            preferences,
            schedule,
            now=delivered_at,
        )
        summaries = await self._summarize_threads(candidate_threads)
        logger.info(
            "[digest] complete user=%s candidate_threads=%s summaries=%s",
            preferences.user_id,
            len(candidate_threads),
            len(summaries),
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
        queries.extend(
            f'hasmy::{reaction.strip(":")}:'
            for reaction in preferences.watched_reactions
            if reaction.strip(":")
        )
        return tuple(dict.fromkeys(query for query in queries if query))

    @staticmethod
    def build_digest_discovery_queries(
        preferences: UserPreferences,
    ) -> tuple[tuple[str, str], ...]:
        queries: list[tuple[str, str]] = [("direct_mention", f'"<@{preferences.user_id}>"')]
        queries.extend(
            ("watched_reaction", f'hasmy::{reaction.strip(":")}:')
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
    ) -> list[SlackThread]:
        window_start, window_end = _local_day_window(schedule.timezone, now)
        logger.info(
            "[digest] window user=%s start=%s end=%s mode=whole_local_day",
            preferences.user_id,
            window_start.isoformat(),
            window_end.isoformat(),
        )

        mention_thread_keys: set[tuple[str, str]] = set()
        reaction_thread_keys: set[tuple[str, str]] = set()
        thread_candidates: dict[tuple[str, str], SearchHit] = {}

        for query_type, query in self.build_digest_discovery_queries(preferences):
            hits = await self._search_hits_for_day(
                query,
                window_start=window_start,
                window_end=window_end,
            )
            for hit in hits:
                key = (hit.channel_id, hit.thread_ts)
                if query_type == "direct_mention":
                    mention_thread_keys.add(key)
                    thread_candidates.setdefault(key, hit)
                    continue

                reaction_thread_keys.add(key)
                thread_candidates.setdefault(key, hit)
            logger.info(
                "[digest] query user=%s type=%s query=%s in_today=%s candidates=%s",
                preferences.user_id,
                query_type,
                query,
                len(hits),
                len(thread_candidates),
            )

        matched_threads: list[SlackThread] = []
        for key, hit in thread_candidates.items():
            thread = await self._mcp_client.read_thread(hit.channel_id, hit.thread_ts)
            if thread.permalink is None and hit.permalink:
                thread = replace(thread, permalink=hit.permalink)
            if _looks_like_digest_thread(thread):
                logger.info(
                    "[digest] skipped user=%s key=%s reason=self_digest activity_ts=%s",
                    preferences.user_id,
                    key,
                    thread.last_activity_ts or thread.thread_ts,
                )
                continue
            if key in mention_thread_keys:
                matched_threads.append(thread)
                logger.info(
                    "[digest] matched user=%s key=%s reason=direct_mention "
                    "messages=%s last_activity=%s",
                    preferences.user_id,
                    key,
                    len(thread.messages),
                    thread.last_activity_ts,
                )
                continue

            if key in reaction_thread_keys:
                matched_threads.append(thread)
                logger.info(
                    "[digest] matched user=%s key=%s reason=watched_reaction "
                    "messages=%s last_activity=%s",
                    preferences.user_id,
                    key,
                    len(thread.messages),
                    thread.last_activity_ts,
                )
                continue

            logger.info(
                "[digest] skipped user=%s key=%s direct_mention_key=%s "
                "watched_key=%s activity_ts=%s",
                preferences.user_id,
                key,
                key in mention_thread_keys,
                key in reaction_thread_keys,
                thread.last_activity_ts or thread.thread_ts,
            )
        deduped = dedupe_threads(matched_threads)
        logger.info(
            "[digest] deduped user=%s matched=%s deduped=%s",
            preferences.user_id,
            len(matched_threads),
            len(deduped),
        )
        return deduped

    async def _search_hits_for_day(
        self,
        query: str,
        *,
        window_start: datetime,
        window_end: datetime,
        page_limit: int = 20,
        max_pages: int = 10,
    ) -> list[SearchHit]:
        collected: list[SearchHit] = []
        seen: set[tuple[str, str, str]] = set()
        cursor: str | None = None

        for _ in range(max_pages):
            page = await self._mcp_client.search_threads_page(
                query,
                limit=page_limit,
                cursor=cursor,
                sort="timestamp",
                sort_dir="desc",
            )
            if not page.hits:
                break

            oldest_hit_dt: datetime | None = None
            for hit in page.hits:
                hit_dt = _slack_ts_to_datetime(hit.message_ts)
                oldest_hit_dt = hit_dt
                if hit_dt < window_start or hit_dt > window_end:
                    continue
                key = (hit.channel_id, hit.thread_ts, hit.message_ts)
                if key in seen:
                    continue
                seen.add(key)
                collected.append(hit)

            if page.next_cursor is None:
                break
            if oldest_hit_dt is not None and oldest_hit_dt < window_start:
                break
            cursor = page.next_cursor

        return collected


def _local_day_window(timezone: str, now: datetime) -> tuple[datetime, datetime]:
    local_now = now.astimezone(ZoneInfo(timezone))
    local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return (local_start.astimezone(UTC), now)


def _looks_like_digest_thread(thread: SlackThread) -> bool:
    root = thread.root_message
    if root is None:
        return False
    return root.text.lstrip().startswith("*Slack 다이제스트")


def _slack_ts_to_datetime(value: str) -> datetime:
    return datetime.fromtimestamp(float(value), tz=UTC)


def _datetime_to_slack_ts(value: datetime) -> str:
    return f"{value.timestamp():.6f}"
