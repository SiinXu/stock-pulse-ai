"""Deterministic coverage for provider health, circuit cooldown, and failover."""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Optional
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

    def get_daily_data(self, **_kwargs) -> Optional[pd.DataFrame]:
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        if outcome is None:
            return None
        assert isinstance(outcome, pd.DataFrame)
        return outcome.copy(deep=True)


class _ObservedCircuitBreaker(CircuitBreaker):
    def __init__(self, watched_provider: str, target_peeks: int, **kwargs) -> None:
        super().__init__(**kwargs)
        self.watched_provider = watched_provider
        self.target_peeks = target_peeks
        self.peek_count = 0
        self.peek_target_reached = threading.Event()
        self._peek_lock = threading.Lock()

    def can_attempt(self, source: str) -> bool:
        result = super().can_attempt(source)
        if source.endswith(f":{self.watched_provider}"):
            with self._peek_lock:
                self.peek_count += 1
                if self.peek_count >= self.target_peeks:
                    self.peek_target_reached.set()
        return result


class _BlockingFailureProvider:
    name = "EfinanceFetcher"
    priority = 0

    def __init__(self) -> None:
        self.calls = 0
        self.entered = threading.Event()
        self.release = threading.Event()

    def get_daily_data(self, **_kwargs) -> pd.DataFrame:
        self.calls += 1
        if self.calls != 1:
            raise AssertionError("an open circuit must stop queued provider calls")
        self.entered.set()
        if not self.release.wait(timeout=2):
            raise AssertionError("test did not release the blocking provider")
        raise TimeoutError("provider timeout")


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
        token = activate_run_diagnostic_context(
            trace_id="trace-provider-failures",
            stock_code="600519",
        )
        try:
            for _ in range(2):
                frame, source = manager.get_daily_data("600519")
                assert not frame.empty
                assert source == "TencentFetcher"
            failure_diagnostics = current_diagnostic_snapshot()
        finally:
            reset_run_diagnostic_context(token)

        primary_failures = [
            run
            for run in failure_diagnostics["provider_runs"]
            if run["provider"] == "EfinanceFetcher"
        ]
        assert len(primary_failures) == 2
        assert "must-not-leak" not in str(failure_diagnostics)
        assert "[REDACTED]" in primary_failures[0]["error_message_sanitized"]

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


def test_queued_calls_recheck_circuit_inside_fetcher_lock() -> None:
    breaker = _ObservedCircuitBreaker(
        watched_provider="EfinanceFetcher",
        target_peeks=2,
        failure_threshold=1,
        cooldown_seconds=60.0,
    )
    primary = _BlockingFailureProvider()
    backup = _SequencedProvider(
        "TencentFetcher",
        1,
        [_daily_frame(), _daily_frame()],
    )
    manager = DataFetcherManager(fetchers=[primary, backup])
    sources: list[str] = []
    errors: list[BaseException] = []

    def fetch() -> None:
        try:
            _, source = manager.get_daily_data("600519")
            sources.append(source)
        except BaseException as exc:  # pragma: no cover - thread assertion transport
            errors.append(exc)

    with patch.object(DataFetcherManager, "_daily_source_health", breaker):
        first = threading.Thread(target=fetch)
        second = threading.Thread(target=fetch)
        first.start()
        assert primary.entered.wait(timeout=1)
        second.start()
        assert breaker.peek_target_reached.wait(timeout=1)
        primary.release.set()
        first.join(timeout=2)
        second.join(timeout=2)

        assert not first.is_alive()
        assert not second.is_alive()
        assert errors == []
        assert sorted(sources) == ["TencentFetcher", "TencentFetcher"]
        assert primary.calls == 1
        key = DataFetcherManager._daily_health_key(primary, "cn")
        assert breaker.get_status()[key] == CircuitBreaker.OPEN


def test_provider_latency_excludes_local_fetcher_lock_queue_time() -> None:
    breaker = _ObservedCircuitBreaker(
        watched_provider="EfinanceFetcher",
        target_peeks=1,
        failure_threshold=3,
        cooldown_seconds=60.0,
    )
    provider = _SequencedProvider("EfinanceFetcher", 0, [_daily_frame()])
    manager = DataFetcherManager(fetchers=[provider])
    result: list[str] = []

    with patch.object(DataFetcherManager, "_daily_source_health", breaker):
        call_lock = manager._get_fetcher_call_lock(provider)
        call_lock.acquire()
        worker = threading.Thread(
            target=lambda: result.append(manager.get_daily_data("600519")[1])
        )
        worker.start()
        assert breaker.peek_target_reached.wait(timeout=1)
        time.sleep(0.2)
        call_lock.release()
        worker.join(timeout=2)

        assert not worker.is_alive()
        assert result == ["EfinanceFetcher"]
        key = DataFetcherManager._daily_health_key(provider, "cn")
        latency_ms = breaker.get_snapshot(key)[key]["average_latency_ms"]
        assert latency_ms is not None
        assert latency_ms < 100.0


