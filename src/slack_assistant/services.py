from __future__ import annotations

import logging
import re
from dataclasses import replace
from datetime import UTC, datetime
from html import unescape
from urllib.parse import parse_qs
from zoneinfo import ZoneInfo

from .formatter import format_summary
from .mcp_client import SlackMCPClient
from .models import (
    DigestResult,
    DigestSchedule,
    GeneratedSummary,
    SearchHit,
    SlackMessage,
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

    async def summarize_thread(
        self,
        channel_id: str,
        thread_ts: str,
        *,
        selected_message_ts: str | None = None,
        selected_message_text: str | None = None,
        selected_message_permalink: str | None = None,
        selected_message_author_name: str | None = None,
    ) -> str:
        focus_ts: str | None = selected_message_ts or thread_ts
        fallback_thread = (
            SlackThread(
                channel_id=channel_id,
                thread_ts=focus_ts or thread_ts,
                messages=(
                    SlackMessage(
                        channel_id=channel_id,
                        ts=focus_ts or thread_ts,
                        text=selected_message_text,
                        author_name=selected_message_author_name,
                        permalink=selected_message_permalink,
                    ),
                ),
                permalink=selected_message_permalink,
                last_activity_ts=focus_ts or thread_ts,
            )
            if selected_message_text
            else None
        )
        try:
            thread = await self._mcp_client.read_thread(channel_id, thread_ts)
            thread = await self._resolve_linked_thread(thread)
        except Exception as error:  # noqa: BLE001
            if not _looks_like_mcp_no_text_error(error) or fallback_thread is None:
                raise
            thread = fallback_thread
        focus_ts = focus_ts if _thread_has_message(thread, focus_ts) else None
        permalink = await self._resolve_permalink(
            thread,
            message_ts=focus_ts or thread.thread_ts,
            preferred_permalink=selected_message_permalink,
        )
        summary = await self._upstage_client.summarize_thread(
            thread,
            selected_message_ts=focus_ts,
            selected_message_author_name=selected_message_author_name,
            selected_message_text_hint=selected_message_text,
        )
        author_name = _resolve_author_name(
            thread,
            focus_ts=focus_ts,
            fallback_author_name=selected_message_author_name,
        )
        rendered = ThreadSummary(
            headline=_render_author_grounded_headline(summary.focus_summary, author_name),
            bullets=_render_supporting_bullets(summary),
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

    async def _summarize_threads(
        self,
        threads: list[SlackThread],
        *,
        focus_hits_by_key: dict[tuple[str, str], SearchHit] | None = None,
    ) -> list[ThreadSummary]:
        summaries: list[ThreadSummary] = []
        for thread in dedupe_threads(threads):
            original_key = (thread.channel_id, thread.thread_ts)
            thread = await self._resolve_linked_thread(thread)
            focus_ts = None
            focus_hit = (
                focus_hits_by_key.get(original_key)
                if focus_hits_by_key is not None
                else None
            )
            if focus_hit is not None and _thread_has_message(thread, focus_hit.message_ts):
                focus_ts = focus_hit.message_ts
            permalink = await self._resolve_permalink(
                thread,
                message_ts=focus_ts or thread.thread_ts,
                preferred_permalink=(focus_hit.permalink if focus_hit else None),
            )
            generated = await self._upstage_client.summarize_thread(
                thread,
                selected_message_ts=focus_ts,
                selected_message_author_name=(focus_hit.author_name if focus_hit else None),
                selected_message_text_hint=(focus_hit.text if focus_hit else None),
            )
            author_name = _resolve_author_name(
                thread,
                focus_ts=focus_ts,
                fallback_author_name=(focus_hit.author_name if focus_hit else None),
            )
            summaries.append(
                ThreadSummary(
                    headline=_render_author_grounded_headline(generated.focus_summary, author_name),
                    bullets=_render_supporting_bullets(generated),
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
        candidate_threads, focus_hits_by_key = await self._discover_daily_digest_threads(
            preferences,
            schedule,
            now=delivered_at,
        )
        summaries = await self._summarize_threads(
            candidate_threads,
            focus_hits_by_key=focus_hits_by_key,
        )
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
    ) -> tuple[list[SlackThread], dict[tuple[str, str], SearchHit]]:
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
        focus_hits_by_key: dict[tuple[str, str], SearchHit] = {}

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
                    focus_hits_by_key.setdefault(key, hit)
                    continue

                reaction_thread_keys.add(key)
                thread_candidates.setdefault(key, hit)
                focus_hits_by_key.setdefault(key, hit)
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
            thread = await self._resolve_linked_thread(thread)
            focus_hits_by_key.setdefault((thread.channel_id, thread.thread_ts), hit)
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
        return deduped, focus_hits_by_key

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

    async def _resolve_linked_thread(self, thread: SlackThread) -> SlackThread:
        root = thread.root_message
        if root is None:
            return thread
        reference = _extract_slack_thread_reference(root.text)
        if reference is None:
            return thread
        channel_id, thread_ts, permalink = reference
        if channel_id == thread.channel_id and thread_ts == thread.thread_ts:
            return thread
        try:
            linked_thread = await self._mcp_client.read_thread(channel_id, thread_ts)
        except Exception as error:  # noqa: BLE001
            if not _looks_like_mcp_no_text_error(error):
                raise
            return replace(thread, permalink=permalink)
        if linked_thread.permalink is None:
            linked_thread = replace(linked_thread, permalink=permalink)
        return linked_thread

    async def _resolve_permalink(
        self,
        thread: SlackThread,
        *,
        message_ts: str,
        preferred_permalink: str | None = None,
    ) -> str:
        normalized_preferred = _normalize_permalink(preferred_permalink)
        if normalized_preferred:
            return normalized_preferred

        message_permalink = _message_permalink(thread, message_ts)
        if message_permalink:
            return message_permalink

        if message_ts == thread.thread_ts and thread.permalink:
            return thread.permalink

        try:
            return await self._mcp_client.get_permalink(thread.channel_id, message_ts)
        except Exception as error:  # noqa: BLE001
            if not _looks_like_mcp_no_text_error(error):
                raise
            if thread.permalink:
                return thread.permalink
            return _fallback_permalink_text(thread.channel_id, message_ts)


def _local_day_window(timezone: str, now: datetime) -> tuple[datetime, datetime]:
    local_now = now.astimezone(ZoneInfo(timezone))
    local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return (local_start.astimezone(UTC), now)


def _looks_like_digest_thread(thread: SlackThread) -> bool:
    root = thread.root_message
    if root is None:
        return False
    return root.text.lstrip().startswith("*Slack 다이제스트")


def _resolve_author_name(
    thread: SlackThread,
    *,
    focus_ts: str | None,
    fallback_author_name: str | None,
) -> str | None:
    if focus_ts is not None:
        for message in thread.messages:
            if message.ts == focus_ts:
                return message.author_name or message.user_id or fallback_author_name
    root = thread.root_message
    if root is not None:
        return root.author_name or root.user_id or fallback_author_name
    return fallback_author_name


def _render_author_grounded_headline(headline: str, author_name: str | None) -> str:
    normalized = headline.strip()
    if not author_name:
        return normalized
    if normalized.startswith(author_name):
        return normalized
    return f"{author_name}: {normalized}"


def _render_supporting_bullets(summary: GeneratedSummary) -> tuple[str, ...]:
    bullets = tuple(
        item
        for item in (
            summary.context_summary,
            summary.next_step_summary,
            summary.risk_summary,
        )
        if item
    )
    return bullets


def _thread_has_message(thread: SlackThread, ts: str | None) -> bool:
    if ts is None:
        return False
    return any(message.ts == ts for message in thread.messages)


def _looks_like_mcp_no_text_error(error: Exception) -> bool:
    return "no_text" in str(error)


def _normalize_permalink(permalink: str | None) -> str | None:
    if not permalink:
        return None
    normalized = permalink.strip()
    return normalized or None


def _message_permalink(thread: SlackThread, message_ts: str) -> str | None:
    for message in thread.messages:
        if message.ts != message_ts:
            continue
        normalized = _normalize_permalink(message.permalink)
        if normalized:
            return normalized
    return None


def _fallback_permalink_text(channel_id: str, message_ts: str) -> str:
    return f"(원본 링크를 가져오지 못함: {channel_id}/{message_ts})"


def _extract_slack_thread_reference(text: str) -> tuple[str, str, str] | None:
    normalized = unescape(text)
    match = re.search(
        r"https://[A-Za-z0-9.-]+\.slack\.com/archives/(?P<channel>[A-Z0-9]+)/p(?P<message>\d{16})(?:\?(?P<query>[^>\s|]+))?",
        normalized,
    )
    if not match:
        return None
    permalink = match.group(0)
    query = parse_qs(match.group("query") or "")
    message_ts = _slack_permalink_message_ts_to_slack_ts(match.group("message"))
    thread_ts = query.get("thread_ts", [message_ts])[0]
    return (match.group("channel"), thread_ts, permalink)


def _slack_permalink_message_ts_to_slack_ts(value: str) -> str:
    return f"{value[:-6]}.{value[-6:]}"


def _slack_ts_to_datetime(value: str) -> datetime:
    return datetime.fromtimestamp(float(value), tz=UTC)


def _datetime_to_slack_ts(value: datetime) -> str:
    return f"{value.timestamp():.6f}"
