"""Environment-based configuration for local dev and production (e.g. Railway).

This is the **canonical** configuration module. Import via ``from bridge import config``
or ``from bridge.config import ...``. The repo-root ``config.py`` is a compatibility shim.
"""

from __future__ import annotations

import os
from pathlib import Path

# Repo root (parent of bridge/)
PROJECT_DIR = Path(__file__).resolve().parent.parent.parent

CHATGPT_ORIGINS = [
    "https://chatgpt.com",
    "https://www.chatgpt.com",
    "https://chat.openai.com",
]


def deployment_mode() -> str:
    """Return ``local`` or ``production``."""
    explicit = os.environ.get("TASKS_BRIDGE_DEPLOYMENT", "").strip().lower()
    if explicit in {"local", "production"}:
        return explicit
    if os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RAILWAY_PUBLIC_DOMAIN"):
        return "production"
    return "local"


DEPLOYMENT = deployment_mode()
IS_PRODUCTION = DEPLOYMENT == "production"

HOST = os.environ.get("HOST", "0.0.0.0" if IS_PRODUCTION else "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))
MCP_PATH = os.environ.get("MCP_PATH", "/mcp")

PUBLIC_HOST = (
    os.environ.get("MCP_PUBLIC_HOST", "").strip()
    or os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
)

# Local OAuth file paths (ignored in production when env creds are set)
CREDENTIALS_FILE = Path(
    os.environ.get("GOOGLE_CREDENTIALS_FILE", PROJECT_DIR / "credentials.json")
)
TOKEN_FILE = Path(os.environ.get("GOOGLE_TOKEN_FILE", PROJECT_DIR / "token.json"))

# Production OAuth (set in Railway secrets)
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
GOOGLE_REFRESH_TOKEN = os.environ.get("GOOGLE_REFRESH_TOKEN", "").strip()

# Optional JSON blobs for platforms that inject full secret JSON
GOOGLE_CREDENTIALS_JSON = os.environ.get("GOOGLE_CREDENTIALS_JSON", "").strip()
GOOGLE_TOKEN_JSON = os.environ.get("GOOGLE_TOKEN_JSON", "").strip()

# Inbound MCP authentication
MCP_AUTH_MODE = os.environ.get("MCP_AUTH_MODE", "").strip()
MCP_API_TOKEN = os.environ.get("MCP_API_TOKEN", "").strip()

# MCP OAuth resource-server mode (WorkOS/AuthKit)
WORKOS_AUTHKIT_DOMAIN = os.environ.get("WORKOS_AUTHKIT_DOMAIN", "").strip()
WORKOS_API_KEY = os.environ.get("WORKOS_API_KEY", "").strip()
MCP_OAUTH_ALLOWED_EMAIL = os.environ.get("MCP_OAUTH_ALLOWED_EMAIL", "").strip()
MCP_OAUTH_ALLOWED_SUB = os.environ.get("MCP_OAUTH_ALLOWED_SUB", "").strip()
MCP_OAUTH_EXTRA_AUDIENCES = os.environ.get("MCP_OAUTH_EXTRA_AUDIENCES", "").strip()

# HTTP hardening
RATE_LIMIT_REQUESTS = int(os.environ.get("MCP_RATE_LIMIT_REQUESTS", "60"))
RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get("MCP_RATE_LIMIT_WINDOW_SECONDS", "60"))
MAX_REQUEST_BYTES = int(os.environ.get("MCP_MAX_REQUEST_BYTES", str(1024 * 1024)))

# Railway preview environments inherit variables by default — block Google secrets
# outside the named production environment unless explicitly overridden.
PRODUCTION_ENVIRONMENT_NAME = os.environ.get(
    "TASKS_BRIDGE_PRODUCTION_ENV", "production"
).strip()
ALLOW_PREVIEW_SECRETS = os.environ.get("ALLOW_PREVIEW_SECRETS", "").strip().lower() in {
    "1",
    "true",
    "yes",
}


def is_railway_preview() -> bool:
    railway_env = os.environ.get("RAILWAY_ENVIRONMENT", "").strip()
    if not railway_env:
        return False
    return railway_env.casefold() != PRODUCTION_ENVIRONMENT_NAME.casefold()


def has_google_oauth_secrets() -> bool:
    return bool(
        GOOGLE_CLIENT_ID
        or GOOGLE_CLIENT_SECRET
        or GOOGLE_REFRESH_TOKEN
        or GOOGLE_TOKEN_JSON
    )


def mcp_http_url(*, host: str | None = None, port: int | None = None) -> str:
    host = host or HOST
    port = port if port is not None else PORT
    return f"http://{host}:{port}{MCP_PATH}"


def auth_mode() -> str:
    """Return resolved inbound auth mode: ``none``, ``static``, or ``oauth``."""
    from bridge.auth.factory import resolve_auth_mode

    return resolve_auth_mode()


def public_mcp_url() -> str | None:
    if not PUBLIC_HOST:
        return None
    host = PUBLIC_HOST.removeprefix("https://").removeprefix("http://").split("/")[0]
    return f"https://{host}{MCP_PATH}"


def authkit_issuer_url() -> str | None:
    """Return the WorkOS AuthKit issuer origin, or None if unset."""
    raw = WORKOS_AUTHKIT_DOMAIN.strip()
    if not raw:
        return None
    if not raw.startswith(("http://", "https://")):
        raw = f"https://{raw}"
    return raw.rstrip("/")


def oauth_allowed_emails() -> frozenset[str]:
    """Lowercased emails allowed to call /mcp when MCP_AUTH_MODE=oauth."""
    return frozenset(
        part.strip().lower()
        for part in MCP_OAUTH_ALLOWED_EMAIL.split(",")
        if part.strip()
    )


def oauth_allowed_subs() -> frozenset[str]:
    """WorkOS user ids (JWT ``sub``) allowed when email cannot be resolved."""
    return frozenset(
        part.strip()
        for part in MCP_OAUTH_ALLOWED_SUB.split(",")
        if part.strip()
    )


def oauth_allowed_audiences() -> frozenset[str]:
    """Token ``aud`` values accepted in oauth mode (resource URL plus extras)."""
    allowed: set[str] = set()
    resource = public_mcp_url()
    if resource:
        allowed.add(resource)
    for part in MCP_OAUTH_EXTRA_AUDIENCES.split(","):
        value = part.strip()
        if value:
            allowed.add(value)
    return frozenset(allowed)
