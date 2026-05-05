from __future__ import annotations

import pytest

from serply_mcp.client import SerplyClient
from serply_mcp.config import Settings
from serply_mcp.server import build_starlette_app, create_app, healthz


@pytest.mark.asyncio
async def test_create_app_registers_8_tools(test_settings):
    async with SerplyClient(test_settings) as client:
        mcp = create_app(test_settings, client)
        tools = await mcp.list_tools()
    names = {t.name for t in tools}
    assert names == {
        "google_search",
        "bing_search",
        "google_video_search",
        "google_news_search",
        "google_jobs_search",
        "google_scholar_search",
        "amazon_product_search",
        "scrape_url",
    }


@pytest.mark.asyncio
async def test_create_app_registers_usage_resource(test_settings):
    async with SerplyClient(test_settings) as client:
        mcp = create_app(test_settings, client)
        resources = await mcp.list_resources()
    uris = [str(r.uri) for r in resources]
    assert any("serply" in u and "usage" in u for u in uris)


@pytest.mark.asyncio
async def test_healthz_returns_ok():
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient

    app = Starlette(routes=[Route("/healthz", healthz, methods=["GET"])])
    client = TestClient(app)
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_build_starlette_app_raises_without_token():
    settings = Settings(
        serply_api_key="k",
        mcp_transport="stdio",
        mcp_auth_token=None,
    )
    client = SerplyClient(settings)
    with pytest.raises((RuntimeError, Exception)):
        build_starlette_app(settings, client)


@pytest.mark.asyncio
async def test_build_starlette_app_creates_valid_asgi(test_settings):
    import httpx

    client = SerplyClient(test_settings)
    app = build_starlette_app(test_settings, client)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        resp = await http.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_mcp_path_requires_auth(test_settings):
    import httpx

    client = SerplyClient(test_settings)
    app = build_starlette_app(test_settings, client)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        resp = await http.post("/mcp")
    assert resp.status_code == 401
