"""Deterministic scheduled-task service and persistence regression tests."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import inspect, select

from src.config import Config
from src.migrations.registry import SCHEDULED_TASK_SCHEMA_MIGRATION, TARGET_VERSION
from src.repositories.scheduled_task_repo import ScheduledTaskRepository
from src.services.scheduled_task_service import (
    ScheduledTaskService,
    ScheduledTaskValidationError,
)
from src.storage import DatabaseManager, DatabaseSchemaMigration
from src.task_execution import TaskNotFoundError, TaskSnapshot, TaskStatus


NOW = datetime(2026, 7, 24, 1, 29)
DUE = datetime(2026, 7, 24, 1, 30)


class FakeTaskQueue:
    def __init__(
        self,
        *,
        initial_status: TaskStatus = TaskStatus.PENDING,
        retry_status: TaskStatus = TaskStatus.PENDING,
    ) -> None:
        self.initial_status = initial_status
        self.retry_status = retry_status
        self.submit_calls = []
        self.retry_calls = []
        self.snapshots = {}
        self._sequence = 0

    def _snapshot(self, task_id: str, status: TaskStatus) -> TaskSnapshot:
        return TaskSnapshot(
            id=task_id,
            kind="stock_analysis",
            status=status,
            progress=100 if status == TaskStatus.COMPLETED else 0,
            result_ref=f"result-{task_id}" if status == TaskStatus.COMPLETED else None,
            error_code="analysis_failed" if status == TaskStatus.FAILED else None,
            trace_id=task_id,
            created_at=NOW,
            updated_at=NOW,
        )

    def submit_tasks_batch(self, **kwargs):
        self.submit_calls.append(kwargs)
        self._sequence += 1
        task_id = f"execution-{self._sequence}"
        self.snapshots[task_id] = self._snapshot(task_id, self.initial_status)
        return [SimpleNamespace(task_id=task_id)], []

    def get(self, task_id: str) -> TaskSnapshot:
        return self.snapshots[task_id]

    def retry(self, task_id: str) -> str:
        self.retry_calls.append(task_id)
        self._sequence += 1
        child_id = f"execution-{self._sequence}"
        self.snapshots[child_id] = self._snapshot(child_id, self.retry_status)
        return child_id

    def set_status(self, task_id: str, status: TaskStatus) -> None:
        self.snapshots[task_id] = self._snapshot(task_id, status)


class MissingRetrySourceQueue(FakeTaskQueue):
    def retry(self, task_id: str) -> str:
        self.retry_calls.append(task_id)
        raise TaskNotFoundError(task_id)


class CoalescingTaskQueue(FakeTaskQueue):
    def __init__(self, *, existing_status: TaskStatus) -> None:
        super().__init__()
        self.existing_task_id = "existing-execution"
        self.snapshots[self.existing_task_id] = self._snapshot(
            self.existing_task_id,
            existing_status,
        )

    def submit_tasks_batch(self, **kwargs):
        self.submit_calls.append(kwargs)
        return [], [SimpleNamespace(existing_task_id=self.existing_task_id)]


@pytest.fixture
def database(tmp_path):
    DatabaseManager.reset_instance()
    Config.reset_instance()
    manager = DatabaseManager(db_url=f"sqlite:///{tmp_path / 'scheduled.sqlite'}")
    try:
        yield manager
    finally:
        DatabaseManager.reset_instance()
        Config.reset_instance()


def task_contract(
    *,
    enabled: bool = True,
    policy: str = "skip",
    max_attempts: int = 1,
):
    return {
        "schema_version": 1,
        "name": "Morning analysis",
        "task_type": "stock_analysis",
        "schedule": {
            "kind": "daily",
            "time": "09:30",
            "timezone": "Asia/Shanghai",
            "calendar_market": "cn",
            "non_trading_day_policy": policy,
        },
        "payload": {
            "stock_code": "600519",
            "report_type": "detailed",
            "notify": False,
        },
        "enabled": enabled,
        "max_attempts": max_attempts,
    }


def build_service(database, queue=None, *, market_open=True):
    return ScheduledTaskService(
        repository=ScheduledTaskRepository(database),
        task_queue=queue or FakeTaskQueue(),
        clock=lambda: NOW,
        market_open_provider=lambda _market, _date: market_open,
    )


def test_schema_migration_and_models_create_both_tables(database) -> None:
    table_names = set(inspect(database._engine).get_table_names())
    assert {"scheduled_tasks", "scheduled_task_runs"}.issubset(table_names)
    assert TARGET_VERSION == SCHEDULED_TASK_SCHEMA_MIGRATION.id
    with database.get_session() as session:
        applied = session.execute(
            select(DatabaseSchemaMigration).where(
                DatabaseSchemaMigration.version == SCHEDULED_TASK_SCHEMA_MIGRATION.id
            )
        ).scalar_one()
    assert applied.checksum == SCHEDULED_TASK_SCHEMA_MIGRATION.checksum


def test_create_list_disable_and_enable_preserve_versioned_contract(database) -> None:
    service = build_service(database)

    created = service.create_task(task_contract(), now=NOW)

    assert created["schema_version"] == 1
    assert created["next_run_at"].replace(tzinfo=None) == DUE
    assert service.list_tasks()["items"] == [created]

    disabled = service.set_enabled(created["id"], False, now=NOW)
    assert disabled["enabled"] is False
    assert disabled["next_run_at"] is None
    assert service.has_enabled_tasks() is False

    enabled = service.set_enabled(created["id"], True, now=NOW)
    assert enabled["enabled"] is True
    assert enabled["next_run_at"].replace(tzinfo=None) == DUE


def test_stock_market_must_match_trading_calendar(database) -> None:
    service = build_service(database)
    contract = task_contract()
    contract["payload"]["stock_code"] = "AAPL"

    with pytest.raises(
        ScheduledTaskValidationError,
        match="stock_code market must match",
    ):
        service.create_task(contract, now=NOW)


def test_due_occurrence_dispatches_once_and_persists_success(database) -> None:
    queue = FakeTaskQueue()
    service = build_service(database, queue)
    task = service.create_task(task_contract(), now=NOW)

    first = service.tick(now=DUE)
    second = service.tick(now=DUE)

    assert first == {"reconciled": 0, "claimed": 1, "skipped": 0}
    assert second["claimed"] == 0
    assert len(queue.submit_calls) == 1
    assert queue.submit_calls[0]["query_source"] == "scheduled_task"
    assert queue.submit_calls[0]["notify"] is False

    running = service.list_runs(task["id"])["items"][0]
    assert running["status"] == "running"
    queue.set_status(running["execution_task_ids"][0], TaskStatus.COMPLETED)

    service.tick(now=DUE + timedelta(seconds=1))

    completed = service.get_status(task["id"])["latest_run"]
    assert completed["status"] == "succeeded"
    assert completed["attempt_count"] == 1
    assert completed["result_refs"] == [
        f"result-{completed['execution_task_ids'][0]}"
    ]


def test_non_trading_day_skip_records_run_without_side_effect(database) -> None:
    queue = FakeTaskQueue()
    service = build_service(database, queue, market_open=False)
    task = service.create_task(task_contract(policy="skip"), now=NOW)

    result = service.tick(now=DUE)

    assert result == {"reconciled": 0, "claimed": 0, "skipped": 1}
    assert queue.submit_calls == []
    run = service.list_runs(task["id"])["items"][0]
    assert run["status"] == "skipped"
    assert run["attempt_count"] == 0
    assert run["error_code"] == "non_trading_day"


def test_non_trading_day_run_policy_dispatches(database) -> None:
    queue = FakeTaskQueue()
    service = build_service(database, queue, market_open=False)
    service.create_task(task_contract(policy="run"), now=NOW)

    result = service.tick(now=DUE)

    assert result["claimed"] == 1
    assert len(queue.submit_calls) == 1


def test_due_occurrence_coalesces_with_existing_canonical_analysis(database) -> None:
    queue = CoalescingTaskQueue(existing_status=TaskStatus.PENDING)
    service = build_service(database, queue)
    task = service.create_task(task_contract(max_attempts=3), now=NOW)

    service.tick(now=DUE)

    running = service.get_status(task["id"])["latest_run"]
    assert running["status"] == "running"
    assert running["execution_task_ids"] == [queue.existing_task_id]
    assert len(queue.submit_calls) == 1

    queue.set_status(queue.existing_task_id, TaskStatus.FAILED)
    service.tick(now=DUE + timedelta(seconds=1))

    failed = service.get_status(task["id"])["latest_run"]
    assert failed["status"] == "failed"
    assert failed["error_code"] == "scheduled_task_coalesced_execution_failed"
    assert queue.retry_calls == []


def test_failed_execution_retries_once_then_stops_at_bound(database) -> None:
    queue = FakeTaskQueue(
        initial_status=TaskStatus.FAILED,
        retry_status=TaskStatus.FAILED,
    )
    service = build_service(database, queue)
    task = service.create_task(task_contract(max_attempts=2), now=NOW)

    service.tick(now=DUE)
    waiting = service.get_status(task["id"])["latest_run"]
    assert waiting["status"] == "retry_wait"
    assert waiting["attempt_count"] == 1

    service.tick(now=DUE + timedelta(seconds=29))
    assert queue.retry_calls == []

    service.tick(now=DUE + timedelta(seconds=30))
    failed = service.get_status(task["id"])["latest_run"]
    assert failed["status"] == "failed"
    assert failed["attempt_count"] == 2
    assert failed["error_code"] == "analysis_failed"
    assert len(queue.retry_calls) == 1


def test_retry_wait_is_interrupted_when_process_local_execution_is_lost(
    database,
) -> None:
    initial_queue = FakeTaskQueue(initial_status=TaskStatus.FAILED)
    service = build_service(database, initial_queue)
    task = service.create_task(task_contract(max_attempts=2), now=NOW)

    service.tick(now=DUE)
    waiting = service.get_status(task["id"])["latest_run"]
    assert waiting["status"] == "retry_wait"
    assert waiting["attempt_count"] == 1

    restarted_queue = MissingRetrySourceQueue()
    restarted_service = build_service(database, restarted_queue)
    restarted_service.tick(now=DUE + timedelta(seconds=30))

    interrupted = restarted_service.get_status(task["id"])["latest_run"]
    assert interrupted["status"] == "interrupted"
    assert interrupted["attempt_count"] == 1
    assert interrupted["error_code"] == "scheduled_task_execution_state_lost"
    assert restarted_queue.retry_calls == waiting["execution_task_ids"]
