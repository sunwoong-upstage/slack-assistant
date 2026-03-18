# Review Checklist

Use this checklist before handing the Slack Assistant implementation back to the lead.

## Product acceptance

- [ ] App is installable from `app_manifest.yaml` without source edits
- [ ] README is sufficient for a non-developer to complete install + local run
- [ ] Slack MCP authorization is separate from Slack bot install and clearly documented
- [ ] On-demand summaries deliver to DM/App Home with a working permalink
- [ ] Scheduled digests include only new relevant threads since the last cursor
- [ ] Summary output stays within the compact contract: 1 headline + max 3 bullets + permalink
- [ ] Only config, encrypted auth material, and cursors are persisted

## Capability spike evidence

- [ ] Mention retrieval verified
- [ ] Alias retrieval verified
- [ ] Reaction-based discovery verified or fallback documented
- [ ] Permalink resolution verified for top-level and threaded messages

## Code quality

- [ ] Config validation fails fast on missing required secrets
- [ ] Retry/fallback behavior exists around Upstage failures
- [ ] Duplicate-thread suppression exists in relevance logic
- [ ] Digest cursor advances only after successful delivery
- [ ] Logs include correlation IDs and redact credentials/tokens
- [ ] No debug prints or temporary fixtures remain

## Verification evidence

- [ ] Lint passes
- [ ] Type check passes
- [ ] Targeted unit tests pass
- [ ] Integration tests for shortcut and digest flows pass
- [ ] Manual install/runbook replay passes
- [ ] Persistence audit confirms no raw Slack history retention

## Review notes to capture with results

- Commands run
- PASS/FAIL per verification step
- Known gaps or deferred follow-ups
- Files touched for docs, manifest, runtime, and tests
