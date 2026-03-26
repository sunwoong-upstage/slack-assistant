from __future__ import annotations

from .models import SlackMessage, SlackThread, UserPreferences


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def message_has_direct_mention(message: SlackMessage, preferences: UserPreferences) -> bool:
    message_text = _normalize(message.text)
    if preferences.user_id in message.mentions:
        return True
    return bool(
        preferences.user_handle and f"@{preferences.user_handle.lower()}" in message_text
    )


def message_has_team_alias(message: SlackMessage, preferences: UserPreferences) -> bool:
    aliases = {alias.lower() for alias in preferences.aliases}
    if not aliases:
        return False
    message_text = _normalize(message.text)
    return any(alias in message_text for alias in aliases)


def message_has_watched_reaction(message: SlackMessage, preferences: UserPreferences) -> bool:
    watched_reactions = {reaction.lower().strip(":") for reaction in preferences.watched_reactions}
    if not watched_reactions:
        return False
    return any(
        reaction.name.lower().strip(":") in watched_reactions
        and (not reaction.user_ids or preferences.user_id in reaction.user_ids)
        for reaction in message.reactions
    )


def thread_relevance_reasons(
    thread: SlackThread,
    preferences: UserPreferences,
    *,
    include_aliases: bool = True,
) -> tuple[str, ...]:

    reasons: set[str] = set()
    for message in thread.messages:
        if message_has_direct_mention(message, preferences):
            reasons.add("direct_mention")
        if include_aliases and message_has_team_alias(message, preferences):
            reasons.add("team_alias")
        if message_has_watched_reaction(message, preferences):
            reasons.add("watched_reaction")

    return tuple(sorted(reasons))


def is_thread_relevant(
    thread: SlackThread,
    preferences: UserPreferences,
    *,
    include_aliases: bool = True,
) -> bool:
    return bool(thread_relevance_reasons(thread, preferences, include_aliases=include_aliases))


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
