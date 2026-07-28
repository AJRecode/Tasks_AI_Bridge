"""Auth mode resolution and provider tests (no Google API)."""

from __future__ import annotations

import importlib
import sys

import pytest

import config
from bridge.auth.factory import create_auth_provider, resolve_auth_mode, validate_deployment
from bridge.auth.static_bearer import StaticBearerAuthProvider


def _reload_config(monkeypatch, **env: str | None):
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
    if "config" in sys.modules:
        importlib.reload(sys.modules["config"])
    for module_name in list(sys.modules):
        if module_name.startswith("bridge.auth") or module_name == "bridge.config":
            importlib.reload(sys.modules[module_name])


def test_local_defaults_to_none_auth_mode(monkeypatch):
    _reload_config(monkeypatch)
    assert resolve_auth_mode() == "none"
    assert create_auth_provider().mode == "none"


def test_production_defaults_to_static_auth_mode(monkeypatch):
    _reload_config(monkeypatch, TASKS_BRIDGE_DEPLOYMENT="production", MCP_API_TOKEN="secret")
    assert resolve_auth_mode() == "static"
    assert create_auth_provider().mode == "static"


def test_explicit_auth_mode_overrides_default(monkeypatch):
    _reload_config(monkeypatch, MCP_AUTH_MODE="static", MCP_API_TOKEN="secret")
    assert resolve_auth_mode() == "static"


def test_invalid_auth_mode_raises(monkeypatch):
    _reload_config(monkeypatch, MCP_AUTH_MODE="enterprise-sso")
    with pytest.raises(RuntimeError, match="Invalid MCP_AUTH_MODE"):
        resolve_auth_mode()


def test_static_production_requires_mcp_api_token(monkeypatch):
    _reload_config(
        monkeypatch,
        TASKS_BRIDGE_DEPLOYMENT="production",
        MCP_AUTH_MODE="static",
        MCP_API_TOKEN=None,
    )
    provider = StaticBearerAuthProvider()
    with pytest.raises(RuntimeError, match="MCP_API_TOKEN"):
        provider.validate_deployment()


def test_none_auth_rejected_in_production(monkeypatch):
    _reload_config(monkeypatch, TASKS_BRIDGE_DEPLOYMENT="production", MCP_AUTH_MODE="none")
    provider = create_auth_provider("none")
    with pytest.raises(RuntimeError, match="not allowed in production"):
        provider.validate_deployment()


def test_production_default_never_resolves_to_none(monkeypatch):
    """Production without MCP_AUTH_MODE must not silently use none."""
    _reload_config(monkeypatch, TASKS_BRIDGE_DEPLOYMENT="production", MCP_API_TOKEN="secret")
    assert resolve_auth_mode() == "static"
    assert create_auth_provider().mode != "none"


def test_production_default_cannot_boot_without_token(monkeypatch):
    """Production default (static) fails fast when MCP_API_TOKEN is missing."""
    _reload_config(
        monkeypatch,
        TASKS_BRIDGE_DEPLOYMENT="production",
        MCP_AUTH_MODE=None,
        MCP_API_TOKEN=None,
    )
    provider = create_auth_provider()
    assert provider.mode == "static"
    with pytest.raises(RuntimeError, match="MCP_API_TOKEN"):
        validate_deployment(provider)


def test_oauth_mode_not_implemented(monkeypatch):
    _reload_config(monkeypatch, MCP_AUTH_MODE="oauth")
    provider = create_auth_provider("oauth")
    with pytest.raises(RuntimeError, match="not implemented"):
        provider.validate_deployment()


def test_preview_environment_blocks_google_secrets(monkeypatch):
    _reload_config(
        monkeypatch,
        TASKS_BRIDGE_DEPLOYMENT="production",
        MCP_AUTH_MODE="static",
        MCP_API_TOKEN="token",
        RAILWAY_ENVIRONMENT="preview-pr-42",
        TASKS_BRIDGE_PRODUCTION_ENV="production",
        GOOGLE_CLIENT_ID="client-id",
        ALLOW_PREVIEW_SECRETS=None,
    )
    provider = StaticBearerAuthProvider()
    with pytest.raises(RuntimeError, match="preview environment"):
        validate_deployment(provider)
