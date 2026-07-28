"""Static bearer token authentication for scripts and compatible MCP clients."""

from __future__ import annotations

import logging
import secrets
from typing import TYPE_CHECKING, Any

from bridge import config
from bridge.auth.base import AuthProvider

if TYPE_CHECKING:
    from mcp.server.fastmcp.server import FastMCP

LOGGER = logging.getLogger("tasks_bridge.auth.static")

UNAUTHORIZED_BODY = {"error": "Unauthorized"}
WWW_AUTHENTICATE = 'Bearer realm="Tasks Bridge MCP"'


def _extract_bearer_token(scope: dict[str, Any]) -> str | None:
    for key, value in scope.get("headers", []):
        if key.decode("latin-1").lower() != "authorization":
            continue
        header = value.decode("latin-1").strip()
        parts = header.split(None, 1)
        if len(parts) != 2:
            return None
        scheme, token = parts[0], parts[1].strip()
        if scheme.lower() != "bearer":
            return None
        return token or None
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
            await _send_json(
                send,
                status=401,
                body=UNAUTHORIZED_BODY,
                extra_headers=[(b"www-authenticate", WWW_AUTHENTICATE.encode("ascii"))],
            )
            return

        await self.app(scope, receive, send)


async def _send_json(
    send,
    *,
    status: int,
    body: dict[str, str],
    extra_headers: list[tuple[bytes, bytes]] | None = None,
) -> None:
    import json

    payload = json.dumps(body).encode("utf-8")
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(payload)).encode("ascii")),
    ]
    if extra_headers:
        headers.extend(extra_headers)
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": headers,
        }
    )
    await send({"type": "http.response.body", "body": payload})


class StaticBearerAuthProvider(AuthProvider):
    @property
    def mode(self) -> str:
        return "static"

    def validate_deployment(self) -> None:
        if not config.MCP_API_TOKEN:
            raise RuntimeError(
                "MCP_AUTH_MODE=static requires MCP_API_TOKEN (local or production). "
                "Generate a long random secret for .env or Railway variables."
            )

    def install_http_auth(self, fastmcp: FastMCP, *, mcp_path: str) -> None:
        token = config.MCP_API_TOKEN
        if not token:
            raise RuntimeError(
                "Static bearer authentication cannot be installed without MCP_API_TOKEN."
            )

        original_streamable_http_app = fastmcp.streamable_http_app

        def streamable_http_app_with_bearer_auth():
            app = original_streamable_http_app()
            return BearerAuthASGI(app, mcp_path=mcp_path, token=token)

        fastmcp.streamable_http_app = streamable_http_app_with_bearer_auth
