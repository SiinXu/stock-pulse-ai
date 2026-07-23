# -*- coding: utf-8 -*-
"""Repository for DecisionSignal memory curation flags (Issue #118)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select

from src.storage import (
    DatabaseManager,
    DecisionSignalMemoryFlagRecord,
    utc_naive_now,
)


class DecisionSignalMemoryFlagRepository:
    """DB access for the per-signal memorable/ignored sidecar table."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or DatabaseManager.get_instance()

    def get(self, *, signal_id: int) -> Optional[DecisionSignalMemoryFlagRecord]:
        with self.db.get_session() as session:
            return session.execute(
                select(DecisionSignalMemoryFlagRecord)
                .where(DecisionSignalMemoryFlagRecord.signal_id == signal_id)
                .limit(1)
            ).scalar_one_or_none()

    def list_for_signals(
        self,
        *,
        signal_ids: List[int],
    ) -> List[DecisionSignalMemoryFlagRecord]:
        if not signal_ids:
            return []
        with self.db.get_session() as session:
            rows = session.execute(
                select(DecisionSignalMemoryFlagRecord).where(
                    DecisionSignalMemoryFlagRecord.signal_id.in_(signal_ids)
                )
            ).scalars().all()
            return list(rows)

    def upsert(self, fields: Dict[str, Any]) -> DecisionSignalMemoryFlagRecord:
        now = utc_naive_now()
        with self.db.get_session() as session:
            existing = session.execute(
                select(DecisionSignalMemoryFlagRecord)
                .where(DecisionSignalMemoryFlagRecord.signal_id == fields["signal_id"])
                .limit(1)
            ).scalar_one_or_none()
            if existing is None:
                row = DecisionSignalMemoryFlagRecord(**fields)
                session.add(row)
                session.commit()
                session.refresh(row)
                return row

            for key, value in fields.items():
                if key in {"id", "signal_id", "created_at"}:
                    continue
                setattr(existing, key, value)
            existing.updated_at = now
            session.commit()
            session.refresh(existing)
            return existing
