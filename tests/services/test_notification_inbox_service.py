# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Unit tests for the in-app notification inbox service (plan A)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, List, Optional, Sequence, Tuple

import pytest

from src.schemas.notification_inbox import build_inbox_item_id
from src.services.notification_inbox_service import (
    NotificationInboxService,
    NotificationInboxValidationError,
)


class _FakeReadRepo:
    def __init__(self) -> None:
        self.read: dict[str, str] = {}

    def list_read_item_ids(self, item_ids: Sequence[str]) -> set[str]:
        return {item_id for item_id in item_ids if item_id in self.read}

    def mark_read(self, items: Sequence[Tuple[str, str]]) -> int:
        written = 0
        for item_id, kind in items:
            if item_id not in self.read:
                written += 1
            self.read[item_id] = kind
        return written

    def delete_read_before(self, cutoff: datetime) -> int:
        # Time-based retention is exercised via service with empty window.
        return 0

    def delete_read_not_in(self, keep_item_ids: Sequence[str]) -> int:
        keep = set(keep_item_ids)
        before = len(self.read)
        self.read = {key: value for key, value in self.read.items() if key in keep}
        return before - len(self.read)


class _FakeAlertRepo:
    def __init__(self, rows: List[Any]) -> None:
        self.rows = rows

    def list_triggers(self, **_kwargs: Any) -> Tuple[List[Any], int]:
        return list(self.rows), len(self.rows)


class _FakeScheduledRepo:
    def __init__(self, rows: List[Any]) -> None:
        self.rows = rows

    def list_runs_between(self, **_kwargs: Any) -> List[Any]:
        return list(self.rows)


class _FakeSignalRepo:
    def __init__(self, rows: List[Any]) -> None:
        self.rows = rows

    def list(self, **_kwargs: Any) -> Tuple[List[Any], int]:
        return list(self.rows), len(self.rows)


class _FakeDb:
    def __init__(self, analysis_rows: List[Any]) -> None:
        self.analysis_rows = analysis_rows

    def get_analysis_history(self, **_kwargs: Any) -> List[Any]:
        return list(self.analysis_rows)


def _analysis(
    *,
    record_id: int = 1,
    code: str = "600519",
    name: str = "Kweichow Moutai",
    created_at: Optional[datetime] = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=record_id,
        code=code,
        name=name,
        operation_advice="hold",
        analysis_summary="Stable outlook",
        report_type="stock",
        query_id=f"q-{record_id}",
        created_at=created_at or datetime.now(),
    )


def _alert(
    *,
    trigger_id: int = 11,
    target: str = "600519",
    triggered_at: Optional[datetime] = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=trigger_id,
        rule_id=3,
        target=target,
        reason="price crossed threshold",
        status="triggered",
        triggered_at=triggered_at or datetime.now(),
    )


def _run(
    *,
    run_id: str = "run1",
    task_id: str = "task1",
    status: str = "succeeded",
    finished_at: Optional[datetime] = None,
) -> SimpleNamespace:
    now = finished_at or datetime.now()
    return SimpleNamespace(
        id=run_id,
        task_id=task_id,
        status=status,
        error_code=None,
        scheduled_for=now,
        finished_at=now,
        updated_at=now,
        created_at=now,
    )


def _signal(
    *,
    signal_id: int = 21,
    stock_code: str = "AAPL",
    created_at: Optional[datetime] = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=signal_id,
        stock_code=stock_code,
        stock_name="Apple",
        action="buy",
        action_label="Buy",
        created_at=created_at or datetime.now(),
    )


def _service(
    *,
    analysis: Optional[List[Any]] = None,
    alerts: Optional[List[Any]] = None,
    runs: Optional[List[Any]] = None,
    signals: Optional[List[Any]] = None,
    retention_days: int = 90,
    max_items: int = 100,
    read_repo: Optional[_FakeReadRepo] = None,
) -> NotificationInboxService:
    return NotificationInboxService(
        db_manager=_FakeDb(analysis or []),  # type: ignore[arg-type]
        repository=read_repo or _FakeReadRepo(),  # type: ignore[arg-type]
        alert_repository=_FakeAlertRepo(alerts or []),  # type: ignore[arg-type]
        scheduled_task_repository=_FakeScheduledRepo(runs or []),  # type: ignore[arg-type]
        decision_signal_repository=_FakeSignalRepo(signals or []),  # type: ignore[arg-type]
        retention_days=retention_days,
        max_items=max_items,
    )


