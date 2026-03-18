from __future__ import annotations

from slack_assistant.formatter import format_summary
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
