"""Analysis-scope contracts for the opt-in Futu portfolio source."""

from types import SimpleNamespace
from unittest.mock import ANY, MagicMock, patch

import pytest

import main
from src.brokers.futu.portfolio import FutuPortfolioError


def _args(**overrides):
    values = {
        "portfolio": "futu",
        "workers": None,
        "force_run": False,
        "single_notify": False,
        "no_context_snapshot": True,
        "no_market_review": True,
        "dry_run": True,
        "no_notify": True,
        "schedule": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _config():
    return SimpleNamespace(
        stock_list=["STATIC"],
        refresh_stock_list=MagicMock(),
        trading_day_check_enabled=False,
        market_review_enabled=False,
        single_stock_notify=False,
        merge_email_notification=False,
        market_review_region="cn",
        daily_market_context_enabled=False,
        schedule_enabled=False,
        analysis_delay=0,
        backtest_enabled=False,
    )


def test_futu_scope_overrides_cli_and_preserves_empty_portfolio() -> None:
    config = _config()
    pipeline = MagicMock()
    pipeline.run.return_value = []

    with patch(
        "src.services.stock_list_parser.resolve_portfolio_stock_list",
        return_value=[],
    ) as resolve_portfolio, patch(
        "src.core.pipeline.StockAnalysisPipeline",
        return_value=pipeline,
    ), patch(
        "main._refresh_stock_index_cache_for_analysis",
    ), patch(
        "main._compute_trading_day_filter",
        return_value=([], None, False),
    ) as trading_filter, patch(
        "src.feishu_doc.FeishuDocManager",
    ):
        assert main.run_full_analysis(config, _args(), ["AAPL"]) is True

    resolve_portfolio.assert_called_once_with("futu")
    config.refresh_stock_list.assert_not_called()
    trading_filter.assert_called_once_with(config, ANY, [])
    pipeline.run.assert_not_called()


def test_futu_scope_failure_propagates_for_runtime_scheduler() -> None:
    config = _config()
    error = FutuPortfolioError("OpenD unavailable")

    with patch(
        "src.services.stock_list_parser.resolve_portfolio_stock_list",
        side_effect=error,
    ), patch("src.core.pipeline.StockAnalysisPipeline") as pipeline_type, pytest.raises(
        FutuPortfolioError,
        match="OpenD unavailable",
    ):
        main.run_full_analysis(config, _args(), ["AAPL"], raise_errors=True)

    config.refresh_stock_list.assert_not_called()
    pipeline_type.assert_not_called()


def test_futu_scope_failure_returns_false_for_cli_service_boundary() -> None:
    config = _config()

    with patch(
        "src.services.stock_list_parser.resolve_portfolio_stock_list",
        side_effect=FutuPortfolioError("OpenD unavailable"),
    ), patch("src.core.pipeline.StockAnalysisPipeline") as pipeline_type:
        assert main.run_full_analysis(config, _args(), ["AAPL"]) is False

    config.refresh_stock_list.assert_not_called()
    pipeline_type.assert_not_called()
