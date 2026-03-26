from __future__ import annotations

import pytest

ENV_KEYS = (
    "SLACK_BOT_TOKEN",
    "SLACK_SIGNING_SECRET",
    "SLACK_APP_TOKEN",
    "SLACK_CLIENT_ID",
    "SLACK_CLIENT_SECRET",
    "SLACK_STATE_SECRET",
    "APP_BASE_URL",
    "APP_ENV",
    "APP_HOST",
    "APP_PORT",
    "SLACK_SHORTCUT_CALLBACK_ID",
    "SLACK_DIGEST_SHORTCUT_CALLBACK_ID",
    "SLACK_DIGEST_VIEW_CALLBACK_ID",
    "SLACK_DEFAULT_DELIVERY_SURFACE",
    "SLACK_MCP_BASE_URL",
    "SLACK_MCP_SEARCH_TOOL",
    "SLACK_MCP_READ_TOOL",
    "SLACK_MCP_PERMALINK_TOOL",
    "UPSTAGE_API_KEY",
    "UPSTAGE_BASE_URL",
    "UPSTAGE_MODEL",
    "UPSTAGE_FALLBACK_MODEL",
    "UPSTAGE_TIMEOUT_SECONDS",
    "UPSTAGE_MAX_RETRIES",
    "STORE_PATH",
    "STORE_ENCRYPTION_KEY",
    "SCHEDULER_POLL_SECONDS",
    "DEFAULT_TIMEZONE",
)


@pytest.fixture(autouse=True)
def clear_loaded_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
