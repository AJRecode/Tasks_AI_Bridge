"""MCP OAuth for ChatGPT over Railway HTTPS (planned — FastMCP native auth)."""

from __future__ import annotations

from auth.base import AuthProvider


class OAuthAuthProvider(AuthProvider):
    """Placeholder until FastMCP auth= / auth_server_provider= is wired."""

    @property
    def mode(self) -> str:
        return "oauth"

    def validate_deployment(self) -> None:
        raise RuntimeError(
            "MCP_AUTH_MODE=oauth is not implemented yet. "
            "Use MCP_AUTH_MODE=static for Railway bearer auth, or the OpenAI "
            "Secure MCP Tunnel for ChatGPT locally. See docs/mcp-oauth-design.md."
        )
