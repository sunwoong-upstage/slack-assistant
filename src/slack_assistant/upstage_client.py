from __future__ import annotations

import json
import logging
import re
from typing import Any, cast

import httpx
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

from .models import GeneratedSummary, SlackMessage, SlackThread

logger = logging.getLogger(__name__)

SUMMARY_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "slack_thread_summary",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "tone_style": {
                    "type": "string",
                    "enum": ["note"],
                    "description": "항상 note 여야 함.",
                },
                "focus_summary": {
                    "type": "string",
                    "description": (
                        "반드시 한국어의 완결된 한 문장으로 작성함. 사람 이름 없이 "
                        "focus message 핵심만 note tone(~함./~음.)으로 정리함."
                    ),
                },
                "context_summary": {
                    "type": "string",
                    "description": (
                        "반드시 한국어의 완결된 한 문장으로 작성함. 사람 이름 없이 "
                        "parent thread 맥락/배경만 note tone(~함./~음.)으로 정리함."
                    ),
                },
                "next_step_summary": {
                    "type": ["string", "null"],
                    "description": (
                        "있으면 한국어 한 문장으로 작성함. 후속 요청/액션을 "
                        "note tone(~함./~음.)으로 정리하고, 없으면 null."
                    ),
                },
                "risk_summary": {
                    "type": ["string", "null"],
                    "description": (
                        "있으면 한국어 한 문장으로 작성함. 리스크/미결 사항을 "
                        "note tone(~함./~음.)으로 정리하고, 없으면 null."
                    ),
                },
            },
            "required": [
                "tone_style",
                "focus_summary",
                "context_summary",
                "next_step_summary",
                "risk_summary",
            ],
            "additionalProperties": False,
        },
    },
}

SYSTEM_PROMPT = """You summarize Slack threads for a busy person.
Return strict JSON following the schema.
Write every field in Korean.
Use note style only: each sentence must end in ~함. / ~음. / ~됨. / ~임.
Produce semantic-only summaries:
- focus_summary: focus message 핵심
- context_summary: parent thread 맥락
- next_step_summary: 후속 요청/액션, 없으면 null
- risk_summary: 리스크/미결 사항, 없으면 null
Prioritize the FOCUS_MESSAGE when present, but use ROOT_CONTEXT to explain why it matters.
The AUTHOR of a message is the speaker. Mentioned users inside the message body are not the speaker.
The FOCUS_MESSAGE_AUTHOR is the highest-priority attribution hint
for who said or requested something.
Do not fabricate or substitute people names in any field. Prefer role-free semantic phrasing.
When writing the summary sentence, prefer the actual message author over any mentioned person.
Do not swap actors. If Gongpil asks Tony to review something, summarize it as Gongpil requesting
Tony's review, not Tony being unavailable or making the request.
Do not invent attendance/status claims unless they are explicitly stated by the message author.
If attribution is ambiguous, say it is ambiguous instead of guessing.
Do not output English prose except for unavoidable proper nouns,
product names, or quoted source text.
Do not use ellipses or incomplete/truncated clauses. The headline must read as a finished sentence.
Do not output any placeholder token (e.g. ROOT_AUTHOR, FOCUS_AUTHOR, AUTHOR_1, MENTION).
Do not include markdown fences.
"""


class UpstageClientError(Exception):
    """Raised when Upstage summarization fails."""


class UpstageClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        fallback_model: str | None = None,
        timeout_seconds: int = 20,
        max_retries: int = 1,
        client: AsyncOpenAI | None = None,
    ) -> None:
        normalized_base_url = self._normalize_base_url(base_url)
        self._client = client or AsyncOpenAI(
            api_key=api_key,
            base_url=normalized_base_url,
            timeout=httpx.Timeout(timeout_seconds, connect=10.0),
        )
        self._model = model
        self._fallback_model = fallback_model
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries

    async def summarize_thread(
        self,
        thread: SlackThread,
        *,
        selected_message_ts: str | None = None,
        selected_message_author_name: str | None = None,
        selected_message_text_hint: str | None = None,
    ) -> GeneratedSummary:
        messages = self._build_messages(
            thread,
            selected_message_ts=selected_message_ts,
            selected_message_author_name=selected_message_author_name,
            selected_message_text_hint=selected_message_text_hint,
        )
        raw_content, model_used, fallback_used = await self._generate_with_policy(messages)
        summary = self.parse_generated_summary(raw_content)
        return GeneratedSummary(
            tone_style=summary.tone_style,
            focus_summary=summary.focus_summary,
            context_summary=summary.context_summary,
            next_step_summary=summary.next_step_summary,
            risk_summary=summary.risk_summary,
            raw_content=raw_content,
            model_used=model_used,
            fallback_used=fallback_used,
        )

    def _build_messages(
        self,
        thread: SlackThread,
        *,
        selected_message_ts: str | None = None,
        selected_message_author_name: str | None = None,
        selected_message_text_hint: str | None = None,
    ) -> list[ChatCompletionMessageParam]:
        root_message = thread.root_message
        focus_message = next(
            (message for message in thread.messages if message.ts == selected_message_ts),
            None,
        )
        placeholder_map = _build_placeholder_map(thread, focus_message)
        rendered_thread = []
        focus_hint_author_role = _placeholder_for_selected_author(
            selected_message_author_name,
            placeholder_map,
        )
        for message in thread.messages:
            author = placeholder_map.get(
                message.author_name or message.user_id or "unknown-user",
                "AUTHOR_UNKNOWN",
            )
            markers: list[str] = []
            if root_message is not None and message.ts == root_message.ts:
                markers.append("ROOT")
            if focus_message is not None and message.ts == focus_message.ts:
                markers.append("FOCUS")
            marker_prefix = f"[{'/'.join(markers)}]" if markers else ""
            rendered_thread.append(
                f"{marker_prefix}[{author}][{message.ts}] "
                f"{_sanitize_text_for_model(message.text, placeholder_map)}"
            )
        prompt = "\n".join(
            [
                "AUTHOR_PLACEHOLDERS:",
                *_render_placeholder_reference_lines(placeholder_map),
                "",
                "ROOT_CONTEXT:",
                f"- author_role: {_placeholder_for_message(root_message, placeholder_map)}",
                (
                    _sanitize_text_for_model(root_message.text, placeholder_map)
                    if root_message
                    else "(none)"
                ),
                "",
                "FOCUS_MESSAGE:",
                f"- author_role: {_placeholder_for_message(focus_message, placeholder_map)}",
                (
                    _sanitize_text_for_model(focus_message.text, placeholder_map)
                    if focus_message
                    else "(not specified)"
                ),
                "",
                "FOCUS_MESSAGE_HINT:",
                f"- author_role: {focus_hint_author_role}",
                (
                    _sanitize_text_for_model(selected_message_text_hint, placeholder_map)
                    if selected_message_text_hint
                    else "(not specified)"
                ),
                "",
                "THREAD_TIMELINE:",
                *rendered_thread,
            ]
        )
        return [
            cast(ChatCompletionMessageParam, {"role": "system", "content": SYSTEM_PROMPT}),
            cast(ChatCompletionMessageParam, {"role": "user", "content": prompt}),
        ]

    async def _generate_with_policy(
        self,
        messages: list[ChatCompletionMessageParam],
    ) -> tuple[str, str, bool]:
        try:
            raw = await self._try_model(self._model, messages, self._max_retries + 1)
            return raw, self._model, False
        except Exception as primary_error:
            if not self._fallback_model:
                raise UpstageClientError("Preferred Upstage model failed") from primary_error

            try:
                raw = await self._try_model(self._fallback_model, messages, 1)
                return raw, self._fallback_model, True
            except Exception as fallback_error:
                raise UpstageClientError(
                    "Preferred and fallback Upstage models failed"
                ) from fallback_error

    async def _try_model(
        self,
        model: str,
        messages: list[ChatCompletionMessageParam],
        attempts: int,
    ) -> str:
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                return await self._request_completion(model, messages)
            except Exception as error:  # noqa: BLE001
                last_error = error
                if not self._is_retryable_error(error) or attempt == attempts:
                    break
                logger.warning("Retrying Upstage request after %s", error)
        raise last_error or UpstageClientError("Upstage request failed")

    async def _request_completion(
        self, model: str, messages: list[ChatCompletionMessageParam]
    ) -> str:
        response = await self._client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.0,
            response_format=cast(Any, SUMMARY_RESPONSE_FORMAT),
        )
        return (response.choices[0].message.content or "").strip()

    @staticmethod
    def _is_retryable_error(error: Exception) -> bool:
        if isinstance(error, httpx.TimeoutException):
            return True
        status_code = getattr(error, "status_code", None) or getattr(error, "status", None)
        if isinstance(status_code, int):
            return status_code in {408, 429} or 500 <= status_code <= 599
        return bool(getattr(error, "retryable", False))

    @staticmethod
    def _normalize_base_url(base_url: str) -> str:
        normalized = base_url.rstrip("/")
        if normalized.endswith("/v2"):
            return f"{normalized[:-3]}/v1"
        return normalized

    @staticmethod
    def parse_generated_summary(raw_content: str) -> GeneratedSummary:
        content = raw_content.strip()
        if content.startswith("```"):
            lines = [line for line in content.splitlines() if not line.strip().startswith("```")]
            content = "\n".join(lines).strip()

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as error:
            raise UpstageClientError("Upstage response was not valid JSON") from error

        tone_style = str(parsed.get("tone_style", "")).strip()
        focus_summary = _validate_generated_sentence(
            str(parsed.get("focus_summary", "")).strip()
        )
        context_summary = _validate_generated_sentence(
            str(parsed.get("context_summary", "")).strip()
        )
        next_step_raw = parsed.get("next_step_summary")
        risk_raw = parsed.get("risk_summary")
        next_step_summary = (
            _validate_generated_sentence(str(next_step_raw).strip())
            if isinstance(next_step_raw, str) and str(next_step_raw).strip()
            else None
        )
        risk_summary = (
            _validate_generated_sentence(str(risk_raw).strip())
            if isinstance(risk_raw, str) and str(risk_raw).strip()
            else None
        )
        if tone_style != "note":
            raise UpstageClientError("Upstage response missing note tone_style")
        return GeneratedSummary(
            tone_style=tone_style,
            focus_summary=focus_summary,
            raw_content=raw_content,
            model_used="",
            context_summary=context_summary,
            next_step_summary=next_step_summary,
            risk_summary=risk_summary,
        )


