# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Agent prediction persistence contracts (Issue #1112 / Epic #1107).

Owns status constants and the detached row shape used by the prediction store.
Typed claim payloads belong to the A1 PredictionRecord contract (#1101); this
module stores claims and outcomes as JSON text and does not invent claims.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Mapping, Optional

from src.schemas.prediction_record import PredictionRecord


AGENT_PREDICTION_SCHEMA_VERSION = "agent-prediction-v1"

STATUS_PENDING = "pending"
STATUS_RESOLVING = "resolving"
STATUS_RESOLVED = "resolved"
STATUS_DATA_UNAVAILABLE = "data_unavailable"
STATUS_EXPIRED = "expired"
STATUS_ERROR = "error"
STATUS_NO_VERIFIABLE_CLAIM = "no_verifiable_claim"

# Union of Issue #1112 lifecycle states and A1 PredictionRecord statuses.
AGENT_PREDICTION_STATUSES = frozenset(
    {
        STATUS_PENDING,
        STATUS_RESOLVING,
        STATUS_RESOLVED,
        STATUS_DATA_UNAVAILABLE,
        STATUS_EXPIRED,
        STATUS_ERROR,
        STATUS_NO_VERIFIABLE_CLAIM,
    }
)

# Terminal statuses must not be overwritten by concurrent resolvers.
TERMINAL_AGENT_PREDICTION_STATUSES = frozenset({STATUS_RESOLVED})

# Rows that may be claimed by a resolver worker (including expired leases).
CLAIMABLE_AGENT_PREDICTION_STATUSES = frozenset(
    {
        STATUS_PENDING,
    }
)

# Source statuses allowed for a one-shot resolve transition.
RESOLVABLE_AGENT_PREDICTION_STATUSES = frozenset(
    {
        STATUS_PENDING,
        STATUS_RESOLVING,
    }
)


@dataclass(frozen=True)
class AgentPredictionRecord:
    """Detached prediction row returned by the repository."""

    prediction_id: str
    run_id: str
    symbol: str
    market: str
    as_of: date
    horizon: str
    resolve_after: datetime
    status: str
    claims: List[Any]
    created_at: datetime
    updated_at: datetime
    attempts: int = 0
    lease_owner: Optional[str] = None
    lease_token: Optional[str] = None
    lease_expires_at: Optional[datetime] = None
    outcome: Optional[Dict[str, Any]] = None
    model_meta: Optional[Dict[str, Any]] = None
    source_decision_id: Optional[str] = None
    no_verifiable_reason: Optional[str] = None
    notes: Optional[str] = None
    resolved_at: Optional[datetime] = None
    provenance_source: Optional[str] = None
    actor_id: Optional[str] = None

    def is_terminal(self) -> bool:
        return self.status in TERMINAL_AGENT_PREDICTION_STATUSES


@dataclass(frozen=True)
class AgentPredictionInsert:
    """Fields required to insert a pending prediction row."""

    prediction_id: str
    run_id: str
    symbol: str
    market: str
    as_of: date
    horizon: str
    resolve_after: datetime
    claims: List[Any]
    model_meta: Optional[Mapping[str, Any]] = None
    created_at: Optional[datetime] = None
    status: str = STATUS_PENDING
    source_decision_id: Optional[str] = None
    no_verifiable_reason: Optional[str] = None
    notes: Optional[str] = None

    @classmethod
    def from_prediction_record(
        cls, record: PredictionRecord
    ) -> "AgentPredictionInsert":
        """Project the complete A1 draft fields needed by persistence/resolution."""
        return cls(
            prediction_id=record.prediction_id,
            run_id=record.run_id,
            symbol=record.symbol,
            market=record.market or "",
            as_of=record.as_of,
            horizon=record.horizon,
            resolve_after=record.resolve_after,
            claims=[claim.model_dump(mode="json") for claim in record.claims],
            model_meta=record.model_meta.model_dump(mode="json"),
            created_at=record.created_at,
            status=record.status,
            source_decision_id=record.source_decision_id,
            no_verifiable_reason=record.no_verifiable_reason,
            notes=record.notes,
        )
