# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""API request/response models for the in-app notification inbox."""

from __future__ import annotations

from typing import Annotated, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.notification_inbox import (
    NOTIFICATION_INBOX_MAX_PAGE_SIZE,
    NOTIFICATION_INBOX_MAX_ITEM_ID_LENGTH,
    NotificationInboxItem,
    NotificationInboxMarkAllReadResult,
    NotificationInboxMarkReadResult,
    NotificationInboxPage,
    NotificationInboxUnreadCount,
)


class NotificationInboxListResponse(NotificationInboxPage):
    """GET /notification-inbox/items response body."""


class NotificationInboxUnreadCountResponse(NotificationInboxUnreadCount):
    """GET /notification-inbox/unread-count response body."""


class NotificationInboxMarkReadRequest(BaseModel):
    """POST /notification-inbox/items/mark-read request body."""

    model_config = ConfigDict(extra="forbid")

    item_ids: List[
        Annotated[str, Field(min_length=1, max_length=NOTIFICATION_INBOX_MAX_ITEM_ID_LENGTH)]
    ] = Field(
        ...,
        min_length=1,
        max_length=NOTIFICATION_INBOX_MAX_PAGE_SIZE,
        description="Versioned stable inbox occurrence ids",
    )


class NotificationInboxMarkReadResponse(NotificationInboxMarkReadResult):
    """POST /notification-inbox/items/mark-read response body."""


class NotificationInboxMarkAllReadRequest(BaseModel):
    """POST /notification-inbox/items/mark-all-read request body."""

    model_config = ConfigDict(extra="forbid")

    kind: Optional[str] = Field(
        default=None,
        description="Optional kind filter when marking the current window",
    )


class NotificationInboxMarkAllReadResponse(NotificationInboxMarkAllReadResult):
    """POST /notification-inbox/items/mark-all-read response body."""


__all__ = [
    "NotificationInboxItem",
    "NotificationInboxListResponse",
    "NotificationInboxUnreadCountResponse",
    "NotificationInboxMarkReadRequest",
    "NotificationInboxMarkReadResponse",
    "NotificationInboxMarkAllReadRequest",
    "NotificationInboxMarkAllReadResponse",
]
