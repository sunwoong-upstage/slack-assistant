# Tickets

이 폴더는 다음 작업을 **개별 실행 단위**로 쪼개서 관리한다.

## 원칙

- TODO.md는 **로드맵 인덱스**
- `tickets/`는 **실제로 집어 들고 구현할 작업 단위**
- 하나의 ticket은 가능하면
  - 목표
  - 범위
  - 완료 조건
  - 테스트 기준
  를 포함해야 한다

## 추천 상태 관리

각 ticket 상단에 다음 중 하나를 둔다:

- Status: todo
- Status: in_progress
- Status: blocked
- Status: done

## 추천 작업 흐름

1. TODO.md에서 우선순위 확인
2. ticket 하나 선택
3. 관련 ADR 확인
4. 구현 / 테스트 / 커밋
5. ticket 상태 갱신
