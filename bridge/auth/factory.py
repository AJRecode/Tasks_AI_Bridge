"""Resolve and construct the inbound MCP auth provider."""

from __future__ import annotations

from bridge import config
from bridge.auth.base import AuthProvider
from bridge.auth.none import NoneAuthProvider
from bridge.auth.oauth import OAuthAuthProvider
from bridge.auth.static_bearer import StaticBearerAuthProvider

_AUTH_MODES = {"none", "static", "oauth"}


def resolve_auth_mode() -> str:
    """Return ``none``, ``static``, or ``oauth`` from env and deployment defaults."""
    explicit = config.MCP_AUTH_MODE.strip().lower()
    if explicit:
        if explicit not in _AUTH_MODES:
            allowed = ", ".join(sorted(_AUTH_MODES))
            raise RuntimeError(
                f"Invalid MCP_AUTH_MODE={config.MCP_AUTH_MODE!r}. "
                f"Expected one of: {allowed}."
            )
        return explicit
    if config.IS_PRODUCTION:
        return "static"
    return "none"


def create_auth_provider(mode: str | None = None) -> AuthProvider:
    """Build the auth provider for the selected mode."""
    selected = mode or resolve_auth_mode()
    if selected not in _AUTH_MODES:
        allowed = ", ".join(sorted(_AUTH_MODES))
        raise RuntimeError(
            f"Invalid auth mode {selected!r}. Expected exactly one of: {allowed}."
        )
    providers: dict[str, AuthProvider] = {
        "none": NoneAuthProvider(),
        "static": StaticBearerAuthProvider(),
        "oauth": OAuthAuthProvider(),
    }
    return providers[selected]


def validate_deployment(auth_provider: AuthProvider) -> None:
    """Run auth-mode and deployment hardening checks before serving HTTP."""
    auth_provider.validate_deployment()
    _validate_preview_environment()


def _validate_preview_environment() -> None:
    if config.is_railway_preview() and not config.ALLOW_PREVIEW_SECRETS:
        if config.has_google_oauth_secrets():
            raise RuntimeError(
                "Google OAuth secrets are present in a Railway preview environment. "
                "Use sealed variables for production only, disable PR environments for "
                "this service, or set ALLOW_PREVIEW_SECRETS=1 only for trusted previews."
            )
