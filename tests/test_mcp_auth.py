from __future__ import annotations

from datetime import UTC, datetime, timedelta

from slack_assistant.config import load_config
from slack_assistant.mcp_auth import (
    MCPAuthError,
    build_authorize_url,
    create_state_token,
    validate_state_token,
)


def test_state_token_round_trip() -> None:
    now = datetime(2026, 3, 18, 7, 15, tzinfo=UTC)
    state = create_state_token("U123", "secret", now=now)

    assert validate_state_token(state, "U123", "secret", now=now) is True


def test_state_token_rejects_wrong_user() -> None:
    state = create_state_token("U123", "secret")

    try:
        validate_state_token(state, "U999", "secret")
    except MCPAuthError as error:
        assert "user mismatch" in str(error)
    else:
        raise AssertionError("Expected MCPAuthError")


def test_state_token_rejects_expired_tokens() -> None:
    issued_at = datetime(2026, 3, 18, 7, 15, tzinfo=UTC)
    state = create_state_token("U123", "secret", now=issued_at)

    try:
        validate_state_token(
            state,
            "U123",
            "secret",
            now=issued_at + timedelta(seconds=601),
            ttl_seconds=600,
        )
    except MCPAuthError as error:
        assert "expired" in str(error)
    else:
        raise AssertionError("Expected MCPAuthError")


def test_build_authorize_url_uses_app_base_url(monkeypatch) -> None:
    monkeypatch.setenv("SLACK_STATE_SECRET", "secret")
    monkeypatch.setenv("SLACK_OAUTH_CLIENT_ID", "123")
    monkeypatch.setenv("APP_BASE_URL", "https://app.example.com")

    config = load_config()
    url = build_authorize_url(config, "U123")

    assert "client_id=123" in url
    assert "redirect_uri=https%3A%2F%2Fapp.example.com%2Fslack%2Foauth_redirect" in url
    assert "state=" in url
