from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class MessageReaction:
    name: str
    user_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class SlackMessage:
    channel_id: str
    ts: str
    text: str
    user_id: str | None = None
    mentions: tuple[str, ...] = ()
    reactions: tuple[MessageReaction, ...] = ()
    permalink: str | None = None


@dataclass(frozen=True)
class SlackThread:
    channel_id: str
    thread_ts: str
    messages: tuple[SlackMessage, ...]
    permalink: str | None = None
    title: str | None = None
    last_activity_ts: str | None = None

    @property
    def root_message(self) -> SlackMessage | None:
        return self.messages[0] if self.messages else None


@dataclass(frozen=True)
class DigestSchedule:
    schedule_id: str
    hour: int
    minute: int
    timezone: str = "UTC"
    days_of_week: tuple[int, ...] = ()


@dataclass(frozen=True)
class UserPreferences:
    user_id: str
    user_handle: str | None = None
    aliases: tuple[str, ...] = ()
    watched_reactions: tuple[str, ...] = ()
    delivery_channel_id: str | None = None
    digest_schedules: tuple[DigestSchedule, ...] = ()


@dataclass(frozen=True)
class SearchHit:
    channel_id: str
    message_ts: str
    thread_ts: str
    text: str
    permalink: str | None = None


@dataclass(frozen=True)
class GeneratedSummary:
    headline: str
    bullets: tuple[str, ...]
    raw_content: str
    model_used: str
    fallback_used: bool = False


@dataclass(frozen=True)
class ThreadSummary:
    headline: str
    bullets: tuple[str, ...]
    permalink: str
    thread_label: str = "thread"


@dataclass(frozen=True)
class MCPTokenSet:
    access_token: str
    refresh_token: str | None = None
    expires_at: datetime | None = None
    scope: str | None = None


@dataclass(frozen=True)
class DigestResult:
    schedule: DigestSchedule
    delivered_at: datetime
    thread_summaries: tuple[ThreadSummary, ...] = field(default_factory=tuple)
    next_cursor: str | None = None
