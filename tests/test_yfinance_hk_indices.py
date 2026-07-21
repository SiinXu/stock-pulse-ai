# -*- coding: utf-8 -*-
"""
data_provider/yfinance_fetcher Unit tests for logic to retrieve China and US stock indices

Use unittest.mock to mock yfinance API response, covering:
- _get_hk_main_indices Bulk fetching of Hong Kong stock index
- Yahoo Finance symbol mapping accuracy for Hong Kong stocks indices.
- Partial/full failure fallback scenarios
"""
import sys
import os
import unittest
from unittest.mock import MagicMock, patch
import pandas as pd

# Mock missing dependencies before importing data_provider to avoid environment differences causing tests to fail.
if 'fake_useragent' not in sys.modules:
    sys.modules['fake_useragent'] = MagicMock()

# Ensure the project modules can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def _make_mock_hist(close: float, prev_close: float, high: float = None, low: float = None) -> pd.DataFrame:
    """Construct a simulated history DataFrame, containing fields required to calculate percentage change"""
    high = high if high is not None else close + 100
    low = low if low is not None else close - 100
    return pd.DataFrame({
        'Close': [prev_close, close],
        'Open': [prev_close - 50, close - 30],
        'High': [prev_close + 100, high],
        'Low': [prev_close - 100, low],
        'Volume': [5000000000.0, 5200000000.0],
    }, index=pd.DatetimeIndex(['2025-02-16', '2025-02-17']))


def _make_mock_yf(hist_df: pd.DataFrame):
    """Construct a simulated yf module, Ticker().history() returns the given DataFrame"""
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = hist_df
    mock_yf = MagicMock()
    mock_yf.Ticker.return_value = mock_ticker
    return mock_yf


class TestHkIndexSymbolMapping(unittest.TestCase):
    """Validate the correctness of Yahoo Finance symbol mapping for Hong Kong stocks"""

    def setUp(self):
        from data_provider.yfinance_fetcher import YfinanceFetcher
        self.fetcher = YfinanceFetcher()

    def test_hk_indices_mapping_symbols(self):
        """The mapping of Hong Kong stocks indices should use the correct Yahoo Finance symbols."""
        mock_yf = MagicMock()
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()
        mock_yf.Ticker.return_value = mock_ticker

        self.fetcher._get_hk_main_indices(mock_yf)

        # Collect all Ticker() call parameters
        ticker_calls = [call.args[0] for call in mock_yf.Ticker.call_args_list]

        self.assertIn('^HSI', ticker_calls, '恒生指数应使用 ^HSI')
        self.assertIn('HSTECH.HK', ticker_calls, '恒生科技指数应使用 HSTECH.HK，而非 ^HSTECH')
        self.assertIn('^HSCE', ticker_calls, '国企指数应使用 ^HSCE，而非 ^HSCEI')

    def test_hk_indices_mapping_no_invalid_symbols(self):
        """Ensure no known incorrect old mapping symbols are used"""
        mock_yf = MagicMock()
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()
        mock_yf.Ticker.return_value = mock_ticker

        self.fetcher._get_hk_main_indices(mock_yf)

        ticker_calls = [call.args[0] for call in mock_yf.Ticker.call_args_list]

        self.assertNotIn('^HSTECH', ticker_calls, '^HSTECH 不是有效的 Yahoo Finance 符号')
        self.assertNotIn('^HSCEI', ticker_calls, '^HSCEI 不是有效的 Yahoo Finance 符号')


