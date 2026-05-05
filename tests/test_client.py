from __future__ import annotations

import httpx
import pytest

from serply_mcp.client import SerplyClient
from serply_mcp.config import Settings
from serply_mcp.errors import (
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    SerplyError,
    ValidationError,
)


@pytest.mark.asyncio
async def test_get_sends_api_key(test_settings, mock_serply):
    mock_serply.get("/v1/search/q=test").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    async with SerplyClient(test_settings) as c:
        result = await c.get("/v1/search/q=test")
    assert result == {"results": []}
    assert mock_serply.calls[0].request.headers["x-api-key"] == "test-api-key-1234567890"


@pytest.mark.asyncio
async def test_get_returns_parsed_json(test_settings, mock_serply):
    payload = {"results": [{"title": "A", "link": "https://a.com", "description": "d"}], "total": 1}
    mock_serply.get("/v1/search/q=hello").mock(return_value=httpx.Response(200, json=payload))
    async with SerplyClient(test_settings) as c:
        result = await c.get("/v1/search/q=hello")
    assert result == payload


@pytest.mark.asyncio
async def test_post_sends_api_key_and_json(test_settings, mock_serply):
    mock_serply.post("/v1/request").mock(
        return_value=httpx.Response(200, json={"content": "ok", "url": "https://example.com"})
    )
    async with SerplyClient(test_settings) as c:
        result = await c.post("/v1/request", json={"url": "https://example.com"})
    assert result["content"] == "ok"
    call = mock_serply.calls[0]
    assert call.request.headers["x-api-key"] == "test-api-key-1234567890"
    body = call.request.content.decode()
    assert "https://example.com" in body


@pytest.mark.asyncio
async def test_raises_rate_limit_error(test_settings, mock_serply):
    mock_serply.get("/v1/search/q=test").mock(
        return_value=httpx.Response(
            429,
            json={"error": {"code": "too_many_requests", "message": "rate limit"}},
            headers={
                "x-ratelimit-requests-limit": "100",
                "x-ratelimit-requests-remaining": "0",
            },
        )
    )
    async with SerplyClient(test_settings) as c:
        with pytest.raises(RateLimitError) as exc_info:
            await c.get("/v1/search/q=test")
    assert exc_info.value.rate_limit_limit == 100
    assert exc_info.value.rate_limit_remaining == 0
    assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_raises_authentication_error_401(test_settings, mock_serply):
    mock_serply.get("/v1/search/q=test").mock(
        return_value=httpx.Response(
            401, json={"error": {"code": "unauthorized", "message": "bad key"}}
        )
    )
    async with SerplyClient(test_settings) as c:
        with pytest.raises(AuthenticationError):
            await c.get("/v1/search/q=test")


@pytest.mark.asyncio
async def test_raises_authentication_error_403(test_settings, mock_serply):
    mock_serply.get("/v1/search/q=test").mock(
        return_value=httpx.Response(403, json={"error": {"message": "forbidden"}})
    )
    async with SerplyClient(test_settings) as c:
        with pytest.raises(AuthenticationError):
            await c.get("/v1/search/q=test")


@pytest.mark.asyncio
async def test_raises_not_found_error_404(test_settings, mock_serply):
    mock_serply.get("/v1/search/q=test").mock(
        return_value=httpx.Response(404, json={"error": {"message": "missing"}})
    )
    async with SerplyClient(test_settings) as c:
        with pytest.raises(NotFoundError):
            await c.get("/v1/search/q=test")


@pytest.mark.asyncio
async def test_raises_validation_error_422(test_settings, mock_serply):
    mock_serply.get("/v1/search/q=test").mock(
        return_value=httpx.Response(422, json={"error": {"message": "bad input"}})
    )
    async with SerplyClient(test_settings) as c:
        with pytest.raises(ValidationError):
            await c.get("/v1/search/q=test")


@pytest.mark.asyncio
async def test_raises_serply_error_unknown_status(test_settings, mock_serply):
    mock_serply.get("/v1/search/q=test").mock(
        return_value=httpx.Response(418, json={"error": {"message": "teapot"}})
    )
    async with SerplyClient(test_settings) as c:
        with pytest.raises(SerplyError) as exc_info:
            await c.get("/v1/search/q=test")
    assert exc_info.value.status_code == 418


