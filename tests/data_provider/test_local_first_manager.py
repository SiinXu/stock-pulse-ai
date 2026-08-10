"""End-to-end manager regressions for the local-first daily-data contract."""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import pytest

from data_provider.base import DataFetchError, DataFetcherManager
from data_provider.daily_cache import (
    DailyCacheConfig,
    DailyCacheKey,
    DailyDataCache,
    LocalDataMissingError,
    MarketDataFetchMode,
    PERSISTED_DAILY_COLUMN_ALLOWLIST,
    REQUIRED_DAILY_COLUMNS,
)


class _Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _bars(
    dates: tuple[str, ...] = ("2026-07-01", "2026-07-10", "2026-07-20"),
    *,
    close: float = 10.0,
    include_volume: bool = True,
    unexpected_secret: Optional[str] = None,
) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "date": [pd.Timestamp(value) for value in dates],
            "open": [close - 0.2 + index for index in range(len(dates))],
            "high": [close + 0.3 + index for index in range(len(dates))],
            "low": [close - 0.5 + index for index in range(len(dates))],
            "close": [close + index for index in range(len(dates))],
            "volume": [1000 + index for index in range(len(dates))],
            "amount": [10000 + index for index in range(len(dates))],
            "pct_chg": [1.0 + index for index in range(len(dates))],
        }
    )
    if not include_volume:
        frame = frame.drop(columns=["volume"])
    if unexpected_secret is not None:
        frame["api_key"] = unexpected_secret
    return frame


class _Provider:
    def __init__(
        self,
        outcomes: list[object],
        *,
        name: str = "ManagerProbe",
        priority: int = 0,
        delay: float = 0.0,
    ) -> None:
        self.outcomes = list(outcomes)
        self.name = name
        self.priority = priority
        self.delay = delay
        self.calls = 0
        self.requests: list[dict[str, object]] = []

    def get_daily_data(self, **kwargs) -> Optional[pd.DataFrame]:
        self.calls += 1
        self.requests.append(dict(kwargs))
        if self.delay:
            time.sleep(self.delay)
        if not self.outcomes:
            raise AssertionError("provider should not be called")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        if outcome is None:
            return None
        assert isinstance(outcome, pd.DataFrame)
        return outcome.copy(deep=True)


def _cache(
    directory: Path,
    clock: _Clock,
    *,
    mode: MarketDataFetchMode,
    enabled: bool = True,
    persistent_ttl: float = 30.0,
    stale_if_error: float = 60.0,
    local_only_max_age: float = 300.0,
    persistent_max_age: float = 1000.0,
    persistent_max_entries: int = 32,
) -> DailyDataCache:
    return DailyDataCache(
        DailyCacheConfig(
            enabled=enabled,
            directory=directory,
            memory_ttl_seconds=5.0,
            persistent_ttl_seconds=persistent_ttl,
            stale_if_error_seconds=stale_if_error,
            memory_max_entries=8,
            fetch_mode=mode,
            persistent_max_age_seconds=persistent_max_age,
            persistent_max_entries=persistent_max_entries,
            local_only_max_age_seconds=local_only_max_age,
            rollover_grace_days=1,
        ),
        clock=clock,
    )


def _manager(provider: _Provider, cache: DailyDataCache) -> DataFetcherManager:
    manager = DataFetcherManager(fetchers=[provider])
    manager._daily_data_cache = cache
    return manager


@pytest.fixture(autouse=True)
def _reset_health() -> None:
    from src.application_services import reset_application_services
    from src.config import Config

    reset_application_services()
    Config.reset_instance()
    DataFetcherManager.reset_daily_source_health()
    yield
    DataFetcherManager.reset_daily_source_health()
    reset_application_services()
    Config.reset_instance()


