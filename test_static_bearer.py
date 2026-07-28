"""Direct ASGI tests for static bearer auth (no Google API, no rate limiter)."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from bridge.auth.static_bearer import BearerAuthASGI, WWW_AUTHENTICATE


async def _post_mcp(app, *, headers: dict[str, str] | None = None) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(
            "/mcp",
            headers=headers or {},
            content=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
        )


def _bearer_app(*, token: str = "test-secret-token"):
    reached = {"value": False}

    async def inner_app(scope, receive, send):
        reached["value"] = True
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": b"{\"ok\":true}"})

    app = BearerAuthASGI(inner_app, mcp_path="/mcp", token=token)
    return app, reached


def test_bearer_asgi_rejects_missing_token():
    app, reached = _bearer_app()
    response = asyncio.run(_post_mcp(app))

    assert response.status_code == 401
    assert response.json() == {"error": "Unauthorized"}
    assert response.headers.get("www-authenticate") == WWW_AUTHENTICATE
    assert reached["value"] is False


def test_bearer_asgi_rejects_wrong_token():
    app, reached = _bearer_app()
    response = asyncio.run(
        _post_mcp(app, headers={"Authorization": "Bearer wrong-token"})
    )

    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == WWW_AUTHENTICATE
    assert reached["value"] is False


def test_bearer_asgi_accepts_valid_token():
    app, reached = _bearer_app()
    response = asyncio.run(
        _post_mcp(app, headers={"Authorization": "Bearer test-secret-token"})
    )

    assert response.status_code == 200
    assert reached["value"] is True


def test_bearer_asgi_accepts_case_insensitive_scheme():
    app, reached = _bearer_app()
    response = asyncio.run(
        _post_mcp(app, headers={"Authorization": "bearer test-secret-token"})
    )

    assert response.status_code == 200
    assert reached["value"] is True


def test_bearer_asgi_rejects_non_bearer_scheme():
    app, reached = _bearer_app()
    response = asyncio.run(
        _post_mcp(app, headers={"Authorization": "Basic dGVzdA=="})
    )

    assert response.status_code == 401
    assert reached["value"] is False


def test_static_mode_requires_token_locally(monkeypatch):
    monkeypatch.setenv("MCP_AUTH_MODE", "static")
    monkeypatch.delenv("MCP_API_TOKEN", raising=False)
    monkeypatch.delenv("TASKS_BRIDGE_DEPLOYMENT", raising=False)
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)

    import importlib

    import bridge.config as bridge_config
    from bridge.auth.static_bearer import StaticBearerAuthProvider

    importlib.reload(bridge_config)
    provider = StaticBearerAuthProvider()
    with pytest.raises(RuntimeError, match="MCP_AUTH_MODE=static requires MCP_API_TOKEN"):
        provider.validate_deployment()
