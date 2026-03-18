# Review Notes

## Initial findings

- `slack-assistant/` started empty, so documentation had to be created before any implementation-specific review could happen.
- The PRD requires a docs-first install path: manifest-driven setup, MCP auth instructions, and a compact summary contract.
- The highest-risk unresolved requirement is Slack MCP reaction-based discovery; the capability spike must prove this before the feature is considered stable.

## Current documentation work added

- `README.md` now defines the install flow, auth split, transport guidance, and verification expectations.
- `.env.example` now defines the initial environment contract for Slack bot auth, Slack MCP auth, Upstage, persistence, and redaction.
- `docs/review-checklist.md` now maps PRD/test-spec expectations to a concrete review gate.
- `docs/mcp-capability-spike.md` now defines the required proof points for mention, alias, reaction, and permalink support.

## Review focus for the next pass

1. Confirm actual env/config names match `.env.example`
2. Confirm `app_manifest.yaml` scopes match the implementation and auth flow
3. Confirm message shortcut handling acknowledges within Slack's deadline and returns results by DM/App Home
4. Confirm summary formatting enforces the visible-character budget before the permalink
5. Confirm persisted state excludes raw message history and logs redact sensitive values

## Blockers / coordination notes

- No Git repository is currently initialized for `slack-assistant/`, so commit-based handoff will need either repo initialization or leader guidance.
- Because multiple workers are assigned the same broad PRD, docs ownership should stay on `README.md`, `.env.example`, and `docs/*` unless the lead reassigns scope.
