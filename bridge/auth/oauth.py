"""MCP OAuth for ChatGPT over Railway HTTPS (exploratory — prefer external IdP)."""

from __future__ import annotations

from bridge.auth.base import AuthProvider


class OAuthAuthProvider(AuthProvider):
    """Placeholder until FastMCP auth= / auth_server_provider= is wired."""

    @property
    def mode(self) -> str:
        return "oauth"

    def validate_deployment(self) -> None:
        raise RuntimeError(
            "MCP_AUTH_MODE=oauth is not implemented yet. "
            "Use MCP_AUTH_MODE=static for Railway bearer auth, or the OpenAI "
            "Secure MCP Tunnel for ChatGPT locally. OAuth direction is exploratory "
            "(external IdP preferred) — see docs/mcp-oauth-design.md."
        )
