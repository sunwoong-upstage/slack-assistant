from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

from slack_assistant.config import load_config
from slack_assistant.models import SlackMessage, SlackThread
from slack_assistant.services import (
    _render_author_grounded_headline,
    _render_supporting_bullets,
)
from slack_assistant.upstage_client import UpstageClient

NOTE_ENDING = re.compile(r"(함\.|음\.|됨\.|임\.|필요함\.|예정임\.)$")


@dataclass(frozen=True)
class EvalCase:
    name: str
    thread: SlackThread
    focus_ts: str
    expected_author: str
    banned_names: tuple[str, ...]
    expected_keywords: tuple[str, ...]


def build_cases() -> list[EvalCase]:
    return [
        EvalCase(
            name="doc_review_request",
            expected_author="Gongpil(공정필)",
            banned_names=("Tony(최선웅)", "Yoonju(최윤주)", "Sophie(정지혜)"),
            expected_keywords=("문서", "검토", "리뷰"),
            focus_ts="1.2",
            thread=SlackThread(
                channel_id="C1",
                thread_ts="1.1",
                messages=(
                    SlackMessage(
                        channel_id="C1",
                        ts="1.1",
                        author_name="Gongpil(공정필)",
                        text="소마 공유 문서 최종 정리 중임.",
                    ),
                    SlackMessage(
                        channel_id="C1",
                        ts="1.2",
                        author_name="Gongpil(공정필)",
                        text="<@U_TONY|Tony(최선웅)> 문서 리뷰 부탁드립니다.",
                    ),
                ),
            ),
        ),
        EvalCase(
            name="schedule_conflict",
            expected_author="Gongpil(공정필)",
            banned_names=("Tony(최선웅)",),
            expected_keywords=("일정", "미팅", "참석"),
            focus_ts="2.2",
            thread=SlackThread(
                channel_id="C2",
                thread_ts="2.1",
                messages=(
                    SlackMessage(
                        channel_id="C2",
                        ts="2.1",
                        author_name="Gongpil(공정필)",
                        text="4시에 다른 필수 미팅이 잡혀 있음.",
                    ),
                    SlackMessage(
                        channel_id="C2",
                        ts="2.2",
                        author_name="Gongpil(공정필)",
                        text="16시 이후 검토 진행 부탁드립니다.",
                    ),
                ),
            ),
        ),
        EvalCase(
            name="coach_contract_review",
            expected_author="Yoonju Choi",
            banned_names=("Gongpil(공정필)", "Sophie(정지혜)"),
            expected_keywords=("계약", "검토", "서비스 범위"),
            focus_ts="3.2",
            thread=SlackThread(
                channel_id="C3",
                thread_ts="3.1",
                messages=(
                    SlackMessage(
                        channel_id="C3",
                        ts="3.1",
                        author_name="Yoonju Choi",
                        text="코치 계약서 검토 중임.",
                    ),
                    SlackMessage(
                        channel_id="C3",
                        ts="3.2",
                        author_name="Yoonju Choi",
                        text="4조 서비스 범위 문구 재검토 필요합니다.",
                    ),
                ),
            ),
        ),
        EvalCase(
            name="external_lecturer_request",
            expected_author="Chris(양세원)",
            banned_names=("Tony(최선웅)", "YoungHoon(전영훈)"),
            expected_keywords=("강사", "자료", "전달"),
            focus_ts="4.2",
            thread=SlackThread(
                channel_id="C4",
                thread_ts="4.1",
                messages=(
                    SlackMessage(
                        channel_id="C4",
                        ts="4.1",
                        author_name="Chris(양세원)",
                        text="외부 강사 진행 방식 검토 중임.",
                    ),
                    SlackMessage(
                        channel_id="C4",
                        ts="4.2",
                        author_name="Chris(양세원)",
                        text="자료 전달과 진행 방식 요약 부탁드립니다.",
                    ),
                ),
            ),
        ),
        EvalCase(
            name="referral_code",
            expected_author="Jay",
            banned_names=("Tony(최선웅)",),
            expected_keywords=("referral", "code", "발급"),
            focus_ts="5.2",
            thread=SlackThread(
                channel_id="C5",
                thread_ts="5.1",
                messages=(
                    SlackMessage(
                        channel_id="C5",
                        ts="5.1",
                        author_name="Jay",
                        text="엠버서더 운영안 정리 중임.",
                    ),
                    SlackMessage(
                        channel_id="C5",
                        ts="5.2",
                        author_name="Jay",
                        text="referral code 발급 방식 검토 요청합니다.",
                    ),
                ),
            ),
        ),
        EvalCase(
            name="feedback_share",
            expected_author="Jay",
            banned_names=("Tony(최선웅)",),
            expected_keywords=("피드백", "기획안", "검토"),
            focus_ts="6.2",
            thread=SlackThread(
                channel_id="C6",
                thread_ts="6.1",
                messages=(
                    SlackMessage(
                        channel_id="C6",
                        ts="6.1",
                        author_name="Jay",
                        text="웅진 기업협업프로젝트 기획안 피드백 공유 예정임.",
                    ),
                    SlackMessage(
                        channel_id="C6",
                        ts="6.2",
                        author_name="Jay",
                        text="기술 및 데이터 지원 범위, 실현 가능성 추가 검토 요청합니다.",
                    ),
                ),
            ),
        ),
        EvalCase(
            name="test1",
            expected_author="Tony(최선웅)",
            banned_names=(),
            expected_keywords=("테스트1", "논의", "진행"),
            focus_ts="7.1",
            thread=SlackThread(
                channel_id="C7",
                thread_ts="7.1",
                messages=(
                    SlackMessage(
                        channel_id="C7",
                        ts="7.1",
                        author_name="Tony(최선웅)",
                        text="테스트1 관련 초기 논의 시작합니다.",
                    ),
                ),
            ),
        ),
        EvalCase(
            name="test2",
            expected_author="Tony(최선웅)",
            banned_names=(),
            expected_keywords=("테스트2", "작업", "요청"),
            focus_ts="8.1",
            thread=SlackThread(
                channel_id="C8",
                thread_ts="8.1",
                messages=(
                    SlackMessage(
                        channel_id="C8",
                        ts="8.1",
                        author_name="Tony(최선웅)",
                        text="테스트2 요청했고 관련 작업 진행 중입니다.",
                    ),
                ),
            ),
        ),
        EvalCase(
            name="test3",
            expected_author="Tony(최선웅)",
            banned_names=(),
            expected_keywords=("테스트3", "확인", "조치"),
            focus_ts="9.1",
            thread=SlackThread(
                channel_id="C9",
                thread_ts="9.1",
                messages=(
                    SlackMessage(
                        channel_id="C9",
                        ts="9.1",
                        author_name="Tony(최선웅)",
                        text="테스트3 관련 내용 확인했고 추가 조치 요청합니다.",
                    ),
                ),
            ),
        ),
        EvalCase(
            name="linked_permalink_wrapper",
            expected_author="Tony(최선웅)",
            banned_names=("Chris(양세원)",),
            expected_keywords=("링크", "원문", "확인"),
            focus_ts="10.2",
            thread=SlackThread(
                channel_id="C10",
                thread_ts="10.1",
                messages=(
                    SlackMessage(
                        channel_id="C10",
                        ts="10.1",
                        author_name="Chris(양세원)",
                        text="wrapper 링크 전달함.",
                    ),
                    SlackMessage(
                        channel_id="C10",
                        ts="10.2",
                        author_name="Tony(최선웅)",
                        text="원문 링크 열어서 확인 필요합니다.",
                    ),
                ),
            ),
        ),
        EvalCase(
            name="ambiguity_case",
            expected_author="Gongpil(공정필)",
            banned_names=("Tony(최선웅)", "Chris(양세원)"),
            expected_keywords=("검토", "요청"),
            focus_ts="11.2",
            thread=SlackThread(
                channel_id="C11",
                thread_ts="11.1",
                messages=(
                    SlackMessage(
                        channel_id="C11",
                        ts="11.1",
                        author_name="Gongpil(공정필)",
                        text="누가 최종 확인할지 아직 애매합니다.",
                    ),
                    SlackMessage(
                        channel_id="C11",
                        ts="11.2",
                        author_name="Gongpil(공정필)",
                        text="<@U_TONY|Tony(최선웅)> 우선 검토 부탁드립니다.",
                    ),
                ),
            ),
        ),
        EvalCase(
            name="risk_case",
            expected_author="Chris(양세원)",
            banned_names=("Tony(최선웅)",),
            expected_keywords=("리스크", "자료", "수정"),
            focus_ts="12.2",
            thread=SlackThread(
                channel_id="C12",
                thread_ts="12.1",
                messages=(
                    SlackMessage(
                        channel_id="C12",
                        ts="12.1",
                        author_name="Chris(양세원)",
                        text="강의 자료 수정 리스크가 있습니다.",
                    ),
                    SlackMessage(
                        channel_id="C12",
                        ts="12.2",
                        author_name="Chris(양세원)",
                        text="자료 수정 범위와 리스크 정리 요청합니다.",
                    ),
                ),
            ),
        ),
    ]


