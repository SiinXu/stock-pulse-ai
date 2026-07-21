"""Deterministic coverage for the layered daily provider cache."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pandas as pd
import pytest

from data_provider.base import DataFetcherManager
from data_provider.daily_cache import DailyCacheConfig, DailyDataCache
from src.services.run_diagnostics import (
    activate_run_diagnostic_context,
    current_diagnostic_snapshot,
    reset_run_diagnostic_context,
)


class _Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _Provider:
    def __init__(
        self,
        outcomes: list[object],
        *,
        name: str = "CacheTestProvider",
        priority: int = 0,
    ) -> None:
        self.name = name
        self.priority = priority
        self.outcomes = list(outcomes)
        self.calls = 0

    def get_daily_data(self, **_kwargs) -> Optional[pd.DataFrame]:
        self.calls += 1
        if not self.outcomes:
            raise AssertionError("provider should not have been called")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        if outcome is None:
            return None
        assert isinstance(outcome, pd.DataFrame)
        return outcome.copy(deep=True)


def _frame(close: float = 10.2) -> pd.DataFrame:
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


def _manager(provider: _Provider, cache: DailyDataCache) -> DataFetcherManager:
    manager = DataFetcherManager(fetchers=[provider])
    manager._daily_data_cache = cache
    return manager


@pytest.fixture(autouse=True)
def _reset_daily_health() -> None:
    DataFetcherManager.reset_daily_source_health()
    yield
    DataFetcherManager.reset_daily_source_health()


def test_environment_defaults_enable_bounded_layered_cache(monkeypatch) -> None:
    for name in (
        "PROVIDER_DAILY_CACHE_ENABLED",
        "PROVIDER_DAILY_CACHE_DIR",
        "PROVIDER_DAILY_CACHE_MEMORY_TTL_SECONDS",
        "PROVIDER_DAILY_CACHE_PERSISTENT_TTL_SECONDS",
        "PROVIDER_DAILY_CACHE_STALE_IF_ERROR_SECONDS",
        "PROVIDER_DAILY_CACHE_MEMORY_MAX_ENTRIES",
    ):
        monkeypatch.delenv(name, raising=False)

    config = DailyCacheConfig.from_env()

    assert config.enabled is True
    assert config.directory == Path("data/provider_cache/daily")
    assert config.memory_ttl_seconds == 60.0
    assert config.persistent_ttl_seconds == 3600.0
    assert config.stale_if_error_seconds == 86400.0
    assert config.memory_max_entries == 256


def test_memory_and_persistent_hits_return_isolated_frames(tmp_path: Path) -> None:
    clock = _Clock()
    provider = _Provider([_frame()])
    manager = _manager(provider, _cache(tmp_path, clock))

    first, first_source = manager.get_daily_data("SH600519")
    first.loc[0, "close"] = 999.0
    memory_hit, memory_source = manager.get_daily_data("600519")

    assert first_source == memory_source == "CacheTestProvider"
    assert provider.calls == 1
    assert memory_hit.loc[0, "close"] == pytest.approx(10.2)
    assert memory_hit.attrs["provider_cache"] == {
        "cache_hit": True,
        "layer": "memory",
        "is_stale": False,
        "stale_seconds": 0,
        "stored_at": "1970-01-12T13:46:40+00:00",
        "source": "CacheTestProvider",
    }

    second_provider = _Provider([])
    second_manager = _manager(second_provider, _cache(tmp_path, clock))
    persistent_hit, persistent_source = second_manager.get_daily_data("600519")

    assert persistent_source == "CacheTestProvider"
    assert second_provider.calls == 0
    assert persistent_hit.loc[0, "close"] == pytest.approx(10.2)
    assert persistent_hit.attrs["provider_cache"]["layer"] == "persistent"


def test_expired_layers_fetch_and_replace_data(tmp_path: Path) -> None:
    clock = _Clock()
    provider = _Provider([_frame(10.2), _frame(11.4)])
    manager = _manager(
        provider,
        _cache(
            tmp_path,
            clock,
            memory_ttl=5.0,
            persistent_ttl=10.0,
            stale_if_error=0.0,
        ),
    )

    first, _ = manager.get_daily_data("600519")
    clock.advance(11.0)
    refreshed, _ = manager.get_daily_data("600519")

    assert first.loc[0, "close"] == pytest.approx(10.2)
    assert refreshed.loc[0, "close"] == pytest.approx(11.4)
    assert refreshed.attrs["provider_cache"]["cache_hit"] is False
    assert provider.calls == 2
    assert manager.get_daily_cache_stats()["misses"] == 2


def test_symbol_invalidation_removes_both_layers(tmp_path: Path) -> None:
    clock = _Clock()
    provider = _Provider([_frame(10.2), _frame(12.5)])
    manager = _manager(provider, _cache(tmp_path, clock))

    manager.get_daily_data("600519")
    removed = manager.invalidate_daily_cache("SH600519")
    refreshed, _ = manager.get_daily_data("600519")

    assert removed == 2
    assert provider.calls == 2
    assert refreshed.loc[0, "close"] == pytest.approx(12.5)


@pytest.mark.parametrize(
    ("symbol", "provider_name", "priority"),
    [
        ("600519", "CacheTestProvider", 0),
        ("AAPL", "FinnhubFetcher", 2),
    ],
    ids=["generic-route", "us-route"],
)
def test_stale_data_is_used_only_after_provider_failure(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    symbol: str,
    provider_name: str,
    priority: int,
) -> None:
    clock = _Clock()
    provider = _Provider(
        [_frame(), TimeoutError("upstream unavailable")],
        name=provider_name,
        priority=priority,
    )
    manager = _manager(
        provider,
        _cache(
            tmp_path,
            clock,
            memory_ttl=5.0,
            persistent_ttl=10.0,
            stale_if_error=60.0,
        ),
    )
    manager.get_daily_data(symbol)
    clock.advance(11.0)

    caplog.set_level(logging.INFO)
    token = activate_run_diagnostic_context(trace_id="trace-daily-cache-stale")
    try:
        stale, source = manager.get_daily_data(symbol)
        diagnostics = current_diagnostic_snapshot()
    finally:
        reset_run_diagnostic_context(token)

    metadata = stale.attrs["provider_cache"]
    assert source == provider_name
    assert provider.calls == 2
    assert metadata["cache_hit"] is True
    assert metadata["is_stale"] is True
    assert metadata["stale_seconds"] == 11
    assert diagnostics["provider_runs"][-1]["cache_hit"] is True
    assert diagnostics["provider_runs"][-1]["stale_seconds"] == 11
    assert manager.get_daily_cache_stats()["stale_hits"] == 1
    assert "provider_cache event=stale_hit" in caplog.text
    assert "provider_failover event=stale_cache" in caplog.text


def test_corrupt_persistent_entry_fails_open_to_provider(tmp_path: Path) -> None:
    clock = _Clock()
    first_provider = _Provider([_frame(10.2)])
    first_manager = _manager(first_provider, _cache(tmp_path, clock))
    first_manager.get_daily_data("600519")
    cache_file = next(tmp_path.glob("*.json"))
    cache_file.write_text("not-json", encoding="utf-8")

    replacement_provider = _Provider([_frame(12.1)])
    replacement_manager = _manager(replacement_provider, _cache(tmp_path, clock))
    refreshed, source = replacement_manager.get_daily_data("600519")

    assert source == "CacheTestProvider"
    assert replacement_provider.calls == 1
    assert refreshed.loc[0, "close"] == pytest.approx(12.1)
    assert refreshed.attrs["provider_cache"]["cache_hit"] is False


def test_cache_key_includes_explicit_window_and_days(tmp_path: Path) -> None:
    clock = _Clock()
    provider = _Provider([_frame(10.2), _frame(10.8)])
    manager = _manager(provider, _cache(tmp_path, clock))

    first, _ = manager.get_daily_data(
        "600519",
        start_date="2026-01-01",
        end_date="2026-07-20",
        days=30,
    )
    second, _ = manager.get_daily_data(
        "600519",
        start_date="2026-01-01",
        end_date="2026-07-20",
        days=31,
    )

    assert first.loc[0, "close"] == pytest.approx(10.2)
    assert second.loc[0, "close"] == pytest.approx(10.8)
    assert provider.calls == 2
    assert DataFetcherManager._daily_cache_key("aapl", None, "2026-07-20", 30) == (
        DataFetcherManager._daily_cache_key("AAPL", None, "2026-07-20", 30)
    )
