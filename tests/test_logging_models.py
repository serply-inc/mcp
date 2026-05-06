from __future__ import annotations

import logging

import pytest

# logging.py

def test_configure_logging_sets_level():
    from serply_mcp.logging import configure_logging, get_logger
    configure_logging(level="DEBUG")
    log = get_logger("test_debug")
    log.debug("test_event")


def test_configure_logging_info_level():
    from serply_mcp.logging import configure_logging, get_logger
    configure_logging(level="INFO")
    log = get_logger("test_info")
    log.info("test_event")


def test_configure_logging_sets_root_level():
    from serply_mcp.logging import configure_logging
    configure_logging(level="WARNING")
    assert logging.getLogger().level == logging.WARNING


def test_get_logger_returns_logger():
    from serply_mcp.logging import get_logger
    log = get_logger("mymodule")
    assert log is not None


# models.py

def test_search_result_defaults():
    from serply_mcp.models import SearchResult
    r = SearchResult()
    assert r.title == ""
    assert r.link == ""
    assert r.description == ""


def test_search_response_defaults():
    from serply_mcp.models import SearchResponse
    r = SearchResponse()
    assert r.results == []
    assert r.total is None
    assert r.answer is None


def test_search_response_with_data():
    from serply_mcp.models import SearchResponse, SearchResult
    r = SearchResponse(
        results=[SearchResult(title="T", link="https://x.com", description="D")],
        total=1,
        answer="yes",
    )
    assert len(r.results) == 1
    assert r.results[0].title == "T"


def test_bing_response_defaults():
    from serply_mcp.models import BingResponse
    r = BingResponse()
    assert r.results == []
    assert r.ads == []


def test_job_description_defaults():
    from serply_mcp.models import JobDescription
    d = JobDescription()
    assert d.is_remote is False
    assert d.is_hybrid is False
    assert d.perks == []


def test_jobs_response_defaults():
    from serply_mcp.models import JobsResponse
    r = JobsResponse()
    assert r.jobs == []


def test_news_response_defaults():
    from serply_mcp.models import NewsFeed, NewsResponse
    r = NewsResponse()
    assert isinstance(r.feed, NewsFeed)
    assert r.entities == []


def test_news_feed_entries():
    from serply_mcp.models import NewsEntry, NewsFeed
    f = NewsFeed(entries=[NewsEntry(title="Headline", link="https://news.com")])
    assert len(f.entries) == 1
    assert f.entries[0].title == "Headline"


def test_product_result_defaults():
    from serply_mcp.models import ProductResult
    p = ProductResult()
    assert p.bestseller is False
    assert p.prime is False
    assert p.is_sponsor is False


def test_product_response_defaults():
    from serply_mcp.models import ProductResponse
    r = ProductResponse()
    assert r.products == []
    assert r.ads == []


def test_scrape_response_defaults():
    from serply_mcp.models import ScrapeResponse
    r = ScrapeResponse()
    assert r.content == ""
    assert r.response_type == "markdown"


def test_proxy_locations_tuple():
    from serply_mcp.models import PROXY_LOCATIONS
    assert "US" in PROXY_LOCATIONS
    assert "GB" in PROXY_LOCATIONS
    assert len(PROXY_LOCATIONS) == 14


# config.py edge cases

def test_settings_rejects_short_token():
    from serply_mcp.config import Settings
    with pytest.raises(ValueError, match="32"):
        Settings(
            serply_api_key="key",
            mcp_transport="http",
            mcp_api_key="short",
        )


def test_settings_rejects_http_without_token():
    from serply_mcp.config import Settings
    with pytest.raises(ValueError):
        Settings(
            serply_api_key="key",
            mcp_transport="http",
            mcp_api_key=None,
        )


def test_settings_allows_stdio_without_token():
    from serply_mcp.config import Settings
    s = Settings(serply_api_key="key", mcp_transport="stdio")
    assert s.mcp_api_key is None


def test_settings_allows_exact_32_char_token():
    from serply_mcp.config import Settings
    s = Settings(
        serply_api_key="key",
        mcp_transport="http",
        mcp_api_key="a" * 32,
    )
    assert len(s.mcp_api_key) == 32  # type: ignore[arg-type]


# errors.py

def test_to_mcp_error_maps_429():
    from serply_mcp.errors import RateLimitError, to_mcp_error
    err = RateLimitError(remaining=0, limit=100)
    mcp_err = to_mcp_error(err)
    assert mcp_err.code == -32003


def test_to_mcp_error_maps_401():
    from serply_mcp.errors import AuthenticationError, to_mcp_error
    err = AuthenticationError()
    mcp_err = to_mcp_error(err)
    assert mcp_err.code == -32001


def test_to_mcp_error_maps_404():
    from serply_mcp.errors import NotFoundError, to_mcp_error
    err = NotFoundError()
    mcp_err = to_mcp_error(err)
    assert mcp_err.code == -32002


def test_to_mcp_error_maps_unknown_to_internal():
    from serply_mcp.errors import SerplyError, to_mcp_error
    err = SerplyError("oops", status_code=503)
    mcp_err = to_mcp_error(err)
    assert mcp_err.code == -32603


def test_rate_limit_error_message_without_headers():
    from serply_mcp.errors import RateLimitError
    err = RateLimitError()
    assert "rate limit" in str(err).lower()


def test_rate_limit_error_message_with_headers():
    from serply_mcp.errors import RateLimitError
    err = RateLimitError(remaining=5, limit=100)
    assert "100" in str(err)
    assert "5" in str(err)
