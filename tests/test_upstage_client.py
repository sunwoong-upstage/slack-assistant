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
    summary = UpstageClient.parse_generated_summary(
        "```json\n"
        '{"tone_style":"note","focus_summary":"출시 준비 완료함.",'
        '"context_summary":"문서와 QA 준비가 끝났음.",'
        '"next_step_summary":"배포만 진행하면 됨.","risk_summary":null}\n'
        "```"
    )

    assert summary.tone_style == "note"
    assert summary.focus_summary == "출시 준비 완료함."
    assert summary.context_summary == "문서와 QA 준비가 끝났음."
    assert summary.next_step_summary == "배포만 진행하면 됨."
    assert summary.risk_summary is None


def test_build_messages_marks_root_and_focus(sample_thread: SlackThread) -> None:
    client = StubUpstageClient(
        [
            '{"tone_style":"note","focus_summary":"요청 내용 확인함.",'
            '"context_summary":"배경 논의 이어지는 중임.",'
            '"next_step_summary":null,"risk_summary":null}'
        ]
    )

    messages = client._build_messages(sample_thread, selected_message_ts="1710000000.000100")
    prompt = str(messages[1]["content"])

    assert "ROOT_CONTEXT:" in prompt
    assert "AUTHOR_PLACEHOLDERS:" in prompt
    assert "- FOCUS_AUTHOR: internal participant reference only" in prompt
    assert "FOCUS_MESSAGE:" in prompt
    assert "FOCUS_MESSAGE_HINT:" in prompt
    assert "THREAD_TIMELINE:" in prompt
    assert "[ROOT/FOCUS][FOCUS_AUTHOR][1710000000.000100] Need a summary" in prompt
    assert "Alice" not in prompt


@pytest.mark.asyncio
async def test_summarize_thread_retries_retryable_errors(sample_thread: SlackThread) -> None:
    client = StubUpstageClient(
        [
            StatusError(429),
            (
                '{"tone_style":"note","focus_summary":"출시 준비 완료함.",'
                '"context_summary":"문서 준비 끝났음.",'
                '"next_step_summary":"배포 진행하면 됨.",'
                '"risk_summary":null}'
            ),
        ],
        max_retries=1,
    )

    summary = await client.summarize_thread(sample_thread)

    assert summary.focus_summary == "출시 준비 완료함."
    assert client.calls == ["solar-pro", "solar-pro"]


@pytest.mark.asyncio
async def test_summarize_thread_uses_fallback_model(sample_thread: SlackThread) -> None:
    client = StubUpstageClient(
        [
            RuntimeError("primary failed"),
            (
                '{"tone_style":"note","focus_summary":"대체 모델로 요약 완료함.",'
                '"context_summary":"기본 모델 실패했음.",'
                '"next_step_summary":null,"risk_summary":null}'
            ),
        ],
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
        "tone_style",
        "focus_summary",
        "context_summary",
        "next_step_summary",
        "risk_summary",
    ]


def test_system_prompt_requires_korean_output() -> None:
    from slack_assistant.upstage_client import SYSTEM_PROMPT

    assert "Write every field in Korean." in SYSTEM_PROMPT
    assert "Do not use ellipses or incomplete/truncated clauses." in SYSTEM_PROMPT
    assert "Do not output any placeholder token" in SYSTEM_PROMPT


def test_parse_generated_summary_strips_placeholder_tokens_and_bad_suffixes() -> None:
    summary = UpstageClient.parse_generated_summary(
        '{"tone_style":"note","focus_summary":"FOCUS_AUTHOR가 작업 진행 중임음.",'
        '"context_summary":"ROOT_AUTHOR가 배경 설명함.",'
        '"next_step_summary":null,"risk_summary":null}'
    )

    assert summary.focus_summary == "작업 진행 중임."
    assert summary.context_summary == "배경 설명함."
