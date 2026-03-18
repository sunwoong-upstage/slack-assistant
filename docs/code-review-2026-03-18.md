# Code Review Notes — 2026-03-18

## Automated verification snapshot

Run from `slack-assistant/`:

```bash
uv run --group dev ruff check src
uv run python -m compileall src
uv run --group dev pytest -q
```

Current result:

- Ruff: PASS
- Syntax compilation: PASS
- Pytest: PASS (`26 passed`)

These checks show the scaffold is currently stable at the lint/syntax/unit-test level.

## Prioritized review findings

### 1. High — bootstrap still bypasses the per-user MCP auth/store path

- `src/slack_assistant/main.py:16-23`
- `src/slack_assistant/store.py:62-89`

The runtime still requires a single `SLACK_MCP_ACCESS_TOKEN` environment variable at process start. That bypasses the per-user OAuth/token-storage path implied by `mcp_auth.py` and `store.py`, and it does not yet match the PRD requirement that Slack MCP access be user-authorized and stored safely per user.

**Recommendation:** wire app startup to the persisted token path (or an auth bootstrap flow) before calling the feature complete.

### 2. High — delivery surface config is defined but not honored

- `src/slack_assistant/config.py:25`
- `src/slack_assistant/slack_app.py:25-34`

`SLACK_DEFAULT_DELIVERY_SURFACE` exists in config, but the shortcut handler always delivers by `client.chat_postMessage(channel=user_id, text=summary_text)`. That means App Home vs DM behavior is not actually configurable yet.

**Recommendation:** introduce a delivery abstraction that explicitly routes to DM or App Home and make the shortcut path use it.

### 3. High — shortcut handler uses `asyncio.run(...)` inside the Bolt request path

- `src/slack_assistant/slack_app.py:25-34`

The current sync Bolt shortcut handler acks first and then calls `asyncio.run(service.summarize_thread(...))`. This is a risky execution model for a Slack handler because it creates a fresh event loop per request and has no structured fallback if summarization fails after the ack.

**Recommendation:** move to Bolt's async app surface or queue/background-task execution, and add post-ack error delivery so users do not get silent failures.

### 4. Medium — OAuth state tokens are signed but not time-bounded

- `src/slack_assistant/mcp_auth.py:12-30`

The state token includes a timestamp, but validation checks only user match + HMAC. There is no max-age or replay window enforcement.

**Recommendation:** add expiry validation and tests for stale/replayed state tokens.

### 5. Medium — MCP transport advertises SSE but parses JSON only

- `src/slack_assistant/mcp_client.py:33-51`

The transport sends `Accept: application/json, text/event-stream` but then immediately calls `response.json()`. If Slack MCP ever returns an SSE-framed response for tool calls, this transport will fail.

**Recommendation:** either constrain the transport to JSON-only responses or implement explicit SSE handling after confirming the live Slack MCP behavior.

### 6. Medium — reaction-discovery syntax is still an assumption pending the capability spike

- `src/slack_assistant/services.py:52-56`
- `scripts/mcp_capability_spike.py:33-37`
- `tests/test_services.py:95-100`

The code already normalizes reaction discovery into a search query like `":eyes:"`, and tests verify that local contract. However, the PRD explicitly requires the live Slack MCP capability spike first because this exact query shape is still a product risk.

**Recommendation:** do not treat reaction-based discovery as production-ready until the live spike records a passing result in `docs/mcp-capability-spike.md`.

### 7. Medium — JSON store writes are not atomic

- `src/slack_assistant/store.py:105-109`

The store writes directly to the target file with no temp-file swap or locking. That is acceptable for a scaffold, but it is fragile once scheduler writes and OAuth/token writes can overlap.

**Recommendation:** switch to atomic writes (temp file + replace) before relying on the store for concurrent runtime flows.

## Review conclusion

The current scaffold is in good shape for a feature skeleton: it is lint-clean, syntax-clean, and unit-tested. The remaining issues are mainly architecture/production-readiness gaps around auth flow completion, delivery-surface behavior, async execution model, live MCP capability proof, and persistence hardening.

## Suggested next order

1. Finish live MCP capability spike and record real results
2. Replace bootstrap-wide `SLACK_MCP_ACCESS_TOKEN` usage with per-user auth/store wiring
3. Fix delivery-surface abstraction and post-ack error handling
4. Harden OAuth state expiry and store writes
