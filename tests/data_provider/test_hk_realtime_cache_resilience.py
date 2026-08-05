# -*- coding: utf-8 -*-
"""HK Eastmoney realtime cache resilience: failed refresh must not nuke usable data."""

from __future__ import annotations

import sys
import time
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from tests.litellm_stub import ensure_litellm_stub

ensure_litellm_stub()
try:
    import json_repair  # noqa: F401
except ImportError:
    if "json_repair" not in sys.modules:
        sys.modules["json_repair"] = MagicMock()

from data_provider import akshare_fetcher as akshare_fetcher_module
from data_provider.akshare_fetcher import AkshareFetcher


class _DummyCircuitBreaker:
    def __init__(self):
        self.failures = []
        self.successes = []

    def is_available(self, source: str) -> bool:
        return True

    def record_success(self, source: str) -> None:
        self.successes.append(source)

    def record_failure(self, source: str, error=None) -> None:
        self.failures.append((source, error))


def _make_spot_em_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "代码": "00700",
                "名称": "腾讯控股",
                "最新价": 370.0,
                "涨跌幅": 1.5,
                "涨跌额": 5.5,
                "成交量": 10000,
                "成交额": 3700000.0,
                "量比": 1.2,
                "换手率": 0.3,
                "振幅": 2.0,
                "市盈率": 20.0,
                "市净率": 3.5,
                "总市值": 3.5e12,
                "流通市值": 3.5e12,
                "52周最高": 400.0,
                "52周最低": 280.0,
            }
        ]
    )


def _make_spot_df() -> pd.DataFrame:
    """Sina snapshot: strictly smaller field set (no turnover_rate / pe / pb / 52w)."""
    return pd.DataFrame(
        [
            {
                "代码": "00700",
                "名称": "腾讯控股",
                "最新价": 368.0,
                "涨跌额": 3.5,
                "涨跌幅": 0.96,
                "买入": 367.8,
                "卖出": 368.2,
                "昨收": 364.5,
                "今开": 365.0,
                "最高": 370.0,
                "最低": 364.0,
                "成交量": 9800,
                "成交额": 3606400.0,
            }
        ]
    )


