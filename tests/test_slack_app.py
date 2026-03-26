from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
from cryptography.fernet import Fernet

from slack_assistant.config import load_config
from slack_assistant.models import MCPTokenSet
from slack_assistant.slack_app import (
    _run_summary_job,
    build_app_home_opened_handler,
    build_digest_command_handler,
    build_digest_settings_shortcut_handler,
    build_digest_settings_submission_handler,
    build_open_digest_settings_action_handler,
    build_send_connect_link_action_handler,
    build_shortcut_handler,
)
from slack_assistant.store import EncryptedJSONStore


class FakeService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str | None, str | None]] = []

    async def summarize_thread(
        self,
        channel_id: str,
        thread_ts: str,
        *,
        selected_message_ts: str | None = None,
        selected_message_text: str | None = None,
        selected_message_permalink: str | None = None,
        selected_message_author_name: str | None = None,
    ) -> str:
        self.calls.append((channel_id, thread_ts, selected_message_ts, selected_message_text))
        await asyncio.sleep(0)
        return "summary text"


class FailingMCPService:
    async def summarize_thread(
        self,
        channel_id: str,
        thread_ts: str,
        *,
        selected_message_ts: str | None = None,
        selected_message_text: str | None = None,
        selected_message_permalink: str | None = None,
        selected_message_author_name: str | None = None,
    ) -> str:
        raise httpx.HTTPStatusError(
            "bad request",
            request=httpx.Request("POST", "https://mcp.slack.com/mcp"),
            response=httpx.Response(400),
        )


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
    monkeypatch.setenv("SLACK_OAUTH_CLIENT_ID", "123")
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
    runner_calls: list[tuple[str, str, str, str, str, str | None, str | None]] = []

    def ack() -> None:
        acked.append("ack")

    def runner(
        config_arg,
        store_arg,
        service_factory,
        client_arg,
        user_id,
        channel_id,
        thread_ts,
        selected_message_ts,
        selected_message_text,
        selected_message_permalink,
        selected_message_author_name,
    ):
        assert config_arg == config
        assert store_arg == store
        assert client_arg == client
        assert callable(service_factory)
        runner_calls.append(
            (
                user_id,
                channel_id,
                thread_ts,
                selected_message_ts,
                selected_message_text,
                selected_message_permalink,
                selected_message_author_name,
            )
        )

    handler = build_shortcut_handler(config, store, lambda token: FakeService(), runner=runner)
    handler(
        ack,
        {
            "channel": {"id": "C123"},
            "message": {
                "ts": "1710.1",
                "thread_ts": "1710.1",
                "text": "selected message",
                "permalink": "https://slack.example/p/17101",
            },
            "user": {"id": "U123"},
        },
        client,
    )

    assert acked == ["ack"]
    assert runner_calls == [
        (
            "U123",
            "C123",
            "1710.1",
            "1710.1",
            "selected message",
            "https://slack.example/p/17101",
            None,
        )
    ]


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
        "1710.1",
        "selected message",
        "https://slack.example/p/17101",
        None,
    )

    assert service.calls == [
        (
            "C123",
            "1710.1",
            "1710.1",
            "selected message",
        )
    ]
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
        "1710.1",
        "selected message",
        "https://slack.example/p/17101",
        None,
    )

    assert client.messages == [("U123", "summary text")]
    assert client.views == []


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
        "1710.1",
        "selected message",
        "https://slack.example/p/17101",
        None,
    )

    assert client.views == []
    assert len(client.messages) == 1
    assert "Slack 접근 권한" in client.messages[0][1]


def test_run_summary_job_clears_bad_mcp_tokens_and_reconnects(
    monkeypatch, tmp_path: Path
) -> None:
    config = _config(monkeypatch, tmp_path, delivery_surface="dm")
    store = EncryptedJSONStore(config.store_path, encryption_key=config.store_encryption_key)
    store.save_tokens("U123", MCPTokenSet(access_token="xoxp-123"))
    client = FakeClient()

    _run_summary_job(
        config,
        store,
        lambda token: FailingMCPService(),
        client,
        "U123",
        "C123",
        "1710.1",
        "1710.1",
        "selected message",
        "https://slack.example/p/17101",
        None,
    )

    assert store.load_tokens("U123") is None
    assert "Slack 권한 연결" in client.messages[0][1]


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
    assert "평일 다이제스트 설정이 저장되었습니다" in client.messages[0][1]
    assert client.views[0][0] == "U123"


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
                "errors": {"timezone": "Asia/Seoul 같은 올바른 IANA 타임존을 입력하세요."},
            },
        )
    ]
    assert store.load_preferences("U123") is None
    assert client.messages == []


def test_digest_command_opens_settings_modal_by_default(monkeypatch, tmp_path: Path) -> None:
    config = _config(monkeypatch, tmp_path)
    store = EncryptedJSONStore(config.store_path, encryption_key=config.store_encryption_key)
    client = FakeClient()
    acked: list[str] = []

    handler = build_digest_command_handler(config, store)
    handler(
        lambda: acked.append("ack"),
        {"user_id": "U123", "trigger_id": "trigger-123", "text": ""},
        client,
    )

    assert acked == ["ack"]
    assert client.opened_views[0][0] == "trigger-123"


def test_digest_command_help_sends_dm(monkeypatch, tmp_path: Path) -> None:
    config = _config(monkeypatch, tmp_path)
    store = EncryptedJSONStore(config.store_path, encryption_key=config.store_encryption_key)
    client = FakeClient()

    handler = build_digest_command_handler(config, store)
    handler(
        lambda: None,
        {"user_id": "U123", "trigger_id": "trigger-123", "text": "help"},
        client,
    )

    assert "Slack Assistant 명령어 안내" in client.messages[0][1]
    assert config.slack_digest_command in client.messages[0][1]


def test_app_home_opened_publishes_status_view(monkeypatch, tmp_path: Path) -> None:
    config = _config(monkeypatch, tmp_path)
    store = EncryptedJSONStore(config.store_path, encryption_key=config.store_encryption_key)
    client = FakeClient()

    handler = build_app_home_opened_handler(config, store)
    handler({"user": "U123"}, client, None)

    assert client.views[0][0] == "U123"
    assert client.views[0][1]["type"] == "home"


def test_app_home_action_opens_settings_modal(monkeypatch, tmp_path: Path) -> None:
    config = _config(monkeypatch, tmp_path)
    store = EncryptedJSONStore(config.store_path, encryption_key=config.store_encryption_key)
    client = FakeClient()

    handler = build_open_digest_settings_action_handler(config, store)
    handler(
        lambda: None,
        {"user": {"id": "U123"}, "trigger_id": "trigger-123"},
        client,
    )

    assert client.opened_views[0][0] == "trigger-123"


def test_app_home_action_sends_connect_link(monkeypatch, tmp_path: Path) -> None:
    config = _config(monkeypatch, tmp_path)
    store = EncryptedJSONStore(config.store_path, encryption_key=config.store_encryption_key)
    client = FakeClient()

    handler = build_send_connect_link_action_handler(config, store)
    handler(
        lambda: None,
        {"user": {"id": "U123"}, "trigger_id": "trigger-123"},
        client,
    )

    assert "Slack 접근 권한" in client.messages[0][1]
    assert client.views[0][0] == "U123"
