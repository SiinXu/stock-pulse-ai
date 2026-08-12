# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Batch prediction resolution: leases, coalesce, backpressure, no double-score."""

from __future__ import annotations

import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from src.services.prediction_resolution import (
    ActualsSnapshot,
    ClaimScoreResult,
    DataUnavailable,
    InMemoryPredictionWorkStore,
    PredictionBatchResolver,
    PredictionResolveConfig,
    PredictionWorkItem,
    coalesce_key,
    group_by_actuals_key,
    load_prediction_resolve_config,
)
from src.services.prediction_resolution.contracts import (
    STATUS_DATA_UNAVAILABLE_RETRY,
    STATUS_ERROR,
    STATUS_PENDING,
    STATUS_RESOLVED,
    ResolveOutcome,
)
from src.services.prediction_resolution.postmortem_queue import InMemoryPostmortemQueue


NOW = datetime(2026, 8, 12, 12, 0, 0)
AS_OF = date(2026, 8, 11)


def _item(
    prediction_id: str,
    *,
    symbol: str = "600519",
    market: str = "cn",
    as_of: date = AS_OF,
    resolve_after: Optional[datetime] = None,
    status: str = STATUS_PENDING,
    claims: Optional[Tuple[Mapping[str, Any], ...]] = None,
    attempt_count: int = 0,
) -> PredictionWorkItem:
    return PredictionWorkItem(
        prediction_id=prediction_id,
        symbol=symbol,
        market=market,
        as_of_date=as_of,
        resolve_after=resolve_after or (NOW - timedelta(minutes=5)),
        claims=claims
        or (
            {
                "type": "direction",
                "payload": {"direction": "up"},
                "confidence": 0.7,
            },
        ),
        status=status,
        attempt_count=attempt_count,
        created_at=NOW - timedelta(days=1),
    )


@dataclass
class RecordingFetcher:
    responses: Dict[Tuple[str, str, str], Any] = field(default_factory=dict)
    default: Any = field(
        default_factory=lambda: ActualsSnapshot(
            symbol="600519",
            market="cn",
            as_of_date=AS_OF,
            fields={"close": 1800.0, "open": 1780.0},
            provider="fixture",
            fetched_at=NOW,
        )
    )
    calls: List[Tuple[str, str, date]] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)
    delay_seconds: float = 0.0

    def fetch(
        self,
        *,
        symbol: str,
        market: str,
        as_of_date: date,
    ) -> ActualsSnapshot | DataUnavailable:
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        with self.lock:
            self.calls.append((symbol, market, as_of_date))
            key = (symbol.upper(), market.lower(), as_of_date.isoformat())
            if key in self.responses:
                return self.responses[key]
            if isinstance(self.default, ActualsSnapshot):
                return ActualsSnapshot(
                    symbol=symbol,
                    market=market,
                    as_of_date=as_of_date,
                    fields=dict(self.default.fields),
                    provider=self.default.provider,
                    fetched_at=NOW,
                )
            return self.default


@dataclass
class ScoreByPredictionId:
    calls: List[str] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)
    labels: Dict[str, str] = field(default_factory=dict)
    default_label: str = "hit"

    def score(
        self,
        claims: Sequence[Mapping[str, Any]],
        actuals: ActualsSnapshot,
    ) -> ClaimScoreResult:
        pid = ""
        for claim in claims:
            pid = str(claim.get("prediction_id") or pid)
        with self.lock:
            self.calls.append(pid)
        label = self.labels.get(pid, self.default_label)
        return ClaimScoreResult(
            aggregate_label=label,
            claim_results=({"prediction_id": pid, "label": label},),
            metrics={},
            needs_postmortem=label == "miss",
        )


