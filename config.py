"""Deprecated compatibility shim — no importers remain in this repo.

Prefer ``from bridge import config`` or ``from bridge.config import ...``.
Scheduled for removal once external docs stop referencing root ``config.py``.
"""
from bridge.config import *  # noqa: F403
