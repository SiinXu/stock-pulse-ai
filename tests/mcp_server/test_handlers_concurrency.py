# -*- coding: utf-8 -*-
"""Handler behavior: thin service calls and analysis concurrency protection."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.mcp_server.config import McpServerConfig
from src.mcp_server.errors import McpBusyError, map_exception_to_tool_result
from src.mcp_server.handlers import McpToolHandlers
from src.mcp_server.tools import call_tool


def _config(**overrides) -> McpServerConfig:
    base = dict(
        enabled=True,
        transport="stdio",
        host="127.0.0.1",
        port=8765,
        session_token=None,
        analysis_timeout_seconds=30,
        analysis_max_stocks=2,
    )
    base.update(overrides)
    return McpServerConfig(**base)


class TestReadHandlers:
    def test_quote_calls_stock_service(self):
        stock = MagicMock()
        stock.get_realtime_quote.return_value = {"stock_code": "AAPL", "current_price": 1}
        handlers = McpToolHandlers(config=_config(), stock_service=stock)
        result = handlers.get_realtime_quote(stock_code="AAPL")
        stock.get_realtime_quote.assert_called_once_with("AAPL")
        assert result["stock_code"] == "AAPL"

    def test_history_list_bounds_limit(self):
        history = MagicMock()
        history.get_history_list.return_value = {"total": 0, "items": []}
        handlers = McpToolHandlers(config=_config(), history_service=history)
        handlers.list_analysis_history(limit=9999, page=0)
        kwargs = history.get_history_list.call_args.kwargs
        assert kwargs["limit"] == 100
        assert kwargs["page"] == 1

    def test_portfolio_snapshot_defaults_no_realtime(self):
        portfolio = MagicMock()
        portfolio.get_portfolio_snapshot.return_value = {"accounts": []}
        handlers = McpToolHandlers(config=_config(), portfolio_service=portfolio)
        handlers.get_portfolio_snapshot()
        kwargs = portfolio.get_portfolio_snapshot.call_args.kwargs
        assert kwargs["include_realtime"] is False


class TestTriggerAnalysisConcurrency:
    def test_busy_when_lock_not_acquired(self):
        analysis = MagicMock()
        lock_calls = []

        def fake_lock(runner, config, args, stock_codes, *, blocking=True):
            lock_calls.append(blocking)
            return False

        handlers = McpToolHandlers(
            config=_config(),
            analysis_api_service=analysis,
            get_config=lambda: SimpleNamespace(),
            run_with_lock=fake_lock,
            security_audit=MagicMock(),
        )
        with pytest.raises(McpBusyError):
            handlers.trigger_analysis(stock_code="600519")
        analysis.trigger_analysis.assert_not_called()
        assert lock_calls == [False]

        tool_result = call_tool(
            handlers, "trigger_analysis", {"stock_code": "600519"}
        )
        assert tool_result["isError"] is True
        assert tool_result["structuredContent"]["error"] == "busy"

    def test_submits_when_lock_acquired(self):
        analysis = MagicMock()
        analysis.trigger_analysis.return_value = {
            "task_id": "t1",
            "status": "pending",
        }

        def fake_lock(runner, config, args, stock_codes, *, blocking=True):
            runner(config, args, stock_codes)
            return True

        handlers = McpToolHandlers(
            config=_config(),
            analysis_api_service=analysis,
            get_config=lambda: SimpleNamespace(name="cfg"),
            run_with_lock=fake_lock,
            security_audit=MagicMock(),
        )
        result = handlers.trigger_analysis(stock_code="600519")
        analysis.trigger_analysis.assert_called_once()
        assert result["task_id"] == "t1"

    def test_rejects_over_max_stocks(self):
        handlers = McpToolHandlers(
            config=_config(analysis_max_stocks=2),
            analysis_api_service=MagicMock(),
            run_with_lock=lambda *a, **k: True,
        )
        with pytest.raises(ValueError):
            handlers.trigger_analysis(stock_codes=["a", "b", "c"])

    def test_busy_error_maps_to_api_code(self):
        payload = map_exception_to_tool_result(McpBusyError())
        assert payload["structuredContent"]["error"] == "busy"


    def test_timeout_when_analysis_hangs(self):
        import time
        from src.mcp_server.config import McpServerConfig

        analysis = MagicMock()

        def slow_trigger(*args, **kwargs):
            time.sleep(2)
            return {"task_id": "late"}

        analysis.trigger_analysis.side_effect = slow_trigger

        def fake_lock(runner, config, args, stock_codes, *, blocking=True):
            runner(config, args, stock_codes)
            return True

        handlers = McpToolHandlers(
            config=McpServerConfig(
                enabled=True,
                transport="stdio",
                host="127.0.0.1",
                port=8765,
                session_token=None,
                analysis_timeout_seconds=1,
                analysis_max_stocks=2,
            ),
            analysis_api_service=analysis,
            get_config=lambda: SimpleNamespace(),
            run_with_lock=fake_lock,
            security_audit=MagicMock(),
        )
        tool_result = call_tool(
            handlers, "trigger_analysis", {"stock_code": "600519"}
        )
        assert tool_result["isError"] is True
        assert tool_result["structuredContent"]["error"] == "timeout"

