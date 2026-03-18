from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from threading import Thread
from typing import Any, Protocol

from slack_bolt import App

from .config import AppConfig
from .services import SlackAssistantService

logger = logging.getLogger(__name__)


class SlackShortcutClient(Protocol):
    def chat_postMessage(self, *, channel: str, text: str) -> None: ...  # noqa: N802


SummaryRunner = Callable[
    [SlackAssistantService, SlackShortcutClient, str, str, str],
    None,
]


def _run_summary_job(
    service: SlackAssistantService,
    client: SlackShortcutClient,
    user_id: str,
    channel_id: str,
    thread_ts: str,
) -> None:
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        summary_text = loop.run_until_complete(service.summarize_thread(channel_id, thread_ts))
    finally:
        asyncio.set_event_loop(None)
        loop.close()
    client.chat_postMessage(channel=user_id, text=summary_text)
    logger.info("Delivered summary to user %s for %s/%s", user_id, channel_id, thread_ts)


def _start_background_summary(
    service: SlackAssistantService,
    client: SlackShortcutClient,
    user_id: str,
    channel_id: str,
    thread_ts: str,
) -> Thread:
    worker = Thread(
        target=_run_summary_job,
        args=(service, client, user_id, channel_id, thread_ts),
        daemon=True,
    )
    worker.start()
    return worker


def build_shortcut_handler(
    service: SlackAssistantService,
    *,
    runner: SummaryRunner = _start_background_summary,
) -> Callable[[Any, dict[str, Any], SlackShortcutClient], None]:
    def summarize_shortcut(ack: Any, body: dict[str, Any], client: SlackShortcutClient) -> None:
        ack()
        channel_id = body["channel"]["id"]
        message = body["message"]
        thread_ts = message.get("thread_ts") or message["ts"]
        user_id = body["user"]["id"]
        runner(service, client, user_id, channel_id, thread_ts)

    return summarize_shortcut


def create_slack_app(config: AppConfig, service: SlackAssistantService) -> App:
    if not config.slack_bot_token or not config.slack_signing_secret:
        raise ValueError("Slack bot token and signing secret are required")

    app = App(
        token=config.slack_bot_token,
        signing_secret=config.slack_signing_secret,
        process_before_response=True,
    )
    app.shortcut(config.slack_shortcut_callback_id)(build_shortcut_handler(service))
    return app
