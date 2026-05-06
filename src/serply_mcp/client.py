from __future__ import annotations

import asyncio
import logging
import random
import time
import urllib.parse
from typing import Any

import httpx

from serply_mcp import __version__
from serply_mcp.config import Settings
from serply_mcp.errors import (
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    SerplyError,
    ValidationError,
)

logger = logging.getLogger(__name__)

_RETRY_STATUS = {429, 500, 502, 503, 504}


class SerplyClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.serply_base_url,
            timeout=httpx.Timeout(settings.serply_timeout_seconds),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            headers={
                "User-Agent": f"serply-mcp-server/{__version__} (+github)",
                "Accept": "application/json",
            },
            follow_redirects=True,
        )

    async def __aenter__(self) -> SerplyClient:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    def _auth_headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        from serply_mcp.context import request_api_key
        key = request_api_key.get() or self._settings.serply_api_key
        headers: dict[str, str] = {"X-Api-Key": key}
        if extra:
            headers.update(extra)
        return headers

    def _safe_log_headers(self, headers: dict[str, str]) -> dict[str, str]:
        return {
            k: "***REDACTED***" if k.lower() == "x-api-key" else v
            for k, v in headers.items()
        }

    async def get(self, path: str, *, extra_headers: dict[str, str] | None = None) -> dict[str, Any]:
        return await self._request("GET", path, extra_headers=extra_headers)

    async def post(self, path: str, *, json: dict[str, Any], extra_headers: dict[str, str] | None = None) -> dict[str, Any]:
        return await self._request("POST", path, json=json, extra_headers=extra_headers)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        headers = self._auth_headers(extra_headers)
        max_attempts = self._settings.serply_max_retries + 1

        for attempt in range(max_attempts):
            start = time.monotonic()
            try:
                if method == "GET":
                    resp = await self._client.get(path, headers=headers)
                else:
                    resp = await self._client.post(path, headers=headers, json=json)
            except httpx.TimeoutException as exc:
                raise SerplyError(f"Request timed out: {exc}", status_code=504) from exc
            except httpx.RequestError as exc:
                raise SerplyError(f"Network error: {exc}", status_code=503) from exc

            latency_ms = int((time.monotonic() - start) * 1000)
            rl_limit = resp.headers.get("x-ratelimit-requests-limit")
            rl_remaining = resp.headers.get("x-ratelimit-requests-remaining")

            logger.info(
                "serply request",
                extra={
                    "method": method,
                    "path": path,
                    "status": resp.status_code,
                    "latency_ms": latency_ms,
                    "request_id": resp.headers.get("x-request-id"),
                },
            )

            if resp.status_code == 200:
                return resp.json()  # type: ignore[no-any-return]

            # Parse error body
            try:
                body = resp.json()
                msg = body.get("error", {}).get("message", resp.text)
                code = body.get("error", {}).get("code")
            except Exception:
                msg = resp.text
                code = None

            # Retry on transient errors with exponential backoff + jitter
            if resp.status_code in _RETRY_STATUS and attempt < max_attempts - 1:
                delay = (0.5 * (2 ** attempt)) + random.uniform(0, 0.5)
                logger.warning("retrying after %s (attempt %d)", resp.status_code, attempt + 1)
                await asyncio.sleep(delay)
                continue

            logger.warning("serply error %s: %s", resp.status_code, msg)

            if resp.status_code == 429:
                raise RateLimitError(
                    remaining=int(rl_remaining) if rl_remaining else None,
                    limit=int(rl_limit) if rl_limit else None,
                )
            if resp.status_code in (401, 403):
                raise AuthenticationError(msg)
            if resp.status_code == 404:
                raise NotFoundError(msg)
            if resp.status_code == 422:
                raise ValidationError(msg)
            raise SerplyError(msg, status_code=resp.status_code, serply_code=code)

        raise SerplyError("Max retries exceeded", status_code=503)

    @staticmethod
    def build_query_path(base_path: str, query: str, **params: Any) -> str:
        qs = f"q={urllib.parse.quote_plus(query)}"
        for key, val in params.items():
            if val is not None:
                qs += f"&{key}={urllib.parse.quote_plus(str(val))}"
        return f"{base_path}/{qs}"
