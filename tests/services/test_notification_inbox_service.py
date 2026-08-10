# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Contract tests for the durable in-app notification inbox."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

import pytest

from src.repositories.base import RepositoryError
from src.services.notification_inbox_service import (
    NotificationInboxService,
    NotificationInboxValidationError,
)

NOW = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)


class _FakeReadRepo:
    def __init__(self) -> None:
        self.read: dict[str, str] = {}
        self.time_retention_calls = 0

    def list_read_item_ids(self, item_ids: Sequence[str]) -> set[str]:
        return {item_id for item_id in item_ids if item_id in self.read}

    def mark_read(self, items: Sequence[Tuple[str, str]]) -> int:
        written = 0
        for item_id, kind in items:
            if item_id not in self.read:
                written += 1
            self.read[item_id] = kind
        return written

    def delete_read_before(self, _cutoff: datetime) -> int:
        self.time_retention_calls += 1
        return 0

    def delete_read_not_in(self, keep_item_ids: Sequence[str]) -> int:
        keep = set(keep_item_ids)
        before = len(self.read)
        self.read = {key: value for key, value in self.read.items() if key in keep}
        return before - len(self.read)


class _FakeAlertRepo:
    def __init__(self, rows: List[Any], error: Optional[RepositoryError] = None) -> None:
        self.rows = rows
        self.error = error

    def list_triggers(self, **kwargs: Any) -> Tuple[List[Any], int]:
        if self.error:
            raise self.error
        limit = int(kwargs["page_size"])
        return list(self.rows[:limit]), len(self.rows)


class _FakeScheduledRepo:
    def __init__(self, rows: List[Any], error: Optional[RepositoryError] = None) -> None:
        self.rows = rows
        self.error = error

    def list_recent_runs_between(self, **kwargs: Any) -> List[Any]:
        if self.error:
            raise self.error
        limit = int(kwargs["limit"])
        return sorted(
            self.rows,
            key=lambda row: (row.finished_at, row.id),
            reverse=True,
        )[:limit]


class _FakeSignalRepo:
    def __init__(self, rows: List[Any], error: Optional[RepositoryError] = None) -> None:
        self.rows = rows
        self.error = error
        self.statuses: list[Optional[str]] = []

    def list(self, **kwargs: Any) -> Tuple[List[Any], int]:
        if self.error:
            raise self.error
        self.statuses.append(kwargs.get("status"))
        page = int(kwargs["page"])
        page_size = int(kwargs["page_size"])
        start = (page - 1) * page_size
        return list(self.rows[start:start + page_size]), len(self.rows)


class _FakeDb:
    def __init__(self, rows: List[Any], error: Optional[RepositoryError] = None) -> None:
        self.rows = rows
        self.error = error

    def get_analysis_history(self, **kwargs: Any) -> List[Any]:
        if self.error:
            raise self.error
        return list(self.rows[: int(kwargs["limit"])])


def _analysis(
    *,
    record_id: int = 1,
    created_at: Optional[datetime] = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=record_id,
        code="600519",
        name="Kweichow Moutai",
        operation_advice="hold",
        analysis_summary="Stable outlook",
        report_type="stock",
        query_id=f"q-{record_id}",
        created_at=created_at or datetime(2026, 8, 10, 19, 0),
    )


def _alert(*, trigger_id: int = 11, triggered_at: Optional[datetime] = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=trigger_id,
        rule_id=3,
        target="600519",
        reason="price crossed threshold",
        status="triggered",
        triggered_at=triggered_at or datetime(2026, 8, 10, 19, 30),
    )


def _run(
    *,
    run_id: str = "run1",
    status: str = "succeeded",
    finished_at: Optional[datetime] = None,
) -> SimpleNamespace:
    occurred_at = finished_at or datetime(2026, 8, 10, 11, 45)
    return SimpleNamespace(
        id=run_id,
        task_id="task1",
        status=status,
        error_code=None,
        scheduled_for=occurred_at,
        finished_at=occurred_at,
        updated_at=occurred_at,
        created_at=occurred_at,
    )


def _signal(
    *,
    signal_id: int = 21,
    status: str = "active",
    created_at: Optional[datetime] = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=signal_id,
        stock_code="AAPL",
        stock_name="Apple",
        action="buy",
        action_label="Buy",
        status=status,
        created_at=created_at or datetime(2026, 8, 10, 11, 30),
    )


