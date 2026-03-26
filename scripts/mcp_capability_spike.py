from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


async def run_checks(args: argparse.Namespace) -> list[dict[str, Any]]:
    from slack_assistant.config import load_config
    from slack_assistant.mcp_client import SlackMCPHTTPTransport

    config = load_config()
    checks = [
        {
            "name": "mention_search",
            "tool": config.slack_mcp_search_tool,
            "arguments": {"query": f'"<@{args.user_id}>"', "limit": 5},
        },
        {
            "name": "alias_search",
            "tool": config.slack_mcp_search_tool,
            "arguments": {"query": f'"{args.alias}"', "limit": 5},
        },
        {
            "name": "reaction_search",
            "tool": config.slack_mcp_search_tool,
            "arguments": {"query": f'":{args.reaction.strip(":")}:"', "limit": 5},
        },
    ]
    if args.channel_id and args.message_ts:
        checks.append(
            {
                "name": "permalink_lookup",
                "tool": config.slack_mcp_permalink_tool,
                "arguments": {"channel_id": args.channel_id, "message_ts": args.message_ts},
            }
        )

    if args.dry_run:
        return [{**check, "status": "dry_run"} for check in checks]

    access_token = os.getenv("SLACK_MCP_ACCESS_TOKEN")
    if not access_token:
        raise SystemExit("SLACK_MCP_ACCESS_TOKEN is required unless --dry-run is used")

    transport = SlackMCPHTTPTransport(base_url=config.slack_mcp_base_url, access_token=access_token)
    results: list[dict[str, Any]] = []
    for check in checks:
        try:
            result = await transport.call_tool(check["tool"], check["arguments"])
            results.append({**check, "status": "ok", "result": result})
        except Exception as error:  # noqa: BLE001
            results.append({**check, "status": "error", "error": str(error)})
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Slack MCP capability spike")
    parser.add_argument("--user-id", default="U123")
    parser.add_argument("--alias", default="team-edu")
    parser.add_argument("--reaction", default="eyes")
    parser.add_argument("--channel-id")
    parser.add_argument("--message-ts")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", default="capability-spike.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    results = asyncio.run(run_checks(args))
    output_path = Path(args.output)
    output_path.write_text(json.dumps(results, indent=2) + "\n")
    print(output_path.resolve())
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
