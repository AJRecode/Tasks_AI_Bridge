"""Production HTTP hardening for the MCP streamable-http endpoint."""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict, deque
from typing import TYPE_CHECKING, Any

from starlette.responses import JSONResponse

from bridge import config

if TYPE_CHECKING:
    from mcp.server.fastmcp.server import FastMCP

LOGGER = logging.getLogger("tasks_bridge.security")

RATE_LIMIT_BODY = {"error": "Too many requests"}
PAYLOAD_TOO_LARGE_BODY = {"error": "Payload too large"}
INTERNAL_ERROR_BODY = {"error": "Internal server error"}


def _client_ip(scope: dict[str, Any]) -> str:
    client = scope.get("client")
    if client:
        return client[0]
    return "unknown"


class _RateLimiter:
    def __init__(self, *, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        window_start = now - self.window_seconds
        events = self._events[key]
        while events and events[0] < window_start:
            events.popleft()
        if len(events) >= self.max_requests:
            return False
        events.append(now)
        return True


async def _send_json(send, *, status: int, body: dict[str, str]) -> None:
    payload = json.dumps(body).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": payload})


class ProductionSecurityASGI:
    """Rate limits, request-size limits, and error shielding for MCP HTTP traffic."""

    def __init__(self, app, *, mcp_path: str) -> None:
        self.app = app
        self.mcp_path = mcp_path.rstrip("/") or "/mcp"
        self._rate_limiter = _RateLimiter(
            max_requests=config.RATE_LIMIT_REQUESTS,
            window_seconds=config.RATE_LIMIT_WINDOW_SECONDS,
        )

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "").rstrip("/") or "/"
        if path != self.mcp_path:
            await self._call_with_error_shield(scope, receive, send)
            return

        if not self._rate_limiter.allow(_client_ip(scope)):
            LOGGER.warning("Rate limited MCP request from %s", _client_ip(scope))
            await _send_json(send, status=429, body=RATE_LIMIT_BODY)
            return

        await self._call_with_error_shield(
            scope,
            _limit_body_size(receive, config.MAX_REQUEST_BYTES),
            send,
        )

    async def _call_with_error_shield(self, scope, receive, send) -> None:
        response_started = False

        async def shielded_send(message) -> None:
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, shielded_send)
        except PayloadTooLargeError:
            LOGGER.warning("Rejected oversized MCP request from %s", _client_ip(scope))
            if response_started:
                raise
            await _send_json(send, status=413, body=PAYLOAD_TOO_LARGE_BODY)
        except Exception:
            LOGGER.exception("Unhandled HTTP error on %s", scope.get("path", ""))
            if response_started:
                raise
            status = 500
            body = INTERNAL_ERROR_BODY if config.IS_PRODUCTION else {
                "error": "Internal server error",
                "detail": "See server logs.",
            }
            await _send_json(send, status=status, body=body)


def _limit_body_size(receive, max_bytes: int):
    total = 0

    async def wrapped_receive():
        nonlocal total
        message = await receive()
        if message.get("type") != "http.request":
            return message

        chunk = message.get("body", b"")
        total += len(chunk)
        if total > max_bytes:
            raise PayloadTooLargeError()
        return message

    return wrapped_receive


class PayloadTooLargeError(Exception):
    pass


def install_http_security(fastmcp: FastMCP, *, mcp_path: str) -> None:
    """Wrap the streamable HTTP app with rate/size limits and error shielding."""
    original_streamable_http_app = fastmcp.streamable_http_app

    def streamable_http_app_with_security():
        app = original_streamable_http_app()
        return ProductionSecurityASGI(app, mcp_path=mcp_path)

    fastmcp.streamable_http_app = streamable_http_app_with_security


def production_safe_tool_error(exc: Exception) -> RuntimeError:
    """Return a client-safe tool error while logging the original failure."""
    if isinstance(exc, ValueError):
        raise exc
    LOGGER.exception("Tool execution failed")
    if config.IS_PRODUCTION:
        return RuntimeError("Request failed.")
    return exc
