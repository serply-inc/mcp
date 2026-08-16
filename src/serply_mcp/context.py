"""Request-local context shared by MCP authentication and the API client."""

from __future__ import annotations

from contextvars import ContextVar

# Set by PassthroughKeyMiddleware on each HTTP request.
# SerplyClient reads this to use the caller's own API key for upstream calls.
#
# Defaults to "" rather than None: client.py falls back with
# `request_api_key.get() or settings.serply_api_key`, and an empty string keeps
# the ContextVar's type a plain str, so nothing downstream has to narrow it.
request_api_key: ContextVar[str] = ContextVar("serply_request_api_key", default="")
