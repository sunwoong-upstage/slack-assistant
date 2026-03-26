from __future__ import annotations

from slack_assistant.models import MessageReaction, SlackMessage, SlackThread, UserPreferences
from slack_assistant.relevance import dedupe_threads, thread_relevance_reasons


def _thread(
    *, text: str, mentions: tuple[str, ...] = (), reactions: tuple[MessageReaction, ...] = ()
) -> SlackThread:
    return SlackThread(
        channel_id="C123",
        thread_ts="1710000000.000100",
        last_activity_ts="1710000000.000200",
        messages=(
            SlackMessage(
                channel_id="C123",
                ts="1710000000.000100",
                user_id="U999",
                text=text,
                mentions=mentions,
                reactions=reactions,
            ),
        ),
    )


def test_relevance_matches_direct_mentions_aliases_and_reactions() -> None:
    preferences = UserPreferences(
        user_id="U123",
        user_handle="sunwoong",
        aliases=("team-edu",),
        watched_reactions=(":eyes:",),
    )
    thread = _thread(
        text="Heads up @sunwoong and team-edu",
        mentions=("U123",),
        reactions=(MessageReaction(name="eyes", user_ids=("U123",)),),
    )

    reasons = thread_relevance_reasons(thread, preferences)

    assert reasons == ("direct_mention", "team_alias", "watched_reaction")


def test_dedupe_threads_keeps_latest_activity() -> None:
    older = _thread(text="first")
    newer = SlackThread(
        channel_id="C123",
        thread_ts="1710000000.000100",
        last_activity_ts="1710000000.000300",
        messages=older.messages,
    )

    deduped = dedupe_threads([older, newer])

    assert deduped == [newer]


def test_relevance_can_suppress_alias_matching() -> None:
    preferences = UserPreferences(
        user_id="U123",
        user_handle="sunwoong",
        aliases=("team-edu",),
        watched_reactions=(":eyes:",),
    )
    thread = _thread(
        text="Heads up @sunwoong and team-edu",
        mentions=("U123",),
        reactions=(MessageReaction(name="eyes", user_ids=("U123",)),),
    )

    reasons = thread_relevance_reasons(thread, preferences, include_aliases=False)

    assert reasons == ("direct_mention", "watched_reaction")
