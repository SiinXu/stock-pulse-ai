# -*- coding: utf-8 -*-
"""Concurrency, coalescing, and backpressure tests for PredictionResolver."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from random import Random
from types import SimpleNamespace
from typing import Any, Dict, List, Sequence
from unittest.mock import patch

import pytest

from src.services.prediction_resolver import (
    InMemoryPostmortemQueue,
    InMemoryPredictionStore,
    PredictionResolver,
    build_prediction_resolver_background_tasks,
    compute_retry_delay_seconds,
)


NOW = datetime(2026, 8, 12, 12, 0, 0)


@dataclass
class _Bar:
    close: float


@dataclass
class _Snapshot:
    status: str = "ok"
    reason: str = ""
    retryable: bool = True
    as_of_bar: _Bar | None = None
    end_bar: _Bar | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    @property
    def data_unavailable(self) -> bool:
        return not self.ok

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "retryable": self.retryable,
        }


@dataclass
class _Aggregate:
    scored_claims: int = 1
    hit_count: int = 1
    partial_count: int = 0
    miss_count: int = 0
    data_unavailable_count: int = 0


@dataclass
class _Report:
    aggregate: _Aggregate

    def to_dict(self) -> Dict[str, Any]:
        return {"aggregate": self.aggregate.__dict__}


class _Scorer:
    def __init__(self, *, miss: bool = False) -> None:
        self.miss = miss
        self.calls = 0

    def score(self, claims: Sequence[Any], actuals: Any, config: Any = None) -> _Report:
        self.calls += 1
        if self.miss:
            return _Report(_Aggregate(hit_count=0, miss_count=1))
        return _Report(_Aggregate())


class _TrackingFetcher:
    def __init__(self, *, delay: float = 0.0, fail: bool = False) -> None:
        self.delay = delay
        self.fail = fail
        self.calls: List[Dict[str, Any]] = []
        self.active = 0
        self.max_active = 0
        self._lock = threading.Lock()

    def fetch(self, **kwargs: Any) -> _Snapshot:
        with self._lock:
            self.calls.append(dict(kwargs))
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                time.sleep(self.delay)
            if self.fail:
                return _Snapshot(status="provider_down", reason="provider_down")
            return _Snapshot(as_of_bar=_Bar(100.0), end_bar=_Bar(101.0))
        finally:
            with self._lock:
                self.active -= 1


class _OutOfOrderFetcher(_TrackingFetcher):
    def fetch(self, **kwargs: Any) -> _Snapshot:
        if kwargs["symbol"] == "SLOW":
            time.sleep(0.03)
        return super().fetch(**kwargs)


def _seed(
    store: InMemoryPredictionStore,
    index: int,
    *,
    symbol: str = "AAPL",
    resolve_after: datetime | None = None,
) -> None:
    store.insert(
        prediction_id=f"pred-{index:03d}",
        run_id=f"run-{index:03d}",
        symbol=symbol,
        market="us",
        horizon="1d",
        as_of=date(2026, 8, 10),
        resolve_after=resolve_after or NOW - timedelta(hours=1),
        created_at=NOW - timedelta(days=1),
        claims=[{"claim_id": f"claim-{index}", "direction": "up"}],
    )


def test_large_backlog_drains_across_ticks_and_coalesces_fetches() -> None:
    store = InMemoryPredictionStore()
    store._clock = lambda: NOW
    for index in range(100):
        _seed(store, index)
    fetcher = _TrackingFetcher()
    scorer = _Scorer()
    resolver = PredictionResolver(
        store=store,
        actuals_fetcher=fetcher,
        claim_scorer=scorer,
        max_per_tick=25,
        fetch_concurrency=4,
        clock=lambda: NOW,
    )

    summaries = [resolver.tick() for _ in range(4)]

    assert [summary.claimed for summary in summaries] == [25, 25, 25, 25]
    assert [summary.resolved for summary in summaries] == [25, 25, 25, 25]
    assert [summary.fetch_calls for summary in summaries] == [1, 1, 1, 1]
    assert summaries[0].fetch_coalesced_saved == 24
    assert summaries[0].deferred_by_backpressure == 75
    assert summaries[-1].due_after == 0
    assert len(fetcher.calls) == 4
    assert scorer.calls == 100


def test_coalesce_key_keeps_distinct_horizon_end_dates_separate() -> None:
    store = InMemoryPredictionStore()
    store._clock = lambda: NOW
    _seed(store, 1, resolve_after=NOW - timedelta(days=2))
    _seed(store, 2, resolve_after=NOW - timedelta(days=1))
    fetcher = _TrackingFetcher()
    resolver = PredictionResolver(
        store=store,
        actuals_fetcher=fetcher,
        claim_scorer=_Scorer(),
        clock=lambda: NOW,
    )

    summary = resolver.tick()

    assert summary.resolved == 2
    assert summary.groups == 2
    assert summary.fetch_calls == 2
    assert {call["end"] for call in fetcher.calls} == {
        date(2026, 8, 10),
        date(2026, 8, 11),
    }


def test_fetch_pool_never_exceeds_configured_concurrency() -> None:
    store = InMemoryPredictionStore()
    store._clock = lambda: NOW
    for index in range(12):
        _seed(store, index, symbol=f"SYM{index}")
    fetcher = _TrackingFetcher(delay=0.02)
    resolver = PredictionResolver(
        store=store,
        actuals_fetcher=fetcher,
        claim_scorer=_Scorer(),
        fetch_concurrency=3,
        clock=lambda: NOW,
    )

    summary = resolver.tick()

    assert summary.resolved == 12
    assert summary.fetch_calls == 12
    assert 1 < fetcher.max_active <= 3


def test_parallel_fetch_completion_preserves_due_item_order() -> None:
    store = InMemoryPredictionStore()
    store._clock = lambda: NOW
    _seed(store, 1, symbol="SLOW")
    _seed(store, 2, symbol="FAST")
    resolver = PredictionResolver(
        store=store,
        actuals_fetcher=_OutOfOrderFetcher(),
        claim_scorer=_Scorer(),
        fetch_concurrency=2,
        clock=lambda: NOW,
    )

    summary = resolver.tick()

    assert [item.prediction_id for item in summary.items] == [
        "pred-001",
        "pred-002",
    ]


def test_provider_error_circuit_reduces_next_tick_claims() -> None:
    store = InMemoryPredictionStore()
    store._clock = lambda: NOW
    for index in range(3):
        _seed(store, index, symbol=f"FAIL{index}")
    resolver = PredictionResolver(
        store=store,
        actuals_fetcher=_TrackingFetcher(fail=True),
        claim_scorer=_Scorer(),
        max_per_tick=10,
        provider_error_circuit_threshold=3,
        circuit_open_max_per_tick=1,
        clock=lambda: NOW,
    )

    first = resolver.tick()
    for index in range(3, 8):
        _seed(store, index, symbol=f"FAIL{index}")
    second = resolver.tick(now=NOW + timedelta(seconds=1))

    assert first.fetch_errors == 3
    assert first.circuit_open is True
    assert second.circuit_open is True
    assert second.claimed == 1
    assert second.deferred_by_backpressure == 4


def test_non_retryable_unavailable_does_not_open_provider_circuit() -> None:
    class _DelistedFetcher:
        def fetch(self, **kwargs: Any) -> _Snapshot:
            return _Snapshot(status="delisted", reason="delisted", retryable=False)

    store = InMemoryPredictionStore()
    store._clock = lambda: NOW
    for index in range(3):
        _seed(store, index, symbol=f"OLD{index}")
    resolver = PredictionResolver(
        store=store,
        actuals_fetcher=_DelistedFetcher(),
        claim_scorer=_Scorer(),
        provider_error_circuit_threshold=1,
        clock=lambda: NOW,
    )

    summary = resolver.tick()

    assert summary.fetch_errors == 3
    assert summary.circuit_open is False


def test_postmortem_handoff_prioritizes_misses_and_honors_tick_budget() -> None:
    store = InMemoryPredictionStore()
    store._clock = lambda: NOW
    for index in range(3):
        _seed(store, index)
    queue = InMemoryPostmortemQueue(max_depth=10)
    resolver = PredictionResolver(
        store=store,
        actuals_fetcher=_TrackingFetcher(),
        claim_scorer=_Scorer(miss=True),
        postmortem_queue=queue,
        postmortem_max_per_tick=2,
        clock=lambda: NOW,
    )

    summary = resolver.tick()
    jobs = queue.pop_batch(10)

    assert summary.resolved == 3
    assert summary.postmortem_enqueued == 2
    assert summary.postmortem_dropped == 1
    assert summary.postmortem_queue_depth == 2
    assert [job.priority for job in jobs] == [10, 10]


def test_retry_jitter_is_injected_and_stays_bounded() -> None:
    assert compute_retry_delay_seconds(
        1,
        base_seconds=30,
        max_seconds=3600,
        jitter_ratio=0.1,
        random_value=0.5,
    ) == 31.5
    assert compute_retry_delay_seconds(
        20,
        base_seconds=30,
        max_seconds=3600,
        jitter_ratio=1.0,
        random_value=1.0,
    ) == 3600

    store = InMemoryPredictionStore()
    store._clock = lambda: NOW
    _seed(store, 1)
    resolver = PredictionResolver(
        store=store,
        actuals_fetcher=_TrackingFetcher(fail=True),
        claim_scorer=_Scorer(),
        retry_jitter_ratio=0.1,
        rng=Random(0),
        clock=lambda: NOW,
    )
    resolver.tick()
    row = store.get("pred-001")
    assert row is not None and row.outcome is not None
    assert 30.0 <= row.outcome["retry_delay_seconds"] <= 33.0


def test_zero_tick_budget_does_not_requeue_ready_retry() -> None:
    store = InMemoryPredictionStore()
    store._clock = lambda: NOW
    _seed(store, 1)
    resolver = PredictionResolver(
        store=store,
        actuals_fetcher=_TrackingFetcher(fail=True),
        claim_scorer=_Scorer(),
        retry_jitter_ratio=0.0,
        clock=lambda: NOW,
    )

    first = resolver.tick()
    row = store.get("pred-001")
    assert first.data_unavailable == 1
    assert row is not None
    assert row.status == "data_unavailable"
    assert row.next_attempt_at is not None

    second = resolver.tick(now=row.next_attempt_at + timedelta(seconds=1), limit=0)

    assert second.claimed == 0
    assert store.get("pred-001").status == "data_unavailable"  # type: ignore[union-attr]


def test_background_builder_passes_backpressure_configuration() -> None:
    sentinel = PredictionResolver(
        store=InMemoryPredictionStore(),
        actuals_fetcher=_TrackingFetcher(),
        claim_scorer=_Scorer(),
    )
    config = SimpleNamespace(
        prediction_resolve_enabled=True,
        prediction_resolve_interval_seconds=60,
        prediction_resolve_lease_seconds=120,
        prediction_resolve_max_per_tick=50,
        prediction_resolve_max_attempts=5,
        prediction_resolve_fetch_concurrency=7,
        prediction_resolve_postmortem_max_per_tick=8,
        prediction_resolve_provider_error_circuit_threshold=9,
        prediction_resolve_provider_error_circuit_cooldown_seconds=600,
        prediction_resolve_circuit_open_max_per_tick=2,
        prediction_resolve_retry_jitter_ratio=0.2,
    )
    queue = InMemoryPostmortemQueue(max_depth=10)
    with patch(
        "src.services.prediction_resolver.resolver.build_prediction_resolver",
        return_value=sentinel,
    ) as build:
        tasks = build_prediction_resolver_background_tasks(
            config,
            postmortem_queue=queue,
        )

    assert len(tasks) == 1
    assert build.call_args.kwargs["fetch_concurrency"] == 7
    assert build.call_args.kwargs["postmortem_queue"] is queue
    assert build.call_args.kwargs["postmortem_max_per_tick"] == 8
    assert build.call_args.kwargs["provider_error_circuit_threshold"] == 9
    assert build.call_args.kwargs["provider_error_circuit_cooldown_seconds"] == 600
    assert build.call_args.kwargs["circuit_open_max_per_tick"] == 2
    assert build.call_args.kwargs["retry_jitter_ratio"] == 0.2


def test_postmortem_queue_is_bounded_and_releases_dedupe_after_pop() -> None:
    queue = InMemoryPostmortemQueue(max_depth=2)
    assert queue.enqueue(prediction_id="low", outcome={"label": "partial"}, priority=5)
    assert queue.enqueue(prediction_id="high", outcome={"label": "miss"}, priority=10)
    assert not queue.enqueue(prediction_id="third", outcome={}, priority=20)
    assert not queue.enqueue(prediction_id="high", outcome={}, priority=20)

    jobs = queue.pop_batch(1)

    assert [job.prediction_id for job in jobs] == ["high"]
    assert queue.enqueue(prediction_id="high", outcome={"label": "miss"}, priority=10)
    assert queue.depth() == 2


def test_postmortem_drain_honors_worker_cap() -> None:
    queue = InMemoryPostmortemQueue(max_depth=10)
    for index in range(4):
        assert queue.enqueue(
            prediction_id=f"job-{index}",
            outcome={"label": "miss"},
            priority=10,
        )
    lock = threading.Lock()
    active = 0
    max_active = 0

    def handle(_job: Any) -> None:
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        try:
            time.sleep(0.02)
        finally:
            with lock:
                active -= 1

    drained = queue.drain(handler=handle, max_items=4, max_workers=2)

    assert drained == 4
    assert 1 < max_active <= 2
    assert queue.depth() == 0


def test_postmortem_drain_requeues_failures_and_keeps_dedupe_reserved() -> None:
    queue = InMemoryPostmortemQueue(max_depth=2)
    assert queue.enqueue(
        prediction_id="retry-me",
        outcome={"label": "miss"},
        priority=10,
    )
    entered = threading.Event()
    release = threading.Event()

    def fail(_job: Any) -> None:
        entered.set()
        release.wait(timeout=1)
        raise RuntimeError("handler failed")

    error: List[Exception] = []

    def run_drain() -> None:
        try:
            queue.drain(handler=fail, max_items=1, max_workers=1)
        except Exception as exc:
            error.append(exc)

    worker = threading.Thread(target=run_drain)
    worker.start()
    assert entered.wait(timeout=1)
    assert not queue.enqueue(
        prediction_id="retry-me",
        outcome={"label": "miss"},
        priority=10,
    )
    release.set()
    worker.join(timeout=2)

    assert not worker.is_alive()
    assert len(error) == 1
    assert isinstance(error[0], RuntimeError)
    assert queue.depth() == 1
    assert [job.prediction_id for job in queue.pop_batch(1)] == ["retry-me"]


def test_postmortem_drain_rejects_invalid_worker_cap() -> None:
    queue = InMemoryPostmortemQueue(max_depth=1)
    with pytest.raises(ValueError, match="max_workers"):
        queue.drain(handler=lambda _job: None, max_items=1, max_workers=0)
    with pytest.raises(ValueError, match="max_items"):
        queue.drain(handler=lambda _job: None, max_items=True, max_workers=1)
