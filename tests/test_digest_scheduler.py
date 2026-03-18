from __future__ import annotations

from datetime import UTC, datetime

from slack_assistant.digest_scheduler import DigestScheduler
from slack_assistant.models import DigestSchedule, SlackThread


def test_next_run_respects_timezone_and_future_window() -> None:
    schedule = DigestSchedule(schedule_id="daily", hour=18, minute=0, timezone="Asia/Seoul")
    after = datetime(2026, 3, 18, 8, 30, tzinfo=UTC)  # 17:30 KST

    next_run = DigestScheduler.next_run(schedule, after=after)

    assert next_run == datetime(2026, 3, 18, 9, 0, tzinfo=UTC)


def test_advance_cursor_uses_latest_thread_timestamp() -> None:
    threads = [
        SlackThread(channel_id="C1", thread_ts="1710.1", last_activity_ts="1710.2", messages=()),
        SlackThread(channel_id="C2", thread_ts="1710.3", last_activity_ts="1710.4", messages=()),
    ]

    assert DigestScheduler.advance_cursor("1710.0", threads) == "1710.4"
