"""MCP server exposing Google Tasks tools via task_services.

Local HTTP (default):
    python mcp_server.py

Stdio (Cursor subprocess mode):
    python mcp_server.py --stdio

Production (Railway):
    HOST=0.0.0.0 PORT=$PORT TASKS_BRIDGE_DEPLOYMENT=production python mcp_server.py

See docs/local-dev.md and docs/railway.md.
"""

from __future__ import annotations

import argparse
import functools
import logging
import os
import socket
import sys

from starlette.requests import Request
from starlette.responses import JSONResponse

from bridge import config
from bridge.auth.base import AuthProvider
from bridge.auth.factory import create_auth_provider, validate_deployment
from bridge.diagnostics import build_diagnostics
from bridge.logging import install_discovery_logging, log_startup_banner
from bridge.transport import (
    build_transport_security,
    install_http_middleware_stack,
    production_safe_tool_error,
)
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from services.tasks import (
    complete_task as mark_task_complete,
    create_task as add_task,
    create_task_list as add_task_list,
    get_open_tasks as fetch_open_tasks,
    get_task_lists as fetch_task_lists,
    get_tasks as fetch_tasks,
    move_task as relocate_task,
    search_tasks as find_tasks,
    update_task as modify_task,
)

READ_ONLY = ToolAnnotations(readOnlyHint=True)
WRITE_BOUNDED = ToolAnnotations(
    readOnlyHint=False,
    openWorldHint=False,
    destructiveHint=False,
)


