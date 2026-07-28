"""Bridge version, schema fingerprinting, and diagnostics payloads."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from bridge.config import PROJECT_DIR

if TYPE_CHECKING:
    from mcp.server.fastmcp.tools.tool_manager import ToolManager

# Bump when tool schemas, MCP surface, or security behavior changes.
SERVER_VERSION = "1.6.3"

STARTED_AT = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

BRIDGE_STATE_DIR = PROJECT_DIR / ".tasks-bridge"
RESTART_RECORD_FILE = BRIDGE_STATE_DIR / "server-restart.json"


def resolve_git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=2,
            cwd=PROJECT_DIR,
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
