# Slack Assistant

> Personal Slack catch-up assistant for teams  
> 개인/팀용 Slack 캐치업 어시스턴트

Slack Assistant sends each user a scheduled weekday DM digest of the Slack threads they should catch up on.

Slack Assistant는 각 사용자에게 평일마다 DM으로 “오늘 내가 확인해야 할 스레드” 요약을 보내주는 Slack 앱입니다.

---

# 1. What this app does / 이 앱이 하는 일

## English

This app currently supports two user-facing flows:

1. **Scheduled weekday digest**
   - Users can discover setup through:
     - the `/digest` slash command
     - the Slack Assistant **Home** tab
     - the `Digest settings` global shortcut
   - Each user configures:
     - weekdays
     - delivery time
     - timezone
     - watched emojis
   - The app sends a **DM-only** digest at the configured time.
   - The digest includes threads that:
     - directly mentioned the user
     - or contain a watched emoji reaction that the same user left
   - Each matched thread includes:
     - a short generated summary
     - a permalink back to Slack
   - If nothing matched that day, the app still sends a short “nothing matched today” DM.

2. **Manual one-off thread summary**
   - Users can still use the **Summarize thread** message shortcut.

Important scope note:

- Scheduled digests are **DM-only**
- Alias / team-name matching is **intentionally excluded** from the digest flow
- Live Slack MCP reaction-search behavior still needs workspace validation before the emoji path is considered production-proven

## 한국어

이 앱은 현재 사용자 관점에서 두 가지 기능을 제공합니다.

1. **평일 예약 DM 다이제스트**
   - 사용자는 아래 진입점으로 쉽게 설정할 수 있습니다:
     - `/digest` 슬래시 커맨드
     - Slack Assistant **Home** 탭
     - `Digest settings` 글로벌 shortcut
   - 각 사용자가 직접 설정할 수 있습니다:
     - 요일
     - 발송 시간
     - 타임존
     - 감시할 이모지 목록
   - 설정한 시간에 **DM 전용** 다이제스트가 발송됩니다.
   - 다이제스트에는 아래 조건에 맞는 스레드가 포함됩니다:
     - 사용자를 직접 멘션한 스레드
     - 또는 사용자가 직접 남긴 특정 이모지 반응이 있는 스레드
   - 각 스레드에는 다음이 포함됩니다:
     - 짧은 생성 요약
     - Slack permalink
   - 해당 날짜에 매칭된 항목이 없더라도 “오늘은 매칭된 항목이 없음” DM을 보냅니다.

2. **수동 단건 스레드 요약**
   - 기존의 **Summarize thread** 메시지 shortcut도 계속 사용할 수 있습니다.

중요한 범위 제한:

- 예약 다이제스트는 **DM 전용**입니다
- alias / 팀 이름 매칭은 다이제스트 기능에서 **의도적으로 제외**되어 있습니다
- 이모지 검색은 로컬 코드/테스트는 완료됐지만, 실제 Slack workspace에서의 라이브 검증은 아직 필요합니다

---

# 2. High-level architecture / 전체 구조

## English

This app is a Python service that:

- runs a Slack Bolt app
- uses Socket Mode for Slack events/interactions
- serves an OAuth callback endpoint at `/slack/oauth_redirect`
- stores encrypted user tokens and preferences in a local JSON file
- runs a background digest dispatcher in-process

Key pieces:

- `src/slack_assistant/slack_app.py`
  - Slack shortcuts, slash command, App Home, and modal handlers
- `src/slack_assistant/digest_dispatcher.py`
  - scheduled digest polling / DM dispatch
- `src/slack_assistant/services.py`
  - digest candidate discovery + summarization pipeline
- `src/slack_assistant/store.py`
  - encrypted persistence for preferences/tokens/cursors
- `app_manifest.yaml`
  - Slack app manifest template

## 한국어

이 앱은 다음을 수행하는 Python 서비스입니다.

- Slack Bolt 앱 실행
- Slack 이벤트/인터랙션 처리를 위해 Socket Mode 사용
- `/slack/oauth_redirect` 경로로 OAuth 콜백 수신
- 사용자 토큰/설정을 암호화된 JSON 파일에 저장
- 같은 프로세스 안에서 background digest dispatcher 실행

주요 파일:

- `src/slack_assistant/slack_app.py`
  - Slack shortcut, slash command, App Home, modal 처리
