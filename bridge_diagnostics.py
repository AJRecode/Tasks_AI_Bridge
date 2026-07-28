"""Compatibility shim — prefer ``bridge.diagnostics`` and ``bridge.logging``."""
from bridge.diagnostics import *  # noqa: F403
from bridge.logging import (  # noqa: F401
    install_discovery_logging,
    log_startup_banner,
)
