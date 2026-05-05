"""Tests for all 8 Serply MCP tools (tools.py)."""
from __future__ import annotations

import unittest.mock as mock

import httpx
import pytest
import respx

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from serply_mcp.client import SerplyClient
from serply_mcp.errors import RateLimitError
from serply_mcp.tools import register_tools


def _make_mcp(test_settings, client):
    mcp = FastMCP("test")
    register_tools(mcp, client, test_settings)
    return mcp


def _unwrap(result):
    """Handle FastMCP call_tool returning dict or (content, structured) tuple."""
    return result[1] if isinstance(result, tuple) else result


# ── google_search ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_google_search_path_and_headers(test_settings, mock_serply):
    mock_serply.get(url__regex=r".*/v1/search/.*").mock(return_value=httpx.Response(200, json={
        "results": [{"title": "A", "link": "https://a.com", "description": "d"}],
        "total": 1,
        "answer": "42",
    }))
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        result = _unwrap(await mcp.call_tool("google_search", {"query": "hello world", "num": 5}))
    assert len(result["results"]) == 1
    assert result["answer"] == "42"
    assert "hello+world" in str(mock_serply.calls[0].request.url)
    assert mock_serply.calls[0].request.headers["x-api-key"] == "test-api-key-1234567890"


@pytest.mark.asyncio
async def test_google_search_start_offset(test_settings, mock_serply):
    mock_serply.get(url__regex=r".*/v1/search/.*").mock(return_value=httpx.Response(200, json={"results": []}))
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        await mcp.call_tool("google_search", {"query": "test", "start": 20})
    assert "start=20" in str(mock_serply.calls[0].request.url)


@pytest.mark.asyncio
async def test_google_search_tool_error_on_failure(test_settings, mock_serply):
    mock_serply.get(url__regex=r".*/v1/search/.*").mock(return_value=httpx.Response(404, json={"error": {"message": "missing"}}))
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        with pytest.raises(ToolError):
            await mcp.call_tool("google_search", {"query": "test"})


# ── bing_search ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bing_search_path_and_response(test_settings, mock_serply):
    mock_serply.get(url__regex=r".*/v1/b/search/.*").mock(return_value=httpx.Response(200, json={
        "results": [{"title": "B", "link": "https://b.com", "description": "d"}],
        "ads": [{"title": "Ad"}],
        "shopping_ads": [],
    }))
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        result = _unwrap(await mcp.call_tool("bing_search", {"query": "bing test"}))
    assert len(result["results"]) == 1
    assert len(result["ads"]) == 1
    assert "bing+test" in str(mock_serply.calls[0].request.url)


@pytest.mark.asyncio
async def test_bing_search_rate_limit_error(test_settings, mock_serply):
    mock_serply.get(url__regex=r".*/v1/b/search/.*").mock(return_value=httpx.Response(
        429, json={"error": {"message": "rl"}},
        headers={"x-ratelimit-requests-limit": "10", "x-ratelimit-requests-remaining": "0"},
    ))
    async with SerplyClient(test_settings) as client:
        with pytest.raises(RateLimitError):
            await client.get("/v1/b/search/q=test")


# ── google_video_search ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_google_video_search(test_settings, mock_serply):
    mock_serply.get(url__regex=r".*/v1/video/.*").mock(return_value=httpx.Response(200, json={
        "results": [{"title": "V", "link": "https://youtube.com/v", "description": "d"}],
        "total": 1,
    }))
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        result = _unwrap(await mcp.call_tool("google_video_search", {"query": "python tutorial"}))
    assert len(result["results"]) == 1
    assert "/v1/video/" in str(mock_serply.calls[0].request.url)


@pytest.mark.asyncio
async def test_google_video_tool_error(test_settings, mock_serply):
    mock_serply.get(url__regex=r".*/v1/video/.*").mock(return_value=httpx.Response(500, json={"error": {"message": "boom"}}))
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        with pytest.raises(ToolError):
            await mcp.call_tool("google_video_search", {"query": "test"})


# ── google_news_search ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_google_news_search_basic(test_settings, mock_serply):
    mock_serply.get(url__regex=r".*/v1/news/.*").mock(return_value=httpx.Response(200, json={
        "feed": {"entries": [{"title": "N", "link": "https://news.com"}], "title": "feed"},
        "entities": [],
    }))
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        result = _unwrap(await mcp.call_tool("google_news_search", {"query": "tech news"}))
    assert len(result["feed"]["entries"]) == 1


@pytest.mark.asyncio
async def test_google_news_search_with_ceid(test_settings, mock_serply):
    mock_serply.get(url__regex=r".*/v1/news/.*").mock(return_value=httpx.Response(200, json={"feed": {}, "entities": []}))
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        await mcp.call_tool("google_news_search", {"query": "brexit", "ceid": "GB:en"})
    assert "ceid=GB%3Aen" in str(mock_serply.calls[0].request.url)


# ── google_jobs_search ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_google_jobs_search(test_settings, mock_serply):
    mock_serply.get(url__regex=r".*/v1/job/search/.*").mock(return_value=httpx.Response(200, json={
        "jobs": [{"position": "Engineer", "link": "https://jobs.com"}],
    }))
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        result = _unwrap(await mcp.call_tool("google_jobs_search", {"query": "python engineer"}))
    assert len(result["jobs"]) == 1