- `src/slack_assistant/digest_dispatcher.py`
  - 예약 다이제스트 폴링 / DM 발송
- `src/slack_assistant/services.py`
  - 다이제스트 후보 검색 + 요약 파이프라인
- `src/slack_assistant/store.py`
  - 토큰 / 설정 / 커서 저장
- `app_manifest.yaml`
  - Slack 앱 manifest 템플릿

---

# 3. Requirements / 준비물

## English

You need:

- Python 3.12+
- `uv`
- a Slack workspace where you can install apps
- an Upstage API key
- for local development:
  - a public HTTPS tunnel such as **ngrok**

## 한국어

필요한 것:

- Python 3.12+
- `uv`
- Slack 앱 설치가 가능한 Slack workspace
- Upstage API key
- 로컬 개발 시:
  - **ngrok** 같은 public HTTPS tunnel

---

# 4. Clone and local setup / 클론 및 로컬 세팅

## English

```bash
git clone git@github.com:sunwoong-upstage/slack-assistant.git
cd slack-assistant
uv sync --extra dev
cp .env.example .env
```

## 한국어

```bash
git clone git@github.com:sunwoong-upstage/slack-assistant.git
cd slack-assistant
uv sync --extra dev
cp .env.example .env
```

---

# 5. Fill out `.env` / `.env` 채우기

## English

You should edit `.env`, not `.env.example`.

### 5.1 Generate local secrets

#### `SLACK_STATE_SECRET`

```bash
openssl rand -hex 32
```

#### `STORE_ENCRYPTION_KEY`

```bash
python3 - <<'PY'
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
PY
```

### 5.2 Slack app values

Get these from your Slack app settings:

- `SLACK_BOT_TOKEN` → **OAuth & Permissions** → **Bot User OAuth Token**
- `SLACK_SIGNING_SECRET` → **Basic Information** → **Signing Secret**
- `SLACK_APP_TOKEN` → **Basic Information** → **App-Level Tokens**
  - create one with scope `connections:write`
- `SLACK_OAUTH_CLIENT_ID` → **Basic Information**
- `SLACK_OAUTH_CLIENT_SECRET` → **Basic Information**

### 5.3 Public app URL

For local development, `APP_BASE_URL` usually comes from ngrok:

```bash
ngrok http 3000
```

If ngrok shows:

```txt
https://abcd-1234.ngrok-free.app -> http://localhost:3000
```

then use:

```env
APP_BASE_URL=https://abcd-1234.ngrok-free.app
```

### 5.4 Upstage

Set:

```env
UPSTAGE_API_KEY=...
```

### 5.5 Values you can usually keep as-is

- `APP_ENV=development`
- `APP_HOST=0.0.0.0`
- `APP_PORT=3000`
- `SLACK_DIGEST_COMMAND=/digest`
- `SLACK_SHORTCUT_CALLBACK_ID=summarize_thread`
- `SLACK_DIGEST_SHORTCUT_CALLBACK_ID=configure_digest_settings`
- `SLACK_DIGEST_VIEW_CALLBACK_ID=configure_digest_settings_modal`
- `SLACK_MCP_BASE_URL=https://mcp.slack.com/mcp`
- `SLACK_MCP_SEARCH_TOOL=search_messages`
- `SLACK_MCP_READ_TOOL=read_thread`
- `SLACK_MCP_PERMALINK_TOOL=chat_getPermalink`
- `UPSTAGE_BASE_URL=https://api.upstage.ai/v1`
- `UPSTAGE_MODEL=solar-pro3`
- `UPSTAGE_FALLBACK_MODEL=solar-pro2`
- `UPSTAGE_TIMEOUT_SECONDS=20`
- `UPSTAGE_MAX_RETRIES=1`
- `STORE_PATH=.data/store.json`
- `SCHEDULER_POLL_SECONDS=30`

## 한국어

수정해야 하는 파일은 `.env`이고, `.env.example`은 예시 파일입니다.

### 5.1 로컬 시크릿 생성

#### `SLACK_STATE_SECRET`

```bash
openssl rand -hex 32
```

#### `STORE_ENCRYPTION_KEY`

```bash
python3 - <<'PY'
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
PY
```

### 5.2 Slack 앱 값

Slack 앱 설정 페이지에서 아래 값을 가져옵니다.

