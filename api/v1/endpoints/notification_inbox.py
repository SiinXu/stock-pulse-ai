# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""In-app notification inbox API (Issue #181 / T20).

Read-side aggregation over durable event sources. Does not send outbound
notifications and does not mutate alert evaluation or scheduled-task writers.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query

from api.deps import get_notification_inbox_service
from api.v1.errors import api_error
from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.notification_inbox import (
    NotificationInboxListResponse,
    NotificationInboxMarkAllReadRequest,
    NotificationInboxMarkAllReadResponse,
    NotificationInboxMarkReadRequest,
    NotificationInboxMarkReadResponse,
    NotificationInboxUnreadCountResponse,
)
from src.repositories.base import RepositoryError
from src.schemas.notification_inbox import NOTIFICATION_INBOX_MAX_PAGE_SIZE
from src.services.notification_inbox_service import (
    NotificationInboxService,
    NotificationInboxValidationError,
)
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)
router = APIRouter()


def _translate_error(exc: Exception) -> None:
    if isinstance(exc, NotificationInboxValidationError):
        raise api_error(400, exc.error_code, str(exc)) from exc
    if isinstance(exc, RepositoryError):
        log_safe_exception(
            logger,
            "Notification inbox repository failure",
            exc,
            error_code=getattr(exc, "error_code", None) or "internal_error",
            context=getattr(exc, "context", None),
        )
        raise api_error(500, "internal_error", "Notification inbox storage failed") from exc
    log_safe_exception(
        logger,
        "Notification inbox operation failed",
        exc,
        error_code="notification_inbox_internal_error",
    )
    raise api_error(500, "internal_error", "Notification inbox operation failed") from exc


@router.get(
    "/items",
    response_model=NotificationInboxListResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="List in-app notification inbox items",
)
def list_inbox_items(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=NOTIFICATION_INBOX_MAX_PAGE_SIZE),
    kind: Optional[str] = Query(None, min_length=1, max_length=64),
    unread_only: bool = Query(False),
    service: NotificationInboxService = Depends(get_notification_inbox_service),
) -> NotificationInboxListResponse:
    try:
        page_result = service.list_items(
            page=page,
            page_size=page_size,
            kind=kind,
            unread_only=unread_only,
        )
        return NotificationInboxListResponse.model_validate(page_result.model_dump())
    except (NotificationInboxValidationError, RepositoryError) as exc:
        _translate_error(exc)
    except Exception as exc:  # broad-exception: fallback_recorded - stable API envelope
        _translate_error(exc)


@router.get(
    "/unread-count",
    response_model=NotificationInboxUnreadCountResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Get unread notification inbox count",
)
def get_inbox_unread_count(
    kind: Optional[str] = Query(None, min_length=1, max_length=64),
    service: NotificationInboxService = Depends(get_notification_inbox_service),
) -> NotificationInboxUnreadCountResponse:
    try:
        result = service.get_unread_count(kind=kind)
        return NotificationInboxUnreadCountResponse.model_validate(result.model_dump())
    except (NotificationInboxValidationError, RepositoryError) as exc:
        _translate_error(exc)
    except Exception as exc:  # broad-exception: fallback_recorded - stable API envelope
        _translate_error(exc)


@router.post(
    "/items/mark-read",
    response_model=NotificationInboxMarkReadResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Mark specific notification inbox items as read",
)
def mark_inbox_items_read(
    body: NotificationInboxMarkReadRequest,
    service: NotificationInboxService = Depends(get_notification_inbox_service),
) -> NotificationInboxMarkReadResponse:
    try:
        result = service.mark_read(body.item_ids)
        return NotificationInboxMarkReadResponse.model_validate(result.model_dump())
    except (NotificationInboxValidationError, RepositoryError) as exc:
        _translate_error(exc)
    except Exception as exc:  # broad-exception: fallback_recorded - stable API envelope
        _translate_error(exc)


@router.post(
    "/items/mark-all-read",
    response_model=NotificationInboxMarkAllReadResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Mark the current notification inbox window as read",
)
def mark_all_inbox_items_read(
    body: NotificationInboxMarkAllReadRequest | None = None,
    service: NotificationInboxService = Depends(get_notification_inbox_service),
) -> NotificationInboxMarkAllReadResponse:
    payload = body or NotificationInboxMarkAllReadRequest()
    try:
        result = service.mark_all_read(kind=payload.kind)
        return NotificationInboxMarkAllReadResponse.model_validate(result.model_dump())
    except (NotificationInboxValidationError, RepositoryError) as exc:
        _translate_error(exc)
    except Exception as exc:  # broad-exception: fallback_recorded - stable API envelope
        _translate_error(exc)
