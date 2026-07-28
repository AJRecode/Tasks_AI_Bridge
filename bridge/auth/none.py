"""Local development — no inbound authentication on /mcp."""

from __future__ import annotations

from bridge import config
from bridge.auth.base import AuthProvider


class NoneAuthProvider(AuthProvider):
    @property
    def mode(self) -> str:
        return "none"

    def validate_deployment(self) -> None:
        if config.IS_PRODUCTION:
            raise RuntimeError(
                "MCP_AUTH_MODE=none is not allowed in production. "
                "Use MCP_AUTH_MODE=static for bearer-protected Railway deploys, "
                "or MCP_AUTH_MODE=oauth when implemented. See docs/mcp-oauth-design.md."
            )
