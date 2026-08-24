# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Read-only prediction-resolver claimable-due diagnostics (#1114)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

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


def _oldest_due_items(rows: List[Any], *, as_of: datetime) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for row in rows[:OLDEST_DUE_LIMIT]:
        resolve_after = _to_datetime(_attr(row, "resolve_after"))
        if resolve_after is None:
            resolve_after_iso = _to_utc_iso(as_of)
            lag_seconds = 0.0
        else:
            resolve_after_iso = _to_utc_iso(resolve_after)
            lag_seconds = max(0.0, (as_of - resolve_after).total_seconds())
        items.append(
            {
                "prediction_id": str(_attr(row, "prediction_id") or ""),
                "symbol": str(_attr(row, "symbol") or ""),
                "market": str(_attr(row, "market") or ""),
                "status": str(_attr(row, "status") or ""),
                "resolve_after": resolve_after_iso,
                "lag_seconds": lag_seconds,
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
    """Compose a read-only claimable-due snapshot for this API process.

    Never claims, requeues, ticks, constructs, or starts a resolver worker.
    ``this_process_worker_registered`` is this process's scheduler cache only.
    """
    observed = now if now is not None else _utc_now()
    as_of = _as_utc_naive(observed)
    claim_limit = _claim_limit(config)
    probe_limit = _probe_limit(claim_limit)
    try:
        rows = list(list_claimable_due(store, as_of=as_of, limit=probe_limit))
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
    }
