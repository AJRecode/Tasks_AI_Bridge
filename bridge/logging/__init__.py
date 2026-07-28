"""MCP discovery logging and HTTP initialize tracing."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from bridge.diagnostics import (
    SERVER_VERSION,
    build_diagnostics,
    compute_schema_hash,
    ordered_tool_names,
    record_server_restart,
    resolve_git_sha,
)
from bridge.diagnostics import BRIDGE_STATE_DIR

if TYPE_CHECKING:
    from mcp.server.fastmcp.server import FastMCP
    from mcp.server.fastmcp.tools.tool_manager import ToolManager

DISCOVERY_LOGGER = logging.getLogger("tasks_bridge.discovery")
DISCOVERY_TIMELINE_FILE = BRIDGE_STATE_DIR / "discovery-timeline.jsonl"


def connection_id_from_http(scope: dict[str, Any]) -> str:
    headers = {
        key.decode("latin-1").lower(): value.decode("latin-1")
        for key, value in scope.get("headers", [])
    }
    parts = [
        headers.get("mcp-session-id", ""),
        scope.get("client", ("", 0))[0],
        headers.get("user-agent", ""),
    ]
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:12]
    return f"conn-{digest}"


def log_discovery_event(
    *,
    method: str,
    tool_manager: ToolManager,
    connection_id: str,
    request_id: Any = None,
    client_name: str | None = None,
    client_version: str | None = None,
    user_agent: str | None = None,
) -> None:
    payload = {
        "event": "mcp_discovery",
        "timestamp": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "method": method,
        "server_version": SERVER_VERSION,
        "git_sha": resolve_git_sha(),
        "schema_hash": compute_schema_hash(tool_manager),
        "tool_names": ordered_tool_names(tool_manager),
        "connection_id": connection_id,
        "request_id": request_id,
    }
    if client_name:
        payload["client_name"] = client_name
    if client_version:
        payload["client_version"] = client_version
    if user_agent:
        payload["user_agent"] = user_agent
    DISCOVERY_LOGGER.info(json.dumps(payload, separators=(",", ":")))
    _append_discovery_timeline(payload)


def log_startup_banner(tool_manager: ToolManager) -> None:
    diagnostics = build_diagnostics(tool_manager)
    record_server_restart(tool_manager)
    DISCOVERY_LOGGER.info(
        "Tasks Bridge %s started (git %s, schema %s, tools=%s)",
        diagnostics["server_version"],
        diagnostics["git_sha"],
        diagnostics["schema_hash"],
        ", ".join(diagnostics["tool_names"]),
    )


def install_discovery_logging(fastmcp: FastMCP, *, mcp_path: str = "/mcp") -> None:
    """Log initialize (HTTP) and tools/list (handler) for discovery tracing."""
    from bridge.transport.discovery_asgi import MCPDiscoveryLoggingASGI

    fastmcp._mcp_server.version = SERVER_VERSION

    original_list_tools = fastmcp.list_tools

    async def logged_list_tools():
        tools = await original_list_tools()
        client_name, client_version, user_agent = _client_info_from_fastmcp(fastmcp)
        log_discovery_event(
            method="tools/list",
            tool_manager=fastmcp._tool_manager,
            connection_id=_connection_id_from_fastmcp(fastmcp),
            request_id=_request_id_from_fastmcp(fastmcp),
            client_name=client_name,
            client_version=client_version,
            user_agent=user_agent,
        )
        return tools

    fastmcp.list_tools = logged_list_tools

    original_streamable_http_app = fastmcp.streamable_http_app

    def streamable_http_app_with_logging():
        app = original_streamable_http_app()
        return MCPDiscoveryLoggingASGI(app, mcp_path=mcp_path, tool_manager=fastmcp._tool_manager)

    fastmcp.streamable_http_app = streamable_http_app_with_logging


def _append_discovery_timeline(payload: dict[str, Any]) -> None:
    try:
        BRIDGE_STATE_DIR.mkdir(parents=True, exist_ok=True)
        with DISCOVERY_TIMELINE_FILE.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, separators=(",", ":")) + "\n")
    except OSError:
        pass


def _connection_id_from_fastmcp(fastmcp: FastMCP) -> str:
    try:
        context = fastmcp.get_context()
        request = context.request_context.request if context.request_context else None
        if request is not None and hasattr(request, "scope"):
            return connection_id_from_http(request.scope)
    except Exception:
        pass
    return "conn-unknown"


def _request_id_from_fastmcp(fastmcp: FastMCP) -> Any:
    try:
        context = fastmcp.get_context()
        if context.request_context is not None:
            return context.request_context.request_id
    except Exception:
        pass
    return None


def _client_info_from_fastmcp(fastmcp: FastMCP) -> tuple[str | None, str | None, str | None]:
    client_name = None
    client_version = None
    user_agent = None
    try:
        context = fastmcp.get_context()
        if context.request_context is not None:
            session = context.request_context.session
            params = getattr(session, "client_params", None)
            if params is not None and params.clientInfo is not None:
                client_name = params.clientInfo.name
                client_version = params.clientInfo.version
            request = context.request_context.request
            if request is not None and hasattr(request, "headers"):
                user_agent = request.headers.get("user-agent")
    except Exception:
        pass
    return client_name, client_version, user_agent
