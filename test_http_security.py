"""HTTP security tests (no Google API)."""

from __future__ import annotations

import asyncio
import importlib
import json
import sys
from unittest.mock import patch

import httpx
import pytest

import config
import http_security
from http_security import ProductionSecurityASGI


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
    importlib.reload(config)
    if "http_security" in sys.modules:
        importlib.reload(http_security)


def test_unauthenticated_mcp_returns_401_before_handler(monkeypatch):
    _reload_security_modules(
        monkeypatch,
        TASKS_BRIDGE_DEPLOYMENT="production",
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

    app = ProductionSecurityASGI(inner_app, mcp_path="/mcp")
    response = asyncio.run(_post_mcp(app))

    assert response.status_code == 401
    assert response.json() == {"error": "Unauthorized"}
    assert reached_handler["value"] is False


def test_unauthenticated_mcp_does_not_call_google(monkeypatch):
    _reload_security_modules(
        monkeypatch,
        TASKS_BRIDGE_DEPLOYMENT="production",
        MCP_API_TOKEN="test-secret-token",
    )

    async def inner_app(scope, receive, send):
        import google_auth

        google_auth.get_credentials()
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": b"{}"})

    app = ProductionSecurityASGI(inner_app, mcp_path="/mcp")
    with patch("google_auth.get_credentials") as google_mock:
        response = asyncio.run(_post_mcp(app))

    assert response.status_code == 401
    google_mock.assert_not_called()


def test_authenticated_mcp_reaches_handler(monkeypatch):
    _reload_security_modules(
        monkeypatch,
        TASKS_BRIDGE_DEPLOYMENT="production",
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

    app = ProductionSecurityASGI(inner_app, mcp_path="/mcp")
    response = asyncio.run(
        _post_mcp(
            app,
            headers={"Authorization": "Bearer test-secret-token"},
        )
    )

    assert response.status_code == 200
    assert reached_handler["value"] is True


def test_production_requires_mcp_api_token(monkeypatch):
    _reload_security_modules(
        monkeypatch,
        TASKS_BRIDGE_DEPLOYMENT="production",
        MCP_API_TOKEN=None,
    )
    with pytest.raises(RuntimeError, match="MCP_API_TOKEN"):
        http_security.validate_deployment_security()


def test_preview_environment_blocks_google_secrets(monkeypatch):
    _reload_security_modules(
        monkeypatch,
        TASKS_BRIDGE_DEPLOYMENT="production",
        MCP_API_TOKEN="token",
        RAILWAY_ENVIRONMENT="preview-pr-42",
        TASKS_BRIDGE_PRODUCTION_ENV="production",
        GOOGLE_CLIENT_ID="client-id",
        ALLOW_PREVIEW_SECRETS=None,
    )
    with pytest.raises(RuntimeError, match="preview environment"):
        http_security.validate_deployment_security()
