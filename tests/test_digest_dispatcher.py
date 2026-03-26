from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
from cryptography.fernet import Fernet

from slack_assistant.config import load_config
from slack_assistant.digest_dispatcher import ScheduledDigestDispatcher
from slack_assistant.models import (
    DigestResult,
    DigestSchedule,
    MCPTokenSet,
    ThreadSummary,
    UserPreferences,
)
from slack_assistant.store import EncryptedJSONStore


class FakeClient:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def chat_postMessage(self, *, channel: str, text: str) -> None:  # noqa: N802
        self.messages.append((channel, text))


class FakeDigestService:
    def __init__(self, result: DigestResult | None = None, *, raise_error: bool = False) -> None:
        self._result = result
        self._raise_error = raise_error

    async def summarize_daily_digest(
        self,
        preferences: UserPreferences,
        schedule: DigestSchedule,
        *,
        now: datetime | None = None,
        cursor: str | None = None,
    ) -> DigestResult:
        if self._raise_error:
            raise RuntimeError("boom")
        assert self._result is not None
        return self._result


class MCPStatusErrorService:
    async def summarize_daily_digest(
        self,
        preferences: UserPreferences,
        schedule: DigestSchedule,
        *,
        now: datetime | None = None,
        cursor: str | None = None,
    ) -> DigestResult:
        raise httpx.HTTPStatusError(
            "bad request",
            request=httpx.Request("POST", "https://mcp.slack.com/mcp"),
            response=httpx.Response(400),
        )


def _config(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("SLACK_STATE_SECRET", "secret")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-123")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "signing-secret")
    monkeypatch.setenv("SLACK_OAUTH_CLIENT_ID", "123")
    monkeypatch.setenv("APP_BASE_URL", "https://app.example.com")
    monkeypatch.setenv("STORE_ENCRYPTION_KEY", Fernet.generate_key().decode("utf-8"))
    monkeypatch.setenv("UPSTAGE_API_KEY", "upstage-key")
    monkeypatch.setenv("STORE_PATH", str(tmp_path / "store.json"))
    monkeypatch.setenv("SLACK_DEFAULT_DELIVERY_SURFACE", "app_home")
    return load_config()


def test_dispatcher_sends_dm_and_advances_cursor(monkeypatch, tmp_path: Path) -> None:
    config = _config(monkeypatch, tmp_path)
    store = EncryptedJSONStore(config.store_path, encryption_key=config.store_encryption_key)
    store.save_tokens("U123", MCPTokenSet(access_token="xoxp-123"))
    store.save_preferences(
        UserPreferences(
            user_id="U123",
            watched_reactions=("loading",),
            digest_schedules=(
                DigestSchedule(
                    schedule_id="daily",
                    hour=18,
                    minute=0,
                    timezone="UTC",
                    days_of_week=(0, 1, 2, 3, 4, 5, 6),
                ),
            ),
        )
    )
    client = FakeClient()
    dispatcher = ScheduledDigestDispatcher(
        config,
        store,
        lambda token: FakeDigestService(
            DigestResult(
                schedule=DigestSchedule(
                    schedule_id="daily",
                    hour=18,
                    minute=0,
                    timezone="UTC",
                    days_of_week=(0, 1, 2, 3, 4, 5, 6),
                ),
                delivered_at=datetime(2026, 3, 23, 18, 0, tzinfo=UTC),
                thread_summaries=(
                    ThreadSummary(
                        headline="Decision: ship",
                        bullets=("QA is green",),
                        permalink="https://slack.example/thread",
                    ),
                ),
                next_cursor="1774288800.000000",
            )
        ),
        client,
    )

    delivered = dispatcher.run_pending(now=datetime(2026, 3, 23, 18, 5, tzinfo=UTC))

    assert delivered == [("U123", "daily")]
    assert client.messages[0][0] == "U123"
    assert "Slack 다이제스트" in client.messages[0][1]
    assert store.load_cursor("U123", "daily") == "1774288800.000000"


def test_dispatcher_sends_no_activity_dm(monkeypatch, tmp_path: Path) -> None:
    config = _config(monkeypatch, tmp_path)
    store = EncryptedJSONStore(config.store_path, encryption_key=config.store_encryption_key)
    store.save_tokens("U123", MCPTokenSet(access_token="xoxp-123"))
    store.save_preferences(
        UserPreferences(
            user_id="U123",
            digest_schedules=(
                DigestSchedule(
                    schedule_id="daily",
                    hour=18,
                    minute=0,
                    timezone="UTC",
                    days_of_week=(0, 1, 2, 3, 4, 5, 6),
                ),
            ),
        )
    )
    client = FakeClient()
    dispatcher = ScheduledDigestDispatcher(
        config,
        store,
        lambda token: FakeDigestService(
            DigestResult(
                schedule=DigestSchedule(
                    schedule_id="daily",
                    hour=18,
                    minute=0,
                    timezone="UTC",
                    days_of_week=(0, 1, 2, 3, 4, 5, 6),
                ),
                delivered_at=datetime(2026, 3, 23, 18, 0, tzinfo=UTC),
                thread_summaries=(),
                next_cursor="1774288800.000000",
            )
        ),
        client,
    )

    dispatcher.run_pending(now=datetime(2026, 3, 23, 18, 5, tzinfo=UTC))

    assert (
        "오늘은 직접 멘션되었거나 감시 이모지와 매칭된 스레드가 없습니다."
        in client.messages[0][1]
    )


def test_dispatcher_does_not_advance_cursor_on_failure(monkeypatch, tmp_path: Path) -> None:
    config = _config(monkeypatch, tmp_path)
    store = EncryptedJSONStore(config.store_path, encryption_key=config.store_encryption_key)
    store.save_tokens("U123", MCPTokenSet(access_token="xoxp-123"))
    store.save_preferences(
        UserPreferences(
            user_id="U123",
            digest_schedules=(
                DigestSchedule(
                    schedule_id="daily",
                    hour=18,
                    minute=0,
                    timezone="UTC",
                    days_of_week=(0, 1, 2, 3, 4, 5, 6),
                ),
            ),
        )
    )
    client = FakeClient()
    dispatcher = ScheduledDigestDispatcher(
        config,
        store,
        lambda token: FakeDigestService(raise_error=True),
        client,
    )

    delivered = dispatcher.run_pending(now=datetime(2026, 3, 23, 18, 5, tzinfo=UTC))

    assert delivered == []
    assert store.load_cursor("U123", "daily") is None
    assert store.load_tokens("U123") is not None


def test_dispatcher_clears_bad_tokens_and_prompts_reconnect(monkeypatch, tmp_path: Path) -> None:
    config = _config(monkeypatch, tmp_path)
    store = EncryptedJSONStore(config.store_path, encryption_key=config.store_encryption_key)
    store.save_tokens("U123", MCPTokenSet(access_token="xoxp-123"))
    store.save_preferences(
        UserPreferences(
            user_id="U123",
            digest_schedules=(
                DigestSchedule(
                    schedule_id="daily",
                    hour=18,
                    minute=0,
                    timezone="UTC",
                    days_of_week=(0, 1, 2, 3, 4, 5, 6),
                ),
            ),
        )
    )
    client = FakeClient()
    dispatcher = ScheduledDigestDispatcher(
        config,
        store,
        lambda token: MCPStatusErrorService(),
        client,
    )

    delivered = dispatcher.run_pending(now=datetime(2026, 3, 23, 18, 5, tzinfo=UTC))

    assert delivered == []
    assert store.load_tokens("U123") is None
    assert "Slack 권한 연결" in client.messages[0][1]
