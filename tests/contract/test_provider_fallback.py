# -*- coding: utf-8 -*-
"""Issue #1069 — offline contracts for provider fallback, circuit, and cache.

This suite fills **gaps** left by the existing offline coverage. It does not
re-assert cases already locked elsewhere. Inventory (main baseline):

| Contract | Existing coverage | This file |
| --- | --- | --- |
| Primary fails → secondary used | ``tests/data_provider/test_provider_fallback_contract.py`` | multi-hop order (3 providers) |
| All fail → typed ``DataFetchError`` | ``test_provider_fallback_contract.py`` | multi-provider + ``provider_failure_count`` |
| All fail → stale cache (enabled) | ``test_daily_provider_cache.py`` (single provider) | multi-provider chain then stale |
| Open circuit → skip unhealthy | ``test_provider_resilience.py`` | open/close with ordered failover; all-open typed fail |
| Partial / missing fields | fixtures + validation suite | manager-level reject + all-missing typed fail |
| Cache hit + expiry | ``test_daily_provider_cache.py`` | multi-provider: hit skips chain; expiry re-enters |
| Single source failure does not abort analysis | single-request failover | multi-symbol isolation |

Hard rules:
- Exercise the real ``DataFetcherManager`` fallback / circuit / cache seams.
- Providers are offline stubs (no live network).
- Do not mock manager orchestration methods under test.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional
from unittest.mock import patch

import pandas as pd
import pytest

from src.data_provider.base import DataFetchError, DataFetcherManager
from src.data_provider.daily_cache import DailyCacheConfig, DailyDataCache
from src.data_provider.realtime_types import CircuitBreaker
from src.services.run_diagnostics import (
    activate_run_diagnostic_context,
    current_diagnostic_snapshot,
    reset_run_diagnostic_context,
)


class _Clock:
    def __init__(self, now: float = 1_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _SequencedProvider:
    """Minimal DataProvider-shaped stub; outcomes script one call each."""

    def __init__(
        self,
        name: str,
        priority: int,
        outcomes: list[object],
        *,
        per_symbol: Optional[dict[str, list[object]]] = None,
    ) -> None:
        self.name = name
        self.priority = priority
        self.outcomes = list(outcomes)
        self.per_symbol = {
            key: list(value) for key, value in (per_symbol or {}).items()
        }
        self.calls = 0
        self.call_codes: list[str] = []

    def get_daily_data(self, stock_code: str = "", **_kwargs) -> Optional[pd.DataFrame]:
        self.calls += 1
        self.call_codes.append(str(stock_code))
        queue = self.per_symbol.get(str(stock_code))
        if queue is None:
            queue = self.outcomes
        if not queue:
            raise AssertionError(f"{self.name} called more times than scripted")
        outcome = queue.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        if outcome is None:
            return None
        assert isinstance(outcome, pd.DataFrame)
        return outcome.copy(deep=True)


def _ok_frame(close: float = 10.2) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": [pd.Timestamp("2026-07-20")],
            "open": [10.0],
            "high": [10.5],
            "low": [9.8],
            "close": [close],
            "volume": [1000],
            "amount": [10200],
            "pct_chg": [2.0],
        }
    )


def _partial_missing_close() -> pd.DataFrame:
    """Non-empty frame that omits a required STANDARD_COLUMNS field."""
    return pd.DataFrame(
        {
            "date": [pd.Timestamp("2026-07-20")],
            "open": [10.0],
            "high": [10.5],
            "low": [9.8],
            "volume": [1000],
            "amount": [10200],
            "pct_chg": [2.0],
        }
    )


def _fresh_breaker(
    *,
    failure_threshold: int = 99,
    cooldown_seconds: float = 60.0,
    clock: Optional[_Clock] = None,
) -> CircuitBreaker:
    kwargs: dict[str, object] = {
        "failure_threshold": failure_threshold,
        "cooldown_seconds": cooldown_seconds,
        "health_window_size": 20,
    }
    if clock is not None:
        kwargs["clock"] = clock
    return CircuitBreaker(**kwargs)


def _cache(
    directory: Path,
    clock: _Clock,
    *,
    memory_ttl: float = 5.0,
    persistent_ttl: float = 30.0,
    stale_if_error: float = 60.0,
) -> DailyDataCache:
    return DailyDataCache(
        DailyCacheConfig(
            enabled=True,
            directory=directory,
            memory_ttl_seconds=memory_ttl,
            persistent_ttl_seconds=persistent_ttl,
            stale_if_error_seconds=stale_if_error,
            memory_max_entries=8,
        ),
        clock=clock,
    )


@pytest.fixture(autouse=True)
def _reset_manager_health() -> None:
    from src.application_services import reset_application_services
    from src.config import Config

    reset_application_services()
    Config.reset_instance()
    DataFetcherManager.reset_daily_source_health()
    yield
    DataFetcherManager.reset_daily_source_health()
    reset_application_services()
    Config.reset_instance()


# ---------------------------------------------------------------------------
# Fallback order (multi-hop priority chain)
# ---------------------------------------------------------------------------


def test_multi_hop_priority_order_tries_providers_in_sequence() -> None:
    """Priority 0 → 1 → 2: earlier failures continue; final source succeeds.

    Asserts the real manager fallback chain (not a mocked switch), including
    diagnostic ``fallback_to`` links between hops.
    """
    p0 = _SequencedProvider("EfinanceFetcher", 0, [TimeoutError("p0 down")])
    p1 = _SequencedProvider("TencentFetcher", 1, [pd.DataFrame()])
    p2 = _SequencedProvider("AkshareFetcher", 2, [_ok_frame(13.5)])
    manager = DataFetcherManager(fetchers=[p0, p1, p2])

    with patch.object(DataFetcherManager, "_daily_source_health", _fresh_breaker()):
        token = activate_run_diagnostic_context(
            trace_id="trace-1069-multi-hop",
            stock_code="600519",
        )
        try:
            frame, source = manager.get_daily_data("600519")
            diagnostics = current_diagnostic_snapshot()
        finally:
            reset_run_diagnostic_context(token)

    assert source == "AkshareFetcher"
    assert float(frame.iloc[0]["close"]) == pytest.approx(13.5)
    assert (p0.calls, p1.calls, p2.calls) == (1, 1, 1)

    runs = diagnostics["provider_runs"]
    assert [run["provider"] for run in runs] == [
        "EfinanceFetcher",
        "TencentFetcher",
        "AkshareFetcher",
    ]
    assert runs[0]["success"] is False
    assert runs[0]["fallback_to"] == "TencentFetcher"
    assert runs[1]["success"] is False
    assert runs[1]["fallback_to"] == "AkshareFetcher"
    assert runs[2]["success"] is True


# ---------------------------------------------------------------------------
# Partial success / missing fields → typed failure path, not silent empty
# ---------------------------------------------------------------------------


def test_missing_required_column_is_rejected_and_falls_back() -> None:
    """Manager schema gate rejects incomplete OHLCV; next priority continues.

    A non-empty frame missing ``close`` must not be returned as success.
    """
    primary = _SequencedProvider("EfinanceFetcher", 0, [_partial_missing_close()])
    backup = _SequencedProvider("TencentFetcher", 1, [_ok_frame(11.0)])
    manager = DataFetcherManager(fetchers=[primary, backup])

    with patch.object(DataFetcherManager, "_daily_source_health", _fresh_breaker()):
        token = activate_run_diagnostic_context(
            trace_id="trace-1069-missing-column",
            stock_code="600519",
        )
        try:
            frame, source = manager.get_daily_data("600519")
            diagnostics = current_diagnostic_snapshot()
        finally:
            reset_run_diagnostic_context(token)

    assert source == "TencentFetcher"
    assert "close" in frame.columns
    assert float(frame.iloc[0]["close"]) == pytest.approx(11.0)
    assert primary.calls == 1
    assert backup.calls == 1
    failed = [run for run in diagnostics["provider_runs"] if not run["success"]]
    assert failed
    assert failed[0]["provider"] == "EfinanceFetcher"
    assert failed[0]["fallback_to"] == "TencentFetcher"
    # Typed path: DataFetchError (or wrapped) — never empty success.
    assert failed[0]["error_type"] in {"DataFetchError", "ValueError", "KeyError"}
    err_blob = f"{failed[0].get('error_message') or ''} {failed[0]}".lower()
    assert "close" in err_blob


def test_all_providers_fail_without_stale_raises_typed_data_fetch_error() -> None:
    """Total chain failure with cache off remains a typed DataFetchError."""
    primary = _SequencedProvider("EfinanceFetcher", 0, [TimeoutError("t1")])
    backup = _SequencedProvider("TencentFetcher", 1, [TimeoutError("t2")])
    manager = DataFetcherManager(fetchers=[primary, backup])

    with patch.object(DataFetcherManager, "_daily_source_health", _fresh_breaker()):
        with pytest.raises(DataFetchError) as exc_info:
            manager.get_daily_data("600519")

    err = exc_info.value
    message = str(err)
    assert "600519" in message
    assert "EfinanceFetcher" in message
    assert "TencentFetcher" in message
    assert err.provider_failure_count >= 2
    assert primary.calls == 1
    assert backup.calls == 1


def test_all_providers_missing_required_columns_raise_typed_failure() -> None:
    """Every provider returning a non-empty incomplete frame is a typed failure.

    A missing ``close`` column must not become a successful empty (or partial)
    daily payload when no later source can complete the schema.
    """
    primary = _SequencedProvider("EfinanceFetcher", 0, [_partial_missing_close()])
    backup = _SequencedProvider("TencentFetcher", 1, [_partial_missing_close()])
    manager = DataFetcherManager(fetchers=[primary, backup])

    with patch.object(DataFetcherManager, "_daily_source_health", _fresh_breaker()):
        token = activate_run_diagnostic_context(
            trace_id="trace-1069-all-missing-columns",
            stock_code="600519",
        )
        try:
            with pytest.raises(DataFetchError) as exc_info:
                result = manager.get_daily_data("600519")
                pytest.fail(f"expected DataFetchError, got success: {result!r}")
            diagnostics = current_diagnostic_snapshot()
        finally:
            reset_run_diagnostic_context(token)

    err = exc_info.value
    message = str(err)
    assert "600519" in message
    assert "EfinanceFetcher" in message
    assert "TencentFetcher" in message
    assert "close" in message
    assert err.provider_failure_count >= 2
    assert primary.calls == 1
    assert backup.calls == 1
    failed = [run for run in diagnostics["provider_runs"] if not run["success"]]
    assert {run["provider"] for run in failed} >= {"EfinanceFetcher", "TencentFetcher"}
    assert all(run["error_type"] == "DataFetchError" for run in failed)
    assert all(
        "close" in (run.get("error_message_sanitized") or run.get("error_message") or "")
        for run in failed
    )


# ---------------------------------------------------------------------------
# Circuit open / close (manager seam; real CircuitBreaker)
# ---------------------------------------------------------------------------


def test_open_circuit_skips_provider_and_recovers_after_cooldown() -> None:
    """After threshold failures the open circuit is skipped; cooldown reopens it."""
    clock = _Clock(now=5_000.0)
    breaker = _fresh_breaker(failure_threshold=2, cooldown_seconds=30.0, clock=clock)
    primary = _SequencedProvider(
        "EfinanceFetcher",
        0,
        [TimeoutError("down-1"), TimeoutError("down-2"), _ok_frame(15.0)],
    )
    backup = _SequencedProvider(
        "TencentFetcher",
        1,
        [_ok_frame(10.0), _ok_frame(10.1), _ok_frame(10.2)],
    )
    manager = DataFetcherManager(fetchers=[primary, backup])

    with patch.object(DataFetcherManager, "_daily_source_health", breaker):
        for _ in range(2):
            _, source = manager.get_daily_data("600519")
            assert source == "TencentFetcher"

        health_key = DataFetcherManager._daily_health_key(primary, "cn")
        assert breaker.get_status()[health_key] == CircuitBreaker.OPEN
        assert primary.calls == 2

        token = activate_run_diagnostic_context(
            trace_id="trace-1069-circuit-open",
            stock_code="600519",
        )
        try:
            _, source = manager.get_daily_data("600519")
            diagnostics = current_diagnostic_snapshot()
        finally:
            reset_run_diagnostic_context(token)

        assert source == "TencentFetcher"
        # Open circuit must not invoke the unhealthy provider body.
        assert primary.calls == 2
        assert diagnostics["provider_runs"][0]["provider"] == "EfinanceFetcher"
        assert diagnostics["provider_runs"][0]["error_type"] == "CircuitOpen"
        assert diagnostics["provider_runs"][0]["fallback_to"] == "TencentFetcher"

        clock.advance(30.0)
        frame, source = manager.get_daily_data("600519")
        assert source == "EfinanceFetcher"
        assert float(frame.iloc[0]["close"]) == pytest.approx(15.0)
        assert primary.calls == 3
        assert breaker.get_status()[health_key] == CircuitBreaker.CLOSED


def test_all_open_circuits_raise_typed_failure_and_skip_providers() -> None:
    """When every eligible circuit is open the request fails closed.

    Provider bodies must not run during cooldown. The manager raises
    ``DataFetchError`` with per-provider ``CircuitOpen`` detail rather than
    returning an empty successful frame.
    """
    clock = _Clock(now=8_000.0)
    breaker = _fresh_breaker(failure_threshold=1, cooldown_seconds=30.0, clock=clock)
    primary = _SequencedProvider(
        "EfinanceFetcher",
        0,
        [TimeoutError("primary down"), _ok_frame(15.0)],
    )
    backup = _SequencedProvider(
        "TencentFetcher",
        1,
        [TimeoutError("backup down"), _ok_frame(16.0)],
    )
    manager = DataFetcherManager(fetchers=[primary, backup])

    with patch.object(DataFetcherManager, "_daily_source_health", breaker):
        with pytest.raises(DataFetchError):
            manager.get_daily_data("600519")
        assert primary.calls == 1
        assert backup.calls == 1
        assert breaker.get_status()[DataFetcherManager._daily_health_key(primary, "cn")] == (
            CircuitBreaker.OPEN
        )
        assert breaker.get_status()[DataFetcherManager._daily_health_key(backup, "cn")] == (
            CircuitBreaker.OPEN
        )

        token = activate_run_diagnostic_context(
            trace_id="trace-1069-all-circuits-open",
            stock_code="600519",
        )
        try:
            with pytest.raises(DataFetchError) as exc_info:
                result = manager.get_daily_data("600519")
                pytest.fail(f"expected DataFetchError, got success: {result!r}")
            diagnostics = current_diagnostic_snapshot()
        finally:
            reset_run_diagnostic_context(token)

    err = exc_info.value
    message = str(err)
    assert "600519" in message
    assert "EfinanceFetcher" in message
    assert "TencentFetcher" in message
    assert "CircuitOpen" in message
    assert err.provider_failure_count >= 2
    assert primary.calls == 1
    assert backup.calls == 1
    skipped = [run for run in diagnostics["provider_runs"] if not run["success"]]
    assert [run["provider"] for run in skipped] == ["EfinanceFetcher", "TencentFetcher"]
    assert all(run["error_type"] == "CircuitOpen" for run in skipped)


def test_all_open_circuits_use_stale_cache_when_enabled(tmp_path: Path) -> None:
    """Open circuits still degrade to eligible stale cache instead of aborting."""
    clock = _Clock()
    breaker = _fresh_breaker(failure_threshold=1, cooldown_seconds=60.0, clock=clock)
    primary = _SequencedProvider(
        "EfinanceFetcher",
        0,
        [_ok_frame(10.2), TimeoutError("primary down")],
    )
    backup = _SequencedProvider(
        "TencentFetcher",
        1,
        [TimeoutError("backup down")],
    )
    manager = DataFetcherManager(fetchers=[primary, backup])
    manager._daily_data_cache = _cache(
        tmp_path,
        clock,
        memory_ttl=5.0,
        persistent_ttl=10.0,
        stale_if_error=60.0,
    )

    with patch.object(DataFetcherManager, "_daily_source_health", breaker):
        seed, seed_source = manager.get_daily_data("600519")
        assert seed_source == "EfinanceFetcher"
        clock.advance(11.0)
        stale, source = manager.get_daily_data("600519")
        assert source == "EfinanceFetcher"
        assert float(stale.iloc[0]["close"]) == pytest.approx(10.2)
        assert stale.attrs["provider_cache"]["is_stale"] is True
        assert primary.calls == 2
        assert backup.calls == 1
        assert breaker.get_status()[DataFetcherManager._daily_health_key(primary, "cn")] == (
            CircuitBreaker.OPEN
        )
        assert breaker.get_status()[DataFetcherManager._daily_health_key(backup, "cn")] == (
            CircuitBreaker.OPEN
        )

        token = activate_run_diagnostic_context(
            trace_id="trace-1069-all-open-stale",
            stock_code="600519",
        )
        try:
            skipped_stale, skipped_source = manager.get_daily_data("600519")
            diagnostics = current_diagnostic_snapshot()
        finally:
            reset_run_diagnostic_context(token)

    assert skipped_source == "EfinanceFetcher"
    assert float(skipped_stale.iloc[0]["close"]) == pytest.approx(10.2)
    assert skipped_stale.attrs["provider_cache"]["is_stale"] is True
    # Open circuits must not re-enter provider bodies on the stale retry.
    assert primary.calls == 2
    assert backup.calls == 1
    skipped = [run for run in diagnostics["provider_runs"] if run.get("error_type") == "CircuitOpen"]
    assert {run["provider"] for run in skipped} >= {"EfinanceFetcher", "TencentFetcher"}


# ---------------------------------------------------------------------------
# Cache hit, expiry, and multi-provider stale degradation
# ---------------------------------------------------------------------------


def test_cache_hit_skips_provider_chain_and_expiry_reenters(
    tmp_path: Path,
) -> None:
    """Fresh cache hit must not call any provider; expiry re-enters the chain."""
    clock = _Clock()
    primary = _SequencedProvider("EfinanceFetcher", 0, [_ok_frame(10.2), _ok_frame(11.8)])
    backup = _SequencedProvider("TencentFetcher", 1, [_ok_frame(99.0)])
    manager = DataFetcherManager(fetchers=[primary, backup])
    manager._daily_data_cache = _cache(
        tmp_path,
        clock,
        memory_ttl=5.0,
        persistent_ttl=5.0,
        stale_if_error=0.0,
    )

    with patch.object(DataFetcherManager, "_daily_source_health", _fresh_breaker()):
        first, first_source = manager.get_daily_data("600519")
        assert first_source == "EfinanceFetcher"
        assert primary.calls == 1
        assert backup.calls == 0

        hit, hit_source = manager.get_daily_data("600519")
        assert hit_source == "EfinanceFetcher"
        assert primary.calls == 1
        assert backup.calls == 0
        assert hit.attrs["provider_cache"]["cache_hit"] is True
        assert hit.attrs["provider_cache"]["is_stale"] is False
        assert float(hit.iloc[0]["close"]) == pytest.approx(10.2)
        # Isolation: mutating the returned frame must not poison the cache.
        first.loc[0, "close"] = 999.0
        assert float(hit.iloc[0]["close"]) == pytest.approx(10.2)

        clock.advance(6.0)
        refreshed, refreshed_source = manager.get_daily_data("600519")
        assert refreshed_source == "EfinanceFetcher"
        assert primary.calls == 2
        assert backup.calls == 0
        assert float(refreshed.iloc[0]["close"]) == pytest.approx(11.8)
        assert refreshed.attrs["provider_cache"]["cache_hit"] is False


def test_all_providers_fail_uses_stale_cache_when_enabled(
    tmp_path: Path,
) -> None:
    """After a full multi-provider failure, eligible stale cache degrades open.

    Seed with primary success, expire beyond fresh TTL (still within
    stale-if-error), then fail every provider — manager must return stale
    bars rather than abort the request.
    """
    clock = _Clock()
    primary = _SequencedProvider(
        "EfinanceFetcher",
        0,
        [_ok_frame(10.2), TimeoutError("primary dead")],
    )
    backup = _SequencedProvider(
        "TencentFetcher",
        1,
        [TimeoutError("backup dead")],
    )
    manager = DataFetcherManager(fetchers=[primary, backup])
    manager._daily_data_cache = _cache(
        tmp_path,
        clock,
        memory_ttl=5.0,
        persistent_ttl=10.0,
        stale_if_error=60.0,
    )

    with patch.object(DataFetcherManager, "_daily_source_health", _fresh_breaker()):
        seed, seed_source = manager.get_daily_data("600519")
        assert seed_source == "EfinanceFetcher"
        assert float(seed.iloc[0]["close"]) == pytest.approx(10.2)
        # Backup must not have been needed on the seed path.
        assert backup.calls == 0

        clock.advance(11.0)
        token = activate_run_diagnostic_context(
            trace_id="trace-1069-multi-stale",
            stock_code="600519",
        )
        try:
            stale, source = manager.get_daily_data("600519")
            diagnostics = current_diagnostic_snapshot()
        finally:
            reset_run_diagnostic_context(token)

    meta = stale.attrs["provider_cache"]
    assert source == "EfinanceFetcher"
    assert float(stale.iloc[0]["close"]) == pytest.approx(10.2)
    assert meta["cache_hit"] is True
    assert meta["is_stale"] is True
    assert meta["stale_seconds"] >= 11
    # Full chain was attempted before stale degradation.
    assert primary.calls == 2
    assert backup.calls == 1
    assert manager.get_daily_cache_stats()["stale_hits"] == 1
    # Diagnostics record the failed provider runs that preceded stale use.
    failed = [run for run in diagnostics["provider_runs"] if not run["success"]]
    assert {run["provider"] for run in failed} >= {"EfinanceFetcher", "TencentFetcher"}


# ---------------------------------------------------------------------------
# Single-source failure does not interrupt overall analysis (multi-symbol)
# ---------------------------------------------------------------------------


def test_single_source_failure_does_not_abort_multi_symbol_analysis() -> None:
    """One symbol's primary failure must not poison a later symbol request.

    Models the analysis-batch contract: per-symbol failover, independent
    success for the next code on the same manager instance.
    """
    primary = _SequencedProvider(
        "EfinanceFetcher",
        0,
        [],
        per_symbol={
            "600519": [TimeoutError("primary only for 600519")],
            "600520": [_ok_frame(20.0)],
        },
    )
    backup = _SequencedProvider(
        "TencentFetcher",
        1,
        [],
        per_symbol={
            "600519": [_ok_frame(10.5)],
            "600520": [_ok_frame(99.0)],  # must not be required
        },
    )
    manager = DataFetcherManager(fetchers=[primary, backup])

    with patch.object(DataFetcherManager, "_daily_source_health", _fresh_breaker()):
        frame_a, source_a = manager.get_daily_data("600519")
        frame_b, source_b = manager.get_daily_data("600520")

    assert source_a == "TencentFetcher"
    assert float(frame_a.iloc[0]["close"]) == pytest.approx(10.5)
    assert source_b == "EfinanceFetcher"
    assert float(frame_b.iloc[0]["close"]) == pytest.approx(20.0)
    assert primary.calls == 2
    # Backup used only for the failed primary symbol.
    assert backup.calls == 1
    assert backup.call_codes == ["600519"]
