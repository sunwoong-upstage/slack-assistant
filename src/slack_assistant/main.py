from __future__ import annotations

from threading import Thread

from slack_bolt.adapter.socket_mode import SocketModeHandler

from .config import load_config
from .digest_dispatcher import ScheduledDigestDispatcher
from .mcp_client import SlackMCPClient, SlackMCPHTTPTransport
from .services import SlackAssistantService
from .slack_app import create_slack_app
from .store import EncryptedJSONStore
from .upstage_client import UpstageClient
from .web import create_http_app


def main() -> None:
    config = load_config()
    if not config.upstage_api_key:
        raise ValueError("UPSTAGE_API_KEY is required to start the app")
    if not config.store_encryption_key:
        raise ValueError("STORE_ENCRYPTION_KEY is required to start the app")

    store = EncryptedJSONStore(config.store_path, encryption_key=config.store_encryption_key)

    upstage_client = UpstageClient(
        api_key=config.upstage_api_key,
        base_url=config.upstage_base_url,
        model=config.upstage_model,
        fallback_model=config.upstage_fallback_model,
        timeout_seconds=config.upstage_timeout_seconds,
        max_retries=config.upstage_max_retries,
    )

    def service_factory(access_token: str) -> SlackAssistantService:
        mcp_client = SlackMCPClient(
            SlackMCPHTTPTransport(base_url=config.slack_mcp_base_url, access_token=access_token),
            search_tool=config.slack_mcp_search_tool,
            read_tool=config.slack_mcp_read_tool,
            permalink_tool=config.slack_mcp_permalink_tool,
        )
        return SlackAssistantService(mcp_client=mcp_client, upstage_client=upstage_client)

    bolt_app = create_slack_app(config, store, service_factory)
    digest_dispatcher = ScheduledDigestDispatcher(config, store, service_factory, bolt_app.client)
    Thread(
        target=digest_dispatcher.run_forever,
        daemon=True,
    ).start()
    http_app = create_http_app(config, bolt_app, store)

    if config.transport_mode == "socket_mode":
        Thread(
            target=lambda: SocketModeHandler(bolt_app, config.slack_app_token).start(),
            daemon=True,
        ).start()

    http_app.run(host=config.app_host, port=config.app_port)


if __name__ == "__main__":
    main()
