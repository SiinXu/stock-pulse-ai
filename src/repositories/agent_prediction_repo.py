# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""SQLite-backed agent prediction store with CAS status transitions.

Issue #1112: concurrent claim/resolve must not overwrite a terminal row.
Provider failures use ``data_unavailable`` and remain re-claimable; never
fabricate hit/miss outcomes here.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError

from src.repositories.agent_prediction_tables import agent_predictions_table
from src.repositories.base import BaseRepository, RepositoryError
from src.schemas.agent_prediction import (
    AGENT_PREDICTION_STATUSES,
    CLAIMABLE_AGENT_PREDICTION_STATUSES,
    RESOLVABLE_AGENT_PREDICTION_STATUSES,
    STATUS_DATA_UNAVAILABLE,
    STATUS_PENDING,
    STATUS_RESOLVED,
    STATUS_RESOLVING,
    AgentPredictionInsert,
    AgentPredictionRecord,
)
from src.storage import DatabaseManager
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)


def _utc_naive_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, default=str)


def _json_loads(raw: Optional[str], *, default: Any) -> Any:
    if raw is None or raw == "":
        return default
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return default
    return parsed


def _is_unique_or_primary_key_conflict(exc: BaseException) -> bool:
    """Return True only for PK/UNIQUE collisions, not CHECK/NOT NULL failures."""
    message = str(exc).lower()
    if "check constraint failed" in message:
        return False
    if "not null constraint failed" in message:
        return False
    if "unique constraint failed" in message:
        return True
    if "primary key" in message:
        return True
    return False


