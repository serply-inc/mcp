"""Coverage for config validation, errors, models, and logging."""
from __future__ import annotations

import pytest

from serply_mcp.config import Settings, get_settings
from serply_mcp.errors import (
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    SerplyError,
    ValidationError,
    to_mcp_error,
)
from serply_mcp.logging import configure_logging, get_logger
from serply_mcp.models import (
    BingResponse,
    JobsResponse,
    NewsResponse,
    ProductResponse,
    ScrapeResponse,
    SearchResponse,
)

# Settings

def test_settings_defaults():
    s = Settings(serply_api_key="k")
    assert s.mcp_transport == "stdio"
    assert s.serply_base_url == "https://api.serply.io"
    assert s.block_internal_urls is True


def test_settings_http_transport():
    s = Settings(serply_api_key="k", mcp_transport="http")
    assert s.mcp_transport == "http"


def test_get_settings_returns_settings(monkeypatch):
    monkeypatch.setenv("SERPLY_API_KEY", "abc")
    monkeypatch.setenv("MCP_TRANSPORT", "stdio")
    s = get_settings()
    assert s.serply_api_key == "abc"
    assert s.mcp_transport == "stdio"


def test_get_settings_missing_api_key(monkeypatch):
    monkeypatch.delenv("SERPLY_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SERPLY_API_KEY"):
        get_settings()


# Errors

def test_serply_error_default_status():
    e = SerplyError("oops")
    assert e.status_code == 500
    assert str(e) == "oops"


def test_rate_limit_error_message_includes_counts():
    e = RateLimitError(remaining=0, limit=100)
    assert "limit=100" in str(e)
    assert "remaining=0" in str(e)
    assert e.rate_limit_remaining == 0
    assert e.rate_limit_limit == 100


def test_rate_limit_error_no_counts():
    e = RateLimitError()
    assert "rate limit exceeded" in str(e).lower()
    assert e.rate_limit_limit is None


def test_authentication_error_default_message():
    e = AuthenticationError()
    assert "API key" in str(e)
    assert e.status_code == 401


def test_not_found_error_default():
    e = NotFoundError()
    assert e.status_code == 404


def test_validation_error_status():
    e = ValidationError("bad")
    assert e.status_code == 422


def test_to_mcp_error_maps_known_codes():
    e = AuthenticationError()
    out = to_mcp_error(e)
    assert out.code == -32001

    e2 = NotFoundError()
    assert to_mcp_error(e2).code == -32002

    e3 = RateLimitError()
    assert to_mcp_error(e3).code == -32003

    e4 = ValidationError("x")
    assert to_mcp_error(e4).code == -32602


def test_to_mcp_error_unknown_code_falls_back():
    e = SerplyError("weird", status_code=418)
    out = to_mcp_error(e)
    assert out.code == -32603


# Models

def test_search_response_defaults():
    r = SearchResponse()
    assert r.results == []
    assert r.total is None


def test_bing_response_defaults():
    r = BingResponse()
    assert r.ads == []
    assert r.shopping_ads == []


def test_jobs_response_defaults():
    r = JobsResponse()
    assert r.jobs == []


def test_news_response_defaults():
    r = NewsResponse()
    assert r.feed.entries == []


def test_product_response_defaults():
    r = ProductResponse()
    assert r.products == []


def test_scrape_response_defaults():
    r = ScrapeResponse()
    assert r.content == ""
    assert r.response_type == "markdown"


# Logging

def test_configure_logging_debug():
    configure_logging(level="DEBUG")
    log = get_logger("test")
    log.info("hello")


def test_configure_logging_info():
    configure_logging(level="INFO")
    log = get_logger("test")
    log.info("hello")


def test_configure_logging_invalid_level_falls_back():
    configure_logging(level="WHATEVER")