def test_manager_auto_warms_then_serves_overlap_and_restart(tmp_path: Path) -> None:
    clock = _Clock()
    provider = _Provider([_bars()])
    manager = _manager(provider, _cache(tmp_path, clock, mode=MarketDataFetchMode.AUTO))

    first, source = manager.get_daily_data(
        "SH600519", start_date="2026-07-01", end_date="2026-07-20", days=30
    )
    subset, subset_source = manager.get_daily_data(
        "600519", start_date="2026-07-10", end_date="2026-07-20", days=5
    )

    assert source == subset_source == "ManagerProbe"
    assert provider.calls == 1
    assert list(first["date"].dt.strftime("%Y-%m-%d")) == [
        "2026-07-01", "2026-07-10", "2026-07-20"
    ]
    assert list(subset["date"].dt.strftime("%Y-%m-%d")) == [
        "2026-07-10", "2026-07-20"
    ]

    restarted_provider = _Provider([])
    restarted = _manager(
        restarted_provider,
        _cache(tmp_path, clock, mode=MarketDataFetchMode.LOCAL_ONLY),
    )
    persisted, _ = restarted.get_daily_data(
        "600519", start_date="2026-07-10", end_date="2026-07-20", days=5
    )
    assert restarted_provider.calls == 0
    assert len(persisted) == 2
    assert persisted.attrs["provider_cache"]["layer"] == "persistent"


def test_manager_local_only_rejects_cached_data_that_fails_current_policy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.application_services import reset_application_services
    from src.config import Config

    clock = _Clock()
    invalid = _bars()
    invalid["close"] = invalid["close"].astype(object)
    invalid.loc[0, "close"] = "bad"
    monkeypatch.setenv("DATA_VALIDATION_ENABLED", "true")
    monkeypatch.setenv("DATA_VALIDATION_STRICT", "false")
    reset_application_services()
    Config.reset_instance()
    warm_provider = _Provider([invalid])
    warm_manager = _manager(
        warm_provider,
        _cache(tmp_path, clock, mode=MarketDataFetchMode.AUTO),
    )
    warm_manager.get_daily_data("600519")

    monkeypatch.setenv("DATA_VALIDATION_STRICT", "true")
    monkeypatch.setenv("DATA_VALIDATION_STRICT_SCOPES", "cn/equity")
    reset_application_services()
    Config.reset_instance()
    offline_provider = _Provider([])
    offline_manager = _manager(
        offline_provider,
        _cache(tmp_path, clock, mode=MarketDataFetchMode.LOCAL_ONLY),
    )

    with pytest.raises(LocalDataMissingError) as exc_info:
        offline_manager.get_daily_data("600519")

    assert exc_info.value.missing.reason == "quality_rejected"
    assert offline_provider.calls == 0
    assert offline_manager.get_daily_cache_stats()["invalidations"] >= 1


def test_manager_default_end_date_rollover_uses_covered_bars_without_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _ManagerNow(datetime):
        current = datetime(2026, 7, 20)

        @classmethod
        def now(cls, tz=None):  # type: ignore[no-untyped-def]
            value = cls.current
            return value if tz is None else value.replace(tzinfo=tz)

    monkeypatch.setattr("data_provider.base.datetime", _ManagerNow)
    clock = _Clock()
    warm_provider = _Provider([_bars()])
    warm_manager = _manager(
        warm_provider,
        _cache(tmp_path, clock, mode=MarketDataFetchMode.AUTO),
    )
    warm_manager.get_daily_data("600519", days=30)

    _ManagerNow.current = datetime(2026, 7, 21)
    provider = _Provider([])
    manager = _manager(
        provider,
        _cache(tmp_path, clock, mode=MarketDataFetchMode.LOCAL_ONLY),
    )

    frame, source = manager.get_daily_data("600519", days=30)

    assert source == "ManagerProbe"
    assert warm_provider.calls == 1
    assert provider.calls == 0
    assert list(frame["date"].dt.strftime("%Y-%m-%d")) == [
        "2026-07-01", "2026-07-10", "2026-07-20"
    ]


def test_manager_explicit_end_date_does_not_use_rollover_grace(
    tmp_path: Path,
) -> None:
    clock = _Clock()
    cache = _cache(tmp_path, clock, mode=MarketDataFetchMode.LOCAL_ONLY)
    cache.store(
        DailyCacheKey("600519", "2026-07-01", "2026-07-20", 30),
        _bars(),
        "ManagerProbe",
    )
    provider = _Provider([])
    manager = _manager(provider, cache)

    with pytest.raises(LocalDataMissingError) as exc_info:
        manager.get_daily_data(
            "600519",
            start_date="2026-07-01",
            end_date="2026-07-21",
            days=30,
        )

    assert provider.calls == 0
    assert exc_info.value.to_dict()["missing_ranges"] == [
        {"start_date": "2026-07-21", "end_date": "2026-07-21"}
    ]


