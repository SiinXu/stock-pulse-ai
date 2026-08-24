# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Unit tests for read-only prediction resolver diagnostics collection."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from typing import Any, List

import pytest

from src.services.prediction_resolver.memory_store import (
    STATUS_DATA_UNAVAILABLE,
    STATUS_PENDING,
    STATUS_RESOLVING,
    InMemoryPredictionStore,
)
from src.services.prediction_resolver_diagnostics import (
    OLDEST_DUE_LIMIT,
    PredictionResolverDiagnosticsStoreError,
    collect_prediction_resolver_diagnostics,
)
from tests.services.test_prediction_resolver import _now


def _config(**overrides: Any) -> SimpleNamespace:
    values = dict(
        prediction_resolve_enabled=False,
        prediction_resolve_interval_seconds=60,
        prediction_resolve_max_per_tick=50,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def _insert(
    store: InMemoryPredictionStore,
    *,
    prediction_id: str,
    resolve_after_hours: int = 1,
    status: str = STATUS_PENDING,
    **kwargs: Any,
) -> None:
    now = _now()
    store.insert(
        prediction_id=prediction_id,
        run_id="run-1",
        symbol="600519",
        market="cn",
        horizon="1d",
        resolve_after=now - timedelta(hours=resolve_after_hours),
        created_at=now - timedelta(days=1),
        claims=[{"claim_id": "c1", "claim_type": "direction", "direction": "up"}],
        status=status,
        **kwargs,
    )


def test_collect_disabled_empty_store_is_honest() -> None:
    store = InMemoryPredictionStore()
    store._clock = _now
    payload = collect_prediction_resolver_diagnostics(
        config=_config(),
        store=store,
        scheduler=None,
        now=_now(),
    )
    assert payload["enabled"] is False
    assert payload["interval_seconds"] == 60
    assert payload["this_process_worker_registered"] is False
    assert payload["claimable_due_count"] == 0
    assert payload["oldest_due"] == []
    assert payload["claimable_due_truncated"] is False
    assert payload["claimable_due_probe_limit"] == 1000
    assert payload["observed_at"].endswith("+00:00")


def test_collect_includes_pending_and_expired_resolving_without_requeue() -> None:
    store = InMemoryPredictionStore()
    store._clock = _now
    now = _now()
    _insert(store, prediction_id="pred-pending", resolve_after_hours=3)
    _insert(
        store,
        prediction_id="pred-expired",
        resolve_after_hours=2,
        status=STATUS_RESOLVING,
        lease_owner="dead-worker",
        lease_token="old-token",
        lease_expires_at=now - timedelta(minutes=1),
    )
    _insert(
        store,
        prediction_id="pred-retry",
        resolve_after_hours=4,
        status=STATUS_DATA_UNAVAILABLE,
        next_attempt_at=now - timedelta(seconds=1),
        outcome={
            "label": STATUS_DATA_UNAVAILABLE,
            "retryable": True,
            "next_attempt_at": (now - timedelta(seconds=1)).isoformat(),
        },
    )
    requeue_calls: List[str] = []
    original = store.requeue_pending

    def _requeue(*, prediction_id, as_of=None):
        requeue_calls.append(prediction_id)
        return original(prediction_id=prediction_id, as_of=as_of)

    store.requeue_pending = _requeue  # type: ignore[method-assign]
    payload = collect_prediction_resolver_diagnostics(
        config=_config(prediction_resolve_enabled=True),
        store=store,
        scheduler=None,
        now=now,
    )
    ids = [item["prediction_id"] for item in payload["oldest_due"]]
    assert ids == ["pred-pending", "pred-expired"]
    assert payload["claimable_due_count"] == 2
    assert payload["oldest_due"][1]["status"] == STATUS_RESOLVING
    assert requeue_calls == []
    assert store.get("pred-retry").status == STATUS_DATA_UNAVAILABLE  # type: ignore[union-attr]
    assert store.get("pred-pending").status == STATUS_PENDING  # type: ignore[union-attr]


def test_collect_oldest_due_caps_at_ten_and_keep_oldest_first() -> None:
    store = InMemoryPredictionStore()
    store._clock = _now
    now = _now()
    for index in range(12):
        _insert(
            store,
            prediction_id=f"pred-{index:02d}",
            resolve_after_hours=12 - index,
        )
    payload = collect_prediction_resolver_diagnostics(
        config=_config(),
        store=store,
        now=now,
    )
    ids = [item["prediction_id"] for item in payload["oldest_due"]]
    assert payload["claimable_due_count"] == 12
    assert len(ids) == OLDEST_DUE_LIMIT
    assert ids == [f"pred-{index:02d}" for index in range(10)]
    assert payload["oldest_due"][0]["lag_seconds"] >= payload["oldest_due"][-1]["lag_seconds"]
    assert payload["claimable_due_truncated"] is False


def test_collect_truncated_when_probe_hits_cap(monkeypatch) -> None:
    import src.services.prediction_resolver_diagnostics as diagnostics

    monkeypatch.setattr(diagnostics, "PREDICTION_RESOLVER_BACKLOG_PROBE_LIMIT", 2)
    store = InMemoryPredictionStore()
    store._clock = _now
    for index in range(3):
        _insert(store, prediction_id=f"pred-{index}", resolve_after_hours=3 - index)
    payload = collect_prediction_resolver_diagnostics(
        config=_config(prediction_resolve_max_per_tick=1),
        store=store,
        now=_now(),
    )
    assert payload["claimable_due_probe_limit"] == 2
    assert payload["claimable_due_count"] == 2
    assert payload["claimable_due_truncated"] is True
    assert [item["prediction_id"] for item in payload["oldest_due"]] == ["pred-0", "pred-1"]


def test_collect_store_failure_is_explicit() -> None:
    class _BrokenStore:
        def list_due(self, *, as_of, limit, statuses=None):
            raise RuntimeError("db down")

    with pytest.raises(PredictionResolverDiagnosticsStoreError):
        collect_prediction_resolver_diagnostics(
            config=_config(),
            store=_BrokenStore(),
            now=_now(),
        )


def test_collect_registration_bit_is_this_process_cache_only() -> None:
    store = InMemoryPredictionStore()
    store._clock = _now

    class _TrapScheduler:
        def __init__(self) -> None:
            self.calls: List[str] = []

        def has_registered_background_task(self, name: str) -> bool:
            self.calls.append(name)
            return name == "prediction_resolver"

        def start(self) -> None:
            raise AssertionError("diagnostics must not start the scheduler")

        def _current_prediction_resolver_background_tasks(self, config):
            raise AssertionError("diagnostics must not construct a worker")

    scheduler = _TrapScheduler()
    payload = collect_prediction_resolver_diagnostics(
        config=_config(prediction_resolve_enabled=True),
        store=store,
        scheduler=scheduler,
        now=_now(),
    )
    assert payload["this_process_worker_registered"] is True
    assert scheduler.calls == ["prediction_resolver"]

    missing = collect_prediction_resolver_diagnostics(
        config=_config(prediction_resolve_enabled=True),
        store=store,
        scheduler=None,
        now=_now(),
    )
    assert missing["this_process_worker_registered"] is False