- `SLACK_BOT_TOKEN` → **OAuth & Permissions** → **Bot User OAuth Token**
- `SLACK_SIGNING_SECRET` → **Basic Information** → **Signing Secret**
- `SLACK_APP_TOKEN` → **Basic Information** → **App-Level Tokens**
  - scope는 `connections:write`
- `SLACK_OAUTH_CLIENT_ID` → **Basic Information**
- `SLACK_OAUTH_CLIENT_SECRET` → **Basic Information**

### 5.3 Public app URL

로컬 개발에서는 보통 ngrok 주소를 `APP_BASE_URL`로 사용합니다.

```bash
ngrok http 3000
```

예를 들어 ngrok가 다음처럼 보여주면:

```txt
https://abcd-1234.ngrok-free.app -> http://localhost:3000
```

`.env`에는 이렇게 넣습니다:

```env
APP_BASE_URL=https://abcd-1234.ngrok-free.app
```

### 5.4 Upstage

```env
UPSTAGE_API_KEY=...
```

### 5.5 기본값으로 두어도 되는 항목

- `APP_ENV=development`
- `APP_HOST=0.0.0.0`
- `APP_PORT=3000`
- `SLACK_DIGEST_COMMAND=/digest`
- `SLACK_SHORTCUT_CALLBACK_ID=summarize_thread`
- `SLACK_DIGEST_SHORTCUT_CALLBACK_ID=configure_digest_settings`
- `SLACK_DIGEST_VIEW_CALLBACK_ID=configure_digest_settings_modal`
- `SLACK_MCP_BASE_URL=https://mcp.slack.com/mcp`
- `SLACK_MCP_SEARCH_TOOL=search_messages`
- `SLACK_MCP_READ_TOOL=read_thread`
- `SLACK_MCP_PERMALINK_TOOL=chat_getPermalink`
- `UPSTAGE_BASE_URL=https://api.upstage.ai/v1`
- `UPSTAGE_MODEL=solar-pro3`
- `UPSTAGE_FALLBACK_MODEL=solar-pro2`
- `UPSTAGE_TIMEOUT_SECONDS=20`
- `UPSTAGE_MAX_RETRIES=1`
- `STORE_PATH=.data/store.json`
- `SCHEDULER_POLL_SECONDS=30`

---

# 6. Create the Slack app / Slack 앱 만들기

## English

1. Render the manifest:

```bash
mkdir -p build
APP_BASE_URL=https://your-public-url uv run python scripts/render_manifest.py > build/app_manifest.generated.yaml
```

2. Go to Slack app admin
3. Create a new app **from manifest**
4. Paste `build/app_manifest.generated.yaml`
5. Install the app to your workspace

The manifest already includes:

- slash command: `/digest`
- message shortcut: `Summarize thread`
- global shortcut: `Digest settings`
- App Home setup surface
- Socket Mode enabled
- OAuth redirect URL template

### If you already created the app from scratch

You do **not** need to delete and recreate it.

You can apply the manifest to the existing app:

1. Open your app in Slack app admin
2. Go to **App Manifest**
3. Paste the rendered `build/app_manifest.generated.yaml`
4. Review the config diff
5. Save / apply it
6. Reinstall the app if Slack asks

This is the easiest way to sync slash commands, shortcuts, App Home settings, OAuth redirect URLs, and Socket Mode-related config into an existing manually created app.

## 한국어

1. manifest를 렌더링합니다:

```bash
mkdir -p build
APP_BASE_URL=https://your-public-url uv run python scripts/render_manifest.py > build/app_manifest.generated.yaml
```

2. Slack 앱 관리자 페이지로 이동
3. **manifest로 앱 생성**
4. `build/app_manifest.generated.yaml` 내용 붙여넣기
5. workspace에 앱 설치

이 manifest에는 이미 다음이 포함되어 있습니다.

- slash command: `/digest`
- message shortcut: `Summarize thread`
- global shortcut: `Digest settings`
- App Home 설정 화면
- Socket Mode 활성화
- OAuth redirect URL 템플릿

### 이미 Slack 앱을 from scratch로 만든 경우

기존 앱을 지우고 새로 만들 필요는 없습니다.

이미 만든 앱에도 manifest를 적용할 수 있습니다.

1. Slack 앱 관리자에서 해당 앱 열기
2. **App Manifest** 메뉴로 이동
3. 렌더링된 `build/app_manifest.generated.yaml` 내용을 붙여넣기
4. 변경사항(diff) 확인
5. 저장 / 적용
6. Slack이 요구하면 앱 재설치