def test_manager_local_only_empty_cache_is_structured_and_zero_outbound(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _Clock()
    provider = _Provider([_bars()])
    manager = _manager(
        provider,
        _cache(tmp_path, clock, mode=MarketDataFetchMode.LOCAL_ONLY),
    )

    socket_calls = 0

    def _forbid_socket(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        nonlocal socket_calls
        socket_calls += 1
        raise AssertionError("outbound probe entered")

    monkeypatch.setattr("socket.socket", _forbid_socket)
    with pytest.raises(LocalDataMissingError) as exc_info:
        manager.get_daily_data(
            "AAPL", start_date="2026-07-01", end_date="2026-07-20", days=20
        )

    payload = exc_info.value.to_dict()
    assert provider.calls == 0
    assert socket_calls == 0
    assert payload["reason"] == "no_local_entry"
    assert payload["fields"] == list(REQUIRED_DAILY_COLUMNS)
    assert payload["missing_ranges"] == [
        {"start_date": "2026-07-01", "end_date": "2026-07-20"}
    ]


def test_manager_local_only_disabled_cache_does_not_call_provider(tmp_path: Path) -> None:
    clock = _Clock()
    provider = _Provider([_bars()])
    manager = _manager(
        provider,
        _cache(
            tmp_path,
            clock,
            mode=MarketDataFetchMode.LOCAL_ONLY,
            enabled=False,
        ),
    )

    with pytest.raises(LocalDataMissingError) as exc_info:
        manager.get_daily_data(
            "600519", start_date="2026-07-01", end_date="2026-07-20"
        )
    assert exc_info.value.missing.reason == "cache_disabled"
    assert provider.calls == 0


def test_manager_local_only_reports_only_partial_fields_and_ranges(tmp_path: Path) -> None:
    clock = _Clock()
    cache = _cache(tmp_path, clock, mode=MarketDataFetchMode.LOCAL_ONLY)
    cache.store(
        DailyCacheKey("600519", "2026-07-10", "2026-07-20", 10),
        _bars(("2026-07-10", "2026-07-20"), include_volume=False),
        "PartialSource",
    )
    provider = _Provider([])
    manager = _manager(provider, cache)

    with pytest.raises(LocalDataMissingError) as exc_info:
        manager.get_daily_data(
            "600519", start_date="2026-07-01", end_date="2026-07-20", days=30
        )

    payload = exc_info.value.to_dict()
    assert provider.calls == 0
    assert payload["reason"] == "missing_fields_and_ranges"
    assert payload["fields"] == ["volume"]
    assert payload["missing_ranges"] == [
        {"start_date": "2026-07-01", "end_date": "2026-07-09"}
    ]
    assert payload["available_start_date"] == "2026-07-10"
    assert payload["available_end_date"] == "2026-07-20"


def test_manager_auto_partial_cache_fetches_once_and_replaces_coverage(tmp_path: Path) -> None:
    clock = _Clock()
    cache = _cache(tmp_path, clock, mode=MarketDataFetchMode.AUTO)
    cache.store(
        DailyCacheKey("600519", "2026-07-10", "2026-07-20", 10),
        _bars(("2026-07-10", "2026-07-20")),
        "ManagerProbe",
    )
    provider = _Provider([_bars()])
    manager = _manager(provider, cache)

    frame, _ = manager.get_daily_data(
        "600519", start_date="2026-07-01", end_date="2026-07-20", days=30
    )

    assert provider.calls == 1
    assert provider.requests[0]["start_date"] == "2026-07-01"
    assert provider.requests[0]["end_date"] == "2026-07-20"
    assert len(frame) == 3


def test_manager_rejects_incomplete_provider_schema_and_falls_back(
    tmp_path: Path,
) -> None:
    clock = _Clock()
    incomplete = _Provider(
        [_bars(include_volume=False)],
        name="IncompleteProvider",
        priority=0,
    )
    complete = _Provider([_bars()], name="CompleteProvider", priority=1)
    manager = DataFetcherManager(fetchers=[incomplete, complete])
    manager._daily_data_cache = _cache(
        tmp_path,
        clock,
        mode=MarketDataFetchMode.AUTO,
    )

    frame, source = manager.get_daily_data(
        "600519", start_date="2026-07-01", end_date="2026-07-20", days=30
    )

    assert source == "CompleteProvider"
    assert list(frame.columns) == list(REQUIRED_DAILY_COLUMNS)
    assert incomplete.calls == 1
    assert complete.calls == 1


def test_manager_auto_stale_on_total_failure_once_and_expiry(tmp_path: Path) -> None:
    clock = _Clock()
    provider = _Provider([_bars(), TimeoutError("offline"), TimeoutError("offline")])
    cache = _cache(
        tmp_path,
        clock,
        mode=MarketDataFetchMode.AUTO,
        persistent_ttl=10.0,
        stale_if_error=20.0,
    )
    manager = _manager(provider, cache)
    kwargs = {"start_date": "2026-07-01", "end_date": "2026-07-20", "days": 30}
    manager.get_daily_data("600519", **kwargs)

    clock.advance(11.0)
    stale, _ = manager.get_daily_data("600519", **kwargs)
    assert provider.calls == 2
    assert stale.attrs["provider_cache"]["is_stale"] is True
    assert manager.get_daily_cache_stats()["stale_hits"] == 1

    clock.advance(20.0)
    with pytest.raises(DataFetchError):
        manager.get_daily_data("600519", **kwargs)
    assert provider.calls == 3
    assert manager.get_daily_cache_stats()["stale_hits"] == 1


def test_manager_refresh_skips_local_fails_without_stale_and_persists_success(
    tmp_path: Path,
) -> None:
    clock = _Clock()
    key = DailyCacheKey("600519", "2026-07-01", "2026-07-20", 30)
    seed = _cache(tmp_path, clock, mode=MarketDataFetchMode.REFRESH)
    seed.store(key, _bars(close=10.0), "OldSource")
    failing = _Provider([TimeoutError("refresh failed")])
    manager = _manager(failing, seed)

    with pytest.raises(DataFetchError):
        manager.get_daily_data(
            "600519", start_date="2026-07-01", end_date="2026-07-20", days=30
        )
    assert failing.calls == 1
    assert seed.stats_snapshot()["stale_hits"] == 0

    success_provider = _Provider([_bars(close=20.0)], name="NewSource")
    success_manager = _manager(success_provider, seed)
    refreshed, source = success_manager.get_daily_data(
        "600519", start_date="2026-07-01", end_date="2026-07-20", days=30
    )
    assert source == "NewSource"
    assert float(refreshed.iloc[0]["close"]) == pytest.approx(20.0)
    assert success_provider.calls == 1

    restarted = _manager(
        _Provider([]),
        _cache(tmp_path, clock, mode=MarketDataFetchMode.LOCAL_ONLY),
    )
    persisted, persisted_source = restarted.get_daily_data(
        "600519", start_date="2026-07-01", end_date="2026-07-20", days=30
    )
    assert persisted_source == "NewSource"
    assert float(persisted.iloc[0]["close"]) == pytest.approx(20.0)


def test_manager_concurrent_callers_share_one_provider_attempt(tmp_path: Path) -> None:
    clock = _Clock()
    provider = _Provider([_bars()], delay=0.05)
    manager = _manager(provider, _cache(tmp_path, clock, mode=MarketDataFetchMode.AUTO))
    kwargs = {"start_date": "2026-07-01", "end_date": "2026-07-20", "days": 30}

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(manager.get_daily_data, "600519", **kwargs) for _ in range(2)]
        results = [future.result() for future in futures]

    assert provider.calls == 1
    assert [source for _frame, source in results] == ["ManagerProbe", "ManagerProbe"]
    assert sorted(result[0].attrs["provider_cache"]["cache_hit"] for result in results) == [False, True]


def test_persistence_allowlist_strips_secret_shaped_columns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _Clock()
    secret = "sk-test-must-not-persist"
    config_secret = "config-token-must-not-persist"
    monkeypatch.setenv("TUSHARE_TOKEN", config_secret)
    cache = _cache(tmp_path, clock, mode=MarketDataFetchMode.REFRESH)
    manager = _manager(_Provider([_bars(unexpected_secret=secret)]), cache)

    frame, _ = manager.get_daily_data(
        "600519", start_date="2026-07-01", end_date="2026-07-20", days=30
    )
    payload_text = next(tmp_path.glob("*.json")).read_text(encoding="utf-8")
    payload = json.loads(payload_text)

    assert "api_key" not in frame.columns
    assert secret not in payload_text
    assert config_secret not in payload_text
    assert payload["schema_version"] == 2
    assert payload["column_allowlist"] == list(PERSISTED_DAILY_COLUMN_ALLOWLIST)
    assert payload["identity"] == {
        "symbol": "600519",
        "adjustment": "provider_default",
        "schema_id": "normalized_daily_v1",
    }
    assert payload["source_name"] == "ManagerProbe"


def test_adjustment_and_schema_identities_are_isolated_without_clobbering(
    tmp_path: Path,
) -> None:
    clock = _Clock()
    cache = _cache(tmp_path, clock, mode=MarketDataFetchMode.LOCAL_ONLY)
    raw_key = DailyCacheKey(
        "600519",
        "2026-07-01",
        "2026-07-20",
        30,
        adjustment="raw",
        schema_id="normalized_daily_v1",
    )
    adjusted_key = DailyCacheKey(
        "600519",
        "2026-07-01",
        "2026-07-20",
        30,
        adjustment="qfq",
        schema_id="normalized_daily_v2",
    )

    cache.store(raw_key, _bars(close=10.0), "RawSource")
    cache.store(adjusted_key, _bars(close=20.0), "AdjustedSource")
    cache._memory.clear()

    raw = cache.lookup_local_store(raw_key)
    adjusted = cache.lookup_local_store(adjusted_key)
    assert raw is not None and adjusted is not None
    assert raw.source_name == "RawSource"
    assert adjusted.source_name == "AdjustedSource"
    assert float(raw.frame.iloc[0]["close"]) == pytest.approx(10.0)
    assert float(adjusted.frame.iloc[0]["close"]) == pytest.approx(20.0)
    assert len(list(tmp_path.glob("*.json"))) == 2


def test_manager_tickflow_adjustment_identity_prevents_cross_run_reuse(
    tmp_path: Path,
) -> None:
    clock = _Clock()
    forward_provider = _Provider([_bars(close=10.0)], name="TickFlowFetcher")
    forward_provider.kline_adjust = "forward"
    forward_manager = _manager(
        forward_provider,
        _cache(tmp_path, clock, mode=MarketDataFetchMode.REFRESH),
    )

    forward, _ = forward_manager.get_daily_data(
        "600519",
        start_date="2026-07-01",
        end_date="2026-07-20",
        days=30,
    )

    backward_provider = _Provider([], name="TickFlowFetcher")
    backward_provider.kline_adjust = "backward"
    backward_manager = _manager(
        backward_provider,
        _cache(tmp_path, clock, mode=MarketDataFetchMode.LOCAL_ONLY),
    )

    with pytest.raises(LocalDataMissingError):
        backward_manager.get_daily_data(
            "600519",
            start_date="2026-07-01",
            end_date="2026-07-20",
            days=30,
        )

    assert float(forward.iloc[0]["close"]) == pytest.approx(10.0)
    assert backward_provider.calls == 0
    identities = {
        json.loads(path.read_text(encoding="utf-8"))["identity"]["adjustment"]
        for path in tmp_path.glob("*.json")
    }
    assert identities == {"tickflow:forward"}


def test_different_provider_sources_are_not_merged_into_false_coverage(
    tmp_path: Path,
) -> None:
    clock = _Clock()
    cache = _cache(tmp_path, clock, mode=MarketDataFetchMode.LOCAL_ONLY)
    cache.store(
        DailyCacheKey("600519", "2026-07-01", "2026-07-10", 10),
        _bars(("2026-07-01", "2026-07-10")),
        "SourceA",
    )
    cache.store(
        DailyCacheKey("600519", "2026-07-11", "2026-07-20", 10),
        _bars(("2026-07-11", "2026-07-20")),
        "SourceB",
    )
    manager = _manager(_Provider([]), cache)

    with pytest.raises(LocalDataMissingError) as exc_info:
        manager.get_daily_data(
            "600519",
            start_date="2026-07-01",
            end_date="2026-07-20",
            days=20,
        )

    assert exc_info.value.to_dict()["available_start_date"] == "2026-07-11"
    assert exc_info.value.to_dict()["missing_ranges"] == [
        {"start_date": "2026-07-01", "end_date": "2026-07-10"}
    ]


def test_corrupt_entry_is_not_a_local_success(tmp_path: Path) -> None:
    clock = _Clock()
    cache = _cache(tmp_path, clock, mode=MarketDataFetchMode.LOCAL_ONLY)
    key = DailyCacheKey("600519", "2026-07-01", "2026-07-20", 30)
    cache.store(key, _bars(), "Source")
    cache._memory.clear()
    next(tmp_path.glob("*.json")).write_text("not-json", encoding="utf-8")
    manager = _manager(_Provider([]), cache)

    with pytest.raises(LocalDataMissingError) as exc_info:
        manager.get_daily_data(
            "600519", start_date="2026-07-01", end_date="2026-07-20", days=30
        )
    assert exc_info.value.missing.reason == "no_local_entry"


def test_local_only_rejects_entry_past_explicit_maximum_age(tmp_path: Path) -> None:
    clock = _Clock()
    cache = _cache(
        tmp_path,
        clock,
        mode=MarketDataFetchMode.LOCAL_ONLY,
        local_only_max_age=20.0,
        persistent_max_age=100.0,
    )
    key = DailyCacheKey("600519", "2026-07-01", "2026-07-20", 30)
    cache.store(key, _bars(), "Source")
    clock.advance(21.0)
    manager = _manager(_Provider([]), cache)

    with pytest.raises(LocalDataMissingError) as exc_info:
        manager.get_daily_data(
            "600519", start_date="2026-07-01", end_date="2026-07-20", days=30
        )
    assert exc_info.value.missing.reason == "local_entry_too_old"
    assert exc_info.value.to_dict()["age_seconds"] == 21


def test_retention_prunes_oldest_by_age_then_count(tmp_path: Path) -> None:
    clock = _Clock()
    cache = _cache(
        tmp_path,
        clock,
        mode=MarketDataFetchMode.AUTO,
        persistent_max_age=50.0,
        persistent_max_entries=2,
    )
    for symbol in ("600001", "600002", "600003"):
        cache.store(
            DailyCacheKey(symbol, "2026-07-01", "2026-07-20", 30),
            _bars(),
            "Source",
        )
        clock.advance(1.0)
    assert len(list(tmp_path.glob("*.json"))) == 2

    clock.advance(51.0)
    cache.lookup(DailyCacheKey("600003", "2026-07-01", "2026-07-20", 30))
    assert list(tmp_path.glob("*.json")) == []
    assert cache.stats_snapshot()["pruned_entries"] >= 3


def test_schema_v1_entry_is_read_compatible_after_restart(tmp_path: Path) -> None:
    clock = _Clock()
    key = DailyCacheKey("600519", "2026-07-01", "2026-07-20", 30)
    payload = {
        "schema_version": 1,
        "key": key.legacy_dict(),
        "stored_at": clock.now,
        "source_name": "LegacySource",
        "dataframe": _bars().to_json(orient="table", date_format="iso", date_unit="ms"),
    }
    path = tmp_path / f"{key.symbol_digest()}-legacy.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    manager = _manager(
        _Provider([]),
        _cache(tmp_path, clock, mode=MarketDataFetchMode.LOCAL_ONLY),
    )
    frame, source = manager.get_daily_data(
        "600519", start_date="2026-07-01", end_date="2026-07-20", days=30
    )

    assert source == "LegacySource"
    assert len(frame) == 3
    assert manager.get_daily_cache_stats()["schema_v1_reads"] >= 1


