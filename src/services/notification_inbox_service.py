# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""In-app notification inbox: aggregate existing event sources (plan A).

This service is a read-side consumer. It does not call NotificationService or
mutate alert / scheduled-task business logic. Items are projected from durable
tables; only read markers are written to notification_inbox_read_state.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

from src.repositories.alert_repo import AlertRepository
from src.repositories.base import RepositoryError
from src.repositories.decision_signal_repo import DecisionSignalRepository
from src.repositories.notification_inbox_repo import NotificationInboxRepository
from src.repositories.scheduled_task_repo import ScheduledTaskRepository
from src.schemas.notification_inbox import (
    INBOX_KIND_VALUES,
    NOTIFICATION_INBOX_MAX_ITEMS_DEFAULT,
    NOTIFICATION_INBOX_MAX_PAGE_SIZE,
    NOTIFICATION_INBOX_RETENTION_DAYS_DEFAULT,
    NOTIFICATION_INBOX_SOURCE_FETCH_LIMIT,
    NotificationInboxItem,
    NotificationInboxKind,
    NotificationInboxMarkAllReadResult,
    NotificationInboxMarkReadResult,
    NotificationInboxPage,
    NotificationInboxRetentionResult,
    NotificationInboxSeverity,
    NotificationInboxUnreadCount,
    build_inbox_item_id,
    parse_inbox_item_id,
)
from src.schemas.scheduled_task import ScheduledRunStatus
from src.storage import AnalysisHistory, DatabaseManager
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

_TERMINAL_SCHEDULED_STATUSES = frozenset({
    ScheduledRunStatus.SUCCEEDED.value,
    ScheduledRunStatus.FAILED.value,
    ScheduledRunStatus.SKIPPED.value,
    ScheduledRunStatus.INTERRUPTED.value,
})


class NotificationInboxValidationError(ValueError):
    """Raised for invalid inbox query or mutation parameters."""

    def __init__(self, message: str, *, error_code: str = "validation_error") -> None:
        super().__init__(message)
        self.error_code = error_code


@dataclass(frozen=True)
class _ProjectedItem:
    kind: NotificationInboxKind
    source_id: str
    title: str
    summary: str
    severity: NotificationInboxSeverity
    created_at: datetime
    href: str
    metadata: Dict[str, Any]

    @property
    def item_id(self) -> str:
        return build_inbox_item_id(self.kind, self.source_id)


