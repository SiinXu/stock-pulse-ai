# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Append and bounded-query access for durable security audit events."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Optional

from sqlalchemy import delete, desc, func, select

from src.schemas.security_audit import (
    SECURITY_AUDIT_MAX_PAGE_SIZE,
    SecurityAuditActor,
    SecurityAuditEvent,
    SecurityAuditEventCreate,
    SecurityAuditTarget,
)
from src.storage import DatabaseManager, SecurityAuditEventRecord


class SecurityAuditRepository:
    """The only persistence boundary for the append-oriented audit table."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None) -> None:
        self.db = db_manager or DatabaseManager.get_instance()

    def append(self, event: SecurityAuditEventCreate) -> SecurityAuditEvent:
        row = SecurityAuditEventRecord(
            schema_version=event.schema_version,
            occurred_at=event.occurred_at.astimezone(timezone.utc).replace(tzinfo=None),
            event_type=event.event_type,
            phase=event.phase,
            actor_type=event.actor.type,
            actor_id=event.actor.id,
            execution_id=event.execution_id,
            action=event.action,
            target_type=event.target.type,
            target_id=event.target.id,
            outcome=event.outcome,
            reason_code=event.reason_code,
            correlation_id=event.correlation_id,
            metadata_json=json.dumps(
                event.metadata,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
        )
        with self.db.get_session() as session:
            session.add(row)
            session.commit()
            session.refresh(row)
            return self._to_event(row)

    def apply_retention(self, *, cutoff: datetime) -> int:
        cutoff_utc_naive = cutoff.astimezone(timezone.utc).replace(tzinfo=None)
        with self.db.get_session() as session:
            result = session.execute(
                delete(SecurityAuditEventRecord).where(
                    SecurityAuditEventRecord.occurred_at < cutoff_utc_naive
                )
            )
            session.commit()
            return int(result.rowcount or 0)

    def list_events(
        self,
        *,
        page: int,
        page_size: int,
        event_type: str | None = None,
        outcome: str | None = None,
        correlation_id: str | None = None,
        occurred_from: datetime | None = None,
        occurred_to: datetime | None = None,
    ) -> tuple[list[SecurityAuditEvent], int]:
        safe_page = max(1, int(page))
        safe_page_size = max(1, min(int(page_size), SECURITY_AUDIT_MAX_PAGE_SIZE))
        conditions = []
        if event_type:
            conditions.append(SecurityAuditEventRecord.event_type == event_type)
        if outcome:
            conditions.append(SecurityAuditEventRecord.outcome == outcome)
        if correlation_id:
            conditions.append(
                SecurityAuditEventRecord.correlation_id == correlation_id
            )
        if occurred_from is not None:
            conditions.append(
                SecurityAuditEventRecord.occurred_at
                >= occurred_from.astimezone(timezone.utc).replace(tzinfo=None)
            )
        if occurred_to is not None:
            conditions.append(
                SecurityAuditEventRecord.occurred_at
                <= occurred_to.astimezone(timezone.utc).replace(tzinfo=None)
            )

        with self.db.get_session() as session:
            count_query = select(func.count(SecurityAuditEventRecord.id))
            rows_query = select(SecurityAuditEventRecord)
            if conditions:
                count_query = count_query.where(*conditions)
                rows_query = rows_query.where(*conditions)
            total = int(session.execute(count_query).scalar() or 0)
            rows = session.execute(
                rows_query
                .order_by(
                    desc(SecurityAuditEventRecord.occurred_at),
                    desc(SecurityAuditEventRecord.id),
                )
                .offset((safe_page - 1) * safe_page_size)
                .limit(safe_page_size)
            ).scalars().all()
            return [self._to_event(row) for row in rows], total

    @staticmethod
    def _to_event(row: SecurityAuditEventRecord) -> SecurityAuditEvent:
        occurred_at = row.occurred_at
        if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
            occurred_at = occurred_at.replace(tzinfo=timezone.utc)
        return SecurityAuditEvent(
            id=row.id,
            schema_version=row.schema_version,
            occurred_at=occurred_at,
            event_type=row.event_type,
            phase=row.phase,
            actor=SecurityAuditActor(type=row.actor_type, id=row.actor_id),
            execution_id=row.execution_id,
            action=row.action,
            target=SecurityAuditTarget(type=row.target_type, id=row.target_id),
            outcome=row.outcome,
            reason_code=row.reason_code,
            correlation_id=row.correlation_id,
            metadata=json.loads(row.metadata_json),
        )
