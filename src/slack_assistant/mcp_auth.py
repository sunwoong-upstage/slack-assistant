from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime, timedelta


class MCPAuthError(Exception):
    """Raised when Slack MCP auth state is invalid."""


def create_state_token(user_id: str, secret: str, *, now: datetime | None = None) -> str:
    timestamp = (now or datetime.now(UTC)).strftime("%Y%m%d%H%M%S")
    payload = f"{user_id}:{timestamp}"
    digest = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}:{digest}"


def validate_state_token(
    state: str,
    user_id: str,
    secret: str,
    *,
    now: datetime | None = None,
    ttl_seconds: int | None = 600,
) -> bool:
    try:
        token_user_id, timestamp, digest = state.split(":", 2)
    except ValueError:
        raise MCPAuthError("Malformed OAuth state token") from None
    if token_user_id != user_id:
        raise MCPAuthError("OAuth state token user mismatch")
    try:
        issued_at = datetime.strptime(timestamp, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    except ValueError:
        raise MCPAuthError("OAuth state token timestamp is invalid") from None
    current_time = now or datetime.now(UTC)
    if ttl_seconds is not None and current_time > issued_at + timedelta(seconds=ttl_seconds):
        raise MCPAuthError("OAuth state token has expired")
    payload = f"{token_user_id}:{timestamp}"
    expected = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, digest):
        raise MCPAuthError("OAuth state token failed validation")
    return True
