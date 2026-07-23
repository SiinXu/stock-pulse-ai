"""Deterministic coverage for adaptive daily-provider ordering and telemetry."""

from __future__ import annotations

import json
import logging
import os
from unittest.mock import patch

import pandas as pd
import pytest

from data_provider.base import DataFetcherManager
from data_provider.realtime_types import CircuitBreaker


def _daily_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": ["2026-07-21"],
            "open": [10.0],
            "high": [10.5],
            "low": [9.8],
            "close": [10.2],
            "volume": [1000],
            "amount": [10200],
            "pct_chg": [2.0],
        }
    )


class _Provider:
    def __init__(self, name: str, priority: int, outcome: object) -> None:
        self.name = name
        self.priority = priority
        self.outcome = outcome
        self.calls = 0

    def get_daily_data(self, **_kwargs) -> pd.DataFrame:
        self.calls += 1
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        assert isinstance(self.outcome, pd.DataFrame)
        return self.outcome.copy(deep=True)


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _adaptive_environment(*, enabled: bool = True, min_samples: int = 3) -> dict[str, str]:
    return {
        "PROVIDER_ADAPTIVE_PRIORITY_ENABLED": "true" if enabled else "false",
        "PROVIDER_ADAPTIVE_PRIORITY_MIN_SAMPLES": str(min_samples),
        "PROVIDER_CIRCUIT_BREAKER_ENABLED": "false",
        "PROVIDER_DAILY_CACHE_ENABLED": "false",
    }


def _record_successes(
    breaker: CircuitBreaker,
    manager: DataFetcherManager,
    provider: _Provider,
    *,
    latency_ms: float,
    count: int = 3,
) -> None:
    key = manager._daily_health_key(provider, "cn")
    for _ in range(count):
        breaker.record_success(key, latency_ms=latency_ms)


def _record_quality_failures(
    breaker: CircuitBreaker,
    manager: DataFetcherManager,
    provider: _Provider,
    *,
    latency_ms: float,
    count: int = 3,
) -> None:
    key = manager._daily_health_key(provider, "cn")
    for _ in range(count):
        breaker.record_quality_failure(key, latency_ms=latency_ms)


def test_recent_success_rate_reorders_only_within_static_priority(caplog) -> None:
    breaker = CircuitBreaker()
    static_anchor = _Provider("StaticAnchor", 0, TimeoutError("anchor down"))
    degraded_peer = _Provider("DegradedPeer", 1, TimeoutError("must not be called"))
    healthy_peer = _Provider("HealthyPeer", 1, _daily_frame())

    caplog.set_level(logging.INFO, logger="data_provider.base")
    with patch.object(DataFetcherManager, "_daily_source_health", breaker):
        with patch.dict(os.environ, _adaptive_environment(), clear=False):
            manager = DataFetcherManager(
                fetchers=[static_anchor, degraded_peer, healthy_peer]
            )
            _record_quality_failures(
                breaker,
                manager,
                static_anchor,
                latency_ms=50,
            )
            _record_quality_failures(
                breaker,
                manager,
                degraded_peer,
                latency_ms=50,
            )
            _record_successes(
                breaker,
                manager,
                healthy_peer,
                latency_ms=500,
            )

            ordered = manager._order_daily_fetchers(
                manager._get_fetchers_snapshot(),
                "cn",
            )
            _, source = manager.get_daily_data("600519")

    assert [provider.name for provider in ordered] == [
        "StaticAnchor",
        "HealthyPeer",
        "DegradedPeer",
    ]
    assert source == "HealthyPeer"
    assert static_anchor.calls == 1
    assert healthy_peer.calls == 1
    assert degraded_peer.calls == 0
    assert "event=adaptive_reorder" in caplog.text
    assert "static_order=StaticAnchor,DegradedPeer,HealthyPeer" in caplog.text
    assert "selected_order=StaticAnchor,HealthyPeer,DegradedPeer" in caplog.text


