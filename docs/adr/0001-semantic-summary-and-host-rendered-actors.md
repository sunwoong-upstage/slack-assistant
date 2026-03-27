# ADR-0001: Semantic-only summaries with host-rendered actor names

- Status: accepted
- Date: 2026-03-27

## Context

Digest / shortcut summaries에서 다음 문제가 반복되었다:

- actor drift
- 영어/한국어 혼합
- `~다. / ~입니다. / ~음.` 말투 혼재
- LLM이 visible actor 이름까지 생성함

Slack 쪽에는 `user_id`, `author_name`, focus hit metadata가 이미 존재하므로,
사람 이름까지 모델에게 맡길 필요가 없었다.

## Decision

- LLM은 **semantic-only structured output** 만 생성한다.
- visible actor 이름은 **host code가 deterministic하게 렌더링**한다.
- summary schema는 semantic field 중심으로 유지한다.
- note-style 톤(`~함. / ~음.`)은 prompt + host normalization으로 관리한다.

## Consequences

### Positive

- actor drift 감소
- 이름 일관성 개선
- 출력 품질 계약을 테스트하기 쉬워짐
- host에서 최종 렌더링을 통제 가능

### Negative

- host rendering 로직 복잡도 증가
- prompt/schema/formatter/test가 더 강하게 결합됨

## Rejected Alternatives

- LLM이 사람 이름까지 포함한 완성 문장을 쓰게 두기
- free-form headline + bullets 구조를 유지하기
