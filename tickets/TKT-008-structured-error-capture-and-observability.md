# TKT-008: Structured error capture and observability

- Status: todo
- Priority: P2

## Goal

Railway 로그만 보지 않고 앱 내부에서 structured error event를 저장/조회할 수 있게 한다.

## Scope

- JSONL 기반 error event 저장
- digest / shortcut / settings surface별 error context 저장
- 운영 확인용 뷰 / 알림 검토

## Done when

- 에러 이벤트를 구조화해서 저장 가능
- 운영자가 나중에 재현/분석 가능한 최소 필드가 남음