이 방법이 가장 간단하게 아래 항목들을 기존 앱에 반영하는 방법입니다.

- slash command
- shortcuts
- App Home 설정
- OAuth redirect URL
- Socket Mode 관련 설정

---

# 7. Run locally / 로컬 실행

## English

```bash
uv run python -m slack_assistant.main
```

Then keep **both** running:

1. your app
2. ngrok tunnel

Why? Because:

- Slack needs to reach your OAuth callback URL
- the digest scheduler must stay alive to send scheduled DMs

## 한국어

```bash
uv run python -m slack_assistant.main
```

그리고 아래 두 개가 모두 살아 있어야 합니다.

1. 앱 프로세스
2. ngrok 터널

이유:

- Slack이 OAuth callback URL에 접근해야 함
- 예약 다이제스트를 보내려면 scheduler가 계속 살아 있어야 함

---

# 8. First-time user flow / 첫 사용자 사용 흐름

## English

1. Install the app in Slack
2. Trigger either:
   - `/digest`
   - the Slack Assistant **Home** tab
   - **Digest settings**
   - or **Summarize thread**
3. If the user has no Slack MCP token yet, the app sends a DM with a connect/auth link
4. Complete OAuth
5. Open **Digest settings**
   - or run `/digest`
   - or click the button in App Home
6. Save:
   - weekdays
   - delivery time
   - timezone
   - watched emojis
7. Wait for the next scheduled run

## 한국어

1. Slack에 앱 설치
2. 아래 중 하나 실행:
   - `/digest`
   - Slack Assistant **Home** 탭
   - **Digest settings**
   - 또는 **Summarize thread**
3. 아직 Slack MCP 토큰이 없으면 앱이 DM으로 인증 링크를 보냄
4. OAuth 완료
5. **Digest settings** 열기
   - 또는 `/digest` 실행
   - 또는 App Home 버튼 클릭
6. 아래 설정 저장:
   - 요일
   - 시간
   - 타임존
   - 감시할 이모지
7. 다음 예약 시간까지 대기

---

# 9. Railway deployment guide / Railway 배포 가이드

## English

Railway is a good choice if:

- you want teammates to use the app
- you want the scheduler to keep running
- you want a stable public HTTPS URL

### Recommended deployment order

1. Push this repo to GitHub
2. Create a Railway project from the GitHub repo
3. Add a **volume**
4. Set env vars
5. Get the Railway public domain
6. Update `APP_BASE_URL`
7. Re-render the Slack manifest
8. Update your Slack app if the URL changed

### 9.1 Create project

- Railway → **New Project**
- **Deploy from GitHub repo**
- choose this repo

### 9.2 Add volume

Because user tokens/preferences/cursors are stored in a file, you should use a persistent volume.

Recommended:

```env
STORE_PATH=/data/store.json
```

### 9.3 Set Railway environment variables

Set the same values as your local `.env`, but:

- `APP_BASE_URL=https://your-service.up.railway.app`
- `STORE_PATH=/data/store.json`
- `APP_HOST=0.0.0.0`
- `APP_PORT=3000`

### 9.4 Start command

If Railway does not auto-detect it correctly, use:

```bash
uv run python -m slack_assistant.main
```

### 9.5 After Railway gives you a public URL

Example:

```txt
https://slack-assistant-production.up.railway.app
```

Then:

1. set `APP_BASE_URL` to that URL
2. render the manifest again
3. update the Slack app if needed

### 9.6 Why deployment is better than local-only

If your laptop is off:

- no OAuth callback
- no scheduled digest

So for real teammate use, deployment is strongly recommended.

## 한국어

Railway는 아래 상황에서 좋은 선택입니다.

- 팀원들도 이 앱을 사용해야 할 때
- scheduler가 항상 살아 있어야 할 때
- 안정적인 public HTTPS URL이 필요할 때

### 권장 배포 순서

1. GitHub에 푸시
2. GitHub repo 기반으로 Railway 프로젝트 생성
3. **Volume 추가**
4. 환경 변수 설정
5. Railway public domain 확인
6. `APP_BASE_URL` 업데이트
7. Slack manifest 다시 렌더링
8. URL이 바뀌었으면 Slack 앱 설정 갱신

### 9.1 프로젝트 생성

