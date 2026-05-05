from __future__ import annotations

import asyncio

from serply_mcp.config import Settings, get_settings
from serply_mcp.logging import configure_logging, get_logger


def main() -> None:
    settings = get_settings()
    configure_logging(level=settings.log_level)
    log = get_logger("serply_mcp")
    log.info("starting serply-mcp transport=%s", settings.mcp_transport)

    if settings.mcp_transport == "stdio":
        _run_stdio(settings)
    else:
        _run_http(settings)


def _run_stdio(settings: Settings) -> None:
    from serply_mcp.client import SerplyClient
    from serply_mcp.server import create_app

    async def _main() -> None:
        async with SerplyClient(settings) as client:
            mcp = create_app(settings, client)
            await mcp.run_stdio_async()

    asyncio.run(_main())


def _run_http(settings: Settings) -> None:
    import uvicorn

    from serply_mcp.client import SerplyClient
    from serply_mcp.server import build_starlette_app

    client = SerplyClient(settings)
    app = build_starlette_app(settings, client)
    uvicorn.run(
        app,
        host=settings.mcp_http_host,
        port=settings.mcp_http_port,
        log_config=None,
        access_log=False,
    )


if __name__ == "__main__":
    main()