class TestHKRealtimeCacheResilience(unittest.TestCase):
    def setUp(self) -> None:
        self.fetcher = AkshareFetcher()
        akshare_fetcher_module._realtime_cache["hk"].update(
            {
                "data": None,
                "timestamp": 0,
                "ttl": 1200,
                "failure_ttl": 30,
                "failure_at": 0,
                "last_result": None,
            }
        )
        self.fetcher._enforce_rate_limit = lambda: None
        self.fetcher._set_random_user_agent = lambda: None

    @patch("data_provider.akshare_fetcher.get_realtime_circuit_breaker")
    def test_warm_snapshot_survives_refresh_raise_within_original_ttl(self, mock_cb):
        """(a) Warm snapshot + refresh raises → still serve EM fields within TTL."""
        mock_cb.return_value = _DummyCircuitBreaker()
        good = _make_spot_em_df()
        # Cold start so the refresh path runs; the primary call plants a warm
        # snapshot then raises — the failure handler must keep that snapshot.
        ak_mock = MagicMock()

        def plant_then_fail():
            now = time.time()
            akshare_fetcher_module._realtime_cache["hk"].update(
                {
                    "data": good.copy(),
                    "timestamp": now,
                    "last_result": "success",
                    "failure_at": 0,
                }
            )
            raise RuntimeError("eastmoney hiccup after partial success")

        ak_mock.stock_hk_spot_em.side_effect = plant_then_fail
        ak_mock.stock_hk_spot.return_value = _make_spot_df()

        with patch.dict(sys.modules, {"akshare": ak_mock}):
            first = self.fetcher._get_hk_realtime_quote("HK00700")
            second = self.fetcher._get_hk_realtime_quote("HK00700")

        # First call falls through to Sina (refresh raised); second must hit EM cache.
        self.assertIsNotNone(first)
        self.assertAlmostEqual(first.price, 368.0)
        self.assertIsNone(first.turnover_rate)

        self.assertIsNotNone(second)
        self.assertAlmostEqual(second.price, 370.0)
        self.assertAlmostEqual(second.turnover_rate, 0.3)
        self.assertAlmostEqual(second.pe_ratio, 20.0)
        self.assertIsNotNone(akshare_fetcher_module._realtime_cache["hk"]["data"])
        ak_mock.stock_hk_spot_em.assert_called_once()

    @patch("data_provider.akshare_fetcher.get_realtime_circuit_breaker")
    def test_cold_refresh_failure_uses_failure_ttl_and_sina(self, mock_cb):
        """(b) Cold + refresh raises → failure TTL, Sina fallback, retry after TTL."""
        mock_cb.return_value = _DummyCircuitBreaker()
        ak_mock = MagicMock()
        ak_mock.stock_hk_spot_em.side_effect = RuntimeError("eastmoney down")
        ak_mock.stock_hk_spot.return_value = _make_spot_df()

        with patch.dict(sys.modules, {"akshare": ak_mock}):
            first = self.fetcher._get_hk_realtime_quote("HK00700")
            second = self.fetcher._get_hk_realtime_quote("HK00700")

            self.assertIsNotNone(first)
            self.assertAlmostEqual(first.price, 368.0)
            self.assertIsNone(first.turnover_rate)
            self.assertEqual(ak_mock.stock_hk_spot_em.call_count, 1)
            self.assertEqual(ak_mock.stock_hk_spot.call_count, 2)
            self.assertEqual(
                akshare_fetcher_module._realtime_cache["hk"]["last_result"],
                "failure",
            )

            # Advance past failure TTL; next call retries Eastmoney.
            hk = akshare_fetcher_module._realtime_cache["hk"]
            hk["failure_at"] = time.time() - (hk["failure_ttl"] + 1)
            if hk.get("data") is None:
                hk["timestamp"] = time.time() - (hk["failure_ttl"] + 1)

            ak_mock.stock_hk_spot_em.side_effect = None
            ak_mock.stock_hk_spot_em.return_value = _make_spot_em_df()
            third = self.fetcher._get_hk_realtime_quote("HK00700")

        self.assertIsNotNone(third)
        self.assertAlmostEqual(third.turnover_rate, 0.3)
        self.assertEqual(ak_mock.stock_hk_spot_em.call_count, 2)
        self.assertEqual(
            akshare_fetcher_module._realtime_cache["hk"]["last_result"],
            "success",
        )

    @patch("data_provider.akshare_fetcher.get_realtime_circuit_breaker")
    def test_validation_raise_preserves_warm_snapshot(self, mock_cb):
        """(c) Validation-raise on refresh keeps a still-usable snapshot."""
        mock_cb.return_value = _DummyCircuitBreaker()
        good = _make_spot_em_df()
        ak_mock = MagicMock()

        def plant_then_invalid():
            now = time.time()
            akshare_fetcher_module._realtime_cache["hk"].update(
                {
                    "data": good.copy(),
                    "timestamp": now,
                    "last_result": "success",
                    "failure_at": 0,
                }
            )
            # Missing 代码 column → validation KeyError in refresh path.
            return pd.DataFrame([{"名称": "腾讯控股", "最新价": 1.0}])

        ak_mock.stock_hk_spot_em.side_effect = plant_then_invalid
        ak_mock.stock_hk_spot.return_value = _make_spot_df()

        with patch.dict(sys.modules, {"akshare": ak_mock}):
            first = self.fetcher._get_hk_realtime_quote("HK00700")
            second = self.fetcher._get_hk_realtime_quote("HK00700")

        self.assertIsNotNone(first)
        self.assertIsNone(first.turnover_rate)
        self.assertIsNotNone(second)
        self.assertAlmostEqual(second.turnover_rate, 0.3)
        self.assertIsNotNone(akshare_fetcher_module._realtime_cache["hk"]["data"])

    @patch("data_provider.akshare_fetcher.get_realtime_circuit_breaker")
    def test_validation_raise_cold_installs_failure_ttl(self, mock_cb):
        """(c) Validation-raise when cold installs short failure TTL like network fail."""
        mock_cb.return_value = _DummyCircuitBreaker()
        ak_mock = MagicMock()
        ak_mock.stock_hk_spot_em.return_value = pd.DataFrame(
            columns=["代码", "名称", "最新价"]
        )
        ak_mock.stock_hk_spot.return_value = _make_spot_df()

        with patch.dict(sys.modules, {"akshare": ak_mock}):
            quote = self.fetcher._get_hk_realtime_quote("HK00700")
            again = self.fetcher._get_hk_realtime_quote("HK00700")

        self.assertIsNotNone(quote)
        self.assertAlmostEqual(quote.price, 368.0)
        self.assertEqual(ak_mock.stock_hk_spot_em.call_count, 1)
        self.assertEqual(ak_mock.stock_hk_spot.call_count, 2)
        self.assertEqual(
            akshare_fetcher_module._realtime_cache["hk"]["last_result"],
            "failure",
        )
        self.assertIsNotNone(again)

    @patch("data_provider.akshare_fetcher.get_realtime_circuit_breaker")
    def test_sina_fallback_missing_fields_are_none_not_zero(self, mock_cb):
        """(d) Sina path leaves EM-only fields as None, not 0."""
        mock_cb.return_value = _DummyCircuitBreaker()
        ak_mock = MagicMock()
        ak_mock.stock_hk_spot_em.side_effect = RuntimeError("eastmoney down")
        ak_mock.stock_hk_spot.return_value = _make_spot_df()

        with patch.dict(sys.modules, {"akshare": ak_mock}):
            quote = self.fetcher._get_hk_realtime_quote("HK00700")

        self.assertIsNotNone(quote)
        self.assertIsNone(quote.turnover_rate)
        self.assertIsNone(quote.pe_ratio)
        self.assertIsNone(quote.pb_ratio)
        self.assertIsNone(quote.volume_ratio)
        self.assertIsNone(quote.high_52w)
        self.assertIsNone(quote.low_52w)
        # Explicitly not coerced to zero by the Sina merge path.
        self.assertNotEqual(quote.turnover_rate, 0)
        self.assertNotEqual(quote.pe_ratio, 0)

    @patch("data_provider.akshare_fetcher.get_realtime_circuit_breaker")
    def test_failed_refresh_does_not_clear_prior_snapshot_bytes(self, mock_cb):
        """Expired prior snapshot is kept (not set to None) across a failed refresh."""
        mock_cb.return_value = _DummyCircuitBreaker()
        good = _make_spot_em_df()
        past = time.time() - 5000
        akshare_fetcher_module._realtime_cache["hk"].update(
            {
                "data": good.copy(),
                "timestamp": past,
                "ttl": 1200,
                "failure_ttl": 30,
                "failure_at": 0,
                "last_result": "success",
            }
        )
        ak_mock = MagicMock()
        ak_mock.stock_hk_spot_em.side_effect = RuntimeError("timeout")
        ak_mock.stock_hk_spot.return_value = _make_spot_df()

        with patch.dict(sys.modules, {"akshare": ak_mock}):
            quote = self.fetcher._get_hk_realtime_quote("HK00700")

        self.assertIsNotNone(quote)
        self.assertIsNone(quote.turnover_rate)
        # Snapshot object preserved; success timestamp not rewritten to "now".
        self.assertIsNotNone(akshare_fetcher_module._realtime_cache["hk"]["data"])
        self.assertEqual(akshare_fetcher_module._realtime_cache["hk"]["timestamp"], past)
        self.assertEqual(
            akshare_fetcher_module._realtime_cache["hk"]["last_result"],
            "failure",
        )
        self.assertGreater(
            akshare_fetcher_module._realtime_cache["hk"]["failure_at"],
            past,
        )


if __name__ == "__main__":
    unittest.main()
