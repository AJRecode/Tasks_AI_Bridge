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

# AuthKit's advertised OIDC/MCP scopes. Listed on PRM so ChatGPT can request
# refresh tokens (offline_access) during connector setup.
DISCOVERY_SCOPES = ("email", "offline_access", "openid", "profile")

_CORS_ALLOW_HEADERS = (
    "Authorization, Content-Type, Accept, mcp-protocol-version, mcp-session-id"
)
_CORS_ALLOW_METHODS = "GET, POST, DELETE, OPTIONS"
_CORS_EXPOSE_HEADERS = "WWW-Authenticate, mcp-session-id, mcp-protocol-version"

_PRM_PATHS = (
    "/.well-known/oauth-protected-resource",
    "/.well-known/oauth-protected-resource/mcp",
)
_AS_METADATA_PATHS = (
    "/.well-known/oauth-authorization-server",
    "/.well-known/oauth-authorization-server/mcp",
)
_OIDC_METADATA_PATHS = (
    "/.well-known/openid-configuration",
    "/.well-known/openid-configuration/mcp",
    "/mcp/.well-known/openid-configuration",
)


def cors_headers() -> dict[str, str]:
    """Browser CORS headers for ChatGPT/Claude connector discovery."""
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": _CORS_ALLOW_METHODS,
        "Access-Control-Allow-Headers": _CORS_ALLOW_HEADERS,
        "Access-Control-Expose-Headers": _CORS_EXPOSE_HEADERS,
        "Access-Control-Max-Age": "86400",
    }


def cors_preflight() -> Response:
    return Response(status_code=204, headers=cors_headers())


def json_with_cors(payload: dict[str, Any], status_code: int = 200) -> JSONResponse:
    return JSONResponse(payload, status_code=status_code, headers=cors_headers())


def protected_resource_payload(resource: str, issuer: str) -> dict[str, Any]:
    return {
        "resource": resource,
        "authorization_servers": [issuer],
        "bearer_methods_supported": ["header"],
        "scopes_supported": list(DISCOVERY_SCOPES),
    }


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


async def fetch_authkit_well_known(issuer: str, document: str) -> Response:
    """Proxy AuthKit RFC 8414 / OIDC discovery JSON onto this host."""
    url = f"{issuer}/.well-known/{document}"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            upstream = await client.get(url)
    except httpx.HTTPError:
        LOGGER.exception("Failed to fetch AuthKit %s metadata", document)
        return json_with_cors({"error": "authorization_server_unavailable"}, 502)
    headers = cors_headers()
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type="application/json",
        headers=headers,
    )


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


class OAuthCorsASGI:
    """Answer /mcp OPTIONS preflights and attach CORS to MCP responses.

    FastMCP's RequireAuthMiddleware otherwise 401s OPTIONS before ChatGPT's
    browser can read WWW-Authenticate or complete connector setup.
    """

    def __init__(self, app, *, mcp_path: str) -> None:
        self.app = app
        self.mcp_path = mcp_path.rstrip("/") or "/mcp"

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "").rstrip("/") or "/"
        if path != self.mcp_path:
            await self.app(scope, receive, send)
            return

        if scope.get("method") == "OPTIONS":
            await _send_preflight(send)
            return

        cors = [(key.lower().encode("latin-1"), value.encode("latin-1"))
                for key, value in cors_headers().items()]

        async def send_with_cors(message) -> None:
            if message.get("type") == "http.response.start":
                headers = list(message.get("headers", []))
                existing = {key.lower() for key, _value in headers}
                for key, value in cors:
                    if key not in existing:
                        headers.append((key, value))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_cors)


async def _send_preflight(send) -> None:
    headers = [
        (key.lower().encode("latin-1"), value.encode("latin-1"))
        for key, value in cors_headers().items()
    ]
    await send({"type": "http.response.start", "status": 204, "headers": headers})
    await send({"type": "http.response.body", "body": b""})


def _route_name(prefix: str, path: str) -> str:
    slug = path.strip("/").replace("/", "-").replace(".", "")
    return f"{prefix}-{slug}"


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

    def install_http_auth(self, fastmcp: FastMCP, *, mcp_path: str) -> None:
        original_streamable_http_app = fastmcp.streamable_http_app

        def streamable_http_app_with_oauth_cors():
            app = original_streamable_http_app()
            return OAuthCorsASGI(app, mcp_path=mcp_path)

        fastmcp.streamable_http_app = streamable_http_app_with_oauth_cors

    def register_routes(self, fastmcp: FastMCP) -> None:
        issuer = config.authkit_issuer_url()
        resource = config.public_mcp_url()
        if not issuer or not resource:
            return

        prm_body = protected_resource_payload(resource, issuer)

        async def protected_resource_metadata(request: Request) -> Response:
            if request.method == "OPTIONS":
                return cors_preflight()
            return json_with_cors(prm_body)

        async def authorization_server_metadata(request: Request) -> Response:
            if request.method == "OPTIONS":
                return cors_preflight()
            return await fetch_authkit_well_known(issuer, "oauth-authorization-server")

        async def openid_configuration(request: Request) -> Response:
            if request.method == "OPTIONS":
                return cors_preflight()
            return await fetch_authkit_well_known(issuer, "openid-configuration")

        for path in _PRM_PATHS:
            fastmcp.custom_route(
                path,
                methods=["GET", "OPTIONS"],
                name=_route_name("prm", path),
            )(protected_resource_metadata)

        for path in _AS_METADATA_PATHS:
            fastmcp.custom_route(
                path,
                methods=["GET", "OPTIONS"],
                name=_route_name("as", path),
            )(authorization_server_metadata)

        for path in _OIDC_METADATA_PATHS:
            fastmcp.custom_route(
                path,
                methods=["GET", "OPTIONS"],
                name=_route_name("oidc", path),
            )(openid_configuration)
