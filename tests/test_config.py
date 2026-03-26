from __future__ import annotations

import pytest

from slack_assistant.config import load_config


@pytest.fixture(autouse=True)
def base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLACK_STATE_SECRET", "secret")
    monkeypatch.delenv("SLACK_APP_TOKEN", raising=False)


def test_load_config_requires_state_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SLACK_STATE_SECRET", raising=False)

    with pytest.raises(ValueError, match="SLACK_STATE_SECRET"):
        load_config()


def test_load_config_selects_socket_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-123")

    config = load_config()

    assert config.transport_mode == "socket_mode"


def test_load_config_defaults_store_path() -> None:
    config = load_config()

    assert config.store_path.as_posix() == ".data/store.json"
    assert config.oauth_redirect_url is None


def test_load_config_builds_oauth_redirect_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_BASE_URL", "https://app.example.com/")

    config = load_config()

    assert config.oauth_redirect_url == "https://app.example.com/slack/oauth_redirect"
