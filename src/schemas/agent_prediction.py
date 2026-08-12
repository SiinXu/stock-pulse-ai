# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Agent prediction persistence contracts (Issue #1112 / Epic #1107).

Owns status constants and the detached row shape used by the prediction store.
Typed claim payloads belong to the A1 PredictionRecord contract (#1101); this
module stores claims and outcomes as JSON text and does not invent claims.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional


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
        STATUS_DATA_UNAVAILABLE,
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
    resolved_at: Optional[datetime] = None

    def is_terminal(self) -> bool:
        return self.status in TERMINAL_AGENT_PREDICTION_STATUSES


@dataclass(frozen=True)
class AgentPredictionInsert:
    """Fields required to insert a pending prediction row."""

    prediction_id: str
    run_id: str
    symbol: str
    market: str
    horizon: str
    resolve_after: datetime
    claims: List[Any]
    model_meta: Optional[Mapping[str, Any]] = None
    created_at: Optional[datetime] = None
    status: str = STATUS_PENDING
