from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from .models import ThreadSummary


def _clean_line(text: str) -> str:
    return " ".join(text.split())


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    if limit <= 1:
        return text[:limit]
    return text[: limit - 1].rstrip() + "…"


def format_summary(summary: ThreadSummary, *, max_visible_chars: int = 900) -> str:
    headline = _truncate(_clean_line(summary.headline), 120)
    bullet_lines = [
        f"• {_truncate(_clean_line(bullet), 220)}"
        for bullet in summary.bullets[:3]
        if bullet.strip()
    ]
    lines = [f"[{headline} - {summary.thread_label}]"]
    lines.extend(bullet_lines)

    while len("\n".join(lines)) > max_visible_chars and len(lines) > 1:
        last = lines[-1]
        if len(last) > 20:
            lines[-1] = _truncate(last, len(last) - 20)
        else:
            lines.pop()

    visible = "\n".join(lines)
    if len(visible) > max_visible_chars:
        visible = _truncate(visible, max_visible_chars)

    return f"{visible}\n{summary.permalink}"


def format_digest(
    thread_summaries: list[ThreadSummary] | tuple[ThreadSummary, ...],
    *,
    timezone: str,
    delivered_at: datetime,
) -> str:
    local_time = delivered_at.astimezone(ZoneInfo(timezone))
    header = (
        f"*Slack 다이제스트 — {local_time.strftime('%a, %b %d')}*"
        f"\n오늘 매칭된 스레드 {len(thread_summaries)}개"
    )
    rendered_threads = [format_summary(summary) for summary in thread_summaries]
    return "\n\n".join([header, *rendered_threads])


def format_empty_digest(*, timezone: str, delivered_at: datetime) -> str:
    local_time = delivered_at.astimezone(ZoneInfo(timezone))
    return (
        f"*Slack 다이제스트 — {local_time.strftime('%a, %b %d')}*"
        "\n오늘은 직접 멘션되었거나 감시 이모지와 매칭된 스레드가 없습니다."
    )