def _build_placeholder_map(
    thread: SlackThread,
    focus_message: SlackMessage | None,
) -> dict[str, str]:
    mapping: dict[str, str] = {}
    root = thread.root_message
    if focus_message is not None and (focus_message.author_name or focus_message.user_id):
        mapping[focus_message.author_name or focus_message.user_id or ""] = "FOCUS_AUTHOR"
    if root is not None and (root.author_name or root.user_id):
        root_name = root.author_name or root.user_id or ""
        mapping.setdefault(root_name, "ROOT_AUTHOR")
    counter = 1
    for message in thread.messages:
        name = message.author_name or message.user_id or ""
        if not name or name in mapping:
            continue
        mapping[name] = f"AUTHOR_{counter}"
        counter += 1
    return {key: value for key, value in mapping.items() if key}


def _render_placeholder_reference_lines(placeholder_map: dict[str, str]) -> list[str]:
    lines: list[str] = []
    for placeholder in placeholder_map.values():
        lines.append(f"- {placeholder}: internal participant reference only")
        lines.append(f"- never output {placeholder} or any real person name")
    return lines


def _sanitize_text_for_model(text: str | None, placeholder_map: dict[str, str]) -> str:
    if not text:
        return "(not specified)"
    sanitized = text
    sanitized = re.sub(r"<@[^>]+>", "[MENTION]", sanitized)
    sanitized = re.sub(r"@[A-Za-z0-9._-]+", "[MENTION]", sanitized)
    for actual, placeholder in sorted(
        placeholder_map.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        sanitized = sanitized.replace(actual, placeholder)
    return sanitized.strip()


def _placeholder_for_message(
    message: SlackMessage | None,
    placeholder_map: dict[str, str],
) -> str:
    if message is None:
        return "(none)"
    return placeholder_map.get(message.author_name or message.user_id or "", "AUTHOR_UNKNOWN")


def _placeholder_for_selected_author(
    author_name: str | None,
    placeholder_map: dict[str, str],
) -> str:
    if author_name is None:
        return "(not specified)"
    return placeholder_map.get(author_name, "AUTHOR_UNKNOWN")


def _validate_generated_sentence(text: str) -> str:
    normalized = _normalize_generated_sentence(text)
    if not normalized:
        raise UpstageClientError("Upstage response missing required summary text")
    if "..." in normalized or "…" in normalized:
        raise UpstageClientError("Upstage response used ellipsis")
    normalized = _coerce_note_style(normalized)
    if not re.search(r"(함\.|음\.|됨\.|임\.|필요함\.|예정임\.)$", normalized):
        raise UpstageClientError("Upstage response missing note-style ending")
    return normalized


def _normalize_generated_sentence(text: str) -> str:
    normalized = text.strip()
    normalized = re.sub(
        r"(?:FOCUS_AUTHOR|ROOT_AUTHOR|AUTHOR_\d+|MENTION)"
        r"(?:가|이|은|는|와|과|를|을|의)?\s*",
        "",
        normalized,
    )
    normalized = normalized.replace("임음.", "임.")
    normalized = normalized.replace("함음.", "함.")
    normalized = normalized.replace("됨음.", "됨.")
    normalized = normalized.replace("음음.", "음.")
    normalized = re.sub(r"\s{2,}", " ", normalized).strip()
    return normalized


def _coerce_note_style(text: str) -> str:
    replacements = (
        (r"합니다\.$", "함."),
        (r"했습니다\.$", "했음."),
        (r"하였다\.$", "했음."),
        (r"했다\.$", "했음."),
        (r"한다\.$", "함."),
        (r"된다\.$", "됨."),
        (r"되었다\.$", "됐음."),
        (r"있다\.$", "있음."),
        (r"없다\.$", "없음."),
        (r"필요하다\.$", "필요함."),
        (r"예정이다\.$", "예정임."),
        (r"임\.$", "임."),
    )
    coerced = text
    for pattern, replacement in replacements:
        updated = re.sub(pattern, replacement, coerced)
        if updated != coerced:
            return updated
    if re.search(r"(함\.|음\.|됨\.|임\.|필요함\.|예정임\.)$", coerced):
        return coerced
    if coerced.endswith("."):
        coerced = coerced[:-1].rstrip()
    return f"{coerced}함."
