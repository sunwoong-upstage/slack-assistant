from __future__ import annotations

from .models import SlackThread, UserPreferences


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def thread_relevance_reasons(thread: SlackThread, preferences: UserPreferences) -> tuple[str, ...]:
    user_mentions = {preferences.user_id}
    if preferences.user_handle:
        user_mentions.add(preferences.user_handle.lower())
    aliases = {alias.lower() for alias in preferences.aliases}
    watched_reactions = {reaction.lower().strip(":") for reaction in preferences.watched_reactions}

    reasons: set[str] = set()
    for message in thread.messages:
        message_text = _normalize(message.text)
        if preferences.user_id in message.mentions:
            reasons.add("direct_mention")
        if preferences.user_handle and f"@{preferences.user_handle.lower()}" in message_text:
            reasons.add("direct_mention")
        if any(alias in message_text for alias in aliases):
            reasons.add("team_alias")
        for reaction in message.reactions:
            if (
                reaction.name.lower().strip(":") in watched_reactions
                and (not reaction.user_ids or preferences.user_id in reaction.user_ids)
            ):
                reasons.add("watched_reaction")

    return tuple(sorted(reasons))


def is_thread_relevant(thread: SlackThread, preferences: UserPreferences) -> bool:
    return bool(thread_relevance_reasons(thread, preferences))


def dedupe_threads(threads: list[SlackThread]) -> list[SlackThread]:
    deduped: dict[tuple[str, str], SlackThread] = {}
    for thread in threads:
        key = (thread.channel_id, thread.thread_ts)
        current = deduped.get(key)
        if current is None:
            deduped[key] = thread
            continue
        current_ts = current.last_activity_ts or current.thread_ts
        candidate_ts = thread.last_activity_ts or thread.thread_ts
        if candidate_ts >= current_ts:
            deduped[key] = thread
    return list(deduped.values())
