# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Persistence for process-local task-queue in-flight checkpoints."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, select

from src.repositories.base import BaseRepository, RepositoryError
from src.storage import DatabaseManager, TaskQueueInflightRecord, utc_naive_now
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TaskQueueInflightCheckpoint:
    """Detached checkpoint used by restart recovery."""

    task_id: str
    kind: str
    status: str
    stock_code: Optional[str]
    recovery_class: str
    dedupe_key: Optional[str]
    idempotency_key: Optional[str]
    idempotency_fingerprint: Optional[str]
    failure_error_code: Optional[str]
    none_is_success: bool
    metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime


class TaskQueueInflightRepository(BaseRepository):
    """SQLite-backed checkpoints for single-process restart recovery."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None) -> None:
        super().__init__(db_manager)

    @staticmethod
    def _row_to_checkpoint(row: TaskQueueInflightRecord) -> TaskQueueInflightCheckpoint:
        try:
            metadata = json.loads(row.metadata_json or "{}")
        except (TypeError, ValueError):
            metadata = {}
        if not isinstance(metadata, dict):
            metadata = {}
        return TaskQueueInflightCheckpoint(
            task_id=str(row.task_id),
            kind=str(row.kind or ""),
            status=str(row.status or ""),
            stock_code=row.stock_code,
            recovery_class=str(row.recovery_class or "interrupt"),
            dedupe_key=row.dedupe_key,
            idempotency_key=row.idempotency_key,
            idempotency_fingerprint=row.idempotency_fingerprint,
            failure_error_code=row.failure_error_code,
            none_is_success=bool(row.none_is_success),
            metadata=metadata,
            created_at=row.created_at or utc_naive_now(),
            updated_at=row.updated_at or utc_naive_now(),
        )

    def upsert(self, fields: Dict[str, Any]) -> None:
        """Insert or replace one non-terminal checkpoint."""
        task_id = str(fields.get("task_id") or "").strip()
        if not task_id:
            raise ValueError("task_id is required")
        now = fields.get("updated_at") or utc_naive_now()
        created_at = fields.get("created_at") or now
        metadata = fields.get("metadata")
        if metadata is None:
            metadata_json = str(fields.get("metadata_json") or "{}")
        else:
            metadata_json = json.dumps(metadata, ensure_ascii=False, default=str)
        try:
            with self.db.get_session() as session:
                row = session.get(TaskQueueInflightRecord, task_id)
                if row is None:
                    row = TaskQueueInflightRecord(
                        task_id=task_id,
                        created_at=created_at,
                    )
                    session.add(row)
                row.kind = str(fields.get("kind") or "background")
                row.status = str(fields.get("status") or "pending")
                row.stock_code = fields.get("stock_code")
                row.recovery_class = str(fields.get("recovery_class") or "interrupt")
                row.dedupe_key = fields.get("dedupe_key")
                row.idempotency_key = fields.get("idempotency_key")
                row.idempotency_fingerprint = fields.get("idempotency_fingerprint")
                row.failure_error_code = fields.get("failure_error_code")
                row.none_is_success = bool(fields.get("none_is_success", False))
                row.metadata_json = metadata_json
                row.updated_at = now
                if row.created_at is None:
                    row.created_at = created_at
                session.commit()
        except Exception as exc:  # broad-exception: fallback_recorded - surface as repository error
            context = {"task_id": task_id}
            log_safe_exception(
                logger,
                "Task queue inflight checkpoint upsert failed",
                exc,
                error_code="task_queue_inflight_upsert_failed",
                context=context,
            )
            raise RepositoryError(
                "Task queue inflight checkpoint upsert failed",
                error_code="task_queue_inflight_upsert_failed",
                context=context,
            ) from exc

    def delete(self, task_id: str) -> None:
        """Remove a checkpoint after a terminal transition or rollback."""
        canonical = str(task_id or "").strip()
        if not canonical:
            return
        try:
            with self.db.get_session() as session:
                session.execute(
                    delete(TaskQueueInflightRecord).where(
                        TaskQueueInflightRecord.task_id == canonical
                    )
                )
                session.commit()
        except Exception as exc:  # broad-exception: fallback_recorded - surface as repository error
            context = {"task_id": canonical}
            log_safe_exception(
                logger,
                "Task queue inflight checkpoint delete failed",
                exc,
                error_code="task_queue_inflight_delete_failed",
                context=context,
            )
            raise RepositoryError(
                "Task queue inflight checkpoint delete failed",
                error_code="task_queue_inflight_delete_failed",
                context=context,
            ) from exc

    def list_inflight(self) -> List[TaskQueueInflightCheckpoint]:
        """Return all checkpoints left by a previous process."""
        try:
            with self.db.get_session() as session:
                rows = session.execute(
                    select(TaskQueueInflightRecord).order_by(
                        TaskQueueInflightRecord.updated_at.asc()
                    )
                ).scalars().all()
                return [self._row_to_checkpoint(row) for row in rows]
        except Exception as exc:  # broad-exception: fallback_recorded - surface as repository error
            log_safe_exception(
                logger,
                "Task queue inflight checkpoint list failed",
                exc,
                error_code="task_queue_inflight_list_failed",
            )
            raise RepositoryError(
                "Task queue inflight checkpoint list failed",
                error_code="task_queue_inflight_list_failed",
            ) from exc

    def try_upsert(self, fields: Dict[str, Any]) -> bool:
        """Best-effort upsert that never aborts live execution."""
        try:
            self.upsert(fields)
            return True
        except (RepositoryError, ValueError) as exc:
            log_safe_exception(
                logger,
                "Task queue inflight checkpoint upsert degraded",
                exc,
                error_code="task_queue_inflight_upsert_degraded",
                level=logging.WARNING,
                context={"task_id": str(fields.get("task_id") or "")},
            )
            return False

    def try_delete(self, task_id: str) -> bool:
        """Best-effort delete that never aborts live execution."""
        try:
            self.delete(task_id)
            return True
        except RepositoryError as exc:
            log_safe_exception(
                logger,
                "Task queue inflight checkpoint delete degraded",
                exc,
                error_code="task_queue_inflight_delete_degraded",
                level=logging.WARNING,
                context={"task_id": str(task_id or "")},
            )
            return False
