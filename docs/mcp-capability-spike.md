# Slack MCP Capability Spike

Run this spike before treating the Slack Assistant implementation as feature-complete.

## Goal

Prove that Slack MCP can support the v1 discovery and retrieval contract required by the PRD.

## Preconditions

- Internal Slack app exists and is installable
- Slack MCP OAuth flow succeeds for a test user
- At least one channel contains fixtures for mention, alias, reaction, and irrelevant-thread cases
- Bot token and MCP user token are available in a non-production test workspace

## Checks

### 1. Mention-based discovery

- Query for threads that directly mention the authenticated user
- Confirm the returned result can be expanded into full thread context
- Record the IDs/fields needed for downstream permalink resolution

### 2. Alias-based discovery

- Configure a team alias fixture such as `@team-edu`
- Query for threads containing the configured alias
- Confirm duplicate threads are suppressed when the same thread also mentions the user directly

### 3. Reaction-based discovery

- Add a configured emoji reaction to a known thread
- Confirm Slack MCP can find the thread using the reaction signal alone
- If native reaction querying is weak or unavailable, record the fallback strategy before shipping

### 4. Permalink resolution

- Resolve a permalink for a top-level message
- Resolve a permalink for a threaded reply
- Confirm the returned link opens to the correct thread context in Slack

## Evidence template

| Check | PASS/FAIL | Notes | Fallback needed? |
|---|---|---|---|
| Mention discovery |  |  |  |
| Alias discovery |  |  |  |
| Reaction discovery |  |  |  |
| Permalink resolution |  |  |  |

## Required handoff notes

- Exact query/filter shape that worked
- Fields required to fetch or format downstream thread summaries
- Any rate-limit, auth, or scope issues encountered
- The documented fallback if reaction discovery is weaker than required
