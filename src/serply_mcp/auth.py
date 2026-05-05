from __future__ import annotations

import ipaddress
import secrets
import socket
import time
from collections import deque

import structlog
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

logger = structlog.get_logger(__name__)


class RateLimiter:
    """In-memory sliding-window rate limiter keyed by token."""

    def __init__(self, requests_per_minute: int) -> None:
        self._limit = requests_per_minute
        self._windows: dict[str, deque[float]] = {}

    def is_allowed(self, token: str) -> bool:
        now = time.monotonic()
        window_start = now - 60.0
        if token not in self._windows:
            self._windows[token] = deque()
        dq = self._windows[token]
        while dq and dq[0] < window_start:
            dq.popleft()
        if len(dq) >= self._limit:
            return False
        dq.append(now)
        return True


_PRIVATE_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),   # link-local / AWS metadata
    ipaddress.ip_network("100.64.0.0/10"),    # CGNAT
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


async def check_ssrf(url: str) -> None:
    """Raise ValueError if the URL resolves to a private/internal address."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Scheme '{parsed.scheme}' is not allowed; only http/https permitted")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL has no hostname")
    try:
        # Resolve to get actual IP(s)
        infos = await _resolve(hostname)
    except OSError as exc:
        raise ValueError(f"Could not resolve hostname '{hostname}': {exc}") from exc

    for addr in infos:
        ip = ipaddress.ip_address(addr)
        for net in _PRIVATE_NETWORKS:
            if ip in net:
                raise ValueError(
                    f"URL '{url}' resolves to a private/internal address ({ip}) which is not allowed"
                )


async def _resolve(hostname: str) -> list[str]:
    import asyncio
    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(
        None,
        lambda: socket.getaddrinfo(hostname, None, socket.AF_UNSPEC)
    )
    return [str(r[4][0]) for r in results]


class BearerAuthMiddleware:
    """ASGI middleware enforcing bearer-token auth on the MCP path."""

    def __init__(
        self,
        app: ASGIApp,
        token: str,
        mcp_path: str,
        rate_limiter: RateLimiter,
    ) -> None:
        self._app = app
        self._token = token
        self._mcp_path = mcp_path.rstrip("/")
        self._rate_limiter = rate_limiter

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self._app(scope, receive, send)
            return

        path: str = scope.get("path", "")

        # Health check is exempt
        if path == "/healthz":
            await self._app(scope, receive, send)
            return

        # Only enforce on MCP path
        if not path.startswith(self._mcp_path):
            await self._app(scope, receive, send)
            return

        request = Request(scope, receive)
        auth_header = request.headers.get("authorization", "")

        if not auth_header.lower().startswith("bearer "):
            await self._send_401(send, scope)
            return

        provided_token = auth_header[7:]  # strip "Bearer "

        if not secrets.compare_digest(provided_token.encode(), self._token.encode()):
            logger.warning("auth_failed", reason="invalid_token")
            await self._send_401(send, scope)
            return

        if not self._rate_limiter.is_allowed(provided_token):
            logger.warning("rate_limit_exceeded")
            await self._send_429(send, scope)
            return

        await self._app(scope, receive, send)

    @staticmethod
    async def _send_401(send: Send, scope: Scope) -> None:
        response = JSONResponse(
            {"error": "Unauthorized"},
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )
        await response(scope, {}, send)  # type: ignore[arg-type]

    @staticmethod
    async def _send_429(send: Send, scope: Scope) -> None:
        response = JSONResponse({"error": "Too Many Requests"}, status_code=429)
        await response(scope, {}, send)  # type: ignore[arg-type]
