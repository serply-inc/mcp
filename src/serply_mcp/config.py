from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Settings:
    serply_api_key: str = ""
    serply_base_url: str = "https://api.serply.io"
    serply_timeout_seconds: float = 30.0
    serply_max_retries: int = 3
    mcp_transport: str = "stdio"
    mcp_http_host: str = "0.0.0.0"
    mcp_http_port: int = 8000
    mcp_http_path: str = "/mcp"
    mcp_rate_limit_per_minute: int = 60
    block_internal_urls: bool = True
    log_level: str = "INFO"


def get_settings() -> Settings:
    return Settings(
        serply_api_key=os.environ.get("SERPLY_API_KEY", ""),
        serply_base_url=os.environ.get("SERPLY_BASE_URL", "https://api.serply.io"),
        serply_timeout_seconds=float(os.environ.get("SERPLY_TIMEOUT_SECONDS", "30")),
        serply_max_retries=int(os.environ.get("SERPLY_MAX_RETRIES", "3")),
        mcp_transport=os.environ.get("MCP_TRANSPORT", "stdio"),
        mcp_http_host=os.environ.get("MCP_HTTP_HOST", "0.0.0.0"),
        mcp_http_port=int(os.environ.get("MCP_HTTP_PORT", "8000")),
        mcp_http_path=os.environ.get("MCP_HTTP_PATH", "/mcp"),
        mcp_rate_limit_per_minute=int(os.environ.get("MCP_RATE_LIMIT_PER_MINUTE", "60")),
        block_internal_urls=os.environ.get("BLOCK_INTERNAL_URLS", "true").lower() == "true",
        log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    )
