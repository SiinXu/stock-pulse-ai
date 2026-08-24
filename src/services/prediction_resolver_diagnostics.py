# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Read-only prediction-resolver claimable-due, UTC-day, and lag diagnostics (#1114)."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence

from src.services.prediction_resolver.resolver import (
    PREDICTION_RESOLVER_BACKLOG_PROBE_LIMIT,
    PREDICTION_RESOLVER_BACKGROUND_TASK_NAME,
    _as_utc_naive,
    _attr,
    _resolver_interval_seconds,
    _to_datetime,
    list_claimable_due,
)
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)
OLDEST_DUE_LIMIT = 10
_RESOLVED_UTC_DAY_COUNT_KEYS = ("hit", "miss", "partial", "unavailable", "unlabeled")


class PredictionResolverDiagnosticsStoreError(RuntimeError):
    """Raised when the claimable-due store probe cannot be read."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_utc_iso(value: datetime) -> str:
    return _as_utc_naive(value).replace(tzinfo=timezone.utc).isoformat()


def _this_process_worker_registered(scheduler: Any) -> bool:
    if scheduler is None:
        return False
    reader = getattr(scheduler, "has_registered_background_task", None)
    if not callable(reader):
        return False
    return bool(reader(PREDICTION_RESOLVER_BACKGROUND_TASK_NAME))


def _claim_limit(config: Any) -> int:
    raw = getattr(config, "prediction_resolve_max_per_tick", 50)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 50
    return max(0, value)


def _probe_limit(claim_limit: int) -> int:
    return min(
        10_000,
        max(PREDICTION_RESOLVER_BACKLOG_PROBE_LIMIT, claim_limit + 1),
    )


def _utc_civil_day_bounds(as_of: datetime) -> tuple[datetime, datetime]:
    naive = _as_utc_naive(as_of)
    start = datetime(naive.year, naive.month, naive.day)
    end = start + timedelta(days=1)
    return start, end


def _normalize_resolved_utc_day_counts(raw: Any) -> Dict[str, int]:
    if not isinstance(raw, Mapping):
        raise TypeError("count_resolved_utc_day must return a mapping")
    counts: Dict[str, int] = {}
    for key in _RESOLVED_UTC_DAY_COUNT_KEYS:
        value = raw[key]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{key} count must be a non-negative integer")
        counts[key] = value
    return counts


def _row_lag_seconds(row: Any, *, as_of: datetime) -> float:
    resolve_after = _to_datetime(_attr(row, "resolve_after"))
    if resolve_after is None:
        return 0.0
    return max(0.0, (as_of - resolve_after).total_seconds())


def _nearest_rank_quantile(sorted_values: Sequence[float], percentile: float) -> float:
    n = len(sorted_values)
    rank = min(n, max(1, math.ceil(percentile / 100.0 * n)))
    return float(sorted_values[rank - 1])


def _claimable_due_lag_seconds(
    rows: List[Any], *, as_of: datetime
) -> Dict[str, Optional[float]]:
    if not rows:
        return {"p50": None, "p95": None, "max": None}
    lags = sorted(_row_lag_seconds(row, as_of=as_of) for row in rows)
    return {
        "p50": _nearest_rank_quantile(lags, 50),
        "p95": _nearest_rank_quantile(lags, 95),
        "max": lags[-1],
    }


def _oldest_due_items(rows: List[Any], *, as_of: datetime) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for row in rows[:OLDEST_DUE_LIMIT]:
        resolve_after = _to_datetime(_attr(row, "resolve_after"))
        if resolve_after is None:
            resolve_after_iso = _to_utc_iso(as_of)
        else:
            resolve_after_iso = _to_utc_iso(resolve_after)
        items.append(
            {
                "prediction_id": str(_attr(row, "prediction_id") or ""),
                "symbol": str(_attr(row, "symbol") or ""),
                "market": str(_attr(row, "market") or ""),
                "status": str(_attr(row, "status") or ""),
                "resolve_after": resolve_after_iso,
                "lag_seconds": _row_lag_seconds(row, as_of=as_of),
            }
        )
    return items


def collect_prediction_resolver_diagnostics(
    *,
    config: Any,
    store: Any,
    scheduler: Any = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Compose a read-only claimable-due and UTC-day snapshot for this API process.

    Never claims, requeues, ticks, constructs, or starts a resolver worker.
    ``this_process_worker_registered`` is this process's scheduler cache only.
    Either store probe failure raises ``PredictionResolverDiagnosticsStoreError``.
    """
    observed = now if now is not None else _utc_now()
    as_of = _as_utc_naive(observed)
    day_start, day_end = _utc_civil_day_bounds(as_of)
    claim_limit = _claim_limit(config)
    probe_limit = _probe_limit(claim_limit)
    try:
        rows = list(list_claimable_due(store, as_of=as_of, limit=probe_limit))
        counter = getattr(store, "count_resolved_utc_day", None)
        if not callable(counter):
            raise TypeError("prediction store does not implement count_resolved_utc_day")
        counts = _normalize_resolved_utc_day_counts(counter(as_of=as_of))
    except Exception as exc:  # broad-exception: fallback_recorded - map unread store to explicit 503
        log_safe_exception(
            logger,
            "Prediction resolver diagnostics store is unavailable",
            exc,
            error_code="internal_error",
        )
        raise PredictionResolverDiagnosticsStoreError(
            "Prediction resolver diagnostics store is unavailable"
        ) from exc
    return {
        "enabled": bool(getattr(config, "prediction_resolve_enabled", False)),
        "interval_seconds": _resolver_interval_seconds(config),
        "this_process_worker_registered": _this_process_worker_registered(scheduler),
        "observed_at": _to_utc_iso(as_of),
        "claimable_due_count": len(rows),
        "claimable_due_truncated": len(rows) >= probe_limit,
        "claimable_due_probe_limit": probe_limit,
        "oldest_due": _oldest_due_items(rows, as_of=as_of),
        "resolved_utc_day_start": _to_utc_iso(day_start),
        "resolved_utc_day_end": _to_utc_iso(day_end),
        "resolved_utc_day_counts": counts,
        "claimable_due_lag_seconds": _claimable_due_lag_seconds(rows, as_of=as_of),
    }
