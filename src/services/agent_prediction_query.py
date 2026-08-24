# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Read-only projection of stored predictions for the authenticated query API.

Issue #1102 leftover: HTTP get-by-id and identity-filtered list. This module
calls only repository ``get`` / ``list_by_run_id`` / ``list_by_symbol_market``.
It never claims, resolves, requeues, lists due work, or returns raw outcome
payloads, claims, leases, or model metadata.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, Mapping, Optional

from src.repositories.agent_prediction_repo import AgentPredictionRepository
from src.schemas.agent_prediction import (
    AGENT_PREDICTION_STATUSES,
    STATUS_DATA_UNAVAILABLE,
    AgentPredictionRecord,
)
from src.schemas.prediction_record import PREDICTION_HORIZON_TOKENS
from src.storage import DatabaseManager


PUBLIC_LIST_LIMIT_MAX = 50
ALLOWED_OUTCOME_LABELS = frozenset({"hit", "miss", "partial", "data_unavailable"})


class AgentPredictionQueryError(Exception):
    """Base error for authenticated prediction query reads."""


class AgentPredictionNotFoundError(AgentPredictionQueryError):
    """Raised when the requested prediction identity does not exist."""


class AgentPredictionFilterError(AgentPredictionQueryError):
    """Raised when list identity filters are mutually invalid."""


class AgentPredictionQueryService:
    """Project allowlisted prediction fields from the existing store readers."""

    def __init__(
        self,
        *,
        store: Optional[AgentPredictionRepository] = None,
        db_manager: Optional[DatabaseManager] = None,
    ) -> None:
        self.store = store or AgentPredictionRepository(db_manager)

    def get_prediction(self, prediction_id: str) -> Dict[str, Any]:
        record = self.store.get(prediction_id)
        if record is None:
            raise AgentPredictionNotFoundError("Prediction was not found")
        return project_prediction_item(record)

    def list_predictions(
        self,
        *,
        run_id: Optional[str] = None,
        symbol: Optional[str] = None,
        market: Optional[str] = None,
        limit: int = PUBLIC_LIST_LIMIT_MAX,
    ) -> Dict[str, Any]:
        bound = _public_limit(limit)
        has_run = run_id is not None
        has_symbol = symbol is not None
        has_market = market is not None
        if has_run and not has_symbol and not has_market:
            rows = self.store.list_by_run_id(run_id, limit=bound)
        elif (not has_run) and has_symbol and has_market:
            rows = self.store.list_by_symbol_market(
                symbol=symbol,
                market=market,
                limit=bound,
            )
        else:
            raise AgentPredictionFilterError(
                "Provide exactly one identity filter: run_id, or both symbol and market"
            )
        items = [project_prediction_item(row) for row in rows]
        return {"items": items, "truncated": len(items) == bound}


def _public_limit(limit: int) -> int:
    try:
        value = int(limit)
    except (TypeError, ValueError):
        value = PUBLIC_LIST_LIMIT_MAX
    return max(1, min(value, PUBLIC_LIST_LIMIT_MAX))


def project_outcome_label(record: AgentPredictionRecord) -> Optional[str]:
    """Return a bounded outcome token, or None. Unexpected labels fail closed."""
    status = str(getattr(record, "status", "") or "")
    if status == STATUS_DATA_UNAVAILABLE:
        return "data_unavailable"
    outcome = getattr(record, "outcome", None)
    if not isinstance(outcome, Mapping):
        return None
    label = outcome.get("label")
    if isinstance(label, str) and label in ALLOWED_OUTCOME_LABELS:
        return label
    return None


def project_prediction_item(record: AgentPredictionRecord) -> Dict[str, Any]:
    """Construct the public item. Never dump the store dataclass."""
    status = str(record.status or "")
    if status not in AGENT_PREDICTION_STATUSES:
        raise ValueError("prediction status is not allowlisted")
    horizon = str(record.horizon or "")
    if horizon not in PREDICTION_HORIZON_TOKENS:
        raise ValueError("prediction horizon is not allowlisted")
    return {
        "prediction_id": str(record.prediction_id),
        "run_id": str(record.run_id),
        "symbol": str(record.symbol),
        "market": str(record.market or "").lower(),
        "as_of": _as_of_iso(record.as_of),
        "horizon": horizon,
        "resolve_after": _to_utc_iso(record.resolve_after),
        "status": status,
        "outcome_label": project_outcome_label(record),
        "created_at": _to_utc_iso(record.created_at),
        "updated_at": _to_utc_iso(record.updated_at),
        "resolved_at": (
            _to_utc_iso(record.resolved_at) if record.resolved_at is not None else None
        ),
    }


def _as_of_iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value or "").strip()
    if not text:
        raise ValueError("prediction as_of is missing")
    return text


def _to_utc_iso(value: datetime) -> str:
    if not isinstance(value, datetime):
        raise ValueError("prediction timestamp must be a datetime")
    if value.tzinfo is None:
        aware = value.replace(tzinfo=timezone.utc)
    else:
        aware = value.astimezone(timezone.utc)
    return aware.isoformat()
