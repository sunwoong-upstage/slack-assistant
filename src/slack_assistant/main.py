from __future__ import annotations

import os

from slack_bolt.adapter.socket_mode import SocketModeHandler

from .config import load_config
from .mcp_client import SlackMCPClient, SlackMCPHTTPTransport
from .services import SlackAssistantService
from .slack_app import create_slack_app
from .upstage_client import UpstageClient


def main() -> None:
    config = load_config()
    mcp_access_token = os.getenv("SLACK_MCP_ACCESS_TOKEN", "")
    if not mcp_access_token:
        raise ValueError("SLACK_MCP_ACCESS_TOKEN is required to start the app")
    if not config.upstage_api_key:
        raise ValueError("UPSTAGE_API_KEY is required to start the app")

    mcp_client = SlackMCPClient(
        SlackMCPHTTPTransport(base_url=config.slack_mcp_base_url, access_token=mcp_access_token),
        search_tool=config.slack_mcp_search_tool,
        read_tool=config.slack_mcp_read_tool,
        permalink_tool=config.slack_mcp_permalink_tool,
    )
    upstage_client = UpstageClient(
        api_key=config.upstage_api_key,
        base_url=config.upstage_base_url,
        model=config.upstage_model,
        fallback_model=config.upstage_fallback_model,
        timeout_seconds=config.upstage_timeout_seconds,
        max_retries=config.upstage_max_retries,
    )
    app = create_slack_app(
        config, SlackAssistantService(mcp_client=mcp_client, upstage_client=upstage_client)
    )

    if config.transport_mode == "socket_mode":
        SocketModeHandler(app, config.slack_app_token).start()
        return

    app.start(port=config.app_port)


if __name__ == "__main__":
    main()
