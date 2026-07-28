"""DNS rebinding and origin allowlists for public MCP HTTP transport."""

from __future__ import annotations

from urllib.parse import urlparse

from bridge import config
from mcp.server.transport_security import TransportSecuritySettings


def _normalize_public_host(value: str) -> str:
    value = value.strip()
    if not value:
        return ""

    if "://" in value:
        parsed = urlparse(value)
        return parsed.netloc or parsed.path.split("/")[0]

    return value.split("/")[0]


def _host_allowlist(*hosts: str) -> list[str]:
    allowlist: list[str] = []
    for host in hosts:
        if not host:
            continue
        allowlist.append(host)
        if not host.endswith(":*"):
            allowlist.append(f"{host}:*")
    return allowlist


def build_transport_security() -> TransportSecuritySettings | None:
    public_host = _normalize_public_host(config.PUBLIC_HOST)

    if not public_host:
        return None

    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=_host_allowlist(
            "127.0.0.1",
            "localhost",
            public_host,
        ),
        allowed_origins=[
            "http://127.0.0.1:*",
            "http://localhost:*",
            f"https://{public_host}",
            f"https://{public_host}:*",
            *config.CHATGPT_ORIGINS,
        ],
    )
