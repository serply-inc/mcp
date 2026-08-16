"""Tests for all 13 Serply MCP tools (tools.py)."""
from __future__ import annotations

import unittest.mock as mock

import httpx
import pytest
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


def _unwrap_structured(result):
    """The structured half of a FastMCP (content, structured) result.

    Every other tool renders a string and is asserted on with `in`, so _unwrap
    takes the first element. google_maps_search is the one tool that returns a
    dict, and its assertions index into that dict, so it needs the second.
    Merging the Maps branch brought a version of _unwrap that returned the
    structured half for everything, which broke all the string assertions.
    """
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


# ── google_maps_search ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_google_maps_search_path_and_response(test_settings, mock_serply):
    mock_serply.get(url__regex=r".*/v1/maps/search/.*").mock(
        return_value=httpx.Response(
            200,
            json={
                "search_engine": "google_maps",
                "query": "personal injury lawyer chicago",
                "places": [
                    {
                        "position": 1,
                        "name": "Example Law",
                        "data_id": "0xabc:0xdef",
                        "place_id": "ChIJexample",
                        "website": "https://example.com",
                        "latitude": 41.88,
                        "longitude": -87.63,
                    }
                ],
                "result_count": 1,
                "metadata": {"transport": "direct"},
            },
        )
    )
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        result = _unwrap_structured(
            await mcp.call_tool(
                "google_maps_search",
                {
                    "query": "personal injury lawyer chicago",
                    "num": 40,
                    "hl": "en",
                    "gl": "US",
                },
            )
        )

    request_url = str(mock_serply.calls[0].request.url)
    assert "/v1/maps/search/personal%20injury%20lawyer%20chicago" in request_url
    assert "num=40" in request_url
    assert "hl=en" in request_url
    assert "gl=us" in request_url
    assert result["places"][0]["place_id"] == "ChIJexample"
    assert result["metadata"]["transport"] == "direct"
    assert result["summary"] == (
        "Found 1 Google Maps places for 'personal injury lawyer chicago'"
    )


@pytest.mark.asyncio
async def test_google_maps_search_tool_error(test_settings, mock_serply):
    mock_serply.get(url__regex=r".*/v1/maps/search/.*").mock(
        return_value=httpx.Response(
            502,
            json={"error": {"message": "maps unavailable"}},
        )
    )
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        with pytest.raises(ToolError):
            await mcp.call_tool("google_maps_search", {"query": "coffee chicago"})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "arguments",
    [
        {"query": "coffee chicago", "num": 0},
        {"query": "coffee chicago", "num": 201},
        {"query": "coffee chicago", "hl": "not_a_locale"},
        {"query": "coffee chicago", "gl": "USA"},
    ],
)
async def test_google_maps_search_validates_inputs(
    test_settings,
    mock_serply,
    arguments,
):
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        with pytest.raises(ToolError):
            await mcp.call_tool("google_maps_search", arguments)
    assert not mock_serply.calls


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


# ── reddit ────────────────────────────────────────────────────────────────────

def _listing(*children, after=None):
    return {"kind": "Listing", "data": {"after": after, "children": list(children)}}


_POST = {
    "kind": "t3",
    "data": {
        "id": "1vfemi1",
        "title": "Showcase Thread",
        "subreddit_name_prefixed": "r/Python",
        "author": "AutoModerator",
        "selftext": "Post all of your code/projects/showcases here",
        "score": 42,
        "num_comments": 118,
        "created_utc": 1755302400,
        "permalink": "/r/Python/comments/1vfemi1/showcase_thread/",
        "is_self": True,
        "stickied": True,
    },
}


@pytest.mark.asyncio
async def test_reddit_subreddit_posts(test_settings, mock_serply):
    mock_serply.get(url__regex=r".*/v1/reddit/subreddit/python.*").mock(
        return_value=httpx.Response(200, json=_listing(_POST, after="t3_1vpk70t"))
    )
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        result = _unwrap(await mcp.call_tool(
            "reddit_subreddit_posts", {"subreddit": "python", "limit": 10, "sort": "top", "t": "week"}
        ))

    request_url = str(mock_serply.calls[0].request.url)
    assert "/v1/reddit/subreddit/python?" in request_url
    assert "limit=10" in request_url
    assert "sort=top" in request_url
    assert "t=week" in request_url
    assert "Showcase Thread" in result
    assert "u/AutoModerator" in result
    assert "118 comments" in result
    assert "id: 1vfemi1" in result
    assert "https://www.reddit.com/r/Python/comments/1vfemi1/showcase_thread/" in result
    assert "after=t3_1vpk70t" in result


