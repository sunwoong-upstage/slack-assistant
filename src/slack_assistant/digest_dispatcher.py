from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from threading import Event
from typing import Protocol, TypeVar
from zoneinfo import ZoneInfo

from .config import AppConfig
from .digest_scheduler import DigestScheduler
from .formatter import format_digest, format_empty_digest
from .mcp_auth import MCPAuthError, build_authorize_url
from .models import DigestSchedule, UserPreferences
from .services import SlackAssistantService
from .store import EncryptedJSONStore

logger = logging.getLogger(__name__)


class DigestDeliveryClient(Protocol):
    def chat_postMessage(self, *, channel: str, text: str) -> object: ...  # noqa: N802


ServiceFactory = Callable[[str], SlackAssistantService]
NowFactory = Callable[[], datetime]
AwaitableT = TypeVar("AwaitableT")


class ScheduledDigestDispatcher:
    def __init__(
        self,
        config: AppConfig,
        store: EncryptedJSONStore,
        service_factory: ServiceFactory,
        client: DigestDeliveryClient,
        *,
        now_factory: NowFactory | None = None,
    ) -> None:
        self._config = config
        self._store = store
        self._service_factory = service_factory
        self._client = client
        self._now_factory = now_factory or (lambda: datetime.now(UTC))

    def run_forever(self, *, stop_event: Event | None = None) -> None:
        while True:
            if stop_event is not None and stop_event.is_set():
                return
            self.run_pending()
            if stop_event is None:
                time.sleep(self._config.scheduler_poll_seconds)
            else:
                stop_event.wait(self._config.scheduler_poll_seconds)

    def run_pending(self, *, now: datetime | None = None) -> list[tuple[str, str]]:
        current_time = now or self._now_factory()
        delivered: list[tuple[str, str]] = []
        for preferences in self._store.list_preferences():
            for schedule in preferences.digest_schedules:
                try:
                    if not self._is_schedule_due(preferences.user_id, schedule, now=current_time):
                        continue
                    if self._deliver_digest(preferences, schedule, now=current_time):
                        delivered.append((preferences.user_id, schedule.schedule_id))
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "Scheduled digest loop failed for %s/%s",
                        preferences.user_id,
                        schedule.schedule_id,
                    )
        return delivered

    def _deliver_digest(
        self,
        preferences: UserPreferences,
        schedule: DigestSchedule,
        *,
        now: datetime,
    ) -> bool:
        cursor = self._store.load_cursor(preferences.user_id, schedule.schedule_id)
        watermark = f"{now.timestamp():.6f}"
        token = self._store.load_tokens(preferences.user_id)
        if token is None:
            reminder_text = self._build_connect_text(preferences.user_id)
            if reminder_text is None:
                return False
            try:
                self._client.chat_postMessage(channel=preferences.user_id, text=reminder_text)
                self._store.save_cursor(preferences.user_id, schedule.schedule_id, watermark)
                return True
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Failed to send digest auth reminder for %s/%s",
                    preferences.user_id,
                    schedule.schedule_id,
                )
                return False

        try:
            result = self._run_async(
                self._service_factory(token.access_token).summarize_daily_digest(
                    preferences,
                    schedule,
                    now=now,
                    cursor=cursor,
                )
            )
            message_text = (
                format_digest(
                    result.thread_summaries,
                    timezone=schedule.timezone,
                    delivered_at=result.delivered_at,
                )
                if result.thread_summaries
                else format_empty_digest(
                    timezone=schedule.timezone,
                    delivered_at=result.delivered_at,
                )
            )
            self._client.chat_postMessage(channel=preferences.user_id, text=message_text)
            self._store.save_cursor(
                preferences.user_id,
                schedule.schedule_id,
                result.next_cursor or watermark,
            )
            logger.info(
                "Delivered scheduled digest to %s for %s",
                preferences.user_id,
                schedule.schedule_id,
            )
            return True
        except Exception:  # noqa: BLE001
            logger.exception(
                "Failed to deliver scheduled digest for %s/%s",
                preferences.user_id,
                schedule.schedule_id,
            )
            return False

    def _is_schedule_due(
        self,
        user_id: str,
        schedule: DigestSchedule,
        *,
        now: datetime,
    ) -> bool:
        local_now = now.astimezone(ZoneInfo(schedule.timezone))
        if schedule.days_of_week and local_now.weekday() not in set(schedule.days_of_week):
            return False
        scheduled_today = local_now.replace(
            hour=schedule.hour,
            minute=schedule.minute,
            second=0,
            microsecond=0,
        )
        if local_now < scheduled_today:
            return False

        cursor = self._store.load_cursor(user_id, schedule.schedule_id)
        if cursor is None:
            return True

        last_delivery = datetime.fromtimestamp(float(cursor), tz=UTC)
        return DigestScheduler.next_run(schedule, after=last_delivery) <= now

    def _build_connect_text(self, user_id: str) -> str | None:
        try:
            auth_url = build_authorize_url(self._config, user_id)
        except MCPAuthError:
            logger.exception("Unable to build Slack auth URL for scheduled digest")
            return None
        return (
            "Connect Slack access to receive scheduled digests: "
            f"<{auth_url}|Connect Slack access>"
        )

    @staticmethod
    def _run_async(coro: Awaitable[AwaitableT]) -> AwaitableT:
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(coro)
        finally:
            asyncio.set_event_loop(None)
            loop.close()
