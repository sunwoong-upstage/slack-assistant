from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest
from openai.types.chat import ChatCompletionMessageParam

from slack_assistant.models import SlackMessage, SlackThread
from slack_assistant.upstage_client import (
    SUMMARY_RESPONSE_FORMAT,
    UpstageClient,
    UpstageClientError,
)


class StatusError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"status {status_code}")
        self.status_code = status_code


class StubUpstageClient(UpstageClient):
    def __init__(self, responses: list[object], **kwargs: object) -> None:
        super().__init__(
            api_key="test-key",
            base_url="https://api.upstage.ai/v1",
            model="solar-pro",
            fallback_model="solar-mini",
            client=MagicMock(),
            **kwargs,
        )
        self.calls: list[str] = []
        self._responses = responses

    async def _request_completion(
        self, model: str, messages: list[ChatCompletionMessageParam]
    ) -> str:
        self.calls.append(model)
        result = self._responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return str(result)


@pytest.fixture
def sample_thread() -> SlackThread:
    return SlackThread(
        channel_id="C123",
        thread_ts="1710000000.000100",
        messages=(
            SlackMessage(
                channel_id="C123",
                ts="1710000000.000100",
                user_id="U1",
                author_name="Alice",
                text="Need a summary",
            ),
        ),
    )


def test_parse_generated_summary_accepts_markdown_wrapped_json() -> None:
    headline, bullets = UpstageClient.parse_generated_summary(
        '```json\n{"headline":"Shipping today","bullets":["Docs done","QA green"]}\n```'
    )

    assert headline == "Shipping today"
    assert bullets == ("Docs done", "QA green")


def test_build_messages_marks_root_and_focus(sample_thread: SlackThread) -> None:
    client = StubUpstageClient(['{"headline":"ok","bullets":["one"]}'])

    messages = client._build_messages(sample_thread, selected_message_ts="1710000000.000100")
    prompt = str(messages[1]["content"])

    assert "ROOT_CONTEXT:" in prompt
    assert "- author: Alice" in prompt
    assert "FOCUS_MESSAGE:" in prompt
    assert "FOCUS_MESSAGE_HINT:" in prompt
    assert "THREAD_TIMELINE:" in prompt
    assert "[ROOT/FOCUS][Alice][1710000000.000100] Need a summary" in prompt


@pytest.mark.asyncio
async def test_summarize_thread_retries_retryable_errors(sample_thread: SlackThread) -> None:
    client = StubUpstageClient(
        [StatusError(429), '{"headline":"Shipping today","bullets":["Docs done"]}'],
        max_retries=1,
    )

    summary = await client.summarize_thread(sample_thread)

    assert summary.headline == "Shipping today"
    assert client.calls == ["solar-pro", "solar-pro"]


@pytest.mark.asyncio
async def test_summarize_thread_uses_fallback_model(sample_thread: SlackThread) -> None:
    client = StubUpstageClient(
        [RuntimeError("primary failed"), '{"headline":"Fallback used","bullets":["Condensed"]}'],
        max_retries=0,
    )

    summary = await client.summarize_thread(sample_thread)

    assert summary.fallback_used is True
    assert client.calls == ["solar-pro", "solar-mini"]


def test_parse_generated_summary_rejects_invalid_json() -> None:
    with pytest.raises(UpstageClientError):
        UpstageClient.parse_generated_summary("not-json")


def test_retryable_timeout_detection() -> None:
    assert UpstageClient._is_retryable_error(httpx.TimeoutException("timeout")) is True


def test_normalize_base_url_rewrites_v2_to_v1() -> None:
    assert UpstageClient._normalize_base_url("https://api.upstage.ai/v2") == (
        "https://api.upstage.ai/v1"
    )
    assert UpstageClient._normalize_base_url("https://api.upstage.ai/v1") == (
        "https://api.upstage.ai/v1"
    )


def test_summary_response_format_uses_strict_json_schema() -> None:
    assert SUMMARY_RESPONSE_FORMAT["type"] == "json_schema"
    assert SUMMARY_RESPONSE_FORMAT["json_schema"]["strict"] is True
    assert SUMMARY_RESPONSE_FORMAT["json_schema"]["schema"]["required"] == [
        "headline",
        "bullets",
    ]


def test_system_prompt_requires_korean_output() -> None:
    from slack_assistant.upstage_client import SYSTEM_PROMPT

    assert "Write every headline and bullet in Korean." in SYSTEM_PROMPT
    assert "Do not use ellipses or incomplete/truncated clauses." in SYSTEM_PROMPT
