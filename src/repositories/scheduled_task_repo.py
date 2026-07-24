"""Persistence operations for scheduled task definitions and run records."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import desc, func, select, update
from sqlalchemy.exc import IntegrityError

from src.schemas.scheduled_task import ACTIVE_SCHEDULED_RUN_STATUSES
from src.storage import DatabaseManager, ScheduledTaskRecord, ScheduledTaskRunRecord


class ScheduledTaskRepository:
    """SQLAlchemy repository with an atomic due-occurrence claim."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None) -> None:
        self.db = db_manager or DatabaseManager.get_instance()

    @staticmethod
    def _detach(session, row):
        if row is not None:
            session.expunge(row)
        return row

    def create_task(self, fields: Dict[str, Any]) -> ScheduledTaskRecord:
        with self.db.get_session() as session:
            row = ScheduledTaskRecord(**fields)
            session.add(row)
            session.commit()
            session.refresh(row)
            return self._detach(session, row)

    def get_task(self, task_id: str) -> Optional[ScheduledTaskRecord]:
        with self.db.get_session() as session:
            row = session.execute(
                select(ScheduledTaskRecord)
                .where(ScheduledTaskRecord.id == task_id)
                .limit(1)
            ).scalar_one_or_none()
            return self._detach(session, row)

    def list_tasks(
        self,
        *,
        enabled: Optional[bool] = None,
        limit: int = 100,
    ) -> List[ScheduledTaskRecord]:
        query = select(ScheduledTaskRecord)
        if enabled is not None:
            query = query.where(ScheduledTaskRecord.enabled.is_(enabled))
        with self.db.get_session() as session:
            rows = session.execute(
                query.order_by(
                    desc(ScheduledTaskRecord.updated_at),
                    ScheduledTaskRecord.id,
                ).limit(max(1, min(int(limit), 500)))
            ).scalars().all()
            for row in rows:
                session.expunge(row)
            return list(rows)

    def has_enabled_tasks(self) -> bool:
        with self.db.get_session() as session:
            return session.execute(
                select(ScheduledTaskRecord.id)
                .where(ScheduledTaskRecord.enabled.is_(True))
                .limit(1)
            ).scalar_one_or_none() is not None

    def count_tasks(self, *, enabled: Optional[bool] = None) -> int:
        query = select(func.count(ScheduledTaskRecord.id))
        if enabled is not None:
            query = query.where(ScheduledTaskRecord.enabled.is_(enabled))
        with self.db.get_session() as session:
            return int(session.execute(query).scalar() or 0)

    def set_enabled(
        self,
        task_id: str,
        *,
        enabled: bool,
        next_run_at: Optional[datetime],
        updated_at: datetime,
    ) -> Optional[ScheduledTaskRecord]:
        with self.db.get_session() as session:
            row = session.execute(
                select(ScheduledTaskRecord)
                .where(ScheduledTaskRecord.id == task_id)
                .limit(1)
            ).scalar_one_or_none()
            if row is None:
                return None
            row.enabled = enabled
            row.next_run_at = next_run_at
            row.updated_at = updated_at
            session.commit()
            session.refresh(row)
            return self._detach(session, row)

    def list_due_tasks(
        self,
        *,
        now: datetime,
        limit: int = 100,
    ) -> List[ScheduledTaskRecord]:
        with self.db.get_session() as session:
            rows = session.execute(
                select(ScheduledTaskRecord)
                .where(
                    ScheduledTaskRecord.enabled.is_(True),
                    ScheduledTaskRecord.next_run_at.is_not(None),
                    ScheduledTaskRecord.next_run_at <= now,
                )
                .order_by(ScheduledTaskRecord.next_run_at, ScheduledTaskRecord.id)
                .limit(max(1, min(int(limit), 500)))
            ).scalars().all()
            for row in rows:
                session.expunge(row)
            return list(rows)

    def claim_due_occurrence(
        self,
        *,
        task_id: str,
        expected_next_run_at: datetime,
        next_run_at: datetime,
        run_fields: Dict[str, Any],
        updated_at: datetime,
    ) -> Optional[ScheduledTaskRunRecord]:
        """Advance one due definition and create its unique run atomically."""
        with self.db.get_session() as session:
            result = session.execute(
                update(ScheduledTaskRecord)
                .where(
                    ScheduledTaskRecord.id == task_id,
                    ScheduledTaskRecord.enabled.is_(True),
                    ScheduledTaskRecord.next_run_at == expected_next_run_at,
                )
                .values(next_run_at=next_run_at, updated_at=updated_at)
            )
            if result.rowcount != 1:
                session.rollback()
                return None
            run = ScheduledTaskRunRecord(**run_fields)
            session.add(run)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = session.execute(
                    select(ScheduledTaskRunRecord.id)
                    .where(
                        ScheduledTaskRunRecord.task_id == task_id,
                        ScheduledTaskRunRecord.scheduled_for == expected_next_run_at,
                    )
                    .limit(1)
                ).scalar_one_or_none()
                if existing is not None:
                    return None
                raise
            session.refresh(run)
            return self._detach(session, run)

    def get_run(self, run_id: str) -> Optional[ScheduledTaskRunRecord]:
        with self.db.get_session() as session:
            row = session.execute(
                select(ScheduledTaskRunRecord)
                .where(ScheduledTaskRunRecord.id == run_id)
                .limit(1)
            ).scalar_one_or_none()
            return self._detach(session, row)

    def update_run(
        self,
        run_id: str,
        fields: Dict[str, Any],
    ) -> Optional[ScheduledTaskRunRecord]:
        with self.db.get_session() as session:
            row = session.execute(
                select(ScheduledTaskRunRecord)
                .where(ScheduledTaskRunRecord.id == run_id)
                .limit(1)
            ).scalar_one_or_none()
            if row is None:
                return None
            for key, value in fields.items():
                setattr(row, key, value)
            session.commit()
            session.refresh(row)
            return self._detach(session, row)

    def list_runs(
        self,
        task_id: str,
        *,
        limit: int = 100,
    ) -> List[ScheduledTaskRunRecord]:
        with self.db.get_session() as session:
            rows = session.execute(
                select(ScheduledTaskRunRecord)
                .where(ScheduledTaskRunRecord.task_id == task_id)
                .order_by(
                    desc(ScheduledTaskRunRecord.scheduled_for),
                    desc(ScheduledTaskRunRecord.created_at),
                )
                .limit(max(1, min(int(limit), 500)))
            ).scalars().all()
            for row in rows:
                session.expunge(row)
            return list(rows)

    def count_runs(self, task_id: str) -> int:
        with self.db.get_session() as session:
            return int(
                session.execute(
                    select(func.count(ScheduledTaskRunRecord.id)).where(
                        ScheduledTaskRunRecord.task_id == task_id
                    )
                ).scalar()
                or 0
            )

    def list_active_runs(self, *, limit: int = 500) -> List[ScheduledTaskRunRecord]:
        with self.db.get_session() as session:
            rows = session.execute(
                select(ScheduledTaskRunRecord)
                .where(ScheduledTaskRunRecord.status.in_(ACTIVE_SCHEDULED_RUN_STATUSES))
                .order_by(ScheduledTaskRunRecord.created_at, ScheduledTaskRunRecord.id)
                .limit(max(1, min(int(limit), 1000)))
            ).scalars().all()
            for row in rows:
                session.expunge(row)
            return list(rows)
