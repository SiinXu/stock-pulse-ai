# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""PredictionResolver: claim due → actuals → score → write-back (#1102 / #1116)."""

from __future__ import annotations

import logging
import math
import random
import socket
import threading
import uuid
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from src.services.prediction_resolver.memory_store import new_lease_token
from src.services.prediction_resolver.ports import (
    ActualsFetcherPort,
    ClaimScorerPort,
    EvolutionEventSink,
    PostmortemQueuePort,
    PredictionStorePort,
)
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

PREDICTION_RESOLVER_BACKGROUND_TASK_NAME = "prediction_resolver"
PREDICTION_RESOLVER_DEFAULT_INTERVAL_SECONDS = 60
PREDICTION_RESOLVER_MIN_INTERVAL_SECONDS = 30
PREDICTION_RESOLVER_ENGINE_VERSION = "prediction-resolver-v1"
# Bounded exponential backoff for data_unavailable retries (seconds).
PREDICTION_RESOLVER_RETRY_BASE_SECONDS = 30.0
PREDICTION_RESOLVER_RETRY_MAX_SECONDS = 3600.0
PREDICTION_RESOLVER_BACKLOG_PROBE_LIMIT = 1000

OUTCOME_HIT = "hit"
OUTCOME_MISS = "miss"
OUTCOME_PARTIAL = "partial"
OUTCOME_DATA_UNAVAILABLE = "data_unavailable"

TERMINAL_SCORE_LABELS = frozenset({OUTCOME_HIT, OUTCOME_MISS, OUTCOME_PARTIAL})