def evaluate_case(
    case: EvalCase,
    summary_headline: str,
    bullets: tuple[str, ...],
) -> tuple[bool, list[str]]:
    issues: list[str] = []
    prefix = f"{case.expected_author}: "
    if not summary_headline.startswith(prefix):
        issues.append("wrong_author_prefix")
    body = (
        summary_headline[len(prefix):]
        if summary_headline.startswith(prefix)
        else summary_headline
    )
    if "..." in body or "…" in body:
        issues.append("ellipsis")
    if re.search(r"(다\.|입니다\.)$", body):
        issues.append("non_note_tone")
    if not NOTE_ENDING.search(body):
        issues.append("headline_not_note_style")
    for bullet in bullets:
        if "..." in bullet or "…" in bullet:
            issues.append("bullet_ellipsis")
        if re.search(r"(다\.|입니다\.)$", bullet):
            issues.append("bullet_non_note_tone")
        if not NOTE_ENDING.search(bullet):
            issues.append("bullet_not_note_style")
    lowered_blob = " ".join((body, *bullets))
    if not any(keyword in lowered_blob for keyword in case.expected_keywords):
        issues.append("missing_focus_keyword")
    for name in case.banned_names:
        if name and name in lowered_blob:
            issues.append(f"name_leak:{name}")
    if re.search(r"\b(?:FOCUS_AUTHOR|ROOT_AUTHOR|AUTHOR_\d+|MENTION)\b", lowered_blob):
        issues.append("placeholder_leak")
    return (not issues, issues)