def _cfg(**overrides: Any) -> PredictionResolveConfig:
    base = PredictionResolveConfig(
        enabled=True,
        max_per_tick=50,
        fetch_concurrency=4,
        postmortem_concurrency=1,
        postmortem_max_per_tick=10,
        lease_seconds=60,
        max_attempts=5,
        retry_base_seconds=30.0,
        retry_max_seconds=3600.0,
        retry_jitter_ratio=0.0,
        provider_error_circuit_threshold=100,
        provider_error_circuit_cooldown_seconds=60.0,
        circuit_open_max_per_tick=5,
    )
    return PredictionResolveConfig(**{**base.__dict__, **overrides})


def _seed_many(
    store: InMemoryPredictionWorkStore,
    n: int,
    *,
    symbols: Optional[List[str]] = None,
) -> None:
    items = []
    for i in range(n):
        if symbols:
            symbol = symbols[i % len(symbols)]
        else:
            symbol = f"{600000 + (i % 20)}"
        pid = f"p-{i:04d}"
        items.append(
            _item(
                pid,
                symbol=symbol,
                claims=(
                    {
                        "type": "direction",
                        "payload": {"direction": "up"},
                        "prediction_id": pid,
                    },
                ),
            )
        )
    store.seed(items)


def test_coalesce_key_normalizes_symbol_market() -> None:
    assert coalesce_key(symbol="aapl", market="US", as_of_date=AS_OF) == (
        "AAPL",
        "us",
        "2026-08-11",
    )


def test_group_by_actuals_key_merges_same_symbol_as_of() -> None:
    items = [
        _item("a", symbol="600519"),
        _item("b", symbol="600519"),
        _item("c", symbol="000001"),
    ]
    groups = group_by_actuals_key(items)
    assert len(groups) == 2
    by_symbol = {g.symbol: g.size for g in groups}
    assert by_symbol["600519"] == 2
    assert by_symbol["000001"] == 1


def test_claim_due_exclusive_under_concurrency() -> None:
    store = InMemoryPredictionWorkStore()
    _seed_many(store, 40)
    worker_claims: Dict[str, List[str]] = {}
    lock = threading.Lock()

    def worker(wid: str) -> int:
        claimed = store.claim_due(
            now=NOW,
            limit=25,
            worker_id=wid,
            lease_seconds=120,
        )
        ids = [c.prediction_id for c in claimed]
        with lock:
            worker_claims[wid] = ids
        return len(ids)

    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = [pool.submit(worker, f"w{i}") for i in range(8)]
        total = sum(f.result() for f in as_completed(futs))

    all_ids = [pid for ids in worker_claims.values() for pid in ids]
    assert len(all_ids) == len(set(all_ids)), "duplicate claim across workers"
    assert total == len(set(all_ids))
    assert total == 40


def test_complete_resolved_rejects_second_score() -> None:
    store = InMemoryPredictionWorkStore()
    store.seed([_item("p1")])
    claimed = store.claim_due(now=NOW, limit=1, worker_id="w1", lease_seconds=60)
    assert len(claimed) == 1

    outcome = ResolveOutcome(
        prediction_id="p1",
        aggregate_label="hit",
        claim_results=(),
        metrics={},
        scored_at=NOW,
        actuals_provider="fixture",
        worker_id="w1",
    )
    assert store.complete_resolved("p1", worker_id="w1", outcome=outcome) is True
    assert store.complete_resolved("p1", worker_id="w1", outcome=outcome) is False
    assert store.complete_resolved("p1", worker_id="w2", outcome=outcome) is False
    row = store.get("p1")
    assert row is not None
    assert row.status == STATUS_RESOLVED
    assert row.score_count == 1


