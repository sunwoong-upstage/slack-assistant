from __future__ import annotations

import asyncio
from pathlib import Path

from cryptography.fernet import Fernet

from slack_assistant.config import load_config
from slack_assistant.models import MCPTokenSet
from slack_assistant.slack_app import (
    _run_summary_job,
    build_digest_settings_shortcut_handler,
    build_digest_settings_submission_handler,
    build_shortcut_handler,
)
from slack_assistant.store import EncryptedJSONStore


class FakeService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def summarize_thread(self, channel_id: str, thread_ts: str) -> str:
        self.calls.append((channel_id, thread_ts))
        await asyncio.sleep(0)
        return "summary text"


class FakeClient:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []
        self.views: list[tuple[str, dict[str, object]]] = []
        self.opened_views: list[tuple[str, dict[str, object]]] = []

    def chat_postMessage(self, *, channel: str, text: str) -> None:  # noqa: N802
        self.messages.append((channel, text))

    def views_publish(self, *, user_id: str, view: dict[str, object]) -> None:  # noqa: N802
        self.views.append((user_id, view))

    def views_open(self, *, trigger_id: str, view: dict[str, object]) -> None:  # noqa: N802
        self.opened_views.append((trigger_id, view))


def _config(monkeypatch, tmp_path: Path, *, delivery_surface: str = "dm"):
    monkeypatch.setenv("SLACK_STATE_SECRET", "secret")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-123")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "signing-secret")
    monkeypatch.setenv("SLACK_CLIENT_ID", "123")
    monkeypatch.setenv("APP_BASE_URL", "https://app.example.com")
    monkeypatch.setenv("STORE_ENCRYPTION_KEY", Fernet.generate_key().decode("utf-8"))
    monkeypatch.setenv("UPSTAGE_API_KEY", "upstage-key")
    monkeypatch.setenv("STORE_PATH", str(tmp_path / "store.json"))
    monkeypatch.setenv("SLACK_DEFAULT_DELIVERY_SURFACE", delivery_surface)
    return load_config()


def test_build_shortcut_handler_acks_before_dispatch(monkeypatch, tmp_path: Path) -> None:
    config = _config(monkeypatch, tmp_path)
    store = EncryptedJSONStore(config.store_path, encryption_key=config.store_encryption_key)
    client = FakeClient()
    acked: list[str] = []
    runner_calls: list[tuple[str, str, str]] = []

    def ack() -> None:
        acked.append("ack")

    def runner(config_arg, store_arg, service_factory, client_arg, user_id, channel_id, thread_ts):
        assert config_arg == config
        assert store_arg == store
        assert client_arg == client
        assert callable(service_factory)
        runner_calls.append((user_id, channel_id, thread_ts))

    handler = build_shortcut_handler(config, store, lambda token: FakeService(), runner=runner)
    handler(
        ack,
        {
            "channel": {"id": "C123"},
            "message": {"ts": "1710.1", "thread_ts": "1710.1"},
            "user": {"id": "U123"},
        },
        client,
    )

    assert acked == ["ack"]
    assert runner_calls == [("U123", "C123", "1710.1")]


def test_run_summary_job_delivers_dm_when_authorized(monkeypatch, tmp_path: Path) -> None:
    config = _config(monkeypatch, tmp_path, delivery_surface="dm")
    store = EncryptedJSONStore(config.store_path, encryption_key=config.store_encryption_key)
    store.save_tokens("U123", MCPTokenSet(access_token="xoxp-123"))
    client = FakeClient()
    service = FakeService()

    _run_summary_job(
        config,
        store,
        lambda token: service,
        client,
        "U123",
        "C123",
        "1710.1",
    )

    assert service.calls == [("C123", "1710.1")]
    assert client.messages == [("U123", "summary text")]
    assert client.views == []


def test_run_summary_job_delivers_app_home_when_configured(monkeypatch, tmp_path: Path) -> None:
    config = _config(monkeypatch, tmp_path, delivery_surface="app_home")
    store = EncryptedJSONStore(config.store_path, encryption_key=config.store_encryption_key)
    store.save_tokens("U123", MCPTokenSet(access_token="xoxp-123"))
    client = FakeClient()

    _run_summary_job(
        config,
        store,
        lambda token: FakeService(),
        client,
        "U123",
        "C123",
        "1710.1",
    )

    assert client.messages == []
    assert client.views[0][0] == "U123"


