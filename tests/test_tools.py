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


def _unwrap(result) -> str:
    """Extract the text content from a FastMCP call_tool result."""
    content = result[0] if isinstance(result, tuple) else result
    return content[0].text if content else ""


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
    assert "A" in result
    assert "https://a.com" in result
    assert "42" in result
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
async def test_google_search_no_results(test_settings, mock_serply):
    mock_serply.get(url__regex=r".*/v1/search/.*").mock(return_value=httpx.Response(200, json={"results": []}))
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        result = _unwrap(await mcp.call_tool("google_search", {"query": "test"}))
    assert "No results" in result


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
        "ads": [{"title": "Ad Title", "displayUrl": "example.com › ads", "content": "Buy now"}],
        "shoppingAds": [],
    }))
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        result = _unwrap(await mcp.call_tool("bing_search", {"query": "bing test"}))
    assert "B" in result
    assert "https://b.com" in result
    assert "Ad Title" in result
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


@pytest.mark.asyncio
async def test_bing_search_shopping_ads(test_settings, mock_serply):
    mock_serply.get(url__regex=r".*/v1/b/search/.*").mock(return_value=httpx.Response(200, json={
        "results": [],
        "ads": [],
        "shoppingAds": [{"title": "Widget Pro", "price": "$9.99"}],
    }))
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        result = _unwrap(await mcp.call_tool("bing_search", {"query": "widget"}))
    assert "Widget Pro" in result
    assert "$9.99" in result


# ── google_video_search ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_google_video_search(test_settings, mock_serply):
    mock_serply.get(url__regex=r".*/v1/video/.*").mock(return_value=httpx.Response(200, json={
        "results": [{"title": "Python Tutorial", "link": "https://youtube.com/v", "description": "Learn Python"}],
        "total": 1,
    }))
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        result = _unwrap(await mcp.call_tool("google_video_search", {"query": "python tutorial"}))
    assert "Python Tutorial" in result
    assert "youtube.com" in result
    assert "/v1/video/" in str(mock_serply.calls[0].request.url)


@pytest.mark.asyncio
async def test_google_video_url_clean(test_settings, mock_serply):
    tracked = "https://www.youtube.com/watch%3Fv%3Dabc&sa=U&ved=XYZ&usg=ABC"
    mock_serply.get(url__regex=r".*/v1/video/.*").mock(return_value=httpx.Response(200, json={
        "results": [{"title": "V", "link": tracked}],
    }))
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        result = _unwrap(await mcp.call_tool("google_video_search", {"query": "test"}))
    assert "youtube.com/watch?v=abc" in result
    assert "&sa=" not in result


@pytest.mark.asyncio
async def test_google_video_tool_error(test_settings, mock_serply):
    mock_serply.get(url__regex=r".*/v1/video/.*").mock(return_value=httpx.Response(500, json={"error": {"message": "boom"}}))
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        with pytest.raises(ToolError):
            await mcp.call_tool("google_video_search", {"query": "test"})


# ── google_news_search ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_google_news_search_top_level_entries(test_settings, mock_serply):
    """Entries at top level (actual API response format)."""
    mock_serply.get(url__regex=r".*/v1/news/.*").mock(return_value=httpx.Response(200, json={
        "feed": {"title": "Google News"},
        "entries": [
            {"title": "Big News", "link": "https://news.com/1", "published": "Mon, 05 May 2026",
             "source": {"title": "Reuters"}},
        ],
    }))
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        result = _unwrap(await mcp.call_tool("google_news_search", {"query": "tech news"}))
    assert "Big News" in result
    assert "Reuters" in result
    assert "https://news.com/1" in result


@pytest.mark.asyncio
async def test_google_news_search_nested_entries_fallback(test_settings, mock_serply):
    """Fallback: entries nested inside feed object."""
    mock_serply.get(url__regex=r".*/v1/news/.*").mock(return_value=httpx.Response(200, json={
        "feed": {"entries": [{"title": "Nested News", "link": "https://news.com/2"}], "title": "feed"},
        "entities": [],
    }))
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        result = _unwrap(await mcp.call_tool("google_news_search", {"query": "tech news"}))
    assert "Nested News" in result


