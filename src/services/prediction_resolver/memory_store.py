# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""In-memory prediction store with real lease / CAS semantics for tests."""

from __future__ import annotations

import copy
import threading
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence


STATUS_PENDING = "pending"
STATUS_RESOLVING = "resolving"
STATUS_RESOLVED = "resolved"
STATUS_DATA_UNAVAILABLE = "data_unavailable"

CLAIMABLE = frozenset({STATUS_PENDING, STATUS_DATA_UNAVAILABLE})
RESOLVABLE = frozenset({STATUS_PENDING, STATUS_RESOLVING})
TERMINAL = frozenset({STATUS_RESOLVED})


def _utc_naive_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass
class MemoryPredictionRecord:
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

    def snapshot(self) -> "MemoryPredictionRecord":
        return replace(
            self,
            claims=copy.deepcopy(self.claims),
            outcome=copy.deepcopy(self.outcome) if self.outcome is not None else None,
            model_meta=copy.deepcopy(self.model_meta) if self.model_meta is not None else None,
        )


@dataclass
class InMemoryPredictionStore:
    _rows: Dict[str, MemoryPredictionRecord] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock)
    _clock: Any = field(default=_utc_naive_now)

    def insert(
        self,
        *,
        prediction_id: str,
        run_id: str,
        symbol: str,
        market: str,
        horizon: str,
        resolve_after: datetime,
        claims: Sequence[Any],
        created_at: Optional[datetime] = None,
        model_meta: Optional[Mapping[str, Any]] = None,
        status: str = STATUS_PENDING,
    ) -> MemoryPredictionRecord:
        now = created_at or self._clock()
        row = MemoryPredictionRecord(
            prediction_id=str(prediction_id),
            run_id=str(run_id),
            symbol=str(symbol),
            market=str(market).lower(),
            horizon=str(horizon),
            resolve_after=resolve_after,
            status=status,
            claims=list(claims),
            created_at=now,
            updated_at=now,
            model_meta=dict(model_meta) if model_meta is not None else None,
        )
        with self._lock:
            if row.prediction_id in self._rows:
                raise ValueError(f"prediction already exists: {row.prediction_id}")
            self._rows[row.prediction_id] = row
            return row.snapshot()

    def get(self, prediction_id: str) -> Optional[MemoryPredictionRecord]:
        with self._lock:
            row = self._rows.get(str(prediction_id))
            return row.snapshot() if row is not None else None

    def list_due(self, *, as_of: datetime, limit: int) -> List[MemoryPredictionRecord]:
        bound = max(1, min(int(limit), 1000))
        with self._lock:
            due = [
                row.snapshot()
                for row in self._rows.values()
                if row.status in CLAIMABLE and row.resolve_after <= as_of
            ]
        due.sort(key=lambda r: (r.resolve_after, r.prediction_id))
        return due[:bound]

    def claim_for_resolve(
        self,
        *,
        prediction_id: str,
        lease_owner: str,
        lease_token: str,
        lease_ttl_seconds: int = 120,
        as_of: Optional[datetime] = None,
    ) -> Optional[MemoryPredictionRecord]:
        canonical = str(prediction_id or "").strip()
        owner = str(lease_owner or "").strip()
        token = str(lease_token or "").strip()
        if not canonical or not owner or not token:
            raise ValueError("prediction_id, lease_owner, and lease_token are required")
        now = as_of or self._clock()
        expires = now + timedelta(seconds=max(1, int(lease_ttl_seconds)))
        with self._lock:
            row = self._rows.get(canonical)
            if row is None or row.status in TERMINAL:
                return None
            claimable = row.status in CLAIMABLE
            expired_lease = (
                row.status == STATUS_RESOLVING
                and (row.lease_expires_at is None or row.lease_expires_at <= now)
            )
            if not claimable and not expired_lease:
                return None
            row.status = STATUS_RESOLVING
            row.lease_owner = owner
            row.lease_token = token
            row.lease_expires_at = expires
            row.attempts = int(row.attempts or 0) + 1
            row.updated_at = now
            return row.snapshot()

    def resolve(
        self,
        *,
        prediction_id: str,
        outcome: Mapping[str, Any],
        expected_lease_token: Optional[str] = None,
        as_of: Optional[datetime] = None,
    ) -> tuple[bool, Optional[MemoryPredictionRecord]]:
        canonical = str(prediction_id or "").strip()
        if not canonical:
            raise ValueError("prediction_id is required")
        if not isinstance(outcome, Mapping):
            raise ValueError("outcome must be a mapping")
        now = as_of or self._clock()
        with self._lock:
            row = self._rows.get(canonical)
            if row is None:
                return False, None
            if row.status in TERMINAL or row.status not in RESOLVABLE:
                return False, row.snapshot()
            if expected_lease_token is not None and row.lease_token != str(expected_lease_token):
                return False, row.snapshot()
            row.status = STATUS_RESOLVED
            row.outcome = dict(outcome)
            row.resolved_at = now
            row.updated_at = now
            row.lease_owner = None
            row.lease_token = None
            row.lease_expires_at = None
            return True, row.snapshot()

    def mark_data_unavailable(
        self,
        *,
        prediction_id: str,
        reason: str,
        expected_lease_token: Optional[str] = None,
        as_of: Optional[datetime] = None,
        outcome: Optional[Mapping[str, Any]] = None,
    ) -> tuple[bool, Optional[MemoryPredictionRecord]]:
        canonical = str(prediction_id or "").strip()
        if not canonical:
            raise ValueError("prediction_id is required")
        now = as_of or self._clock()
        payload: Dict[str, Any] = {
            "label": STATUS_DATA_UNAVAILABLE,
            "reason": str(reason or "data_unavailable"),
        }
        if outcome:
            payload.update(dict(outcome))
        with self._lock:
            row = self._rows.get(canonical)
            if row is None:
                return False, None
            if row.status in TERMINAL or row.status != STATUS_RESOLVING:
                return False, row.snapshot()
            if expected_lease_token is not None and row.lease_token != str(expected_lease_token):
                return False, row.snapshot()
            row.status = STATUS_DATA_UNAVAILABLE
            row.outcome = payload
            row.updated_at = now
            row.lease_owner = None
            row.lease_token = None
            row.lease_expires_at = None
            return True, row.snapshot()


def new_lease_token() -> str:
    return uuid.uuid4().hex