class NotificationInboxService:
    """Aggregate durable events into a paginated, markable inbox."""

    def __init__(
        self,
        db_manager: Optional[DatabaseManager] = None,
        *,
        repository: Optional[NotificationInboxRepository] = None,
        alert_repository: Optional[AlertRepository] = None,
        scheduled_task_repository: Optional[ScheduledTaskRepository] = None,
        decision_signal_repository: Optional[DecisionSignalRepository] = None,
        retention_days: Optional[int] = None,
        max_items: Optional[int] = None,
    ) -> None:
        self.db = db_manager or DatabaseManager.get_instance()
        self.repository = repository or NotificationInboxRepository(self.db)
        self.alert_repository = alert_repository or AlertRepository(self.db)
        self.scheduled_task_repository = (
            scheduled_task_repository or ScheduledTaskRepository(self.db)
        )
        self.decision_signal_repository = (
            decision_signal_repository or DecisionSignalRepository(self.db)
        )
        self.retention_days = self._resolve_positive_int(
            retention_days,
            env_key="NOTIFICATION_INBOX_RETENTION_DAYS",
            default=NOTIFICATION_INBOX_RETENTION_DAYS_DEFAULT,
            minimum=1,
            maximum=3650,
        )
        self.max_items = self._resolve_positive_int(
            max_items,
            env_key="NOTIFICATION_INBOX_MAX_ITEMS",
            default=NOTIFICATION_INBOX_MAX_ITEMS_DEFAULT,
            minimum=10,
            maximum=5000,
        )

    def list_items(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        kind: Optional[str] = None,
        unread_only: bool = False,
    ) -> NotificationInboxPage:
        safe_page = max(1, int(page))
        safe_page_size = max(1, min(int(page_size), NOTIFICATION_INBOX_MAX_PAGE_SIZE))
        kind_filter = self._normalize_kind_filter(kind)

        projected = self._project_window(kind_filter=kind_filter)
        read_ids = self.repository.list_read_item_ids([item.item_id for item in projected])
        items = [self._to_item(row, is_read=row.item_id in read_ids) for row in projected]
        unread_total = sum(1 for item in items if not item.is_read)
        if unread_only:
            items = [item for item in items if not item.is_read]
        total = len(items)
        offset = (safe_page - 1) * safe_page_size
        page_items = items[offset: offset + safe_page_size]
        return NotificationInboxPage(
            items=page_items,
            page=safe_page,
            page_size=safe_page_size,
            total=total,
            unread_total=unread_total,
            retention_days=self.retention_days,
            max_items=self.max_items,
        )

    def get_unread_count(self, *, kind: Optional[str] = None) -> NotificationInboxUnreadCount:
        kind_filter = self._normalize_kind_filter(kind)
        projected = self._project_window(kind_filter=kind_filter)
        read_ids = self.repository.list_read_item_ids([item.item_id for item in projected])
        unread_total = sum(1 for item in projected if item.item_id not in read_ids)
        return NotificationInboxUnreadCount(
            unread_total=unread_total,
            retention_days=self.retention_days,
            max_items=self.max_items,
        )

    def mark_read(self, item_ids: Sequence[str]) -> NotificationInboxMarkReadResult:
        pairs: list[tuple[str, str]] = []
        for raw in item_ids:
            parsed = parse_inbox_item_id(str(raw).strip())
            if parsed is None:
                raise NotificationInboxValidationError(
                    f"Invalid inbox item id: {raw!r}",
                    error_code="invalid_item_id",
                )
            kind, _source_id = parsed
            pairs.append((str(raw).strip(), kind))
        marked_count = self.repository.mark_read(pairs)
        unread = self.get_unread_count()
        return NotificationInboxMarkReadResult(
            marked_count=marked_count,
            unread_total=unread.unread_total,
        )

    def mark_all_read(self, *, kind: Optional[str] = None) -> NotificationInboxMarkAllReadResult:
        kind_filter = self._normalize_kind_filter(kind)
        projected = self._project_window(kind_filter=kind_filter)
        pairs = [(item.item_id, item.kind) for item in projected]
        marked_count = self.repository.mark_read(pairs)
        unread = self.get_unread_count(kind=kind_filter)
        return NotificationInboxMarkAllReadResult(
            marked_count=marked_count,
            unread_total=unread.unread_total,
        )

    def apply_retention(self) -> NotificationInboxRetentionResult:
        """Prune stale read markers (time window + orphans outside current items)."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.retention_days)
        deleted_by_time = self.repository.delete_read_before(cutoff)
        window_ids = [item.item_id for item in self._project_window(kind_filter=None)]
        deleted_orphans = self.repository.delete_read_not_in(window_ids)
        return NotificationInboxRetentionResult(
            deleted_count=deleted_by_time + deleted_orphans,
            cutoff=cutoff,
            retention_days=self.retention_days,
        )

    def _project_window(
        self,
        *,
        kind_filter: Optional[str],
    ) -> List[_ProjectedItem]:
        cutoff = datetime.now() - timedelta(days=self.retention_days)
        fetch_limit = min(NOTIFICATION_INBOX_SOURCE_FETCH_LIMIT, self.max_items)
        projected: List[_ProjectedItem] = []

        if kind_filter in (None, "analysis_complete"):
            projected.extend(self._project_analysis(cutoff=cutoff, limit=fetch_limit))
        if kind_filter in (None, "alert_triggered"):
            projected.extend(self._project_alerts(limit=fetch_limit))
        if kind_filter in (None, "scheduled_task_result"):
            projected.extend(self._project_scheduled_runs(cutoff=cutoff, limit=fetch_limit))
        if kind_filter in (None, "decision_signal"):
            projected.extend(self._project_decision_signals(limit=fetch_limit))

        projected = [
            item for item in projected
            if self._as_naive(item.created_at) >= self._as_naive(cutoff)
        ]
        projected.sort(
            key=lambda item: (self._as_naive(item.created_at), item.item_id),
            reverse=True,
        )
        if len(projected) > self.max_items:
            projected = projected[: self.max_items]
        return projected

    def _project_analysis(self, *, cutoff: datetime, limit: int) -> List[_ProjectedItem]:
        try:
            rows: List[AnalysisHistory] = self.db.get_analysis_history(
                days=self.retention_days,
                limit=limit,
            )
        except Exception as exc:
            log_safe_exception(
                logger,
                "Notification inbox analysis projection failed",
                exc,
                error_code="notification_inbox_analysis_projection_failed",
            )
            raise RepositoryError(
                "Notification inbox analysis projection failed",
                error_code="notification_inbox_analysis_projection_failed",
            ) from exc

        items: List[_ProjectedItem] = []
        for row in rows:
            created_at = row.created_at or cutoff
            if self._as_naive(created_at) < self._as_naive(cutoff):
                continue
            code = (row.code or "").strip() or "unknown"
            name = (row.name or "").strip()
            title = f"Analysis complete: {name or code}"
            advice = (row.operation_advice or "").strip()
            summary_bits = [bit for bit in (advice, (row.analysis_summary or "").strip()) if bit]
            summary = (
                " · ".join(summary_bits)
                if summary_bits
                else f"Report type: {row.report_type or 'stock'}"
            )
            record_id = int(row.id)
            href = f"/research/analysis?segment=history&recordId={record_id}"
            items.append(
                _ProjectedItem(
                    kind="analysis_complete",
                    source_id=str(record_id),
                    title=title,
                    summary=summary[:280],
                    severity="info",
                    created_at=created_at,
                    href=href,
                    metadata={
                        "record_id": record_id,
                        "stock_code": code,
                        "stock_name": name or None,
                        "report_type": row.report_type,
                        "query_id": row.query_id,
                    },
                )
            )
        return items

    def _project_alerts(self, *, limit: int) -> List[_ProjectedItem]:
        try:
            rows, _total = self.alert_repository.list_triggers(page=1, page_size=limit)
        except Exception as exc:
            log_safe_exception(
                logger,
                "Notification inbox alert projection failed",
                exc,
                error_code="notification_inbox_alert_projection_failed",
            )
            raise RepositoryError(
                "Notification inbox alert projection failed",
                error_code="notification_inbox_alert_projection_failed",
            ) from exc

        items: List[_ProjectedItem] = []
        for row in rows:
            trigger_id = int(row.id)
            created_at = row.triggered_at or datetime.now()
            target = (row.target or "").strip() or "unknown"
            reason = (row.reason or "").strip() or (row.status or "triggered")
            href = f"/signals?tab=history&trigger={trigger_id}"
            items.append(
                _ProjectedItem(
                    kind="alert_triggered",
                    source_id=str(trigger_id),
                    title=f"Alert triggered: {target}",
                    summary=reason[:280],
                    severity="warning",
                    created_at=created_at,
                    href=href,
                    metadata={
                        "trigger_id": trigger_id,
                        "rule_id": row.rule_id,
                        "target": target,
                        "status": row.status,
                    },
                )
            )
        return items

    def _project_scheduled_runs(self, *, cutoff: datetime, limit: int) -> List[_ProjectedItem]:
        end = datetime.now() + timedelta(days=1)
        try:
            rows = self.scheduled_task_repository.list_runs_between(
                start=cutoff,
                end=end,
                limit=limit,
            )
        except Exception as exc:
            log_safe_exception(
                logger,
                "Notification inbox scheduled-run projection failed",
                exc,
                error_code="notification_inbox_scheduled_projection_failed",
            )
            raise RepositoryError(
                "Notification inbox scheduled-run projection failed",
                error_code="notification_inbox_scheduled_projection_failed",
            ) from exc

        items: List[_ProjectedItem] = []
        for row in rows:
            status = (row.status or "").strip().lower()
            if status not in _TERMINAL_SCHEDULED_STATUSES:
                continue
            created_at = row.finished_at or row.updated_at or row.created_at or cutoff
            run_id = str(row.id)
            task_id = str(row.task_id)
            severity: NotificationInboxSeverity = (
                "error" if status == ScheduledRunStatus.FAILED.value else "info"
            )
            if status == ScheduledRunStatus.INTERRUPTED.value:
                severity = "warning"
            title = f"Scheduled task {status}: {task_id}"
            error_code = (row.error_code or "").strip()
            summary = error_code or f"Occurrence {row.scheduled_for}"
            href = "/settings?section=system_security&view=runtime"
            items.append(
                _ProjectedItem(
                    kind="scheduled_task_result",
                    source_id=run_id,
                    title=title,
                    summary=str(summary)[:280],
                    severity=severity,
                    created_at=created_at,
                    href=href,
                    metadata={
                        "run_id": run_id,
                        "task_id": task_id,
                        "status": status,
                        "error_code": error_code or None,
                    },
                )
            )
        return items

    def _project_decision_signals(self, *, limit: int) -> List[_ProjectedItem]:
        try:
            rows, _total = self.decision_signal_repository.list(
                status="active",
                page=1,
                page_size=limit,
            )
        except Exception as exc:
            log_safe_exception(
                logger,
                "Notification inbox decision-signal projection failed",
                exc,
                error_code="notification_inbox_signal_projection_failed",
            )
            raise RepositoryError(
                "Notification inbox decision-signal projection failed",
                error_code="notification_inbox_signal_projection_failed",
            ) from exc

        items: List[_ProjectedItem] = []
        for row in rows:
            signal_id = int(row.id)
            created_at = row.created_at or datetime.now()
            stock_code = (row.stock_code or "").strip() or "unknown"
            stock_name = (getattr(row, "stock_name", None) or "").strip()
            label = (row.action_label or row.action or "").strip() or "signal"
            title = f"Decision signal: {stock_name or stock_code}"
            href = f"/signals?signal={signal_id}"
            items.append(
                _ProjectedItem(
                    kind="decision_signal",
                    source_id=str(signal_id),
                    title=title,
                    summary=label[:280],
                    severity="info",
                    created_at=created_at,
                    href=href,
                    metadata={
                        "signal_id": signal_id,
                        "stock_code": stock_code,
                        "stock_name": stock_name or None,
                        "action": row.action,
                    },
                )
            )
        return items

    @staticmethod
    def _to_item(row: _ProjectedItem, *, is_read: bool) -> NotificationInboxItem:
        created_at = row.created_at
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return NotificationInboxItem(
            id=row.item_id,
            kind=row.kind,
            title=row.title,
            summary=row.summary,
            severity=row.severity,
            created_at=created_at,
            is_read=is_read,
            href=row.href,
            source_id=row.source_id,
            metadata=dict(row.metadata),
        )

    @staticmethod
    def _as_naive(value: datetime) -> datetime:
        if value.tzinfo is not None and value.utcoffset() is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    @staticmethod
    def _normalize_kind_filter(kind: Optional[str]) -> Optional[str]:
        if kind is None or str(kind).strip() == "":
            return None
        normalized = str(kind).strip()
        if normalized not in INBOX_KIND_VALUES:
            raise NotificationInboxValidationError(
                f"Unsupported inbox kind: {kind}",
                error_code="invalid_kind",
            )
        return normalized

    @staticmethod
    def _resolve_positive_int(
        explicit: Optional[int],
        *,
        env_key: str,
        default: int,
        minimum: int,
        maximum: int,
    ) -> int:
        if explicit is not None:
            value = int(explicit)
        else:
            raw = os.getenv(env_key, "").strip()
            if not raw:
                value = default
            else:
                try:
                    value = int(raw)
                except ValueError:
                    logger.warning(
                        "Invalid %s=%r; using default %s",
                        env_key,
                        raw,
                        default,
                    )
                    value = default
        if value < minimum:
            return minimum
        if value > maximum:
            return maximum
        return value
