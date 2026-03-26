from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class AppConfig:
    slack_bot_token: str | None
    slack_signing_secret: str | None
    slack_app_token: str | None
    slack_client_id: str | None
    slack_client_secret: str | None
    slack_state_secret: str
    app_base_url: str | None
    app_env: str
    app_host: str
    app_port: int
    slack_shortcut_callback_id: str
    slack_digest_shortcut_callback_id: str
    slack_digest_view_callback_id: str
    slack_default_delivery_surface: str
    slack_mcp_base_url: str
    slack_mcp_search_tool: str
    slack_mcp_read_tool: str
    slack_mcp_permalink_tool: str
    upstage_api_key: str | None
    upstage_base_url: str
    upstage_model: str
    upstage_fallback_model: str | None
    upstage_timeout_seconds: int
    upstage_max_retries: int
    store_path: Path
    store_encryption_key: str | None
    scheduler_poll_seconds: int
    default_timezone: str

    @property
    def transport_mode(self) -> str:
        return "socket_mode" if self.slack_app_token else "http"

    @property
    def is_development(self) -> bool:
        return self.app_env.lower() == "development"

    @property
    def oauth_redirect_path(self) -> str:
        return "/slack/oauth_redirect"

    @property
    def oauth_redirect_url(self) -> str | None:
        if not self.app_base_url:
            return None
        return f"{self.app_base_url.rstrip('/')}{self.oauth_redirect_path}"


def _get_required(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise ValueError(f"Missing required environment variable: {name}")
    return value.strip()


def _get_optional(name: str) -> str | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    return value.strip()


def load_config() -> AppConfig:
    return AppConfig(
        slack_bot_token=_get_optional("SLACK_BOT_TOKEN"),
        slack_signing_secret=_get_optional("SLACK_SIGNING_SECRET"),
        slack_app_token=_get_optional("SLACK_APP_TOKEN"),
        slack_client_id=_get_optional("SLACK_CLIENT_ID"),
        slack_client_secret=_get_optional("SLACK_CLIENT_SECRET"),
        slack_state_secret=_get_required("SLACK_STATE_SECRET"),
        app_base_url=_get_optional("APP_BASE_URL"),
        app_env=os.getenv("APP_ENV", "development"),
        app_host=os.getenv("APP_HOST", "0.0.0.0"),
        app_port=int(os.getenv("APP_PORT", "3000")),
        slack_shortcut_callback_id=os.getenv("SLACK_SHORTCUT_CALLBACK_ID", "summarize_thread"),
        slack_digest_shortcut_callback_id=os.getenv(
            "SLACK_DIGEST_SHORTCUT_CALLBACK_ID", "configure_digest_settings"
        ),
        slack_digest_view_callback_id=os.getenv(
            "SLACK_DIGEST_VIEW_CALLBACK_ID", "configure_digest_settings_modal"
        ),
        slack_default_delivery_surface=os.getenv("SLACK_DEFAULT_DELIVERY_SURFACE", "app_home"),
        slack_mcp_base_url=os.getenv("SLACK_MCP_BASE_URL", "https://mcp.slack.com/mcp"),
        slack_mcp_search_tool=os.getenv("SLACK_MCP_SEARCH_TOOL", "search_messages"),
        slack_mcp_read_tool=os.getenv("SLACK_MCP_READ_TOOL", "read_thread"),
        slack_mcp_permalink_tool=os.getenv("SLACK_MCP_PERMALINK_TOOL", "chat_getPermalink"),
        upstage_api_key=_get_optional("UPSTAGE_API_KEY"),
        upstage_base_url=os.getenv("UPSTAGE_BASE_URL", "https://api.upstage.ai/v2"),
        upstage_model=os.getenv("UPSTAGE_MODEL", "solar-pro"),
        upstage_fallback_model=_get_optional("UPSTAGE_FALLBACK_MODEL"),
        upstage_timeout_seconds=int(os.getenv("UPSTAGE_TIMEOUT_SECONDS", "20")),
        upstage_max_retries=int(os.getenv("UPSTAGE_MAX_RETRIES", "1")),
        store_path=Path(os.getenv("STORE_PATH", ".data/store.json")),
        store_encryption_key=_get_optional("STORE_ENCRYPTION_KEY"),
        scheduler_poll_seconds=int(os.getenv("SCHEDULER_POLL_SECONDS", "30")),
        default_timezone=os.getenv("DEFAULT_TIMEZONE", "UTC"),
    )
