"""Compose inbound HTTP middleware for the MCP streamable-http app."""

from __future__ import annotations

from typing import TYPE_CHECKING

from bridge.transport.http_security import install_http_security

if TYPE_CHECKING:
    from bridge.auth.base import AuthProvider
    from mcp.server.fastmcp.server import FastMCP


def install_http_middleware_stack(
    fastmcp: FastMCP,
    auth_provider: AuthProvider,
    *,
    mcp_path: str,
) -> None:
    """Wrap streamable HTTP so inbound requests flow: Bearer → Security → FastMCP.

    Install inner layers first (security on FastMCP, then bearer outside security).
    """
    install_http_security(fastmcp, mcp_path=mcp_path)
    auth_provider.install_http_auth(fastmcp, mcp_path=mcp_path)
