from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from threading import Thread
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from slack_bolt import App

from .config import AppConfig
from .mcp_auth import build_authorize_url
from .models import DigestSchedule, UserPreferences
from .services import SlackAssistantService
from .store import EncryptedJSONStore

logger = logging.getLogger(__name__)

DEFAULT_DIGEST_SCHEDULE_ID = "weekday-digest"
DEFAULT_DIGEST_DAYS = (0, 1, 2, 3, 4)
DEFAULT_DIGEST_HOUR = 18
DEFAULT_DIGEST_MINUTE = 0
OPEN_DIGEST_SETTINGS_ACTION_ID = "open_digest_settings"
SEND_CONNECT_LINK_ACTION_ID = "send_connect_link"


class SlackShortcutClient(Protocol):
    def chat_postMessage(self, *, channel: str, text: str) -> object: ...  # noqa: N802

    def views_publish(self, *, user_id: str, view: dict[str, Any]) -> object: ...  # noqa: N802

    def views_open(self, *, trigger_id: str, view: dict[str, Any]) -> object: ...  # noqa: N802


ServiceFactory = Callable[[str], SlackAssistantService]
SummaryRunner = Callable[
    [AppConfig, EncryptedJSONStore, ServiceFactory, SlackShortcutClient, str, str, str],
    Thread | None,
]


def _build_app_home_view(summary_text: str) -> dict[str, Any]:
    return {
        "type": "home",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*최근 Slack Assistant 요약*",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": summary_text,
                },
            },
        ],
    }


def _build_digest_home_view(
    preferences: UserPreferences | None,
    *,
    connected: bool,
    default_timezone: str,
    digest_command: str,
) -> dict[str, Any]:
    schedule = _primary_schedule(preferences, default_timezone=default_timezone)
    day_labels = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    selected_days = schedule.days_of_week or DEFAULT_DIGEST_DAYS
    schedule_text = (
        f"{', '.join(day_labels[index] for index in selected_days)}"
        f" · {schedule.hour:02d}:{schedule.minute:02d} · {schedule.timezone}"
    )
    watched_text = (
        ", ".join(f":{reaction}:" for reaction in preferences.watched_reactions)
        if preferences and preferences.watched_reactions
        else "아직 설정된 감시 이모지가 없습니다."
    )
    connection_text = "연결됨" if connected else "아직 연결되지 않음"
    connection_help = (
        "Slack 접근 권한이 연결되어 다이제스트가 Slack 내역을 검색할 수 있습니다."
        if connected
        else "먼저 Slack 접근 권한을 연결해야 다이제스트가 Slack 내역을 검색할 수 있습니다."
    )
    return {
        "type": "home",
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "Slack Assistant 설정"},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "*사용 방법*\n"
                        "1. Slack 접근 권한을 연결합니다.\n"
                        "2. 요일, 시간, 타임존, 감시할 이모지를 설정합니다.\n"
                        "3. 평일마다 자동으로 DM 다이제스트를 받습니다.\n"
                        f"4. 언제든 `{digest_command}` 로 설정을 다시 열 수 있습니다."
                    ),
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Slack 접근 권한*\n{connection_text}"},
                    {"type": "mrkdwn", "text": f"*평일 다이제스트*\n{schedule_text}"},
                    {"type": "mrkdwn", "text": f"*감시 이모지*\n{watched_text}"},
                    {"type": "mrkdwn", "text": f"*상태 안내*\n{connection_help}"},
                ],
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "다이제스트 설정"},
                        "action_id": OPEN_DIGEST_SETTINGS_ACTION_ID,
                        "style": "primary",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Slack 권한 연결"},
                        "action_id": SEND_CONNECT_LINK_ACTION_ID,
                    },
                ],
            },
        ],
    }


