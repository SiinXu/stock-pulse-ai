# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""SQLite store for principal-scoped layered memory observations (Issue #1118).

This repository is the durable authority for ``PrincipalMemoryLifecycle``
observation rows, consent, and append-only access audit. It is not
``agent_episodes``, not EvolutionEvent, not a semantic-fact table, and not a
procedural-weight store. User HTTP CRUD and prompt injection are out of slice.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from src.agent.memory_layers import (
    MemoryObservation,
    parse_instant,
    validate_principal_id,
)
from src.agent.memory_retrieval import AuthorizedMemoryProjector
from src.agent.memory_governance import MemoryAuditEvent
from src.repositories.base import BaseRepository, RepositoryError
from src.repositories.layered_memory_tables import (
    layered_memory_access_audit_table,
    layered_memory_consent_table,
    layered_memory_observations_table,
)
from src.storage import DatabaseManager


logger = logging.getLogger(__name__)

LAYERED_MEMORY_OBSERVATION_SCHEMA_VERSION = "layered-memory-observation-v1"

_obs = layered_memory_observations_table
_consent = layered_memory_consent_table
_audit = layered_memory_access_audit_table


def _utc_naive_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _as_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _iso_to_naive(name: str, value: Optional[str]) -> Optional[datetime]:
    if value is None:
        return None
    return parse_instant(name, value).replace(tzinfo=None)