@pytest.mark.asyncio
async def test_reddit_subreddit_posts_strips_r_prefix_and_omits_unset_params(
    test_settings, mock_serply
):
    mock_serply.get(url__regex=r".*/v1/reddit/subreddit/.*").mock(
        return_value=httpx.Response(200, json=_listing())
    )
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        result = _unwrap(await mcp.call_tool("reddit_subreddit_posts", {"subreddit": "r/AskReddit"}))

    request_url = str(mock_serply.calls[0].request.url)
    assert "/v1/reddit/subreddit/AskReddit?" in request_url
    assert "&t=" not in request_url
    assert "after=" not in request_url
    assert "No posts found" in result


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "arguments",
    [
        {"subreddit": "../../v1/search"},
        {"subreddit": "a"},
        {"subreddit": "python", "limit": 101},
        {"subreddit": "python", "sort": "bogus"},
        {"subreddit": "python", "t": "decade"},
        {"subreddit": "python", "after": "t3_abc; drop"},
    ],
)
async def test_reddit_subreddit_posts_validates_inputs(test_settings, mock_serply, arguments):
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        with pytest.raises(ToolError):
            await mcp.call_tool("reddit_subreddit_posts", arguments)
    assert not mock_serply.calls


@pytest.mark.asyncio
async def test_reddit_subreddit_about(test_settings, mock_serply):
    mock_serply.get(url__regex=r".*/v1/reddit/subreddit/python/about.*").mock(
        return_value=httpx.Response(200, json={
            "kind": "t5",
            "data": {
                "display_name_prefixed": "r/Python",
                "title": "Python",
                "public_description": "News about the programming language Python.",
                "subscribers": 1400000,
                "active_user_count": 2100,
                "created_utc": 1201233135,
                "subreddit_type": "public",
                "url": "/r/Python/",
            },
        })
    )
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        result = _unwrap(await mcp.call_tool("reddit_subreddit_about", {"subreddit": "python"}))

    assert mock_serply.calls[0].request.url.path == "/v1/reddit/subreddit/python/about"
    assert "r/Python" in result
    assert "1,400,000 subscribers" in result
    assert "2,100 online" in result
    assert "News about the programming language Python." in result


@pytest.mark.asyncio
async def test_reddit_subreddit_about_error(test_settings, mock_serply):
    mock_serply.get(url__regex=r".*/v1/reddit/subreddit/.*/about.*").mock(
        return_value=httpx.Response(404, json={"error": {"message": "no such subreddit"}})
    )
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        with pytest.raises(ToolError):
            await mcp.call_tool("reddit_subreddit_about", {"subreddit": "nosuchsub"})


@pytest.mark.asyncio
async def test_reddit_user_posts_renders_posts_and_comments(test_settings, mock_serply):
    comment = {
        "kind": "t1",
        "data": {
            "author": "spez",
            "body": "Thanks for the feedback.",
            "score": 7,
            "created_utc": 1755302400,
            "link_title": "Announcement thread",
            "subreddit_name_prefixed": "r/announcements",
            "permalink": "/r/announcements/comments/abc/x/def/",
        },
    }
    mock_serply.get(url__regex=r".*/v1/reddit/user/spez.*").mock(
        return_value=httpx.Response(200, json=_listing(_POST, comment))
    )
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        result = _unwrap(await mcp.call_tool("reddit_user_posts", {"username": "u/spez"}))

    request_url = str(mock_serply.calls[0].request.url)
    assert "/v1/reddit/user/spez?" in request_url
    assert "sort=new" in request_url
    assert "Showcase Thread" in result
    assert "Comment on: Announcement thread" in result
    assert "Thanks for the feedback." in result


