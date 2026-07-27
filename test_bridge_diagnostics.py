"""Tests for bridge_diagnostics (no Google API)."""

from bridge_diagnostics import (
    SERVER_VERSION,
    build_diagnostics,
    compute_schema_hash,
    connection_id_from_http,
    ordered_tool_names,
)
from mcp.server.fastmcp.tools.tool_manager import ToolManager


def _tool_manager_with(*names: str) -> ToolManager:
    manager = ToolManager()

    def make_tool(name: str):
        def fn() -> str:
            return name

        manager.add_tool(fn, name=name, description=f"Tool {name}")
        return fn

    for name in names:
        make_tool(name)
    return manager


def test_build_diagnostics_shape():
    manager = _tool_manager_with("alpha", "beta")
    payload = build_diagnostics(manager)

    assert payload["server_version"] == SERVER_VERSION
    assert isinstance(payload["git_sha"], str)
    assert payload["git_sha"]
    assert payload["started_at"].endswith("Z")
    assert payload["schema_hash"].startswith("sha256:")
    assert payload["tool_names"] == ["alpha", "beta"]


def test_schema_hash_changes_when_tools_change():
    first = compute_schema_hash(_tool_manager_with("alpha"))
    second = compute_schema_hash(_tool_manager_with("alpha", "beta"))
    assert first != second


def test_connection_id_is_stable_for_same_headers():
    scope = {
        "headers": [
            (b"mcp-session-id", b"session-123"),
            (b"user-agent", b"inspector-client/1.0"),
        ],
        "client": ("127.0.0.1", 12345),
    }
    assert connection_id_from_http(scope) == connection_id_from_http(scope)


def test_ordered_tool_names_sorted():
    manager = _tool_manager_with("zebra", "alpha")
    assert ordered_tool_names(manager) == ["alpha", "zebra"]
