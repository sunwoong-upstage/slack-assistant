from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx

from .config import AppConfig
from .models import MCPTokenSet


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


def extract_state_user_id(state: str) -> str:
    try:
        user_id, _timestamp, _digest = state.split(":", 2)
    except ValueError:
        raise MCPAuthError("Malformed OAuth state token") from None
    return user_id


def build_authorize_url(config: AppConfig, user_id: str) -> str:
    if not config.slack_client_id:
        raise MCPAuthError("SLACK_CLIENT_ID is required to build the Slack auth URL")
    if not config.oauth_redirect_url:
        raise MCPAuthError("APP_BASE_URL is required to build the Slack auth URL")

    state = create_state_token(user_id, config.slack_state_secret)
    params = {
        "client_id": config.slack_client_id,
        "redirect_uri": config.oauth_redirect_url,
        "user_scope": ",".join(
            [
                "channels:history",
                "groups:history",
                "im:history",
                "mpim:history",
                "search:read.public",
                "search:read.private",
                "search:read.im",
                "search:read.mpim",
                "users:read",
            ]
        ),
        "state": state,
    }
    return f"https://slack.com/oauth/v2/authorize?{urlencode(params)}"


def extract_user_id(state: str) -> str:
    try:
        token_user_id, _, digest = state.split(":", 2)
    except ValueError:
        raise MCPAuthError("Malformed OAuth state token") from None
    if not token_user_id or not digest:
        raise MCPAuthError("Malformed OAuth state token")
    return token_user_id


def exchange_code_for_tokens(
    config: AppConfig,
    code: str,
    *,
    http_client: httpx.Client | None = None,
) -> tuple[str | None, MCPTokenSet]:
    if not config.slack_client_id or not config.slack_client_secret:
        raise MCPAuthError("Slack OAuth client credentials are required")
    if not config.oauth_redirect_url:
        raise MCPAuthError("APP_BASE_URL is required for OAuth callback handling")

    client = http_client or httpx.Client(timeout=20.0)
    should_close = http_client is None
    try:
        response = client.post(
            "https://slack.com/api/oauth.v2.access",
            data={
                "client_id": config.slack_client_id,
                "client_secret": config.slack_client_secret,
                "code": code,
                "redirect_uri": config.oauth_redirect_url,
            },
        )
    finally:
        if should_close:
            client.close()

    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        error = str(payload.get("error", "unknown_error"))
        raise MCPAuthError(f"Slack OAuth exchange failed: {error}")

    authed_user = payload.get("authed_user") or {}
    access_token = str(authed_user.get("access_token") or payload.get("access_token") or "").strip()
    if not access_token:
        raise MCPAuthError("Slack OAuth exchange returned no access token")

    expires_at = None
    expires_in = authed_user.get("expires_in") or payload.get("expires_in")
    if expires_in:
        expires_at = datetime.now(UTC) + timedelta(seconds=int(expires_in))

    raw_scope = authed_user.get("scope") or payload.get("scope")
    user_id = authed_user.get("id")
    token = MCPTokenSet(
        access_token=access_token,
        refresh_token=authed_user.get("refresh_token") or payload.get("refresh_token"),
        expires_at=expires_at,
        scope=str(raw_scope).strip() if raw_scope else None,
    )
    return (str(user_id).strip() if user_id else None), token
