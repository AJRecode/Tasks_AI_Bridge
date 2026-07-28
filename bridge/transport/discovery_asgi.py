"""ASGI middleware for MCP initialize discovery logging."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from bridge.logging import connection_id_from_http, log_discovery_event

if TYPE_CHECKING:
    from mcp.server.fastmcp.tools.tool_manager import ToolManager


class MCPDiscoveryLoggingASGI:
    """ASGI wrapper that logs MCP initialize requests on the HTTP transport."""

    def __init__(self, app, *, mcp_path: str, tool_manager: ToolManager):
        self.app = app
        self.mcp_path = mcp_path.rstrip("/") or "/mcp"
        self.tool_manager = tool_manager

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            await self.app(scope, receive, send)
            return

        if (
            scope.get("type") == "http"
            and scope.get("method") == "POST"
            and (scope.get("path", "").rstrip("/") or "/") == self.mcp_path
        ):
            await self.app(scope, _logging_receive(scope, receive, self.tool_manager), send)
            return

        await self.app(scope, receive, send)


def _logging_receive(scope: dict[str, Any], receive, tool_manager: ToolManager):
    chunks: list[bytes] = []
    logged = False

    async def wrapped_receive():
        nonlocal logged
        message = await receive()
        if not logged and message.get("type") == "http.request":
            chunks.append(message.get("body", b""))
            if not message.get("more_body", False):
                _log_initialize_from_body(scope, b"".join(chunks), tool_manager)
                logged = True
        return message

    return wrapped_receive


def _log_initialize_from_body(scope: dict[str, Any], body: bytes, tool_manager: ToolManager) -> None:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return

    if payload.get("method") != "initialize":
        return

    params = payload.get("params") or {}
    client_info = params.get("clientInfo") or {}
    headers = {
        key.decode("latin-1").lower(): value.decode("latin-1")
        for key, value in scope.get("headers", [])
    }
    log_discovery_event(
        method="initialize",
        tool_manager=tool_manager,
        connection_id=connection_id_from_http(scope),
        request_id=payload.get("id"),
        client_name=client_info.get("name"),
        client_version=client_info.get("version"),
        user_agent=headers.get("user-agent"),
    )
