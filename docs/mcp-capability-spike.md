# Slack MCP Capability Spike

Run this spike before treating the scheduled digest feature as fully validated.

## Goal

Prove that Slack MCP can support the digest discovery contract required by the current product scope:

- direct mention discovery
- watched emoji discovery for reactions left by the same user
- full thread expansion
- permalink resolution

## Preconditions

- Internal Slack app exists and is installable
- Slack MCP OAuth flow succeeds for a test user
- At least one test workspace channel contains:
  - a direct-mention thread
  - a watched-emoji thread
  - an irrelevant thread
- Bot token and MCP user token are available in a non-production workspace

## Checks

### 1. Direct mention discovery

- Query for threads that directly mention the authenticated user
- Confirm the result can be expanded into full thread context
- Confirm the resulting thread appears in the digest candidate set

### 2. Watched emoji discovery

- Add a configured watched emoji such as `:loading:` to a known thread as the authenticated user
- Confirm Slack MCP can find that thread from the emoji query shape alone
- Confirm the thread can be expanded and summarized
- If native reaction querying is weak or incomplete, record the exact limitation before shipping

### 3. Alias exclusion sanity check

- Confirm alias/team-name-only threads are **not** included by the digest flow
- Record the query/relevance behavior used to suppress alias-only matches

### 4. Permalink resolution

- Resolve a permalink for a top-level message
- Resolve a permalink for a threaded reply
- Confirm the returned links open the correct thread context in Slack

## Evidence template

| Check | PASS/FAIL | Notes | Blocking? |
|---|---|---|---|
| Direct mention discovery | PASS (dry-run) | Dry-run query shape exists for `"<@U123>"`. Live proof still pending. | Yes |
| Watched emoji discovery | PASS (dry-run), LIVE PENDING | Dry-run query shape exists for `":eyes:"` / `":loading:"`, but live Slack MCP proof is still required. | Yes |
| Alias exclusion | LOCAL PASS | Digest plan/code explicitly suppress alias queries and alias relevance for this feature. Live end-to-end proof still desirable. | No |
| Permalink resolution | PASS (dry-run path present) | Dry-run path exists when channel/message IDs are supplied. Live confirmation still pending. | Yes |

## Current recorded run

- Date: 2026-03-18
- Command: `SLACK_MCP_ACCESS_TOKEN=xoxp-dev-token uv run python scripts/mcp_capability_spike.py --dry-run --output build/capability-spike.json`
- Result: **PASS (dry-run contract)** — the script emitted the expected mention, alias, reaction, and optional permalink tool-call shapes.
- External blocker for live proof: no real Slack MCP workspace credentials/scopes were available in this environment, so live Slack validation remains pending operator-supplied credentials.

## Required handoff notes

- Exact query/filter shape that worked for direct mentions
- Exact query/filter shape that worked for watched emoji discovery
- Fields required to read downstream thread summaries
- Any rate-limit, auth, or scope issues encountered
- Whether reaction discovery is fully reliable enough for the digest release gate