def _require_int(name: str, value: Any, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _canonical_worker_id(value: Optional[str]) -> str:
    canonical = (
        f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"
        if value is None
        else str(value).strip()
    )
    if not canonical:
        raise ValueError("worker_id must not be empty")
    if len(canonical) > 128:
        raise ValueError("worker_id must not exceed 128 characters")
    if any(ord(character) < 32 or ord(character) == 127 for character in canonical):
        raise ValueError("worker_id must not contain control characters")
    return canonical


def _utc_naive_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _as_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _to_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _as_utc_naive(value).date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _to_datetime(value: Any) -> Optional[datetime]:
    if value is None or value is False:
        return None
    if isinstance(value, datetime):
        return _as_utc_naive(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return _as_utc_naive(datetime.fromisoformat(text.replace("Z", "+00:00")))
    except ValueError:
        return None


def _mapping(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        if isinstance(payload, Mapping):
            return dict(payload)
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    return {}


def _attr(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def derive_aggregate_label(
    *,
    scored_claims: int,
    hit_count: int,
    partial_count: int,
    miss_count: int,
    data_unavailable_count: int,
) -> str:
    """Map claim counts to a single OutcomeLabel."""
    if scored_claims <= 0:
        return OUTCOME_DATA_UNAVAILABLE
    if partial_count == 0 and miss_count == 0 and hit_count == scored_claims:
        return OUTCOME_HIT
    if partial_count == 0 and hit_count == 0 and miss_count == scored_claims:
        return OUTCOME_MISS
    if (
        data_unavailable_count > 0
        and hit_count == 0
        and miss_count == 0
        and partial_count == 0
    ):
        return OUTCOME_DATA_UNAVAILABLE
    return OUTCOME_PARTIAL


def compute_retry_delay_seconds(
    attempts: int,
    *,
    base_seconds: float = PREDICTION_RESOLVER_RETRY_BASE_SECONDS,
    max_seconds: float = PREDICTION_RESOLVER_RETRY_MAX_SECONDS,
    jitter_ratio: float = 0.0,
    random_value: float = 0.0,
) -> float:
    """Bounded exponential backoff with optional positive jitter."""
    if isinstance(attempts, bool) or not isinstance(attempts, int):
        raise ValueError("attempts must be an integer")
    safe_attempts = max(1, attempts)
    base = float(base_seconds)
    maximum = float(max_seconds)
    if not math.isfinite(base) or base <= 0.0:
        raise ValueError("base_seconds must be finite and positive")
    if not math.isfinite(maximum) or maximum < base:
        raise ValueError("max_seconds must be finite and >= base_seconds")
    ratio = float(jitter_ratio)
    sample = float(random_value)
    if not math.isfinite(ratio) or not 0.0 <= ratio <= 1.0:
        raise ValueError("jitter_ratio must be finite and between 0 and 1")
    if not math.isfinite(sample) or not 0.0 <= sample <= 1.0:
        raise ValueError("random_value must be finite and between 0 and 1")
    # Avoid constructing 2 ** attempts for corrupt/untrusted persisted counters.
    if safe_attempts > 1 + math.ceil(math.log2(maximum / base)):
        return maximum
    delay = min(maximum, base * (2.0 ** (safe_attempts - 1)))
    return min(maximum, delay * (1.0 + ratio * sample))


def build_data_unavailable_outcome(
    *,
    reason: str,
    as_of: datetime,
    attempts: int,
    max_attempts: int,
    worker_id: str,
    extra: Optional[Mapping[str, Any]] = None,
    retry_jitter_ratio: float = 0.0,
    retry_random_value: float = 0.0,
) -> Dict[str, Any]:
    """Build outcome payload including retry scheduling metadata.

    Stores that only persist ``outcome_json`` can still honor backoff by reading
    ``next_attempt_at`` / ``retry_exhausted`` from the payload (memory store does).
    """
    retryable = bool((extra or {}).get("retryable", True))
    exhausted = int(attempts) >= int(max_attempts) or not retryable
    payload: Dict[str, Any] = {
        "label": OUTCOME_DATA_UNAVAILABLE,
        "reason": str(reason or "data_unavailable"),
        "engine_version": PREDICTION_RESOLVER_ENGINE_VERSION,
        "worker_id": worker_id,
        "attempts": int(attempts),
        "max_attempts": int(max_attempts),
        "retry_exhausted": exhausted,
    }
    if extra:
        payload.update(dict(extra))
    # Keep explicit exhausted/reason authority after extra merge.
    payload["retry_exhausted"] = exhausted
    payload["reason"] = str(reason or "data_unavailable")
    if exhausted:
        payload["next_attempt_at"] = None
    else:
        delay = compute_retry_delay_seconds(
            attempts,
            jitter_ratio=retry_jitter_ratio,
            random_value=retry_random_value,
        )
        payload["next_attempt_at"] = (
            as_of + timedelta(seconds=delay)
        ).isoformat()
        payload["retry_delay_seconds"] = delay
    return payload


def _label_from_score_report(report: Any) -> str:
    aggregate = _attr(report, "aggregate")
    if aggregate is None:
        return OUTCOME_DATA_UNAVAILABLE
    return derive_aggregate_label(
        scored_claims=int(_attr(aggregate, "scored_claims", 0) or 0),
        hit_count=int(_attr(aggregate, "hit_count", 0) or 0),
        partial_count=int(_attr(aggregate, "partial_count", 0) or 0),
        miss_count=int(_attr(aggregate, "miss_count", 0) or 0),
        data_unavailable_count=int(_attr(aggregate, "data_unavailable_count", 0) or 0),
    )


def _claim_actuals_from_snapshot(snapshot: Any) -> Dict[str, Any]:
    if snapshot is None:
        return {"unavailable_reason": "missing_snapshot"}
    if bool(_attr(snapshot, "data_unavailable", False)) or not bool(
        _attr(snapshot, "ok", True)
    ):
        reason = _attr(snapshot, "reason") or _attr(snapshot, "status") or "data_unavailable"
        return {"unavailable_reason": str(reason)}

    as_of_bar = _attr(snapshot, "as_of_bar")
    end_bar = _attr(snapshot, "end_bar")
    start_price = _attr(as_of_bar, "close") if as_of_bar is not None else None
    end_price = _attr(end_bar, "close") if end_bar is not None else None
    start_price = _attr(snapshot, "start_price", start_price)
    end_price = _attr(snapshot, "end_price", end_price)
    high_price = _attr(snapshot, "high_price")
    low_price = _attr(snapshot, "low_price")
    # A4 end_bar.high/low cover only the final session. They are not path
    # extrema for the full [as_of, end] window and must not prove a false miss.
    payload: Dict[str, Any] = {
        "start_price": start_price,
        "end_price": end_price,
        "high_price": high_price,
        "low_price": low_price,
    }
    return_pct = _attr(snapshot, "return_pct")
    if return_pct is not None:
        payload["return_pct"] = return_pct
    if start_price is None and end_price is None:
        payload["unavailable_reason"] = "missing_prices"
    return payload


@dataclass(frozen=True)
class TickItemResult:
    prediction_id: str
    disposition: str
    label: Optional[str] = None
    reason: Optional[str] = None
    applied: bool = False


@dataclass(frozen=True)
class _ActualsRequest:
    symbol: str
    market: Optional[str]
    as_of: date
    end: date

    @property
    def key(self) -> Tuple[str, str, str, str]:
        return (
            self.symbol.upper(),
            self.market or "",
            self.as_of.isoformat(),
            self.end.isoformat(),
        )


@dataclass(frozen=True)
class _ClaimedWork:
    record: Any
    lease_token: str
    attempts: int
    request: _ActualsRequest


@dataclass
class TickSummary:
    claimed: int = 0
    resolved: int = 0
    data_unavailable: int = 0
    skipped: int = 0
    errors: int = 0
    due_before: int = 0
    due_after: int = 0
    due_lag_seconds: Optional[float] = None
    backlog_probe_truncated: bool = False
    deferred_by_backpressure: int = 0
    fetch_calls: int = 0
    fetch_errors: int = 0
    fetch_coalesced_saved: int = 0
    groups: int = 0
    circuit_open: bool = False
    postmortem_enqueued: int = 0
    postmortem_dropped: int = 0
    postmortem_queue_depth: int = 0
    skipped_overlap: bool = False
    items: List[TickItemResult] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "claimed": self.claimed,
            "resolved": self.resolved,
            "data_unavailable": self.data_unavailable,
            "skipped": self.skipped,
            "errors": self.errors,
            "due_before": self.due_before,
            "due_after": self.due_after,
            "due_lag_seconds": self.due_lag_seconds,
            "backlog_probe_truncated": self.backlog_probe_truncated,
            "deferred_by_backpressure": self.deferred_by_backpressure,
            "fetch_calls": self.fetch_calls,
            "fetch_errors": self.fetch_errors,
            "fetch_coalesced_saved": self.fetch_coalesced_saved,
            "groups": self.groups,
            "circuit_open": self.circuit_open,
            "resolve_rate": (
                self.resolved / self.claimed if self.claimed else 0.0
            ),
            "postmortem_enqueued": self.postmortem_enqueued,
            "postmortem_dropped": self.postmortem_dropped,
            "postmortem_queue_depth": self.postmortem_queue_depth,
            "skipped_overlap": self.skipped_overlap,
            "items": [asdict(item) for item in self.items],
        }


class PredictionResolver:
    """System-driven horizon resolver with process-local overlap protection."""

    def __init__(
        self,
        *,
        store: PredictionStorePort,
        actuals_fetcher: ActualsFetcherPort,
        claim_scorer: ClaimScorerPort,
        worker_id: Optional[str] = None,
        lease_seconds: int = 120,
        max_per_tick: int = 50,
        max_attempts: int = 5,
        event_sink: Optional[EvolutionEventSink] = None,
        postmortem_queue: Optional[PostmortemQueuePort] = None,
        postmortem_max_per_tick: int = 10,
        fetch_concurrency: int = 4,
        provider_error_circuit_threshold: int = 5,
        provider_error_circuit_cooldown_seconds: int = 60,
        circuit_open_max_per_tick: int = 5,
        retry_jitter_ratio: float = 0.1,
        rng: Optional[random.Random] = None,
        clock: Optional[Callable[[], datetime]] = None,
        score_config: Any = None,
    ) -> None:
        lease_seconds = _require_int(
            "lease_seconds", lease_seconds, minimum=5, maximum=86_400
        )
        max_per_tick = _require_int(
            "max_per_tick", max_per_tick, minimum=0, maximum=10_000
        )
        max_attempts = _require_int(
            "max_attempts", max_attempts, minimum=1, maximum=100
        )
        postmortem_max_per_tick = _require_int(
            "postmortem_max_per_tick",
            postmortem_max_per_tick,
            minimum=0,
            maximum=10_000,
        )
        fetch_concurrency = _require_int(
            "fetch_concurrency", fetch_concurrency, minimum=1, maximum=64
        )
        provider_error_circuit_threshold = _require_int(
            "provider_error_circuit_threshold",
            provider_error_circuit_threshold,
            minimum=1,
            maximum=10_000,
        )
        provider_error_circuit_cooldown_seconds = _require_int(
            "provider_error_circuit_cooldown_seconds",
            provider_error_circuit_cooldown_seconds,
            minimum=1,
            maximum=86_400,
        )
        circuit_open_max_per_tick = _require_int(
            "circuit_open_max_per_tick",
            circuit_open_max_per_tick,
            minimum=0,
            maximum=10_000,
        )
        retry_jitter_ratio = float(retry_jitter_ratio)
        if not math.isfinite(retry_jitter_ratio) or not 0.0 <= retry_jitter_ratio <= 1.0:
            raise ValueError("retry_jitter_ratio must be finite and between 0 and 1")
        self._store = store
        self._actuals = actuals_fetcher
        self._scorer = claim_scorer
        self._worker_id = _canonical_worker_id(worker_id)
        self._lease_seconds = int(lease_seconds)
        self._max_per_tick = int(max_per_tick)
        self._max_attempts = int(max_attempts)
        self._event_sink = event_sink
        self._postmortem_queue = postmortem_queue
        self._postmortem_max_per_tick = int(postmortem_max_per_tick)
        self._fetch_concurrency = int(fetch_concurrency)
        self._provider_error_circuit_threshold = int(
            provider_error_circuit_threshold
        )
        self._provider_error_circuit_cooldown_seconds = int(
            provider_error_circuit_cooldown_seconds
        )
        self._circuit_open_max_per_tick = int(circuit_open_max_per_tick)
        self._retry_jitter_ratio = retry_jitter_ratio
        self._rng = rng or random.Random()
        self._circuit_open_until: Optional[datetime] = None
        self._postmortem_budget_remaining = 0
        self._postmortem_enqueued = 0
        self._postmortem_dropped = 0
        self._clock = clock or _utc_naive_now
        self._score_config = score_config
        self._tick_lock = threading.Lock()

    @property
    def worker_id(self) -> str:
        return self._worker_id

    def tick(
        self,
        *,
        now: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> TickSummary:
        summary = TickSummary()
        if not self._tick_lock.acquire(blocking=False):
            summary.skipped_overlap = True
            logger.info(
                "[PredictionResolver] skip tick: previous still running worker=%s",
                self._worker_id,
            )
            return summary
        try:
            as_of = _as_utc_naive(now if now is not None else self._clock())
            requested_limit = (
                self._max_per_tick
                if limit is None
                else _require_int("limit", limit, minimum=0, maximum=10_000)
            )
            claim_limit = min(self._max_per_tick, requested_limit)
            circuit_was_open = self._circuit_is_open(as_of)
            summary.circuit_open = circuit_was_open
            if circuit_was_open:
                claim_limit = min(claim_limit, self._circuit_open_max_per_tick)
            self._requeue_ready_retries(as_of=as_of, limit=claim_limit)

            probe_limit = min(
                10_000,
                max(PREDICTION_RESOLVER_BACKLOG_PROBE_LIMIT, claim_limit + 1),
            )
            observed_due = self._list_claimable(as_of=as_of, limit=probe_limit)
            summary.due_before = len(observed_due)
            summary.backlog_probe_truncated = len(observed_due) >= probe_limit
            if observed_due:
                oldest_due_at = _to_datetime(_attr(observed_due[0], "resolve_after"))
                if oldest_due_at is not None:
                    summary.due_lag_seconds = max(
                        0.0,
                        (as_of - oldest_due_at).total_seconds(),
                    )
            summary.deferred_by_backpressure = max(
                0,
                len(observed_due) - claim_limit,
            )
            if claim_limit == 0:
                summary.due_after = summary.due_before
                summary.postmortem_queue_depth = self._postmortem_depth()
                self._emit("prediction.resolve.tick", summary.as_dict())
                return summary

            self._postmortem_budget_remaining = self._postmortem_max_per_tick
            self._postmortem_enqueued = 0
            self._postmortem_dropped = 0
            claimed_work: List[_ClaimedWork] = []
            for candidate in observed_due[:claim_limit]:
                prediction_id = str(_attr(candidate, "prediction_id") or "").strip()
                if not prediction_id:
                    summary.skipped += 1
                    continue
                work, item = self._claim_one(candidate, as_of=as_of)
                if item is not None:
                    summary.items.append(item)
                if work is not None:
                    summary.claimed += 1
                    claimed_work.append(work)
                    continue
                if item is None:
                    summary.errors += 1
                    continue
                if item.disposition == "claimed_failed":
                    summary.skipped += 1
                    continue
                if item.disposition == "error" and item.reason == "claim_failed":
                    summary.errors += 1
                    continue
                summary.claimed += 1
                if item.disposition == "resolved":
                    summary.resolved += 1
                elif item.disposition == "data_unavailable":
                    summary.data_unavailable += 1
                elif item.disposition == "error":
                    summary.errors += 1
                else:
                    summary.skipped += 1

            self._process_claimed_groups(
                claimed_work,
                as_of=as_of,
                summary=summary,
            )
            summary.postmortem_enqueued = self._postmortem_enqueued
            summary.postmortem_dropped = self._postmortem_dropped
            summary.postmortem_queue_depth = self._postmortem_depth()
            summary.circuit_open = self._circuit_is_open(as_of)
            summary.due_after = len(
                self._list_claimable(as_of=as_of, limit=probe_limit)
            )
            self._emit("prediction.resolve.tick", summary.as_dict())
            if summary.claimed or summary.due_before:
                logger.info(
                    "[PredictionResolver] tick complete worker=%s claimed=%s "
                    "resolved=%s data_unavailable=%s skipped=%s errors=%s "
                    "fetch_calls=%s fetch_errors=%s deferred=%s circuit_open=%s",
                    self._worker_id,
                    summary.claimed,
                    summary.resolved,
                    summary.data_unavailable,
                    summary.skipped,
                    summary.errors,
                    summary.fetch_calls,
                    summary.fetch_errors,
                    summary.deferred_by_backpressure,
                    summary.circuit_open,
                )
            return summary
        finally:
            self._tick_lock.release()

    def _circuit_is_open(self, as_of: datetime) -> bool:
        if self._circuit_open_until is None:
            return False
        if as_of >= self._circuit_open_until:
            self._circuit_open_until = None
            return False
        return True

    def _open_circuit(self, as_of: datetime) -> None:
        self._circuit_open_until = as_of + timedelta(
            seconds=self._provider_error_circuit_cooldown_seconds
        )
        logger.warning(
            "[PredictionResolver] provider circuit open worker=%s until=%s",
            self._worker_id,
            self._circuit_open_until.isoformat(),
        )

    def _postmortem_depth(self) -> int:
        if self._postmortem_queue is None:
            return 0
        try:
            return max(0, int(self._postmortem_queue.depth()))
        except Exception as exc:  # broad-exception: fallback_recorded - metrics only
            log_safe_exception(
                logger,
                "Prediction postmortem queue depth failed",
                exc,
                error_code="prediction_resolver_postmortem_depth_failed",
                level=logging.WARNING,
            )
            return 0

    def _requeue_ready_retries(self, *, as_of: datetime, limit: int) -> None:
        """Move durable A3 data-unavailable rows back to pending after backoff."""
        if limit <= 0:
            return
        retry_rows = self._store.list_due(
            as_of=as_of,
            limit=limit,
            statuses=(OUTCOME_DATA_UNAVAILABLE,),
        )
        for row in retry_rows:
            outcome = _mapping(_attr(row, "outcome"))
            if bool(outcome.get("retry_exhausted", False)):
                continue
            if outcome.get("retryable") is False:
                continue
            next_attempt_at = _to_datetime(outcome.get("next_attempt_at"))
            if next_attempt_at is None or next_attempt_at > as_of:
                continue
            prediction_id = str(_attr(row, "prediction_id") or "").strip()
            if not prediction_id:
                continue
            self._store.requeue_pending(
                prediction_id=prediction_id,
                as_of=as_of,
            )

    def _list_claimable(self, *, as_of: datetime, limit: int) -> List[Any]:
        """Combine pending rows with only genuinely expired A3 leases."""
        pending = list(
            self._store.list_due(
                as_of=as_of,
                limit=limit,
                statuses=("pending",),
            )
        )
        # A3's generic status scan does not itself filter resolving lease age.
        # Inspect a bounded recovery window without allowing active leases to
        # crowd pending work out of the per-tick cap.
        resolving = self._store.list_due(
            as_of=as_of,
            limit=1000,
            statuses=("resolving",),
        )
        expired = [
            row
            for row in resolving
            if (
                _to_datetime(_attr(row, "lease_expires_at")) is None
                or _to_datetime(_attr(row, "lease_expires_at")) <= as_of
            )
        ]
        combined = pending + expired
        combined.sort(
            key=lambda row: (
                _to_datetime(_attr(row, "resolve_after")) or datetime.max,
                str(_attr(row, "prediction_id") or ""),
            )
        )
        return combined[:limit]

    def _claim_one(
        self,
        candidate: Any,
        *,
        as_of: datetime,
    ) -> Tuple[Optional[_ClaimedWork], Optional[TickItemResult]]:
        prediction_id = str(_attr(candidate, "prediction_id") or "").strip()
        lease_token = new_lease_token()
        try:
            claimed = self._store.claim_for_resolve(
                prediction_id=prediction_id,
                lease_owner=self._worker_id,
                lease_token=lease_token,
                lease_ttl_seconds=self._lease_seconds,
                as_of=as_of,
            )
        except Exception as exc:  # broad-exception: fallback_recorded - isolate one row
            log_safe_exception(
                logger,
                "Prediction claim failed",
                exc,
                error_code="prediction_resolver_claim_failed",
                context={"prediction_id": prediction_id},
                level=logging.WARNING,
            )
            return None, TickItemResult(
                prediction_id=prediction_id, disposition="error", reason="claim_failed"
            )
        if claimed is None:
            return None, TickItemResult(
                prediction_id=prediction_id,
                disposition="claimed_failed",
                reason="lease_lost",
            )
        attempts = int(_attr(claimed, "attempts", 0) or 0)
        if attempts > self._max_attempts:
            # Claim already incremented attempts; stop retrying without scoring.
            applied = self._mark_unavailable(
                prediction_id=prediction_id,
                reason="max_attempts_exhausted",
                lease_token=lease_token,
                as_of=as_of,
                attempts=attempts,
            )
            return None, self._data_unavailable_result(
                prediction_id=prediction_id,
                reason="max_attempts_exhausted",
                applied=applied,
            )
        request = self._actuals_request(claimed, as_of=as_of)
        if request is None:
            applied = self._mark_unavailable(
                prediction_id=prediction_id,
                reason="invalid_prediction_fields",
                lease_token=lease_token,
                as_of=as_of,
                attempts=attempts,
            )
            return None, self._data_unavailable_result(
                prediction_id=prediction_id,
                reason="invalid_prediction_fields",
                applied=applied,
            )
        return (
            _ClaimedWork(
                record=claimed,
                lease_token=lease_token,
                attempts=attempts,
                request=request,
            ),
            None,
        )

    @staticmethod
    def _actuals_request(claimed: Any, *, as_of: datetime) -> Optional[_ActualsRequest]:
        symbol = str(_attr(claimed, "symbol") or "").strip()
        market = str(_attr(claimed, "market") or "").strip().lower() or None
        as_of_date = _to_date(_attr(claimed, "as_of"))
        end_date = _to_date(_attr(claimed, "resolve_after")) or _to_date(as_of)
        if not symbol or as_of_date is None or end_date is None:
            return None
        return _ActualsRequest(
            symbol=symbol,
            market=market,
            as_of=as_of_date,
            end=end_date,
        )

    def _process_claimed_groups(
        self,
        work_items: List[_ClaimedWork],
        *,
        as_of: datetime,
        summary: TickSummary,
    ) -> None:
        groups: "OrderedDict[Tuple[str, str, str, str], List[_ClaimedWork]]" = (
            OrderedDict()
        )
        for work in work_items:
            groups.setdefault(work.request.key, []).append(work)
        summary.groups = len(groups)
        summary.fetch_coalesced_saved = sum(
            max(0, len(group) - 1) for group in groups.values()
        )
        if not groups:
            return

        fetch_workers = min(self._fetch_concurrency, len(groups))
        futures: Dict[Future[Any], Tuple[str, str, str, str]] = {}
        snapshots: Dict[Tuple[str, str, str, str], Any] = {}
        fetch_exceptions: Dict[Tuple[str, str, str, str], Exception] = {}
        with ThreadPoolExecutor(
            max_workers=fetch_workers,
            thread_name_prefix="prediction-actuals",
        ) as pool:
            for group in groups.values():
                request = group[0].request
                future = pool.submit(
                    self._actuals.fetch,
                    symbol=request.symbol,
                    as_of=request.as_of,
                    market=request.market,
                    end=request.end,
                )
                futures[future] = request.key

            for future in as_completed(futures):
                key = futures[future]
                summary.fetch_calls += 1
                try:
                    snapshots[key] = future.result()
                except Exception as exc:  # broad-exception: fallback_recorded - never invent actuals
                    summary.fetch_errors += 1
                    fetch_exceptions[key] = exc
                    log_safe_exception(
                        logger,
                        "ActualsFetcher raised; marking group data_unavailable",
                        exc,
                        error_code="prediction_resolver_fetch_failed",
                        context={"coalesce_key": list(key)},
                        level=logging.WARNING,
                    )

        provider_error_counts: Dict[str, int] = {}
        for key, group in groups.items():
            if key in fetch_exceptions:
                provider_error_counts["unknown"] = (
                    provider_error_counts.get("unknown", 0) + 1
                )
                for work in group:
                    item = self._mark_group_fetch_exception(work, as_of=as_of)
                    self._record_item(summary, item)
                continue

            snapshot = snapshots[key]
            snapshot_failed = not bool(_attr(snapshot, "ok", False)) or bool(
                _attr(snapshot, "data_unavailable", False)
            )
            if snapshot_failed:
                summary.fetch_errors += 1
                if bool(_attr(snapshot, "retryable", True)):
                    provider = str(_attr(snapshot, "provider") or "unknown")
                    provider_error_counts[provider] = (
                        provider_error_counts.get(provider, 0) + 1
                    )
            for work in group:
                try:
                    item = self._score_snapshot_and_write(
                        work,
                        snapshot=snapshot,
                        as_of=as_of,
                    )
                except Exception as exc:  # broad-exception: fallback_recorded - isolate one row
                    log_safe_exception(
                        logger,
                        "Prediction resolve path failed; marking data_unavailable",
                        exc,
                        error_code="prediction_resolver_path_failed",
                        context={
                            "prediction_id": str(
                                _attr(work.record, "prediction_id") or ""
                            )
                        },
                        level=logging.WARNING,
                    )
                    item = self._handle_resolve_exception(
                        work,
                        as_of=as_of,
                    )
                self._record_item(summary, item)

        if any(
            count >= self._provider_error_circuit_threshold
            for count in provider_error_counts.values()
        ):
            self._open_circuit(as_of)

    @staticmethod
    def _record_item(summary: TickSummary, item: TickItemResult) -> None:
        summary.items.append(item)
        if item.disposition == "resolved":
            summary.resolved += 1
        elif item.disposition == "data_unavailable":
            summary.data_unavailable += 1
        elif item.disposition == "error":
            summary.errors += 1
        else:
            summary.skipped += 1

    def _mark_group_fetch_exception(
        self,
        work: _ClaimedWork,
        *,
        as_of: datetime,
    ) -> TickItemResult:
        prediction_id = str(_attr(work.record, "prediction_id"))
        try:
            applied = self._mark_unavailable(
                prediction_id=prediction_id,
                reason="provider_exception",
                lease_token=work.lease_token,
                as_of=as_of,
                attempts=work.attempts,
                extra={"retryable": True},
            )
        except Exception as exc:  # broad-exception: fallback_recorded - preserve lease for recovery
            log_safe_exception(
                logger,
                "Prediction provider failure write-back failed",
                exc,
                error_code="prediction_resolver_writeback_failed",
                context={"prediction_id": prediction_id},
                level=logging.WARNING,
            )
            return TickItemResult(
                prediction_id=prediction_id,
                disposition="error",
                reason="data_unavailable_write_failed",
            )
        return self._data_unavailable_result(
            prediction_id=prediction_id,
            reason="provider_exception",
            applied=applied,
        )

    def _handle_resolve_exception(
        self,
        work: _ClaimedWork,
        *,
        as_of: datetime,
    ) -> TickItemResult:
        prediction_id = str(_attr(work.record, "prediction_id"))
        try:
            applied = self._mark_unavailable(
                prediction_id=prediction_id,
                reason="resolver_exception",
                lease_token=work.lease_token,
                as_of=as_of,
                attempts=work.attempts,
            )
        except Exception as write_exc:  # broad-exception: fallback_recorded - preserve lease for recovery
            log_safe_exception(
                logger,
                "Prediction data_unavailable write-back failed",
                write_exc,
                error_code="prediction_resolver_writeback_failed",
                context={"prediction_id": prediction_id},
                level=logging.WARNING,
            )
            return TickItemResult(
                prediction_id=prediction_id,
                disposition="error",
                reason="data_unavailable_write_failed",
            )
        return self._data_unavailable_result(
            prediction_id=prediction_id,
            reason="resolver_exception",
            applied=applied,
        )

    @staticmethod
    def _data_unavailable_result(
        *, prediction_id: str, reason: str, applied: bool
    ) -> TickItemResult:
        if not applied:
            return TickItemResult(
                prediction_id=prediction_id,
                disposition="skipped",
                reason="data_unavailable_not_applied",
                applied=False,
            )
        return TickItemResult(
            prediction_id=prediction_id,
            disposition="data_unavailable",
            label=OUTCOME_DATA_UNAVAILABLE,
            reason=reason,
            applied=True,
        )

    def _mark_unavailable(
        self,
        *,
        prediction_id: str,
        reason: str,
        lease_token: str,
        as_of: datetime,
        attempts: int,
        extra: Optional[Mapping[str, Any]] = None,
    ) -> bool:
        outcome = build_data_unavailable_outcome(
            reason=reason,
            as_of=as_of,
            attempts=attempts,
            max_attempts=self._max_attempts,
            worker_id=self._worker_id,
            extra=extra,
            retry_jitter_ratio=self._retry_jitter_ratio,
            retry_random_value=self._rng.random(),
        )
        applied, _ = self._store.mark_data_unavailable(
            prediction_id=prediction_id,
            reason=reason,
            expected_lease_token=lease_token,
            as_of=as_of,
            outcome=outcome,
        )
        self._emit(
            "prediction.resolve.data_unavailable",
            {
                "prediction_id": prediction_id,
                "reason": reason,
                "applied": applied,
                "attempts": attempts,
                "retry_exhausted": bool(outcome.get("retry_exhausted")),
                "next_attempt_at": outcome.get("next_attempt_at"),
            },
        )
        return applied

    def _score_snapshot_and_write(
        self,
        work: _ClaimedWork,
        *,
        snapshot: Any,
        as_of: datetime,
    ) -> TickItemResult:
        claimed = work.record
        lease_token = work.lease_token
        attempts = work.attempts
        request = work.request
        prediction_id = str(_attr(claimed, "prediction_id"))
        symbol = request.symbol
        market = request.market
        claims = list(_attr(claimed, "claims") or [])
        snapshot_ok = bool(_attr(snapshot, "ok", False)) and not bool(
            _attr(snapshot, "data_unavailable", False)
        )
        if not snapshot_ok:
            reason = str(
                _attr(snapshot, "reason")
                or _attr(snapshot, "status")
                or "data_unavailable"
            )
            applied = self._mark_unavailable(
                prediction_id=prediction_id,
                reason=reason,
                lease_token=lease_token,
                as_of=as_of,
                attempts=attempts,
                extra={
                    "retryable": bool(_attr(snapshot, "retryable", True)),
                    "actuals": _mapping(snapshot),
                    "symbol": symbol,
                    "market": market,
                },
            )
            return self._data_unavailable_result(
                prediction_id=prediction_id,
                reason=reason,
                applied=applied,
            )

        claim_actuals = _claim_actuals_from_snapshot(snapshot)
        if claim_actuals.get("unavailable_reason"):
            reason = str(claim_actuals["unavailable_reason"])
            applied = self._mark_unavailable(
                prediction_id=prediction_id,
                reason=reason,
                lease_token=lease_token,
                as_of=as_of,
                attempts=attempts,
                extra={"actuals": _mapping(snapshot)},
            )
            return self._data_unavailable_result(
                prediction_id=prediction_id,
                reason=reason,
                applied=applied,
            )

        report = self._scorer.score(claims, claim_actuals, self._score_config)
        label = _label_from_score_report(report)
        report_payload = _mapping(report)

        if label == OUTCOME_DATA_UNAVAILABLE or label not in TERMINAL_SCORE_LABELS:
            reason = "score_data_unavailable"
            applied = self._mark_unavailable(
                prediction_id=prediction_id,
                reason=reason,
                lease_token=lease_token,
                as_of=as_of,
                attempts=attempts,
                extra={
                    "score": report_payload,
                    "actuals": _mapping(snapshot),
                },
            )
            return self._data_unavailable_result(
                prediction_id=prediction_id,
                reason=reason,
                applied=applied,
            )

        outcome: Dict[str, Any] = {
            "label": label,
            "score": report_payload,
            "actuals": _mapping(snapshot),
            "engine_version": PREDICTION_RESOLVER_ENGINE_VERSION,
            "scored_at": as_of.isoformat(),
            "worker_id": self._worker_id,
            "attempts": attempts,
            "symbol": symbol,
            "market": market,
            "as_of": request.as_of.isoformat(),
            "end": request.end.isoformat(),
        }
        applied, _ = self._store.resolve(
            prediction_id=prediction_id,
            outcome=outcome,
            expected_lease_token=lease_token,
            as_of=as_of,
        )
        self._emit(
            "prediction.resolve.completed",
            {
                "prediction_id": prediction_id,
                "label": label,
                "applied": applied,
                "symbol": symbol,
                "market": market,
                "run_id": _attr(claimed, "run_id"),
            },
        )
        if applied and label in {OUTCOME_MISS, OUTCOME_PARTIAL}:
            self._maybe_enqueue_postmortem(
                prediction_id=prediction_id,
                outcome=outcome,
                label=label,
            )
        return TickItemResult(
            prediction_id=prediction_id,
            disposition="resolved" if applied else "skipped",
            label=label,
            reason=None if applied else "resolve_not_applied",
            applied=applied,
        )

    def _maybe_enqueue_postmortem(
        self,
        *,
        prediction_id: str,
        outcome: Mapping[str, Any],
        label: str,
    ) -> None:
        if self._postmortem_queue is None:
            return
        if self._postmortem_budget_remaining <= 0:
            self._postmortem_dropped += 1
            return
        self._postmortem_budget_remaining -= 1
        try:
            accepted = self._postmortem_queue.enqueue(
                prediction_id=prediction_id,
                outcome=outcome,
                priority=10 if label == OUTCOME_MISS else 5,
            )
        except Exception as exc:  # broad-exception: fallback_recorded - optional hand-off
            log_safe_exception(
                logger,
                "Prediction postmortem enqueue failed",
                exc,
                error_code="prediction_resolver_postmortem_enqueue_failed",
                context={"prediction_id": prediction_id},
                level=logging.WARNING,
            )
            accepted = False
        if accepted:
            self._postmortem_enqueued += 1
        else:
            self._postmortem_dropped += 1

    def _emit(self, event_type: str, payload: Mapping[str, Any]) -> None:
        if self._event_sink is None:
            return
        try:
            self._event_sink.emit(event_type, dict(payload))
        except Exception as exc:  # broad-exception: fallback_recorded - audit must not block
            log_safe_exception(
                logger,
                "Prediction evolution event sink failed",
                exc,
                error_code="prediction_resolver_event_sink_failed",
                context={"event_type": event_type},
                level=logging.WARNING,
            )


class _LoggingEventSink:
    def emit(self, event_type: str, payload: Mapping[str, Any]) -> None:
        logger.info(
            "[PredictionResolver] event type=%s payload=%s",
            event_type,
            dict(payload),
        )


def build_prediction_resolver(
    *,
    store: Optional[PredictionStorePort] = None,
    actuals_fetcher: Optional[ActualsFetcherPort] = None,
    claim_scorer: Optional[ClaimScorerPort] = None,
    worker_id: Optional[str] = None,
    lease_seconds: int = 120,
    max_per_tick: int = 50,
    max_attempts: int = 5,
    fetch_concurrency: int = 4,
    postmortem_queue: Optional[PostmortemQueuePort] = None,
    postmortem_max_per_tick: int = 10,
    provider_error_circuit_threshold: int = 5,
    provider_error_circuit_cooldown_seconds: int = 60,
    circuit_open_max_per_tick: int = 5,
    retry_jitter_ratio: float = 0.1,
    event_sink: Optional[EvolutionEventSink] = None,
    require_persistence: bool = True,
) -> Optional[PredictionResolver]:
    """Build a resolver, discovering A3/A4/A5 implementations when omitted."""
    resolved_store = store
    resolved_fetcher = actuals_fetcher
    resolved_scorer = claim_scorer

    if resolved_store is None:
        try:
            from src.repositories.agent_prediction_repo import AgentPredictionRepository

            resolved_store = AgentPredictionRepository()
        except Exception as exc:  # broad-exception: fallback_recorded - optional dep
            log_safe_exception(
                logger,
                "Prediction store unavailable",
                exc,
                error_code="prediction_resolver_store_unavailable",
                level=logging.WARNING,
            )
            if require_persistence:
                return None

    if resolved_fetcher is None:
        try:
            from src.services.actuals_fetcher import ActualsFetcher

            resolved_fetcher = ActualsFetcher()
        except Exception as exc:  # broad-exception: fallback_recorded - optional dep
            log_safe_exception(
                logger,
                "ActualsFetcher unavailable",
                exc,
                error_code="prediction_resolver_actuals_unavailable",
                level=logging.WARNING,
            )
            return None

    if resolved_scorer is None:
        try:
            from src.services.claim_scorer import ClaimScorer

            resolved_scorer = ClaimScorer()
        except Exception as exc:  # broad-exception: fallback_recorded - optional dep
            log_safe_exception(
                logger,
                "ClaimScorer unavailable",
                exc,
                error_code="prediction_resolver_scorer_unavailable",
                level=logging.WARNING,
            )
            return None

    if resolved_store is None or resolved_fetcher is None or resolved_scorer is None:
        return None

    return PredictionResolver(
        store=resolved_store,
        actuals_fetcher=resolved_fetcher,
        claim_scorer=resolved_scorer,
        worker_id=worker_id,
        lease_seconds=lease_seconds,
        max_per_tick=max_per_tick,
        max_attempts=max_attempts,
        fetch_concurrency=fetch_concurrency,
        postmortem_queue=postmortem_queue,
        postmortem_max_per_tick=postmortem_max_per_tick,
        provider_error_circuit_threshold=provider_error_circuit_threshold,
        provider_error_circuit_cooldown_seconds=(
            provider_error_circuit_cooldown_seconds
        ),
        circuit_open_max_per_tick=circuit_open_max_per_tick,
        retry_jitter_ratio=retry_jitter_ratio,
        event_sink=event_sink if event_sink is not None else _LoggingEventSink(),
    )


def _resolver_enabled(config: Any) -> bool:
    return bool(getattr(config, "prediction_resolve_enabled", False))


def _resolver_interval_seconds(config: Any) -> int:
    raw = getattr(
        config,
        "prediction_resolve_interval_seconds",
        PREDICTION_RESOLVER_DEFAULT_INTERVAL_SECONDS,
    )
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = PREDICTION_RESOLVER_DEFAULT_INTERVAL_SECONDS
    return max(PREDICTION_RESOLVER_MIN_INTERVAL_SECONDS, value)


def build_prediction_resolver_background_tasks(
    config: Any,
    *,
    config_provider: Optional[Callable[[], Any]] = None,
    resolver: Optional[PredictionResolver] = None,
    postmortem_queue: Optional[PostmortemQueuePort] = None,
) -> List[Dict[str, Any]]:
    """Register periodic prediction_resolver task on the existing Scheduler."""
    del config_provider
    if not _resolver_enabled(config):
        return []

    lease_seconds = int(getattr(config, "prediction_resolve_lease_seconds", 120))
    max_per_tick = int(getattr(config, "prediction_resolve_max_per_tick", 50))
    max_attempts = int(getattr(config, "prediction_resolve_max_attempts", 5))
    fetch_concurrency = int(
        getattr(config, "prediction_resolve_fetch_concurrency", 4)
    )
    postmortem_max_per_tick = int(
        getattr(config, "prediction_resolve_postmortem_max_per_tick", 10)
    )
    provider_error_circuit_threshold = int(
        getattr(config, "prediction_resolve_provider_error_circuit_threshold", 5)
    )
    provider_error_circuit_cooldown_seconds = int(
        getattr(
            config,
            "prediction_resolve_provider_error_circuit_cooldown_seconds",
            60,
        )
    )
    circuit_open_max_per_tick = int(
        getattr(config, "prediction_resolve_circuit_open_max_per_tick", 5)
    )
    retry_jitter_ratio = float(
        getattr(config, "prediction_resolve_retry_jitter_ratio", 0.1)
    )

    active = resolver
    if active is None:
        active = build_prediction_resolver(
            lease_seconds=lease_seconds,
            max_per_tick=max_per_tick,
            max_attempts=max_attempts,
            fetch_concurrency=fetch_concurrency,
            postmortem_queue=postmortem_queue,
            postmortem_max_per_tick=postmortem_max_per_tick,
            provider_error_circuit_threshold=provider_error_circuit_threshold,
            provider_error_circuit_cooldown_seconds=(
                provider_error_circuit_cooldown_seconds
            ),
            circuit_open_max_per_tick=circuit_open_max_per_tick,
            retry_jitter_ratio=retry_jitter_ratio,
            require_persistence=True,
        )
    if active is None:
        logger.warning(
            "[PredictionResolver] enabled but store/fetcher/scorer unavailable; "
            "background task not registered"
        )
        return []

    def prediction_resolver_task() -> None:
        summary = active.tick()
        if summary.skipped_overlap:
            return
        if summary.claimed or summary.errors:
            logger.info(
                "[PredictionResolver] scheduled tick resolved=%s data_unavailable=%s errors=%s",
                summary.resolved,
                summary.data_unavailable,
                summary.errors,
            )

    return [
        {
            "task": prediction_resolver_task,
            "interval_seconds": _resolver_interval_seconds(config),
            "run_immediately": True,
            "name": PREDICTION_RESOLVER_BACKGROUND_TASK_NAME,
        }
    ]
