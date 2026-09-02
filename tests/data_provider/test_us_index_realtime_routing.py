# -*- coding: utf-8 -*-
"""
Regression tests for U.S. index realtime quote routing.

US index quotes are YFinance-only: missing or partial YFinance data must not
fall back to or field-supplement from Longbridge. Non-index U.S. stocks keep
the existing Longbridge fallback/supplement chain.
"""

import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

if "litellm" not in sys.modules:
    sys.modules["litellm"] = MagicMock()
if "json_repair" not in sys.modules:
    sys.modules["json_repair"] = MagicMock()

from src.data_provider.base import DataFetcherManager
from src.data_provider.realtime_types import RealtimeSource, UnifiedRealtimeQuote


def _quote(code: str, **overrides) -> UnifiedRealtimeQuote:
    payload = {
        "code": code,
        "name": code,
        "source": RealtimeSource.YFINANCE,
        "price": 5000.0,
        "change_pct": 0.5,
    }
    payload.update(overrides)
    return UnifiedRealtimeQuote(**payload)


def _realtime_config() -> SimpleNamespace:
    return SimpleNamespace(
        enable_realtime_quote=True,
        realtime_source_priority="efinance,akshare_em,tushare",
        realtime_cache_ttl=600,
    )


def _fetcher(name: str, priority: int, result=None) -> MagicMock:
    fetcher = MagicMock()
    fetcher.name = name
    fetcher.priority = priority
    fetcher.is_available_for_request.return_value = True
    fetcher.get_realtime_quote.return_value = result
    return fetcher


class TestUSIndexRealtimeRouting(unittest.TestCase):
    """Keep US index realtime quotes off the Longbridge fallback/supplement path."""

    @patch("src.config.get_config")
    def test_us_index_does_not_fallback_to_longbridge(self, mock_get_config):
        mock_get_config.return_value = _realtime_config()

        yfinance = _fetcher("YfinanceFetcher", 4, result=None)
        longbridge = _fetcher("LongbridgeFetcher", 5, result=_quote("SPX"))

        manager = DataFetcherManager(fetchers=[yfinance, longbridge])
        quote = manager.get_realtime_quote("SPX")

        self.assertIsNone(quote)
        yfinance.get_realtime_quote.assert_called_once_with("SPX")
        longbridge.get_realtime_quote.assert_not_called()

    @patch("src.config.get_config")
    def test_us_index_does_not_field_supplement_from_longbridge(self, mock_get_config):
        mock_get_config.return_value = _realtime_config()

        primary = _quote("SPX", source=RealtimeSource.YFINANCE, volume_ratio=None)
        longbridge_quote = _quote(
            "SPX",
            source=RealtimeSource.LONGBRIDGE,
            volume_ratio=1.25,
            turnover_rate=0.4,
        )
        yfinance = _fetcher("YfinanceFetcher", 4, result=primary)
        longbridge = _fetcher("LongbridgeFetcher", 5, result=longbridge_quote)

        manager = DataFetcherManager(fetchers=[yfinance, longbridge])
        quote = manager.get_realtime_quote("SPX")

        self.assertIs(quote, primary)
        self.assertIsNone(quote.volume_ratio)
        self.assertIsNone(quote.turnover_rate)
        yfinance.get_realtime_quote.assert_called_once_with("SPX")
        longbridge.get_realtime_quote.assert_not_called()

    @patch("src.config.get_config")
    def test_us_stock_still_falls_back_from_longbridge_to_yfinance(self, mock_get_config):
        mock_get_config.return_value = _realtime_config()

        yfinance_quote = _quote("AAPL", source=RealtimeSource.YFINANCE)
        longbridge = _fetcher("LongbridgeFetcher", 5, result=None)
        yfinance = _fetcher("YfinanceFetcher", 4, result=yfinance_quote)

        manager = DataFetcherManager(fetchers=[longbridge, yfinance])
        quote = manager.get_realtime_quote("AAPL")

        self.assertIs(quote, yfinance_quote)
        self.assertEqual(quote.fallback_from, "longbridge")
        longbridge.get_realtime_quote.assert_called_once_with("AAPL")
        yfinance.get_realtime_quote.assert_called_once_with("AAPL")

    @patch("src.config.get_config")
    def test_us_stock_still_supplements_missing_fields_from_secondary(self, mock_get_config):
        mock_get_config.return_value = _realtime_config()

        primary = _quote(
            "AAPL",
            source=RealtimeSource.LONGBRIDGE,
            volume_ratio=None,
            turnover_rate=None,
        )
        yfinance_quote = _quote(
            "AAPL",
            source=RealtimeSource.YFINANCE,
            volume_ratio=1.1,
            turnover_rate=0.2,
        )
        longbridge = _fetcher("LongbridgeFetcher", 5, result=primary)
        yfinance = _fetcher("YfinanceFetcher", 4, result=yfinance_quote)

        manager = DataFetcherManager(fetchers=[longbridge, yfinance])
        quote = manager.get_realtime_quote("AAPL")

        self.assertIs(quote, primary)
        self.assertEqual(quote.volume_ratio, 1.1)
        self.assertEqual(quote.turnover_rate, 0.2)
        longbridge.get_realtime_quote.assert_called_once_with("AAPL")
        yfinance.get_realtime_quote.assert_called_once_with("AAPL")


if __name__ == "__main__":
    unittest.main()
