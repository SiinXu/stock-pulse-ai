"""Thin service handlers and safe asynchronous analysis submission."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.mcp_server.config import ALL_MCP_SCOPES, McpServerConfig
from src.mcp_server.errors import McpBusyError
from src.mcp_server.handlers import McpToolHandlers
from src.mcp_server.tools import call_tool
from src.services.analysis_submission_service import (
    AnalysisSubmissionCommand,
    AnalysisSubmissionResult,
)


def _config(**overrides) -> McpServerConfig:
    values = {
        "enabled": True,
        "transport": "stdio",
        "stdio_scopes": ALL_MCP_SCOPES,
        "analysis_max_stocks": 2,
    }
    values.update(overrides)
    return McpServerConfig(**values)


def test_read_handlers_forward_already_validated_values() -> None:
    stock = MagicMock()
    stock.get_realtime_quote.return_value = {"stock_code": "AAPL", "current_price": 1}
    stock.get_history_data.return_value = {"data": []}
    handlers = McpToolHandlers(config=_config(), stock_service=stock)
    assert handlers.get_realtime_quote(stock_code="AAPL")["stock_code"] == "AAPL"
    handlers.get_stock_history(stock_code="AAPL", period="daily", days=30)
    stock.get_realtime_quote.assert_called_once_with("AAPL")
    stock.get_history_data.assert_called_once_with("AAPL", period="daily", days=30)


def test_string_boolean_is_rejected_before_portfolio_service() -> None:
    portfolio = MagicMock()
    handlers = McpToolHandlers(config=_config(), portfolio_service=portfolio)
    with pytest.raises(Exception):
        call_tool(handlers, "get_portfolio_snapshot", {"include_realtime": "false"})
    portfolio.get_portfolio_snapshot.assert_not_called()


def test_busy_submission_never_calls_analysis_service() -> None:
    analysis = MagicMock()
    handlers = McpToolHandlers(
        config=_config(),
        analysis_submission_service=analysis,
        get_config=lambda: SimpleNamespace(),
        run_with_lock=lambda *args, **kwargs: False,
        security_audit=MagicMock(),
    )
    with pytest.raises(McpBusyError):
        handlers.trigger_analysis(stock_code="600519")
    analysis.submit.assert_not_called()


def test_trigger_submits_typed_async_request_under_global_lock() -> None:
    analysis = MagicMock()
    task = SimpleNamespace(task_id="t1", stock_code="600519", analysis_phase="auto")
    analysis.submit.return_value = AnalysisSubmissionResult((task,), ())
    lock_modes: list[bool] = []

    def fake_lock(runner, config, args, stock_codes, *, blocking=True):
        lock_modes.append(blocking)
        runner(config, args, stock_codes)
        return True

    audit = MagicMock()
    handlers = McpToolHandlers(
        config=_config(),
        analysis_submission_service=analysis,
        get_config=lambda: SimpleNamespace(name="cfg"),
        run_with_lock=fake_lock,
        security_audit=audit,
    )
    result = handlers.trigger_analysis(stock_code="600519")
    request = analysis.submit.call_args.args[0]
    assert isinstance(request, AnalysisSubmissionCommand)
    assert request.stock_codes == ("600519",)
    assert analysis.submit.call_args.kwargs["security_audit"] is audit
    assert lock_modes == [False]
    assert result["task_id"] == "t1"


def test_trigger_rejects_more_than_configured_cost_budget() -> None:
    handlers = McpToolHandlers(
        config=_config(analysis_max_stocks=2),
        analysis_submission_service=MagicMock(),
        run_with_lock=lambda *args, **kwargs: True,
        security_audit=MagicMock(),
    )
    with pytest.raises(ValueError, match="At most 2"):
        handlers.trigger_analysis(stock_codes=["AAPL", "MSFT", "NVDA"])


def test_trigger_does_not_expose_synchronous_analysis() -> None:
    handlers = McpToolHandlers(config=_config(), security_audit=MagicMock())
    with pytest.raises(ValueError, match="async_mode=true"):
        handlers.trigger_analysis(stock_code="AAPL", async_mode=False)
