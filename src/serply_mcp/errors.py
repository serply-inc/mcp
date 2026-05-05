from __future__ import annotations

from mcp import types as mcp_types


class SerplyError(Exception):
    def __init__(
        self,
        message: str,
        status_code: int = 500,
        serply_code: str | None = None,
        rate_limit_remaining: int | None = None,
        rate_limit_limit: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.serply_code = serply_code
        self.rate_limit_remaining = rate_limit_remaining
        self.rate_limit_limit = rate_limit_limit


class RateLimitError(SerplyError):
    def __init__(
        self,
        remaining: int | None = None,
        limit: int | None = None,
    ) -> None:
        msg = "Serply rate limit exceeded"
        if remaining is not None and limit is not None:
            msg += f" (limit={limit}, remaining={remaining})"
        super().__init__(msg, status_code=429, serply_code="too_many_requests",
                         rate_limit_remaining=remaining, rate_limit_limit=limit)


class AuthenticationError(SerplyError):
    def __init__(self, message: str = "Invalid or missing Serply API key") -> None:
        super().__init__(message, status_code=401, serply_code="unauthorized")


class NotFoundError(SerplyError):
    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message, status_code=404, serply_code="not_found")


class ValidationError(SerplyError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=422, serply_code="validation_error")


_STATUS_MAP: dict[int, type[SerplyError]] = {
    401: AuthenticationError,
    403: AuthenticationError,
    404: NotFoundError,
    422: ValidationError,
    429: RateLimitError,
}


def to_mcp_error(err: SerplyError) -> mcp_types.ErrorData:
    code_map = {
        400: -32602,
        401: -32001,
        403: -32001,
        404: -32002,
        422: -32602,
        429: -32003,
        500: -32603,
    }
    code = code_map.get(err.status_code, -32603)
    return mcp_types.ErrorData(code=code, message=str(err))