def test_concurrent_workers_never_double_score_same_prediction() -> None:
    """Hard requirement: concurrency must not score one prediction twice."""
    store = InMemoryPredictionWorkStore()
    n = 100
    _seed_many(store, n, symbols=["AAA", "BBB", "CCC", "DDD", "EEE"])
    scorer = ScoreByPredictionId(default_label="hit")
    fetcher = RecordingFetcher(delay_seconds=0.01)

    def run_worker(wid: str) -> int:
        resolver = PredictionBatchResolver(
            store=store,
            fetcher=fetcher,
            scorer=scorer,
            config=_cfg(max_per_tick=40, fetch_concurrency=4, lease_seconds=30),
            worker_id=wid,
            now_provider=lambda: NOW,
            rng=random.Random(0),
        )
        resolved = 0
        for _ in range(10):
            tick = resolver.run_tick()
            resolved += tick.resolved
            if tick.claimed == 0:
                break
        return resolved

    with ThreadPoolExecutor(max_workers=6) as pool:
        futs = [pool.submit(run_worker, f"worker-{i}") for i in range(6)]
        total_resolved = sum(f.result() for f in as_completed(futs))

    rows = store.list_all()
    resolved_rows = [r for r in rows if r.status == STATUS_RESOLVED]
    assert len(resolved_rows) == n
    assert total_resolved == n
    assert all(r.score_count == 1 for r in resolved_rows)
    assert len(scorer.calls) == n
    assert len(set(scorer.calls)) == n


def test_coalesced_fetch_same_symbol_as_of() -> None:
    store = InMemoryPredictionWorkStore()
    items = [
        _item(
            f"p{i}",
            symbol="600519",
            claims=({"type": "direction", "prediction_id": f"p{i}"},),
        )
        for i in range(8)
    ]
    items.append(
        _item(
            "other",
            symbol="AAPL",
            market="us",
            claims=({"type": "direction", "prediction_id": "other"},),
        )
    )
    store.seed(items)
    fetcher = RecordingFetcher()
    scorer = ScoreByPredictionId()
    resolver = PredictionBatchResolver(
        store=store,
        fetcher=fetcher,
        scorer=scorer,
        config=_cfg(max_per_tick=50, fetch_concurrency=2),
        worker_id="solo",
        now_provider=lambda: NOW,
        rng=random.Random(0),
    )
    tick = resolver.run_tick()
    assert tick.resolved == 9
    assert tick.fetch_calls == 2
    assert tick.fetch_coalesced_saved == 7
    assert len(fetcher.calls) == 2


def test_backpressure_max_per_tick_defers_excess() -> None:
    store = InMemoryPredictionWorkStore()
    _seed_many(store, 100)
    fetcher = RecordingFetcher()
    scorer = ScoreByPredictionId()
    resolver = PredictionBatchResolver(
        store=store,
        fetcher=fetcher,
        scorer=scorer,
        config=_cfg(max_per_tick=10, fetch_concurrency=2),
        worker_id="bp",
        now_provider=lambda: NOW,
        rng=random.Random(0),
    )
    tick = resolver.run_tick()
    assert tick.claimed == 10
    assert tick.resolved == 10
    assert tick.deferred_by_backpressure == 90
    assert tick.due_before == 100
    assert store.count_due(now=NOW) == 90

    resolver.run_until_idle(max_ticks=20)
    assert sum(1 for r in store.list_all() if r.status == STATUS_RESOLVED) == 100
    assert all(r.score_count == 1 for r in store.list_all() if r.status == STATUS_RESOLVED)


