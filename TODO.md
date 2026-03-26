# TODO

## 추후 개선 예정안

- 다이제스트 기본 매칭 기준을 **직접 멘션 제외 / watched emoji 중심**으로 재정리하기
  - 직접 멘션 포함 여부는 옵션화 검토
- **Team Group / User Group** 추적 기능 추가
  - 예: `@team-education`
  - 사용자별로 N개까지 설정 가능하게 하기
- Slack 앱 **아이콘 / 브랜딩 / App Home 정리**
  - 앱 아이콘 설정
  - 소개 문구 / 사용 가이드 정리
  - 설정 UX 다듬기
- 프롬프트 / structured output / host rendering 고도화
  - 더 일관적인 한국어 응답
  - actor attribution 안정화
  - truncation/ellipsis 없는 완결형 문장 유지
  - digest / shortcut 출력 품질 계약을 TDD로 계속 고정

## Future improvements

- Revisit digest defaults so **watched emojis** become the primary matching signal
  - Consider making direct-mention inclusion optional
- Add **Team Group / User Group** tracking
  - Example: `@team-education`
  - Allow each user to configure up to N tracked groups
- Improve Slack app **icon / branding / App Home UX**
  - app icon
  - clearer onboarding copy
  - cleaner settings experience
- Further harden prompts / structured output / host rendering
  - consistent Korean output
  - stable actor attribution
  - no truncated / ellipsis-style lead sentences
  - keep digest / shortcut quality contracts locked with TDD