class AgentPredictionRepository(BaseRepository):
    """Persist predictions and apply one-shot resolve transitions."""

    def __init__(
        self,
        db_manager: Optional[DatabaseManager] = None,
        *,
        clock: Callable[[], datetime] = _utc_naive_now,
    ) -> None:
        super().__init__(db_manager)
        self._clock = clock

    @staticmethod
    def _row_to_record(row: Any) -> AgentPredictionRecord:
        claims = _json_loads(row.claims_json, default=[])
        if not isinstance(claims, list):
            claims = []
        outcome = _json_loads(row.outcome_json, default=None)
        if outcome is not None and not isinstance(outcome, dict):
            outcome = {"value": outcome}
        model_meta = _json_loads(row.model_meta_json, default=None)
        if model_meta is not None and not isinstance(model_meta, dict):
            model_meta = {"value": model_meta}
        return AgentPredictionRecord(
            prediction_id=str(row.prediction_id),
            run_id=str(row.run_id),
            symbol=str(row.symbol),
            market=str(row.market),
            horizon=str(row.horizon),
            resolve_after=row.resolve_after,
            status=str(row.status),
            claims=claims,
            created_at=row.created_at,
            updated_at=row.updated_at,
            attempts=int(row.attempts or 0),
            lease_owner=row.lease_owner,
            lease_token=row.lease_token,
            lease_expires_at=row.lease_expires_at,
            outcome=outcome,
            model_meta=model_meta,
            resolved_at=row.resolved_at,
        )

    def insert_pending(
        self, fields: AgentPredictionInsert
    ) -> Tuple[bool, AgentPredictionRecord]:
        """Insert a row. Returns ``(created, record)``; never overwrites."""
        prediction_id = str(fields.prediction_id or "").strip()
        run_id = str(fields.run_id or "").strip()
        symbol = str(fields.symbol or "").strip()
        # Persistence normalizes market to lowercase so symbol/market indexes
        # and list filters share one canonical casing (A1 may send mixed case).
        market = str(fields.market or "").strip().lower()
        horizon = str(fields.horizon or "").strip()
        status = str(fields.status or STATUS_PENDING).strip()
        if not prediction_id or not run_id or not symbol or not market or not horizon:
            raise ValueError(
                "prediction_id, run_id, symbol, market, and horizon are required"
            )
        if len(prediction_id) > 128 or len(run_id) > 128:
            raise ValueError("prediction_id and run_id must be at most 128 characters")
        if len(symbol) > 32 or len(market) > 16 or len(horizon) > 32:
            raise ValueError("symbol/market/horizon exceed column width")
        if fields.resolve_after is None:
            raise ValueError("resolve_after is required")
        if not isinstance(fields.claims, list):
            raise ValueError("claims must be a list")
        if status not in AGENT_PREDICTION_STATUSES:
            raise ValueError(f"unsupported status: {status!r}")
        if status in {STATUS_RESOLVED}:
            raise ValueError("cannot insert a terminal resolved prediction")

        now = fields.created_at or self._clock()
        values = {
            "prediction_id": prediction_id,
            "run_id": run_id,
            "symbol": symbol,
            "market": market,
            "horizon": horizon,
            "resolve_after": fields.resolve_after,
            "status": status,
            "lease_owner": None,
            "lease_token": None,
            "lease_expires_at": None,
            "claims_json": _json_dumps(fields.claims),
            "outcome_json": None,
            "model_meta_json": (
                _json_dumps(dict(fields.model_meta))
                if fields.model_meta is not None
                else None
            ),
            "attempts": 0,
            "created_at": now,
            "updated_at": now,
            "resolved_at": None,
        }
        try:
            with self.db.get_session() as session:
                session.execute(agent_predictions_table.insert().values(**values))
                session.commit()
            created = self.get(prediction_id)
            if created is None:
                raise RepositoryError(
                    "agent prediction insert committed but row is missing",
                    error_code="agent_prediction_insert_missing",
                    context={"prediction_id": prediction_id},
                )
            return True, created
        except IntegrityError as exc:
            # Only PK/UNIQUE collisions are idempotent no-overwrite; CHECK and
            # NOT NULL failures must not be reported as "existing row" races.
            if not _is_unique_or_primary_key_conflict(exc):
                context = {"prediction_id": prediction_id}
                log_safe_exception(
                    logger,
                    "Agent prediction insert constraint failed",
                    exc,
                    error_code="agent_prediction_insert_constraint",
                    context=context,
                )
                raise RepositoryError(
                    "Agent prediction insert constraint failed",
                    error_code="agent_prediction_insert_constraint",
                    context=context,
                ) from exc
            existing = self.get(prediction_id)
            if existing is None:
                raise RepositoryError(
                    "agent prediction insert collided but row is missing",
                    error_code="agent_prediction_insert_race",
                    context={"prediction_id": prediction_id},
                )
            return False, existing
        except RepositoryError:
            raise
        except Exception as exc:  # broad-exception: fallback_recorded - surface as repository error
            context = {"prediction_id": prediction_id}
            log_safe_exception(
                logger,
                "Agent prediction insert failed",
                exc,
                error_code="agent_prediction_insert_failed",
                context=context,
            )
            raise RepositoryError(
                "Agent prediction insert failed",
                error_code="agent_prediction_insert_failed",
                context=context,
            ) from exc

    def get(self, prediction_id: str) -> Optional[AgentPredictionRecord]:
        canonical = str(prediction_id or "").strip()
        if not canonical:
            return None
        with self.db.get_session() as session:
            row = session.execute(
                select(agent_predictions_table)
                .where(agent_predictions_table.c.prediction_id == canonical)
                .limit(1)
            ).one_or_none()
        return self._row_to_record(row) if row is not None else None

    def list_due(
        self,
        *,
        as_of: Optional[datetime] = None,
        limit: int = 100,
        statuses: Optional[Sequence[str]] = None,
    ) -> List[AgentPredictionRecord]:
        """Return due rows using ``(status, resolve_after)`` index predicates."""
        now = as_of or self._clock()
        allowed = tuple(
            status
            for status in (statuses or (STATUS_PENDING, STATUS_DATA_UNAVAILABLE))
            if status in AGENT_PREDICTION_STATUSES
        )
        if not allowed:
            return []
        bound = max(1, min(int(limit), 1000))
        with self.db.get_session() as session:
            rows = session.execute(
                select(agent_predictions_table)
                .where(
                    agent_predictions_table.c.status.in_(allowed),
                    agent_predictions_table.c.resolve_after <= now,
                )
                .order_by(
                    agent_predictions_table.c.resolve_after.asc(),
                    agent_predictions_table.c.prediction_id.asc(),
                )
                .limit(bound)
            ).all()
        return [self._row_to_record(row) for row in rows]

    def list_by_symbol_market(
        self,
        *,
        symbol: str,
        market: str,
        limit: int = 50,
    ) -> List[AgentPredictionRecord]:
        """List predictions for a symbol/market using the composite index."""
        code = str(symbol or "").strip()
        mkt = str(market or "").strip().lower()
        if not code or not mkt:
            return []
        bound = max(1, min(int(limit), 500))
        with self.db.get_session() as session:
            rows = session.execute(
                select(agent_predictions_table)
                .where(
                    agent_predictions_table.c.symbol == code,
                    agent_predictions_table.c.market == mkt,
                )
                .order_by(
                    agent_predictions_table.c.created_at.desc(),
                    agent_predictions_table.c.prediction_id.desc(),
                )
                .limit(bound)
            ).all()
        return [self._row_to_record(row) for row in rows]

    def claim_for_resolve(
        self,
        *,
        prediction_id: str,
        lease_owner: str,
        lease_token: str,
        lease_ttl_seconds: int = 120,
        as_of: Optional[datetime] = None,
    ) -> Optional[AgentPredictionRecord]:
        """CAS claim a due prediction for resolution.

        Succeeds when the row is claimable, or when an existing ``resolving``
        lease has expired. Concurrent claims race on ``rowcount``.
        """
        canonical = str(prediction_id or "").strip()
        owner = str(lease_owner or "").strip()
        token = str(lease_token or "").strip()
        if not canonical or not owner or not token:
            raise ValueError("prediction_id, lease_owner, and lease_token are required")
        now = as_of or self._clock()
        ttl = max(1, int(lease_ttl_seconds))
        expires = now + timedelta(seconds=ttl)
        try:
            with self.db.get_session() as session:
                result = session.execute(
                    update(agent_predictions_table)
                    .where(
                        agent_predictions_table.c.prediction_id == canonical,
                        or_(
                            agent_predictions_table.c.status.in_(
                                tuple(CLAIMABLE_AGENT_PREDICTION_STATUSES)
                            ),
                            and_(
                                agent_predictions_table.c.status == STATUS_RESOLVING,
                                or_(
                                    agent_predictions_table.c.lease_expires_at.is_(
                                        None
                                    ),
                                    agent_predictions_table.c.lease_expires_at <= now,
                                ),
                            ),
                        ),
                    )
                    .values(
                        status=STATUS_RESOLVING,
                        lease_owner=owner,
                        lease_token=token,
                        lease_expires_at=expires,
                        attempts=agent_predictions_table.c.attempts + 1,
                        updated_at=now,
                    )
                )
                if int(result.rowcount or 0) != 1:
                    session.rollback()
                    return None
                session.commit()
        except Exception as exc:  # broad-exception: fallback_recorded - surface as repository error
            context = {"prediction_id": canonical}
            log_safe_exception(
                logger,
                "Agent prediction claim failed",
                exc,
                error_code="agent_prediction_claim_failed",
                context=context,
            )
            raise RepositoryError(
                "Agent prediction claim failed",
                error_code="agent_prediction_claim_failed",
                context=context,
            ) from exc
        return self.get(canonical)

    def resolve(
        self,
        *,
        prediction_id: str,
        outcome: Mapping[str, Any],
        expected_lease_token: Optional[str] = None,
        as_of: Optional[datetime] = None,
    ) -> Tuple[bool, Optional[AgentPredictionRecord]]:
        """One-shot resolve: ``pending|resolving`` → ``resolved`` only once.

        Returns ``(applied, record)``. Concurrent winners see ``applied=False``
        and the terminal row that already won.

        Callers that previously claimed the row via :meth:`claim_for_resolve`
        **should always pass** ``expected_lease_token`` so another worker cannot
        complete the resolve without the lease. Omitting the token still uses
        status CAS (terminal write happens at most once) but does not bind the
        writer to a specific lease holder.
        """
        canonical = str(prediction_id or "").strip()
        if not canonical:
            raise ValueError("prediction_id is required")
        if not isinstance(outcome, Mapping):
            raise ValueError("outcome must be a mapping")
        now = as_of or self._clock()
        conditions = [
            agent_predictions_table.c.prediction_id == canonical,
            agent_predictions_table.c.status.in_(
                tuple(RESOLVABLE_AGENT_PREDICTION_STATUSES)
            ),
        ]
        if expected_lease_token is not None:
            conditions.append(
                agent_predictions_table.c.lease_token == str(expected_lease_token)
            )
        try:
            with self.db.get_session() as session:
                result = session.execute(
                    update(agent_predictions_table)
                    .where(and_(*conditions))
                    .values(
                        status=STATUS_RESOLVED,
                        outcome_json=_json_dumps(dict(outcome)),
                        resolved_at=now,
                        updated_at=now,
                        lease_owner=None,
                        lease_token=None,
                        lease_expires_at=None,
                    )
                )
                applied = int(result.rowcount or 0) == 1
                if applied:
                    session.commit()
                else:
                    session.rollback()
        except Exception as exc:  # broad-exception: fallback_recorded - surface as repository error
            message = str(exc).lower()
            if "resolved agent_predictions are immutable" in message:
                return False, self.get(canonical)
            context = {"prediction_id": canonical}
            log_safe_exception(
                logger,
                "Agent prediction resolve failed",
                exc,
                error_code="agent_prediction_resolve_failed",
                context=context,
            )
            raise RepositoryError(
                "Agent prediction resolve failed",
                error_code="agent_prediction_resolve_failed",
                context=context,
            ) from exc
        return applied, self.get(canonical)

    def mark_data_unavailable(
        self,
        *,
        prediction_id: str,
        reason: str,
        expected_lease_token: Optional[str] = None,
        as_of: Optional[datetime] = None,
        outcome: Optional[Mapping[str, Any]] = None,
    ) -> Tuple[bool, Optional[AgentPredictionRecord]]:
        """CAS ``resolving`` → ``data_unavailable`` for provider failures."""
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
        conditions = [
            agent_predictions_table.c.prediction_id == canonical,
            agent_predictions_table.c.status == STATUS_RESOLVING,
        ]
        if expected_lease_token is not None:
            conditions.append(
                agent_predictions_table.c.lease_token == str(expected_lease_token)
            )
        try:
            with self.db.get_session() as session:
                result = session.execute(
                    update(agent_predictions_table)
                    .where(and_(*conditions))
                    .values(
                        status=STATUS_DATA_UNAVAILABLE,
                        outcome_json=_json_dumps(payload),
                        updated_at=now,
                        lease_owner=None,
                        lease_token=None,
                        lease_expires_at=None,
                    )
                )
                applied = int(result.rowcount or 0) == 1
                if applied:
                    session.commit()
                else:
                    session.rollback()
        except Exception as exc:  # broad-exception: fallback_recorded - surface as repository error
            message = str(exc).lower()
            if "resolved agent_predictions are immutable" in message:
                return False, self.get(canonical)
            context = {"prediction_id": canonical}
            log_safe_exception(
                logger,
                "Agent prediction data_unavailable mark failed",
                exc,
                error_code="agent_prediction_data_unavailable_failed",
                context=context,
            )
            raise RepositoryError(
                "Agent prediction data_unavailable mark failed",
                error_code="agent_prediction_data_unavailable_failed",
                context=context,
            ) from exc
        return applied, self.get(canonical)

    def requeue_pending(
        self,
        *,
        prediction_id: str,
        as_of: Optional[datetime] = None,
    ) -> Tuple[bool, Optional[AgentPredictionRecord]]:
        """Move ``data_unavailable`` back to ``pending`` for a later due scan."""
        canonical = str(prediction_id or "").strip()
        if not canonical:
            raise ValueError("prediction_id is required")
        now = as_of or self._clock()
        try:
            with self.db.get_session() as session:
                result = session.execute(
                    update(agent_predictions_table)
                    .where(
                        agent_predictions_table.c.prediction_id == canonical,
                        agent_predictions_table.c.status == STATUS_DATA_UNAVAILABLE,
                    )
                    .values(
                        status=STATUS_PENDING,
                        updated_at=now,
                        lease_owner=None,
                        lease_token=None,
                        lease_expires_at=None,
                    )
                )
                applied = int(result.rowcount or 0) == 1
                if applied:
                    session.commit()
                else:
                    session.rollback()
        except Exception as exc:  # broad-exception: fallback_recorded - surface as repository error
            context = {"prediction_id": canonical}
            log_safe_exception(
                logger,
                "Agent prediction requeue failed",
                exc,
                error_code="agent_prediction_requeue_failed",
                context=context,
            )
            raise RepositoryError(
                "Agent prediction requeue failed",
                error_code="agent_prediction_requeue_failed",
                context=context,
            ) from exc
        return applied, self.get(canonical)
