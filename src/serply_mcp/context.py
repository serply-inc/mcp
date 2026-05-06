from __future__ import annotations

from contextvars import ContextVar

# Set by PassthroughKeyMiddleware on each HTTP request.
# SerplyClient reads this to use the caller's own API key for upstream calls.
request_api_key: ContextVar[str] = ContextVar("serply_request_api_key", default="")
