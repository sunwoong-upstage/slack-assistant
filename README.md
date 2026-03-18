# Slack Assistant

Python 3.12 Slack MCP + Upstage summary bot scaffold.

## Quick start

1. Copy `.env.example` to `.env`.
2. Set Slack bot credentials, `SLACK_STATE_SECRET`, `SLACK_MCP_ACCESS_TOKEN`, and `UPSTAGE_API_KEY`.
3. Install dependencies with `uv sync --group dev`.
4. Run the capability spike in dry-run mode:
   - `uv run --directory slack-assistant python scripts/mcp_capability_spike.py --dry-run`
5. Start the app:
   - `uv run --directory slack-assistant python -m slack_assistant.main`