class TestGetHkMainIndices(unittest.TestCase):
    """_get_hk_main_indices Batch retrieval of Hong Kong Stock Index test"""

    def setUp(self):
        from data_provider.yfinance_fetcher import YfinanceFetcher
        self.fetcher = YfinanceFetcher()

    def test_returns_list_when_all_succeed(self):
        """Returns a list containing three indices if all index fetching succeeds"""
        mock_hist = _make_mock_hist(close=20000.0, prev_close=19800.0)
        mock_yf = _make_mock_yf(mock_hist)

        result = self.fetcher._get_hk_main_indices(mock_yf)

        self.assertIsNotNone(result)
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 3)

        codes = {item['code'] for item in result}
        self.assertEqual(codes, {'HSI', 'HSTECH', 'HSCEI'})

        for item in result:
            self.assertIn('code', item)
            self.assertIn('name', item)
            self.assertIn('current', item)
            self.assertIn('change_pct', item)
            self.assertIn('prev_close', item)
            self.assertIn('amplitude', item)

    def test_returns_correct_computed_values(self):
        """Validate the calculated percentage change and amplitude."""
        mock_hist = _make_mock_hist(
            close=20000.0, prev_close=19800.0, high=20200.0, low=19700.0
        )
        mock_yf = _make_mock_yf(mock_hist)

        result = self.fetcher._get_hk_main_indices(mock_yf)

        self.assertIsNotNone(result)
        item = result[0]
        self.assertEqual(item['current'], 20000.0)
        self.assertEqual(item['prev_close'], 19800.0)
        self.assertAlmostEqual(item['change'], 200.0)
        expected_pct = (200.0 / 19800.0) * 100
        self.assertAlmostEqual(item['change_pct'], expected_pct)
        expected_amplitude = ((20200.0 - 19700.0) / 19800.0) * 100
        self.assertAlmostEqual(item['amplitude'], expected_amplitude)

    def test_handles_partial_failure(self):
        """When some index histories are empty, the system still returns indices that can be retrieved data from."""
        call_count = [0]

        def history_side_effect(period):
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_mock_hist(close=20000.0, prev_close=19800.0)
            return pd.DataFrame()

        mock_ticker = MagicMock()
        mock_ticker.history.side_effect = history_side_effect
        mock_yf = MagicMock()
        mock_yf.Ticker.return_value = mock_ticker

        result = self.fetcher._get_hk_main_indices(mock_yf)

        self.assertIsNotNone(result)
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)

    def test_returns_none_when_all_fail(self):
        """Returns None if all data fetching fails"""
        mock_yf = _make_mock_yf(pd.DataFrame())

        result = self.fetcher._get_hk_main_indices(mock_yf)

        self.assertIsNone(result)

    def test_handles_ticker_exception(self):
        """Ticker.history throws an exception, skips this index, does not cause overall failure"""
        mock_ticker = MagicMock()
        mock_ticker.history.side_effect = Exception("Network error")
        mock_yf = MagicMock()
        mock_yf.Ticker.return_value = mock_ticker

        result = self.fetcher._get_hk_main_indices(mock_yf)

        self.assertIsNone(result)

    def test_return_codes_match_expected_keys(self):
        """The value in the 'code' field should be HSI/HSTECH/HSCEI, consistent with MarketAnalyzer prompt"""
        mock_hist = _make_mock_hist(close=20000.0, prev_close=19800.0)
        mock_yf = _make_mock_yf(mock_hist)

        result = self.fetcher._get_hk_main_indices(mock_yf)

        self.assertIsNotNone(result)
        codes = [item['code'] for item in result]
        self.assertIn('HSI', codes)
        self.assertIn('HSTECH', codes)
        self.assertIn('HSCEI', codes)


class TestGetMainIndicesDispatch(unittest.TestCase):
    """get_main_indices region distribution test"""

    def setUp(self):
        from data_provider.yfinance_fetcher import YfinanceFetcher
        self.fetcher = YfinanceFetcher()

    def test_region_hk_dispatches_to_hk_method(self):
        """region='hk' Respond to/delegate to _get_hk_main_indices"""
        mock_yf = MagicMock()
        with patch.dict('sys.modules', {'yfinance': mock_yf}):
            with patch.object(self.fetcher, '_get_hk_main_indices', return_value=[{'code': 'HSI'}]) as mock_hk:
                result = self.fetcher.get_main_indices(region='hk')

                mock_hk.assert_called_once()
                self.assertEqual(result, [{'code': 'HSI'}])


if __name__ == '__main__':
    unittest.main()
