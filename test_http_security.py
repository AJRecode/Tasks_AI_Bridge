"""HTTP security tests (no Google API)."""

from __future__ import annotations

import asyncio
import importlib
import json
import sys
from unittest.mock import patch

import httpx
import pytest

from bridge.auth.static_bearer import BearerAuthASGI
from bridge.transport.http_security import ProductionSecurityASGI


async def _post_mcp(app, *, headers: dict[str, str] | None = None) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(
            "/mcp",
            headers=headers or {},
            content=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
        )


def _reload_security_modules(monkeypatch, **env: str | None) -> None:
    keys = {
        "TASKS_BRIDGE_DEPLOYMENT",
        "MCP_AUTH_MODE",
        "MCP_API_TOKEN",
        "RAILWAY_ENVIRONMENT",
        "TASKS_BRIDGE_PRODUCTION_ENV",
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "GOOGLE_REFRESH_TOKEN",
        "ALLOW_PREVIEW_SECRETS",
    }
    for key in keys:
        if key not in env:
            monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    import bridge.config as config

    importlib.reload(config)
    import bridge.transport.http_security as http_security
    importlib.reload(http_security)
    for module_name in list(sys.modules):
        if module_name.startswith("bridge.auth"):
            importlib.reload(sys.modules[module_name])


def _protected_mcp_app(inner_app, *, token: str = "test-secret-token"):
    """Match production install order: security inner, bearer auth outer."""
    secured = ProductionSecurityASGI(inner_app, mcp_path="/mcp")
    return BearerAuthASGI(secured, mcp_path="/mcp", token=token)


def test_unauthenticated_mcp_returns_401_before_handler(monkeypatch):
    _reload_security_modules(
        monkeypatch,
        TASKS_BRIDGE_DEPLOYMENT="production",
        MCP_AUTH_MODE="static",
        MCP_API_TOKEN="test-secret-token",
    )

    reached_handler = {"value": False}

    async def inner_app(scope, receive, send):
        reached_handler["value"] = True
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": b"{}"})

    app = _protected_mcp_app(inner_app)
    response = asyncio.run(_post_mcp(app))

    assert response.status_code == 401
    assert response.json() == {"error": "Unauthorized"}
    assert response.headers.get("www-authenticate") == "Bearer realm=\"Tasks Bridge MCP\""
    assert reached_handler["value"] is False


def test_unauthenticated_mcp_does_not_call_google(monkeypatch):
    _reload_security_modules(
        monkeypatch,
        TASKS_BRIDGE_DEPLOYMENT="production",
        MCP_AUTH_MODE="static",
        MCP_API_TOKEN="test-secret-token",
    )

    async def inner_app(scope, receive, send):
        import services.tasks.google_auth as google_auth

        google_auth.get_credentials()
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": b"{}"})

    app = _protected_mcp_app(inner_app)
    with patch("services.tasks.google_auth.get_credentials") as google_mock:
        response = asyncio.run(_post_mcp(app))

    assert response.status_code == 401
    google_mock.assert_not_called()


def test_authenticated_mcp_reaches_handler(monkeypatch):
    _reload_security_modules(
        monkeypatch,
        TASKS_BRIDGE_DEPLOYMENT="production",
        MCP_AUTH_MODE="static",
        MCP_API_TOKEN="test-secret-token",
    )

    reached_handler = {"value": False}

    async def inner_app(scope, receive, send):
        reached_handler["value"] = True
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": b"{\"ok\":true}"})

    app = _protected_mcp_app(inner_app)
    response = asyncio.run(
        _post_mcp(
            app,
            headers={"Authorization": "Bearer test-secret-token"},
        )
    )

    assert response.status_code == 200
    assert reached_handler["value"] is True