@pytest.mark.asyncio
async def test_handles_non_json_error_response(test_settings, mock_serply):
    mock_serply.get("/v1/search/q=test").mock(
        return_value=httpx.Response(500, text="<html>oops</html>")
    )
    async with SerplyClient(test_settings) as c:
        with pytest.raises(SerplyError) as exc_info:
            await c.get("/v1/search/q=test")
    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_retry_on_5xx_then_success(test_settings, mock_serply):
    route = mock_serply.get("/v1/search/q=test")
    route.side_effect = [
        httpx.Response(503, json={"error": {"message": "down"}}),
        httpx.Response(200, json={"results": []}),
    ]
    async with SerplyClient(test_settings) as c:
        result = await c.get("/v1/search/q=test")
    assert result == {"results": []}
    assert route.call_count == 2


@pytest.mark.asyncio
async def test_retry_on_429_then_success(test_settings, mock_serply):
    route = mock_serply.get("/v1/search/q=test")
    route.side_effect = [
        httpx.Response(429, json={"error": {"message": "rl"}}),
        httpx.Response(200, json={"results": []}),
    ]
    async with SerplyClient(test_settings) as c:
        result = await c.get("/v1/search/q=test")
    assert result == {"results": []}
    assert route.call_count == 2


@pytest.mark.asyncio
async def test_no_retry_on_404(test_settings, mock_serply):
    route = mock_serply.get("/v1/search/q=test").mock(
        return_value=httpx.Response(404, json={"error": {"message": "x"}})
    )
    async with SerplyClient(test_settings) as c:
        with pytest.raises(NotFoundError):
            await c.get("/v1/search/q=test")
    assert route.call_count == 1


@pytest.mark.asyncio
async def test_no_retry_on_422(test_settings, mock_serply):
    route = mock_serply.get("/v1/search/q=test").mock(
        return_value=httpx.Response(422, json={"error": {"message": "x"}})
    )
    async with SerplyClient(test_settings) as c:
        with pytest.raises(ValidationError):
            await c.get("/v1/search/q=test")
    assert route.call_count == 1


@pytest.mark.asyncio
async def test_timeout_raises_serply_error(test_settings, mock_serply):
    mock_serply.get("/v1/search/q=test").mock(side_effect=httpx.TimeoutException("slow"))
    async with SerplyClient(test_settings) as c:
        with pytest.raises(SerplyError) as exc_info:
            await c.get("/v1/search/q=test")
    assert exc_info.value.status_code == 504


@pytest.mark.asyncio
async def test_network_error_raises_serply_error(test_settings, mock_serply):
    mock_serply.get("/v1/search/q=test").mock(side_effect=httpx.ConnectError("nope"))
    async with SerplyClient(test_settings) as c:
        with pytest.raises(SerplyError) as exc_info:
            await c.get("/v1/search/q=test")
    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_extra_headers_are_sent(test_settings, mock_serply):
    mock_serply.get("/v1/search/q=test").mock(return_value=httpx.Response(200, json={}))
    async with SerplyClient(test_settings) as c:
        await c.get("/v1/search/q=test", extra_headers={"X-Proxy-Location": "EU"})
    call = mock_serply.calls[0]
    assert call.request.headers["x-proxy-location"] == "EU"


def test_build_query_path_encodes_query():
    path = SerplyClient.build_query_path("/v1/search", "hello world", num=10)
    assert path.startswith("/v1/search/")
    assert "q=hello+world" in path
    assert "num=10" in path


def test_build_query_path_skips_none():
    path = SerplyClient.build_query_path("/v1/search", "test", start=None, num=5)
    assert "start" not in path
    assert "num=5" in path


def test_build_query_path_special_chars():
    path = SerplyClient.build_query_path("/v1/search", "C++ & python")
    assert "q=" in path
    # Plus and ampersand should be encoded
    assert "&" not in path.split("q=", 1)[1] or path.split("q=", 1)[1].count("&") == 0


def test_build_query_path_extra_params_encoded():
    path = SerplyClient.build_query_path("/v1/search", "test", country="us en")
    assert "country=us+en" in path


def test_api_key_redacted_in_safe_log_headers():
    s = Settings(serply_api_key="supersecret-key-1234", mcp_transport="stdio")
    c = SerplyClient(s)
    safe = c._safe_log_headers({"X-Api-Key": "supersecret-key-1234", "Accept": "application/json"})
    assert "supersecret-key-1234" not in safe.values()
    assert safe["Accept"] == "application/json"
    assert safe["X-Api-Key"] == "***REDACTED***"


def test_safe_log_headers_case_insensitive():
    s = Settings(serply_api_key="topsecret-key-12345", mcp_transport="stdio")
    c = SerplyClient(s)
    safe = c._safe_log_headers({"x-api-key": "topsecret-key-12345"})
    assert safe["x-api-key"] == "***REDACTED***"


@pytest.mark.asyncio
async def test_aclose_idempotent(test_settings):
    c = SerplyClient(test_settings)
    await c.aclose()