def test_equal_success_rate_uses_recent_latency() -> None:
    breaker = CircuitBreaker()
    slow = _Provider("SlowPeer", 2, _daily_frame())
    fast = _Provider("FastPeer", 2, _daily_frame())

    with patch.object(DataFetcherManager, "_daily_source_health", breaker):
        with patch.dict(os.environ, _adaptive_environment(), clear=False):
            manager = DataFetcherManager(fetchers=[slow, fast])
            _record_successes(breaker, manager, slow, latency_ms=900)
            _record_successes(breaker, manager, fast, latency_ms=100)

            ordered = manager._order_daily_fetchers([slow, fast], "cn")

    assert [provider.name for provider in ordered] == ["FastPeer", "SlowPeer"]


def test_disabled_adaptive_priority_restores_static_order() -> None:
    breaker = CircuitBreaker()
    degraded = _Provider("DegradedPeer", 1, _daily_frame())
    healthy = _Provider("HealthyPeer", 1, _daily_frame())

    with patch.object(DataFetcherManager, "_daily_source_health", breaker):
        with patch.dict(
            os.environ,
            _adaptive_environment(enabled=False),
            clear=False,
        ):
            manager = DataFetcherManager(fetchers=[degraded, healthy])
            _record_quality_failures(breaker, manager, degraded, latency_ms=100)
            _record_successes(breaker, manager, healthy, latency_ms=100)

            ordered = manager._order_daily_fetchers([degraded, healthy], "cn")
            _, source = manager.get_daily_data("600519")

    assert [provider.name for provider in ordered] == ["DegradedPeer", "HealthyPeer"]
    assert source == "DegradedPeer"
    assert degraded.calls == 1
    assert healthy.calls == 0


def test_sparse_provider_is_uncrossable_sampling_anchor() -> None:
    breaker = CircuitBreaker()
    degraded = _Provider("DegradedPeer", 1, TimeoutError("provider down"))
    sparse = _Provider("SparsePeer", 1, _daily_frame())
    healthy = _Provider("HealthyPeer", 1, _daily_frame())

    with patch.object(DataFetcherManager, "_daily_source_health", breaker):
        with patch.dict(os.environ, _adaptive_environment(min_samples=3), clear=False):
            manager = DataFetcherManager(fetchers=[degraded, sparse, healthy])
            _record_quality_failures(
                breaker,
                manager,
                degraded,
                latency_ms=100,
                count=3,
            )
            _record_successes(
                breaker,
                manager,
                sparse,
                latency_ms=100,
                count=1,
            )
            _record_successes(
                breaker,
                manager,
                healthy,
                latency_ms=100,
                count=3,
            )

            ordered = manager._order_daily_fetchers(
                [degraded, sparse, healthy],
                "cn",
            )
            _, source = manager.get_daily_data("600519")

    assert [provider.name for provider in ordered] == [
        "DegradedPeer",
        "SparsePeer",
        "HealthyPeer",
    ]
    assert source == "SparsePeer"
    assert degraded.calls == 1
    assert sparse.calls == 1
    assert healthy.calls == 0


def test_open_provider_is_uncrossable_half_open_recovery_anchor() -> None:
    clock = _Clock()
    breaker = CircuitBreaker(
        failure_threshold=2,
        cooldown_seconds=30,
        clock=clock,
    )
    degraded = _Provider("DegradedPeer", 1, TimeoutError("provider down"))
    recovering = _Provider("RecoveringPeer", 1, _daily_frame())
    healthy = _Provider("HealthyPeer", 1, _daily_frame())
    environment = _adaptive_environment(min_samples=2)
    environment.update(
        {
            "PROVIDER_CIRCUIT_BREAKER_ENABLED": "true",
            "PROVIDER_CIRCUIT_FAILURE_THRESHOLD": "2",
            "PROVIDER_CIRCUIT_COOLDOWN_SECONDS": "30",
        }
    )

    with patch.object(DataFetcherManager, "_daily_source_health", breaker):
        with patch.dict(os.environ, environment, clear=False):
            manager = DataFetcherManager(fetchers=[degraded, recovering, healthy])
            _record_quality_failures(
                breaker,
                manager,
                degraded,
                latency_ms=100,
                count=2,
            )
            recovering_key = manager._daily_health_key(recovering, "cn")
            breaker.record_failure(recovering_key, latency_ms=100)
            breaker.record_failure(recovering_key, latency_ms=100)
            _record_successes(
                breaker,
                manager,
                healthy,
                latency_ms=100,
                count=2,
            )

            clock.advance(30)
            ordered = manager._order_daily_fetchers(
                [degraded, recovering, healthy],
                "cn",
            )
            _, source = manager.get_daily_data("600519")

    assert [provider.name for provider in ordered] == [
        "DegradedPeer",
        "RecoveringPeer",
        "HealthyPeer",
    ]
    assert source == "RecoveringPeer"
    assert breaker.get_status()[recovering_key] == CircuitBreaker.CLOSED
    assert degraded.calls == 1
    assert recovering.calls == 1
    assert healthy.calls == 0


