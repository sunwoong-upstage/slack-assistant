# Slack Assistant

Slack Assistant is a Python 3.12 Slack app that uses Slack MCP for Slack retrieval and Upstage Solar for concise thread summaries.

## What v1 does

- Summarizes a specific Slack thread from a message shortcut
- Delivers summaries to DM/App Home with a permalink back to the source thread
- Builds scheduled digests for threads relevant to the user
- Uses Slack MCP for read/search access instead of broad channel scraping
- Stores only config, auth material, and digest cursors; it does **not** retain raw Slack history long-term

## Product constraints

- Slack MCP is only available to **internal** or **directory-published** Slack apps
- The app needs two auth surfaces:
  - Slack bot/app install for in-Slack UX
  - Slack MCP user authorization for search/read access
- Slack shortcuts triggered from threaded messages cannot reliably post back into that same thread, so v1 returns results by DM/App Home

## Architecture at a glance

1. User installs the internal Slack app from `app_manifest.yaml`
2. User opens App Home and completes Slack MCP authorization
3. A message shortcut or scheduled job requests relevant thread data via Slack MCP
4. The service resolves a permalink with Slack Web API
5. Upstage generates a short summary
6. The app sends a compact result back to DM/App Home

## Planned project layout

```text
slack-assistant/
├── README.md
├── .env.example
├── app_manifest.yaml
├── docs/
│   ├── mcp-capability-spike.md
│   ├── review-checklist.md
│   └── review-notes.md
├── src/slack_assistant/
│   ├── config.py
│   ├── main.py
│   ├── slack_app.py
│   ├── mcp_auth.py
│   ├── mcp_client.py
│   ├── relevance.py
│   ├── upstage_client.py
│   ├── formatter.py
│   ├── digest_scheduler.py
│   └── store.py
└── tests/
```

## Setup flow

### 1. Prerequisites

- Python 3.12
- A Slack workspace where you can install an **internal** app
- An Upstage API key
- A secret-management approach for production token storage

### 2. Create the Slack app

1. Create the app from `app_manifest.yaml`
2. Enable App Home, interactivity, and the message shortcut
3. Install the app to the workspace
4. Copy the generated bot token, signing secret, and (for local Socket Mode) app token into `.env`

### 3. Configure local environment

```bash
cd slack-assistant
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Populate `.env` with Slack bot credentials, Slack MCP OAuth credentials, Upstage settings, and the encryption key for persisted secrets.

### 4. Run the MCP capability spike first

Before building the full feature flow, explicitly verify:

- mention-based retrieval works
- alias-based retrieval works
- reaction-based discovery works for the configured emoji set
- permalink resolution works for top-level and threaded messages

Record the results in `docs/mcp-capability-spike.md` so the fallback path is clear if reaction queries are weaker than expected.

### 5. Start the app

Local development should default to **Socket Mode**. Production should switch to an HTTP request URL.

Expected runtime behaviors:

- acknowledge shortcut requests within 3 seconds
- send results to DM/App Home, not back into the originating thread
- keep summaries short: 1 headline + up to 3 bullets + permalink

## User flow

### On-demand summary

1. User opens the message shortcut on a Slack message
2. App reads the surrounding thread via Slack MCP
3. App summarizes the thread with Upstage
4. App delivers a concise summary with permalink in DM/App Home

### Scheduled digest

1. User configures aliases, watched reactions, and a digest time
2. Scheduler finds new relevant threads since the last cursor
3. App summarizes each thread and delivers a digest in DM/App Home
4. Cursor advances only after successful delivery

## Configuration contract

See `.env.example` for the initial environment contract. Keep these rules:

- never log plaintext bot or MCP user tokens
- keep Upstage model selection environment-driven
- separate local/dev transport config from production transport config
- persist only encrypted auth material, user preferences, and digest cursors

## Verification checklist

Use `docs/review-checklist.md` as the handoff gate. At minimum, verify:

- install flow from manifest + README
- MCP auth path
- message shortcut -> DM/App Home summary path
- digest scheduling path
- summary format and permalink contract
- persistence and logging do not retain raw Slack history or plaintext secrets

## Known open questions

- Exact Slack MCP reaction query shape still needs capability-spike proof
- Final scope list in `app_manifest.yaml` must match the actual MCP + delivery implementation
- Production secret storage backend is still an implementation decision; docs assume encryption or managed secrets, not plaintext files