def _safe_google_tool(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            safe = production_safe_tool_error(exc)
            if safe is not exc:
                raise safe
            raise

    return wrapper


def _register_tools(server: FastMCP) -> None:
    @server.custom_route("/health", methods=["GET"])
    async def health_check(_request: Request) -> JSONResponse:
        """Lightweight health endpoint for Railway and load balancers."""
        payload = {"status": "ok", "deployment": config.DEPLOYMENT}
        if not config.IS_PRODUCTION:
            payload["server_version"] = build_diagnostics(server._tool_manager)[
                "server_version"
            ]
        return JSONResponse(payload)

    @server.tool(annotations=READ_ONLY)
    def get_bridge_diagnostics() -> dict:
        """Return server version, git sha, schema hash, and registered tool names."""
        payload = build_diagnostics(server._tool_manager)
        payload["deployment"] = config.DEPLOYMENT
        payload["auth_mode"] = config.auth_mode()
        public_url = config.public_mcp_url()
        if public_url:
            payload["public_mcp_url"] = public_url
        return payload

    @server.tool(annotations=READ_ONLY)
    @_safe_google_tool
    def get_task_lists() -> list[dict]:
        """Return all task lists with name, id, and updated timestamp."""
        return fetch_task_lists()

    @server.tool(annotations=READ_ONLY)
    @_safe_google_tool
    def get_tasks(list_name: str) -> list[dict]:
        """Return all tasks from one list, identified by name."""
        return fetch_tasks(list_name)

    @server.tool(annotations=READ_ONLY)
    @_safe_google_tool
    def search_tasks(text: str) -> list[dict]:
        """Search task titles and notes across all lists."""
        return find_tasks(text)

    @server.tool(annotations=READ_ONLY)
    @_safe_google_tool
    def get_open_tasks(list_name: str) -> list[dict]:
        """Return open (incomplete) tasks from one list."""
        return fetch_open_tasks(list_name)

    @server.tool(annotations=WRITE_BOUNDED)
    @_safe_google_tool
    def create_task_list(list_name: str) -> dict:
        """Create a new task list. Rejects blank names and case-insensitive duplicates."""
        return add_task_list(list_name)

    @server.tool(annotations=WRITE_BOUNDED)
    @_safe_google_tool
    def create_task(
        list_name: str,
        title: str,
        notes: str = "",
        due: str | None = None,
    ) -> dict:
        """Create a new task in one list, identified by name."""
        return add_task(list_name, title, notes=notes, due=due)

    @server.tool(annotations=WRITE_BOUNDED)
    @_safe_google_tool
    def complete_task(list_name: str, task_id: str) -> dict:
        """Mark one task completed. Use task id from get_open_tasks or search_tasks."""
        return mark_task_complete(list_name, task_id)

    @server.tool(annotations=WRITE_BOUNDED)
    @_safe_google_tool
    def update_task(
        list_name: str,
        task_id: str,
        title: str | None = None,
        notes: str | None = None,
        due: str | None = None,
    ) -> dict:
        """Update a task's title, notes, or due date. Pass notes="" to clear notes; due="" clears due."""
        return modify_task(list_name, task_id, title=title, notes=notes, due=due)

    @server.tool(annotations=WRITE_BOUNDED)
    @_safe_google_tool
    def move_task(from_list_name: str, task_id: str, to_list_name: str) -> dict:
        """Move a task from one list to another. Returns the task in its new list."""
        return relocate_task(from_list_name, task_id, to_list_name)


def create_server(auth_provider: AuthProvider) -> FastMCP:
    """Build FastMCP with the selected inbound auth configuration."""
    server = FastMCP(
        "Tasks Bridge",
        instructions=(
            "Access to the user's personal Google Tasks. Use get_task_lists to discover "
            "list names. Use get_tasks or get_open_tasks for one list. Use search_tasks "
            "to find tasks by text. Use get_bridge_diagnostics to verify server version, "
            "schema hash, and registered tool names (useful when ChatGPT tool discovery "
            "lags). Use create_task_list to add a list; use create_task to add "
            "a task; use complete_task with a task id from get_open_tasks or search_tasks. "
            "Use update_task to change title, notes (pass empty string to clear), or due. "
            "Use move_task to move a task between lists (from_list_name, task_id, to_list_name). "
            "list_name accepts exact or partial matches."
        ),
        host=config.HOST,
        port=config.PORT,
        streamable_http_path=config.MCP_PATH,
        stateless_http=True,
        transport_security=build_transport_security(),
        **auth_provider.fastmcp_kwargs(),
    )
    _register_tools(server)
    return server


def build_app() -> tuple[FastMCP, AuthProvider]:
    """Create FastMCP and the resolved inbound auth provider from current config."""
    auth_provider = create_auth_provider()
    server = create_server(auth_provider)
    return server, auth_provider


def prepare_http_stack(server: FastMCP, auth_provider: AuthProvider) -> None:
    """Validate deployment and install HTTP middleware (Bearer → Security → FastMCP)."""
    validate_deployment(auth_provider)
    install_http_middleware_stack(
        server,
        auth_provider,
        mcp_path=config.MCP_PATH,
    )


def _run_stdio() -> None:
    server, _auth_provider = build_app()
    install_discovery_logging(server, mcp_path=config.MCP_PATH)
    log_startup_banner(server._tool_manager)
    print("Tasks Bridge running on stdio.")
    server.run(transport="stdio")


def _port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            return True
    return False


def _report_already_running() -> None:
    local_url = config.mcp_http_url(host="127.0.0.1")
    print(f"Tasks Bridge is already running at {local_url}")

    public_url = config.public_mcp_url()
    if public_url:
        print(f"Public MCP URL: {public_url}")
        print("If you changed MCP_PUBLIC_HOST, stop the old server and start again.")
    else:
        print("Nothing to do.")


def _run_http() -> None:
    bind_host = "127.0.0.1" if config.HOST in {"0.0.0.0", "::"} else config.HOST
    if not config.IS_PRODUCTION and _port_in_use(bind_host, config.PORT):
        _report_already_running()
        sys.exit(0)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    server, auth_provider = build_app()
    prepare_http_stack(server, auth_provider)
    install_discovery_logging(server, mcp_path=config.MCP_PATH)
    log_startup_banner(server._tool_manager)

    print(f"Deployment: {config.DEPLOYMENT}")
    print(f"Auth mode: {auth_provider.mode}")
    print(f"Listening on http://{config.HOST}:{config.PORT}{config.MCP_PATH}")

    public_url = config.public_mcp_url()
    if public_url:
        print(f"Public MCP URL: {public_url}")
    elif config.IS_PRODUCTION:
        print("Warning: MCP_PUBLIC_HOST or RAILWAY_PUBLIC_DOMAIN is not set.")
    else:
        print("Local HTTP mode. ChatGPT tunnel: see docs/local-dev.md.")

    server.run(transport="streamable-http")


def main() -> None:
    parser = argparse.ArgumentParser(description="Tasks Bridge MCP server")
    parser.add_argument(
        "--stdio",
        action="store_true",
        help="Use stdio transport for Cursor subprocess mode (default is HTTP on port 8000)",
    )
    args = parser.parse_args()

    transport = os.environ.get("MCP_TRANSPORT", "").strip().lower()
    if args.stdio or transport == "stdio":
        _run_stdio()
    else:
        _run_http()


if __name__ == "__main__":
    main()
