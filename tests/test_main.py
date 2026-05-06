from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from serply_mcp.config import Settings


def test_main_stdio_dispatch(monkeypatch):
    from serply_mcp import __main__ as main_mod

    called = {}

    def fake_stdio(settings):
        called["stdio"] = True

    def fake_http(settings):
        called["http"] = True

    monkeypatch.setattr(main_mod, "_run_stdio", fake_stdio)
    monkeypatch.setattr(main_mod, "_run_http", fake_http)

    fake_settings = Settings(serply_api_key="k", mcp_transport="stdio")
    monkeypatch.setattr(main_mod, "get_settings", lambda: fake_settings)

    main_mod.main()
    assert called.get("stdio") is True
    assert "http" not in called


def test_main_http_dispatch(monkeypatch):
    from serply_mcp import __main__ as main_mod

    called = {}

    def fake_stdio(settings):
        called["stdio"] = True

    def fake_http(settings):
        called["http"] = True

    monkeypatch.setattr(main_mod, "_run_stdio", fake_stdio)
    monkeypatch.setattr(main_mod, "_run_http", fake_http)

    fake_settings = Settings(
        serply_api_key="k",
        mcp_transport="http",
        mcp_api_key="z" * 32,
    )
    monkeypatch.setattr(main_mod, "get_settings", lambda: fake_settings)

    main_mod.main()
    assert called.get("http") is True
    assert "stdio" not in called


def test_run_stdio_invokes_event_loop(stdio_settings):
    # SerplyClient and create_app are imported locally inside _run_stdio,
    # so patch at their source module locations.
    mock_mcp = AsyncMock()
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("serply_mcp.client.SerplyClient", return_value=mock_client), \
         patch("serply_mcp.server.create_app", return_value=mock_mcp):
        from serply_mcp.__main__ import _run_stdio
        _run_stdio(stdio_settings)

    mock_mcp.run_stdio_async.assert_awaited_once()


def test_run_http_calls_uvicorn_with_correct_args(test_settings):
    mock_client = MagicMock()
    mock_app = MagicMock()

    with patch("serply_mcp.client.SerplyClient", return_value=mock_client), \
         patch("serply_mcp.server.build_starlette_app", return_value=mock_app), \
         patch("uvicorn.run") as mock_uvicorn_run:
        from serply_mcp.__main__ import _run_http
        _run_http(test_settings)

    mock_uvicorn_run.assert_called_once()
    args, kwargs = mock_uvicorn_run.call_args
    assert args[0] is mock_app
    assert kwargs["host"] == test_settings.mcp_http_host
    assert kwargs["port"] == test_settings.mcp_http_port
    assert kwargs["log_config"] is None
    assert kwargs["access_log"] is False