@pytest.mark.asyncio
async def test_google_news_search_with_ceid(test_settings, mock_serply):
    mock_serply.get(url__regex=r".*/v1/news/.*").mock(return_value=httpx.Response(200, json={"feed": {}, "entries": []}))
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        await mcp.call_tool("google_news_search", {"query": "brexit", "ceid": "GB:en"})
    assert "ceid=GB%3Aen" in str(mock_serply.calls[0].request.url)


# ── google_jobs_search ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_google_jobs_search(test_settings, mock_serply):
    mock_serply.get(url__regex=r".*/v1/job/search/.*").mock(return_value=httpx.Response(200, json={
        "jobs": [{
            "position": "Python Engineer",
            "link": "https://jobs.com/1",
            "description": {"employer": "Acme", "is_remote": True, "perks": []},
            "highlights": ["5+ years Python"],
            "metadata": {"location": "New York"},
        }],
    }))
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        result = _unwrap(await mcp.call_tool("google_jobs_search", {"query": "python engineer"}))
    assert "Python Engineer" in result
    assert "Acme" in result
    assert "Remote" in result
    assert "https://jobs.com/1" in result


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
        "results": [{"title": "Attention Is All You Need", "link": "https://arxiv.org/abs/1706.03762", "description": "Vaswani et al. 2017"}],
        "total": 1,
    }))
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        result = _unwrap(await mcp.call_tool("google_scholar_search", {"query": "transformer attention"}))
    assert "Attention Is All You Need" in result
    assert "arxiv.org" in result
    assert "Vaswani" in result


@pytest.mark.asyncio
async def test_google_scholar_tool_error(test_settings, mock_serply):
    mock_serply.get(url__regex=r".*/v1/scholar/.*").mock(return_value=httpx.Response(422, json={"error": {"message": "bad"}}))
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        with pytest.raises(ToolError):
            await mcp.call_tool("google_scholar_search", {"query": "test"})


# ── amazon_product_search ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_amazon_product_search_products_key(test_settings, mock_serply):
    """API returns products under 'products' key."""
    mock_serply.get(url__regex=r".*/v1/product/search/.*").mock(return_value=httpx.Response(200, json={
        "products": [{"title": "Widget", "price": "$9.99", "asin": "B001", "rating_stars": 4.5, "review_count": 100}],
        "ads": [],
    }))
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        result = _unwrap(await mcp.call_tool("amazon_product_search", {"query": "usb cable"}))
    assert "Widget" in result
    assert "$9.99" in result
    assert "B001" in result
    assert "4.5" in result


@pytest.mark.asyncio
async def test_amazon_product_search_results_key(test_settings, mock_serply):
    """API returns products under 'results' key (actual API response format)."""
    mock_serply.get(url__regex=r".*/v1/product/search/.*").mock(return_value=httpx.Response(200, json={
        "results": [{"title": "Cable", "price": "$4.99", "asin": "B002", "prime": True}],
    }))
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        result = _unwrap(await mcp.call_tool("amazon_product_search", {"query": "cable"}))
    assert "Cable" in result
    assert "$4.99" in result
    assert "Prime" in result


@pytest.mark.asyncio
async def test_amazon_product_search_empty(test_settings, mock_serply):
    mock_serply.get(url__regex=r".*/v1/product/search/.*").mock(return_value=httpx.Response(200, json={
        "results": [], "total": 0,
    }))
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        result = _unwrap(await mcp.call_tool("amazon_product_search", {"query": "test"}))
    assert "No products" in result


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
    assert "# Hello" in result
    assert "World" in result
    assert "example.com" in result
    assert "sha256:" in result


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
    assert "ok" in result


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
