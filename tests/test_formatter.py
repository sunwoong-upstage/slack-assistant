from __future__ import annotations

from datetime import UTC, datetime

from slack_assistant.formatter import format_digest, format_empty_digest, format_summary
from slack_assistant.models import ThreadSummary


def test_format_summary_limits_bullets_and_appends_permalink() -> None:
    rendered = format_summary(
        ThreadSummary(
            headline="Launch blocked on final legal approval",
            bullets=(
                "Need legal sign-off",
                "Finance needs a revised date",
                "Owner will update roadmap",
                "drop me",
            ),
            permalink="https://slack.example/thread",
        )
    )

    assert rendered.count("•") == 3
    assert rendered.splitlines()[-1] == "https://slack.example/thread"
    assert rendered.startswith("[Launch blocked on final legal approval - thread]")


def test_format_summary_enforces_visible_budget() -> None:
    rendered = format_summary(
        ThreadSummary(
            headline="A" * 140,
            bullets=("B" * 250, "C" * 250, "D" * 250),
            permalink="https://slack.example/thread",
        ),
        max_visible_chars=120,
    )

    visible = "\n".join(rendered.splitlines()[:-1])
    assert len(visible) <= 120


def test_format_digest_renders_header_and_each_thread() -> None:
    rendered = format_digest(
        [
            ThreadSummary(
                headline="Ship the digest runner",
                bullets=("Scheduler is green",),
                permalink="https://slack.example/1",
            ),
            ThreadSummary(
                headline="Review the emoji path",
                bullets=("Need live workspace proof",),
                permalink="https://slack.example/2",
            ),
        ],
        timezone="Asia/Seoul",
        delivered_at=datetime(2026, 3, 23, 9, 0, tzinfo=UTC),
    )

    assert rendered.startswith("*Slack digest — Mon, Mar 23*")
    assert "2 matching threads today." in rendered
    assert rendered.count("https://slack.example/") == 2


def test_format_empty_digest_mentions_no_matches() -> None:
    rendered = format_empty_digest(
        timezone="Asia/Seoul",
        delivered_at=datetime(2026, 3, 23, 9, 0, tzinfo=UTC),
    )

    assert rendered.startswith("*Slack digest — Mon, Mar 23*")
    assert "No direct mentions or watched emoji threads matched today." in rendered
