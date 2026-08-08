# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""API tests for the in-app notification inbox endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import deps as api_deps
from api.middlewares.error_handler import add_error_handlers
from api.v1.endpoints import notification_inbox as endpoint
from src.schemas.notification_inbox import (
    NotificationInboxItem,
    NotificationInboxMarkAllReadResult,
    NotificationInboxMarkReadResult,
    NotificationInboxPage,
    NotificationInboxUnreadCount,
)
from src.services.notification_inbox_service import NotificationInboxValidationError


def _client(service) -> TestClient:
    app = FastAPI()
    app.include_router(endpoint.router, prefix="/api/v1/notification-inbox")
    app.dependency_overrides[api_deps.get_notification_inbox_service] = lambda: service
    add_error_handlers(app)
    return TestClient(app)


def _item(*, item_id: str = "analysis_complete:1", is_read: bool = False) -> NotificationInboxItem:
    return NotificationInboxItem(
        id=item_id,
        kind="analysis_complete",
        title="Analysis complete: 600519",
        summary="hold",
        severity="info",
        created_at=datetime(2026, 8, 9, tzinfo=timezone.utc),
        is_read=is_read,
        href="/research/analysis?segment=history&recordId=1",
        source_id="1",
        metadata={"record_id": 1},
    )


def test_list_items_returns_page() -> None:
    service = MagicMock()
    service.list_items.return_value = NotificationInboxPage(
        items=[_item()],
        page=1,
        page_size=20,
        total=1,
        unread_total=1,
        retention_days=90,
        max_items=500,
    )
    response = _client(service).get("/api/v1/notification-inbox/items")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == "analysis_complete:1"
    service.list_items.assert_called_once()


def test_unread_count_endpoint() -> None:
    service = MagicMock()
    service.get_unread_count.return_value = NotificationInboxUnreadCount(
        unread_total=3,
        retention_days=90,
        max_items=500,
    )
    response = _client(service).get("/api/v1/notification-inbox/unread-count")
    assert response.status_code == 200
    assert response.json()["unread_total"] == 3


def test_mark_read_and_mark_all_read() -> None:
    service = MagicMock()
    service.mark_read.return_value = NotificationInboxMarkReadResult(
        marked_count=1,
        unread_total=0,
    )
    service.mark_all_read.return_value = NotificationInboxMarkAllReadResult(
        marked_count=2,
        unread_total=0,
    )
    client = _client(service)
    mark_one = client.post(
        "/api/v1/notification-inbox/items/mark-read",
        json={"item_ids": ["analysis_complete:1"]},
    )
    assert mark_one.status_code == 200
    assert mark_one.json()["marked_count"] == 1
    mark_all = client.post("/api/v1/notification-inbox/items/mark-all-read", json={})
    assert mark_all.status_code == 200
    assert mark_all.json()["unread_total"] == 0


def test_validation_error_maps_to_400() -> None:
    service = MagicMock()
    service.list_items.side_effect = NotificationInboxValidationError(
        "bad kind",
        error_code="invalid_kind",
    )
    response = _client(service).get(
        "/api/v1/notification-inbox/items",
        params={"kind": "nope"},
    )
    assert response.status_code == 400
    body = response.json()
    detail = body.get("detail") or body
    assert detail.get("error") == "invalid_kind" or "invalid_kind" in str(body)