@pytest.mark.asyncio
async def test_google_jobs_tool_error(test_settings, mock_serply):
    mock_serply.get(url__regex=r".*/v1/job/search/.*").mock(return_value=httpx.Response(401, json={"error": {"message": "unauth"}}))
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        with pytest.raises(ToolError):
            await mcp.call_tool("google_jobs_search", {"query": "test"})


# ── google_scholar_search ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_google_scholar_search(test_settings, mock_serply):
    mock_serply.get(url__regex=r".*/v1/scholar/.*").mock(return_value=httpx.Response(200, json={
        "results": [{"title": "Paper", "link": "https://scholar.google.com"}],
        "total": 1,
    }))
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        result = _unwrap(await mcp.call_tool("google_scholar_search", {"query": "transformer attention"}))
    assert len(result["results"]) == 1


@pytest.mark.asyncio
async def test_google_scholar_tool_error(test_settings, mock_serply):
    mock_serply.get(url__regex=r".*/v1/scholar/.*").mock(return_value=httpx.Response(422, json={"error": {"message": "bad"}}))
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        with pytest.raises(ToolError):
            await mcp.call_tool("google_scholar_search", {"query": "test"})


# ── amazon_product_search ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_amazon_product_search(test_settings, mock_serply):
    mock_serply.get(url__regex=r".*/v1/product/search/.*").mock(return_value=httpx.Response(200, json={
        "products": [{"title": "Widget", "price": "$9.99", "asin": "B001"}],
        "ads": [],
    }))
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        result = _unwrap(await mcp.call_tool("amazon_product_search", {"query": "usb cable"}))
    assert len(result["products"]) == 1
    assert result["products"][0]["asin"] == "B001"


@pytest.mark.asyncio
async def test_amazon_product_tool_error(test_settings, mock_serply):
    mock_serply.get(url__regex=r".*/v1/product/search/.*").mock(return_value=httpx.Response(500, json={"error": {"message": "err"}}))
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        with pytest.raises(ToolError):
            await mcp.call_tool("amazon_product_search", {"query": "test"})


# ── scrape_url ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scrape_url_markdown(test_settings, mock_serply):
    mock_serply.post("/v1/request").mock(return_value=httpx.Response(200, json={
        "content": "# Hello\n\nWorld",
        "url": "https://example.com",
        "response_type": "markdown",
    }))
    with mock.patch("serply_mcp.tools.check_ssrf"):
        async with SerplyClient(test_settings) as client:
            mcp = _make_mcp(test_settings, client)
            result = _unwrap(await mcp.call_tool("scrape_url", {"url": "https://example.com"}))
    assert result["content"].startswith("# Hello")
    assert "content_hash" in result
    assert result["content_length"] == len("# Hello\n\nWorld")


@pytest.mark.asyncio
async def test_scrape_url_blocks_file_scheme(test_settings, mock_serply):
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        with pytest.raises(ToolError, match="Scheme"):
            await mcp.call_tool("scrape_url", {"url": "file:///etc/passwd"})


@pytest.mark.asyncio
async def test_scrape_url_blocks_loopback(test_settings, mock_serply):
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        with pytest.raises(ToolError, match="private"):
            await mcp.call_tool("scrape_url", {"url": "http://127.0.0.1/"})


@pytest.mark.asyncio
async def test_scrape_url_blocks_metadata(test_settings, mock_serply):
    with mock.patch("serply_mcp.auth._resolve", return_value=["169.254.169.254"]):
        async with SerplyClient(test_settings) as client:
            mcp = _make_mcp(test_settings, client)
            with pytest.raises(ToolError, match="private"):
                await mcp.call_tool("scrape_url", {"url": "http://metadata.example/"})


@pytest.mark.asyncio
async def test_scrape_url_blocks_private_10(test_settings, mock_serply):
    with mock.patch("serply_mcp.auth._resolve", return_value=["10.1.2.3"]):
        async with SerplyClient(test_settings) as client:
            mcp = _make_mcp(test_settings, client)
            with pytest.raises(ToolError, match="private"):
                await mcp.call_tool("scrape_url", {"url": "http://internal.example/"})


@pytest.mark.asyncio
async def test_scrape_url_ssrf_disabled(test_settings, mock_serply):
    settings_no_ssrf = test_settings.__class__(
        **{**test_settings.__dict__, "block_internal_urls": False}
    )
    mock_serply.post("/v1/request").mock(return_value=httpx.Response(200, json={
        "content": "ok", "url": "http://127.0.0.1/", "response_type": "markdown",
    }))
    async with SerplyClient(settings_no_ssrf) as client:
        mcp = _make_mcp(settings_no_ssrf, client)
        result = _unwrap(await mcp.call_tool("scrape_url", {"url": "http://127.0.0.1/"}))
    assert result["content"] == "ok"


@pytest.mark.asyncio
async def test_scrape_url_serply_error(test_settings, mock_serply):
    mock_serply.post("/v1/request").mock(return_value=httpx.Response(500, json={"error": {"message": "oops"}}))
    with mock.patch("serply_mcp.tools.check_ssrf"):
        async with SerplyClient(test_settings) as client:
            mcp = _make_mcp(test_settings, client)
            with pytest.raises(ToolError):
                await mcp.call_tool("scrape_url", {"url": "https://example.com"})


# ── usage resource ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_usage_resource_registered(test_settings):
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        resources = await mcp.list_resources()
    uris = [str(r.uri) for r in resources]
    assert any("serply" in u and "usage" in u for u in uris)