def _build_digest_settings_view(
    preferences: UserPreferences | None,
    *,
    default_timezone: str,
    callback_id: str,
) -> dict[str, Any]:
    schedule = _primary_schedule(preferences, default_timezone=default_timezone)
    selected_days = set(schedule.days_of_week or DEFAULT_DIGEST_DAYS)
    weekday_labels = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
    weekdays = [
        {"value": str(index), "text": {"type": "plain_text", "text": label}}
        for index, label in enumerate(weekday_labels)
    ]
    initial_options = [
        {"value": str(index), "text": {"type": "plain_text", "text": label}}
        for index, label in enumerate(weekday_labels)
        if index in selected_days
    ]
    watched_reactions = ", ".join(
        f":{reaction.strip(':')}:"
        for reaction in (preferences.watched_reactions if preferences is not None else ())
    )
    return {
        "type": "modal",
        "callback_id": callback_id,
        "title": {"type": "plain_text", "text": "다이제스트 설정"},
        "submit": {"type": "plain_text", "text": "저장"},
        "close": {"type": "plain_text", "text": "취소"},
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "평일 다이제스트를 언제 받을지, "
                        "그리고 어떤 이모지 반응을 추적할지 설정하세요."
                    ),
                },
            },
            {
                "type": "input",
                "block_id": "weekdays",
                "element": {
                    "type": "checkboxes",
                    "action_id": "selected_days",
                    "options": weekdays,
                    "initial_options": initial_options,
                },
                "label": {"type": "plain_text", "text": "요일"},
            },
            {
                "type": "input",
                "block_id": "time",
                "element": {
                    "type": "plain_text_input",
                    "action_id": "time_input",
                    "initial_value": f"{schedule.hour:02d}:{schedule.minute:02d}",
                    "placeholder": {"type": "plain_text", "text": "18:00"},
                },
                "label": {"type": "plain_text", "text": "받는 시간 (24시간 HH:MM)"},
            },
            {
                "type": "input",
                "block_id": "timezone",
                "element": {
                    "type": "plain_text_input",
                    "action_id": "timezone_input",
                    "initial_value": schedule.timezone,
                    "placeholder": {"type": "plain_text", "text": "Asia/Seoul"},
                },
                "label": {"type": "plain_text", "text": "타임존"},
            },
            {
                "type": "input",
                "optional": True,
                "block_id": "reactions",
                "element": {
                    "type": "plain_text_input",
                    "action_id": "reactions_input",
                    "initial_value": watched_reactions,
                    "placeholder": {"type": "plain_text", "text": ":loading:, :eyes:"},
                },
                "label": {"type": "plain_text", "text": "감시할 이모지"},
            },
        ],
    }


def _build_connect_text(config: AppConfig, user_id: str) -> str:
    auth_url = build_authorize_url(config, user_id)
    return (
        "요약과 다이제스트를 사용하려면 먼저 Slack 접근 권한을 연결하세요: "
        f"<{auth_url}|Slack 권한 연결>"
    )


def _deliver_summary(
    client: SlackShortcutClient,
    *,
    delivery_surface: str,
    user_id: str,
    summary_text: str,
) -> None:
    if delivery_surface == "app_home":
        client.views_publish(user_id=user_id, view=_build_app_home_view(summary_text))
        return
    client.chat_postMessage(channel=user_id, text=summary_text)


def _run_summary_job(
    config: AppConfig,
    store: EncryptedJSONStore,
    service_factory: ServiceFactory,
    client: SlackShortcutClient,
    user_id: str,
    channel_id: str,
    thread_ts: str,
) -> None:
    try:
        token = store.load_tokens(user_id)
        if token is None:
            _deliver_summary(
                client,
                delivery_surface=config.slack_default_delivery_surface,
                user_id=user_id,
                summary_text=_build_connect_text(config, user_id),
            )
            return

        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            summary_text = loop.run_until_complete(
                service_factory(token.access_token).summarize_thread(channel_id, thread_ts)
            )
        finally:
            asyncio.set_event_loop(None)
            loop.close()

        _deliver_summary(
            client,
            delivery_surface=config.slack_default_delivery_surface,
            user_id=user_id,
            summary_text=summary_text,
        )
        logger.info("Delivered summary to user %s for %s/%s", user_id, channel_id, thread_ts)
    except Exception as error:  # noqa: BLE001
        logger.exception("Failed to deliver summary for %s/%s", channel_id, thread_ts)
        _deliver_summary(
            client,
            delivery_surface="dm",
            user_id=user_id,
            summary_text=f"Slack Assistant could not summarize that thread: {error}",
        )


def _start_background_summary(
    config: AppConfig,
    store: EncryptedJSONStore,
    service_factory: ServiceFactory,
    client: SlackShortcutClient,
    user_id: str,
    channel_id: str,
    thread_ts: str,
) -> Thread:
    worker = Thread(
        target=_run_summary_job,
        args=(config, store, service_factory, client, user_id, channel_id, thread_ts),
        daemon=True,
    )
    worker.start()
    return worker


def build_shortcut_handler(
    config: AppConfig,
    store: EncryptedJSONStore,
    service_factory: ServiceFactory,
    *,
    runner: SummaryRunner = _start_background_summary,
) -> Callable[[Any, dict[str, Any], SlackShortcutClient], None]:
    def summarize_shortcut(ack: Any, body: dict[str, Any], client: SlackShortcutClient) -> None:
        ack()
        channel_id = body["channel"]["id"]
        message = body["message"]
        thread_ts = message.get("thread_ts") or message["ts"]
        user_id = body["user"]["id"]
        runner(config, store, service_factory, client, user_id, channel_id, thread_ts)

    return summarize_shortcut


