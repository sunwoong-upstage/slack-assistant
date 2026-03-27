# TKT-007: Performance and concurrency

- Status: todo
- Priority: P2

## Goal

여러 사용자가 동시에 같은 시간대에 digest를 요청할 때 shared work를 최대한 dedupe하여 처리한다.

## Scope

- queue / worker 설계
- thread read dedupe
- summary cache
- batch 가능성 검토
- profiling / latency measurement

## Done when

- concurrency architecture 초안이 존재함
- shared work와 per-user fan-out 경계가 정의됨
- 병목 구간이 측정 가능해짐
