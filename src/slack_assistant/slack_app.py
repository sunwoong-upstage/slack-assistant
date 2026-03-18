from __future__ import annotations

import asyncio
import logging
from typing import Any

from slack_bolt import App

from .config import AppConfig
from .services import SlackAssistantService

logger = logging.getLogger(__name__)


def create_slack_app(config: AppConfig, service: SlackAssistantService) -> App:
    if not config.slack_bot_token or not config.slack_signing_secret:
        raise ValueError("Slack bot token and signing secret are required")

    app = App(
        token=config.slack_bot_token,
        signing_secret=config.slack_signing_secret,
        process_before_response=True,
    )

    @app.shortcut(config.slack_shortcut_callback_id)
    def summarize_shortcut(ack: Any, body: dict[str, Any], client: Any) -> None:
        ack()
        channel_id = body["channel"]["id"]
        message = body["message"]
        thread_ts = message.get("thread_ts") or message["ts"]
        user_id = body["user"]["id"]
        summary_text = asyncio.run(service.summarize_thread(channel_id, thread_ts))
        client.chat_postMessage(channel=user_id, text=summary_text)
        logger.info("Delivered summary to user %s for %s/%s", user_id, channel_id, thread_ts)

    return app
