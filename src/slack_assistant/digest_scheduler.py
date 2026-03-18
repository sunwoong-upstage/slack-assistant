from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from .models import DigestSchedule, SlackThread


class DigestScheduler:
    @staticmethod
    def next_run(schedule: DigestSchedule, *, after: datetime | None = None) -> datetime:
        after = after or datetime.now(UTC)
        tz = ZoneInfo(schedule.timezone)
        local_after = after.astimezone(tz)
        candidate = local_after.replace(
            hour=schedule.hour,
            minute=schedule.minute,
            second=0,
            microsecond=0,
        )
        if candidate <= local_after:
            candidate += timedelta(days=1)
        if schedule.days_of_week:
            allowed = set(schedule.days_of_week)
            while candidate.weekday() not in allowed:
                candidate += timedelta(days=1)
        return candidate.astimezone(UTC)

    @staticmethod
    def advance_cursor(existing_cursor: str | None, threads: list[SlackThread]) -> str | None:
        latest = existing_cursor
        for thread in threads:
            candidate = thread.last_activity_ts or thread.thread_ts
            if latest is None or candidate > latest:
                latest = candidate
        return latest
