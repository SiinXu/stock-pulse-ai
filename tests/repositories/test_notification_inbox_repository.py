# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Persistence regressions for notification inbox source ordering."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src.repositories.scheduled_task_repo import ScheduledTaskRepository
from src.storage import DatabaseManager, ScheduledTaskRecord, ScheduledTaskRunRecord


@pytest.fixture
def database(tmp_path):
    DatabaseManager.reset_instance()
    manager = DatabaseManager(db_url=f"sqlite:///{tmp_path / 'notification-inbox.sqlite'}")
    try:
        yield manager
    finally:
        DatabaseManager.reset_instance()


def test_recent_scheduled_runs_keep_the_newest_rows_beyond_source_limit(database) -> None:
    repository = ScheduledTaskRepository(database)
    start = datetime(2026, 8, 10, 0, 0)
    with database.get_session() as session:
        session.add(ScheduledTaskRecord(
            id="task1",
            schema_version=1,
            execution_generation=1,
            name="Inbox ordering",
            task_type="stock_analysis",
            schedule_kind="daily",
            schedule_time="09:30",
            timezone="UTC",
            calendar_market="us",
            non_trading_day_policy="skip",
            payload_json="{}",
            enabled=True,
            max_attempts=1,
        ))
        for index in range(250):
            occurred_at = start + timedelta(minutes=index)
            session.add(ScheduledTaskRunRecord(
                id=f"run{index:04d}",
                task_id="task1",
                scheduled_for=occurred_at,
                definition_schema_version=1,
                definition_generation=1,
                status="succeeded",
                attempt_count=1,
                dispatch_failure_count=0,
                execution_task_ids_json="[]",
                owned_execution_task_ids_json="[]",
                result_refs_json="[]",
                notification_channels_json="[]",
                notification_failed_channels_json="[]",
                finished_at=occurred_at,
            ))
        session.commit()

    rows = repository.list_recent_runs_between(
        start=start,
        end=start + timedelta(days=1),
        statuses=("succeeded",),
        limit=200,
    )

    assert len(rows) == 200
    assert rows[0].id == "run0249"
    assert rows[-1].id == "run0050"
    assert all(row.id != "run0049" for row in rows)
