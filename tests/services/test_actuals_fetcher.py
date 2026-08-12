# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Tests for ActualsFetcher (Issue #1110 / Epic #1107).

Covers:
- successful OHLC/return projection through DataFetcherManager
- provider_down / data_unavailable with no fabricated prices
- process-local cache + fetch_many coalesce (one provider call per key)
- non-finite numeric rejection
- concurrent same-key in-flight merge
"""

from __future__ import annotations

import math
import threading
import unittest
from datetime import date, datetime, timezone
from typing import Any, List, Optional, Tuple
from unittest.mock import MagicMock, patch

import pandas as pd

from data_provider.base import (
    DataFetchError,
    DataFetcherManager,
    DataSourceUnavailableError,
)
from data_provider.realtime_types import CircuitBreaker
from src.schemas.prediction_actuals import (
    ACTUALS_STATUS_DATA_UNAVAILABLE,
    ACTUALS_STATUS_EMPTY,
    ACTUALS_STATUS_HALTED,
    ACTUALS_STATUS_OK,
    ACTUALS_STATUS_PROVIDER_DOWN,
    FIELD_OHLC,
    FIELD_RETURN,
    FIELD_VOLUME,
    REASON_NON_FINITE,
    REASON_END_NOT_REACHED,
    REASON_INVALID_WINDOW,
    REASON_NO_BAR_FOR_END,
    REASON_PROVIDER_FAILURE,
    ActualsBar,
    ActualsRequest,
    ActualsSnapshot,
)
from src.services.actuals_fetcher import ActualsFetcher


def _daily_frame(
    rows: List[Tuple[str, float, float, float, float, float]],
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": trade_date,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
                "amount": volume * close,
                "pct_chg": 0.0,
            }
            for trade_date, open_, high, low, close, volume in rows
        ]
    )


class _RecordingManager:
    """Minimal manager double that records get_daily_data calls."""

    def __init__(
        self,
        result: Optional[Tuple[pd.DataFrame, str]] = None,
        *,
        error: Optional[BaseException] = None,
        delay_event: Optional[threading.Event] = None,
        release_event: Optional[threading.Event] = None,
    ) -> None:
        self.result = result
        self.error = error
        self.delay_event = delay_event
        self.release_event = release_event
        self.calls: List[dict] = []
        self._lock = threading.Lock()

    def get_daily_data(
        self,
        stock_code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        days: int = 30,
    ) -> Tuple[pd.DataFrame, str]:
        with self._lock:
            self.calls.append(
                {
                    "stock_code": stock_code,
                    "start_date": start_date,
                    "end_date": end_date,
                    "days": days,
                }
            )
        if self.delay_event is not None:
            self.delay_event.set()
        if self.release_event is not None:
            self.release_event.wait(timeout=5.0)
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


class _OfflineProvider:
    """DataProvider-shaped stub used under the real manager fallback layer."""

    def __init__(self, name: str, priority: int, outcome: Any) -> None:
        self.name = name
        self.priority = priority
        self.outcome = outcome
        self.calls = 0

    def get_daily_data(self, **_kwargs):
        self.calls += 1
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome.copy(deep=True)


class ActualsFetcherSuccessTests(unittest.TestCase):
    def test_fetch_success_projects_ohlc_return_volume(self) -> None:
        frame = _daily_frame(
            [
                ("2026-04-10", 10.0, 11.0, 9.5, 10.5, 1000.0),
                ("2026-04-13", 10.5, 12.0, 10.0, 11.55, 1500.0),
            ]
        )
        manager = _RecordingManager(result=(frame, "EfinanceFetcher"))
        fetcher = ActualsFetcher(manager=manager, cache_ttl_seconds=30.0)

        snapshot = fetcher.fetch(
            symbol="600519",
            market="cn",
            as_of=date(2026, 4, 10),
            end=date(2026, 4, 13),
        )

        self.assertEqual(snapshot.status, ACTUALS_STATUS_OK)
        self.assertTrue(snapshot.ok)
        self.assertFalse(snapshot.data_unavailable)
        self.assertIsNotNone(snapshot.as_of_bar)
        self.assertIsNotNone(snapshot.end_bar)
        assert snapshot.as_of_bar is not None
        assert snapshot.end_bar is not None
        self.assertEqual(snapshot.as_of_bar.close, 10.5)
        self.assertEqual(snapshot.end_bar.close, 11.55)
        self.assertAlmostEqual(snapshot.return_pct or 0.0, 10.0, places=6)
        self.assertEqual(snapshot.as_of_bar.volume, 1000.0)
        self.assertEqual(snapshot.source, "EfinanceFetcher")
        self.assertFalse(snapshot.from_cache)
        self.assertEqual(len(manager.calls), 1)
        self.assertEqual(manager.calls[0]["stock_code"], "600519")
        self.assertIsNotNone(manager.calls[0]["start_date"])
        self.assertIsNotNone(manager.calls[0]["end_date"])


class ActualsFetcherFailureTests(unittest.TestCase):
    def test_provider_down_returns_typed_status_without_prices(self) -> None:
        manager = _RecordingManager(
            error=DataFetchError("all providers failed", provider_failure_count=3)
        )
        fetcher = ActualsFetcher(manager=manager, max_attempts=1)

        snapshot = fetcher.fetch(
            symbol="600519",
            market="cn",
            as_of=date(2026, 4, 10),
        )

        self.assertEqual(snapshot.status, ACTUALS_STATUS_PROVIDER_DOWN)
        self.assertTrue(snapshot.data_unavailable)
        self.assertEqual(snapshot.reason, REASON_PROVIDER_FAILURE)
        self.assertTrue(snapshot.retryable)
        self.assertIsNone(snapshot.as_of_bar)
        self.assertIsNone(snapshot.end_bar)
        self.assertIsNone(snapshot.return_pct)
        self.assertEqual(snapshot.provider_failure_count, 3)
        self.assertEqual(len(manager.calls), 1)

    def test_data_source_unavailable_is_provider_down(self) -> None:
        manager = _RecordingManager(error=DataSourceUnavailableError("circuit open"))
        fetcher = ActualsFetcher(manager=manager, max_attempts=1)

        snapshot = fetcher.fetch(symbol="AAPL", market="us", as_of="2026-04-10")

        self.assertEqual(snapshot.status, ACTUALS_STATUS_PROVIDER_DOWN)
        self.assertTrue(snapshot.data_unavailable)
        self.assertIsNone(snapshot.as_of_bar)
        self.assertIsNone(snapshot.return_pct)

    def test_empty_frame_is_empty_not_ok(self) -> None:
        manager = _RecordingManager(result=(pd.DataFrame(), "AkshareFetcher"))
        fetcher = ActualsFetcher(manager=manager)

        snapshot = fetcher.fetch(symbol="600519", as_of=date(2026, 4, 10))

        self.assertEqual(snapshot.status, ACTUALS_STATUS_EMPTY)
        self.assertTrue(snapshot.data_unavailable)
        self.assertIsNone(snapshot.as_of_bar)
        self.assertIsNone(snapshot.return_pct)

    def test_non_finite_close_rejected_as_data_unavailable(self) -> None:
        frame = _daily_frame(
            [
                ("2026-04-10", 10.0, 11.0, 9.5, math.nan, 1000.0),
            ]
        )
        frame.loc[0, "close"] = float("inf")
        manager = _RecordingManager(result=(frame, "YfinanceFetcher"))
        fetcher = ActualsFetcher(manager=manager)

        snapshot = fetcher.fetch(
            symbol="AAPL",
            market="us",
            as_of=date(2026, 4, 10),
            field_set=(FIELD_OHLC,),
        )

        self.assertEqual(snapshot.status, ACTUALS_STATUS_DATA_UNAVAILABLE)
        self.assertEqual(snapshot.reason, REASON_NON_FINITE)
        self.assertTrue(snapshot.data_unavailable)
        self.assertIsNone(snapshot.as_of_bar)
        self.assertIsNone(snapshot.return_pct)
        self.assertFalse(snapshot.ok)

    def test_halted_session_is_typed_not_scoreable_hit(self) -> None:
        frame = _daily_frame(
            [
                ("2026-04-09", 10.0, 10.5, 9.8, 10.2, 2000.0),
                ("2026-04-10", 10.2, 10.2, 10.2, 10.2, 0.0),
            ]
        )
        manager = _RecordingManager(result=(frame, "TushareFetcher"))
        fetcher = ActualsFetcher(manager=manager)

        snapshot = fetcher.fetch(
            symbol="600519",
            market="cn",
            as_of=date(2026, 4, 10),
        )

        self.assertEqual(snapshot.status, ACTUALS_STATUS_HALTED)
        self.assertTrue(snapshot.data_unavailable)
        self.assertFalse(snapshot.ok)
        self.assertIsNotNone(snapshot.as_of_bar)
        self.assertIsNone(snapshot.return_pct)

    def test_missing_end_bar_is_retryable_not_stale_zero_return(self) -> None:
        frame = _daily_frame(
            [("2026-04-10", 10.0, 11.0, 9.5, 10.5, 1000.0)]
        )
        manager = _RecordingManager(result=(frame, "EfinanceFetcher"))
        fetcher = ActualsFetcher(manager=manager)

        snapshot = fetcher.fetch(
            symbol="600519",
            market="cn",
            as_of=date(2026, 4, 10),
            end=date(2026, 4, 13),
        )

        self.assertEqual(snapshot.status, ACTUALS_STATUS_DATA_UNAVAILABLE)
        self.assertEqual(snapshot.reason, REASON_NO_BAR_FOR_END)
        self.assertTrue(snapshot.retryable)
        self.assertIsNone(snapshot.as_of_bar)
        self.assertIsNone(snapshot.end_bar)
        self.assertIsNone(snapshot.return_pct)

    def test_halted_end_session_is_not_scored_as_sideways(self) -> None:
        frame = _daily_frame(
            [
                ("2026-04-10", 10.0, 10.5, 9.8, 10.2, 2000.0),
                ("2026-04-13", 10.2, 10.2, 10.2, 10.2, 0.0),
            ]
        )
        manager = _RecordingManager(result=(frame, "TushareFetcher"))
        fetcher = ActualsFetcher(manager=manager)

        snapshot = fetcher.fetch(
            symbol="600519",
            market="cn",
            as_of=date(2026, 4, 10),
            end=date(2026, 4, 13),
        )

        self.assertEqual(snapshot.status, ACTUALS_STATUS_HALTED)
        self.assertIsNone(snapshot.return_pct)
        self.assertTrue(snapshot.data_unavailable)

    def test_missing_requested_volume_fails_closed(self) -> None:
        frame = _daily_frame(
            [("2026-04-10", 10.0, 11.0, 9.5, 10.5, 1000.0)]
        ).drop(columns=["volume"])
        manager = _RecordingManager(result=(frame, "EfinanceFetcher"))
        fetcher = ActualsFetcher(manager=manager)

        snapshot = fetcher.fetch(
            symbol="600519",
            market="cn",
            as_of=date(2026, 4, 10),
            field_set=(FIELD_VOLUME,),
        )

        self.assertEqual(snapshot.status, ACTUALS_STATUS_DATA_UNAVAILABLE)
        self.assertEqual(snapshot.reason, REASON_NON_FINITE)
        self.assertIsNone(snapshot.as_of_bar)


class ActualsFetcherCacheCoalesceTests(unittest.TestCase):
    def test_cache_hit_avoids_second_provider_call(self) -> None:
        frame = _daily_frame(
            [
                ("2026-04-10", 10.0, 11.0, 9.5, 10.5, 1000.0),
            ]
        )
        manager = _RecordingManager(result=(frame, "EfinanceFetcher"))
        fetcher = ActualsFetcher(manager=manager, cache_ttl_seconds=60.0)

        first = fetcher.fetch(symbol="600519", market="cn", as_of=date(2026, 4, 10))
        second = fetcher.fetch(symbol="600519", market="cn", as_of=date(2026, 4, 10))

        self.assertEqual(first.status, ACTUALS_STATUS_OK)
        self.assertEqual(second.status, ACTUALS_STATUS_OK)
        self.assertFalse(first.from_cache)
        self.assertTrue(second.from_cache)
        self.assertEqual(len(manager.calls), 1)
        self.assertEqual(first.cache_key, second.cache_key)
        self.assertTrue(
            str(first.cache_key or "").startswith("actuals:cn:600519:2026-04-10:")
        )

    def test_fetch_many_coalesces_identical_keys(self) -> None:
        frame = _daily_frame(
            [
                ("2026-04-10", 10.0, 11.0, 9.5, 10.5, 1000.0),
                ("2026-04-11", 10.5, 11.5, 10.0, 11.0, 1200.0),
            ]
        )
        manager = _RecordingManager(result=(frame, "EfinanceFetcher"))
        fetcher = ActualsFetcher(manager=manager, cache_ttl_seconds=60.0)

        results = fetcher.fetch_many(
            [
                ActualsRequest(
                    symbol="600519",
                    market="cn",
                    as_of=date(2026, 4, 10),
                    end=date(2026, 4, 11),
                ),
                {
                    "symbol": "600519",
                    "market": "cn",
                    "as_of": "2026-04-10",
                    "end": "2026-04-11",
                },
                ActualsRequest(
                    symbol="AAPL",
                    market="us",
                    as_of=date(2026, 4, 10),
                ),
            ]
        )

        self.assertEqual(len(results), 3)
        self.assertEqual(results[0].status, ACTUALS_STATUS_OK)
        self.assertEqual(results[1].status, ACTUALS_STATUS_OK)
        self.assertEqual(len(manager.calls), 2)
        cn_calls = [c for c in manager.calls if c["stock_code"] == "600519"]
        us_calls = [c for c in manager.calls if c["stock_code"] == "AAPL"]
        self.assertEqual(len(cn_calls), 1)
        self.assertEqual(len(us_calls), 1)

    def test_inflight_coalesce_merges_concurrent_same_key(self) -> None:
        frame = _daily_frame(
            [
                ("2026-04-10", 10.0, 11.0, 9.5, 10.5, 1000.0),
            ]
        )
        started = threading.Event()
        release = threading.Event()
        manager = _RecordingManager(
            result=(frame, "EfinanceFetcher"),
            delay_event=started,
            release_event=release,
        )
        fetcher = ActualsFetcher(manager=manager, cache_ttl_seconds=60.0)

        results: List[Any] = [None, None]
        errors: List[BaseException] = []

        def _worker(index: int) -> None:
            try:
                results[index] = fetcher.fetch(
                    symbol="600519",
                    market="cn",
                    as_of=date(2026, 4, 10),
                )
            except BaseException as exc:  # collect for assertion
                errors.append(exc)

        threads = [
            threading.Thread(target=_worker, args=(0,)),
            threading.Thread(target=_worker, args=(1,)),
        ]
        for thread in threads:
            thread.start()
        self.assertTrue(started.wait(timeout=2.0))
        release.set()
        for thread in threads:
            thread.join(timeout=5.0)

        self.assertEqual(errors, [])
        self.assertIsNotNone(results[0])
        self.assertIsNotNone(results[1])
        self.assertEqual(results[0].status, ACTUALS_STATUS_OK)
        self.assertEqual(results[1].status, ACTUALS_STATUS_OK)
        self.assertEqual(len(manager.calls), 1)

    def test_retryable_provider_failure_is_cached_as_short_cooldown(self) -> None:
        manager = _RecordingManager(
            error=DataFetchError("down", provider_failure_count=2)
        )
        fetcher = ActualsFetcher(manager=manager, max_attempts=1, cache_ttl_seconds=60.0)

        first = fetcher.fetch(symbol="600519", as_of=date(2026, 4, 10))
        second = fetcher.fetch(symbol="600519", as_of=date(2026, 4, 10))

        self.assertEqual(first.status, ACTUALS_STATUS_PROVIDER_DOWN)
        self.assertEqual(second.status, ACTUALS_STATUS_PROVIDER_DOWN)
        self.assertFalse(first.from_cache)
        self.assertTrue(second.from_cache)
        self.assertEqual(len(manager.calls), 1)

    def test_timeout_does_not_start_overlapping_outer_retry(self) -> None:
        frame = _daily_frame(
            [("2026-04-10", 10.0, 11.0, 9.5, 10.5, 1000.0)]
        )
        started = threading.Event()
        release = threading.Event()
        manager = _RecordingManager(
            result=(frame, "slow-provider"),
            delay_event=started,
            release_event=release,
        )
        fetcher = ActualsFetcher(
            manager=manager,
            request_timeout_seconds=0.01,
            max_attempts=3,
            cache_ttl_seconds=60.0,
        )

        first = fetcher.fetch(symbol="600519", as_of=date(2026, 4, 10))
        self.assertTrue(started.is_set())
        second = fetcher.fetch(symbol="600519", as_of=date(2026, 4, 10))
        release.set()

        self.assertEqual(first.status, ACTUALS_STATUS_DATA_UNAVAILABLE)
        self.assertTrue(first.retryable)
        self.assertTrue(second.from_cache)
        self.assertEqual(len(manager.calls), 1)


class ActualsFetcherContractTests(unittest.TestCase):
    def test_real_manager_fallback_path_reaches_backup_provider(self) -> None:
        frame = _daily_frame(
            [("2026-04-10", 10.0, 11.0, 9.5, 10.5, 1000.0)]
        )
        primary = _OfflineProvider(
            "EfinanceFetcher",
            0,
            TimeoutError("primary down"),
        )
        backup = _OfflineProvider("TencentFetcher", 1, frame)
        manager = DataFetcherManager(fetchers=[primary, backup])
        breaker = CircuitBreaker(
            failure_threshold=99,
            cooldown_seconds=60.0,
            health_window_size=20,
        )
        fetcher = ActualsFetcher(manager=manager, max_attempts=1)

        with patch.object(DataFetcherManager, "_daily_source_health", breaker):
            snapshot = fetcher.fetch(
                symbol="600519",
                market="cn",
                as_of=date(2026, 4, 10),
            )

        self.assertEqual(snapshot.status, ACTUALS_STATUS_OK)
        self.assertEqual(snapshot.source, "TencentFetcher")
        self.assertEqual((primary.calls, backup.calls), (1, 1))

    def test_uses_injected_manager_not_agent_tools(self) -> None:
        """Guardrail: ActualsFetcher must call manager.get_daily_data only."""
        frame = _daily_frame(
            [
                ("2026-04-10", 1.0, 1.1, 0.9, 1.05, 10.0),
            ]
        )
        manager = MagicMock()
        manager.get_daily_data.return_value = (frame, "mock-provider")
        fetcher = ActualsFetcher(
            manager=manager,
            request_timeout_seconds=5.0,
            max_attempts=1,
        )

        snapshot = fetcher.fetch(
            symbol="00700",
            market="hk",
            as_of=date(2026, 4, 10),
            field_set=(FIELD_OHLC, FIELD_RETURN, FIELD_VOLUME),
        )

        self.assertEqual(snapshot.status, ACTUALS_STATUS_OK)
        manager.get_daily_data.assert_called_once()
        self.assertEqual(manager.method_calls[0][0], "get_daily_data")

    def test_invalid_window_is_data_unavailable(self) -> None:
        manager = _RecordingManager(
            result=(_daily_frame([("2026-04-10", 1, 1, 1, 1, 1)]), "x")
        )
        fetcher = ActualsFetcher(manager=manager)

        snapshot = fetcher.fetch(
            symbol="600519",
            as_of=date(2026, 4, 12),
            end=date(2026, 4, 10),
        )

        self.assertEqual(snapshot.status, ACTUALS_STATUS_DATA_UNAVAILABLE)
        self.assertEqual(len(manager.calls), 0)

    def test_invalid_batch_item_does_not_abort_valid_neighbor(self) -> None:
        frame = _daily_frame(
            [("2026-04-10", 1.0, 1.1, 0.9, 1.05, 10.0)]
        )
        manager = _RecordingManager(result=(frame, "provider"))
        fetcher = ActualsFetcher(manager=manager)

        results = fetcher.fetch_many(
            [
                {"symbol": "600519", "as_of": "not-a-date"},
                ActualsRequest(
                    symbol="600519",
                    market="cn",
                    as_of=datetime(2026, 4, 10, 12, 30),  # type: ignore[arg-type]
                ),
            ]
        )

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].status, ACTUALS_STATUS_DATA_UNAVAILABLE)
        self.assertEqual(results[0].reason, REASON_INVALID_WINDOW)
        self.assertEqual(results[1].status, ACTUALS_STATUS_OK)
        self.assertEqual(results[1].as_of, date(2026, 4, 10))
        self.assertEqual(len(manager.calls), 1)

    def test_future_end_is_retryable_without_provider_call(self) -> None:
        manager = _RecordingManager(
            result=(_daily_frame([("2026-04-10", 1, 1, 1, 1, 1)]), "x")
        )
        fetcher = ActualsFetcher(
            manager=manager,
            now_utc=lambda: datetime(2026, 4, 10, 12, tzinfo=timezone.utc),
        )

        snapshot = fetcher.fetch(
            symbol="600519",
            as_of=date(2026, 4, 10),
            end=date(2026, 4, 11),
        )

        self.assertEqual(snapshot.status, ACTUALS_STATUS_DATA_UNAVAILABLE)
        self.assertEqual(snapshot.reason, REASON_END_NOT_REACHED)
        self.assertTrue(snapshot.retryable)
        self.assertEqual(manager.calls, [])

    def test_constructor_rejects_non_finite_limits(self) -> None:
        with self.assertRaisesRegex(ValueError, "cache_ttl_seconds"):
            ActualsFetcher(cache_ttl_seconds=float("nan"))
        with self.assertRaisesRegex(ValueError, "request_timeout_seconds"):
            ActualsFetcher(request_timeout_seconds=float("inf"))

    def test_snapshot_contract_rejects_prices_on_provider_failure(self) -> None:
        bar = ActualsBar(trade_date=date(2026, 4, 10), close=10.0)
        with self.assertRaisesRegex(ValueError, "must not carry price bars"):
            ActualsSnapshot(
                symbol="600519",
                market="cn",
                as_of=date(2026, 4, 10),
                end=date(2026, 4, 10),
                status=ACTUALS_STATUS_PROVIDER_DOWN,
                field_set=(FIELD_RETURN,),
                as_of_bar=bar,
            )

    def test_cache_key_formula(self) -> None:
        key = ActualsFetcher.build_cache_key(
            market="CN",
            symbol="600519",
            as_of=date(2026, 4, 10),
            end=date(2026, 4, 10),
            field_set=(FIELD_VOLUME, FIELD_OHLC),
        )
        self.assertEqual(key, "actuals:cn:600519:2026-04-10:2026-04-10:ohlc,volume")


if __name__ == "__main__":
    unittest.main()