- Railway → **New Project**
- **Deploy from GitHub repo**
- 이 repo 선택

### 9.2 Volume 추가

이 앱은 사용자 토큰/설정/커서를 파일로 저장하므로 persistent volume을 쓰는 것이 좋습니다.

권장값:

```env
STORE_PATH=/data/store.json
```

### 9.3 Railway 환경 변수

로컬 `.env`와 거의 동일하지만 아래처럼 바꾸는 것이 일반적입니다.

- `APP_BASE_URL=https://your-service.up.railway.app`
- `STORE_PATH=/data/store.json`
- `APP_HOST=0.0.0.0`
- `APP_PORT=3000`

### 9.4 시작 명령어

Railway가 자동 감지를 못하면 아래를 사용하세요:

```bash
uv run python -m slack_assistant.main
```

### 9.5 Railway URL을 받은 뒤

예:

```txt
https://slack-assistant-production.up.railway.app
```

그 다음:

1. `APP_BASE_URL`에 이 URL 반영
2. manifest 다시 렌더링
3. 필요하면 Slack 앱 설정 갱신

### 9.6 왜 로컬보다 배포가 낫나

노트북이 꺼져 있으면:

- OAuth callback 불가
- 예약 다이제스트 발송 불가

그래서 실제 팀 사용 목적이면 Railway 배포를 강력히 추천합니다.

---

# 10. Validation and checks / 검증 방법

## English

Run:

```bash
uv run --extra dev ruff check src tests
uv run --extra dev mypy src
uv run --extra dev pytest -q
```

## 한국어

아래 명령으로 검증합니다:

```bash
uv run --extra dev ruff check src tests
uv run --extra dev mypy src
uv run --extra dev pytest -q
```

---

# 11. Known limitations / 현재 한계

## English

- Live Slack MCP reaction-search behavior still needs a real workspace validation run
- The app currently stores state in a file, so persistent storage matters in deployment
- Scheduled digests are built in-process, not via a separate worker service

## 한국어

- Slack MCP의 실제 이모지 검색 동작은 real workspace에서 추가 검증이 필요합니다
- 상태를 파일에 저장하므로 배포 환경에서는 persistent storage가 중요합니다
- 예약 다이제스트는 별도 worker가 아니라 앱 프로세스 안에서 동작합니다

---

# 12. Troubleshooting / 문제 해결

## English

### “Slack OAuth redirect does not work”

Check:

- `APP_BASE_URL` is correct
- your tunnel/deployment URL is alive
- the Slack app redirect URL matches your current `APP_BASE_URL`

### “No digest arrives”

Check:

- the app process is running
- the scheduler is running
- the user saved digest settings
- the user completed Slack MCP OAuth
- it is currently one of the configured weekdays/time

### “Digest arrives but emoji threads are missing”

Possible reason:

- live Slack MCP reaction-search behavior may differ from local dry-run assumptions

Check `docs/mcp-capability-spike.md`.

## 한국어

### “Slack OAuth redirect가 안 됨”

확인:

- `APP_BASE_URL`가 맞는지
- tunnel/deployment URL이 살아 있는지
- Slack 앱 redirect URL이 현재 `APP_BASE_URL`와 일치하는지

### “다이제스트가 오지 않음”

확인:

- 앱 프로세스가 실행 중인지
- scheduler가 실행 중인지
- 사용자가 digest 설정을 저장했는지
- 사용자가 Slack MCP OAuth를 완료했는지
- 현재 시간이 설정한 요일/시간대인지

### “다이제스트는 오는데 이모지 스레드가 빠짐”

가능한 원인:

- 실제 Slack MCP reaction search 동작이 로컬 가정과 다를 수 있음

`docs/mcp-capability-spike.md`를 확인하세요.

---

# 13. Repository / 저장소

```txt
git@github.com:sunwoong-upstage/slack-assistant.git
```

Current remote configured locally:

```bash
git remote -v
```

---

# 14. Next recommended steps / 다음 추천 작업

## English

1. Push the repo to GitHub
2. Fill out `.env`
3. Test locally with ngrok
4. Deploy to Railway
5. Run the live Slack MCP capability spike in a real workspace

## 한국어

1. GitHub에 푸시
2. `.env` 채우기
3. ngrok로 로컬 테스트
4. Railway 배포
5. 실제 Slack workspace에서 live capability spike 실행
