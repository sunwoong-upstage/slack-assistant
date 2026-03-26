from __future__ import annotations

import json
import logging
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
                "headline": {
                    "type": "string",
                    "description": (
                        "반드시 한국어의 완결된 한 문장으로 작성한다. 줄임표(..., …)를 "
                        "쓰지 말고, parent thread 맥락과 focus message 핵심을 함께 담는다. "
                        "사람 이름은 host가 붙일 수 있으므로 headline 안에서 새로 만들지 않는다."
                    ),
                },
                "bullets": {
                    "type": "array",
                    "description": (
                        "반드시 한국어로 작성한다. 맥락, 핵심 내용, 다음 액션을 "
                        "사실 기반 bullet 2~4개로 정리한다."
                    ),
                    "items": {"type": "string"},
                    "minItems": 2,
                    "maxItems": 4,
                },
            },
            "required": ["headline", "bullets"],
            "additionalProperties": False,
        },
    },
}

SYSTEM_PROMPT = """You summarize Slack threads for a busy person.
Return strict JSON with keys headline and bullets.
Write every headline and bullet in Korean.
- headline: one specific sentence that captures both the parent-thread context
  and the focus message's main point.
- bullets: 2 to 4 concise bullets.
  - include the broader thread context / workstream
  - include the focus message's concrete request, update, or issue
  - include decision, owner, next step, or risk when available
Prioritize the FOCUS_MESSAGE when present, but use ROOT_CONTEXT to explain why it matters.
The AUTHOR of a message is the speaker. Mentioned users inside the message body are not the speaker.
The FOCUS_MESSAGE_AUTHOR is the highest-priority attribution hint
for who said or requested something.
Do not fabricate or substitute people names in the headline. Prefer role-free semantic phrasing
because the host application may prepend the exact author name deterministically.
When writing the summary sentence, prefer the actual message author over any mentioned person.
Do not swap actors. If Gongpil asks Tony to review something, summarize it as Gongpil requesting
Tony's review, not Tony being unavailable or making the request.
Do not invent attendance/status claims unless they are explicitly stated by the message author.
If attribution is ambiguous, say it is ambiguous instead of guessing.
Do not output English prose except for unavoidable proper nouns,
product names, or quoted source text.
Do not use ellipses or incomplete/truncated clauses. The headline must read as a finished sentence.
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
        headline, bullets = self.parse_generated_summary(raw_content)
        return GeneratedSummary(
            headline=headline,
            bullets=bullets,
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
        rendered_thread = []
        for message in thread.messages:
            author = message.author_name or message.user_id or "unknown-user"
            markers: list[str] = []
            if root_message is not None and message.ts == root_message.ts:
                markers.append("ROOT")
            if focus_message is not None and message.ts == focus_message.ts:
                markers.append("FOCUS")
            marker_prefix = f"[{'/'.join(markers)}]" if markers else ""
            rendered_thread.append(
                f"{marker_prefix}[{author}][{message.ts}] {message.text.strip()}"
            )
        prompt = "\n".join(
            [
                "ROOT_CONTEXT:",
                f"- author: {_author_label(root_message) if root_message else '(none)'}",
                (root_message.text.strip() if root_message else "(none)"),
                "",
                "FOCUS_MESSAGE:",
                f"- author: {_author_label(focus_message) if focus_message else '(not specified)'}",
                (focus_message.text.strip() if focus_message else "(not specified)"),
                "",
                "FOCUS_MESSAGE_HINT:",
                f"- author: {selected_message_author_name or '(not specified)'}",
                (
                    selected_message_text_hint.strip()
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
            max_tokens=400,
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
    def parse_generated_summary(raw_content: str) -> tuple[str, tuple[str, ...]]:
        content = raw_content.strip()
        if content.startswith("```"):
            lines = [line for line in content.splitlines() if not line.strip().startswith("```")]
            content = "\n".join(lines).strip()

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as error:
            raise UpstageClientError("Upstage response was not valid JSON") from error

        headline = str(parsed.get("headline", "")).strip()
        bullets = tuple(
            str(item).strip() for item in parsed.get("bullets", []) if str(item).strip()
        )[:4]
        if not headline:
            raise UpstageClientError("Upstage response missing headline")
        return headline, bullets


def _author_label(message: SlackMessage | None) -> str:
    if message is None:
        return "(none)"
    return message.author_name or message.user_id or "unknown-user"
