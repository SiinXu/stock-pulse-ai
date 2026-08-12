# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""PredictionResolver: claim due → actuals → score → write-back (#1102 / #1116)."""

from __future__ import annotations

import logging
import socket
import threading
import uuid
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from src.services.prediction_resolver.memory_store import new_lease_token
from src.services.prediction_resolver.ports import (
    ActualsFetcherPort,
    ClaimScorerPort,
    EvolutionEventSink,
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

OUTCOME_HIT = "hit"
OUTCOME_MISS = "miss"
OUTCOME_PARTIAL = "partial"
OUTCOME_DATA_UNAVAILABLE = "data_unavailable"

TERMINAL_SCORE_LABELS = frozenset({OUTCOME_HIT, OUTCOME_MISS, OUTCOME_PARTIAL})


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


def _mapping(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        if isinstance(payload, Mapping):
            return dict(payload)
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
) -> float:
    """Bounded exponential backoff from the current attempt count."""
    safe_attempts = max(1, int(attempts))
    delay = float(base_seconds) * (2.0 ** max(0, safe_attempts - 1))
    return min(float(max_seconds), delay)


def build_data_unavailable_outcome(
    *,
    reason: str,
    as_of: datetime,
    attempts: int,
    max_attempts: int,
    worker_id: str,
    extra: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Build outcome payload including retry scheduling metadata.

    Stores that only persist ``outcome_json`` can still honor backoff by reading
    ``next_attempt_at`` / ``retry_exhausted`` from the payload (memory store does).
    """
    exhausted = int(attempts) >= int(max_attempts)
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
        delay = compute_retry_delay_seconds(attempts)
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
    if high_price is None and end_bar is not None:
        high_price = _attr(end_bar, "high")
    if low_price is None and end_bar is not None:
        low_price = _attr(end_bar, "low")
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


@dataclass
class TickSummary:
    claimed: int = 0
    resolved: int = 0
    data_unavailable: int = 0
    skipped: int = 0
    errors: int = 0
    skipped_overlap: bool = False
    items: List[TickItemResult] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "claimed": self.claimed,
            "resolved": self.resolved,
            "data_unavailable": self.data_unavailable,
            "skipped": self.skipped,
            "errors": self.errors,
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
        clock: Optional[Callable[[], datetime]] = None,
        score_config: Any = None,
    ) -> None:
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be >= 1")
        if max_per_tick < 0:
            raise ValueError("max_per_tick must be >= 0")
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        self._store = store
        self._actuals = actuals_fetcher
        self._scorer = claim_scorer
        self._worker_id = worker_id or f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"
        self._lease_seconds = int(lease_seconds)
        self._max_per_tick = int(max_per_tick)
        self._max_attempts = int(max_attempts)
        self._event_sink = event_sink
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
            as_of = _as_utc_naive(now) if now is not None else self._clock()
            claim_limit = self._max_per_tick if limit is None else max(0, int(limit))
            if claim_limit == 0:
                return summary
            due = list(self._store.list_due(as_of=as_of, limit=claim_limit))
            for candidate in due:
                prediction_id = str(_attr(candidate, "prediction_id") or "").strip()
                if not prediction_id:
                    summary.skipped += 1
                    continue
                item = self._resolve_one(candidate, as_of=as_of)
                summary.items.append(item)
                if item.disposition == "claimed_failed":
                    summary.skipped += 1
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
            if summary.claimed or summary.skipped_overlap:
                logger.info(
                    "[PredictionResolver] tick complete worker=%s claimed=%s "
                    "resolved=%s data_unavailable=%s skipped=%s errors=%s",
                    self._worker_id,
                    summary.claimed,
                    summary.resolved,
                    summary.data_unavailable,
                    summary.skipped,
                    summary.errors,
                )
            return summary
        finally:
            self._tick_lock.release()

    def _resolve_one(self, candidate: Any, *, as_of: datetime) -> TickItemResult:
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
            return TickItemResult(
                prediction_id=prediction_id,
                disposition="error",
                reason="claim_failed",
            )
        if claimed is None:
            return TickItemResult(
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
            return TickItemResult(
                prediction_id=prediction_id,
                disposition="data_unavailable",
                label=OUTCOME_DATA_UNAVAILABLE,
                reason="max_attempts_exhausted",
                applied=applied,
            )
        try:
            return self._score_and_write(
                claimed,
                lease_token=lease_token,
                as_of=as_of,
                attempts=attempts,
            )
        except Exception as exc:  # broad-exception: fallback_recorded - never invent hit
            log_safe_exception(
                logger,
                "Prediction resolve path failed; marking data_unavailable",
                exc,
                error_code="prediction_resolver_path_failed",
                context={"prediction_id": prediction_id},
                level=logging.WARNING,
            )
            applied = self._mark_unavailable(
                prediction_id=prediction_id,
                reason="resolver_exception",
                lease_token=lease_token,
                as_of=as_of,
                attempts=attempts,
            )
            return TickItemResult(
                prediction_id=prediction_id,
                disposition="data_unavailable",
                label=OUTCOME_DATA_UNAVAILABLE,
                reason="resolver_exception",
                applied=applied,
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

    def _score_and_write(
        self,
        claimed: Any,
        *,
        lease_token: str,
        as_of: datetime,
        attempts: int,
    ) -> TickItemResult:
        prediction_id = str(_attr(claimed, "prediction_id"))
        symbol = str(_attr(claimed, "symbol") or "").strip()
        market = str(_attr(claimed, "market") or "").strip().lower() or None
        claims = list(_attr(claimed, "claims") or [])
        created_at = _attr(claimed, "created_at")
        resolve_after = _attr(claimed, "resolve_after")
        as_of_date = _to_date(created_at) or _to_date(as_of)
        end_date = _to_date(resolve_after) or _to_date(as_of)

        if not symbol or as_of_date is None or end_date is None:
            applied = self._mark_unavailable(
                prediction_id=prediction_id,
                reason="invalid_prediction_fields",
                lease_token=lease_token,
                as_of=as_of,
                attempts=attempts,
            )
            return TickItemResult(
                prediction_id=prediction_id,
                disposition="data_unavailable",
                label=OUTCOME_DATA_UNAVAILABLE,
                reason="invalid_prediction_fields",
                applied=applied,
            )

        snapshot = self._actuals.fetch(
            symbol=symbol,
            as_of=as_of_date,
            market=market,
            end=end_date,
        )
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
            return TickItemResult(
                prediction_id=prediction_id,
                disposition="data_unavailable",
                label=OUTCOME_DATA_UNAVAILABLE,
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
            return TickItemResult(
                prediction_id=prediction_id,
                disposition="data_unavailable",
                label=OUTCOME_DATA_UNAVAILABLE,
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
            return TickItemResult(
                prediction_id=prediction_id,
                disposition="data_unavailable",
                label=OUTCOME_DATA_UNAVAILABLE,
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
            "as_of": as_of_date.isoformat(),
            "end": end_date.isoformat(),
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
        return TickItemResult(
            prediction_id=prediction_id,
            disposition="resolved" if applied else "skipped",
            label=label,
            reason=None if applied else "resolve_not_applied",
            applied=applied,
        )

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
) -> List[Dict[str, Any]]:
    """Register periodic prediction_resolver task on the existing Scheduler."""
    del config_provider
    if not _resolver_enabled(config):
        return []

    lease_seconds = int(getattr(config, "prediction_resolve_lease_seconds", 120) or 120)
    max_per_tick = int(getattr(config, "prediction_resolve_max_per_tick", 50) or 50)
    max_attempts = int(getattr(config, "prediction_resolve_max_attempts", 5) or 5)

    active = resolver
    if active is None:
        active = build_prediction_resolver(
            lease_seconds=lease_seconds,
            max_per_tick=max_per_tick,
            max_attempts=max_attempts,
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
