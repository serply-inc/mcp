from __future__ import annotations

import ipaddress
import logging
import socket
import time
from collections import deque

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)


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


class PassthroughKeyMiddleware:
    """Extract the caller's Serply API key and make it available for upstream calls.

    Accepts the key via either:
      - X-Api-Key: <key>
      - Authorization: Bearer <key>

    Returns 401 if no key is present. The extracted key is stored in a
    ContextVar so SerplyClient can use it for the duration of the request.
    """

    def __init__(
        self,
        app: ASGIApp,
        mcp_path: str,
        rate_limiter: RateLimiter,
    ) -> None:
        self._app = app
        self._mcp_path = mcp_path.rstrip("/")
        self._rate_limiter = rate_limiter

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self._app(scope, receive, send)
            return

        path: str = scope.get("path", "")

        if path == "/healthz" or not path.startswith(self._mcp_path):
            await self._app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        key = headers.get(b"x-api-key", b"").decode().strip()
        if not key:
            auth = headers.get(b"authorization", b"").decode()
            if auth.lower().startswith("bearer "):
                key = auth[7:].strip()

        if not key:
            await self._send_401(send, scope)
            return

        if not self._rate_limiter.is_allowed(key):
            logger.warning("rate limit exceeded for key prefix=%s", key[:8])
            await self._send_429(send, scope)
            return

        from serply_mcp.context import request_api_key
        token = request_api_key.set(key)
        try:
            await self._app(scope, receive, send)
        finally:
            request_api_key.reset(token)

    @staticmethod
    async def _send_401(send: Send, scope: Scope) -> None:
        response = JSONResponse(
            {"error": "Unauthorized — provide your Serply API key via X-Api-Key header"},
            status_code=401,
        )
        await response(scope, {}, send)  # type: ignore[arg-type]

    @staticmethod
    async def _send_429(send: Send, scope: Scope) -> None:
        response = JSONResponse({"error": "Too Many Requests"}, status_code=429)
        await response(scope, {}, send)  # type: ignore[arg-type]
