# -*- coding: utf-8 -*-
"""Regression tests for pipeline data-fetch error handling."""

from datetime import date, datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from src.core.pipeline import StockAnalysisPipeline


class PipelineFetchErrorTestCase(unittest.TestCase):
    """`fetch_and_save_stock_data` should preserve the original exception."""

    def test_fetch_and_save_handles_stock_name_lookup_failure(self):
        pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
        pipeline.fetcher_manager = MagicMock()
        pipeline.db = MagicMock()
        pipeline.fetcher_manager.get_stock_name.side_effect = RuntimeError("name lookup failed")

        success, error = StockAnalysisPipeline.fetch_and_save_stock_data(pipeline, "600519")

        self.assertFalse(success)
        self.assertIn("name lookup failed", error or "")

    @patch.object(
        StockAnalysisPipeline,
        "_resolve_resume_target_date",
        return_value=date(2026, 3, 27),
    )
    def test_fetch_and_save_uses_effective_trading_date_for_resume_check(self, _mock_target):
        pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
        pipeline.fetcher_manager = MagicMock()
        pipeline.db = MagicMock()
        pipeline.fetcher_manager.get_stock_name.return_value = "贵州茅台"
        pipeline.db.has_today_data.return_value = True
        pipeline.db.get_data_range.return_value = [object()] * 60
        current_time = datetime(2026, 3, 28, 1, 0, tzinfo=timezone.utc)

        success, error = StockAnalysisPipeline.fetch_and_save_stock_data(
            pipeline,
            "600519",
            current_time=current_time,
        )

        self.assertTrue(success)
        self.assertIsNone(error)
        _mock_target.assert_called_once_with("600519", current_time=current_time)
        pipeline.db.has_today_data.assert_called_once_with("600519", date(2026, 3, 27))
        pipeline.fetcher_manager.get_daily_data.assert_not_called()

    @patch.object(
        StockAnalysisPipeline,
        "_resolve_resume_target_date",
        return_value=date(2026, 3, 27),
    )
    def test_target_date_with_insufficient_ma250_history_is_backfilled(self, _mock_target):
        pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
        pipeline.fetcher_manager = MagicMock()
        pipeline.db = MagicMock()
        pipeline.config = SimpleNamespace(
            indicator_ma_periods=[5, 10, 20, 60, 250],
            indicator_macd_fast=12,
            indicator_macd_slow=26,
            indicator_macd_signal=9,
            indicator_rsi_periods=[6, 12, 24],
            indicator_period_source="global_settings",
        )
        pipeline.fetcher_manager.get_stock_name.return_value = "贵州茅台"
        pipeline.db.has_today_data.return_value = True
        pipeline.db.get_data_range.return_value = [object()] * 40
        pipeline.fetcher_manager.get_daily_data.return_value = (
            pd.DataFrame([{"date": "2026-03-27", "close": 1.0}]),
            "dummy",
        )
        pipeline.db.save_daily_data.return_value = 1

        success, error = StockAnalysisPipeline.fetch_and_save_stock_data(
            pipeline,
            "600519",
        )

        self.assertTrue(success)
        self.assertIsNone(error)
        expected_days = int(250 * 1.8) + 10
        pipeline.fetcher_manager.get_daily_data.assert_called_once_with(
            "600519",
            days=expected_days,
        )
        coverage_call = pipeline.db.get_data_range.call_args
        self.assertEqual(coverage_call.args[0], "600519")
        self.assertEqual(coverage_call.args[2], date(2026, 3, 27))
        self.assertEqual(
            (coverage_call.args[2] - coverage_call.args[1]).days,
            expected_days,
        )

    @patch.object(
        StockAnalysisPipeline,
        "_resolve_resume_target_date",
        return_value=date(2026, 3, 27),
    )
    def test_long_history_backfill_provider_failure_is_explicit(self, _mock_target):
        pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
        pipeline.fetcher_manager = MagicMock()
        pipeline.db = MagicMock()
        pipeline.config = SimpleNamespace(
            indicator_ma_periods=[30, 60, 250],
            indicator_macd_fast=12,
            indicator_macd_slow=26,
            indicator_macd_signal=9,
            indicator_rsi_periods=[14],
            indicator_period_source="global_settings",
        )
        pipeline.fetcher_manager.get_stock_name.return_value = "贵州茅台"
        pipeline.db.has_today_data.return_value = True
        pipeline.db.get_data_range.return_value = [object()] * 10
        pipeline.fetcher_manager.get_daily_data.side_effect = RuntimeError(
            "all providers exhausted"
        )

        success, error = StockAnalysisPipeline.fetch_and_save_stock_data(
            pipeline,
            "600519",
        )

        self.assertFalse(success)
        self.assertIn("all providers exhausted", error or "")
        pipeline.db.save_daily_data.assert_not_called()

    def test_resolve_resume_target_date_normalizes_supported_a_share_formats(self):
        with patch("src.core.pipeline.get_market_for_stock", return_value="cn") as mock_market, patch(
            "src.core.pipeline.get_effective_trading_date",
            return_value=date(2026, 3, 27),
        ) as mock_target:
            for code in ("SH600519", "000001.SZ", "BJ920748"):
                result = StockAnalysisPipeline._resolve_resume_target_date(code)
                self.assertEqual(result, date(2026, 3, 27))

        self.assertEqual(
            [args.args[0] for args in mock_market.call_args_list],
            ["600519", "000001", "920748"],
        )
        self.assertEqual(mock_target.call_count, 3)


if __name__ == "__main__":
    unittest.main()
