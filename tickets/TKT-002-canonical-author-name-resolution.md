# TKT-002: Canonical author name resolution

- Status: todo
- Priority: P0

## Goal

`user_id -> display_name(real_name)` 기반 canonical author name resolution을 추가한다.

## Why

- MCP text 기반 이름 문자열은 흔들릴 수 있음
- workspace 규칙상 canonical name 형태가 이미 존재함

## Scope

- user_id 기반 canonical lookup 경로 설계
- digest / shortcut / linked-thread / search-hit 전 경로 통일
- bot/system 메시지 fallback 규칙 정의

## Done when

- visible author name이 canonical source로 통일됨
- 관련 테스트 추가됨
- 기존 rendered text 의존 경로가 줄어듦
