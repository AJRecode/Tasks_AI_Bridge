"""Environment-based configuration for local dev and production (e.g. Railway)."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent

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


def mcp_http_url(*, host: str | None = None, port: int | None = None) -> str:
    host = host or HOST
    port = port if port is not None else PORT
    return f"http://{host}:{port}{MCP_PATH}"


def public_mcp_url() -> str | None:
    if not PUBLIC_HOST:
        return None
    host = PUBLIC_HOST.removeprefix("https://").removeprefix("http://").split("/")[0]
    return f"https://{host}{MCP_PATH}"
