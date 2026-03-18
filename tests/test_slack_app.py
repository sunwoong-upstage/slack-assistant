from __future__ import annotations

import asyncio

from slack_assistant.slack_app import _run_summary_job, build_shortcut_handler


class FakeService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def summarize_thread(self, channel_id: str, thread_ts: str) -> str:
        self.calls.append((channel_id, thread_ts))
        await asyncio.sleep(0)
        return "summary text"


class FakeClient:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def chat_postMessage(self, *, channel: str, text: str) -> None:  # noqa: N802
        self.messages.append((channel, text))


def test_build_shortcut_handler_acks_before_dispatch() -> None:
    service = FakeService()
    client = FakeClient()
    acked: list[str] = []
    runner_calls: list[tuple[FakeService, FakeClient, str, str, str]] = []

    def ack() -> None:
        acked.append("ack")

    def runner(
        runner_service: FakeService,
        runner_client: FakeClient,
        user_id: str,
        channel_id: str,
        thread_ts: str,
    ) -> None:
        runner_calls.append((runner_service, runner_client, user_id, channel_id, thread_ts))

    handler = build_shortcut_handler(service, runner=runner)
    handler(
        ack,
        {
            "channel": {"id": "C123"},
            "message": {"ts": "1710.1", "thread_ts": "1710.1"},
            "user": {"id": "U123"},
        },
        client,
    )

    assert acked == ["ack"]
    assert runner_calls == [(service, client, "U123", "C123", "1710.1")]


def test_run_summary_job_delivers_dm_message() -> None:
    service = FakeService()
    client = FakeClient()

    _run_summary_job(service, client, "U123", "C123", "1710.1")

    assert service.calls == [("C123", "1710.1")]
    assert client.messages == [("U123", "summary text")]
