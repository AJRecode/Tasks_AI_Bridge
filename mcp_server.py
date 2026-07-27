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
import logging
import os
import socket
import sys
from urllib.parse import urlparse

from starlette.requests import Request
from starlette.responses import JSONResponse

import config
from bridge_diagnostics import (
    build_diagnostics,
    install_discovery_logging,
    log_startup_banner,
)
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from task_services import (
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

CHATGPT_ORIGINS = config.CHATGPT_ORIGINS


def _normalize_public_host(value: str) -> str:
    value = value.strip()
    if not value:
        return ""

    if "://" in value:
        parsed = urlparse(value)
        return parsed.netloc or parsed.path.split("/")[0]

    return value.split("/")[0]


def _host_allowlist(*hosts: str) -> list[str]:
    allowlist: list[str] = []
    for host in hosts:
        if not host:
            continue
        allowlist.append(host)
        if not host.endswith(":*"):
            allowlist.append(f"{host}:*")
    return allowlist


def _build_transport_security() -> TransportSecuritySettings | None:
    public_host = _normalize_public_host(config.PUBLIC_HOST)

    if not public_host:
        return None

    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=_host_allowlist(
            "127.0.0.1",
            "localhost",
            public_host,
        ),
        allowed_origins=[
            "http://127.0.0.1:*",
            "http://localhost:*",
            f"https://{public_host}",
            f"https://{public_host}:*",
            *CHATGPT_ORIGINS,
        ],
    )


READ_ONLY = ToolAnnotations(readOnlyHint=True)
WRITE_BOUNDED = ToolAnnotations(
    readOnlyHint=False,
    openWorldHint=False,
    destructiveHint=False,
)

mcp = FastMCP(
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
    transport_security=_build_transport_security(),
)


@mcp.custom_route("/health", methods=["GET"])
async def health_check(_request: Request) -> JSONResponse:
    """Lightweight health endpoint for Railway and load balancers."""
    return JSONResponse(
        {
            "status": "ok",
            "deployment": config.DEPLOYMENT,
            "server_version": build_diagnostics(mcp._tool_manager)["server_version"],
        }
    )


@mcp.tool(annotations=READ_ONLY)
def get_bridge_diagnostics() -> dict:
    """Return server version, git sha, schema hash, and registered tool names."""
    payload = build_diagnostics(mcp._tool_manager)
    payload["deployment"] = config.DEPLOYMENT
    public_url = config.public_mcp_url()
    if public_url:
        payload["public_mcp_url"] = public_url
    return payload


@mcp.tool(annotations=READ_ONLY)
def get_task_lists() -> list[dict]:
    """Return all task lists with name, id, and updated timestamp."""
    return fetch_task_lists()


@mcp.tool(annotations=READ_ONLY)
def get_tasks(list_name: str) -> list[dict]:
    """Return all tasks from one list, identified by name."""
    return fetch_tasks(list_name)


@mcp.tool(annotations=READ_ONLY)
def search_tasks(text: str) -> list[dict]:
    """Search task titles and notes across all lists."""
    return find_tasks(text)


@mcp.tool(annotations=READ_ONLY)
def get_open_tasks(list_name: str) -> list[dict]:
    """Return open (incomplete) tasks from one list."""
    return fetch_open_tasks(list_name)


@mcp.tool(annotations=WRITE_BOUNDED)
def create_task_list(list_name: str) -> dict:
    """Create a new task list. Rejects blank names and case-insensitive duplicates."""
    return add_task_list(list_name)


@mcp.tool(annotations=WRITE_BOUNDED)
def create_task(
    list_name: str,
    title: str,
    notes: str = "",
    due: str | None = None,
) -> dict:
    """Create a new task in one list, identified by name."""
    return add_task(list_name, title, notes=notes, due=due)


@mcp.tool(annotations=WRITE_BOUNDED)
def complete_task(list_name: str, task_id: str) -> dict:
    """Mark one task completed. Use task id from get_open_tasks or search_tasks."""
    return mark_task_complete(list_name, task_id)


@mcp.tool(annotations=WRITE_BOUNDED)
def update_task(
    list_name: str,
    task_id: str,
    title: str | None = None,
    notes: str | None = None,
    due: str | None = None,
) -> dict:
    """Update a task's title, notes, or due date. Pass notes="" to clear notes; due="" clears due."""
    return modify_task(list_name, task_id, title=title, notes=notes, due=due)


@mcp.tool(annotations=WRITE_BOUNDED)
def move_task(from_list_name: str, task_id: str, to_list_name: str) -> dict:
    """Move a task from one list to another. Returns the task in its new list."""
    return relocate_task(from_list_name, task_id, to_list_name)


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


def _run_stdio() -> None:
    install_discovery_logging(mcp, mcp_path=config.MCP_PATH)
    log_startup_banner(mcp._tool_manager)
    print("Tasks Bridge running on stdio.")
    mcp.run(transport="stdio")


def _run_http() -> None:
    bind_host = "127.0.0.1" if config.HOST in {"0.0.0.0", "::"} else config.HOST
    if not config.IS_PRODUCTION and _port_in_use(bind_host, config.PORT):
        _report_already_running()
        sys.exit(0)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    install_discovery_logging(mcp, mcp_path=config.MCP_PATH)
    log_startup_banner(mcp._tool_manager)

    print(f"Deployment: {config.DEPLOYMENT}")
    print(f"Listening on http://{config.HOST}:{config.PORT}{config.MCP_PATH}")

    public_url = config.public_mcp_url()
    if public_url:
        print(f"Public MCP URL: {public_url}")
    elif config.IS_PRODUCTION:
        print("Warning: MCP_PUBLIC_HOST or RAILWAY_PUBLIC_DOMAIN is not set.")
    else:
        print("Local HTTP mode. ChatGPT tunnel: see docs/local-dev.md.")

    mcp.run(transport="streamable-http")


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
