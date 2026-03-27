# ADR-0002: Favor emoji-driven digest matching over direct-mention-driven matching

- Status: proposed
- Date: 2026-03-27

## Context

실사용 관점에서 “내가 언급된 것 전부”는 noise가 많다.
반면 사용자가 직접 `:loading:` 같은 signal을 남긴 항목은
“나중에 다시 볼 것”이라는 의도가 더 명확하다.

또한 direct mention은 이미 해결된 task / FYI / 일정 공유까지 많이 포함할 수 있다.

## Decision

기본 방향은 다음으로 제안한다:

- digest 기본값은 **watched emoji 중심**
- direct mention 포함 여부는 **옵션화**
- 향후 Team Group / User Group 추적은 별도 옵션으로 추가

## Consequences

### Positive

- digest noise 감소
- 사용자가 통제 가능한 signal 중심
- “다시 볼 것”에 더 가까운 backlog성 UX 제공

### Negative

- 사용자 onboarding이 조금 더 필요함
- 이모지를 직접 달지 않은 중요한 항목은 놓칠 수 있음

## Rejected Alternatives

- direct mention을 항상 기본 포함
- 모든 mention / alias / group mention을 한 번에 기본 포함
