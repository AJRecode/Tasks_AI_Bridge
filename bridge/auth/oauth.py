"""MCP OAuth resource-server mode — WorkOS/AuthKit access-token verification."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import httpx
from pydantic import AnyHttpUrl
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from bridge import config
from bridge.auth.base import AuthProvider
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings

if TYPE_CHECKING:
    from mcp.server.fastmcp.server import FastMCP

LOGGER = logging.getLogger("tasks_bridge.auth.oauth")

_JWT_ALGORITHMS = ("RS256", "ES256")
_JWT_LEEWAY_SECONDS = 60


def email_from_claims(claims: dict[str, Any]) -> str | None:
    """Extract a lowercase email from a WorkOS (or similar) access-token payload."""
    email = claims.get("email")
    if isinstance(email, str) and email.strip():
        return email.strip().lower()
    emails = claims.get("emails")
    if isinstance(emails, list) and emails:
        first = emails[0]
        if isinstance(first, str) and first.strip():
            return first.strip().lower()
        if isinstance(first, dict):
            nested = first.get("email") or first.get("value")
            if isinstance(nested, str) and nested.strip():
                return nested.strip().lower()
    return None


def audience_values(claim: Any) -> list[str]:
    if claim is None:
        return []
    if isinstance(claim, str):
        return [claim]
    if isinstance(claim, (list, tuple)):
        return [str(item) for item in claim if item]
    return [str(claim)]


class WorkOSTokenVerifier:
    """Validate AuthKit JWTs and restrict access to configured emails."""

    def __init__(
        self,
        *,
        issuer: str,
        audiences: frozenset[str],
        allowed_emails: frozenset[str],
    ) -> None:
        self.issuer = issuer
        self.audiences = audiences
        self.allowed_emails = allowed_emails
        self._jwks_client = None

    def _claims_for_token(self, token: str) -> dict[str, Any] | None:
        import jwt
        from jwt import PyJWKClient

        if self._jwks_client is None:
            self._jwks_client = PyJWKClient(f"{self.issuer}/oauth2/jwks")
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            return jwt.decode(
                token,
                signing_key.key,
                algorithms=list(_JWT_ALGORITHMS),
                issuer=self.issuer,
                leeway=_JWT_LEEWAY_SECONDS,
                options={"verify_aud": False, "require": ["exp", "iss", "sub"]},
            )
        except jwt.PyJWTError:
            LOGGER.info("Rejected MCP OAuth token (JWT validation failed)")
            return None

    async def verify_token(self, token: str) -> AccessToken | None:
        claims = self._claims_for_token(token)
        if not claims:
            return None

        auds = audience_values(claims.get("aud"))
        if not self.audiences.intersection(auds):
            LOGGER.warning(
                "Rejected MCP OAuth token with unmatched audience %s (allowed %s)",
                auds,
                sorted(self.audiences),
            )
            return None

        email = email_from_claims(claims)
        if not email or email not in self.allowed_emails:
            LOGGER.warning("Rejected MCP OAuth token for email %r", email)
            return None

        raw_scope = claims.get("scope") or claims.get("scp") or ""
        if isinstance(raw_scope, str):
            scopes = [part for part in raw_scope.split() if part]
        elif isinstance(raw_scope, list):
            scopes = [str(part) for part in raw_scope if part]
        else:
            scopes = []

        client_id = str(claims.get("azp") or claims.get("client_id") or "workos")
        subject = claims.get("sub")
        expires_at = claims.get("exp")
        return AccessToken(
            token=token,
            client_id=client_id,
            scopes=scopes,
            expires_at=int(expires_at) if expires_at is not None else None,
            resource=next(iter(self.audiences), None),
            subject=str(subject) if subject is not None else None,
            claims=claims,
        )


class OAuthAuthProvider(AuthProvider):
    """FastMCP resource-server mode: verify WorkOS tokens, do not issue them."""

    @property
    def mode(self) -> str:
        return "oauth"

    def validate_deployment(self) -> None:
        issuer = config.authkit_issuer_url()
        if not issuer:
            raise RuntimeError(
                "MCP_AUTH_MODE=oauth requires WORKOS_AUTHKIT_DOMAIN "
                "(AuthKit origin, e.g. https://example.authkit.app)."
            )
        if not config.oauth_allowed_emails():
            raise RuntimeError(
                "MCP_AUTH_MODE=oauth requires MCP_OAUTH_ALLOWED_EMAIL "
                "(comma-separated emails allowed to call /mcp)."
            )
        if not config.public_mcp_url():
            raise RuntimeError(
                "MCP_AUTH_MODE=oauth requires MCP_PUBLIC_HOST or "
                "RAILWAY_PUBLIC_DOMAIN so the MCP resource URL is known."
            )

    def fastmcp_kwargs(self) -> dict[str, Any]:
        issuer = config.authkit_issuer_url()
        resource = config.public_mcp_url()
        if not issuer or not resource:
            return {}
        return {
            "token_verifier": WorkOSTokenVerifier(
                issuer=issuer,
                audiences=config.oauth_allowed_audiences(),
                allowed_emails=config.oauth_allowed_emails(),
            ),
            "auth": AuthSettings(
                issuer_url=AnyHttpUrl(issuer),
                resource_server_url=AnyHttpUrl(resource),
            ),
        }

    def register_routes(self, fastmcp: FastMCP) -> None:
        issuer = config.authkit_issuer_url()
        resource = config.public_mcp_url()
        if not issuer or not resource:
            return

        @fastmcp.custom_route("/.well-known/oauth-protected-resource", methods=["GET"])
        async def protected_resource_metadata(_request: Request) -> JSONResponse:
            return JSONResponse(
                {
                    "resource": resource,
                    "authorization_servers": [issuer],
                    "bearer_methods_supported": ["header"],
                }
            )

        @fastmcp.custom_route(
            "/.well-known/oauth-authorization-server", methods=["GET"]
        )
        async def authorization_server_metadata(_request: Request) -> Response:
            url = f"{issuer}/.well-known/oauth-authorization-server"
            try:
                async with httpx.AsyncClient(timeout=8.0) as client:
                    upstream = await client.get(url)
            except httpx.HTTPError:
                LOGGER.exception("Failed to fetch AuthKit authorization-server metadata")
                return JSONResponse(
                    {"error": "authorization_server_unavailable"},
                    status_code=502,
                )
            return Response(
                content=upstream.content,
                status_code=upstream.status_code,
                media_type="application/json",
            )
