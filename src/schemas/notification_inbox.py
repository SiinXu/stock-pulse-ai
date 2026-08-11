# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Domain models and defaults for the in-app notification inbox."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


NOTIFICATION_INBOX_RETENTION_DAYS_DEFAULT = 90
NOTIFICATION_INBOX_MAX_ITEMS_DEFAULT = 500
NOTIFICATION_INBOX_MAX_PAGE_SIZE = 100
NOTIFICATION_INBOX_MAX_ITEM_ID_LENGTH = 128
NOTIFICATION_INBOX_MAX_CURSOR_LENGTH = 512

NotificationInboxKind = Literal[
    "analysis_complete",
    "alert_triggered",
    "scheduled_task_result",
    "decision_signal",
]

NotificationInboxSeverity = Literal["info", "warning", "error"]

NotificationInboxSource = Literal[
    "analysis",
    "alerts",
    "scheduled_tasks",
    "decision_signals",
]

NotificationInboxTitleKey = Literal[
    "analysisCompleteTitle",
    "alertTriggeredTitle",
    "scheduledTaskResultTitle",
    "decisionSignalTitle",
]

INBOX_KIND_VALUES: tuple[str, ...] = (
    "analysis_complete",
    "alert_triggered",
    "scheduled_task_result",
    "decision_signal",
)

INBOX_SOURCE_VALUES: tuple[str, ...] = (
    "analysis",
    "alerts",
    "scheduled_tasks",
    "decision_signals",
)

_SOURCE_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class NotificationInboxSourceStatus(BaseModel):
    """Availability and bounded provenance for one selected inbox source."""

    model_config = ConfigDict(extra="forbid")

    source: NotificationInboxSource
    available: bool
    item_count: int = Field(..., ge=0)
    error_code: Optional[str] = Field(default=None, max_length=120)


class NotificationInboxItem(BaseModel):
    """One aggregated inbox row projected from durable event sources."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        ...,
        max_length=NOTIFICATION_INBOX_MAX_ITEM_ID_LENGTH,
        description="Versioned stable occurrence key",
    )
    kind: NotificationInboxKind
    title_key: NotificationInboxTitleKey
    title_params: Dict[str, str] = Field(default_factory=dict)
    summary: str
    severity: NotificationInboxSeverity = "info"
    created_at: datetime
    is_read: bool = False
    href: str = Field(..., description="In-app deep link path with query string")
    source_id: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class NotificationInboxPage(BaseModel):
    """Paginated inbox listing with unread total for the current filter window."""

    model_config = ConfigDict(extra="forbid")

    items: list[NotificationInboxItem]
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1, le=NOTIFICATION_INBOX_MAX_PAGE_SIZE)
    total: int = Field(..., ge=0)
    unread_total: int = Field(..., ge=0)
    cursor: Optional[str] = Field(default=None, max_length=NOTIFICATION_INBOX_MAX_CURSOR_LENGTH)
    next_cursor: Optional[str] = Field(default=None, max_length=NOTIFICATION_INBOX_MAX_CURSOR_LENGTH)
    has_more: bool = False
    source_statuses: list[NotificationInboxSourceStatus] = Field(default_factory=list)
    retention_days: int = Field(..., ge=1)
    max_items: int = Field(..., ge=1)


class NotificationInboxUnreadCount(BaseModel):
    """Unread count for the current retention window."""

    model_config = ConfigDict(extra="forbid")

    unread_total: int = Field(..., ge=0)
    source_statuses: list[NotificationInboxSourceStatus] = Field(default_factory=list)
    retention_days: int = Field(..., ge=1)
    max_items: int = Field(..., ge=1)


class NotificationInboxMarkReadResult(BaseModel):
    """Result of marking specific items as read."""

    model_config = ConfigDict(extra="forbid")

    marked_count: int = Field(..., ge=0)
    unread_total: int = Field(..., ge=0)


class NotificationInboxMarkAllReadResult(BaseModel):
    """Result of marking the current aggregation window as read."""

    model_config = ConfigDict(extra="forbid")

    marked_count: int = Field(..., ge=0)
    unread_total: int = Field(..., ge=0)


class NotificationInboxRetentionResult(BaseModel):
    """Result of applying read-state retention cleanup."""

    model_config = ConfigDict(extra="forbid")

    deleted_count: int = Field(..., ge=0)
    cutoff: datetime
    retention_days: int = Field(..., ge=1)


def build_inbox_item_id(kind: str, source_id: str, occurred_at: datetime) -> str:
    """Build a stable, non-reusable key for one durable event occurrence."""
    normalized_kind = str(kind).strip()
    normalized_source_id = str(source_id).strip()
    if normalized_kind not in INBOX_KIND_VALUES:
        raise ValueError("Unsupported inbox kind")
    if not _SOURCE_ID_PATTERN.fullmatch(normalized_source_id):
        raise ValueError("Inbox source id must use 1-64 stable identifier characters")
    if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
        raise ValueError("Inbox occurrence time must be timezone-aware")
    utc_value = occurred_at.astimezone(timezone.utc)
    delta = utc_value - datetime(1970, 1, 1, tzinfo=timezone.utc)
    epoch_microseconds = (
        (delta.days * 86_400 + delta.seconds) * 1_000_000
        + delta.microseconds
    )
    item_id = f"v1:{normalized_kind}:{normalized_source_id}:{epoch_microseconds}"
    if len(item_id) > NOTIFICATION_INBOX_MAX_ITEM_ID_LENGTH:
        raise ValueError("Inbox item id exceeds the supported length")
    return item_id


def parse_inbox_item_id(item_id: str) -> Optional[tuple[str, str, int]]:
    """Parse a bounded versioned occurrence key."""
    if not item_id or len(item_id) > NOTIFICATION_INBOX_MAX_ITEM_ID_LENGTH:
        return None
    parts = item_id.split(":")
    if len(parts) != 4 or parts[0] != "v1":
        return None
    _, kind, source_id, epoch_text = parts
    if kind not in INBOX_KIND_VALUES or not _SOURCE_ID_PATTERN.fullmatch(source_id):
        return None
    if not epoch_text.isascii() or not epoch_text.isdigit():
        return None
    return kind, source_id, int(epoch_text)
