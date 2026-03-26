from __future__ import annotations

import json
import logging
from typing import cast

import httpx
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

from .models import GeneratedSummary, SlackThread

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You summarize Slack threads for a busy person.
Return strict JSON with keys headline and bullets.
- headline: one specific sentence that captures both the parent-thread context
  and the focus message's main point.
- bullets: 2 to 4 concise bullets.
  - include the broader thread context / workstream
  - include the focus message's concrete request, update, or issue
  - include decision, owner, next step, or risk when available
Prioritize the FOCUS_MESSAGE when present, but use ROOT_CONTEXT to explain why it matters.
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
    ) -> GeneratedSummary:
        messages = self._build_messages(thread, selected_message_ts=selected_message_ts)
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
    ) -> list[ChatCompletionMessageParam]:
        root_message = thread.root_message
        focus_message = next(
            (message for message in thread.messages if message.ts == selected_message_ts),
            None,
        )
        rendered_thread = []
        for message in thread.messages:
            author = message.user_id or "unknown-user"
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
                (root_message.text.strip() if root_message else "(none)"),
                "",
                "FOCUS_MESSAGE:",
                (focus_message.text.strip() if focus_message else "(not specified)"),
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
            temperature=0.2,
            max_tokens=400,
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
