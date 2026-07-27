"""Bridge version, schema fingerprinting, and MCP discovery logging."""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp.server.fastmcp.server import FastMCP
    from mcp.server.fastmcp.tools.tool_manager import ToolManager

# Bump when tool schemas, MCP surface, or security behavior changes.
SERVER_VERSION = "1.5.0"

STARTED_AT = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

DISCOVERY_LOGGER = logging.getLogger("tasks_bridge.discovery")

BRIDGE_STATE_DIR = Path(__file__).resolve().parent / ".tasks-bridge"
RESTART_RECORD_FILE = BRIDGE_STATE_DIR / "server-restart.json"
DISCOVERY_TIMELINE_FILE = BRIDGE_STATE_DIR / "discovery-timeline.jsonl"


def resolve_git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=2,
        )
        sha = result.stdout.strip()
        return sha or "unknown"
    except Exception:
        return "unknown"


def ordered_tool_names(tool_manager: ToolManager) -> list[str]:
    return sorted(tool.name for tool in tool_manager.list_tools())


def compute_schema_hash(tool_manager: ToolManager) -> str:
    """Stable hash over tool names and input schemas."""
    entries: list[dict[str, Any]] = []
    for tool in sorted(tool_manager.list_tools(), key=lambda item: item.name):
        entries.append(
            {
                "name": tool.name,
                "description": tool.description or "",
                "inputSchema": tool.parameters,
            }
        )
    canonical = json.dumps(entries, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def build_diagnostics(tool_manager: ToolManager) -> dict[str, Any]:
    return {
        "server_version": SERVER_VERSION,
        "git_sha": resolve_git_sha(),
        "started_at": STARTED_AT,
        "schema_hash": compute_schema_hash(tool_manager),
        "tool_names": ordered_tool_names(tool_manager),
    }


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


def _connection_id_from_fastmcp(fastmcp: FastMCP) -> str:
    try:
        context = fastmcp.get_context()
        request = context.request_context.request if context.request_context else None
        if request is not None and hasattr(request, "headers"):
            scope = request.scope
            return connection_id_from_http(scope)
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


def _append_discovery_timeline(payload: dict[str, Any]) -> None:
    try:
        BRIDGE_STATE_DIR.mkdir(parents=True, exist_ok=True)
        with DISCOVERY_TIMELINE_FILE.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, separators=(",", ":")) + "\n")
    except OSError:
        pass


def record_server_restart(tool_manager: ToolManager) -> None:
    """Persist restart time and schema for post-mortem discovery timelines."""
    payload = {
        "restarted_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        **build_diagnostics(tool_manager),
    }
    try:
        BRIDGE_STATE_DIR.mkdir(parents=True, exist_ok=True)
        RESTART_RECORD_FILE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


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
        if (
            not logged
            and message.get("type") == "http.request"
        ):
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
