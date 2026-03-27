# TKT-003: Semantic summary quality hardening

- Status: todo
- Priority: P0

## Goal

semantic-only summary schema, host rendering, prompt, evaluation harness를 더 고도화한다.

## Scope

- actor drift 방지
- 한국어 note tone 고정
- ellipsis/truncation 방지
- placeholder leak 방지
- eval harness에 real-world failing case 계속 추가

## Done when

- 품질 계약이 테스트와 eval harness에 반영됨
- 새로운 failing case를 재현/고정할 수 있음