def test_empty_and_none_are_health_failures_without_opening_circuit() -> None:
    breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=60.0)
    primary = _SequencedProvider(
        "EfinanceFetcher",
        0,
        [pd.DataFrame(), None, _daily_frame()],
    )
    backup = _SequencedProvider(
        "TencentFetcher",
        1,
        [_daily_frame(), _daily_frame()],
    )
    manager = DataFetcherManager(fetchers=[primary, backup])

    with patch.object(DataFetcherManager, "_daily_source_health", breaker):
        for _ in range(2):
            _, source = manager.get_daily_data("600519")
            assert source == "TencentFetcher"

        key = DataFetcherManager._daily_health_key(primary, "cn")
        degraded = breaker.get_snapshot(key)[key]
        assert degraded["state"] == CircuitBreaker.CLOSED
        assert degraded["consecutive_failures"] == 0
        assert degraded["sample_count"] == 2
        assert degraded["error_rate"] == 1.0

        _, source = manager.get_daily_data("600519")
        assert source == "EfinanceFetcher"
        recovered = breaker.get_snapshot(key)[key]
        assert recovered["state"] == CircuitBreaker.CLOSED
        assert recovered["error_rate"] == pytest.approx(2 / 3, abs=0.0001)


@pytest.mark.parametrize("probe_outcome", [pd.DataFrame(), None], ids=["empty", "none"])
def test_unusable_half_open_probe_returns_to_cooldown(probe_outcome: object) -> None:
    clock = _Clock()
    breaker = CircuitBreaker(
        failure_threshold=1,
        cooldown_seconds=30.0,
        clock=clock,
    )
    primary = _SequencedProvider(
        "EfinanceFetcher",
        0,
        [TimeoutError("down"), probe_outcome, _daily_frame()],
    )
    backup = _SequencedProvider(
        "TencentFetcher",
        1,
        [_daily_frame(), _daily_frame(), _daily_frame()],
    )
    manager = DataFetcherManager(fetchers=[primary, backup])

    with patch.object(DataFetcherManager, "_daily_source_health", breaker):
        _, source = manager.get_daily_data("600519")
        assert source == "TencentFetcher"

        clock.advance(30.0)
        _, source = manager.get_daily_data("600519")
        assert source == "TencentFetcher"

        key = DataFetcherManager._daily_health_key(primary, "cn")
        degraded = breaker.get_snapshot(key)[key]
        assert degraded["state"] == CircuitBreaker.OPEN
        assert degraded["consecutive_failures"] == 1
        assert degraded["error_rate"] == 1.0

        _, source = manager.get_daily_data("600519")
        assert source == "TencentFetcher"
        assert primary.calls == 2

        clock.advance(30.0)
        _, source = manager.get_daily_data("600519")
        assert source == "EfinanceFetcher"
        assert breaker.get_status()[key] == CircuitBreaker.CLOSED


def test_fallback_metadata_and_log_skip_open_intermediate_provider(caplog) -> None:
    breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=60.0)
    primary = _SequencedProvider("EfinanceFetcher", 0, [TimeoutError("down")])
    intermediate = _SequencedProvider("TencentFetcher", 1, [_daily_frame()])
    backup = _SequencedProvider("AkshareFetcher", 2, [_daily_frame()])
    manager = DataFetcherManager(fetchers=[primary, intermediate, backup])
    intermediate_key = DataFetcherManager._daily_health_key(intermediate, "cn")
    breaker.record_failure(intermediate_key, error="already_open")

    caplog.set_level(logging.INFO, logger="data_provider.base")
    with patch.object(DataFetcherManager, "_daily_source_health", breaker):
        token = activate_run_diagnostic_context(trace_id="trace-open-intermediate")
        try:
            _, source = manager.get_daily_data("600519")
            diagnostics = current_diagnostic_snapshot()
        finally:
            reset_run_diagnostic_context(token)

    assert source == "AkshareFetcher"
    assert intermediate.calls == 0
    assert [run["fallback_to"] for run in diagnostics["provider_runs"][:2]] == [
        "AkshareFetcher",
        "AkshareFetcher",
    ]
    assert "[EfinanceFetcher] -> [AkshareFetcher]" in caplog.text
    assert "[EfinanceFetcher] -> [TencentFetcher]" not in caplog.text


def test_us_fallback_metadata_skips_unconfigured_route_tokens() -> None:
    breaker = CircuitBreaker(failure_threshold=3, cooldown_seconds=60.0)
    primary = _SequencedProvider("FinnhubFetcher", 2, [TimeoutError("down")])
    backup = _SequencedProvider("YfinanceFetcher", 4, [_daily_frame()])
    manager = DataFetcherManager(fetchers=[primary, backup])

    with patch.object(DataFetcherManager, "_daily_source_health", breaker):
        token = activate_run_diagnostic_context(trace_id="trace-us-missing-provider")
        try:
            _, source = manager.get_daily_data("AAPL")
            diagnostics = current_diagnostic_snapshot()
        finally:
            reset_run_diagnostic_context(token)

    assert source == "YfinanceFetcher"
    assert diagnostics["provider_runs"][0]["fallback_to"] == "YfinanceFetcher"


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


@pytest.mark.parametrize("configured_value", ["nan", "inf", "-inf"])
def test_non_finite_cooldown_configuration_uses_default(configured_value: str) -> None:
    breaker = CircuitBreaker(cooldown_seconds=12.5)
    provider = _SequencedProvider("EfinanceFetcher", 0, [_daily_frame()])

    with patch.object(DataFetcherManager, "_daily_source_health", breaker):
        with patch.dict(
            os.environ,
            {"PROVIDER_CIRCUIT_COOLDOWN_SECONDS": configured_value},
            clear=False,
        ):
            DataFetcherManager(fetchers=[provider])

    assert breaker.cooldown_seconds == 300.0