def build_digest_command_handler(
    config: AppConfig,
    store: EncryptedJSONStore,
) -> Callable[[Any, dict[str, Any], SlackShortcutClient], None]:
    def handle_digest_command(ack: Any, body: dict[str, Any], client: SlackShortcutClient) -> None:
        ack()
        user_id = body["user_id"]
        command_text = body.get("text", "").strip().lower()
        if command_text in {"", "settings"}:
            client.views_open(
                trigger_id=body["trigger_id"],
                view=_build_digest_settings_view(
                    store.load_preferences(user_id),
                    default_timezone=config.default_timezone,
                    callback_id=config.slack_digest_view_callback_id,
                ),
            )
            return

        if command_text == "help":
            client.chat_postMessage(
                channel=user_id,
                text=(
                    "*Slack Assistant 명령어 안내*\n"
                    f"• `{config.slack_digest_command}` — 다이제스트 설정 열기\n"
                    f"• `{config.slack_digest_command} settings` — 설정 바로 열기\n"
                    f"• `{config.slack_digest_command} help` — 도움말 보기\n"
                    "또는 앱 Home 탭에서 Slack 권한 연결과 현재 설정을 확인할 수 있습니다."
                ),
            )
            return

        client.chat_postMessage(
            channel=user_id,
            text=(
                f"`{command_text}` 명령은 알 수 없습니다.\n"
                f"`{config.slack_digest_command}` 로 설정을 열거나 "
                f"`{config.slack_digest_command} help` 로 도움말을 확인하세요."
            ),
        )

    return handle_digest_command


def build_digest_settings_shortcut_handler(
    config: AppConfig,
    store: EncryptedJSONStore,
) -> Callable[[Any, dict[str, Any], SlackShortcutClient], None]:
    def open_digest_settings(ack: Any, body: dict[str, Any], client: SlackShortcutClient) -> None:
        ack()
        user_id = body["user"]["id"]
        client.views_open(
            trigger_id=body["trigger_id"],
            view=_build_digest_settings_view(
                store.load_preferences(user_id),
                default_timezone=config.default_timezone,
                callback_id=config.slack_digest_view_callback_id,
            ),
        )

    return open_digest_settings


def build_digest_settings_submission_handler(
    config: AppConfig,
    store: EncryptedJSONStore,
) -> Callable[[Any, dict[str, Any], SlackShortcutClient], None]:
    def save_digest_settings(ack: Any, body: dict[str, Any], client: SlackShortcutClient) -> None:
        values = body["view"]["state"]["values"]
        time_value = values["time"]["time_input"].get("value", "")
        timezone_value = values["timezone"]["timezone_input"].get("value", "").strip()
        reaction_value = values["reactions"]["reactions_input"].get("value", "")
        selected_options = values["weekdays"]["selected_days"].get("selected_options", [])

        errors: dict[str, str] = {}
        weekdays = tuple(sorted(int(option["value"]) for option in selected_options))
        if not weekdays:
            errors["weekdays"] = "최소 한 개 이상의 요일을 선택하세요."
        time_parts = time_value.split(":", 1)
        if len(time_parts) != 2 or not all(part.isdigit() for part in time_parts):
            errors["time"] = "시간은 HH:MM 형식으로 입력하세요."
            hour = minute = 0
        else:
            hour, minute = int(time_parts[0]), int(time_parts[1])
            if hour not in range(24) or minute not in range(60):
                errors["time"] = "올바른 24시간 형식을 입력하세요."
        if not timezone_value:
            timezone_value = config.default_timezone
        try:
            ZoneInfo(timezone_value)
        except Exception:  # noqa: BLE001
            errors["timezone"] = "Asia/Seoul 같은 올바른 IANA 타임존을 입력하세요."

        if errors:
            ack(response_action="errors", errors=errors)
            return

        user_id = body["user"]["id"]
        existing = store.load_preferences(user_id) or UserPreferences(user_id=user_id)
        saved_preferences = UserPreferences(
            user_id=user_id,
            user_handle=existing.user_handle,
            aliases=existing.aliases,
            watched_reactions=_parse_watched_reactions(reaction_value),
            delivery_channel_id=existing.delivery_channel_id,
            digest_schedules=(
                DigestSchedule(
                    schedule_id=DEFAULT_DIGEST_SCHEDULE_ID,
                    hour=hour,
                    minute=minute,
                    timezone=timezone_value,
                    days_of_week=weekdays,
                ),
            ),
        )
        store.save_preferences(saved_preferences)

        ack()
        client.chat_postMessage(
            channel=user_id,
            text=_build_digest_settings_confirmation(
                hour=hour,
                minute=minute,
                timezone=timezone_value,
                weekdays=weekdays,
                watched_reactions=_parse_watched_reactions(reaction_value),
            ),
        )
        _publish_digest_home(
            config,
            store,
            client,
            user_id=user_id,
            preferences=saved_preferences,
        )

    return save_digest_settings


