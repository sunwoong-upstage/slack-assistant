from __future__ import annotations

from .formatter import format_summary
from .mcp_client import SlackMCPClient
from .models import SlackThread, ThreadSummary, UserPreferences
from .relevance import dedupe_threads, thread_relevance_reasons
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
    ) -> list[ThreadSummary]:
        relevant_threads = [
            thread
            for thread in dedupe_threads(threads)
            if thread_relevance_reasons(thread, preferences)
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

    @staticmethod
    def build_discovery_queries(preferences: UserPreferences) -> tuple[str, ...]:
        queries: list[str] = [f'"<@{preferences.user_id}>"']
        queries.extend(f'"{alias}"' for alias in preferences.aliases)
        queries.extend(f'":{reaction.strip(":")}:"' for reaction in preferences.watched_reactions)
        return tuple(dict.fromkeys(query for query in queries if query))
