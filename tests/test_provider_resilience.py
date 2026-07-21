"""Deterministic coverage for provider health, circuit cooldown, and failover."""

from __future__ import annotations

import os
from unittest.mock import patch

import pandas as pd
import pytest

from data_provider.base import DataFetcherManager
from data_provider.realtime_types import CircuitBreaker
from src.services.run_diagnostics import (
    activate_run_diagnostic_context,
    current_diagnostic_snapshot,
    reset_run_diagnostic_context,
)


def _daily_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": ["2026-07-20"],
            "open": [10.0],
            "high": [10.5],
            "low": [9.8],
            "close": [10.2],
            "volume": [1000],
            "amount": [10200],
            "pct_chg": [2.0],
        }
    )


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _SequencedProvider:
    def __init__(self, name: str, priority: int, outcomes: list[object]) -> None:
        self.name = name
        self.priority = priority
        self.outcomes = list(outcomes)
        self.calls = 0

    def get_daily_data(self, **_kwargs) -> pd.DataFrame:
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        assert isinstance(outcome, pd.DataFrame)
        return outcome.copy(deep=True)


def test_failure_opens_circuit_failover_continues_and_half_open_recovers() -> None:
    clock = _Clock()
    breaker = CircuitBreaker(
        failure_threshold=2,
        cooldown_seconds=30.0,
        health_window_size=8,
        clock=clock,
    )
    primary = _SequencedProvider(
        "EfinanceFetcher",
        0,
        [TimeoutError("credential=must-not-leak"), TimeoutError("still down"), _daily_frame()],
    )
    backup = _SequencedProvider(
        "TencentFetcher",
        1,
        [_daily_frame(), _daily_frame(), _daily_frame()],
    )
    manager = DataFetcherManager(fetchers=[primary, backup])

    with patch.object(DataFetcherManager, "_daily_source_health", breaker):
        for _ in range(2):
            frame, source = manager.get_daily_data("600519")
            assert not frame.empty
            assert source == "TencentFetcher"

        health_key = DataFetcherManager._daily_health_key(primary, "cn")
        assert breaker.get_status()[health_key] == CircuitBreaker.OPEN

        token = activate_run_diagnostic_context(
            trace_id="trace-provider-circuit",
            stock_code="600519",
        )
        try:
            frame, source = manager.get_daily_data("600519")
            diagnostics = current_diagnostic_snapshot()
        finally:
            reset_run_diagnostic_context(token)

        assert not frame.empty
        assert source == "TencentFetcher"
        assert primary.calls == 2
        assert [run["provider"] for run in diagnostics["provider_runs"]] == [
            "EfinanceFetcher",
            "TencentFetcher",
        ]
        circuit_run = diagnostics["provider_runs"][0]
        assert circuit_run["error_type"] == "CircuitOpen"
        assert circuit_run["fallback_to"] == "TencentFetcher"
        assert "must-not-leak" not in str(diagnostics)

        clock.advance(30.0)
        frame, source = manager.get_daily_data("600519")

        assert not frame.empty
        assert source == "EfinanceFetcher"
        assert primary.calls == 3
        snapshot = DataFetcherManager.get_daily_source_health_snapshot()[health_key]
        assert snapshot["state"] == CircuitBreaker.CLOSED
        assert snapshot["consecutive_failures"] == 0
        assert snapshot["sample_count"] == 3
        assert snapshot["error_rate"] == pytest.approx(2 / 3, abs=0.0001)
        assert 0.0 <= snapshot["health_score"] < 100.0


def test_environment_policy_can_disable_circuit_without_disabling_health() -> None:
    breaker = CircuitBreaker()
    provider = _SequencedProvider("EfinanceFetcher", 0, [_daily_frame()])
    environment = {
        "PROVIDER_CIRCUIT_BREAKER_ENABLED": "false",
        "PROVIDER_CIRCUIT_FAILURE_THRESHOLD": "2",
        "PROVIDER_CIRCUIT_COOLDOWN_SECONDS": "12.5",
        "PROVIDER_HEALTH_WINDOW_SIZE": "4",
    }

    with patch.object(DataFetcherManager, "_daily_source_health", breaker):
        with patch.dict(os.environ, environment, clear=False):
            DataFetcherManager(fetchers=[provider])

        key = "daily_data:cn:EfinanceFetcher"
        breaker.record_failure(key, error="token=must-not-be-stored", latency_ms=250)
        breaker.record_failure(key, error="token=must-not-be-stored", latency_ms=750)

        assert breaker.enabled is False
        assert breaker.failure_threshold == 2
        assert breaker.cooldown_seconds == 12.5
        assert breaker.health_window_size == 4
        assert breaker.is_available(key) is True
        snapshot = breaker.get_snapshot(key)[key]
        assert snapshot["state"] == CircuitBreaker.CLOSED
        assert snapshot["circuit_enabled"] is False
        assert snapshot["average_latency_ms"] == 500.0
        assert "must-not-be-stored" not in str(snapshot)