def _service(
    *,
    analysis: Optional[List[Any]] = None,
    alerts: Optional[List[Any]] = None,
    runs: Optional[List[Any]] = None,
    signals: Optional[List[Any]] = None,
    analysis_error: Optional[RepositoryError] = None,
    alert_error: Optional[RepositoryError] = None,
    scheduled_error: Optional[RepositoryError] = None,
    signal_error: Optional[RepositoryError] = None,
    retention_days: int = 90,
    max_items: int = 100,
    read_repo: Optional[_FakeReadRepo] = None,
    local_timezone: ZoneInfo = ZoneInfo("Asia/Shanghai"),
) -> NotificationInboxService:
    return NotificationInboxService(
        db_manager=_FakeDb(analysis or [], analysis_error),  # type: ignore[arg-type]
        repository=read_repo or _FakeReadRepo(),  # type: ignore[arg-type]
        alert_repository=_FakeAlertRepo(alerts or [], alert_error),  # type: ignore[arg-type]
        scheduled_task_repository=_FakeScheduledRepo(runs or [], scheduled_error),  # type: ignore[arg-type]
        decision_signal_repository=_FakeSignalRepo(signals or [], signal_error),  # type: ignore[arg-type]
        retention_days=retention_days,
        max_items=max_items,
        clock=lambda: NOW,
        local_timezone=local_timezone,
    )


def _failure(source: str) -> RepositoryError:
    return RepositoryError("unavailable", error_code=f"{source}_unavailable")


def test_aggregates_all_sources_with_structured_titles_and_descending_order() -> None:
    service = _service(
        analysis=[_analysis()],
        alerts=[_alert()],
        runs=[_run(status="failed")],
        signals=[_signal()],
    )

    page = service.list_items(page_size=10)

    assert page.total == 4
    assert [item.kind for item in page.items] == [
        "scheduled_task_result",
        "decision_signal",
        "alert_triggered",
        "analysis_complete",
    ]
    assert page.items[2].title_key == "alertTriggeredTitle"
    assert page.items[2].title_params == {"target": "600519"}
    assert all(item.created_at.tzinfo is not None for item in page.items)
    assert all(status.available for status in page.source_statuses)


def test_one_source_failure_returns_other_sources_with_provenance() -> None:
    service = _service(
        analysis=[_analysis()],
        alerts=[_alert()],
        runs=[_run()],
        signals=[_signal()],
        alert_error=_failure("alerts"),
    )

    page = service.list_items()

    assert page.total == 3
    alert_status = next(status for status in page.source_statuses if status.source == "alerts")
    assert alert_status.available is False
    assert alert_status.error_code == "alerts_unavailable"


def test_all_source_failures_fail_the_request() -> None:
    service = _service(
        analysis_error=_failure("analysis"),
        alert_error=_failure("alerts"),
        scheduled_error=_failure("scheduled"),
        signal_error=_failure("signals"),
    )

    with pytest.raises(RepositoryError) as exc_info:
        service.list_items()
    assert exc_info.value.error_code == "notification_inbox_no_source_available"


def test_mark_read_requires_an_authoritative_current_occurrence() -> None:
    service = _service(analysis=[_analysis(record_id=9)])
    item_id = service.list_items().items[0].id

    marked = service.mark_read([item_id])
    assert marked.marked_count == 1
    assert marked.unread_total == 0

    reused_id = item_id.rsplit(":", 1)[0] + ":1786320000000000"
    with pytest.raises(NotificationInboxValidationError) as exc_info:
        service.mark_read([reused_id])
    assert exc_info.value.error_code == "unknown_item_id"


def test_mark_all_fails_closed_when_a_selected_source_is_unavailable() -> None:
    service = _service(analysis=[_analysis()], alert_error=_failure("alerts"))

    with pytest.raises(RepositoryError) as exc_info:
        service.mark_all_read()
    assert exc_info.value.error_code == "notification_inbox_partial_source"


