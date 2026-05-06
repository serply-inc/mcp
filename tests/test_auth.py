from __future__ import annotations

import unittest.mock as mock

import httpx
import pytest

from serply_mcp.auth import ApiKeyMiddleware, RateLimiter, check_ssrf

# RateLimiter

def test_rate_limiter_allows_under_limit():
    rl = RateLimiter(5)
    for _ in range(5):
        assert rl.is_allowed("tok") is True


def test_rate_limiter_blocks_over_limit():
    rl = RateLimiter(2)
    assert rl.is_allowed("tok") is True
    assert rl.is_allowed("tok") is True
    assert rl.is_allowed("tok") is False


def test_rate_limiter_per_token():
    rl = RateLimiter(1)
    assert rl.is_allowed("a") is True
    assert rl.is_allowed("b") is True
    assert rl.is_allowed("a") is False
    assert rl.is_allowed("b") is False


def test_rate_limiter_evicts_old_entries():
    rl = RateLimiter(2)
    rl.is_allowed("tok")
    rl.is_allowed("tok")
    assert rl.is_allowed("tok") is False
    dq = rl._windows["tok"]
    dq.clear()
    assert rl.is_allowed("tok") is True


# SSRF

@pytest.mark.asyncio
async def test_check_ssrf_blocks_loopback_ipv4():
    with pytest.raises(ValueError, match="private"):
        await check_ssrf("http://127.0.0.1/secret")


@pytest.mark.asyncio
async def test_check_ssrf_blocks_loopback_ipv6():
    with pytest.raises(ValueError, match="private"):
        await check_ssrf("http://[::1]/secret")


@pytest.mark.asyncio
async def test_check_ssrf_blocks_private_10():
    with mock.patch("serply_mcp.auth._resolve", return_value=["10.0.0.1"]), pytest.raises(ValueError, match="private"):
        await check_ssrf("http://internal.example.com/data")


@pytest.mark.asyncio
async def test_check_ssrf_blocks_private_172():
    with mock.patch("serply_mcp.auth._resolve", return_value=["172.16.0.5"]), pytest.raises(ValueError, match="private"):
        await check_ssrf("http://internal.example.com/data")


@pytest.mark.asyncio
async def test_check_ssrf_blocks_private_192_168():
    with mock.patch("serply_mcp.auth._resolve", return_value=["192.168.1.1"]), pytest.raises(ValueError, match="private"):
        await check_ssrf("http://router.local/admin")


@pytest.mark.asyncio
async def test_check_ssrf_blocks_metadata():
    with mock.patch("serply_mcp.auth._resolve", return_value=["169.254.169.254"]), pytest.raises(ValueError):
        await check_ssrf("http://metadata.server/credentials")


@pytest.mark.asyncio
async def test_check_ssrf_blocks_cgnat():
    with mock.patch("serply_mcp.auth._resolve", return_value=["100.64.0.1"]), pytest.raises(ValueError, match="private"):
        await check_ssrf("http://cgnat.example.com/")


@pytest.mark.asyncio
async def test_check_ssrf_blocks_ipv6_link_local():
    with mock.patch("serply_mcp.auth._resolve", return_value=["fe80::1"]), pytest.raises(ValueError, match="private"):
        await check_ssrf("http://link-local.example/")


@pytest.mark.asyncio
async def test_check_ssrf_blocks_ipv6_unique_local():
    with mock.patch("serply_mcp.auth._resolve", return_value=["fc00::1"]), pytest.raises(ValueError, match="private"):
        await check_ssrf("http://ula.example/")


@pytest.mark.asyncio
async def test_check_ssrf_allows_public():
    with mock.patch("serply_mcp.auth._resolve", return_value=["93.184.216.34"]):
        await check_ssrf("http://example.com/page")


@pytest.mark.asyncio
async def test_check_ssrf_rejects_file_scheme():
    with pytest.raises(ValueError, match="Scheme"):
        await check_ssrf("file:///etc/passwd")


@pytest.mark.asyncio
async def test_check_ssrf_rejects_ftp_scheme():
    with pytest.raises(ValueError, match="Scheme"):
        await check_ssrf("ftp://example.com/")


@pytest.mark.asyncio
async def test_check_ssrf_rejects_gopher_scheme():
    with pytest.raises(ValueError, match="Scheme"):
        await check_ssrf("gopher://example.com/")


@pytest.mark.asyncio
async def test_check_ssrf_no_hostname():
    with pytest.raises(ValueError, match="hostname"):
        await check_ssrf("http:///nopath")


@pytest.mark.asyncio
async def test_check_ssrf_unresolvable_hostname():
    with mock.patch("serply_mcp.auth._resolve", side_effect=OSError("nope")), pytest.raises(ValueError, match="resolve"):
        await check_ssrf("http://nonexistent-host-xxx.example.com/")


@pytest.mark.asyncio
async def test_check_ssrf_resolve_real_localhost():
    from serply_mcp.auth import _resolve
    addrs = await _resolve("localhost")
    assert any(a in ("127.0.0.1", "::1") for a in addrs)


# ApiKeyMiddleware

async def _ok_app(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"OK"})


@pytest.mark.asyncio
async def test_middleware_allows_health_check():
    rl = RateLimiter(60)
    app = ApiKeyMiddleware(_ok_app, token="x" * 32, mcp_path="/mcp", rate_limiter=rl)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/healthz")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_middleware_passes_through_non_mcp_paths():
    rl = RateLimiter(60)
    app = ApiKeyMiddleware(_ok_app, token="x" * 32, mcp_path="/mcp", rate_limiter=rl)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/something-else")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_middleware_rejects_missing_api_key():
    rl = RateLimiter(60)
    app = ApiKeyMiddleware(_ok_app, token="x" * 32, mcp_path="/mcp", rate_limiter=rl)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post("/mcp")
    assert resp.status_code == 401
    assert resp.headers.get("www-authenticate") == "ApiKey"


@pytest.mark.asyncio
async def test_middleware_rejects_wrong_api_key():
    rl = RateLimiter(60)
    app = ApiKeyMiddleware(_ok_app, token="x" * 32, mcp_path="/mcp", rate_limiter=rl)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post("/mcp", headers={"X-Api-Key": "wrong"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_middleware_accepts_correct_api_key():
    rl = RateLimiter(60)
    token = "x" * 32
    app = ApiKeyMiddleware(_ok_app, token=token, mcp_path="/mcp", rate_limiter=rl)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post("/mcp", headers={"X-Api-Key": token})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_middleware_rate_limits():
    rl = RateLimiter(2)
    token = "x" * 32
    app = ApiKeyMiddleware(_ok_app, token=token, mcp_path="/mcp", rate_limiter=rl)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r1 = await c.post("/mcp", headers={"X-Api-Key": token})
        r2 = await c.post("/mcp", headers={"X-Api-Key": token})
        r3 = await c.post("/mcp", headers={"X-Api-Key": token})
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429


@pytest.mark.asyncio
async def test_middleware_passes_lifespan_through():
    received = []

    async def lifespan_app(scope, receive, send):
        received.append(scope["type"])
        await send({"type": "lifespan.startup.complete"})

    rl = RateLimiter(60)
    app = ApiKeyMiddleware(lifespan_app, token="x" * 32, mcp_path="/mcp", rate_limiter=rl)
    sent = []

    async def receive():
        return {"type": "lifespan.startup"}

    async def send(msg):
        sent.append(msg)

    await app({"type": "lifespan"}, receive, send)
    assert received == ["lifespan"]
    assert sent[0]["type"] == "lifespan.startup.complete"