def test_schema_v1_overlap_prefers_newest_stored_entry_not_filename_order(
    tmp_path: Path,
) -> None:
    clock = _Clock()
    key = DailyCacheKey("600519", "2026-07-01", "2026-07-20", 30)

    def _write_legacy(filename: str, *, stored_at: float, close: float) -> None:
        payload = {
            "schema_version": 1,
            "key": key.legacy_dict(),
            "stored_at": stored_at,
            "source_name": "LegacySource",
            "dataframe": _bars(close=close).to_json(
                orient="table",
                date_format="iso",
                date_unit="ms",
            ),
        }
        (tmp_path / filename).write_text(json.dumps(payload), encoding="utf-8")

    # Lexical order places the newer entry first. Filename-driven
    # concatenation would therefore let the older duplicate win keep-last.
    _write_legacy(
        f"{key.symbol_digest()}-a-new.json",
        stored_at=clock.now,
        close=20.0,
    )
    _write_legacy(
        f"{key.symbol_digest()}-z-old.json",
        stored_at=clock.now - 10.0,
        close=10.0,
    )
    manager = _manager(
        _Provider([]),
        _cache(tmp_path, clock, mode=MarketDataFetchMode.LOCAL_ONLY),
    )

    frame, source = manager.get_daily_data(
        "600519",
        start_date="2026-07-01",
        end_date="2026-07-20",
        days=30,
    )

    assert source == "LegacySource"
    assert float(frame.iloc[0]["close"]) == pytest.approx(20.0)


