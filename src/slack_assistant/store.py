from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet

from .models import DigestSchedule, MCPTokenSet, UserPreferences


class StoreError(Exception):
    """Raised when persistence operations fail."""


class EncryptedJSONStore:
    def __init__(self, path: Path | str, *, encryption_key: str | None = None) -> None:
        self._path = Path(path)
        self._cipher = Fernet(encryption_key) if encryption_key else None
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._write({"users": {}})

    def save_preferences(self, preferences: UserPreferences) -> None:
        data = self._read()
        user_bucket = data.setdefault("users", {}).setdefault(preferences.user_id, {})
        user_bucket["preferences"] = {
            "user_id": preferences.user_id,
            "user_handle": preferences.user_handle,
            "aliases": list(preferences.aliases),
            "watched_reactions": list(preferences.watched_reactions),
            "delivery_channel_id": preferences.delivery_channel_id,
            "digest_schedules": [asdict(schedule) for schedule in preferences.digest_schedules],
        }
        self._write(data)

    def load_preferences(self, user_id: str) -> UserPreferences | None:
        user_bucket = self._read().get("users", {}).get(user_id, {})
        raw = user_bucket.get("preferences")
        if not raw:
            return None
        schedules = tuple(
            DigestSchedule(
                **{
                    **item,
                    "days_of_week": tuple(item.get("days_of_week", ())),
                }
            )
            for item in raw.get("digest_schedules", [])
        )
        return UserPreferences(
            user_id=raw["user_id"],
            user_handle=raw.get("user_handle"),
            aliases=tuple(raw.get("aliases", [])),
            watched_reactions=tuple(raw.get("watched_reactions", [])),
            delivery_channel_id=raw.get("delivery_channel_id"),
            digest_schedules=schedules,
        )

    def save_tokens(self, user_id: str, tokens: MCPTokenSet) -> None:
        if not self._cipher:
            raise StoreError("STORE_ENCRYPTION_KEY is required before persisting tokens")
        data = self._read()
        user_bucket = data.setdefault("users", {}).setdefault(user_id, {})
        serializable = {
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token,
            "expires_at": tokens.expires_at.isoformat() if tokens.expires_at else None,
            "scope": tokens.scope,
        }
        encrypted = self._cipher.encrypt(json.dumps(serializable).encode("utf-8")).decode("utf-8")
        user_bucket["tokens"] = encrypted
        self._write(data)

    def load_tokens(self, user_id: str) -> MCPTokenSet | None:
        raw = self._read().get("users", {}).get(user_id, {}).get("tokens")
        if not raw:
            return None
        if not self._cipher:
            raise StoreError("STORE_ENCRYPTION_KEY is required before reading tokens")
        decrypted = json.loads(self._cipher.decrypt(raw.encode("utf-8")).decode("utf-8"))
        expires_at = decrypted.get("expires_at")
        return MCPTokenSet(
            access_token=decrypted["access_token"],
            refresh_token=decrypted.get("refresh_token"),
            expires_at=datetime.fromisoformat(expires_at) if expires_at else None,
            scope=decrypted.get("scope"),
        )

    def delete_tokens(self, user_id: str) -> None:
        data = self._read()
        user_bucket = data.get("users", {}).get(user_id, {})
        if "tokens" not in user_bucket:
            return
        user_bucket.pop("tokens", None)
        self._write(data)

    def save_cursor(self, user_id: str, schedule_id: str, cursor: str) -> None:
        data = self._read()
        user_bucket = data.setdefault("users", {}).setdefault(user_id, {})
        cursors = user_bucket.setdefault("cursors", {})
        cursors[schedule_id] = cursor
        self._write(data)

    def load_cursor(self, user_id: str, schedule_id: str) -> str | None:
        return self._read().get("users", {}).get(user_id, {}).get("cursors", {}).get(schedule_id)

    def list_preferences(self) -> list[UserPreferences]:
        users = self._read().get("users", {})
        preferences: list[UserPreferences] = []
        for user_id in users:
            loaded = self.load_preferences(user_id)
            if loaded is not None:
                preferences.append(loaded)
        return preferences

    def raw_payload(self) -> dict[str, Any]:
        return self._read()

    def _read(self) -> dict[str, Any]:
        return json.loads(self._path.read_text())

    def _write(self, payload: dict[str, Any]) -> None:
        serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        temp_path = self._path.with_suffix(f"{self._path.suffix}.tmp")
        temp_path.write_text(serialized)
        os.replace(temp_path, self._path)
