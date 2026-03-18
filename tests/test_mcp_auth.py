from __future__ import annotations

from slack_assistant.mcp_auth import MCPAuthError, create_state_token, validate_state_token


def test_state_token_round_trip() -> None:
    state = create_state_token("U123", "secret")

    assert validate_state_token(state, "U123", "secret") is True


def test_state_token_rejects_wrong_user() -> None:
    state = create_state_token("U123", "secret")

    try:
        validate_state_token(state, "U999", "secret")
    except MCPAuthError as error:
        assert "user mismatch" in str(error)
    else:
        raise AssertionError("Expected MCPAuthError")