def test_unusable_provider_schema_records_one_health_failure_before_fallback(
    tmp_path: Path,
) -> None:
    clock = _Clock()
    invalid = _Provider(
        [_bars(include_volume=False)],
        name="EfinanceFetcher",
        priority=0,
    )
    backup = _Provider([_bars()], name="TencentFetcher", priority=1)
    manager = DataFetcherManager(fetchers=[invalid, backup])
    manager._daily_data_cache = _cache(
        tmp_path,
        clock,
        mode=MarketDataFetchMode.REFRESH,
    )

    _frame, source = manager.get_daily_data(
        "600519",
        start_date="2026-07-01",
        end_date="2026-07-20",
        days=30,
    )

    health_key = DataFetcherManager._daily_health_key(invalid, "cn")
    snapshot = manager.get_daily_source_health_snapshot()[health_key]
    assert source == "TencentFetcher"
    assert snapshot["sample_count"] == 1
    assert snapshot["error_rate"] == pytest.approx(1.0)
    assert snapshot["consecutive_failures"] == 1


def test_invalid_mode_fails_at_manager_cache_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PROVIDER_MARKET_DATA_MODE", "offline-ish")
    from src.config_parts.model import Config

    with pytest.raises(ValueError, match="Invalid PROVIDER_MARKET_DATA_MODE='offline-ish'"):
        Config()

    manager = DataFetcherManager(fetchers=[_Provider([_bars()])])

    with pytest.raises(ValueError, match="Invalid PROVIDER_MARKET_DATA_MODE='offline-ish'"):
        manager.get_daily_data(
            "600519", start_date="2026-07-01", end_date="2026-07-20", days=30
        )


@pytest.mark.parametrize(
    "mode",
    [MarketDataFetchMode.AUTO, MarketDataFetchMode.REFRESH],
)
def test_online_modes_with_cache_disabled_call_provider_once_without_persistence(
    tmp_path: Path,
    mode: MarketDataFetchMode,
) -> None:
    clock = _Clock()
    provider = _Provider([_bars()])
    manager = _manager(
        provider,
        _cache(tmp_path, clock, mode=mode, enabled=False),
    )

    frame, _ = manager.get_daily_data(
        "600519", start_date="2026-07-01", end_date="2026-07-20", days=30
    )
    assert provider.calls == 1
    assert len(frame) == 3
    assert list(tmp_path.glob("*.json")) == []