async def main() -> None:
    config = load_config()
    client = UpstageClient(
        api_key=config.upstage_api_key or "",
        base_url=config.upstage_base_url,
        model=config.upstage_model,
        fallback_model=config.upstage_fallback_model,
        timeout_seconds=config.upstage_timeout_seconds,
        max_retries=config.upstage_max_retries,
    )
    cases = build_cases()
    print(
        "model="
        f"{config.upstage_model} fallback={config.upstage_fallback_model} "
        f"base_url={config.upstage_base_url}"
    )
    passed = 0
    for case in cases:
        try:
            summary = await client.summarize_thread(
                case.thread,
                selected_message_ts=case.focus_ts,
                selected_message_author_name=case.expected_author,
                selected_message_text_hint=next(
                    msg.text for msg in case.thread.messages if msg.ts == case.focus_ts
                ),
            )
            headline = _render_author_grounded_headline(summary.focus_summary, case.expected_author)
            bullets = _render_supporting_bullets(summary)
            ok, issues = evaluate_case(case, headline, bullets)
        except Exception as error:  # noqa: BLE001
            ok = False
            headline = ""
            bullets = ()
            issues = [f"exception:{error}"]
        print(f"[{'PASS' if ok else 'FAIL'}] {case.name}")
        if headline:
            print(f"  headline: {headline}")
        if bullets:
            for bullet in bullets:
                print(f"  bullet: {bullet}")
        if issues:
            print(f"  issues: {', '.join(issues)}")
        passed += int(ok)
    print(f"passed={passed}/{len(cases)}")
    if passed != len(cases):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
