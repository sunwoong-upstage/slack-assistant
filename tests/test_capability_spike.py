from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "mcp_capability_spike.py"
SPEC = importlib.util.spec_from_file_location("mcp_capability_spike", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


@pytest.mark.asyncio
async def test_run_checks_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLACK_STATE_SECRET", "secret")
    args = argparse.Namespace(
        user_id="U123",
        alias="team-edu",
        reaction="eyes",
        channel_id=None,
        message_ts=None,
        dry_run=True,
        output="/tmp/capability-spike.json",
    )

    results = await MODULE.run_checks(args)

    assert [result["name"] for result in results] == [
        "mention_search",
        "alias_search",
        "reaction_search",
    ]
    assert all(result["status"] == "dry_run" for result in results)
