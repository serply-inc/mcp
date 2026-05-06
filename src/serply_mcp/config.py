from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Settings:
    serply_api_key: str
    serply_base_url: str = "https://api.serply.io"
    serply_timeout_seconds: float = 30.0
    serply_max_retries: int = 3
    mcp_transport: str = "stdio"
    mcp_http_host: str = "0.0.0.0"
    mcp_http_port: int = 8000
    mcp_http_path: str = "/mcp"
    mcp_api_key: str | None = None
    mcp_rate_limit_per_minute: int = 60
    block_internal_urls: bool = True
    log_level: str = "INFO"

    def __post_init__(self) -> None:
        if self.mcp_api_key is not None and len(self.mcp_api_key) < 32:
            raise ValueError("mcp_api_key must be at least 32 characters")
        if self.mcp_transport == "http" and not self.mcp_api_key:
            raise ValueError("mcp_api_key is required when mcp_transport='http'")


def get_settings() -> Settings:
    api_key = os.environ.get("SERPLY_API_KEY", "")
    if not api_key:
        raise RuntimeError("SERPLY_API_KEY environment variable is required")

    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    mcp_api_key = os.environ.get("MCP_API_KEY") or None

    if transport == "http" and not mcp_api_key:
        raise RuntimeError("MCP_API_KEY is required when MCP_TRANSPORT=http")
    if mcp_api_key and len(mcp_api_key) < 32:
        raise RuntimeError("MCP_API_KEY must be at least 32 characters")

    return Settings(
        serply_api_key=api_key,
        serply_base_url=os.environ.get("SERPLY_BASE_URL", "https://api.serply.io"),
        serply_timeout_seconds=float(os.environ.get("SERPLY_TIMEOUT_SECONDS", "30")),
        serply_max_retries=int(os.environ.get("SERPLY_MAX_RETRIES", "3")),
        mcp_transport=transport,
        mcp_http_host=os.environ.get("MCP_HTTP_HOST", "0.0.0.0"),
        mcp_http_port=int(os.environ.get("MCP_HTTP_PORT", "8000")),
        mcp_http_path=os.environ.get("MCP_HTTP_PATH", "/mcp"),
        mcp_api_key=mcp_api_key,
        mcp_rate_limit_per_minute=int(os.environ.get("MCP_RATE_LIMIT_PER_MINUTE", "60")),
        block_internal_urls=os.environ.get("BLOCK_INTERNAL_URLS", "true").lower() == "true",
        log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    )
