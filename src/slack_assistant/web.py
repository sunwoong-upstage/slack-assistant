from __future__ import annotations

from collections.abc import Callable

from flask import Flask, Response, request
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler

from .config import AppConfig
from .mcp_auth import MCPAuthError, exchange_code_for_tokens, extract_user_id, validate_state_token
from .models import MCPTokenSet
from .store import EncryptedJSONStore

TokenExchange = Callable[[AppConfig, str], tuple[str | None, MCPTokenSet]]


def create_http_app(
    config: AppConfig,
    bolt_app: App,
    store: EncryptedJSONStore,
    *,
    token_exchange: TokenExchange = exchange_code_for_tokens,
) -> Flask:
    app = Flask(__name__)
    handler = SlackRequestHandler(bolt_app)

    @app.post("/slack/events")
    def slack_events() -> Response:
        return handler.handle(request)

    @app.get(config.oauth_redirect_path)
    def oauth_redirect() -> tuple[str, int]:
        code = request.args.get("code", "").strip()
        state = request.args.get("state", "").strip()
        if not code or not state:
            return ("Missing Slack OAuth callback parameters", 400)

        try:
            user_id = extract_user_id(state)
            validate_state_token(state, user_id, config.slack_state_secret)
            authed_user_id, token = token_exchange(config, code)
            if authed_user_id and authed_user_id != user_id:
                raise MCPAuthError("OAuth callback user mismatch")
            store.save_tokens(user_id, token)
        except MCPAuthError as error:
            return (str(error), 400)

        return ("Slack access connected. Return to Slack and retry the shortcut.", 200)

    return app
