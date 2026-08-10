"""Persistence operations for scheduled task definitions and run records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Sequence

from sqlalchemy import desc, func, insert, literal, select, update
from sqlalchemy.exc import IntegrityError

from src.schemas.scheduled_task import (
    ACTIVE_SCHEDULED_RUN_STATUSES,
    MAX_SCHEDULED_TASK_EXECUTION_GENERATION,
)
from src.storage import DatabaseManager, ScheduledTaskRecord, ScheduledTaskRunRecord


@dataclass(frozen=True)
class ScheduledRunFenceResult:
    """Outcome of one queue admission guarded by the definition writer lock."""

    outcome: str
    task: Optional[ScheduledTaskRecord] = None
    run: Optional[ScheduledTaskRunRecord] = None


class ScheduledTaskRepository:
    """SQLAlchemy repository with an atomic due-occurrence claim."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None) -> None:
        self.db = db_manager or DatabaseManager.get_instance()

    @staticmethod
    def _detach(session, row):
        """Detach one ORM row from its short-lived repository session."""
        if row is not None:
            session.expunge(row)
        return row

    def create_task(self, fields: Dict[str, Any]) -> ScheduledTaskRecord:
        """Persist and return one scheduled-task definition."""
        with self.db.get_session() as session:
            row = ScheduledTaskRecord(**fields)
            session.add(row)
            session.commit()
            session.refresh(row)
            return self._detach(session, row)

    def get_task(self, task_id: str) -> Optional[ScheduledTaskRecord]:
        """Return one definition by identifier, if present."""
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
        """List definitions in stable newest-first order."""
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
        """Return whether any persisted definition is enabled."""
        with self.db.get_session() as session:
            return session.execute(
                select(ScheduledTaskRecord.id)
                .where(ScheduledTaskRecord.enabled.is_(True))
                .limit(1)
            ).scalar_one_or_none() is not None

    def count_tasks(self, *, enabled: Optional[bool] = None) -> int:
        """Count definitions matching the optional enablement filter."""
        query = select(func.count(ScheduledTaskRecord.id))
        if enabled is not None:
            query = query.where(ScheduledTaskRecord.enabled.is_(enabled))
        with self.db.get_session() as session:
            return int(session.execute(query).scalar() or 0)

    def list_tasks_by_ids(
        self,
        task_ids: Sequence[str],
    ) -> List[ScheduledTaskRecord]:
        """Return definitions for a bounded identifier set."""
        canonical_ids = list(dict.fromkeys(str(task_id) for task_id in task_ids))
        if not canonical_ids:
            return []
        with self.db.get_session() as session:
            rows = session.execute(
                select(ScheduledTaskRecord)
                .where(ScheduledTaskRecord.id.in_(canonical_ids))
                .order_by(ScheduledTaskRecord.id)
            ).scalars().all()
            for row in rows:
                session.expunge(row)
            return list(rows)

    def list_next_occurrences_between(
        self,
        *,
        start: datetime,
        end: datetime,
        limit: int = 500,
    ) -> List[ScheduledTaskRecord]:
        """List enabled definitions whose next occurrence is in [start, end)."""
        with self.db.get_session() as session:
            rows = session.execute(
                select(ScheduledTaskRecord)
                .where(
                    ScheduledTaskRecord.enabled.is_(True),
                    ScheduledTaskRecord.next_run_at.is_not(None),
                    ScheduledTaskRecord.next_run_at >= start,
                    ScheduledTaskRecord.next_run_at < end,
                )
                .order_by(
                    ScheduledTaskRecord.next_run_at,
                    ScheduledTaskRecord.id,
                )
                .limit(max(1, min(int(limit), 500)))
            ).scalars().all()
            for row in rows:
                session.expunge(row)
            return list(rows)

    def set_enabled(
        self,
        task_id: str,
        *,
        expected_schema_version: int,
        expected_execution_generation: int,
        enabled: bool,
        next_run_at: Optional[datetime],
        updated_at: datetime,
    ) -> Optional[ScheduledTaskRecord]:
        """Update enablement only while the understood schema still matches."""
        with self.db.get_session() as session:
            result = session.execute(
                update(ScheduledTaskRecord)
                .where(
                    ScheduledTaskRecord.id == task_id,
                    ScheduledTaskRecord.schema_version
                    == expected_schema_version,
                    ScheduledTaskRecord.execution_generation
                    == expected_execution_generation,
                )
                .values(
                    enabled=enabled,
                    execution_generation=min(
                        expected_execution_generation + 1,
                        MAX_SCHEDULED_TASK_EXECUTION_GENERATION,
                    ),
                    next_run_at=next_run_at,
                    updated_at=updated_at,
                )
            )
            if result.rowcount != 1:
                session.rollback()
                return None
            session.commit()
            row = session.get(ScheduledTaskRecord, task_id)
            return self._detach(session, row)

    def list_due_tasks(
        self,
        *,
        now: datetime,
        limit: int = 100,
    ) -> List[ScheduledTaskRecord]:
        """List due definitions whose current slot has not been fenced."""
        occurrence_exists = (
            select(ScheduledTaskRunRecord.id)
            .where(
                ScheduledTaskRunRecord.task_id == ScheduledTaskRecord.id,
                ScheduledTaskRunRecord.scheduled_for
                == ScheduledTaskRecord.next_run_at,
            )
            .exists()
        )
        with self.db.get_session() as session:
            rows = session.execute(
                select(ScheduledTaskRecord)
                .where(
                    ScheduledTaskRecord.enabled.is_(True),
                    ScheduledTaskRecord.next_run_at.is_not(None),
                    ScheduledTaskRecord.next_run_at <= now,
                    ~occurrence_exists,
                )
                .order_by(ScheduledTaskRecord.next_run_at, ScheduledTaskRecord.id)
                .limit(max(1, min(int(limit), 500)))
            ).scalars().all()
            for row in rows:
                session.expunge(row)
            return list(rows)

    def list_schema_unsupported_fences(
        self,
        *,
        now: datetime,
        supported_schema_versions: Sequence[int],
        limit: int = 100,
    ) -> List[tuple[ScheduledTaskRecord, ScheduledTaskRunRecord]]:
        """List due slots that only an older binary marked schema-unsupported."""
        versions = list(dict.fromkeys(supported_schema_versions))
        if not versions:
            return []
        with self.db.get_session() as session:
            rows = session.execute(
                select(ScheduledTaskRecord, ScheduledTaskRunRecord)
                .join(
                    ScheduledTaskRunRecord,
                    (
                        ScheduledTaskRunRecord.task_id
                        == ScheduledTaskRecord.id
                    )
                    & (
                        ScheduledTaskRunRecord.scheduled_for
                        == ScheduledTaskRecord.next_run_at
                    )
                    & (
                        ScheduledTaskRunRecord.definition_schema_version
                        == ScheduledTaskRecord.schema_version
                    )
                    & (
                        ScheduledTaskRunRecord.definition_generation
                        == ScheduledTaskRecord.execution_generation
                    ),
                )
                .where(
                    ScheduledTaskRecord.enabled.is_(True),
                    ScheduledTaskRecord.schema_version.in_(versions),
                    ScheduledTaskRecord.next_run_at.is_not(None),
                    ScheduledTaskRecord.next_run_at <= now,
                    ScheduledTaskRunRecord.status == "interrupted",
                    ScheduledTaskRunRecord.error_code
                    == "scheduled_task_schema_unsupported",
                )
                .order_by(
                    ScheduledTaskRecord.next_run_at,
                    ScheduledTaskRecord.id,
                )
                .limit(max(1, min(int(limit), 500)))
            ).all()
            result = []
            for task, run in rows:
                session.expunge(task)
                session.expunge(run)
                result.append((task, run))
            return result

    def advance_schema_unsupported_fence(
        self,
        *,
        task_id: str,
        expected_schema_version: int,
        expected_execution_generation: int,
        expected_next_run_at: datetime,
        expected_run_id: str,
        next_run_at: datetime,
        updated_at: datetime,
    ) -> bool:
        """Advance one now-supported fence without replaying its old occurrence."""
        matching_fence = (
            select(ScheduledTaskRunRecord.id)
            .where(
                ScheduledTaskRunRecord.id == expected_run_id,
                ScheduledTaskRunRecord.task_id == task_id,
                ScheduledTaskRunRecord.scheduled_for
                == expected_next_run_at,
                ScheduledTaskRunRecord.definition_schema_version
                == expected_schema_version,
                ScheduledTaskRunRecord.definition_generation
                == expected_execution_generation,
                ScheduledTaskRunRecord.status == "interrupted",
                ScheduledTaskRunRecord.error_code
                == "scheduled_task_schema_unsupported",
            )
            .exists()
        )
        with self.db.get_session() as session:
            result = session.execute(
                update(ScheduledTaskRecord)
                .where(
                    ScheduledTaskRecord.id == task_id,
                    ScheduledTaskRecord.schema_version
                    == expected_schema_version,
                    ScheduledTaskRecord.execution_generation
                    == expected_execution_generation,
                    ScheduledTaskRecord.enabled.is_(True),
                    ScheduledTaskRecord.next_run_at == expected_next_run_at,
                    matching_fence,
                )
                .values(next_run_at=next_run_at, updated_at=updated_at)
            )
            if result.rowcount != 1:
                session.rollback()
                return False
            session.commit()
            return True

    def claim_due_occurrence(
        self,
        *,
        task_id: str,
        expected_schema_version: int,
        expected_execution_generation: int,
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
                    ScheduledTaskRecord.schema_version
                    == expected_schema_version,
                    ScheduledTaskRecord.execution_generation
                    == expected_execution_generation,
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

    def record_unmodified_interrupted_occurrence(
        self,
        *,
        task_id: str,
        expected_schema_version: int,
        expected_execution_generation: int,
        expected_next_run_at: datetime,
        run_fields: Dict[str, Any],
    ) -> Optional[ScheduledTaskRunRecord]:
        """Fence one unsupported due slot without rewriting its definition."""
        columns = list(run_fields)
        if "task_id" not in columns or "scheduled_for" not in columns:
            raise ValueError("run_fields must include task_id and scheduled_for")

        projected_values = []
        for column in columns:
            if column == "task_id":
                projected_values.append(ScheduledTaskRecord.id)
            elif column == "scheduled_for":
                projected_values.append(ScheduledTaskRecord.next_run_at)
            else:
                projected_values.append(literal(run_fields[column]))

        source = select(*projected_values).where(
            ScheduledTaskRecord.id == task_id,
            ScheduledTaskRecord.schema_version == expected_schema_version,
            ScheduledTaskRecord.execution_generation
            == expected_execution_generation,
            ScheduledTaskRecord.enabled.is_(True),
            ScheduledTaskRecord.next_run_at == expected_next_run_at,
        )
        with self.db.get_session() as session:
            try:
                session.execute(
                    insert(ScheduledTaskRunRecord).from_select(columns, source)
                )
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = session.execute(
                    select(ScheduledTaskRunRecord.id)
                    .where(
                        ScheduledTaskRunRecord.task_id == task_id,
                        ScheduledTaskRunRecord.scheduled_for
                        == expected_next_run_at,
                    )
                    .limit(1)
                ).scalar_one_or_none()
                if existing is not None:
                    return None
                raise
            row = session.get(ScheduledTaskRunRecord, run_fields["id"])
            return self._detach(session, row)

    def quarantine_due_task(
        self,
        *,
        task_id: str,
        expected_schema_version: int,
        expected_execution_generation: int,
        expected_next_run_at: datetime,
        run_fields: Dict[str, Any],
        updated_at: datetime,
    ) -> Optional[ScheduledTaskRunRecord]:
        """Disable one incompatible due definition and record it atomically."""
        with self.db.get_session() as session:
            result = session.execute(
                update(ScheduledTaskRecord)
                .where(
                    ScheduledTaskRecord.id == task_id,
                    ScheduledTaskRecord.schema_version
                    == expected_schema_version,
                    ScheduledTaskRecord.execution_generation
                    == expected_execution_generation,
                    ScheduledTaskRecord.enabled.is_(True),
                    ScheduledTaskRecord.next_run_at == expected_next_run_at,
                )
                .values(
                    enabled=False,
                    execution_generation=expected_execution_generation + 1,
                    next_run_at=None,
                    updated_at=updated_at,
                )
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

    def disable_corrupt_task(
        self,
        *,
        task_id: str,
        expected_schema_version: Any,
        expected_execution_generation: Any,
        expected_next_run_at: Optional[datetime],
        updated_at: datetime,
    ) -> bool:
        """Disable corruption above all valid snapshots, or at the terminal ceiling."""
        session = self.db.get_session()
        try:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            task = session.get(ScheduledTaskRecord, task_id)
            if (
                task is None
                or type(task.schema_version) is not type(expected_schema_version)
                or task.schema_version != expected_schema_version
                or type(task.execution_generation)
                is not type(expected_execution_generation)
                or task.execution_generation != expected_execution_generation
                or task.enabled is not True
                or task.next_run_at != expected_next_run_at
            ):
                session.rollback()
                return False

            max_snapshot = session.execute(
                select(func.max(ScheduledTaskRunRecord.definition_generation))
                .where(
                    ScheduledTaskRunRecord.task_id == task_id,
                    func.typeof(
                        ScheduledTaskRunRecord.definition_generation
                    ) == "integer",
                    ScheduledTaskRunRecord.definition_generation >= 1,
                    ScheduledTaskRunRecord.definition_generation
                    <= MAX_SCHEDULED_TASK_EXECUTION_GENERATION,
                )
            ).scalar()
            valid_generations = [
                int(max_snapshot or 0),
            ]
            if (
                type(task.execution_generation) is int
                and 1
                <= task.execution_generation
                <= MAX_SCHEDULED_TASK_EXECUTION_GENERATION
            ):
                valid_generations.append(task.execution_generation)
            highest_valid_generation = max(valid_generations)
            replacement_generation = min(
                highest_valid_generation + 1,
                MAX_SCHEDULED_TASK_EXECUTION_GENERATION,
            )
            task.enabled = False
            task.execution_generation = replacement_generation
            task.next_run_at = None
            task.updated_at = updated_at
            session.commit()
            return True
        except Exception:  # broad-exception: cleanup - roll back before re-raising.
            session.rollback()
            raise
        finally:
            session.close()

    def reserve_run_admission(
        self,
        *,
        run_id: str,
        dispatch_token: str,
        now: datetime,
    ) -> Optional[ScheduledTaskRunRecord]:
        """Reserve one due retry before any process-local queue side effect."""
        with self.db.get_session() as session:
            result = session.execute(
                update(ScheduledTaskRunRecord)
                .where(
                    ScheduledTaskRunRecord.id == run_id,
                    ScheduledTaskRunRecord.status == "retry_wait",
                    ScheduledTaskRunRecord.dispatch_token.is_(None),
                    ScheduledTaskRunRecord.next_attempt_at.is_not(None),
                    ScheduledTaskRunRecord.next_attempt_at <= now,
                )
                .values(
                    status="dispatching",
                    dispatch_token=dispatch_token,
                    updated_at=now,
                )
            )
            if result.rowcount != 1:
                session.rollback()
                return None
            session.commit()
            row = session.get(ScheduledTaskRunRecord, run_id)
            return self._detach(session, row)

    def update_run_under_definition_fence(
        self,
        *,
        run_id: str,
        expected_schema_version: int,
        expected_dispatch_token: str,
        allowed_run_statuses: Sequence[str],
        now: datetime,
        update_factory: Callable[
            [ScheduledTaskRecord, ScheduledTaskRunRecord],
            Dict[str, Any],
        ],
    ) -> ScheduledRunFenceResult:
        """Apply a queue admission and its run update in one writer window.

        SQLite's writer lock is acquired before the definition and run are read.
        The callback may submit to the process-local queue; concurrent definition
        mutations therefore linearize either before that side effect or after its
        durable execution identity has been recorded.
        """
        session = self.db.get_session()
        try:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            run = session.get(ScheduledTaskRunRecord, run_id)
            task = (
                session.get(ScheduledTaskRecord, run.task_id)
                if run is not None
                else None
            )

            def finish(outcome: str) -> ScheduledRunFenceResult:
                if task is not None:
                    session.expunge(task)
                if run is not None:
                    session.expunge(run)
                session.commit()
                return ScheduledRunFenceResult(outcome, task=task, run=run)

            if run is None:
                return finish("run_missing")
            if task is None:
                return finish("task_missing")
            if (
                type(task.schema_version) is not int
                or type(expected_schema_version) is not int
                or task.schema_version != expected_schema_version
            ):
                return finish("schema_changed")
            if (
                type(run.definition_schema_version) is not int
                or task.schema_version != run.definition_schema_version
            ):
                return finish("schema_changed")
            if run.dispatch_token != expected_dispatch_token:
                return finish("reservation_changed")
            if (
                type(task.execution_generation) is not int
                or type(run.definition_generation) is not int
                or task.execution_generation != run.definition_generation
            ):
                return finish("generation_changed")
            if not bool(task.enabled):
                return finish("disabled")
            if run.status not in set(allowed_run_statuses):
                return finish("run_changed")
            if (
                run.status == "retry_wait"
                and run.next_attempt_at is not None
                and run.next_attempt_at > now
            ):
                return finish("not_due")

            fields = update_factory(task, run)
            for key, value in fields.items():
                setattr(run, key, value)
            session.flush()
            session.refresh(task)
            session.refresh(run)
            return finish("applied")
        except Exception:  # broad-exception: cleanup - Roll back the fenced writer transaction before preserving the original failure.
            session.rollback()
            raise
        finally:
            session.close()

    def finalize_dispatch_reservation(
        self,
        *,
        run_id: str,
        dispatch_token: str,
        fields: Dict[str, Any],
    ) -> Optional[ScheduledTaskRunRecord]:
        """Conditionally finalize one admission reservation after a fence miss."""
        with self.db.get_session() as session:
            result = session.execute(
                update(ScheduledTaskRunRecord)
                .where(
                    ScheduledTaskRunRecord.id == run_id,
                    ScheduledTaskRunRecord.status == "dispatching",
                    ScheduledTaskRunRecord.dispatch_token == dispatch_token,
                )
                .values(**fields)
            )
            if result.rowcount != 1:
                session.rollback()
                return None
            session.commit()
            row = session.get(ScheduledTaskRunRecord, run_id)
            return self._detach(session, row)

    def get_run(self, run_id: str) -> Optional[ScheduledTaskRunRecord]:
        """Return one occurrence record by identifier, if present."""
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
        """Update and return one occurrence record."""
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
        """List occurrence records for one definition."""
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

    def list_runs_between(
        self,
        *,
        start: datetime,
        end: datetime,
        limit: int = 500,
    ) -> List[ScheduledTaskRunRecord]:
        """List occurrence records scheduled in [start, end)."""
        with self.db.get_session() as session:
            rows = session.execute(
                select(ScheduledTaskRunRecord)
                .where(
                    ScheduledTaskRunRecord.scheduled_for >= start,
                    ScheduledTaskRunRecord.scheduled_for < end,
                )
                .order_by(
                    ScheduledTaskRunRecord.scheduled_for,
                    ScheduledTaskRunRecord.task_id,
                    ScheduledTaskRunRecord.id,
                )
                .limit(max(1, min(int(limit), 500)))
            ).scalars().all()
            for row in rows:
                session.expunge(row)
            return list(rows)

    def list_recent_runs_between(
        self,
        *,
        start: datetime,
        end: datetime,
        statuses: Sequence[str],
        limit: int = 500,
    ) -> List[ScheduledTaskRunRecord]:
        """List the newest bounded run occurrences by terminal event time."""
        normalized_statuses = tuple(
            sorted({str(status).strip() for status in statuses if str(status).strip()})
        )
        if not normalized_statuses:
            return []
        occurred_at = func.coalesce(
            ScheduledTaskRunRecord.finished_at,
            ScheduledTaskRunRecord.updated_at,
            ScheduledTaskRunRecord.created_at,
            ScheduledTaskRunRecord.scheduled_for,
        )
        with self.db.get_session() as session:
            rows = session.execute(
                select(ScheduledTaskRunRecord)
                .where(
                    ScheduledTaskRunRecord.status.in_(normalized_statuses),
                    occurred_at >= start,
                    occurred_at < end,
                )
                .order_by(desc(occurred_at), desc(ScheduledTaskRunRecord.id))
                .limit(max(1, min(int(limit), 5000)))
            ).scalars().all()
            for row in rows:
                session.expunge(row)
            return list(rows)

    def count_runs(self, task_id: str) -> int:
        """Count occurrence records for one definition."""
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
        """List runs that still require process-local reconciliation."""
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
