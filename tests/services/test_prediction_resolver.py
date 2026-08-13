# -*- coding: utf-8 -*-
"""End-to-end tests for PredictionResolver.tick (#1102 / #1116)."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Mapping, Optional, Sequence
from unittest.mock import patch

import pytest

from src.services.prediction_resolver import (
    PREDICTION_RESOLVER_BACKGROUND_TASK_NAME,
    InMemoryPredictionStore,
    PredictionResolver,
    TickSummary,
    build_prediction_resolver_background_tasks,
    derive_aggregate_label,
)
from src.services.prediction_resolver.memory_store import (
    STATUS_DATA_UNAVAILABLE,
    STATUS_PENDING,
    STATUS_RESOLVED,
    STATUS_RESOLVING,
)


@dataclass
class _Bar:
    close: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None


@dataclass
class _Snapshot:
    status: str = "ok"
    reason: Optional[str] = None
    retryable: bool = False
    as_of_bar: Optional[_Bar] = None
    end_bar: Optional[_Bar] = None
    return_pct: Optional[float] = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    @property
    def data_unavailable(self) -> bool:
        return self.status != "ok"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "retryable": self.retryable,
            "ok": self.ok,
            "data_unavailable": self.data_unavailable,
        }


@dataclass
class _DatedSnapshot(_Snapshot):
    as_of: date = date(2026, 8, 11)
    end: date = date(2026, 8, 12)

    def to_dict(self) -> Dict[str, Any]:
        payload = super().to_dict()
        payload.update({"as_of": self.as_of.isoformat(), "end": self.end.isoformat()})
        return payload


class _JsonStrictMemoryStore(InMemoryPredictionStore):
    def resolve(self, **kwargs: Any):
        json.dumps(kwargs["outcome"], allow_nan=False)
        return super().resolve(**kwargs)


class _FakeFetcher:
    def __init__(self, snapshot: _Snapshot) -> None:
        self.snapshot = snapshot
        self.calls: List[Dict[str, Any]] = []

    def fetch(self, **kwargs: Any) -> _Snapshot:
        self.calls.append(dict(kwargs))
        return self.snapshot


@dataclass
class _ClaimResult:
    claim_id: str
    claim_type: str
    outcome: str
    score: Optional[float]
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "claim_type": self.claim_type,
            "outcome": self.outcome,
            "score": self.score,
            "reason": self.reason,
        }


@dataclass
class _Aggregate:
    total_claims: int
    scored_claims: int
    hit_count: int
    partial_count: int
    miss_count: int
    data_unavailable_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_claims": self.total_claims,
            "scored_claims": self.scored_claims,
            "hit_count": self.hit_count,
            "partial_count": self.partial_count,
            "miss_count": self.miss_count,
            "data_unavailable_count": self.data_unavailable_count,
        }


@dataclass
class _Report:
    claim_results: List[_ClaimResult]
    aggregate: _Aggregate
    scorer_version: str = "test-scorer"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claim_results": [c.to_dict() for c in self.claim_results],
            "aggregate": self.aggregate.to_dict(),
            "scorer_version": self.scorer_version,
        }


class _FakeScorer:
    def __init__(self) -> None:
        self.calls: List[Any] = []

    def score(self, claims: Sequence[Any], actuals: Any, config: Any = None) -> _Report:
        self.calls.append((list(claims), actuals, config))
        start = float(actuals["start_price"])
        end = float(actuals["end_price"])
        realized = "flat" if abs(end - start) / start <= 0.001 else ("up" if end > start else "down")
        claim = claims[0] if claims else {"direction": "up", "claim_id": "c1"}
        if isinstance(claim, Mapping):
            expected = claim.get("direction") or (claim.get("payload") or {}).get("direction")
            claim_id = str(claim.get("claim_id") or "c1")
        else:
            expected = getattr(claim, "direction", "up")
            claim_id = "c1"
        outcome = "hit" if expected == realized else "miss"
        score = 1.0 if outcome == "hit" else 0.0
        hit = 1 if outcome == "hit" else 0
        miss = 1 if outcome == "miss" else 0
        return _Report(
            claim_results=[_ClaimResult(claim_id, "direction", outcome, score, realized)],
            aggregate=_Aggregate(1, 1, hit, 0, miss, 0),
        )


def _now() -> datetime:
    return datetime(2026, 8, 12, 12, 0, 0)


def _seed(store: InMemoryPredictionStore, *, prediction_id: str = "pred-1", direction: str = "up") -> None:
    now = _now()
    store.insert(
        prediction_id=prediction_id,
        run_id="run-1",
        symbol="600519",
        market="cn",
        horizon="1d",
        resolve_after=now - timedelta(hours=1),
        created_at=now - timedelta(days=1),
        claims=[{
            "claim_id": "c1",
            "claim_type": "direction",
            "type": "direction",
            "direction": direction,
            "confidence": 0.7,
        }],
    )


def test_derive_aggregate_label_matrix() -> None:
    assert derive_aggregate_label(
        scored_claims=0, hit_count=0, partial_count=0, miss_count=0, data_unavailable_count=1
    ) == "data_unavailable"
    assert derive_aggregate_label(
        scored_claims=2, hit_count=2, partial_count=0, miss_count=0, data_unavailable_count=0
    ) == "hit"
    assert derive_aggregate_label(
        scored_claims=2, hit_count=0, partial_count=0, miss_count=2, data_unavailable_count=0
    ) == "miss"
    assert derive_aggregate_label(
        scored_claims=2, hit_count=1, partial_count=0, miss_count=1, data_unavailable_count=0
    ) == "partial"


def test_tick_resolves_due_prediction_end_to_end() -> None:
    store = InMemoryPredictionStore()
    store._clock = _now
    _seed(store, direction="up")
    fetcher = _FakeFetcher(
        _Snapshot(status="ok", as_of_bar=_Bar(100.0), end_bar=_Bar(105.0, 106.0, 99.0), return_pct=5.0)
    )
    scorer = _FakeScorer()
    events: List[str] = []

    class _Sink:
        def emit(self, event_type: str, payload: Mapping[str, Any]) -> None:
            events.append(event_type)

    resolver = PredictionResolver(
        store=store,
        actuals_fetcher=fetcher,
        claim_scorer=scorer,
        worker_id="worker-a",
        event_sink=_Sink(),
        clock=_now,
    )
    summary = resolver.tick()
    assert summary.claimed == 1
    assert summary.resolved == 1
    assert summary.data_unavailable == 0
    assert summary.items[0].label == "hit"
    row = store.get("pred-1")
    assert row is not None
    assert row.status == STATUS_RESOLVED
    assert row.outcome is not None
    assert row.outcome["label"] == "hit"
    assert row.lease_token is None
    assert fetcher.calls
    assert scorer.calls
    assert fetcher.calls[0]["as_of"] == date(2026, 8, 11)
    # A4 exposes only the final session's high/low, not full-window extrema.
    # They must not be forwarded as proof that a level was never crossed.
    assert scorer.calls[0][1]["high_price"] is None
    assert scorer.calls[0][1]["low_price"] is None
    assert "prediction.resolve.completed" in events


def test_tick_uses_prediction_as_of_not_row_creation_time() -> None:
    store = InMemoryPredictionStore()
    store._clock = _now
    store.insert(
        prediction_id="pred-window",
        run_id="run-window",
        symbol="AAPL",
        market="us",
        horizon="1d",
        as_of=date(2026, 8, 8),
        resolve_after=_now() - timedelta(hours=1),
        created_at=_now() - timedelta(days=1),
        claims=[{"claim_id": "c1", "claim_type": "direction", "direction": "up"}],
    )
    fetcher = _FakeFetcher(
        _Snapshot(status="ok", as_of_bar=_Bar(100.0), end_bar=_Bar(101.0))
    )
    resolver = PredictionResolver(
        store=store,
        actuals_fetcher=fetcher,
        claim_scorer=_FakeScorer(),
        clock=_now,
    )

    assert resolver.tick().resolved == 1
    assert fetcher.calls[0]["as_of"] == date(2026, 8, 8)


def test_tick_uses_snapshot_json_projection_for_persistence() -> None:
    store = _JsonStrictMemoryStore()
    store._clock = _now
    _seed(store)
    fetcher = _FakeFetcher(
        _DatedSnapshot(
            status="ok",
            as_of_bar=_Bar(100.0),
            end_bar=_Bar(105.0),
            return_pct=5.0,
        )
    )
    resolver = PredictionResolver(
        store=store,
        actuals_fetcher=fetcher,
        claim_scorer=_FakeScorer(),
        clock=_now,
    )

    summary = resolver.tick()

    assert summary.resolved == 1
    row = store.get("pred-1")
    assert row is not None and row.outcome is not None
    assert row.outcome["actuals"]["as_of"] == "2026-08-11"


def test_tick_provider_failure_never_fabricates_hit() -> None:
    store = InMemoryPredictionStore()
    store._clock = _now
    _seed(store)
    fetcher = _FakeFetcher(_Snapshot(status="provider_down", reason="provider_failure", retryable=True))
    scorer = _FakeScorer()
    resolver = PredictionResolver(
        store=store,
        actuals_fetcher=fetcher,
        claim_scorer=scorer,
        worker_id="worker-b",
        clock=_now,
    )
    summary = resolver.tick()
    assert summary.resolved == 0
    assert summary.data_unavailable == 1
    assert scorer.calls == []
    row = store.get("pred-1")
    assert row is not None
    assert row.status == STATUS_DATA_UNAVAILABLE
    assert row.outcome is not None
    assert row.outcome["label"] == "data_unavailable"
    assert row.outcome.get("reason") == "provider_failure"


def test_data_unavailable_cas_loss_is_counted_as_skipped() -> None:
    class _LostLeaseStore(InMemoryPredictionStore):
        def mark_data_unavailable(self, **kwargs: Any):
            return False, self.get(kwargs["prediction_id"])

    store = _LostLeaseStore()
    store._clock = _now
    _seed(store)
    resolver = PredictionResolver(
        store=store,
        actuals_fetcher=_FakeFetcher(
            _Snapshot(status="provider_down", reason="provider_failure", retryable=True)
        ),
        claim_scorer=_FakeScorer(),
        clock=_now,
    )

    summary = resolver.tick()

    assert summary.claimed == 1
    assert summary.data_unavailable == 0
    assert summary.skipped == 1
    assert summary.items[0].disposition == "skipped"
    assert summary.items[0].reason == "data_unavailable_not_applied"
    assert summary.items[0].applied is False


def test_claim_failure_is_not_counted_as_claimed() -> None:
    class _ClaimFailureStore(InMemoryPredictionStore):
        def claim_for_resolve(self, **kwargs: Any):
            raise RuntimeError("claim failed")

    store = _ClaimFailureStore()
    store._clock = _now
    _seed(store)
    resolver = PredictionResolver(
        store=store,
        actuals_fetcher=_FakeFetcher(_Snapshot()),
        claim_scorer=_FakeScorer(),
        clock=_now,
    )

    summary = resolver.tick()

    assert summary.claimed == 0
    assert summary.errors == 1
    assert summary.items[0].reason == "claim_failed"


def test_explicit_limit_can_only_narrow_configured_batch_cap() -> None:
    store = InMemoryPredictionStore()
    store._clock = _now
    _seed(store, prediction_id="pred-1")
    _seed(store, prediction_id="pred-2")
    fetcher = _FakeFetcher(
        _Snapshot(status="ok", as_of_bar=_Bar(100.0), end_bar=_Bar(101.0))
    )
    resolver = PredictionResolver(
        store=store,
        actuals_fetcher=fetcher,
        claim_scorer=_FakeScorer(),
        max_per_tick=1,
        clock=_now,
    )

    summary = resolver.tick(limit=10)

    assert summary.claimed == 1
    assert len(fetcher.calls) == 1


def test_explicit_limit_cannot_reenable_zero_batch_cap() -> None:
    store = InMemoryPredictionStore()
    store._clock = _now
    _seed(store)
    resolver = PredictionResolver(
        store=store,
        actuals_fetcher=_FakeFetcher(
            _Snapshot(status="ok", as_of_bar=_Bar(100.0), end_bar=_Bar(101.0))
        ),
        claim_scorer=_FakeScorer(),
        max_per_tick=0,
        clock=_now,
    )

    assert resolver.tick(limit=1).claimed == 0


@pytest.mark.parametrize("limit", [True, -1, 10_001, 1.5])
def test_explicit_limit_rejects_invalid_values(limit: Any) -> None:
    resolver = PredictionResolver(
        store=InMemoryPredictionStore(),
        actuals_fetcher=_FakeFetcher(_Snapshot()),
        claim_scorer=_FakeScorer(),
        clock=_now,
    )

    with pytest.raises(ValueError):
        resolver.tick(limit=limit)


@pytest.mark.parametrize("worker_id", ["", "   ", "x" * 129, "worker\nforged"])
def test_worker_id_rejects_store_and_log_unsafe_values(worker_id: str) -> None:
    with pytest.raises(ValueError):
        PredictionResolver(
            store=InMemoryPredictionStore(),
            actuals_fetcher=_FakeFetcher(_Snapshot()),
            claim_scorer=_FakeScorer(),
            worker_id=worker_id,
        )


def test_non_retryable_provider_outcome_is_not_requeued() -> None:
    store = InMemoryPredictionStore()
    store._clock = _now
    _seed(store)
    resolver = PredictionResolver(
        store=store,
        actuals_fetcher=_FakeFetcher(
            _Snapshot(status="delisted", reason="delisted", retryable=False)
        ),
        claim_scorer=_FakeScorer(),
        clock=_now,
    )

    assert resolver.tick().data_unavailable == 1
    row = store.get("pred-1")
    assert row is not None
    assert row.retry_exhausted is True
    assert row.next_attempt_at is None
    assert resolver.tick(now=_now() + timedelta(days=10)).claimed == 0


def test_tick_overlap_skips_second_call() -> None:
    store = InMemoryPredictionStore()
    store._clock = _now
    _seed(store)
    started = threading.Event()
    release = threading.Event()

    class _SlowFetcher:
        def fetch(self, **kwargs: Any) -> _Snapshot:
            started.set()
            release.wait(timeout=2.0)
            return _Snapshot(status="ok", as_of_bar=_Bar(100.0), end_bar=_Bar(101.0))

    resolver = PredictionResolver(
        store=store,
        actuals_fetcher=_SlowFetcher(),
        claim_scorer=_FakeScorer(),
        worker_id="worker-c",
        clock=_now,
    )
    results: List[Any] = []

    def _run() -> None:
        results.append(resolver.tick())

    t = threading.Thread(target=_run)
    t.start()
    assert started.wait(timeout=2.0)
    overlap = resolver.tick()
    assert overlap.skipped_overlap is True
    assert overlap.claimed == 0
    release.set()
    t.join(timeout=2.0)
    assert results and results[0].resolved == 1


def test_second_worker_cannot_double_resolve() -> None:
    store = InMemoryPredictionStore()
    store._clock = _now
    _seed(store)
    claimed_a = store.claim_for_resolve(
        prediction_id="pred-1", lease_owner="a", lease_token="token-a", as_of=_now()
    )
    assert claimed_a is not None and claimed_a.status == STATUS_RESOLVING
    assert store.claim_for_resolve(
        prediction_id="pred-1", lease_owner="b", lease_token="token-b", as_of=_now()
    ) is None
    applied_a, row = store.resolve(
        prediction_id="pred-1", outcome={"label": "hit"}, expected_lease_token="token-a", as_of=_now()
    )
    assert applied_a is True and row is not None and row.status == STATUS_RESOLVED
    applied_b, row2 = store.resolve(
        prediction_id="pred-1", outcome={"label": "miss"}, expected_lease_token="token-b", as_of=_now()
    )
    assert applied_b is False
    assert row2 is not None and row2.outcome is not None and row2.outcome["label"] == "hit"


def test_future_resolve_after_not_claimed() -> None:
    store = InMemoryPredictionStore()
    store._clock = _now
    store.insert(
        prediction_id="pred-future",
        run_id="run-x",
        symbol="AAPL",
        market="us",
        horizon="5d",
        resolve_after=_now() + timedelta(days=1),
        created_at=_now(),
        claims=[{"claim_id": "c1", "claim_type": "direction", "direction": "up"}],
    )
    resolver = PredictionResolver(
        store=store,
        actuals_fetcher=_FakeFetcher(_Snapshot(status="ok", as_of_bar=_Bar(1.0), end_bar=_Bar(2.0))),
        claim_scorer=_FakeScorer(),
        clock=_now,
    )
    summary = resolver.tick()
    assert summary.claimed == 0
    assert store.get("pred-future").status == STATUS_PENDING  # type: ignore[union-attr]


def test_build_background_tasks_gated() -> None:
    assert build_prediction_resolver_background_tasks(
        SimpleNamespace(prediction_resolve_enabled=False)
    ) == []
    store = InMemoryPredictionStore()
    store._clock = _now
    _seed(store, direction="up")
    resolver = PredictionResolver(
        store=store,
        actuals_fetcher=_FakeFetcher(
            _Snapshot(status="ok", as_of_bar=_Bar(100.0), end_bar=_Bar(90.0))
        ),
        claim_scorer=_FakeScorer(),
        clock=_now,
    )
    on = build_prediction_resolver_background_tasks(
        SimpleNamespace(
            prediction_resolve_enabled=True,
            prediction_resolve_interval_seconds=90,
            prediction_resolve_lease_seconds=120,
            prediction_resolve_max_per_tick=50,
            prediction_resolve_max_attempts=5,
        ),
        resolver=resolver,
    )
    assert len(on) == 1
    assert on[0]["name"] == PREDICTION_RESOLVER_BACKGROUND_TASK_NAME
    assert on[0]["interval_seconds"] == 90
    on[0]["task"]()
    row = store.get("pred-1")
    assert row is not None and row.status == STATUS_RESOLVED
    assert row.outcome is not None and row.outcome["label"] == "miss"


def test_cli_main_json_success(capsys: pytest.CaptureFixture[str]) -> None:
    store = InMemoryPredictionStore()
    store._clock = _now
    _seed(store)
    resolver = PredictionResolver(
        store=store,
        actuals_fetcher=_FakeFetcher(
            _Snapshot(status="ok", as_of_bar=_Bar(100.0), end_bar=_Bar(105.0))
        ),
        claim_scorer=_FakeScorer(),
        clock=_now,
    )
    with patch(
        "src.services.prediction_resolver.__main__.build_prediction_resolver",
        return_value=resolver,
    ):
        from src.services.prediction_resolver.__main__ import main

        code = main(["--json"])
    assert code == 0
    out = capsys.readouterr().out
    assert "resolved" in out


def test_cli_honors_zero_batch_cap() -> None:
    from src.services.prediction_resolver.__main__ import main

    config = SimpleNamespace(
        prediction_resolve_lease_seconds=120,
        prediction_resolve_max_per_tick=0,
        prediction_resolve_max_attempts=5,
    )
    resolver = SimpleNamespace(tick=lambda **kwargs: TickSummary())
    with patch(
        "src.application_services.get_application_services",
        return_value=SimpleNamespace(config=config),
    ), patch(
        "src.services.prediction_resolver.__main__.build_prediction_resolver",
        return_value=resolver,
    ) as build_resolver:
        assert main([]) == 0

    assert build_resolver.call_args.kwargs["max_per_tick"] == 0


def test_cli_config_failure_does_not_run_with_defaults() -> None:
    from src.services.prediction_resolver.__main__ import main

    with patch(
        "src.application_services.get_application_services",
        side_effect=RuntimeError("config unavailable"),
    ), patch(
        "src.services.prediction_resolver.__main__.build_prediction_resolver",
    ) as build_resolver:
        assert main([]) == 2

    build_resolver.assert_not_called()


def test_cli_invalid_resolver_configuration_returns_failure() -> None:
    from src.services.prediction_resolver.__main__ import main

    config = SimpleNamespace(
        prediction_resolve_lease_seconds=120,
        prediction_resolve_max_per_tick=50,
        prediction_resolve_max_attempts=5,
    )
    with patch(
        "src.application_services.get_application_services",
        return_value=SimpleNamespace(config=config),
    ), patch(
        "src.services.prediction_resolver.__main__.build_prediction_resolver",
        side_effect=ValueError("invalid worker id"),
    ):
        assert main(["--worker-id", "invalid"]) == 2


def test_cli_tick_failure_returns_failure() -> None:
    from src.services.prediction_resolver.__main__ import main

    config = SimpleNamespace(
        prediction_resolve_lease_seconds=120,
        prediction_resolve_max_per_tick=50,
        prediction_resolve_max_attempts=5,
    )
    resolver = SimpleNamespace(
        tick=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("tick failed"))
    )
    with patch(
        "src.application_services.get_application_services",
        return_value=SimpleNamespace(config=config),
    ), patch(
        "src.services.prediction_resolver.__main__.build_prediction_resolver",
        return_value=resolver,
    ):
        assert main([]) == 2


def test_runtime_scheduler_registers_prediction_resolver_task() -> None:
    from src.services.runtime_scheduler import RuntimeSchedulerService

    class _FakeScheduler:
        def __init__(self, **kwargs):
            self.background_tasks = []

        def set_daily_task(self, task, run_immediately: bool) -> None:
            return None

        def add_background_task(self, task, interval_seconds: int, run_immediately: bool = False, name=None) -> None:
            self.background_tasks.append({
                "task": task,
                "interval_seconds": interval_seconds,
                "run_immediately": run_immediately,
                "name": name,
            })

        def run(self) -> None:
            return None

        def stop(self) -> None:
            return None

        @property
        def schedule(self):
            class _N:
                @staticmethod
                def get_jobs():
                    return []
            return _N

    class _NoopThread:
        def __init__(self, *args, **kwargs):
            pass

        def start(self) -> None:
            return None

    store = InMemoryPredictionStore()
    resolver = PredictionResolver(
        store=store,
        actuals_fetcher=_FakeFetcher(_Snapshot(status="ok", as_of_bar=_Bar(1.0), end_bar=_Bar(1.0))),
        claim_scorer=_FakeScorer(),
    )
    config = SimpleNamespace(
        schedule_enabled=True,
        schedule_time="18:00",
        schedule_times=["18:00"],
        prediction_resolve_enabled=True,
        prediction_resolve_interval_seconds=75,
        prediction_resolve_lease_seconds=120,
        prediction_resolve_max_per_tick=10,
        prediction_resolve_max_attempts=5,
        agent_event_monitor_enabled=False,
        daily_brief_enabled=False,
    )
    service = RuntimeSchedulerService(config_provider=lambda: config)
    service._reload_config = lambda: config
    with patch("src.services.runtime_scheduler.Scheduler", _FakeScheduler), patch(
        "src.services.runtime_scheduler.threading.Thread", _NoopThread
    ), patch(
        "src.services.prediction_resolver.resolver.build_prediction_resolver",
        return_value=resolver,
    ):
        service.start()
    names = [t["name"] for t in service._scheduler.background_tasks]  # type: ignore[union-attr]
    assert PREDICTION_RESOLVER_BACKGROUND_TASK_NAME in names
    task = next(t for t in service._scheduler.background_tasks if t["name"] == PREDICTION_RESOLVER_BACKGROUND_TASK_NAME)  # type: ignore[union-attr]
    assert task["interval_seconds"] == 75


def test_expired_resolving_lease_is_reclaimed_on_next_tick() -> None:
    """Crash-recovery: expired resolving rows must re-enter list_due."""
    store = InMemoryPredictionStore()
    store._clock = _now
    now = _now()
    store.insert(
        prediction_id="pred-stale",
        run_id="run-stale",
        symbol="600519",
        market="cn",
        horizon="1d",
        resolve_after=now - timedelta(hours=2),
        created_at=now - timedelta(days=1),
        claims=[{"claim_id": "c1", "claim_type": "direction", "direction": "up"}],
        status=STATUS_RESOLVING,
        attempts=1,
        lease_owner="dead-worker",
        lease_token="old-token",
        lease_expires_at=now - timedelta(minutes=5),
    )
    # Due scan must surface the expired lease without a manual requeue.
    due = store.list_due(as_of=now, limit=10)
    assert [r.prediction_id for r in due] == ["pred-stale"]

    resolver = PredictionResolver(
        store=store,
        actuals_fetcher=_FakeFetcher(
            _Snapshot(status="ok", as_of_bar=_Bar(100.0), end_bar=_Bar(105.0))
        ),
        claim_scorer=_FakeScorer(),
        worker_id="worker-recover",
        clock=_now,
    )
    summary = resolver.tick()
    assert summary.claimed == 1
    assert summary.resolved == 1
    row = store.get("pred-stale")
    assert row is not None
    assert row.status == STATUS_RESOLVED
    assert row.outcome is not None
    assert row.outcome["label"] == "hit"
    assert row.lease_token is None


def test_data_unavailable_respects_backoff_and_max_attempts() -> None:
    store = InMemoryPredictionStore()
    store._clock = _now
    _seed(store)
    fetcher = _FakeFetcher(
        _Snapshot(status="provider_down", reason="provider_failure", retryable=True)
    )
    resolver = PredictionResolver(
        store=store,
        actuals_fetcher=fetcher,
        claim_scorer=_FakeScorer(),
        worker_id="worker-retry",
        max_attempts=2,
        clock=_now,
    )
    first = resolver.tick()
    assert first.data_unavailable == 1
    row = store.get("pred-1")
    assert row is not None
    assert row.status == STATUS_DATA_UNAVAILABLE
    assert row.attempts == 1
    assert row.retry_exhausted is False
    assert row.next_attempt_at is not None
    assert row.next_attempt_at > _now()
    # Backoff not elapsed: second tick must not reclaim.
    second = resolver.tick()
    assert second.claimed == 0
    assert store.get("pred-1").attempts == 1  # type: ignore[union-attr]

    # Advance clock past backoff.
    later = row.next_attempt_at + timedelta(seconds=1)
    store._clock = lambda: later
    resolver._clock = lambda: later
    third = resolver.tick()
    assert third.data_unavailable == 1
    row2 = store.get("pred-1")
    assert row2 is not None
    assert row2.attempts == 2
    assert row2.retry_exhausted is True
    # Exhausted rows stay out of due scan forever (until external requeue).
    fourth = resolver.tick()
    assert fourth.claimed == 0


def test_a3_style_status_scan_still_honors_durable_backoff() -> None:
    class _A3ShapeStore(InMemoryPredictionStore):
        def list_due(self, *, as_of, limit, statuses=None):
            if statuses == (STATUS_DATA_UNAVAILABLE,):
                with self._lock:
                    rows = [
                        row.snapshot()
                        for row in self._rows.values()
                        if row.status == STATUS_DATA_UNAVAILABLE
                        and row.resolve_after <= as_of
                    ]
                return rows[:limit]
            return super().list_due(as_of=as_of, limit=limit, statuses=statuses)

    store = _A3ShapeStore()
    store._clock = _now
    _seed(store)
    resolver = PredictionResolver(
        store=store,
        actuals_fetcher=_FakeFetcher(
            _Snapshot(status="provider_down", reason="provider_failure", retryable=True)
        ),
        claim_scorer=_FakeScorer(),
        max_attempts=2,
        clock=_now,
    )

    assert resolver.tick().data_unavailable == 1
    row = store.get("pred-1")
    assert row is not None and row.next_attempt_at is not None
    assert resolver.tick(now=_now() + timedelta(seconds=1)).claimed == 0
    assert resolver.tick(now=row.next_attempt_at + timedelta(seconds=1)).claimed == 1


def test_writeback_failure_is_reported_and_lease_is_left_for_recovery() -> None:
    class _FailingWriteStore(InMemoryPredictionStore):
        def mark_data_unavailable(self, **kwargs):
            raise RuntimeError("database unavailable")

    store = _FailingWriteStore()
    store._clock = _now
    _seed(store)
    resolver = PredictionResolver(
        store=store,
        actuals_fetcher=_FakeFetcher(
            _Snapshot(status="provider_down", reason="provider_failure", retryable=True)
        ),
        claim_scorer=_FakeScorer(),
        clock=_now,
    )

    summary = resolver.tick()
    assert summary.data_unavailable == 0
    assert summary.errors == 1
    assert summary.items[0].reason == "data_unavailable_write_failed"
    row = store.get("pred-1")
    assert row is not None and row.status == STATUS_RESOLVING


def test_aware_clock_is_normalized_for_a3_naive_utc_contract() -> None:
    aware_now = _now().replace(tzinfo=timezone.utc)
    store = InMemoryPredictionStore()
    store._clock = _now
    _seed(store)
    resolver = PredictionResolver(
        store=store,
        actuals_fetcher=_FakeFetcher(
            _Snapshot(status="ok", as_of_bar=_Bar(100.0), end_bar=_Bar(101.0))
        ),
        claim_scorer=_FakeScorer(),
        clock=lambda: aware_now,
    )

    assert resolver.tick().resolved == 1


def test_compute_retry_delay_is_bounded() -> None:
    from src.services.prediction_resolver import compute_retry_delay_seconds

    assert compute_retry_delay_seconds(1, base_seconds=30, max_seconds=3600) == 30
    assert compute_retry_delay_seconds(2, base_seconds=30, max_seconds=3600) == 60
    assert compute_retry_delay_seconds(20, base_seconds=30, max_seconds=3600) == 3600
    assert compute_retry_delay_seconds(10**9, base_seconds=30, max_seconds=3600) == 3600
    with pytest.raises(ValueError):
        compute_retry_delay_seconds(True)
    with pytest.raises(ValueError):
        compute_retry_delay_seconds(1, base_seconds=float("nan"))