@pytest.mark.asyncio
async def test_reddit_user_posts_empty(test_settings, mock_serply):
    mock_serply.get(url__regex=r".*/v1/reddit/user/.*").mock(
        return_value=httpx.Response(200, json=_listing())
    )
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        result = _unwrap(await mcp.call_tool("reddit_user_posts", {"username": "ghost"}))
    assert "No activity found" in result


@pytest.mark.asyncio
async def test_reddit_post_comments_array_response(test_settings, mock_serply):
    """The comments endpoint answers with a two-element JSON array, not an object."""
    reply = {
        "kind": "t1",
        "data": {"author": "replier", "body": "Nested reply", "score": 3},
    }
    top = {
        "kind": "t1",
        "data": {
            "author": "commenter",
            "body": "Top level comment",
            "score": 12,
            "created_utc": 1755302400,
            "is_submitter": True,
            "replies": _listing(reply),
        },
    }
    more = {"kind": "more", "data": {"count": 5, "children": ["a", "b"]}}
    mock_serply.get(url__regex=r".*/v1/reddit/comments/1vfemi1.*").mock(
        return_value=httpx.Response(200, json=[_listing(_POST), _listing(top, more)])
    )
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        result = _unwrap(await mcp.call_tool("reddit_post_comments", {"post_id": "t3_1vfemi1"}))

    request_url = str(mock_serply.calls[0].request.url)
    assert "/v1/reddit/comments/1vfemi1?" in request_url
    assert "sort=confidence" in request_url
    assert "limit=" not in request_url
    assert "Showcase Thread" in result
    assert "u/commenter" in result
    assert "OP" in result
    assert "Top level comment" in result
    assert "  Nested reply" in result
    assert "5 more replies not loaded" in result


@pytest.mark.asyncio
async def test_reddit_post_comments_cached_envelope(test_settings, mock_serply):
    """What the API actually returns: the array wrapped as {"cached", "data"}.

    The array fixture above passed while production reported "No comments on
    this post." on every thread, so exercise the shape that ships.
    """
    top = {"kind": "t1", "data": {"author": "commenter", "body": "Top level comment"}}
    mock_serply.get(url__regex=r".*/v1/reddit/comments/.*").mock(
        return_value=httpx.Response(
            200, json={"cached": True, "data": [_listing(_POST), _listing(top)]}
        )
    )
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        result = _unwrap(await mcp.call_tool("reddit_post_comments", {"post_id": "1vfemi1"}))
    assert "Showcase Thread" in result
    assert "u/commenter" in result
    assert "Top level comment" in result
    assert "No comments on this post." not in result


@pytest.mark.asyncio
async def test_reddit_post_comments_respects_max_depth(test_settings, mock_serply):
    deep = {"kind": "t1", "data": {"author": "deep", "body": "Too deep"}}
    top = {"kind": "t1", "data": {"author": "top", "body": "Shallow", "replies": _listing(deep)}}
    mock_serply.get(url__regex=r".*/v1/reddit/comments/.*").mock(
        return_value=httpx.Response(200, json=[_listing(_POST), _listing(top)])
    )
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        result = _unwrap(await mcp.call_tool(
            "reddit_post_comments", {"post_id": "1vfemi1", "max_depth": 0}
        ))
    assert "Shallow" in result
    assert "Too deep" not in result


@pytest.mark.asyncio
async def test_reddit_post_comments_single_listing_and_no_comments(test_settings, mock_serply):
    """A single-object response (no array wrapper) still renders the post."""
    mock_serply.get(url__regex=r".*/v1/reddit/comments/.*").mock(
        return_value=httpx.Response(200, json=_listing(_POST))
    )
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        result = _unwrap(await mcp.call_tool("reddit_post_comments", {"post_id": "1vfemi1"}))
    assert "Showcase Thread" in result
    assert "No comments on this post." in result


@pytest.mark.asyncio
async def test_reddit_post_comments_error(test_settings, mock_serply):
    mock_serply.get(url__regex=r".*/v1/reddit/comments/.*").mock(
        return_value=httpx.Response(502, json={"error": {"message": "reddit proxy unavailable"}})
    )
    async with SerplyClient(test_settings) as client:
        mcp = _make_mcp(test_settings, client)
        with pytest.raises(ToolError):
            await mcp.call_tool("reddit_post_comments", {"post_id": "1vfemi1"})


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
