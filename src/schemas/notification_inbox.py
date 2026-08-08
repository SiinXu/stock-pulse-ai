# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Domain models and defaults for the in-app notification inbox."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


NOTIFICATION_INBOX_RETENTION_DAYS_DEFAULT = 90
NOTIFICATION_INBOX_MAX_ITEMS_DEFAULT = 500
NOTIFICATION_INBOX_MAX_PAGE_SIZE = 100
NOTIFICATION_INBOX_SOURCE_FETCH_LIMIT = 200

NotificationInboxKind = Literal[
    "analysis_complete",
    "alert_triggered",
    "scheduled_task_result",
    "decision_signal",
]

NotificationInboxSeverity = Literal["info", "warning", "error"]

INBOX_KIND_VALUES: tuple[str, ...] = (
    "analysis_complete",
    "alert_triggered",
    "scheduled_task_result",
    "decision_signal",
)


class NotificationInboxItem(BaseModel):
    """One aggregated inbox row projected from durable event sources."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Stable item key kind:source_id")
    kind: NotificationInboxKind
    title: str
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
    retention_days: int = Field(..., ge=1)
    max_items: int = Field(..., ge=1)


class NotificationInboxUnreadCount(BaseModel):
    """Unread count for the current retention window."""

    model_config = ConfigDict(extra="forbid")

    unread_total: int = Field(..., ge=0)
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


def build_inbox_item_id(kind: str, source_id: str) -> str:
    """Build a stable composite item id used for read-state keys."""
    return f"{kind}:{source_id}"


def parse_inbox_item_id(item_id: str) -> Optional[tuple[str, str]]:
    """Parse kind and source_id from a composite item id."""
    if not item_id or ":" not in item_id:
        return None
    kind, source_id = item_id.split(":", 1)
    if kind not in INBOX_KIND_VALUES or not source_id:
        return None
    return kind, source_id