def test_decision_signal_occurrences_survive_status_changes() -> None:
    signal_repo = _FakeSignalRepo([_signal(status="expired")])
    service = NotificationInboxService(
        db_manager=_FakeDb([]),  # type: ignore[arg-type]
        repository=_FakeReadRepo(),  # type: ignore[arg-type]
        alert_repository=_FakeAlertRepo([]),  # type: ignore[arg-type]
        scheduled_task_repository=_FakeScheduledRepo([]),  # type: ignore[arg-type]
        decision_signal_repository=signal_repo,  # type: ignore[arg-type]
        retention_days=90,
        max_items=100,
        clock=lambda: NOW,
        local_timezone=ZoneInfo("Asia/Shanghai"),
    )

    page = service.list_items(kind="decision_signal")

    assert page.total == 1
    assert page.items[0].metadata["status"] == "expired"
    assert signal_repo.statuses == [None]


def test_cursor_continuation_is_stable_when_a_newer_item_arrives() -> None:
    rows = [
        _analysis(record_id=index, created_at=datetime(2026, 8, 10, 20 - index, 0))
        for index in range(1, 5)
    ]
    database = _FakeDb(rows)
    service = NotificationInboxService(
        db_manager=database,  # type: ignore[arg-type]
        repository=_FakeReadRepo(),  # type: ignore[arg-type]
        alert_repository=_FakeAlertRepo([]),  # type: ignore[arg-type]
        scheduled_task_repository=_FakeScheduledRepo([]),  # type: ignore[arg-type]
        decision_signal_repository=_FakeSignalRepo([]),  # type: ignore[arg-type]
        retention_days=90,
        max_items=100,
        clock=lambda: NOW,
        local_timezone=ZoneInfo("Asia/Shanghai"),
    )
    first = service.list_items(page_size=2, kind="analysis_complete")
    database.rows.insert(0, _analysis(record_id=99, created_at=datetime(2026, 8, 10, 21, 0)))

    second = service.list_items(
        page_size=2,
        kind="analysis_complete",
        cursor=first.next_cursor,
    )

    first_ids = {item.id for item in first.items}
    assert first.has_more is True
    assert first_ids.isdisjoint(item.id for item in second.items)
    assert all(item.source_id != "99" for item in second.items)


@pytest.mark.parametrize(
    ("zone_name", "local_value", "expected_utc"),
    [
        ("Asia/Shanghai", datetime(2026, 8, 10, 20, 0), "2026-08-10T12:00:00+00:00"),
        ("America/New_York", datetime(2026, 8, 10, 8, 0), "2026-08-10T12:00:00+00:00"),
    ],
)
def test_local_naive_source_timestamps_are_normalized_at_the_boundary(
    zone_name: str,
    local_value: datetime,
    expected_utc: str,
) -> None:
    service = _service(
        analysis=[_analysis(created_at=local_value)],
        local_timezone=ZoneInfo(zone_name),
    )

    item = service.list_items(kind="analysis_complete").items[0]

    assert item.created_at.isoformat() == expected_utc


def test_versioned_identity_changes_when_a_source_id_is_reused() -> None:
    first = _service(analysis=[_analysis(created_at=datetime(2026, 8, 10, 19, 0))])
    second = _service(analysis=[_analysis(created_at=datetime(2026, 8, 10, 19, 1))])

    assert first.list_items().items[0].id != second.list_items().items[0].id


def test_time_retention_runs_on_normal_reads() -> None:
    read_repo = _FakeReadRepo()
    service = _service(analysis=[_analysis()], read_repo=read_repo)

    service.list_items()
    service.get_unread_count()

    assert read_repo.time_retention_calls == 2


def test_invalid_cursor_kind_and_item_id_are_rejected() -> None:
    service = _service()
    with pytest.raises(NotificationInboxValidationError) as kind_exc:
        service.list_items(kind="not_a_kind")
    assert kind_exc.value.error_code == "invalid_kind"
    with pytest.raises(NotificationInboxValidationError) as cursor_exc:
        service.list_items(cursor="not-a-cursor")
    assert cursor_exc.value.error_code == "invalid_cursor"
    with pytest.raises(NotificationInboxValidationError) as id_exc:
        service.mark_read(["analysis_complete:1"])
    assert id_exc.value.error_code == "invalid_item_id"


def test_old_events_outside_retention_are_excluded() -> None:
    old_local = (NOW - timedelta(days=120)).astimezone(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
    service = _service(
        analysis=[_analysis(created_at=old_local)],
        alerts=[_alert()],
        retention_days=30,
    )
    page = service.list_items()
    assert [item.kind for item in page.items] == ["alert_triggered"]