def test_hundred_synthetic_due_rows_integration() -> None:
    store = InMemoryPredictionWorkStore()
    symbols = [f"S{i:02d}" for i in range(10)]
    _seed_many(store, 100, symbols=symbols)
    fetcher = RecordingFetcher()
    scorer = ScoreByPredictionId(default_label="miss")
    pm = InMemoryPostmortemQueue()
    resolver = PredictionBatchResolver(
        store=store,
        fetcher=fetcher,
        scorer=scorer,
        postmortem_queue=pm,
        config=_cfg(
            max_per_tick=25,
            fetch_concurrency=4,
            postmortem_max_per_tick=5,
        ),
        worker_id="batch100",
        now_provider=lambda: NOW,
        rng=random.Random(1),
    )
    ticks = resolver.run_until_idle(max_ticks=10)
    assert sum(t.claimed for t in ticks) == 100
    assert sum(t.resolved for t in ticks) == 100
    # Coalesce is per-tick: 10 symbols appear in each of 4 ticks of 25 → 40 fetches.
    # Cross-tick ActualsFetcher cache is Issue #1110; this layer does not invent prices.
    assert len(fetcher.calls) == 40
    assert sum(t.fetch_coalesced_saved for t in ticks) == 60  # 100 scores - 40 fetches
    assert pm.depth() <= 20
    assert sum(t.postmortem_enqueued for t in ticks) == pm.depth()
    assert sum(t.postmortem_dropped_cap for t in ticks) == 100 - pm.depth()
    snap = resolver.metrics.snapshot()
    assert snap.resolved == 100
    assert store.queue_depths().get(STATUS_RESOLVED) == 100


def test_provider_failure_retries_never_fabricates_hit() -> None:
    store = InMemoryPredictionWorkStore()
    store.seed([_item("p-fail", claims=({"type": "direction", "prediction_id": "p-fail"},))])
    fetcher = RecordingFetcher(
        default=DataUnavailable(error_code="provider_down", retryable=True)
    )
    scorer = ScoreByPredictionId()
    clock = {"t": NOW}

    def now() -> datetime:
        return clock["t"]

    resolver = PredictionBatchResolver(
        store=store,
        fetcher=fetcher,
        scorer=scorer,
        config=_cfg(max_attempts=3, retry_base_seconds=10.0, retry_jitter_ratio=0.0),
        worker_id="retry",
        now_provider=now,
        rng=random.Random(0),
    )
    tick = resolver.run_tick()
    assert tick.resolved == 0
    assert tick.retried == 1
    row = store.get("p-fail")
    assert row is not None
    assert row.status == STATUS_DATA_UNAVAILABLE_RETRY
    assert row.outcome_label is None
    assert row.score_count == 0
    assert scorer.calls == []

    tick2 = resolver.run_tick()
    assert tick2.claimed == 0

    clock["t"] = NOW + timedelta(seconds=11)
    resolver.run_tick()

    for _ in range(5):
        current = store.get("p-fail")
        assert current is not None
        if current.status == STATUS_ERROR:
            break
        clock["t"] = clock["t"] + timedelta(seconds=10_000)
        resolver.run_tick()
    row = store.get("p-fail")
    assert row is not None
    assert row.status == STATUS_ERROR
    assert row.score_count == 0
    assert scorer.calls == []


def test_expired_lease_can_be_reclaimed_by_other_worker() -> None:
    store = InMemoryPredictionWorkStore()
    store.seed([_item("p-lease")])
    c1 = store.claim_due(now=NOW, limit=1, worker_id="w1", lease_seconds=30)
    assert c1[0].lease_owner == "w1"
    c2 = store.claim_due(now=NOW + timedelta(seconds=5), limit=1, worker_id="w2", lease_seconds=30)
    assert c2 == []
    c3 = store.claim_due(now=NOW + timedelta(seconds=31), limit=1, worker_id="w2", lease_seconds=30)
    assert len(c3) == 1
    assert c3[0].lease_owner == "w2"

    outcome = ResolveOutcome(
        prediction_id="p-lease",
        aggregate_label="hit",
        claim_results=(),
        metrics={},
        scored_at=NOW + timedelta(seconds=31),
        actuals_provider="fixture",
        worker_id="w2",
    )
    assert store.complete_resolved("p-lease", worker_id="w1", outcome=outcome) is False
    assert store.complete_resolved("p-lease", worker_id="w2", outcome=outcome) is True
    row = store.get("p-lease")
    assert row is not None
    assert row.score_count == 1


