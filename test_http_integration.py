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

_MCP_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
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

_PRODUCTION_STATIC_ENV = {
    "TASKS_BRIDGE_DEPLOYMENT": "production",
    "MCP_AUTH_MODE": "static",
    "MCP_API_TOKEN": "integration-secret",
}


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


def _bootstrap_production_http_server(monkeypatch, **env: str | None):
    """Mirror mcp_server production startup: create_server + prepare_http_stack."""
    _apply_env(monkeypatch, **env)
    _reload_runtime_modules()
    from mcp_server import bootstrap_http_server

    return bootstrap_http_server()


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


async def _request_with_session(server, app, method: str, path: str, **kwargs) -> httpx.Response:
    async with server._session_manager.run():
        return await _request(app, method, path, **kwargs)


def test_production_static_without_token_fails_to_start(monkeypatch):
    _apply_env(
        monkeypatch,
        TASKS_BRIDGE_DEPLOYMENT="production",
        MCP_AUTH_MODE="static",
        MCP_API_TOKEN=None,
    )
    _reload_runtime_modules()
    from mcp_server import create_auth_provider, create_server, prepare_http_stack

    auth_provider = create_auth_provider()
    server = create_server(auth_provider)
    assert auth_provider.mode == "static"

    with pytest.raises(RuntimeError, match="MCP_AUTH_MODE=static requires MCP_API_TOKEN"):
        prepare_http_stack(server, auth_provider)


def test_http_middleware_wrapper_order(monkeypatch):
    server, _auth_provider = _bootstrap_production_http_server(
        monkeypatch, **_PRODUCTION_STATIC_ENV
    )

    app = server.streamable_http_app()
    assert type(app).__name__ == "BearerAuthASGI"
    assert type(app.app).__name__ == "ProductionSecurityASGI"


def test_production_http_startup_path_auth_and_health(monkeypatch):
    """Uses create_server() and the real production bootstrap path (not manual middleware)."""
    server, auth_provider = _bootstrap_production_http_server(
        monkeypatch, **_PRODUCTION_STATIC_ENV
    )
    assert auth_provider.mode == "static"

    app = server.streamable_http_app()

    no_token = asyncio.run(
        _request(app, "POST", "/mcp", headers=_MCP_HEADERS, json_body=_INITIALIZE_BODY)
    )
    assert no_token.status_code == 401
    assert no_token.json() == {"error": "Unauthorized"}
    assert no_token.headers.get("www-authenticate") == 'Bearer realm="Tasks Bridge MCP"'

    wrong_token = asyncio.run(
        _request(
            app,
            "POST",
            "/mcp",
            headers={**_MCP_HEADERS, "Authorization": "Bearer wrong-token"},
            json_body=_INITIALIZE_BODY,
        )
    )
    assert wrong_token.status_code == 401
    assert wrong_token.json() == {"error": "Unauthorized"}

    valid_token = asyncio.run(
        _request_with_session(
            server,
            app,
            "POST",
            "/mcp",
            headers={
                **_MCP_HEADERS,
                "Authorization": "Bearer integration-secret",
            },
            json_body=_INITIALIZE_BODY,
        )
    )
    assert valid_token.status_code == 200
    assert "result" in valid_token.text or "event:" in valid_token.text

    health = asyncio.run(_request(app, "GET", "/health"))
    assert health.status_code == 200
    payload = health.json()
    assert payload["status"] == "ok"
    assert payload["deployment"] == "production"
