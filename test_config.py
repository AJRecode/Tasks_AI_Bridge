"""Unit tests for bridge.config (no Google API, no secrets)."""

import importlib
import os
import sys


def _reload_config(**env):
    for key in (
        "TASKS_BRIDGE_DEPLOYMENT",
        "RAILWAY_ENVIRONMENT",
        "RAILWAY_PUBLIC_DOMAIN",
        "MCP_PUBLIC_HOST",
        "HOST",
        "PORT",
    ):
        if key not in env:
            os.environ.pop(key, None)
    for key, value in env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    import bridge.config as config

    return importlib.reload(config)


def test_default_deployment_is_local():
    cfg = _reload_config()
    assert cfg.deployment_mode() == "local"
    assert cfg.HOST == "127.0.0.1"


def test_production_deployment_from_railway():
    cfg = _reload_config(RAILWAY_PUBLIC_DOMAIN="tasks-bridge.up.railway.app")
    assert cfg.deployment_mode() == "production"
    assert cfg.HOST == "0.0.0.0"
    assert cfg.public_mcp_url() == "https://tasks-bridge.up.railway.app/mcp"


def test_public_host_override():
    cfg = _reload_config(MCP_PUBLIC_HOST="example.com")
    assert cfg.PUBLIC_HOST == "example.com"


if __name__ == "__main__":
    test_default_deployment_is_local()
    test_production_deployment_from_railway()
    test_public_host_override()
    _reload_config()
    print("All config tests passed.")
