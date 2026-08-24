# -*- coding: utf-8 -*-
"""Production-path tests for resolver postmortem drain (#1103)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Sequence
from unittest.mock import patch

from src.agent.evolution.episode_lessons import InMemoryEpisodeLessonSink
from src.services.prediction_resolver import (
    InMemoryPostmortemQueue,
    InMemoryPredictionStore,
    PostmortemJob,
    PredictionResolver,
    build_prediction_resolver_background_tasks,
    drain_postmortem_queue,
    map_postmortem_job_to_input,
    maybe_build_postmortem_queue,
)
from src.services.prediction_resolver.memory_store import STATUS_RESOLVED
from src.services.prediction_resolver.postmortem_drain import (
    default_postmortem_lesson_sink,
    handle_postmortem_job,
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
    as_of_bar: Optional[_Bar] = None
    end_bar: Optional[_Bar] = None

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
            "start_price": getattr(self.as_of_bar, "close", None),
            "end_price": getattr(self.end_bar, "close", None),
        }


@dataclass
class _ClaimResult:
    claim_id: str
    claim_type: str
    outcome: str
    score: Optional[float]
    reason: str = ""
    confidence: Optional[float] = None
    actual_direction: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "claim_id": self.claim_id,
            "claim_type": self.claim_type,
            "outcome": self.outcome,
            "score": self.score,
            "reason": self.reason,
            "confidence": self.confidence,
            "actual_direction": self.actual_direction,
        }
        if self.details is not None:
            payload["details"] = dict(self.details)
        return payload


@dataclass
class _Aggregate:
    scored_claims: int = 1
    hit_count: int = 0
    partial_count: int = 0
    miss_count: int = 0
    data_unavailable_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claim_results": [item.to_dict() for item in self.claim_results],
            "aggregate": self.aggregate.to_dict(),
        }


class _Fetcher:
    def __init__(self, snapshot: _Snapshot) -> None:
        self.snapshot = snapshot
        self.calls: List[Dict[str, Any]] = []

    def fetch(self, **kwargs: Any) -> _Snapshot:
        self.calls.append(dict(kwargs))
        return self.snapshot


class _Scorer:
    def __init__(self, *, outcome: str = "miss", confidence: float = 0.9) -> None:
        self.outcome = outcome
        self.confidence = confidence
        self.calls = 0

    def score(self, claims: Sequence[Any], actuals: Any, config: Any = None) -> _Report:
        self.calls += 1
        claim = claims[0] if claims else {"claim_id": "c1", "direction": "up"}
        claim_id = str(claim.get("claim_id") or "c1") if isinstance(claim, dict) else "c1"
        hit = 1 if self.outcome == "hit" else 0
        miss = 1 if self.outcome == "miss" else 0
        partial = 1 if self.outcome == "partial" else 0
        unavailable = 1 if self.outcome == "data_unavailable" else 0
        actual_direction = "down" if self.outcome == "miss" else "up"
        return _Report(
            claim_results=[
                _ClaimResult(
                    claim_id=claim_id,
                    claim_type="direction",
                    outcome=self.outcome,
                    score=1.0 if self.outcome == "hit" else 0.0,
                    confidence=self.confidence,
                    actual_direction=actual_direction,
                )
            ],
            aggregate=_Aggregate(
                scored_claims=1,
                hit_count=hit,
                partial_count=partial,
                miss_count=miss,
                data_unavailable_count=unavailable,
            ),
        )


def _config(**kwargs: Any) -> SimpleNamespace:
    base = {
        "prediction_resolve_enabled": True,
        "prediction_resolve_interval_seconds": 60,
        "prediction_resolve_lease_seconds": 120,
        "prediction_resolve_max_per_tick": 50,
        "prediction_resolve_max_attempts": 5,
        "prediction_resolve_fetch_concurrency": 4,
        "prediction_resolve_postmortem_max_per_tick": 10,
        "prediction_resolve_provider_error_circuit_threshold": 5,
        "prediction_resolve_provider_error_circuit_cooldown_seconds": 60,
        "prediction_resolve_circuit_open_max_per_tick": 5,
        "prediction_resolve_retry_jitter_ratio": 0.1,
        "agent_postmortem_enabled": True,
        "agent_postmortem_llm_budget": 8,
        "agent_postmortem_skip_clean_hits": True,
        "agent_episode_log_enabled": False,
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def _seed(
    store: InMemoryPredictionStore,
    *,
    prediction_id: str = "pred-1",
    direction: str = "up",
    confidence: float = 0.9,
) -> None:
    store.insert(
        prediction_id=prediction_id,
        run_id="run-1",
        symbol="600519",
        market="cn",
        horizon="1d",
        as_of=date(2026, 8, 10),
        resolve_after=NOW - timedelta(hours=1),
        created_at=NOW - timedelta(days=1),
        claims=[
            {
                "claim_id": "c1",
                "claim_type": "direction",
                "type": "direction",
                "direction": direction,
                "confidence": confidence,
            }
        ],
    )


def _resolver(
    store: InMemoryPredictionStore,
    *,
    outcome: str = "miss",
    snapshot: Optional[_Snapshot] = None,
    queue: Any = None,
) -> PredictionResolver:
    fetcher = _Fetcher(
        snapshot
        or _Snapshot(as_of_bar=_Bar(100.0), end_bar=_Bar(90.0))
    )
    return PredictionResolver(
        store=store,
        actuals_fetcher=fetcher,
        claim_scorer=_Scorer(outcome=outcome),
        postmortem_queue=queue,
        clock=lambda: NOW,
    )


def test_production_factory_off_keeps_queue_none_and_writes_no_lessons() -> None:
    config = _config(agent_postmortem_enabled=False)
    queue = maybe_build_postmortem_queue(config)
    store = InMemoryPredictionStore()
    store._clock = lambda: NOW
    _seed(store)
    sidecar = default_postmortem_lesson_sink()
    sidecar.clear()
    resolver = _resolver(store, queue=queue)

    with patch(
        "src.services.prediction_resolver.resolver.build_prediction_resolver",
        return_value=resolver,
    ) as build:
        tasks = build_prediction_resolver_background_tasks(config)

    try:
        assert queue is None
        assert build.call_args.kwargs["postmortem_queue"] is None
        tasks[0]["task"]()
        row = store.get("pred-1")
        assert row is not None and row.status == STATUS_RESOLVED
        assert row.outcome is not None and row.outcome["label"] == "miss"
        assert sidecar.records == []
    finally:
        sidecar.clear()


def test_production_factory_on_injects_queue() -> None:
    config = _config(agent_postmortem_enabled=True)
    sentinel = _resolver(InMemoryPredictionStore())
    with patch(
        "src.services.prediction_resolver.resolver.build_prediction_resolver",
        return_value=sentinel,
    ) as build:
        tasks = build_prediction_resolver_background_tasks(config)

    assert len(tasks) == 1
    injected = build.call_args.kwargs["postmortem_queue"]
    assert isinstance(injected, InMemoryPostmortemQueue)


def test_miss_drain_produces_overconfidence_lesson_from_fixture_score() -> None:
    config = _config()
    queue = maybe_build_postmortem_queue(config)
    store = InMemoryPredictionStore()
    store._clock = lambda: NOW
    _seed(store)
    sidecar = default_postmortem_lesson_sink()
    sidecar.clear()
    resolver = _resolver(store, outcome="miss", queue=queue)
    tasks = build_prediction_resolver_background_tasks(config, resolver=resolver)
    try:
        tasks[0]["task"]()
        row = store.get("pred-1")
        assert row is not None and row.status == STATUS_RESOLVED
        assert queue is not None and queue.depth() == 0
        kinds = [
            lesson["kind"]
            for record in sidecar.records
            for lesson in record["lessons"]
        ]
        assert "overconfidence" in kinds
        assert all(record["layer"] == "postmortem" for record in sidecar.records)
    finally:
        sidecar.clear()


def test_partial_drain_produces_horizon_mismatch_lesson() -> None:
    config = _config()
    queue = maybe_build_postmortem_queue(config)
    store = InMemoryPredictionStore()
    store._clock = lambda: NOW
    _seed(store)
    sink = InMemoryEpisodeLessonSink()
    resolver = _resolver(store, outcome="partial", queue=queue)
    resolver.tick()

    drained = drain_postmortem_queue(
        queue,
        skipped_overlap=False,
        max_items=10,
        config=config,
        sink=sink,
    )

    assert drained == 1
    kinds = [lesson["kind"] for record in sink.records for lesson in record["lessons"]]
    assert kinds == ["horizon_mismatch"]


def test_hit_is_not_enqueued_and_produces_no_lessons() -> None:
    config = _config()
    queue = maybe_build_postmortem_queue(config)
    store = InMemoryPredictionStore()
    store._clock = lambda: NOW
    _seed(store)
    sink = InMemoryEpisodeLessonSink()
    resolver = _resolver(
        store,
        outcome="hit",
        snapshot=_Snapshot(as_of_bar=_Bar(100.0), end_bar=_Bar(105.0)),
        queue=queue,
    )

    summary = resolver.tick()
    drained = drain_postmortem_queue(
        queue,
        skipped_overlap=False,
        max_items=10,
        config=config,
        sink=sink,
    )

    assert summary.resolved == 1
    assert summary.postmortem_enqueued == 0
    assert drained == 0
    assert sink.records == []
    assert store.get("pred-1").status == STATUS_RESOLVED  # type: ignore[union-attr]


def test_data_unavailable_is_not_enqueued() -> None:
    config = _config()
    queue = maybe_build_postmortem_queue(config)
    store = InMemoryPredictionStore()
    store._clock = lambda: NOW
    _seed(store)
    sink = InMemoryEpisodeLessonSink()
    resolver = _resolver(
        store,
        snapshot=_Snapshot(status="provider_down", reason="provider_down"),
        queue=queue,
    )

    summary = resolver.tick()
    drained = drain_postmortem_queue(
        queue,
        skipped_overlap=False,
        max_items=10,
        config=config,
        sink=sink,
    )

    assert summary.data_unavailable == 1
    assert summary.postmortem_enqueued == 0
    assert drained == 0
    assert sink.records == []


def test_overlap_skip_does_not_drain_queued_jobs() -> None:
    config = _config()
    queue = maybe_build_postmortem_queue(config)
    assert queue is not None
    store = InMemoryPredictionStore()
    store._clock = lambda: NOW
    resolver = _resolver(store, queue=queue)
    tasks = build_prediction_resolver_background_tasks(config, resolver=resolver)
    assert queue.enqueue(
        prediction_id="queued-miss",
        outcome={"label": "miss", "run_id": "run-x"},
        priority=10,
    )

    acquired = resolver._tick_lock.acquire(blocking=False)
    assert acquired is True
    try:
        tasks[0]["task"]()
        assert queue.depth() == 1
    finally:
        resolver._tick_lock.release()


def test_drain_error_requeues_without_rolling_back_resolved_row() -> None:
    config = _config()
    queue = maybe_build_postmortem_queue(config)
    store = InMemoryPredictionStore()
    store._clock = lambda: NOW
    _seed(store)
    resolver = _resolver(store, outcome="miss", queue=queue)
    summary = resolver.tick()
    assert summary.resolved == 1
    assert store.get("pred-1").status == STATUS_RESOLVED  # type: ignore[union-attr]

    class _BoomSink(InMemoryEpisodeLessonSink):
        def append_lessons(self, **kwargs: Any) -> None:
            raise RuntimeError("episode sink failed")

    drained = drain_postmortem_queue(
        queue,
        skipped_overlap=False,
        max_items=10,
        config=config,
        sink=_BoomSink(),
    )

    assert drained == 0
    assert queue is not None and queue.depth() == 1
    assert store.get("pred-1").status == STATUS_RESOLVED  # type: ignore[union-attr]
    assert store.get("pred-1").outcome["label"] == "miss"  # type: ignore[union-attr,index]


def test_mapper_does_not_invent_direction_from_prices() -> None:
    job = PostmortemJob(
        prediction_id="pred-1",
        outcome={
            "label": "miss",
            "run_id": "run-1",
            "symbol": "AAPL",
            "market": "us",
            "score": {
                "claim_results": [
                    {
                        "claim_id": "c1",
                        "claim_type": "direction",
                        "outcome": "miss",
                        "confidence": 0.91,
                    }
                ]
            },
            "actuals": {"start_price": 100.0, "end_price": 90.0},
        },
        priority=10,
    )

    mapped = map_postmortem_job_to_input(job)

    assert mapped is not None
    assert mapped.claims[0].predicted == {}
    assert "direction" not in mapped.claims[0].actual
    assert mapped.claims[0].actual["start_price"] == 100.0
    assert mapped.run_id == "run-1"


def test_mapper_copies_stored_direction_and_run_id() -> None:
    job = PostmortemJob(
        prediction_id="pred-2",
        outcome={
            "label": "miss",
            "run_id": "run-2",
            "claims": [{"claim_id": "c1", "direction": "up", "confidence": 0.9}],
            "score": {
                "claim_results": [
                    {
                        "claim_id": "c1",
                        "claim_type": "direction",
                        "outcome": "miss",
                        "confidence": 0.9,
                        "actual_direction": "down",
                    }
                ]
            },
        },
        priority=10,
    )

    mapped = map_postmortem_job_to_input(job)

    assert mapped is not None
    assert mapped.claims[0].predicted == {"direction": "up"}
    assert mapped.claims[0].actual["direction"] == "down"


def test_missing_episode_does_not_fail_handle() -> None:
    config = _config(agent_episode_log_enabled=True)
    sink = InMemoryEpisodeLessonSink()
    job = PostmortemJob(
        prediction_id="pred-3",
        outcome={
            "label": "miss",
            "run_id": "missing-run",
            "claims": [{"claim_id": "c1", "direction": "up", "confidence": 0.9}],
            "score": {
                "claim_results": [
                    {
                        "claim_id": "c1",
                        "claim_type": "direction",
                        "outcome": "miss",
                        "confidence": 0.9,
                    }
                ]
            },
        },
        priority=10,
    )
    with patch(
        "src.services.agent_episode_service.AgentEpisodeService.get_by_run_id",
        return_value=[],
    ):
        handle_postmortem_job(job, config=config, sink=sink)

    assert sink.records
    assert sink.records[0]["episode_id"] == "missing-run"


def test_cli_drains_after_tick_when_enabled() -> None:
    config = _config()
    queue = InMemoryPostmortemQueue()
    resolver = SimpleNamespace(
        tick=lambda **kwargs: SimpleNamespace(skipped_overlap=False, as_dict=lambda: {})
    )
    with patch(
        "src.application_services.get_application_services",
        return_value=SimpleNamespace(config=config),
    ), patch(
        "src.services.prediction_resolver.__main__.maybe_build_postmortem_queue",
        return_value=queue,
    ), patch(
        "src.services.prediction_resolver.__main__.build_prediction_resolver",
        return_value=resolver,
    ), patch(
        "src.services.prediction_resolver.__main__.drain_postmortem_queue",
        return_value=0,
    ) as drain:
        from src.services.prediction_resolver.__main__ import main

        assert main(["--json"]) == 0

    assert drain.call_args.kwargs["skipped_overlap"] is False
    assert drain.call_args.kwargs["max_items"] == 10
    assert drain.call_args.args[0] is queue


def test_default_sidecar_sink_is_process_local() -> None:
    sink = default_postmortem_lesson_sink()
    sink.clear()
    try:
        job = PostmortemJob(
            prediction_id="pred-sidecar",
            outcome={
                "label": "miss",
                "run_id": "run-sidecar",
                "claims": [{"claim_id": "c1", "direction": "up", "confidence": 0.9}],
                "score": {
                    "claim_results": [
                        {
                            "claim_id": "c1",
                            "claim_type": "direction",
                            "outcome": "miss",
                            "confidence": 0.9,
                        }
                    ]
                },
            },
            priority=10,
        )
        handle_postmortem_job(job, config=_config(), sink=None)
        kinds = [lesson["kind"] for record in sink.records for lesson in record["lessons"]]
        assert "overconfidence" in kinds
    finally:
        sink.clear()
