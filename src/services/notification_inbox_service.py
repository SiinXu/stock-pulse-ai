# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Durable, best-effort read model for the in-app notification inbox."""

from __future__ import annotations

import base64
import binascii
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Any, Callable, Dict, List, Optional, Sequence

from sqlalchemy.exc import SQLAlchemyError

from src.repositories.alert_repo import AlertRepository
from src.repositories.base import RepositoryError
from src.repositories.decision_signal_repo import DecisionSignalRepository
from src.repositories.notification_inbox_repo import NotificationInboxRepository
from src.repositories.scheduled_task_repo import ScheduledTaskRepository
from src.schemas.notification_inbox import (
    INBOX_KIND_VALUES,
    NOTIFICATION_INBOX_MAX_CURSOR_LENGTH,
    NOTIFICATION_INBOX_MAX_ITEMS_DEFAULT,
    NOTIFICATION_INBOX_MAX_PAGE_SIZE,
    NOTIFICATION_INBOX_RETENTION_DAYS_DEFAULT,
    NotificationInboxItem,
    NotificationInboxKind,
    NotificationInboxMarkAllReadResult,
    NotificationInboxMarkReadResult,
    NotificationInboxPage,
    NotificationInboxRetentionResult,
    NotificationInboxSeverity,
    NotificationInboxSource,
    NotificationInboxSourceStatus,
    NotificationInboxTitleKey,
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

_KIND_TO_SOURCE: dict[str, NotificationInboxSource] = {
    "analysis_complete": "analysis",
    "alert_triggered": "alerts",
    "scheduled_task_result": "scheduled_tasks",
    "decision_signal": "decision_signals",
}


class NotificationInboxValidationError(ValueError):
    """Raised for invalid inbox query or mutation parameters."""

    def __init__(self, message: str, *, error_code: str = "validation_error") -> None:
        super().__init__(message)
        self.error_code = error_code


@dataclass(frozen=True)
class _ProjectedItem:
    kind: NotificationInboxKind
    source_id: str
    title_key: NotificationInboxTitleKey
    title_params: Dict[str, str]
    summary: str
    severity: NotificationInboxSeverity
    created_at: datetime
    href: str
    metadata: Dict[str, Any]

    @property
    def item_id(self) -> str:
        return build_inbox_item_id(self.kind, self.source_id, self.created_at)

    @property
    def sort_key(self) -> tuple[datetime, str]:
        return self.created_at, self.item_id


@dataclass(frozen=True)
class _ProjectionWindow:
    items: List[_ProjectedItem]
    source_statuses: List[NotificationInboxSourceStatus]


class NotificationInboxService:
    """Aggregate durable occurrences into one cursor-paginated inbox."""

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
        clock: Optional[Callable[[], datetime]] = None,
        local_timezone: Optional[tzinfo] = None,
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
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._local_timezone = (
            local_timezone
            or datetime.now().astimezone().tzinfo
            or timezone.utc
        )

    def list_items(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        cursor: Optional[str] = None,
        kind: Optional[str] = None,
        unread_only: bool = False,
    ) -> NotificationInboxPage:
        safe_page = max(1, int(page))
        safe_page_size = max(1, min(int(page_size), NOTIFICATION_INBOX_MAX_PAGE_SIZE))
        kind_filter = self._normalize_kind_filter(kind)
        cursor_key = self._decode_cursor(cursor) if cursor else None
        self._apply_time_retention()

        window = self._project_window(kind_filter=kind_filter)
        read_ids = self.repository.list_read_item_ids(
            [item.item_id for item in window.items]
        )
        items = [
            self._to_item(row, is_read=row.item_id in read_ids)
            for row in window.items
        ]
        unread_total = sum(1 for item in items if not item.is_read)
        if unread_only:
            items = [item for item in items if not item.is_read]
        total = len(items)

        if cursor_key is not None:
            items = [item for item in items if self._item_sort_key(item) < cursor_key]
            offset = 0
        else:
            offset = (safe_page - 1) * safe_page_size
        page_items = items[offset: offset + safe_page_size]
        has_more = offset + len(page_items) < len(items)
        next_cursor = (
            self._encode_cursor(page_items[-1])
            if has_more and page_items
            else None
        )
        return NotificationInboxPage(
            items=page_items,
            page=safe_page,
            page_size=safe_page_size,
            total=total,
            unread_total=unread_total,
            cursor=cursor,
            next_cursor=next_cursor,
            has_more=has_more,
            source_statuses=window.source_statuses,
            retention_days=self.retention_days,
            max_items=self.max_items,
        )

    def get_unread_count(self, *, kind: Optional[str] = None) -> NotificationInboxUnreadCount:
        kind_filter = self._normalize_kind_filter(kind)
        self._apply_time_retention()
        window = self._project_window(kind_filter=kind_filter)
        read_ids = self.repository.list_read_item_ids(
            [item.item_id for item in window.items]
        )
        unread_total = sum(
            1 for item in window.items if item.item_id not in read_ids
        )
        return NotificationInboxUnreadCount(
            unread_total=unread_total,
            source_statuses=window.source_statuses,
            retention_days=self.retention_days,
            max_items=self.max_items,
        )

    def mark_read(self, item_ids: Sequence[str]) -> NotificationInboxMarkReadResult:
        normalized_ids: list[str] = []
        parsed_by_id: dict[str, tuple[str, str, int]] = {}
        for raw in item_ids:
            item_id = str(raw).strip()
            parsed = parse_inbox_item_id(item_id)
            if parsed is None:
                raise NotificationInboxValidationError(
                    "Invalid inbox item id",
                    error_code="invalid_item_id",
                )
            if item_id not in parsed_by_id:
                normalized_ids.append(item_id)
                parsed_by_id[item_id] = parsed
        if not normalized_ids or len(normalized_ids) > NOTIFICATION_INBOX_MAX_PAGE_SIZE:
            raise NotificationInboxValidationError(
                "Mark-read requires 1-100 unique item ids",
                error_code="invalid_item_count",
            )

        window = self._project_window(kind_filter=None)
        status_by_source = {
            status.source: status for status in window.source_statuses
        }
        available_ids = {item.item_id for item in window.items}
        for item_id in normalized_ids:
            kind, _source_id, _occurred_at = parsed_by_id[item_id]
            source = _KIND_TO_SOURCE[kind]
            status = status_by_source[source]
            if not status.available:
                raise RepositoryError(
                    "Notification source unavailable during mark-read validation",
                    error_code="notification_inbox_source_unavailable",
                    context={"source": source},
                )
            if item_id not in available_ids:
                raise NotificationInboxValidationError(
                    "Inbox item does not exist in the authoritative retention window",
                    error_code="unknown_item_id",
                )

        pairs = [(item_id, parsed_by_id[item_id][0]) for item_id in normalized_ids]
        marked_count = self.repository.mark_read(pairs)
        unread = self.get_unread_count()
        return NotificationInboxMarkReadResult(
            marked_count=marked_count,
            unread_total=unread.unread_total,
        )

    def mark_all_read(self, *, kind: Optional[str] = None) -> NotificationInboxMarkAllReadResult:
        kind_filter = self._normalize_kind_filter(kind)
        window = self._project_window(kind_filter=kind_filter)
        unavailable = [status.source for status in window.source_statuses if not status.available]
        if unavailable:
            raise RepositoryError(
                "Cannot mark all notifications read while sources are unavailable",
                error_code="notification_inbox_partial_source",
                context={"sources": unavailable},
            )
        pairs = [(item.item_id, item.kind) for item in window.items]
        marked_count = self.repository.mark_read(pairs)
        self.apply_retention(window=window)
        unread = self.get_unread_count(kind=kind_filter)
        return NotificationInboxMarkAllReadResult(
            marked_count=marked_count,
            unread_total=unread.unread_total,
        )

    def apply_retention(
        self,
        *,
        window: Optional[_ProjectionWindow] = None,
    ) -> NotificationInboxRetentionResult:
        """Prune old markers and orphans only from a complete source window."""
        cutoff = self._now_utc() - timedelta(days=self.retention_days)
        deleted_by_time = self.repository.delete_read_before(cutoff)
        current_window = window or self._project_window(kind_filter=None)
        if any(not status.available for status in current_window.source_statuses):
            return NotificationInboxRetentionResult(
                deleted_count=deleted_by_time,
                cutoff=cutoff,
                retention_days=self.retention_days,
            )
        window_ids = [item.item_id for item in current_window.items]
        deleted_orphans = self.repository.delete_read_not_in(window_ids)
        return NotificationInboxRetentionResult(
            deleted_count=deleted_by_time + deleted_orphans,
            cutoff=cutoff,
            retention_days=self.retention_days,
        )

    def _apply_time_retention(self) -> None:
        cutoff = self._now_utc() - timedelta(days=self.retention_days)
        self.repository.delete_read_before(cutoff)

    def _project_window(self, *, kind_filter: Optional[str]) -> _ProjectionWindow:
        now_utc = self._now_utc()
        cutoff_utc = now_utc - timedelta(days=self.retention_days)
        selected_sources = (
            {_KIND_TO_SOURCE[kind_filter]}
            if kind_filter is not None
            else set(_KIND_TO_SOURCE.values())
        )
        source_loaders: list[
            tuple[NotificationInboxSource, Callable[[], List[_ProjectedItem]]]
        ] = [
            (
                "analysis",
                lambda: self._project_analysis(cutoff_utc=cutoff_utc),
            ),
            (
                "alerts",
                lambda: self._project_alerts(cutoff_utc=cutoff_utc),
            ),
            (
                "scheduled_tasks",
                lambda: self._project_scheduled_runs(
                    cutoff_utc=cutoff_utc,
                    now_utc=now_utc,
                ),
            ),
            (
                "decision_signals",
                lambda: self._project_decision_signals(cutoff_utc=cutoff_utc),
            ),
        ]

        projected: list[_ProjectedItem] = []
        statuses: list[NotificationInboxSourceStatus] = []
        for source, loader in source_loaders:
            if source not in selected_sources:
                continue
            try:
                source_items = loader()
            except (RepositoryError, SQLAlchemyError) as exc:
                error_code = (
                    getattr(exc, "error_code", None)
                    or f"notification_inbox_{source}_projection_failed"
                )
                log_safe_exception(
                    logger,
                    "Notification inbox source projection failed",
                    exc,
                    error_code=error_code,
                    context={"source": source},
                )
                statuses.append(
                    NotificationInboxSourceStatus(
                        source=source,
                        available=False,
                        item_count=0,
                        error_code=error_code,
                    )
                )
                continue
            projected.extend(source_items)
            statuses.append(
                NotificationInboxSourceStatus(
                    source=source,
                    available=True,
                    item_count=len(source_items),
                )
            )

        if not statuses or all(not status.available for status in statuses):
            raise RepositoryError(
                "No notification inbox source is available",
                error_code="notification_inbox_no_source_available",
            )

        projected = [
            item for item in projected if item.created_at >= cutoff_utc
        ]
        projected.sort(key=lambda item: item.sort_key, reverse=True)
        return _ProjectionWindow(
            items=projected[: self.max_items],
            source_statuses=statuses,
        )

    def _project_analysis(self, *, cutoff_utc: datetime) -> List[_ProjectedItem]:
        rows: List[AnalysisHistory] = self.db.get_analysis_history(
            days=self.retention_days,
            limit=self.max_items,
        )
        items: List[_ProjectedItem] = []
        for row in rows:
            created_at = self._local_naive_to_utc(row.created_at)
            if created_at < cutoff_utc:
                continue
            code = (row.code or "").strip() or "unknown"
            name = (row.name or "").strip()
            label = name or code
            advice = (row.operation_advice or "").strip()
            summary_bits = [
                bit
                for bit in (advice, (row.analysis_summary or "").strip())
                if bit
            ]
            summary = " · ".join(summary_bits) or str(row.report_type or "stock")
            record_id = int(row.id)
            items.append(
                _ProjectedItem(
                    kind="analysis_complete",
                    source_id=str(record_id),
                    title_key="analysisCompleteTitle",
                    title_params={"label": label},
                    summary=summary[:280],
                    severity="info",
                    created_at=created_at,
                    href=f"/research/analysis?segment=history&recordId={record_id}",
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

    def _project_alerts(self, *, cutoff_utc: datetime) -> List[_ProjectedItem]:
        rows, _total = self.alert_repository.list_triggers(
            page=1,
            page_size=self.max_items,
        )
        items: List[_ProjectedItem] = []
        for row in rows:
            created_at = self._local_naive_to_utc(row.triggered_at)
            if created_at < cutoff_utc:
                continue
            trigger_id = int(row.id)
            target = (row.target or "").strip() or "unknown"
            reason = (row.reason or "").strip() or (row.status or "triggered")
            items.append(
                _ProjectedItem(
                    kind="alert_triggered",
                    source_id=str(trigger_id),
                    title_key="alertTriggeredTitle",
                    title_params={"target": target},
                    summary=reason[:280],
                    severity="warning",
                    created_at=created_at,
                    href=f"/signals?tab=history&trigger={trigger_id}",
                    metadata={
                        "trigger_id": trigger_id,
                        "rule_id": row.rule_id,
                        "target": target,
                        "status": row.status,
                    },
                )
            )
        return items

    def _project_scheduled_runs(
        self,
        *,
        cutoff_utc: datetime,
        now_utc: datetime,
    ) -> List[_ProjectedItem]:
        rows = self.scheduled_task_repository.list_recent_runs_between(
            start=cutoff_utc.replace(tzinfo=None),
            end=(now_utc + timedelta(days=1)).replace(tzinfo=None),
            statuses=tuple(_TERMINAL_SCHEDULED_STATUSES),
            limit=self.max_items,
        )
        items: List[_ProjectedItem] = []
        for row in rows:
            status = (row.status or "").strip().lower()
            created_at = self._utc_naive_to_utc(
                row.finished_at or row.updated_at or row.created_at or row.scheduled_for
            )
            if created_at < cutoff_utc:
                continue
            run_id = str(row.id)
            task_id = str(row.task_id)
            severity: NotificationInboxSeverity = (
                "error" if status == ScheduledRunStatus.FAILED.value else "info"
            )
            if status == ScheduledRunStatus.INTERRUPTED.value:
                severity = "warning"
            error_code = (row.error_code or "").strip()
            summary = error_code or self._format_datetime(row.scheduled_for)
            items.append(
                _ProjectedItem(
                    kind="scheduled_task_result",
                    source_id=run_id,
                    title_key="scheduledTaskResultTitle",
                    title_params={"taskId": task_id},
                    summary=summary[:280],
                    severity=severity,
                    created_at=created_at,
                    href="/settings?section=system_security&view=runtime",
                    metadata={
                        "run_id": run_id,
                        "task_id": task_id,
                        "status": status,
                        "error_code": error_code or None,
                    },
                )
            )
        return items

    def _project_decision_signals(self, *, cutoff_utc: datetime) -> List[_ProjectedItem]:
        rows: list[Any] = []
        page = 1
        while len(rows) < self.max_items:
            page_size = min(100, self.max_items - len(rows))
            batch, total = self.decision_signal_repository.list(
                status=None,
                created_from=cutoff_utc.replace(tzinfo=None),
                page=page,
                page_size=page_size,
            )
            rows.extend(batch)
            if len(batch) < page_size or len(rows) >= total:
                break
            page += 1

        items: List[_ProjectedItem] = []
        for row in rows[: self.max_items]:
            created_at = self._utc_naive_to_utc(row.created_at)
            if created_at < cutoff_utc:
                continue
            signal_id = int(row.id)
            stock_code = (row.stock_code or "").strip() or "unknown"
            stock_name = (getattr(row, "stock_name", None) or "").strip()
            label = (row.action_label or row.action or "").strip() or "signal"
            items.append(
                _ProjectedItem(
                    kind="decision_signal",
                    source_id=str(signal_id),
                    title_key="decisionSignalTitle",
                    title_params={"label": stock_name or stock_code},
                    summary=label[:280],
                    severity="info",
                    created_at=created_at,
                    href=f"/signals?signal={signal_id}",
                    metadata={
                        "signal_id": signal_id,
                        "stock_code": stock_code,
                        "stock_name": stock_name or None,
                        "action": row.action,
                        "status": row.status,
                    },
                )
            )
        return items

    @staticmethod
    def _to_item(row: _ProjectedItem, *, is_read: bool) -> NotificationInboxItem:
        return NotificationInboxItem(
            id=row.item_id,
            kind=row.kind,
            title_key=row.title_key,
            title_params=dict(row.title_params),
            summary=row.summary,
            severity=row.severity,
            created_at=row.created_at,
            is_read=is_read,
            href=row.href,
            source_id=row.source_id,
            metadata=dict(row.metadata),
        )

    def _now_utc(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _local_naive_to_utc(self, value: Optional[datetime]) -> datetime:
        if value is None:
            return datetime(1970, 1, 1, tzinfo=timezone.utc)
        if value.tzinfo is not None and value.utcoffset() is not None:
            return value.astimezone(timezone.utc)
        return value.replace(tzinfo=self._local_timezone).astimezone(timezone.utc)

    @staticmethod
    def _utc_naive_to_utc(value: Optional[datetime]) -> datetime:
        if value is None:
            return datetime(1970, 1, 1, tzinfo=timezone.utc)
        if value.tzinfo is not None and value.utcoffset() is not None:
            return value.astimezone(timezone.utc)
        return value.replace(tzinfo=timezone.utc)

    @staticmethod
    def _format_datetime(value: Optional[datetime]) -> str:
        if value is None:
            return ""
        return value.isoformat(timespec="seconds")

    @staticmethod
    def _item_sort_key(item: NotificationInboxItem) -> tuple[datetime, str]:
        created_at = item.created_at
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return created_at.astimezone(timezone.utc), item.id

    @staticmethod
    def _encode_cursor(item: NotificationInboxItem) -> str:
        payload = json.dumps(
            {
                "v": 1,
                "created_at": item.created_at.astimezone(timezone.utc).isoformat(),
                "id": item.id,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")

    @staticmethod
    def _decode_cursor(cursor: str) -> tuple[datetime, str]:
        normalized = str(cursor).strip()
        if not normalized or len(normalized) > NOTIFICATION_INBOX_MAX_CURSOR_LENGTH:
            raise NotificationInboxValidationError(
                "Invalid notification inbox cursor",
                error_code="invalid_cursor",
            )
        try:
            padded = normalized + "=" * (-len(normalized) % 4)
            raw = base64.b64decode(padded, altchars=b"-_", validate=True)
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict) or payload.get("v") != 1:
                raise ValueError("unsupported cursor version")
            item_id = str(payload.get("id") or "")
            if parse_inbox_item_id(item_id) is None:
                raise ValueError("invalid cursor item id")
            created_at = datetime.fromisoformat(str(payload.get("created_at") or ""))
            if created_at.tzinfo is None or created_at.utcoffset() is None:
                raise ValueError("cursor timestamp must include an offset")
            return created_at.astimezone(timezone.utc), item_id
        except (
            binascii.Error,
            json.JSONDecodeError,
            TypeError,
            UnicodeDecodeError,
            ValueError,
        ) as exc:
            raise NotificationInboxValidationError(
                "Invalid notification inbox cursor",
                error_code="invalid_cursor",
            ) from exc

    @staticmethod
    def _normalize_kind_filter(kind: Optional[str]) -> Optional[str]:
        if kind is None or str(kind).strip() == "":
            return None
        normalized = str(kind).strip()
        if normalized not in INBOX_KIND_VALUES:
            raise NotificationInboxValidationError(
                "Unsupported inbox kind",
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
                        "Invalid %s value; using default %s",
                        env_key,
                        default,
                    )
                    value = default
        return max(minimum, min(value, maximum))