def build_app_home_opened_handler(
    config: AppConfig,
    store: EncryptedJSONStore,
) -> Callable[[dict[str, Any], SlackShortcutClient, Any], None]:
    def handle_app_home_opened(
        event: dict[str, Any],
        client: SlackShortcutClient,
        logger: Any,  # noqa: ARG001
    ) -> None:
        _publish_digest_home(config, store, client, user_id=event["user"])

    return handle_app_home_opened


def build_open_digest_settings_action_handler(
    config: AppConfig,
    store: EncryptedJSONStore,
) -> Callable[[Any, dict[str, Any], SlackShortcutClient], None]:
    def open_digest_settings(ack: Any, body: dict[str, Any], client: SlackShortcutClient) -> None:
        ack()
        user_id = body["user"]["id"]
        client.views_open(
            trigger_id=body["trigger_id"],
            view=_build_digest_settings_view(
                store.load_preferences(user_id),
                default_timezone=config.default_timezone,
                callback_id=config.slack_digest_view_callback_id,
            ),
        )

    return open_digest_settings


def build_send_connect_link_action_handler(
    config: AppConfig,
    store: EncryptedJSONStore,
) -> Callable[[Any, dict[str, Any], SlackShortcutClient], None]:
    def send_connect_link(ack: Any, body: dict[str, Any], client: SlackShortcutClient) -> None:
        ack()
        user_id = body["user"]["id"]
        client.chat_postMessage(channel=user_id, text=_build_connect_text(config, user_id))
        _publish_digest_home(config, store, client, user_id=user_id)

    return send_connect_link


def _publish_digest_home(
    config: AppConfig,
    store: EncryptedJSONStore,
    client: SlackShortcutClient,
    *,
    user_id: str,
    preferences: UserPreferences | None = None,
) -> None:
    loaded_preferences = preferences or store.load_preferences(user_id)
    connected = store.load_tokens(user_id) is not None
    client.views_publish(
        user_id=user_id,
        view=_build_digest_home_view(
            loaded_preferences,
            connected=connected,
            default_timezone=config.default_timezone,
            digest_command=config.slack_digest_command,
        ),
    )


def create_slack_app(
    config: AppConfig,
    store: EncryptedJSONStore,
    service_factory: ServiceFactory,
) -> App:
    if not config.slack_bot_token or not config.slack_signing_secret:
        raise ValueError("Slack bot token and signing secret are required")

    app = App(
        token=config.slack_bot_token,
        signing_secret=config.slack_signing_secret,
        process_before_response=True,
    )
    app.command(config.slack_digest_command)(build_digest_command_handler(config, store))
    app.shortcut(config.slack_shortcut_callback_id)(
        build_shortcut_handler(config, store, service_factory)
    )
    app.shortcut(config.slack_digest_shortcut_callback_id)(
        build_digest_settings_shortcut_handler(config, store)
    )
    app.view(config.slack_digest_view_callback_id)(
        build_digest_settings_submission_handler(config, store)
    )
    app.event("app_home_opened")(build_app_home_opened_handler(config, store))
    app.action(OPEN_DIGEST_SETTINGS_ACTION_ID)(
        build_open_digest_settings_action_handler(config, store)
    )
    app.action(SEND_CONNECT_LINK_ACTION_ID)(
        build_send_connect_link_action_handler(config, store)
    )
    return app


def _primary_schedule(
    preferences: UserPreferences | None,
    *,
    default_timezone: str,
) -> DigestSchedule:
    if preferences and preferences.digest_schedules:
        return preferences.digest_schedules[0]
    return DigestSchedule(
        schedule_id=DEFAULT_DIGEST_SCHEDULE_ID,
        hour=DEFAULT_DIGEST_HOUR,
        minute=DEFAULT_DIGEST_MINUTE,
        timezone=default_timezone,
        days_of_week=DEFAULT_DIGEST_DAYS,
    )


def _parse_watched_reactions(raw: str) -> tuple[str, ...]:
    reactions = [item.strip().strip(":").lower() for item in raw.replace("\n", ",").split(",")]
    deduped: list[str] = []
    for reaction in reactions:
        if not reaction or reaction in deduped:
            continue
        deduped.append(reaction)
    return tuple(deduped)


def _build_digest_settings_confirmation(
    *,
    hour: int,
    minute: int,
    timezone: str,
    weekdays: tuple[int, ...],
    watched_reactions: tuple[str, ...],
) -> str:
    day_labels = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    days_text = ", ".join(day_labels[index] for index in weekdays)
    reactions_text = (
        ", ".join(f":{reaction}:" for reaction in watched_reactions)
        if watched_reactions
        else "설정된 감시 이모지 없음"
    )
    return (
        "*평일 다이제스트 설정이 저장되었습니다*\n"
        f"일정: {days_text} {hour:02d}:{minute:02d} ({timezone})\n"
        f"감시 이모지: {reactions_text}"
    )