def _naive_to_iso(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise ValueError("timestamp must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _bool_or_none(value: Any) -> Optional[bool]:
    if value is None:
        return None
    if type(value) is bool:
        return value
    if value in (0, 1):
        return bool(value)
    raise ValueError("was_correct must be a boolean")


class LayeredMemoryRepository(BaseRepository):
    """Persist, list, delete, clear, expire, and project layered observations."""

    def __init__(
        self,
        db_manager: Optional[DatabaseManager] = None,
        *,
        clock: Callable[[], datetime] = _utc_naive_now,
    ) -> None:
        super().__init__(db_manager)
        self._clock = clock

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is not None and now.utcoffset() is not None:
            return now.astimezone(timezone.utc).replace(tzinfo=None)
        return now

    @staticmethod
    def _row_to_observation(row: Any) -> MemoryObservation:
        return MemoryObservation(
            principal_id=str(row.principal_id),
            analysis_history_id=int(row.analysis_history_id),
            stock_code=str(row.stock_code),
            observed_at=_naive_to_iso(row.observed_at) or "",
            expires_at=_naive_to_iso(row.expires_at),
            signal=str(row.signal),
            sentiment_score=float(row.sentiment_score),
            price_at_analysis=float(row.price_at_analysis),
            outcome_id=None if row.outcome_id is None else int(row.outcome_id),
            outcome_horizon_days=(
                None if row.outcome_horizon_days is None else int(row.outcome_horizon_days)
            ),
            evaluated_at=_naive_to_iso(row.evaluated_at),
            was_correct=_bool_or_none(row.was_correct),
            provenance_source=str(row.provenance_source),
            actor_id=None if row.actor_id is None else str(row.actor_id),
        )

    @staticmethod
    def _row_to_audit(row: Any) -> MemoryAuditEvent:
        return MemoryAuditEvent(
            event_id=str(row.event_id),
            principal_id=str(row.principal_id),
            action=str(row.action),
            at=_naive_to_iso(row.at) or "",
            detail="" if row.detail is None else str(row.detail),
            resource_count=int(row.resource_count or 0),
        )

    def upsert_observation(self, observation: MemoryObservation) -> MemoryObservation:
        if not observation.provenance_source:
            raise RepositoryError(
                "layered observation persist requires provenance_source",
                error_code="layered_memory_missing_provenance",
            )
        now = self._now()
        values = {
            "schema_version": LAYERED_MEMORY_OBSERVATION_SCHEMA_VERSION,
            "principal_id": observation.principal_id,
            "analysis_history_id": observation.analysis_history_id,
            "stock_code": observation.stock_code,
            "observed_at": _iso_to_naive("observed_at", observation.observed_at),
            "expires_at": _iso_to_naive("expires_at", observation.expires_at),
            "signal": observation.signal,
            "sentiment_score": float(observation.sentiment_score),
            "price_at_analysis": float(observation.price_at_analysis),
            "outcome_id": observation.outcome_id,
            "outcome_horizon_days": observation.outcome_horizon_days,
            "evaluated_at": _iso_to_naive("evaluated_at", observation.evaluated_at),
            "was_correct": observation.was_correct,
            "provenance_source": observation.provenance_source,
            "actor_id": observation.actor_id,
            "created_at": now,
            "updated_at": now,
        }
        insert_stmt = sqlite_insert(_obs).values(**values)
        upsert_stmt = insert_stmt.on_conflict_do_update(
            index_elements=["principal_id", "analysis_history_id"],
            set_={
                "schema_version": insert_stmt.excluded.schema_version,
                "stock_code": insert_stmt.excluded.stock_code,
                "observed_at": insert_stmt.excluded.observed_at,
                "expires_at": insert_stmt.excluded.expires_at,
                "signal": insert_stmt.excluded.signal,
                "sentiment_score": insert_stmt.excluded.sentiment_score,
                "price_at_analysis": insert_stmt.excluded.price_at_analysis,
                "outcome_id": insert_stmt.excluded.outcome_id,
                "outcome_horizon_days": insert_stmt.excluded.outcome_horizon_days,
                "evaluated_at": insert_stmt.excluded.evaluated_at,
                "was_correct": insert_stmt.excluded.was_correct,
                "provenance_source": insert_stmt.excluded.provenance_source,
                "actor_id": insert_stmt.excluded.actor_id,
                "updated_at": insert_stmt.excluded.updated_at,
            },
        )
        try:
            with self.db.get_session() as session:
                session.execute(upsert_stmt)
                session.commit()
        except IntegrityError as exc:
            self._log_and_raise(
                logger,
                "layered_memory_upsert_conflict",
                exc,
                error_code="layered_memory_upsert_conflict",
                context={
                    "principal_id": observation.principal_id,
                    "analysis_history_id": observation.analysis_history_id,
                },
            )
        except SQLAlchemyError as exc:
            self._log_and_raise(
                logger,
                "layered_memory_upsert_failed",
                exc,
                error_code="layered_memory_upsert_failed",
                context={"principal_id": observation.principal_id},
            )
        stored = self.get_observation(
            observation.principal_id, observation.analysis_history_id
        )
        if stored is None:
            raise RepositoryError(
                "layered observation upsert committed but row is missing",
                error_code="layered_memory_upsert_missing",
                context={
                    "principal_id": observation.principal_id,
                    "analysis_history_id": observation.analysis_history_id,
                },
            )
        return stored

    def get_observation(
        self,
        principal_id: str,
        analysis_history_id: int,
    ) -> Optional[MemoryObservation]:
        validate_principal_id(principal_id)
        if type(analysis_history_id) is not int or analysis_history_id <= 0:
            raise ValueError("analysis_history_id must be a positive int")
        with self.db.get_session() as session:
            row = session.execute(
                select(_obs)
                .where(
                    _obs.c.principal_id == principal_id,
                    _obs.c.analysis_history_id == analysis_history_id,
                )
                .limit(1)
            ).first()
        return self._row_to_observation(row) if row is not None else None

    def count_records(self, principal_id: str) -> int:
        validate_principal_id(principal_id)
        with self.db.get_session() as session:
            total = session.execute(
                select(func.count(_obs.c.id))
                .where(_obs.c.principal_id == principal_id)
            ).scalar()
        return int(total or 0)

    def list_records(
        self,
        principal_id: str,
        *,
        as_of: Optional[str] = None,
    ) -> List[MemoryObservation]:
        validate_principal_id(principal_id)
        if as_of is not None:
            parse_instant("as_of", as_of)
        with self.db.get_session() as session:
            rows = session.execute(
                select(_obs)
                .where(_obs.c.principal_id == principal_id)
                .order_by(_obs.c.observed_at.desc(), _obs.c.analysis_history_id.desc())
            ).all()
        records = [self._row_to_observation(row) for row in rows]
        if as_of is None:
            return records
        cutoff = parse_instant("as_of", as_of)
        visible: List[MemoryObservation] = []
        for record in records:
            if parse_instant("observed_at", record.observed_at) > cutoff:
                continue
            if record.expires_at is not None and parse_instant("expires_at", record.expires_at) <= cutoff:
                continue
            visible.append(record)
        return visible

    def delete(self, principal_id: str, analysis_history_id: int) -> bool:
        validate_principal_id(principal_id)
        if type(analysis_history_id) is not int or analysis_history_id <= 0:
            raise ValueError("analysis_history_id must be a positive int")
        with self.db.get_session() as session:
            result = session.execute(
                delete(_obs).where(
                    _obs.c.principal_id == principal_id,
                    _obs.c.analysis_history_id == analysis_history_id,
                )
            )
            session.commit()
            return int(result.rowcount or 0) > 0

    def clear(self, principal_id: str) -> int:
        validate_principal_id(principal_id)
        with self.db.get_session() as session:
            result = session.execute(
                delete(_obs).where(_obs.c.principal_id == principal_id)
            )
            session.commit()
            return int(result.rowcount or 0)

    def expire_due(
        self,
        *,
        now: str,
        principal_id: Optional[str] = None,
    ) -> Dict[str, int]:
        now_dt = _iso_to_naive("now", now)
        if now_dt is None:
            raise ValueError("now is required")
        conditions = [_obs.c.expires_at.is_not(None), _obs.c.expires_at <= now_dt]
        if principal_id is not None:
            validate_principal_id(principal_id)
            conditions.append(_obs.c.principal_id == principal_id)
        with self.db.get_session() as session:
            expired_rows = session.execute(
                select(_obs.c.principal_id, func.count(_obs.c.id))
                .where(*conditions)
                .group_by(_obs.c.principal_id)
            ).all()
            counts = {str(row[0]): int(row[1]) for row in expired_rows if int(row[1]) > 0}
            if counts:
                session.execute(delete(_obs).where(*conditions))
                session.commit()
        return counts

    def has_consent(self, principal_id: str) -> bool:
        validate_principal_id(principal_id)
        with self.db.get_session() as session:
            row = session.execute(
                select(_consent.c.principal_id)
                .where(_consent.c.principal_id == principal_id)
                .limit(1)
            ).first()
        return row is not None

    def grant_consent(self, principal_id: str, granted_at: str) -> None:
        validate_principal_id(principal_id)
        granted = _iso_to_naive("granted_at", granted_at)
        now = self._now()
        insert_stmt = sqlite_insert(_consent).values(
            principal_id=principal_id,
            granted_at=granted,
            created_at=now,
            updated_at=now,
        )
        upsert_stmt = insert_stmt.on_conflict_do_update(
            index_elements=["principal_id"],
            set_={
                "granted_at": insert_stmt.excluded.granted_at,
                "updated_at": insert_stmt.excluded.updated_at,
            },
        )
        with self.db.get_session() as session:
            session.execute(upsert_stmt)
            session.commit()

    def revoke_consent(self, principal_id: str) -> None:
        validate_principal_id(principal_id)
        with self.db.get_session() as session:
            session.execute(delete(_consent).where(_consent.c.principal_id == principal_id))
            session.commit()

    def append_audit(self, event: MemoryAuditEvent) -> MemoryAuditEvent:
        values = {
            "event_id": event.event_id,
            "principal_id": event.principal_id,
            "action": event.action,
            "at": _iso_to_naive("at", event.at),
            "detail": event.detail,
            "resource_count": event.resource_count,
            "created_at": self._now(),
        }
        try:
            with self.db.get_session() as session:
                session.execute(_audit.insert().values(**values))
                session.commit()
        except IntegrityError as exc:
            self._log_and_raise(
                logger,
                "layered_memory_audit_conflict",
                exc,
                error_code="layered_memory_audit_conflict",
                context={"event_id": event.event_id},
            )
        return event

    def list_audit(self, principal_id: str) -> List[MemoryAuditEvent]:
        validate_principal_id(principal_id)
        with self.db.get_session() as session:
            rows = session.execute(
                select(_audit)
                .where(_audit.c.principal_id == principal_id)
                .order_by(_audit.c.at.asc(), _audit.c.id.asc())
            ).all()
        return [self._row_to_audit(row) for row in rows]

    def project(
        self,
        principal_id: str,
        *,
        stock_code: str,
        as_of: str,
        query: str = "",
        vector_enabled: bool = False,
    ):
        records = self.list_records(principal_id, as_of=as_of)
        projector = AuthorizedMemoryProjector(
            records,
            principal_id=principal_id,
            as_of=as_of,
            vector_enabled=vector_enabled,
        )
        return projector.retrieve_layered(stock_code=stock_code, query=query)


class DurableLayeredMemoryStore:
    """``PrincipalMemoryLifecycle`` store backed by ``LayeredMemoryRepository``."""

    def __init__(self, repository: LayeredMemoryRepository) -> None:
        self._repo = repository

    def has_consent(self, principal_id: str) -> bool:
        return self._repo.has_consent(principal_id)

    def grant_consent(self, principal_id: str, granted_at: str) -> None:
        self._repo.grant_consent(principal_id, granted_at)

    def revoke_consent(self, principal_id: str) -> None:
        self._repo.revoke_consent(principal_id)

    def upsert_observation(self, observation: MemoryObservation) -> MemoryObservation:
        return self._repo.upsert_observation(observation)

    def contains(self, principal_id: str, analysis_history_id: int) -> bool:
        return self._repo.get_observation(principal_id, analysis_history_id) is not None

    def count_records(self, principal_id: str) -> int:
        return self._repo.count_records(principal_id)

    def list_records(self, principal_id: str) -> List[MemoryObservation]:
        return self._repo.list_records(principal_id)

    def delete(self, principal_id: str, analysis_history_id: int) -> bool:
        return self._repo.delete(principal_id, analysis_history_id)

    def clear(self, principal_id: str) -> int:
        return self._repo.clear(principal_id)

    def drop_expired(self, principal_id: str, now_iso: str) -> int:
        counts = self._repo.expire_due(now=now_iso, principal_id=principal_id)
        return int(counts.get(principal_id, 0))

    def expire_all_due(self, now_iso: str) -> Dict[str, int]:
        return self._repo.expire_due(now=now_iso)

    def record_audit(self, event: MemoryAuditEvent) -> MemoryAuditEvent:
        return self._repo.append_audit(event)

    def list_audit(self, principal_id: str) -> List[MemoryAuditEvent]:
        return self._repo.list_audit(principal_id)

    def project(
        self,
        principal_id: str,
        *,
        stock_code: str,
        as_of: str,
        query: str = "",
        vector_enabled: bool = False,
    ):
        return self._repo.project(
            principal_id,
            stock_code=stock_code,
            as_of=as_of,
            query=query,
            vector_enabled=vector_enabled,
        )
