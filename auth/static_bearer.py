"""Static bearer token authentication for scripts and compatible MCP clients."""

from __future__ import annotations

import logging
import secrets
from typing import TYPE_CHECKING, Any

import config
from auth.base import AuthProvider

if TYPE_CHECKING:
    from mcp.server.fastmcp.server import FastMCP

LOGGER = logging.getLogger("tasks_bridge.auth.static")

UNAUTHORIZED_BODY = {"error": "Unauthorized"}


def _extract_bearer_token(scope: dict[str, Any]) -> str | None:
    for key, value in scope.get("headers", []):
        if key.decode("latin-1").lower() != "authorization":
            continue
        header = value.decode("latin-1").strip()
        prefix = "Bearer "
        if header.startswith(prefix):
            return header[len(prefix) :].strip()
        return None
    return None


def _client_ip(scope: dict[str, Any]) -> str:
    client = scope.get("client")
    if client:
        return client[0]
    return "unknown"


class BearerAuthASGI:
    """Reject /mcp requests without a valid MCP_API_TOKEN bearer header."""

    def __init__(self, app, *, mcp_path: str, token: str) -> None:
        self.app = app
        self.mcp_path = mcp_path.rstrip("/") or "/mcp"
        self.token = token

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "").rstrip("/") or "/"
        if path != self.mcp_path:
            await self.app(scope, receive, send)
            return

        provided = _extract_bearer_token(scope)
        if not provided or not secrets.compare_digest(provided, self.token):
            LOGGER.warning(
                "Rejected unauthenticated MCP request from %s", _client_ip(scope)
            )
            await _send_json(send, status=401, body=UNAUTHORIZED_BODY)
            return

        await self.app(scope, receive, send)


async def _send_json(send, *, status: int, body: dict[str, str]) -> None:
    import json

    payload = json.dumps(body).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": payload})


class StaticBearerAuthProvider(AuthProvider):
    @property
    def mode(self) -> str:
        return "static"

    def validate_deployment(self) -> None:
        if config.IS_PRODUCTION and not config.MCP_API_TOKEN:
            raise RuntimeError(
                "MCP_AUTH_MODE=static requires MCP_API_TOKEN in production. "
                "Generate a long random secret and set it in Railway variables."
            )

    def install_http_auth(self, fastmcp: FastMCP, *, mcp_path: str) -> None:
        token = config.MCP_API_TOKEN
        if not token:
            return

        original_streamable_http_app = fastmcp.streamable_http_app

        def streamable_http_app_with_bearer_auth():
            app = original_streamable_http_app()
            return BearerAuthASGI(app, mcp_path=mcp_path, token=token)

        fastmcp.streamable_http_app = streamable_http_app_with_bearer_auth