def test_market_capability_filter_is_a_hard_boundary() -> None:
    breaker = CircuitBreaker()
    unsupported = _Provider("EfinanceFetcher", 0, _daily_frame())
    supported = _Provider("YfinanceFetcher", 9, _daily_frame())

    with patch.object(DataFetcherManager, "_daily_source_health", breaker):
        with patch.dict(os.environ, _adaptive_environment(min_samples=1), clear=False):
            manager = DataFetcherManager(fetchers=[unsupported, supported])
            _record_successes(breaker, manager, unsupported, latency_ms=10)
            _record_quality_failures(breaker, manager, supported, latency_ms=900)

            _, source = manager.get_daily_data("HK00700")

    assert source == "YfinanceFetcher"
    assert unsupported.calls == 0
    assert supported.calls == 1


def test_health_report_is_structured_queryable_and_secret_free(caplog) -> None:
    breaker = CircuitBreaker()
    provider = _Provider("EfinanceFetcher", 0, _daily_frame())

    caplog.set_level(logging.INFO, logger="data_provider.base")
    with patch.object(DataFetcherManager, "_daily_source_health", breaker):
        with patch.dict(os.environ, _adaptive_environment(min_samples=2), clear=False):
            manager = DataFetcherManager(fetchers=[provider])
            health_key = manager._daily_health_key(provider, "cn")
            breaker.record_failure(
                health_key,
                error="credential=must-not-leak",
                latency_ms=250,
            )
            breaker.record_success(health_key, latency_ms=50)

            report = manager.log_daily_provider_health_report("cn")
            DataFetcherManager.reset_daily_source_health()
            reset_report = manager.get_daily_provider_health_report("cn")

    assert report["schema_version"] == "provider_daily_health_v1"
    assert report["adaptive_priority"] == {
        "enabled": True,
        "min_samples": 2,
        "boundary": "equal_static_priority_after_capability_filtering",
    }
    assert report["provider_count"] == 1
    assert report["providers"][0]["provider"] == "EfinanceFetcher"
    assert report["providers"][0]["static_priority"] == 0
    assert report["providers"][0]["supported_markets"] == ["cn"]
    assert report["providers"][0]["sample_count"] == 2
    assert json.loads(json.dumps(report))["provider_count"] == 1
    assert "provider_health event=snapshot" in caplog.text
    assert "must-not-leak" not in caplog.text
    assert reset_report["provider_count"] == 0


def test_environment_defaults_enable_adaptive_priority(monkeypatch) -> None:
    breaker = CircuitBreaker()
    provider = _Provider("DefaultProvider", 1, _daily_frame())
    monkeypatch.delenv("PROVIDER_ADAPTIVE_PRIORITY_ENABLED", raising=False)
    monkeypatch.delenv("PROVIDER_ADAPTIVE_PRIORITY_MIN_SAMPLES", raising=False)

    with patch.object(DataFetcherManager, "_daily_source_health", breaker):
        manager = DataFetcherManager(fetchers=[provider])
        report = manager.get_daily_provider_health_report()

    assert report["adaptive_priority"]["enabled"] is True
    assert report["adaptive_priority"]["min_samples"] == 3


def test_health_report_rejects_unknown_market_without_echoing_input() -> None:
    manager = DataFetcherManager(
        fetchers=[_Provider("DefaultProvider", 1, _daily_frame())]
    )

    with pytest.raises(ValueError, match="market must be one of") as error:
        manager.log_daily_provider_health_report("credential=must-not-leak")

    assert "must-not-leak" not in str(error.value)