def test_run_summary_job_prompts_user_to_connect_auth_when_missing(
    monkeypatch, tmp_path: Path
) -> None:
    config = _config(monkeypatch, tmp_path, delivery_surface="dm")
    store = EncryptedJSONStore(config.store_path, encryption_key=config.store_encryption_key)
    client = FakeClient()

    _run_summary_job(
        config,
        store,
        lambda token: FakeService(),
        client,
        "U123",
        "C123",
        "1710.1",
    )

    assert client.views == []
    assert len(client.messages) == 1
    assert "Connect Slack access" in client.messages[0][1]


def test_settings_shortcut_opens_modal(monkeypatch, tmp_path: Path) -> None:
    config = _config(monkeypatch, tmp_path)
    store = EncryptedJSONStore(config.store_path, encryption_key=config.store_encryption_key)
    client = FakeClient()
    acked: list[str] = []

    handler = build_digest_settings_shortcut_handler(config, store)
    handler(
        lambda: acked.append("ack"),
        {"trigger_id": "trigger-123", "user": {"id": "U123"}},
        client,
    )

    assert acked == ["ack"]
    assert client.opened_views[0][0] == "trigger-123"
    assert client.opened_views[0][1]["callback_id"] == config.slack_digest_view_callback_id


def test_settings_submission_saves_preferences_and_confirms(monkeypatch, tmp_path: Path) -> None:
    config = _config(monkeypatch, tmp_path)
    store = EncryptedJSONStore(config.store_path, encryption_key=config.store_encryption_key)
    client = FakeClient()
    ack_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    handler = build_digest_settings_submission_handler(config, store)
    handler(
        lambda *args, **kwargs: ack_calls.append((args, kwargs)),
        {
            "user": {"id": "U123"},
            "view": {
                "state": {
                    "values": {
                        "weekdays": {
                            "selected_days": {
                                "selected_options": [{"value": "0"}, {"value": "2"}]
                            }
                        },
                        "time": {"time_input": {"value": "18:30"}},
                        "timezone": {"timezone_input": {"value": "Asia/Seoul"}},
                        "reactions": {"reactions_input": {"value": ":loading:, :eyes:"}},
                    }
                }
            },
        },
        client,
    )

    saved = store.load_preferences("U123")

    assert ack_calls == [((), {})]
    assert saved is not None
    assert saved.watched_reactions == ("loading", "eyes")
    assert saved.digest_schedules[0].days_of_week == (0, 2)
    assert saved.digest_schedules[0].hour == 18
    assert saved.digest_schedules[0].minute == 30
    assert saved.digest_schedules[0].timezone == "Asia/Seoul"
    assert "Saved weekday digest settings" in client.messages[0][1]


def test_settings_submission_rejects_invalid_timezone(monkeypatch, tmp_path: Path) -> None:
    config = _config(monkeypatch, tmp_path)
    store = EncryptedJSONStore(config.store_path, encryption_key=config.store_encryption_key)
    client = FakeClient()
    ack_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    handler = build_digest_settings_submission_handler(config, store)
    handler(
        lambda *args, **kwargs: ack_calls.append((args, kwargs)),
        {
            "user": {"id": "U123"},
            "view": {
                "state": {
                    "values": {
                        "weekdays": {
                            "selected_days": {
                                "selected_options": [{"value": "0"}, {"value": "2"}]
                            }
                        },
                        "time": {"time_input": {"value": "18:30"}},
                        "timezone": {"timezone_input": {"value": "Mars/Olympus"}},
                        "reactions": {"reactions_input": {"value": ":loading:"}},
                    }
                }
            },
        },
        client,
    )

    assert ack_calls == [
        (
            (),
            {
                "response_action": "errors",
                "errors": {"timezone": "Use a valid IANA timezone, such as Asia/Seoul."},
            },
        )
    ]
    assert store.load_preferences("U123") is None
    assert client.messages == []