def test_postmortem_per_tick_cap_prevents_unbounded_enqueue() -> None:
    store = InMemoryPredictionWorkStore()
    _seed_many(store, 30, symbols=["X"])
    fetcher = RecordingFetcher()
    scorer = ScoreByPredictionId(default_label="miss")
    pm = InMemoryPostmortemQueue()
    resolver = PredictionBatchResolver(
        store=store,
        fetcher=fetcher,
        scorer=scorer,
        postmortem_queue=pm,
        config=_cfg(max_per_tick=30, postmortem_max_per_tick=3),
        worker_id="pm",
        now_provider=lambda: NOW,
        rng=random.Random(0),
    )
    tick = resolver.run_tick()
    assert tick.resolved == 30
    assert tick.postmortem_enqueued == 3
    assert tick.postmortem_dropped_cap == 27
    assert pm.depth() == 3


def test_circuit_breaker_shrinks_claim_limit() -> None:
    store = InMemoryPredictionWorkStore()
    _seed_many(store, 20)
    fetcher = RecordingFetcher(
        default=DataUnavailable(error_code="provider_down", retryable=True)
    )
    scorer = ScoreByPredictionId()
    clock = {"t": NOW}

    resolver = PredictionBatchResolver(
        store=store,
        fetcher=fetcher,
        scorer=scorer,
        config=_cfg(
            max_per_tick=20,
            fetch_concurrency=4,
            provider_error_circuit_threshold=2,
            provider_error_circuit_cooldown_seconds=60.0,
            circuit_open_max_per_tick=3,
            max_attempts=50,
            retry_base_seconds=1.0,
        ),
        worker_id="circuit",
        now_provider=lambda: clock["t"],
        rng=random.Random(0),
    )
    tick1 = resolver.run_tick()
    assert tick1.fetch_errors >= 1
    clock["t"] = NOW + timedelta(seconds=2)
    tick2 = resolver.run_tick()
    assert tick2.circuit_open is True
    assert tick2.claimed <= 3


def test_queue_depth_metrics_observable() -> None:
    store = InMemoryPredictionWorkStore()
    _seed_many(store, 5)
    store.seed([_item("future", resolve_after=NOW + timedelta(days=1))])
    fetcher = RecordingFetcher()
    scorer = ScoreByPredictionId()
    resolver = PredictionBatchResolver(
        store=store,
        fetcher=fetcher,
        scorer=scorer,
        config=_cfg(max_per_tick=2),
        worker_id="metrics",
        now_provider=lambda: NOW,
        rng=random.Random(0),
    )
    tick = resolver.run_tick()
    assert tick.claimed == 2
    snap = resolver.metrics.snapshot()
    assert snap.ticks == 1
    assert snap.last_due_count == 5
    assert snap.deferred_by_backpressure == 3
    assert "last_queue_depths" in snap.to_dict()


def test_load_config_from_env_mapping() -> None:
    cfg = load_prediction_resolve_config(
        {
            "PREDICTION_RESOLVE_ENABLED": "true",
            "PREDICTION_RESOLVE_MAX_PER_TICK": "7",
            "PREDICTION_RESOLVE_FETCH_CONCURRENCY": "2",
            "PREDICTION_RESOLVE_POSTMORTEM_CONCURRENCY": "1",
            "PREDICTION_RESOLVE_LEASE_SECONDS": "90",
        }
    )
    assert cfg.enabled is True
    assert cfg.max_per_tick == 7
    assert cfg.fetch_concurrency == 2
    assert cfg.lease_seconds == 90


def test_not_due_predictions_are_not_claimed() -> None:
    store = InMemoryPredictionWorkStore()
    store.seed(
        [
            _item("early", resolve_after=NOW + timedelta(hours=1)),
            _item("due", resolve_after=NOW - timedelta(seconds=1)),
        ]
    )
    claimed = store.claim_due(now=NOW, limit=10, worker_id="w", lease_seconds=30)
    assert [c.prediction_id for c in claimed] == ["due"]
