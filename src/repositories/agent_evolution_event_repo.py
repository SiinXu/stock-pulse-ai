# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Append-only SQLite store for EvolutionEvent rows (Issue #1113).

This repository is the only persistence boundary for ``agent_evolution_events``.
Public methods are ``append`` and ``list_events``. ``insert_evolution_event_on_session``
writes on a caller-owned session so irreversible episode deletes can audit in
the same transaction. There is no update/delete API; SQLite triggers are the
immutability authority. Query misses return an empty list. This module does
not reuse ``security_audit_events``, curator-grade sidecars, episode rows, or
resolver process logs.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from typing import Any, Callable, List, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.repositories.agent_evolution_event_tables import agent_evolution_events_table
from src.repositories.base import BaseRepository, RepositoryError
from src.schemas.evolution_event import (
    EVOLUTION_EVENT_SCHEMA_VERSION,
    EvolutionEvent,
    EvolutionEventCreate,
    EvolutionEventReasonRefs,
    normalize_optional_event_type,
    validate_query_limit,
    validate_query_window,
)
from src.storage import DatabaseManager


logger = logging.getLogger(__name__)


def _utc_naive_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _json_dumps(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _as_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _as_utc_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def evolution_event_row_values(
    event: EvolutionEventCreate,
    *,
    created_at: datetime,
) -> dict[str, Any]:
    payload = (
        event
        if isinstance(event, EvolutionEventCreate)
        else EvolutionEventCreate.model_validate(event)
    )
    return {
        "schema_version": payload.schema_version or EVOLUTION_EVENT_SCHEMA_VERSION,
        "event_id": payload.event_id,
        "occurred_at": _as_utc_naive(payload.occurred_at),
        "event_type": payload.event_type,
        "actor": payload.actor,
        "reason_refs_json": _json_dumps(payload.reason_refs.model_dump(mode="python")),
        "before_json": _json_dumps(payload.before),
        "after_json": _json_dumps(payload.after),
        "created_at": created_at,
    }


def insert_evolution_event_on_session(
    session: Any,
    event: EvolutionEventCreate,
    *,
    created_at: datetime,
) -> str:
    """Insert one EvolutionEvent on a caller-owned session. Does not commit.

    Used so irreversible episode deletes can audit in the same transaction.
    Validation/insert failure must propagate so the caller can roll back.
    """
    payload = (
        event
        if isinstance(event, EvolutionEventCreate)
        else EvolutionEventCreate.model_validate(event)
    )
    session.execute(
        agent_evolution_events_table.insert().values(
            **evolution_event_row_values(payload, created_at=created_at)
        )
    )
    return str(payload.event_id)


class AgentEvolutionEventRepository(BaseRepository):
    """Persist and query append-only EvolutionEvent rows."""

    def __init__(
        self,
        db_manager: Optional[DatabaseManager] = None,
        *,
        clock: Callable[[], datetime] = _utc_naive_now,
    ) -> None:
        super().__init__(db_manager)
        self._clock = clock

    @staticmethod
    def _row_to_event(row: Any) -> EvolutionEvent:
        reason_refs = json.loads(row.reason_refs_json)
        before = json.loads(row.before_json)
        after = json.loads(row.after_json)
        if not isinstance(reason_refs, dict) or not isinstance(before, dict) or not isinstance(after, dict):
            raise RepositoryError(
                "evolution event JSON has the wrong shape",
                error_code="evolution_event_corrupt_json",
                context={"event_id": str(row.event_id)},
            )
        return EvolutionEvent.model_validate(
            {
                "id": int(row.id),
                "schema_version": str(row.schema_version),
                "event_id": str(row.event_id),
                "occurred_at": _as_utc_aware(row.occurred_at),
                "event_type": str(row.event_type),
                "actor": str(row.actor),
                "reason_refs": EvolutionEventReasonRefs.model_validate(reason_refs),
                "before": before,
                "after": after,
            }
        )

    def append(self, event: EvolutionEventCreate) -> EvolutionEvent:
        payload = (
            event
            if isinstance(event, EvolutionEventCreate)
            else EvolutionEventCreate.model_validate(event)
        )
        now = self._clock()
        if now.tzinfo is not None and now.utcoffset() is not None:
            created_at = now.astimezone(timezone.utc).replace(tzinfo=None)
        else:
            created_at = now
        try:
            with self.db.get_session() as session:
                result = session.execute(
                    agent_evolution_events_table.insert().values(
                        **evolution_event_row_values(payload, created_at=created_at)
                    )
                )
                session.flush()
                row_id = int(result.inserted_primary_key[0])
                session.commit()
        except IntegrityError as exc:
            self._log_and_raise(
                logger,
                "evolution_event_append_conflict",
                exc,
                error_code="evolution_event_append_conflict",
                context={"event_id": payload.event_id, "event_type": payload.event_type},
            )
        stored = self._load_by_event_id(payload.event_id)
        if stored is None:
            raise RepositoryError(
                "evolution event insert committed but row is missing",
                error_code="evolution_event_insert_missing",
                context={"event_id": payload.event_id, "row_id": row_id},
            )
        return stored

    def _load_by_event_id(self, event_id: str) -> Optional[EvolutionEvent]:
        key = str(event_id or "").strip()
        if not key:
            return None
        with self.db.get_session() as session:
            row = session.execute(
                select(agent_evolution_events_table)
                .where(agent_evolution_events_table.c.event_id == key)
                .limit(1)
            ).first()
        return self._row_to_event(row) if row is not None else None

    def list_events(
        self,
        *,
        occurred_from: datetime,
        occurred_to: datetime,
        event_type: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[EvolutionEvent]:
        start, end = validate_query_window(occurred_from, occurred_to)
        bound = validate_query_limit(limit)
        exact_type = normalize_optional_event_type(event_type)
        conditions = [
            agent_evolution_events_table.c.occurred_at >= _as_utc_naive(start),
            agent_evolution_events_table.c.occurred_at <= _as_utc_naive(end),
        ]
        if exact_type is not None:
            conditions.append(agent_evolution_events_table.c.event_type == exact_type)
        with self.db.get_session() as session:
            rows = session.execute(
                select(agent_evolution_events_table)
                .where(*conditions)
                .order_by(
                    agent_evolution_events_table.c.occurred_at.asc(),
                    agent_evolution_events_table.c.id.asc(),
                )
                .limit(bound)
            ).all()
        return [self._row_to_event(row) for row in rows]
