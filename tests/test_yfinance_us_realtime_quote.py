# -*- coding: utf-8 -*-
"""US stock realtime valuation population in YfinanceFetcher.get_realtime_quote.

yfinance already returns trailingPE / priceToBook via Ticker.info (fetched for
the stock name), so US realtime quotes should surface pe_ratio / pb_ratio
instead of hardcoding them to None and reporting a partial quote.
"""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

if "fake_useragent" not in sys.modules:
    sys.modules["fake_useragent"] = MagicMock()

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _mock_ticker(info):
    ticker = MagicMock()
    ticker.fast_info = SimpleNamespace(
        lastPrice=190.0,
        previousClose=188.0,
        open=189.0,
        dayHigh=191.0,
        dayLow=187.0,
        lastVolume=1_000_000,
        marketCap=3_000_000_000_000,
    )
    ticker.info = info
    return ticker


class TestUsRealtimeValuation(unittest.TestCase):
    def setUp(self):
        from data_provider.yfinance_fetcher import YfinanceFetcher

        self.fetcher = YfinanceFetcher()

    def test_populates_pe_pb_from_ticker_info(self):
        ticker = _mock_ticker(
            {
                "shortName": "Apple Inc.",
                "currency": "USD",
                "trailingPE": 39.67,
                "priceToBook": 45.08,
            }
        )
        with patch("yfinance.Ticker", return_value=ticker):
            quote = self.fetcher.get_realtime_quote("AAPL")

        self.assertIsNotNone(quote)
        self.assertEqual(quote.pe_ratio, 39.67)
        self.assertEqual(quote.pb_ratio, 45.08)
        self.assertNotIn("pe_ratio", quote.missing_fields or [])
        self.assertNotIn("pb_ratio", quote.missing_fields or [])

    def test_leaves_pe_pb_none_when_info_omits_them(self):
        ticker = _mock_ticker({"shortName": "Apple Inc.", "currency": "USD"})
        with patch("yfinance.Ticker", return_value=ticker):
            quote = self.fetcher.get_realtime_quote("AAPL")

        self.assertIsNotNone(quote)
        self.assertIsNone(quote.pe_ratio)
        self.assertIsNone(quote.pb_ratio)
        self.assertIn("pe_ratio", quote.missing_fields or [])
        self.assertIn("pb_ratio", quote.missing_fields or [])


if __name__ == "__main__":
    unittest.main()
