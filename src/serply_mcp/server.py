from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from serply_mcp.auth import ApiKeyMiddleware, RateLimiter
from serply_mcp.client import SerplyClient
from serply_mcp.config import Settings
from serply_mcp.tools import register_tools

logger = logging.getLogger(__name__)


def create_app(settings: Settings, client: SerplyClient) -> FastMCP:
    mcp = FastMCP(
        name="serply-mcp-server",
        instructions=(
            "Real-time web search and scraping via Serply.io. "
            "Tools: google_search, bing_search, google_video_search, "
            "google_news_search, google_jobs_search, google_scholar_search, "
            "amazon_product_search, scrape_url."
        ),
        host=settings.mcp_http_host,
        port=settings.mcp_http_port,
        streamable_http_path=settings.mcp_http_path,
    )
    register_tools(mcp, client, settings)
    return mcp


async def healthz(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


def build_starlette_app(settings: Settings, client: SerplyClient) -> Starlette:
    if not settings.mcp_api_key:
        raise RuntimeError("MCP_API_KEY is required for HTTP transport")

    mcp = create_app(settings, client)
    mcp_asgi = mcp.streamable_http_app()

    rate_limiter = RateLimiter(settings.mcp_rate_limit_per_minute)
    authed_mcp = ApiKeyMiddleware(
        app=mcp_asgi,
        token=settings.mcp_api_key,
        mcp_path=settings.mcp_http_path,
        rate_limiter=rate_limiter,
    )

    app = Starlette(
        routes=[Route("/healthz", healthz, methods=["GET"])],
        lifespan=mcp_asgi.router.lifespan_context,
    )
    app.mount("/", authed_mcp)
    return app
