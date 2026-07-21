# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch, MagicMock, PropertyMock

from data_provider.yfinance_fetcher import YfinanceFetcher
from data_provider.realtime_types import RealtimeSource

try:
    import yfinance  # noqa: F401

    HAS_YFINANCE = True
except Exception:
    HAS_YFINANCE = False


class TestStooqFallback(unittest.TestCase):
    def setUp(self):
        self.fetcher = YfinanceFetcher()

    @patch('data_provider.yfinance_fetcher.urlopen')
    def test_stooq_success_logic(self, mock_urlopen):
        """Test Stooq normal fetching and parsing logic"""
        # Simulate Stooq returned CSV format data (real-time + daily historical)
        mock_realtime_payload = (
            "Symbol,Date,Time,Open,High,Low,Close,Volume\n"
            "AAPL.US,2026-03-10,22:00:00,180.50,185.20,179.80,184.45,50000000\n"
        )
        mock_history_payload = (
            "Date,Open,High,Low,Close,Volume\n"
            "2026-03-09,178.00,181.00,177.00,179.00,48000000\n"
            "2026-03-10,180.50,185.20,179.80,184.45,50000000\n"
        )

        mock_realtime_response = MagicMock()
        mock_realtime_response.read.return_value = mock_realtime_payload.encode('utf-8')
        mock_realtime_response.__enter__.return_value = mock_realtime_response

        mock_history_response = MagicMock()
        mock_history_response.read.return_value = mock_history_payload.encode('utf-8')
        mock_history_response.__enter__.return_value = mock_history_response

        mock_urlopen.side_effect = [mock_realtime_response, mock_history_response]

        quote = self.fetcher._get_us_stock_quote_from_stooq("AAPL")

        self.assertIsNotNone(quote)
        self.assertEqual(quote.code, "AAPL")
        self.assertEqual(quote.price, 184.45)
        self.assertEqual(quote.open_price, 180.50)
        self.assertEqual(quote.high, 185.20)
        self.assertEqual(quote.low, 179.80)
        self.assertEqual(quote.volume, 50000000)
        self.assertEqual(quote.source, RealtimeSource.STOOQ)
        self.assertEqual(quote.pre_close, 179.00)
        self.assertAlmostEqual(quote.change_amount, 5.45, places=2)
        self.assertAlmostEqual(quote.change_pct, 3.04, places=2)
        self.assertAlmostEqual(quote.amplitude, 3.02, places=2)

    @unittest.skipUnless(HAS_YFINANCE, "yfinance is required for this test")
    @patch('yfinance.Ticker')
    def test_fetcher_integration_with_fallback(self, mock_ticker_class):
        """Test automatic triggering of Stooq logic after yfinance failure"""
        # 1. Simulate yfinance completely failing
        mock_ticker = MagicMock()
        # Simulate raising an exception when accessing the fast_info attribute
        type(mock_ticker).fast_info = PropertyMock(side_effect=Exception("API Error"))
        # Simulate history returning an empty list
        mock_ticker.history.return_value = MagicMock(empty=True)
        mock_ticker_class.return_value = mock_ticker

        # 2. Simulate Stooq successful return
        with patch.object(self.fetcher, '_get_us_stock_quote_from_stooq') as mock_stooq:
            mock_stooq.return_value = MagicMock(code="NVDA", price=900.0)

            quote = self.fetcher.get_realtime_quote("NVDA")

            self.assertIsNotNone(quote)
            self.assertEqual(quote.price, 900.0)
            mock_stooq.assert_called_once_with("NVDA")


if __name__ == '__main__':
    unittest.main()
