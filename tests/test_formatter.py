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

    assert rendered.startswith("*Slack 다이제스트 — Mon, Mar 23*")
    assert "오늘 매칭된 스레드 2개" in rendered
    assert "1. Ship the digest runner" in rendered
    assert "   <https://slack.example/1|링크>" in rendered
    assert "2. Review the emoji path" in rendered
    assert "   <https://slack.example/2|링크>" in rendered


def test_format_digest_truncates_with_overflow_count() -> None:
    rendered = format_digest(
        [
            ThreadSummary(
                headline=f"Thread {index}",
                bullets=(),
                permalink=f"https://slack.example/{index}",
            )
            for index in range(1, 80)
        ],
        timezone="Asia/Seoul",
        delivered_at=datetime(2026, 3, 23, 9, 0, tzinfo=UTC),
    )

    assert rendered.startswith("*Slack 다이제스트 — Mon, Mar 23*")
    assert "오늘 매칭된 스레드 79개" in rendered
    assert "… 외 " in rendered


def test_format_empty_digest_mentions_no_matches() -> None:
    rendered = format_empty_digest(
        timezone="Asia/Seoul",
        delivered_at=datetime(2026, 3, 23, 9, 0, tzinfo=UTC),
    )

    assert rendered.startswith("*Slack 다이제스트 — Mon, Mar 23*")
    assert "오늘은 직접 멘션되었거나 감시 이모지와 매칭된 스레드가 없습니다." in rendered
