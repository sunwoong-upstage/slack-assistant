# ADR Guide

이 폴더는 **Architecture Decision Record** 를 보관한다.

## 언제 ADR을 쓰나

다음 중 하나면 ADR 대상이다:

- 다시 논쟁될 수 있는 방향 결정
- 외부 제약 때문에 특정 선택을 한 경우
- product 기본값 / 동작 원칙 변경
- 나중에 “왜 이렇게 했지?”가 다시 나올 가능성이 큰 경우

예:
- MCP 유지 vs Slack API 직결
- digest를 whole-day scan으로 유지
- visible actor 이름은 host가 렌더링
- direct mention 기본 포함 여부 재검토

## 언제 ADR이 아닌가

이런 건 보통 commit만으로 충분하다:

- 작은 버그 수정
- 테스트 추가
- 변수명 정리
- 이미 결정된 방향 안에서의 구현 디테일

## 운영 규칙

- 새 원칙이 생기면 **새 ADR**
- 기존 원칙을 뒤집으면 **기존 ADR 업데이트 또는 superseded 처리**
- ADR은 짧고 명확하게

## 상태 값

- `proposed`
- `accepted`
- `superseded`
- `deprecated`

## 템플릿

```md
# ADR-XXXX: 제목

- Status: proposed | accepted | superseded | deprecated
- Date: YYYY-MM-DD

## Context
배경 / 문제 / 제약

## Decision
무엇을 결정했는지

## Consequences
좋은 점 / 나쁜 점 / 트레이드오프

## Rejected Alternatives
- 대안 A
- 대안 B
```
