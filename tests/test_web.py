from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from cryptography.fernet import Fernet

from slack_assistant.config import load_config
from slack_assistant.mcp_auth import create_state_token
from slack_assistant.models import MCPTokenSet
from slack_assistant.slack_app import create_slack_app
from slack_assistant.store import EncryptedJSONStore
from slack_assistant.web import create_http_app


class FakeService:
    async def summarize_thread(self, channel_id: str, thread_ts: str) -> str:
        return f"{channel_id}:{thread_ts}"


def _config(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("SLACK_STATE_SECRET", "secret")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-123")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "signing-secret")
    monkeypatch.setenv("SLACK_CLIENT_ID", "123")
    monkeypatch.setenv("SLACK_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("APP_BASE_URL", "https://app.example.com")
    monkeypatch.setenv("STORE_ENCRYPTION_KEY", Fernet.generate_key().decode("utf-8"))
    monkeypatch.setenv("UPSTAGE_API_KEY", "upstage-key")
    monkeypatch.setenv("STORE_PATH", str(tmp_path / "store.json"))
    return load_config()


def test_oauth_redirect_saves_tokens(monkeypatch, tmp_path: Path) -> None:
    config = _config(monkeypatch, tmp_path)
    store = EncryptedJSONStore(config.store_path, encryption_key=config.store_encryption_key)
    bolt_app = create_slack_app(config, store, lambda token: FakeService())

    def exchange(_config, code: str):
        assert code == "code-123"
        return (
            "U123",
            MCPTokenSet(
                access_token="xoxp-123",
                refresh_token="refresh",
                expires_at=datetime(2026, 3, 18, tzinfo=UTC),
                scope="search:read.public",
            ),
        )

    app = create_http_app(config, bolt_app, store, token_exchange=exchange)
    client = app.test_client()
    state = create_state_token("U123", "secret")
    response = client.get(
        "/slack/oauth_redirect",
        query_string={
            "code": "code-123",
            "state": state,
        },
    )

    assert response.status_code == 200
    assert store.load_tokens("U123") is not None


def test_oauth_redirect_rejects_bad_state(monkeypatch, tmp_path: Path) -> None:
    config = _config(monkeypatch, tmp_path)
    store = EncryptedJSONStore(config.store_path, encryption_key=config.store_encryption_key)
    bolt_app = create_slack_app(config, store, lambda token: FakeService())
    app = create_http_app(
        config,
        bolt_app,
        store,
        token_exchange=lambda _config, code: ("U123", MCPTokenSet(access_token=code)),
    )
    client = app.test_client()

    response = client.get(
        "/slack/oauth_redirect",
        query_string={"code": "code-123", "state": "bad-state"},
    )

    assert response.status_code == 400