def test_list_items_aggregates_all_event_sources_and_sorts_desc() -> None:
    older = datetime.now() - timedelta(hours=2)
    newer = datetime.now() - timedelta(hours=1)
    service = _service(
        analysis=[_analysis(record_id=1, created_at=older)],
        alerts=[_alert(trigger_id=2, triggered_at=newer)],
        runs=[_run(run_id="r3", status="failed", finished_at=newer + timedelta(minutes=1))],
        signals=[_signal(signal_id=4, created_at=older - timedelta(minutes=1))],
    )
    page = service.list_items(page=1, page_size=10)
    assert page.total == 4
    assert page.unread_total == 4
    assert [item.kind for item in page.items] == [
        "scheduled_task_result",
        "alert_triggered",
        "analysis_complete",
        "decision_signal",
    ]
    assert page.items[0].severity == "error"
    assert page.items[1].href.startswith("/signals?")
    assert "recordId=1" in page.items[2].href


def test_mark_read_and_unread_filter() -> None:
    service = _service(analysis=[_analysis(record_id=9)], alerts=[_alert(trigger_id=8)])
    listed = service.list_items()
    assert listed.unread_total == 2
    first_id = listed.items[0].id
    marked = service.mark_read([first_id])
    assert marked.marked_count == 1
    assert marked.unread_total == 1
    unread_only = service.list_items(unread_only=True)
    assert unread_only.total == 1
    assert unread_only.items[0].id != first_id
    assert unread_only.items[0].is_read is False


def test_mark_all_read_clears_unread() -> None:
    service = _service(
        analysis=[_analysis(record_id=1)],
        alerts=[_alert(trigger_id=2)],
        signals=[_signal(signal_id=3)],
    )
    result = service.mark_all_read()
    assert result.marked_count == 3
    assert result.unread_total == 0
    page = service.list_items()
    assert page.unread_total == 0
    assert all(item.is_read for item in page.items)


def test_retention_drops_orphan_read_markers() -> None:
    read_repo = _FakeReadRepo()
    orphan_id = build_inbox_item_id("analysis_complete", "999")
    read_repo.read[orphan_id] = "analysis_complete"
    service = _service(analysis=[_analysis(record_id=1)], read_repo=read_repo)
    # mark_all_read opportunistically applies retention and removes orphans.
    service.mark_all_read()
    assert orphan_id not in read_repo.read
    assert build_inbox_item_id("analysis_complete", "1") in read_repo.read
    # Explicit retention remains idempotent.
    result = service.apply_retention()
    assert result.deleted_count == 0
    assert build_inbox_item_id("analysis_complete", "1") in read_repo.read


def test_max_items_cap_is_enforced() -> None:
    analysis = [
        _analysis(record_id=i, created_at=datetime.now() - timedelta(minutes=i))
        for i in range(1, 16)
    ]
    service = _service(analysis=analysis, max_items=10)
    page = service.list_items(page_size=20)
    assert page.total == 10
    assert page.max_items == 10


def test_invalid_kind_and_item_id_raise_validation() -> None:
    service = _service()
    with pytest.raises(NotificationInboxValidationError) as kind_exc:
        service.list_items(kind="not_a_kind")
    assert kind_exc.value.error_code == "invalid_kind"
    with pytest.raises(NotificationInboxValidationError) as id_exc:
        service.mark_read(["bad-id"])
    assert id_exc.value.error_code == "invalid_item_id"


def test_old_events_outside_retention_are_excluded() -> None:
    old = datetime.now() - timedelta(days=120)
    service = _service(
        analysis=[_analysis(record_id=1, created_at=old)],
        alerts=[_alert(trigger_id=2, triggered_at=datetime.now())],
        retention_days=30,
    )
    page = service.list_items()
    assert page.total == 1
    assert page.items[0].kind == "alert_triggered"
