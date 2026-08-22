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
from datetime import date, datetime, timedelta, timezone
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Type,
    get_args,
)

from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError

from src.repositories.agent_prediction_tables import agent_predictions_table
from src.repositories.base import BaseRepository, RepositoryError
from src.schemas.agent_prediction import (
    AGENT_PREDICTION_STATUSES,
    CLAIMABLE_AGENT_PREDICTION_STATUSES,
    STATUS_DATA_UNAVAILABLE,
    STATUS_PENDING,
    STATUS_RESOLVED,
    STATUS_RESOLVING,
    AgentPredictionInsert,
    AgentPredictionRecord,
)
from src.schemas.memory_fact_opinion import lock_prediction_outcome_actuals
from src.schemas.memory_provenance import (
    PROVENANCE_SOURCE_SYSTEM_RESOLVE,
    reject_client_provenance_keys,
    stamp_memory_provenance,
)
from src.schemas.prediction_record import (
    NoVerifiableReason,
    PREDICTION_HORIZON_TOKENS,
    PredictionClaim,
    PredictionModelMeta,
)
from src.storage import DatabaseManager
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

_NO_VERIFIABLE_REASONS = frozenset(get_args(NoVerifiableReason))


def _utc_naive_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def _json_loads(
    raw: Optional[str],
    *,
    field: str,
    expected_type: Type[Any],
    allow_none: bool = False,
) -> Any:
    """Load persisted JSON without turning corruption into valid empty data."""
    if raw is None or raw == "":
        if allow_none:
            return None
        raise RepositoryError(
            f"Agent prediction {field} JSON is missing",
            error_code="agent_prediction_corrupt_json",
            context={"field": field},
        )
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise RepositoryError(
            f"Agent prediction {field} JSON is invalid",
            error_code="agent_prediction_corrupt_json",
            context={"field": field},
        ) from exc
    if not isinstance(parsed, expected_type):
        raise RepositoryError(
            f"Agent prediction {field} JSON has the wrong shape",
            error_code="agent_prediction_corrupt_json",
            context={"field": field},
        )
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
        claims = _json_loads(
            row.claims_json,
            field="claims",
            expected_type=list,
        )
        outcome = _json_loads(
            row.outcome_json,
            field="outcome",
            expected_type=dict,
            allow_none=True,
        )
        model_meta = _json_loads(
            row.model_meta_json,
            field="model_meta",
            expected_type=dict,
            allow_none=True,
        )
        return AgentPredictionRecord(
            prediction_id=str(row.prediction_id),
            run_id=str(row.run_id),
            symbol=str(row.symbol),
            market=str(row.market),
            as_of=row.as_of,
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
            source_decision_id=row.source_decision_id,
            no_verifiable_reason=row.no_verifiable_reason,
            notes=row.notes,
            resolved_at=row.resolved_at,
            provenance_source=row.provenance_source,
            actor_id=row.actor_id,
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
        if any(
            char.isspace()
            for value in (prediction_id, run_id, symbol, market)
            for char in value
        ):
            raise ValueError("prediction identifiers must not contain whitespace")
        if len(prediction_id) > 128 or len(run_id) > 128:
            raise ValueError("prediction_id and run_id must be at most 128 characters")
        if len(symbol) > 32 or len(market) > 16 or len(horizon) > 32:
            raise ValueError("symbol/market/horizon exceed column width")
        if horizon not in PREDICTION_HORIZON_TOKENS:
            raise ValueError(f"unsupported horizon: {horizon!r}")
        if not isinstance(fields.as_of, date) or isinstance(fields.as_of, datetime):
            raise ValueError("as_of must be a date")
        if not isinstance(fields.resolve_after, datetime):
            raise ValueError("resolve_after must be a datetime")
        if not isinstance(fields.claims, list):
            raise ValueError("claims must be a list")
        if len(fields.claims) > 32:
            raise ValueError("claims must contain at most 32 entries")
        if status not in AGENT_PREDICTION_STATUSES:
            raise ValueError(f"unsupported status: {status!r}")
        if status in {STATUS_RESOLVING, STATUS_RESOLVED, STATUS_DATA_UNAVAILABLE}:
            raise ValueError(f"cannot insert lifecycle status {status!r} directly")

        try:
            claims = [
                PredictionClaim.model_validate(claim).model_dump(mode="json")
                for claim in fields.claims
            ]
        except (TypeError, ValueError) as exc:
            raise ValueError("claims must conform to the A1 PredictionClaim contract") from exc
        claim_ids = [claim["claim_id"] for claim in claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("claim_id values must be unique")
        if status == STATUS_PENDING and not claims:
            raise ValueError("pending predictions require at least one typed claim")
        if status == "no_verifiable_claim":
            if claims:
                raise ValueError("no_verifiable_claim predictions must not carry claims")
            if not str(fields.no_verifiable_reason or "").strip():
                raise ValueError("no_verifiable_claim requires no_verifiable_reason")
        elif fields.no_verifiable_reason is not None:
            raise ValueError(
                "no_verifiable_reason is only valid for no_verifiable_claim"
            )

        source_decision_id = str(fields.source_decision_id or "").strip() or None
        no_verifiable_reason = (
            str(fields.no_verifiable_reason or "").strip() or None
        )
        notes = str(fields.notes) if fields.notes is not None else None
        if source_decision_id is not None and len(source_decision_id) > 128:
            raise ValueError("source_decision_id must be at most 128 characters")
        if source_decision_id is not None and any(
            char.isspace() for char in source_decision_id
        ):
            raise ValueError("source_decision_id must not contain whitespace")
        if no_verifiable_reason is not None and len(no_verifiable_reason) > 64:
            raise ValueError("no_verifiable_reason must be at most 64 characters")
        if (
            no_verifiable_reason is not None
            and no_verifiable_reason not in _NO_VERIFIABLE_REASONS
        ):
            raise ValueError("unsupported no_verifiable_reason")
        if notes is not None and len(notes) > 500:
            raise ValueError("notes must be at most 500 characters")

        model_meta = None
        if fields.model_meta is not None:
            try:
                model_meta = PredictionModelMeta.model_validate(
                    dict(fields.model_meta)
                ).model_dump(mode="json")
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "model_meta must conform to the A1 PredictionModelMeta contract"
                ) from exc

        now = fields.created_at or self._clock()
        if not isinstance(now, datetime):
            raise ValueError("created_at must be a datetime")
        values = {
            "prediction_id": prediction_id,
            "run_id": run_id,
            "symbol": symbol,
            "market": market,
            "as_of": fields.as_of,
            "horizon": horizon,
            "resolve_after": fields.resolve_after,
            "status": status,
            "lease_owner": None,
            "lease_token": None,
            "lease_expires_at": None,
            "claims_json": _json_dumps(claims),
            "outcome_json": None,
            "model_meta_json": (
                _json_dumps(model_meta) if model_meta is not None else None
            ),
            "source_decision_id": source_decision_id,
            "no_verifiable_reason": no_verifiable_reason,
            "notes": notes,
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
            for status in (statuses or (STATUS_PENDING,))
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
        if len(owner) > 128 or len(token) > 64:
            raise ValueError("lease_owner/lease_token exceed column width")
        now = as_of or self._clock()
        ttl = max(1, int(lease_ttl_seconds))
        expires = now + timedelta(seconds=ttl)
        try:
            with self.db.get_session() as session:
                result = session.execute(
                    update(agent_predictions_table)
                    .where(
                        agent_predictions_table.c.prediction_id == canonical,
                        agent_predictions_table.c.resolve_after <= now,
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
        lock_prediction_outcome_actuals(outcome)
        reject_client_provenance_keys(outcome)
        stamp = stamp_memory_provenance(
            provenance_source=PROVENANCE_SOURCE_SYSTEM_RESOLVE,
            actor_id=None,
        )
        now = as_of or self._clock()
        token = str(expected_lease_token or "").strip() or None
        if token is not None and len(token) > 64:
            raise ValueError("expected_lease_token exceeds column width")
        # Direct pending resolution is allowed for synchronous callers. Once a
        # row is claimed, only the live lease holder may complete it.
        transition = agent_predictions_table.c.status == STATUS_PENDING
        if token is not None:
            transition = and_(
                agent_predictions_table.c.status == STATUS_RESOLVING,
                agent_predictions_table.c.lease_token == token,
                agent_predictions_table.c.lease_expires_at > now,
            )
        conditions = [
            agent_predictions_table.c.prediction_id == canonical,
            transition,
        ]
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
                        provenance_source=stamp["provenance_source"],
                        actor_id=stamp["actor_id"],
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
        token = str(expected_lease_token or "").strip()
        if not token:
            raise ValueError("expected_lease_token is required")
        if len(token) > 64:
            raise ValueError("expected_lease_token exceeds column width")
        now = as_of or self._clock()
        payload: Dict[str, Any] = {}
        if outcome:
            payload.update(dict(outcome))
        # Provider failures are never scoreable. Callers cannot smuggle a hit,
        # miss, or numeric score through the diagnostic extension mapping.
        for reserved in ("label", "score", "hit", "is_hit", "miss"):
            payload.pop(reserved, None)
        payload.update(
            {
                "label": STATUS_DATA_UNAVAILABLE,
                "reason": str(reason or "data_unavailable"),
            }
        )
        lock_prediction_outcome_actuals(payload)
        reject_client_provenance_keys(payload)
        stamp = stamp_memory_provenance(
            provenance_source=PROVENANCE_SOURCE_SYSTEM_RESOLVE,
            actor_id=None,
        )
        conditions = [
            agent_predictions_table.c.prediction_id == canonical,
            agent_predictions_table.c.status == STATUS_RESOLVING,
            agent_predictions_table.c.lease_token == token,
            agent_predictions_table.c.lease_expires_at > now,
        ]
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
                        provenance_source=stamp["provenance_source"],
                        actor_id=stamp["actor_id"],
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
                        outcome_json=None,
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
