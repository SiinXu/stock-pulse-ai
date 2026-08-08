"""Local-first market data modes (auto / local_only / refresh) for daily_cache."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd
import pytest

from data_provider.daily_cache import (
    DailyCacheConfig,
    DailyCacheKey,
    DailyDataCache,
    LocalDataMissingError,
    MarketDataFetchMode,
    parse_market_data_fetch_mode,
)


class _Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


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


def _key(
    symbol: str = "600519",
    *,
    start_date: str = "2026-01-01",
    end_date: str = "2026-07-20",
    days: int = 30,
) -> DailyCacheKey:
    return DailyCacheKey(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        days=days,
    )


def _cache(
    directory: Path,
    clock: _Clock,
    *,
    mode: MarketDataFetchMode = MarketDataFetchMode.AUTO,
    memory_ttl: float = 5.0,
    persistent_ttl: float = 30.0,
    stale_if_error: float = 60.0,
    enabled: bool = True,
) -> DailyDataCache:
    return DailyDataCache(
        DailyCacheConfig(
            enabled=enabled,
            directory=directory,
            memory_ttl_seconds=memory_ttl,
            persistent_ttl_seconds=persistent_ttl,
            stale_if_error_seconds=stale_if_error,
            memory_max_entries=8,
            fetch_mode=mode,
        ),
        clock=clock,
    )


class _NetworkProbe:
    """Callable network_fetch that records invocations for zero-network proofs."""

    def __init__(
        self,
        outcomes: Optional[List[object]] = None,
        *,
        default_frame: Optional[pd.DataFrame] = None,
    ) -> None:
        self.calls = 0
        self.outcomes = list(outcomes or [])
        self.default_frame = default_frame if default_frame is not None else _frame()

    def __call__(self) -> Tuple[pd.DataFrame, str]:
        self.calls += 1
        if self.outcomes:
            outcome = self.outcomes.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            if isinstance(outcome, tuple):
                frame, source = outcome
                return frame.copy(deep=True), source
            assert isinstance(outcome, pd.DataFrame)
            return outcome.copy(deep=True), "ProbeSource"
        return self.default_frame.copy(deep=True), "ProbeSource"


def test_parse_market_data_fetch_mode_values() -> None:
    assert parse_market_data_fetch_mode(None) is MarketDataFetchMode.AUTO
    assert parse_market_data_fetch_mode("") is MarketDataFetchMode.AUTO
    assert parse_market_data_fetch_mode("auto") is MarketDataFetchMode.AUTO
    assert parse_market_data_fetch_mode("LOCAL_ONLY") is MarketDataFetchMode.LOCAL_ONLY
    assert parse_market_data_fetch_mode("local-only") is MarketDataFetchMode.LOCAL_ONLY
    assert parse_market_data_fetch_mode("refresh") is MarketDataFetchMode.REFRESH
    assert parse_market_data_fetch_mode("bogus") is MarketDataFetchMode.AUTO


def test_environment_defaults_include_auto_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "PROVIDER_DAILY_CACHE_ENABLED",
        "PROVIDER_DAILY_CACHE_DIR",
        "PROVIDER_DAILY_CACHE_MEMORY_TTL_SECONDS",
        "PROVIDER_DAILY_CACHE_PERSISTENT_TTL_SECONDS",
        "PROVIDER_DAILY_CACHE_STALE_IF_ERROR_SECONDS",
        "PROVIDER_DAILY_CACHE_MEMORY_MAX_ENTRIES",
        "PROVIDER_MARKET_DATA_MODE",
    ):
        monkeypatch.delenv(name, raising=False)

    config = DailyCacheConfig.from_env()
    assert config.fetch_mode is MarketDataFetchMode.AUTO
    assert config.enabled is True


def test_environment_reads_market_data_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROVIDER_MARKET_DATA_MODE", "local_only")
    config = DailyCacheConfig.from_env()
    assert config.fetch_mode is MarketDataFetchMode.LOCAL_ONLY


def test_auto_mode_prefers_fresh_local_without_network(tmp_path: Path) -> None:
    clock = _Clock()
    cache = _cache(tmp_path, clock, mode=MarketDataFetchMode.AUTO)
    key = _key()
    cache.store(key, _frame(10.2), "SeedSource")
    probe = _NetworkProbe()

    result = cache.resolve(key, network_fetch=probe)

    assert result.from_cache is True
    assert result.mode == "auto"
    assert result.source_name == "SeedSource"
    assert result.frame.loc[0, "close"] == pytest.approx(10.2)
    assert probe.calls == 0


def test_auto_mode_miss_calls_network_and_stores(tmp_path: Path) -> None:
    clock = _Clock()
    cache = _cache(tmp_path, clock, mode=MarketDataFetchMode.AUTO)
    key = _key()
    probe = _NetworkProbe(default_frame=_frame(11.5))

    result = cache.resolve(key, network_fetch=probe)

    assert result.from_cache is False
    assert result.mode == "auto"
    assert result.source_name == "ProbeSource"
    assert probe.calls == 1
    assert result.frame.loc[0, "close"] == pytest.approx(11.5)

    probe2 = _NetworkProbe()
    second = cache.resolve(key, network_fetch=probe2)
    assert second.from_cache is True
    assert probe2.calls == 0


def test_auto_mode_lookup_store_compatible_with_legacy_path(tmp_path: Path) -> None:
    """Existing lookup/store/use_stale contracts remain intact under default auto."""
    clock = _Clock()
    cache = _cache(
        tmp_path,
        clock,
        mode=MarketDataFetchMode.AUTO,
        memory_ttl=5.0,
        persistent_ttl=10.0,
        stale_if_error=60.0,
    )
    key = _key()
    cache.store(key, _frame(10.2), "LegacySource")

    hit = cache.lookup(key)
    assert hit.fresh is not None
    assert hit.fresh.source_name == "LegacySource"
    assert hit.stale is None

    clock.advance(11.0)
    expired = cache.lookup(key)
    assert expired.fresh is None
    assert expired.stale is not None
    assert expired.stale.is_stale is True

    reused = cache.use_stale(expired.stale)
    assert reused is not None
    assert reused.is_stale is True


def test_local_only_serves_local_store_without_network(tmp_path: Path) -> None:
    clock = _Clock()
    cache = _cache(tmp_path, clock, mode=MarketDataFetchMode.LOCAL_ONLY)
    key = _key()
    cache.store(key, _frame(9.9), "WarmSource")
    probe = _NetworkProbe()

    result = cache.resolve(key, network_fetch=probe)

    assert result.mode == "local_only"
    assert result.from_cache is True
    assert result.source_name == "WarmSource"
    assert probe.calls == 0
    assert cache.stats_snapshot()["local_only_hits"] == 1


def test_local_only_serves_aged_entry_that_would_be_stale_in_auto(
    tmp_path: Path,
) -> None:
    clock = _Clock()
    cache = _cache(
        tmp_path,
        clock,
        mode=MarketDataFetchMode.LOCAL_ONLY,
        memory_ttl=5.0,
        persistent_ttl=10.0,
        stale_if_error=5.0,
    )
    key = _key()
    cache.store(key, _frame(8.8), "AgedSource")
    clock.advance(100.0)
    probe = _NetworkProbe()

    result = cache.resolve(key, network_fetch=probe)

    assert result.from_cache is True
    assert result.is_stale is True
    assert probe.calls == 0
    assert result.frame.loc[0, "close"] == pytest.approx(8.8)


def test_local_only_miss_raises_structured_missing_and_never_networks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _Clock()
    cache = _cache(tmp_path, clock, mode=MarketDataFetchMode.LOCAL_ONLY)
    key = _key(
        "AAPL",
        start_date="2026-06-01",
        end_date="2026-07-01",
        days=20,
    )
    probe = _NetworkProbe()

    def _forbid_socket(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("socket must not be opened in local_only mode")

    monkeypatch.setattr("socket.socket", _forbid_socket)

    with pytest.raises(LocalDataMissingError) as exc_info:
        cache.resolve(
            key,
            network_fetch=probe,
            required_fields=("daily_ohlcv", "volume"),
        )

    err = exc_info.value
    assert probe.calls == 0
    payload = err.to_dict()
    assert payload == {
        "symbol": "AAPL",
        "start_date": "2026-06-01",
        "end_date": "2026-07-01",
        "days": 20,
        "fields": ["daily_ohlcv", "volume"],
        "mode": "local_only",
        "reason": "no_local_entry",
    }
    assert "symbol=AAPL" in str(err)
    assert "fields=daily_ohlcv,volume" in str(err)
    assert cache.stats_snapshot()["local_only_misses"] == 1


def test_local_only_disabled_cache_is_structured_miss(tmp_path: Path) -> None:
    clock = _Clock()
    cache = _cache(
        tmp_path,
        clock,
        mode=MarketDataFetchMode.LOCAL_ONLY,
        enabled=False,
    )
    key = _key()
    probe = _NetworkProbe()

    with pytest.raises(LocalDataMissingError) as exc_info:
        cache.resolve(key, network_fetch=probe)

    assert probe.calls == 0
    assert exc_info.value.missing.reason == "cache_disabled"


def test_local_only_never_invokes_network_even_when_callable_side_effects(
    tmp_path: Path,
) -> None:
    """P0 privacy: network_fetch must not run on hit or miss paths."""
    clock = _Clock()
    cache = _cache(tmp_path, clock, mode=MarketDataFetchMode.LOCAL_ONLY)
    key = _key()
    side_effects: List[str] = []

    def evil_network() -> Tuple[pd.DataFrame, str]:
        side_effects.append("called")
        raise RuntimeError("network path reached")

    with pytest.raises(LocalDataMissingError):
        cache.resolve(key, network_fetch=evil_network)
    assert side_effects == []

    cache.store(key, _frame(), "Local")
    result = cache.resolve(key, network_fetch=evil_network)
    assert result.from_cache is True
    assert side_effects == []


def test_refresh_mode_always_fetches_and_updates_local(tmp_path: Path) -> None:
    clock = _Clock()
    cache = _cache(tmp_path, clock, mode=MarketDataFetchMode.REFRESH)
    key = _key()
    cache.store(key, _frame(10.0), "OldSource")
    probe = _NetworkProbe(default_frame=_frame(12.3))

    result = cache.resolve(key, network_fetch=probe)

    assert result.mode == "refresh"
    assert result.from_cache is False
    assert result.source_name == "ProbeSource"
    assert result.frame.loc[0, "close"] == pytest.approx(12.3)
    assert probe.calls == 1
    assert cache.stats_snapshot()["refresh_fetches"] == 1

    local = cache.lookup_local_store(key)
    assert local is not None
    assert local.frame.loc[0, "close"] == pytest.approx(12.3)
    assert local.source_name == "ProbeSource"


def test_refresh_mode_requires_network_fetch(tmp_path: Path) -> None:
    clock = _Clock()
    cache = _cache(tmp_path, clock, mode=MarketDataFetchMode.REFRESH)
    with pytest.raises(ValueError, match="network_fetch is required"):
        cache.resolve(_key(), network_fetch=None)


def test_resolve_mode_override_ignores_config_default(tmp_path: Path) -> None:
    clock = _Clock()
    cache = _cache(tmp_path, clock, mode=MarketDataFetchMode.AUTO)
    key = _key()
    probe = _NetworkProbe()

    with pytest.raises(LocalDataMissingError):
        cache.resolve(
            key,
            network_fetch=probe,
            mode=MarketDataFetchMode.LOCAL_ONLY,
        )
    assert probe.calls == 0
