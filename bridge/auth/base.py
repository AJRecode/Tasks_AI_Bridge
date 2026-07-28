"""Auth provider interface for inbound MCP HTTP requests."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp.server.fastmcp.server import FastMCP


class AuthProvider(ABC):
    """Produces FastMCP and HTTP auth configuration for one inbound auth mode."""

    @property
    @abstractmethod
    def mode(self) -> str:
        """One of ``none``, ``static``, or ``oauth``."""

    @abstractmethod
    def validate_deployment(self) -> None:
        """Fail fast when this mode is unsafe or misconfigured."""

    def fastmcp_kwargs(self) -> dict[str, Any]:
        """Extra keyword arguments for ``FastMCP(...)`` (OAuth uses this)."""
        return {}

    def install_http_auth(self, fastmcp: FastMCP, *, mcp_path: str) -> None:
        """Wrap the streamable HTTP app with mode-specific inbound auth, if any."""
