from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from slack_assistant.models import DigestSchedule, MCPTokenSet, UserPreferences
from slack_assistant.store import EncryptedJSONStore, StoreError


@pytest.fixture
def encryption_key() -> str:
    return Fernet.generate_key().decode("utf-8")


def test_store_round_trips_preferences_and_cursor(tmp_path: Path, encryption_key: str) -> None:
    store = EncryptedJSONStore(tmp_path / "store.json", encryption_key=encryption_key)
    preferences = UserPreferences(
        user_id="U123",
        aliases=("team-edu",),
        watched_reactions=("eyes",),
        digest_schedules=(
            DigestSchedule(schedule_id="daily", hour=18, minute=0, timezone="Asia/Seoul"),
        ),
    )

    store.save_preferences(preferences)
    store.save_cursor("U123", "daily", "1710000000.000100")

    assert store.load_preferences("U123") == preferences
    assert store.load_cursor("U123", "daily") == "1710000000.000100"


def test_store_encrypts_tokens(tmp_path: Path, encryption_key: str) -> None:
    path = tmp_path / "store.json"
    store = EncryptedJSONStore(path, encryption_key=encryption_key)
    tokens = MCPTokenSet(
        access_token="xoxp-secret-token",
        refresh_token="refresh-token",
        expires_at=datetime(2026, 3, 18, tzinfo=UTC),
        scope="search:read",
    )

    store.save_tokens("U123", tokens)
    raw_text = path.read_text()

    assert "xoxp-secret-token" not in raw_text
    assert store.load_tokens("U123") == tokens
    assert "thread body" not in raw_text


def test_store_requires_encryption_key_for_tokens(tmp_path: Path) -> None:
    store = EncryptedJSONStore(tmp_path / "store.json")

    with pytest.raises(StoreError, match="STORE_ENCRYPTION_KEY"):
        store.save_tokens("U123", MCPTokenSet(access_token="secret"))
