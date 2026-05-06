from __future__ import annotations

import pytest
import respx

from serply_mcp.client import SerplyClient
from serply_mcp.config import Settings


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        serply_api_key="test-api-key-1234567890",
        mcp_transport="http",
        mcp_rate_limit_per_minute=60,
        block_internal_urls=True,
        log_level="DEBUG",
    )


@pytest.fixture
def stdio_settings() -> Settings:
    return Settings(
        serply_api_key="test-api-key-1234567890",
        mcp_transport="stdio",
        block_internal_urls=True,
        log_level="DEBUG",
    )


@pytest.fixture
def mock_serply():
    with respx.mock(base_url="https://api.serply.io", assert_all_called=False) as mock:
        yield mock


@pytest.fixture
async def client(test_settings: Settings):
    async with SerplyClient(test_settings) as c:
        yield c
