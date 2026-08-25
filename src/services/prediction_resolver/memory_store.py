# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""In-memory prediction store with real lease / CAS semantics for tests.

Due-scan contract (must stay aligned with A3 store predicates when that lands):

- ``pending`` with ``resolve_after <= as_of``
- ``data_unavailable`` rows remain visible to status-specific scans so the
  resolver can requeue them after durable backoff
- ``resolving`` with expired or missing lease (crash recovery reclaim)
"""

from __future__ import annotations

import copy
import threading
import uuid
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence

from src.schemas.memory_write_policy import require_market_actuals_write


STATUS_PENDING = "pending"
STATUS_RESOLVING = "resolving"
STATUS_RESOLVED = "resolved"
STATUS_DATA_UNAVAILABLE = "data_unavailable"

CLAIMABLE = frozenset({STATUS_PENDING})
RESOLVABLE = frozenset({STATUS_PENDING, STATUS_RESOLVING})
TERMINAL = frozenset({STATUS_RESOLVED})


def _utc_naive_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_optional_datetime(value: Any) -> Optional[datetime]:
    if value is None or value is False:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


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
    as_of: date
    attempts: int = 0
    lease_owner: Optional[str] = None
    lease_token: Optional[str] = None
    lease_expires_at: Optional[datetime] = None
    outcome: Optional[Dict[str, Any]] = None
    model_meta: Optional[Dict[str, Any]] = None
    resolved_at: Optional[datetime] = None
    next_attempt_at: Optional[datetime] = None
    retry_exhausted: bool = False
    provenance_source: Optional[str] = None
    actor_id: Optional[str] = None

    def snapshot(self) -> "MemoryPredictionRecord":
        return replace(
            self,
            claims=copy.deepcopy(self.claims),
            outcome=copy.deepcopy(self.outcome) if self.outcome is not None else None,
            model_meta=copy.deepcopy(self.model_meta) if self.model_meta is not None else None,
        )


_SCORED_OUTCOME_LABELS = frozenset({"hit", "miss", "partial"})
_RESOLVED_UTC_DAY_COUNT_KEYS = ("hit", "miss", "partial", "unavailable", "unlabeled")


def _utc_civil_day_bounds(as_of: datetime) -> tuple[datetime, datetime]:
    naive = as_of
    if naive.tzinfo is not None:
        naive = naive.astimezone(timezone.utc).replace(tzinfo=None)
    start = datetime(naive.year, naive.month, naive.day)
    end = start + timedelta(days=1)
    return start, end


def _outcome_label(outcome: Optional[Mapping[str, Any]]) -> Optional[str]:
    if not isinstance(outcome, Mapping) or "label" not in outcome:
        return None
    raw = outcome.get("label")
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw
    return str(raw)


def _outcome_retry_exhausted(outcome: Optional[Mapping[str, Any]]) -> bool:
    if not isinstance(outcome, Mapping):
        return False
    value = outcome.get("retry_exhausted")
    if value is True or value == 1:
        return True
    return isinstance(value, str) and value.strip().lower() == "true"


def _row_is_due(row: MemoryPredictionRecord, as_of: datetime) -> bool:
    """Whether a row is eligible for claim in the current tick."""
    if row.status in TERMINAL or row.retry_exhausted:
        return False
    if row.status == STATUS_PENDING:
        return row.resolve_after <= as_of
    if row.status == STATUS_DATA_UNAVAILABLE:
        if row.resolve_after > as_of:
            return False
        if row.next_attempt_at is not None and row.next_attempt_at > as_of:
            return False
        return True
    if row.status == STATUS_RESOLVING:
        # Crash recovery: reclaim only when the lease is missing or expired.
        return row.lease_expires_at is None or row.lease_expires_at <= as_of
    return False


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
        as_of: Optional[date] = None,
        model_meta: Optional[Mapping[str, Any]] = None,
        status: str = STATUS_PENDING,
        attempts: int = 0,
        lease_owner: Optional[str] = None,
        lease_token: Optional[str] = None,
        lease_expires_at: Optional[datetime] = None,
        next_attempt_at: Optional[datetime] = None,
        retry_exhausted: bool = False,
        outcome: Optional[Mapping[str, Any]] = None,
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
            as_of=as_of or now.date(),
            attempts=int(attempts or 0),
            lease_owner=lease_owner,
            lease_token=lease_token,
            lease_expires_at=lease_expires_at,
            model_meta=dict(model_meta) if model_meta is not None else None,
            next_attempt_at=next_attempt_at,
            retry_exhausted=bool(retry_exhausted),
            outcome=dict(outcome) if outcome is not None else None,
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

    def list_due(
        self,
        *,
        as_of: datetime,
        limit: int,
        statuses: Optional[Sequence[str]] = None,
    ) -> List[MemoryPredictionRecord]:
        bound = max(1, min(int(limit), 1000))
        allowed = frozenset(statuses) if statuses is not None else None
        with self._lock:
            due = [
                row.snapshot()
                for row in self._rows.values()
                if (allowed is None or row.status in allowed)
                and _row_is_due(row, as_of)
            ]
        due.sort(key=lambda r: (r.resolve_after, r.prediction_id))
        return due[:bound]

    def count_resolved_utc_day(self, *, as_of: datetime) -> Dict[str, int]:
        """Match the SQL UTC-day aggregate using outcome JSON fields only."""
        start, end = _utc_civil_day_bounds(as_of)
        counts = {key: 0 for key in _RESOLVED_UTC_DAY_COUNT_KEYS}
        with self._lock:
            for row in self._rows.values():
                if (
                    row.status == STATUS_RESOLVED
                    and row.resolved_at is not None
                    and start <= row.resolved_at < end
                ):
                    label = _outcome_label(row.outcome)
                    if label in _SCORED_OUTCOME_LABELS:
                        counts[str(label)] += 1
                    else:
                        counts["unlabeled"] += 1
                elif (
                    row.status == STATUS_DATA_UNAVAILABLE
                    and start <= row.updated_at < end
                    and _outcome_retry_exhausted(row.outcome)
                ):
                    counts["unavailable"] += 1
        return counts

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
            if row is None or row.status in TERMINAL or row.retry_exhausted:
                return None
            if not _row_is_due(row, now):
                return None
            # Active (non-expired) resolving lease held by anyone blocks re-claim.
            if (
                row.status == STATUS_RESOLVING
                and row.lease_expires_at is not None
                and row.lease_expires_at > now
            ):
                return None
            row.status = STATUS_RESOLVING
            row.lease_owner = owner
            row.lease_token = token
            row.lease_expires_at = expires
            row.attempts = int(row.attempts or 0) + 1
            row.updated_at = now
            # Clear prior backoff while actively resolving.
            row.next_attempt_at = None
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
        stamp = require_market_actuals_write(outcome).stamp_mapping()
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
            row.provenance_source = stamp["provenance_source"]
            row.actor_id = stamp["actor_id"]
            row.lease_owner = None
            row.lease_token = None
            row.lease_expires_at = None
            row.next_attempt_at = None
            row.retry_exhausted = False
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
        stamp = require_market_actuals_write(payload).stamp_mapping()
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
            row.provenance_source = stamp["provenance_source"]
            row.actor_id = stamp["actor_id"]
            row.lease_owner = None
            row.lease_token = None
            row.lease_expires_at = None
            # Optional retry controls may be carried in outcome for port compatibility
            # with A3 stores that only persist outcome_json.
            row.next_attempt_at = _parse_optional_datetime(payload.get("next_attempt_at"))
            row.retry_exhausted = bool(payload.get("retry_exhausted", False))
            return True, row.snapshot()

    def requeue_pending(
        self,
        *,
        prediction_id: str,
        as_of: Optional[datetime] = None,
    ) -> tuple[bool, Optional[MemoryPredictionRecord]]:
        canonical = str(prediction_id or "").strip()
        if not canonical:
            raise ValueError("prediction_id is required")
        now = as_of or self._clock()
        with self._lock:
            row = self._rows.get(canonical)
            if row is None:
                return False, None
            if row.status != STATUS_DATA_UNAVAILABLE:
                return False, row.snapshot()
            row.status = STATUS_PENDING
            row.outcome = None
            row.updated_at = now
            row.lease_owner = None
            row.lease_token = None
            row.lease_expires_at = None
            row.next_attempt_at = None
            row.retry_exhausted = False
            return True, row.snapshot()


def new_lease_token() -> str:
    return uuid.uuid4().hex
