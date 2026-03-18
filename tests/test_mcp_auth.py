from __future__ import annotations

from datetime import UTC, datetime, timedelta

from slack_assistant.mcp_auth import MCPAuthError, create_state_token, validate_state_token


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
