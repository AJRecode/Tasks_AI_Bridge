"""End-to-end HTTP integration tests for auth + security middleware stack."""

from __future__ import annotations

import asyncio
import importlib
import json
import sys

import httpx
import pytest

_INITIALIZE_BODY = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "integration-test", "version": "1"},
    },
}

_CONFIG_KEYS = (
    "TASKS_BRIDGE_DEPLOYMENT",
    "MCP_AUTH_MODE",
    "MCP_API_TOKEN",
    "RAILWAY_ENVIRONMENT",
    "RAILWAY_PUBLIC_DOMAIN",
    "TASKS_BRIDGE_PRODUCTION_ENV",
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "GOOGLE_REFRESH_TOKEN",
    "ALLOW_PREVIEW_SECRETS",
    "HOST",
    "PORT",
    "MCP_PATH",
    "MCP_PUBLIC_HOST",
)


def _apply_env(monkeypatch, **env: str | None) -> None:
    for key in _CONFIG_KEYS:
        if key not in env:
            monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)


def _reload_runtime_modules() -> None:
    import bridge.config
    import mcp_server

    importlib.reload(bridge.config)
    for module_name in sorted(sys.modules):
        if module_name.startswith("bridge.auth") or module_name.startswith(
            "bridge.transport"
        ):
            importlib.reload(sys.modules[module_name])
    importlib.reload(mcp_server)


def _build_prepared_http_app(monkeypatch, **env: str | None):
    _apply_env(monkeypatch, **env)
    _reload_runtime_modules()
    from mcp_server import build_app, prepare_http_stack

    server, auth_provider = build_app()
    prepare_http_stack(server, auth_provider)
    return server, auth_provider


async def _request(
    app,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    json_body: dict | None = None,
) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1"
    ) as client:
        return await client.request(
            method,
            path,
            headers=headers or {},
            content=json.dumps(json_body) if json_body is not None else None,
        )


def test_production_static_without_token_fails_to_start(monkeypatch):
    _apply_env(
        monkeypatch,
        TASKS_BRIDGE_DEPLOYMENT="production",
        MCP_AUTH_MODE="static",
        MCP_API_TOKEN=None,
    )
    _reload_runtime_modules()
    from mcp_server import build_app, prepare_http_stack

    server, auth_provider = build_app()
    assert auth_provider.mode == "static"

    with pytest.raises(RuntimeError, match="MCP_AUTH_MODE=static requires MCP_API_TOKEN"):
        prepare_http_stack(server, auth_provider)


def _middleware_type_name(app) -> str:
    return type(app).__name__


async def _request_with_session(server, app, method: str, path: str, **kwargs) -> httpx.Response:
    async with server._session_manager.run():
        return await _request(app, method, path, **kwargs)


def test_http_middleware_wrapper_order(monkeypatch):
    server, _auth_provider = _build_prepared_http_app(
        monkeypatch,
        TASKS_BRIDGE_DEPLOYMENT="production",
        MCP_AUTH_MODE="static",
        MCP_API_TOKEN="integration-secret",
    )

    app = server.streamable_http_app()
    assert _middleware_type_name(app) == "BearerAuthASGI"
    assert _middleware_type_name(app.app) == "ProductionSecurityASGI"


def test_wrong_bearer_token_returns_401(monkeypatch):
    server, _auth_provider = _build_prepared_http_app(
        monkeypatch,
        TASKS_BRIDGE_DEPLOYMENT="production",
        MCP_AUTH_MODE="static",
        MCP_API_TOKEN="integration-secret",
    )
    app = server.streamable_http_app()

    response = asyncio.run(
        _request(
            app,
            "POST",
            "/mcp",
            headers={"Authorization": "Bearer wrong-token"},
            json_body=_INITIALIZE_BODY,
        )
    )

    assert response.status_code == 401
    assert response.json() == {"error": "Unauthorized"}
    assert response.headers.get("www-authenticate") == 'Bearer realm="Tasks Bridge MCP"'


def test_correct_bearer_token_reaches_mcp_endpoint(monkeypatch):
    server, _auth_provider = _build_prepared_http_app(
        monkeypatch,
        TASKS_BRIDGE_DEPLOYMENT="production",
        MCP_AUTH_MODE="static",
        MCP_API_TOKEN="integration-secret",
    )
    app = server.streamable_http_app()

    response = asyncio.run(
        _request_with_session(
            server,
            app,
            "POST",
            "/mcp",
            headers={
                "Authorization": "Bearer integration-secret",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
            json_body=_INITIALIZE_BODY,
        )
    )

    assert response.status_code == 200
    body = response.text
    assert "result" in body or "event:" in body


def test_health_accessible_without_authentication(monkeypatch):
    server, _auth_provider = _build_prepared_http_app(
        monkeypatch,
        TASKS_BRIDGE_DEPLOYMENT="production",
        MCP_AUTH_MODE="static",
        MCP_API_TOKEN="integration-secret",
    )
    app = server.streamable_http_app()

    response = asyncio.run(_request(app, "GET", "/health"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["deployment"] == "production"
