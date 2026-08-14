"""Request-local context shared by MCP authentication and the API client."""

from contextvars import ContextVar

request_api_key: ContextVar[str | None] = ContextVar(
    "serply_request_api_key",
    default=None,
)
