# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Batch-oriented prediction resolver with leases, coalesce, and backpressure.

Tick shape (Issue #1104):

```text
due_batch = claim_due(limit=K)          # exclusive leases
group by (symbol, market, as_of_date)
fetch_actuals_once_per_group            # fetch pool concurrency cap
score_all_predictions_in_group          # complete only if lease still held
enqueue_postmortem(misses_only)         # separate smaller pool + per-tick cap
```

Hard invariant: under concurrent workers, a prediction is scored at most once
(``complete_resolved`` is the single-writer fence; stale lease holders are rejected).
Provider failure never fabricates hit/miss — only ``data_unavailable`` + bounded retry.
"""

from __future__ import annotations

import logging
import random
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from src.services.prediction_resolution.coalesce import CoalesceGroup, group_by_actuals_key
from src.services.prediction_resolution.config import (
    PredictionResolveConfig,
    load_prediction_resolve_config,
)
from src.services.prediction_resolution.contracts import (
    OUTCOME_DATA_UNAVAILABLE,
    OUTCOME_MISS,
    OUTCOME_PARTIAL,
    ActualsFetcherPort,
    ActualsSnapshot,
    ClaimScoreResult,
    ClaimScorerPort,
    DataUnavailable,
    PostmortemQueuePort,
    PredictionWorkItem,
    PredictionWorkStore,
    ResolveOutcome,
)
from src.services.prediction_resolution.metrics import PredictionResolveMetrics
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass
class TickResult:
    """Summary of one resolve tick for callers and tests."""

    claimed: int = 0
    resolved: int = 0
    retried: int = 0
    errors: int = 0
    fetch_calls: int = 0
    fetch_errors: int = 0
    fetch_coalesced_saved: int = 0
    scored: int = 0
    score_rejected_stale_lease: int = 0
    postmortem_enqueued: int = 0
    postmortem_dropped_cap: int = 0
    deferred_by_backpressure: int = 0
    due_before: int = 0
    due_after: int = 0
    circuit_open: bool = False
    groups: int = 0
    worker_id: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claimed": self.claimed,
            "resolved": self.resolved,
            "retried": self.retried,
            "errors": self.errors,
            "fetch_calls": self.fetch_calls,
            "fetch_errors": self.fetch_errors,
            "fetch_coalesced_saved": self.fetch_coalesced_saved,
            "scored": self.scored,
            "score_rejected_stale_lease": self.score_rejected_stale_lease,
            "postmortem_enqueued": self.postmortem_enqueued,
            "postmortem_dropped_cap": self.postmortem_dropped_cap,
            "deferred_by_backpressure": self.deferred_by_backpressure,
            "due_before": self.due_before,
            "due_after": self.due_after,
            "circuit_open": self.circuit_open,
            "groups": self.groups,
            "worker_id": self.worker_id,
            "details": dict(self.details),
        }


class _NullPostmortemQueue:
    def enqueue(self, *, prediction_id: str, score: ClaimScoreResult, priority: int = 0) -> bool:
        return False

    def depth(self) -> int:
        return 0

    def try_run(self, *, handler: Any, max_items: int) -> int:
        return 0


class PredictionBatchResolver:
    """Run one or more resolve ticks against injected store/fetcher/scorer ports."""

    def __init__(
        self,
        *,
        store: PredictionWorkStore,
        fetcher: ActualsFetcherPort,
        scorer: ClaimScorerPort,
        postmortem_queue: Optional[PostmortemQueuePort] = None,
        config: Optional[PredictionResolveConfig] = None,
        metrics: Optional[PredictionResolveMetrics] = None,
        now_provider: Optional[Callable[[], datetime]] = None,
        worker_id: Optional[str] = None,
        rng: Optional[random.Random] = None,
    ) -> None:
        self.store = store
        self.fetcher = fetcher
        self.scorer = scorer
        self.postmortem_queue: PostmortemQueuePort = postmortem_queue or _NullPostmortemQueue()
        self.config = config or load_prediction_resolve_config()
        self.metrics = metrics or PredictionResolveMetrics()
        self.now_provider = now_provider or _utc_now
        self.worker_id = str(worker_id or f"resolver-{uuid.uuid4().hex[:10]}")
        self._rng = rng or random.Random()
        self._circuit_lock = threading.Lock()
        self._provider_errors_in_window = 0
        self._circuit_open_until: Optional[datetime] = None
        self._postmortem_lock = threading.Lock()
        self._postmortem_budget_remaining = 0

    def _circuit_is_open(self, now: datetime) -> bool:
        with self._circuit_lock:
            if self._circuit_open_until is None:
                return False
            if now >= self._circuit_open_until:
                self._circuit_open_until = None
                self._provider_errors_in_window = 0
                return False
            return True

    def _note_provider_error(self, now: datetime) -> None:
        cfg = self.config
        with self._circuit_lock:
            self._provider_errors_in_window += 1
            if self._provider_errors_in_window >= cfg.provider_error_circuit_threshold:
                self._circuit_open_until = now + timedelta(
                    seconds=cfg.provider_error_circuit_cooldown_seconds
                )
                logger.warning(
                    "[PredictionBatchResolver] provider error circuit open until %s",
                    self._circuit_open_until.isoformat(),
                )

    def _note_provider_success(self) -> None:
        with self._circuit_lock:
            if self._provider_errors_in_window > 0:
                self._provider_errors_in_window -= 1

    def retry_delay_seconds(self, attempt_count: int) -> float:
        """Exponential backoff with optional jitter, capped by config."""
        cfg = self.config
        exp = max(0, int(attempt_count) - 1)
        base = min(cfg.retry_max_seconds, cfg.retry_base_seconds * (2**exp))
        if cfg.retry_jitter_ratio <= 0:
            return base
        jitter = base * cfg.retry_jitter_ratio * self._rng.random()
        return min(cfg.retry_max_seconds, base + jitter)

    def run_tick(self) -> TickResult:
        """Execute one claim → coalesce → fetch → score cycle."""
        now = self.now_provider()
        cfg = self.config
        result = TickResult(worker_id=self.worker_id)

        due_before = self.store.count_due(now=now)
        result.due_before = due_before
        oldest = self.store.oldest_due_at(now=now)
        due_lag = None
        if oldest is not None:
            due_lag = max(0.0, (now - oldest).total_seconds())

        circuit_open = self._circuit_is_open(now)
        result.circuit_open = circuit_open
        claim_limit = cfg.effective_claim_limit(circuit_open=circuit_open)
        deferred = max(0, due_before - claim_limit) if claim_limit >= 0 else due_before
        result.deferred_by_backpressure = deferred

        depths = dict(self.store.queue_depths())
        self.metrics.record_tick_start(
            now=now,
            due_count=due_before,
            due_lag_seconds=due_lag,
            queue_depths=depths,
            postmortem_depth=self.postmortem_queue.depth(),
            circuit_open=circuit_open,
            deferred=deferred,
        )

        if claim_limit <= 0:
            result.due_after = due_before
            result.details["skipped"] = "claim_limit_zero"
            return result

        claimed = self.store.claim_due(
            now=now,
            limit=claim_limit,
            worker_id=self.worker_id,
            lease_seconds=cfg.lease_seconds,
        )
        result.claimed = len(claimed)
        self.metrics.add_claimed(len(claimed))
        if not claimed:
            result.due_after = self.store.count_due(now=self.now_provider())
            return result

        groups = group_by_actuals_key(claimed)
        result.groups = len(groups)
        coalesced_saved = sum(max(0, g.size - 1) for g in groups)
        result.fetch_coalesced_saved = coalesced_saved
        self.metrics.add_coalesced_saved(coalesced_saved)

        self._postmortem_budget_remaining = cfg.postmortem_max_per_tick

        fetch_workers = max(1, min(cfg.fetch_concurrency, len(groups)))
        with ThreadPoolExecutor(
            max_workers=fetch_workers,
            thread_name_prefix="pred-resolve-fetch",
        ) as pool:
            futures = {
                pool.submit(self._process_group, group, now): group for group in groups
            }
            for future in as_completed(futures):
                group = futures[future]
                try:
                    group_stats = future.result()
                except Exception as exc:  # broad-exception: fallback_recorded - isolate group
                    log_safe_exception(
                        logger,
                        "Prediction resolve group failed",
                        exc,
                        error_code="prediction_resolve_group_failed",
                        level=logging.WARNING,
                        context={"coalesce_key": list(group.key)},
                    )
                    for item in group.items:
                        self._handle_unexpected_item_failure(item, now, str(exc))
                        result.errors += 1
                    continue
                result.fetch_calls += int(group_stats.get("fetch_calls", 0))
                result.fetch_errors += int(group_stats.get("fetch_errors", 0))
                result.resolved += int(group_stats.get("resolved", 0))
                result.retried += int(group_stats.get("retried", 0))
                result.errors += int(group_stats.get("errors", 0))
                result.scored += int(group_stats.get("scored", 0))
                result.score_rejected_stale_lease += int(
                    group_stats.get("score_rejected_stale_lease", 0)
                )
                result.postmortem_enqueued += int(group_stats.get("postmortem_enqueued", 0))
                result.postmortem_dropped_cap += int(
                    group_stats.get("postmortem_dropped_cap", 0)
                )

        result.due_after = self.store.count_due(now=self.now_provider())
        return result

    def _process_group(
        self,
        group: CoalesceGroup,
        claimed_at: datetime,
    ) -> Dict[str, int]:
        stats = {
            "fetch_calls": 0,
            "fetch_errors": 0,
            "resolved": 0,
            "retried": 0,
            "errors": 0,
            "scored": 0,
            "score_rejected_stale_lease": 0,
            "postmortem_enqueued": 0,
            "postmortem_dropped_cap": 0,
        }
        stats["fetch_calls"] = 1
        self.metrics.add_fetch_call()
        try:
            actuals = self.fetcher.fetch(
                symbol=group.symbol,
                market=group.market,
                as_of_date=group.as_of_date,
            )
        except Exception as exc:  # broad-exception: fallback_recorded - never fabricate actuals
            log_safe_exception(
                logger,
                "ActualsFetcher raised; treating as data_unavailable",
                exc,
                error_code="prediction_resolve_fetch_raised",
                level=logging.WARNING,
                context={"symbol": group.symbol, "market": group.market},
            )
            actuals = DataUnavailable(
                error_code="provider_exception",
                message=str(exc) or "provider_exception",
                retryable=True,
            )

        if isinstance(actuals, DataUnavailable):
            stats["fetch_errors"] = 1
            self.metrics.add_fetch_error()
            self._note_provider_error(claimed_at)
            for item in group.items:
                outcome = self._apply_data_unavailable(item, claimed_at, actuals)
                if outcome == "retried":
                    stats["retried"] += 1
                else:
                    stats["errors"] += 1
            return stats

        self._note_provider_success()
        for item in group.items:
            item_stats = self._score_and_complete(item, actuals, claimed_at)
            for key, value in item_stats.items():
                stats[key] = stats.get(key, 0) + value
        return stats

    def _score_and_complete(
        self,
        item: PredictionWorkItem,
        actuals: ActualsSnapshot,
        now: datetime,
    ) -> Dict[str, int]:
        stats = {
            "resolved": 0,
            "retried": 0,
            "errors": 0,
            "scored": 0,
            "score_rejected_stale_lease": 0,
            "postmortem_enqueued": 0,
            "postmortem_dropped_cap": 0,
        }
        try:
            score = self.scorer.score(item.claims, actuals)
        except Exception as exc:  # broad-exception: fallback_recorded - scorer bugs must not double-write
            log_safe_exception(
                logger,
                "ClaimScorer raised",
                exc,
                error_code="prediction_resolve_score_raised",
                level=logging.WARNING,
                context={"prediction_id": item.prediction_id},
            )
            if self.store.mark_error(
                item.prediction_id,
                worker_id=self.worker_id,
                error_code="scorer_exception",
                message=str(exc) or "scorer_exception",
            ):
                stats["errors"] += 1
                self.metrics.add_errors()
            return stats

        if score.aggregate_label == OUTCOME_DATA_UNAVAILABLE:
            unavailable = DataUnavailable(
                error_code="actuals_incomplete",
                message="scorer reported data_unavailable",
                retryable=True,
            )
            outcome = self._apply_data_unavailable(item, now, unavailable)
            if outcome == "retried":
                stats["retried"] += 1
            else:
                stats["errors"] += 1
            return stats

        resolve_outcome = ResolveOutcome(
            prediction_id=item.prediction_id,
            aggregate_label=score.aggregate_label,
            claim_results=tuple(score.claim_results),
            metrics=dict(score.metrics),
            scored_at=now,
            actuals_provider=actuals.provider,
            worker_id=self.worker_id,
        )
        accepted = self.store.complete_resolved(
            item.prediction_id,
            worker_id=self.worker_id,
            outcome=resolve_outcome,
        )
        if not accepted:
            stats["score_rejected_stale_lease"] += 1
            self.metrics.add_score_rejected()
            return stats

        stats["resolved"] += 1
        stats["scored"] += 1
        self.metrics.add_resolved()
        self.metrics.add_scored()

        if score.needs_postmortem or score.aggregate_label in {OUTCOME_MISS, OUTCOME_PARTIAL}:
            self._maybe_enqueue_postmortem(item.prediction_id, score, stats)
        return stats

    def _maybe_enqueue_postmortem(
        self,
        prediction_id: str,
        score: ClaimScoreResult,
        stats: Dict[str, int],
    ) -> None:
        with self._postmortem_lock:
            if self._postmortem_budget_remaining <= 0:
                stats["postmortem_dropped_cap"] += 1
                self.metrics.add_postmortem_dropped()
                return
            self._postmortem_budget_remaining -= 1
        priority = 10 if score.aggregate_label == OUTCOME_MISS else 5
        try:
            ok = self.postmortem_queue.enqueue(
                prediction_id=prediction_id,
                score=score,
                priority=priority,
            )
        except Exception as exc:  # broad-exception: fallback_recorded - postmortem is best-effort
            log_safe_exception(
                logger,
                "Postmortem enqueue failed",
                exc,
                error_code="prediction_resolve_postmortem_enqueue_failed",
                level=logging.WARNING,
                context={"prediction_id": prediction_id},
            )
            ok = False
        if ok:
            stats["postmortem_enqueued"] += 1
            self.metrics.add_postmortem_enqueued()
        else:
            stats["postmortem_dropped_cap"] += 1
            self.metrics.add_postmortem_dropped()

    def _apply_data_unavailable(
        self,
        item: PredictionWorkItem,
        now: datetime,
        unavailable: DataUnavailable,
    ) -> str:
        """Return 'retried' or 'error'."""
        cfg = self.config
        attempt = max(1, int(item.attempt_count))
        if not unavailable.retryable or attempt >= cfg.max_attempts:
            if self.store.mark_error(
                item.prediction_id,
                worker_id=self.worker_id,
                error_code=unavailable.error_code or "data_unavailable",
                message=unavailable.message or "data_unavailable retries exhausted",
            ):
                self.metrics.add_errors()
            return "error"

        delay = self.retry_delay_seconds(attempt)
        next_at = now + timedelta(seconds=delay)
        if self.store.release_for_retry(
            item.prediction_id,
            worker_id=self.worker_id,
            error_code=unavailable.error_code or "data_unavailable",
            next_attempt_at=next_at,
            attempt_count=attempt,
        ):
            self.metrics.add_retried()
            return "retried"
        return "error"

    def _handle_unexpected_item_failure(
        self,
        item: PredictionWorkItem,
        now: datetime,
        message: str,
    ) -> None:
        unavailable = DataUnavailable(
            error_code="group_failure",
            message=message,
            retryable=True,
        )
        self._apply_data_unavailable(item, now, unavailable)

    def run_until_idle(
        self,
        *,
        max_ticks: int = 1000,
    ) -> List[TickResult]:
        """Drain due work across multiple ticks (large backlog / multi-tick tests)."""
        results: List[TickResult] = []
        for _ in range(max(1, int(max_ticks))):
            tick = self.run_tick()
            results.append(tick)
            if tick.claimed == 0 and tick.due_after == 0:
                break
            if tick.claimed == 0:
                break
        return results
