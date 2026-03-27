# TODO / Roadmap

현재 TODO는 단순 아이디어 나열이 아니라 **우선순위 + 티켓 + ADR 연결** 기준으로 관리한다.

## 평가 요약

현재 backlog는 방향은 좋지만, 아래 문제가 있었음:

1. **우선순위가 섞여 있음**
   - product 방향 결정
   - UX polish
   - 성능 최적화
   - 이름 canonicalization
   가 한 리스트에 섞여 있어 실행 순서가 불명확했음.

2. **완료 기준이 없음**
   - “좋아 보이는 개선안” 수준에서 멈춰 있고
   - 언제 done 인지 정의가 부족했음.

3. **결정 이유가 문서화되지 않음**
   - 왜 이모지 중심으로 갈지
   - 왜 semantic-only + host-rendering 구조인지
   - 왜 shortcut과 digest를 분리해서 봐야 하는지
   같은 결정 이유는 ADR로 남길 필요가 있음.

4. **큰 일감을 쪼갠 티켓 단위가 없음**
   - 다음 세션에서 바로 집어 들 수 있는 “작은 작업 단위”가 부족했음.

## 운영 원칙

- **커밋**: 작업 하나 끝날 때마다 작게
- **ADR**: 다시 논쟁될 결정 / 아키텍처 원칙 / 외부 제약 대응 시 작성
- **Tickets**: 실제 구현 가능한 단위로 쪼개서 관리
- **TODO.md**: 이제 개별 아이디어 메모장이 아니라 **로드맵 인덱스** 역할만 함

## 우선순위 로드맵

### P0 — 정확도 / 일관성 / 실사용 안정화

1. **TKT-001** emoji-first digest defaults 재정리  
   - direct mention 기본 포함 여부 재검토  
   - 목표: noise 줄이고 “다시 볼 것만” digest에 남기기

2. **TKT-002** canonical author name resolution  
   - `user_id -> display_name(real_name)` canonicalization  
   - 목표: Chris Yang / Chris(양세원) 같은 흔들림 제거

3. **TKT-003** semantic-only summary quality hardening  
   - prompt / schema / host rendering / TDD 고도화  
   - 목표: actor drift, 영어 drift, 말투 drift 재발 방지

### P1 — 사용자 경험 고도화

4. **TKT-004** Team Group / User Group tracking  
   - 예: `@team-education`  
   - 목표: 직접 멘션이 없어도 팀 단위 업무 포착

5. **TKT-005** formatting & rendering polish  
   - digest / shortcut / App Home surface별 레이아웃 정리  
   - 목표: 더 읽기 쉽고 덜 어색한 출력

6. **TKT-006** Slack app branding / onboarding polish  
   - 앱 아이콘, App Home copy, 설정 UX  
   - 목표: 팀 전체 온보딩성 개선

### P2 — 성능 / 운영성

7. **TKT-007** performance & concurrency design  
   - 병렬 처리, shared dedupe, batching, profiling  
   - 목표: 여러 명 동시 요청 시 효율적 처리

8. **TKT-008** structured error capture / observability  
   - Railway 로그에만 의존하지 않는 앱 내부 에러 저장  
   - 목표: 운영 디버깅 속도 개선

## ADR 문서

- `docs/adr/0001-semantic-summary-and-host-rendered-actors.md`
- `docs/adr/0002-emoji-first-digest-direction.md`

## Ticket 문서

- `tickets/TKT-001-emoji-first-digest-defaults.md`
- `tickets/TKT-002-canonical-author-name-resolution.md`
- `tickets/TKT-003-semantic-summary-quality-hardening.md`
- `tickets/TKT-004-team-group-tracking.md`
- `tickets/TKT-005-formatting-and-rendering-polish.md`
- `tickets/TKT-006-slack-app-branding-and-onboarding.md`
- `tickets/TKT-007-performance-and-concurrency.md`
- `tickets/TKT-008-structured-error-capture-and-observability.md`
