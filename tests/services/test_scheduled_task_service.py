"""Deterministic scheduled-task service and persistence regression tests."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import inspect, select

from src.config import Config
from src.core.trading_calendar import MarketSessionStatus
from src.migrations.registry import SCHEDULED_TASK_SCHEMA_MIGRATION, TARGET_VERSION
from src.repositories.scheduled_task_repo import ScheduledTaskRepository
from src.schemas.scheduled_task import next_daily_run_at
from src.services.scheduled_task_service import (
    ScheduledTaskContractError,
    ScheduledTaskService,
    ScheduledTaskUnsupportedSchemaError,
    ScheduledTaskValidationError,
)
from src.services.task_queue import (
    AnalysisTaskCoalescingContract,
    AnalysisTaskQueue,
)
from src.storage import (
    DatabaseManager,
    DatabaseSchemaMigration,
    ScheduledTaskRecord,
)
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
    def __init__(
        self,
        *,
        existing_status: TaskStatus,
        existing_contract: AnalysisTaskCoalescingContract,
    ) -> None:
        super().__init__()
        self.existing_task_id = "existing-execution"
        self.existing_contract = existing_contract
        self.coalesce = True
        self.snapshots[self.existing_task_id] = self._snapshot(
            self.existing_task_id,
            existing_status,
        )

    def submit_tasks_batch(self, **kwargs):
        if not self.coalesce:
            return super().submit_tasks_batch(**kwargs)
        self.submit_calls.append(kwargs)
        requested_contract = AnalysisTaskCoalescingContract.from_metadata({
            **kwargs,
            "stock_code": kwargs["stock_codes"][0],
        })
        return [], [SimpleNamespace(
            existing_task_id=self.existing_task_id,
            existing_contract=self.existing_contract,
            requested_contract=requested_contract,
        )]


class DeferredExecutor:
    def submit(self, *_args, **_kwargs):
        return Future()

    def shutdown(self, *_args, **_kwargs):
        return None


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


@pytest.fixture
def real_task_queue():
    original = AnalysisTaskQueue._instance
    AnalysisTaskQueue._instance = None
    queue = AnalysisTaskQueue(max_workers=1)
    queue._executor = DeferredExecutor()
    try:
        yield queue
    finally:
        queue.shutdown()
        AnalysisTaskQueue._instance = original


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


def analysis_contract(**overrides) -> AnalysisTaskCoalescingContract:
    metadata = {
        "stock_code": "600519",
        "report_type": "detailed",
        "analysis_phase": "auto",
        "force_refresh": False,
        "notify": False,
        "skills": None,
        "report_language": None,
        "use_memory": None,
        "portfolio_context": None,
        "query_source": "scheduled_task",
        "context_bound": False,
    }
    metadata.update(overrides)
    contract = AnalysisTaskCoalescingContract.from_metadata(metadata)
    assert contract is not None
    return contract


def definition_values(row) -> dict:
    return {
        "id": row.id,
        "schema_version": row.schema_version,
        "name": row.name,
        "task_type": row.task_type,
        "schedule_kind": row.schedule_kind,
        "schedule_time": row.schedule_time,
        "timezone": row.timezone,
        "calendar_market": row.calendar_market,
        "non_trading_day_policy": row.non_trading_day_policy,
        "payload_json": row.payload_json,
        "enabled": row.enabled,
        "max_attempts": row.max_attempts,
        "next_run_at": row.next_run_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def build_service(
    database,
    queue=None,
    *,
    market_status=MarketSessionStatus.OPEN,
    market_session_provider=None,
):
    return ScheduledTaskService(
        repository=ScheduledTaskRepository(database),
        task_queue=queue or FakeTaskQueue(),
        clock=lambda: NOW,
        market_session_provider=(
            market_session_provider
            or (lambda _market, _date: market_status)
        ),
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


def test_daily_schedule_selects_second_fall_back_fold_after_first_passed() -> None:
    result = next_daily_run_at(
        schedule_time="01:30",
        timezone_name="America/New_York",
        after=datetime(2026, 11, 1, 6, 15, tzinfo=timezone.utc),
    )

    assert result == datetime(2026, 11, 1, 6, 30)


def test_daily_schedule_skips_nonexistent_spring_forward_wall_time() -> None:
    result = next_daily_run_at(
        schedule_time="02:30",
        timezone_name="America/New_York",
        after=datetime(2026, 3, 8, 6, 0, tzinfo=timezone.utc),
    )

    assert result == datetime(2026, 3, 9, 6, 30)


def test_market_calendar_uses_exchange_date_not_schedule_timezone(database) -> None:
    observed_dates = []
    queue = FakeTaskQueue()
    service = build_service(
        database,
        queue,
        market_session_provider=lambda _market, session_date: (
            observed_dates.append(session_date) or MarketSessionStatus.CLOSED
        ),
    )
    contract = task_contract()
    contract["schedule"].update({
        "time": "08:00",
        "timezone": "Asia/Tokyo",
        "calendar_market": "us",
    })
    contract["payload"]["stock_code"] = "AAPL"
    due = datetime(2026, 7, 5, 23, 0)
    service.create_task(contract, now=due - timedelta(minutes=1))

    result = service.tick(now=due)

    assert result == {"reconciled": 0, "claimed": 0, "skipped": 1}
    assert observed_dates == [date(2026, 7, 5)]
    assert queue.submit_calls == []


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
    service = build_service(
        database,
        queue,
        market_status=MarketSessionStatus.CLOSED,
    )
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
    service = build_service(
        database,
        queue,
        market_status=MarketSessionStatus.CLOSED,
    )
    service.create_task(task_contract(policy="run"), now=NOW)

    result = service.tick(now=DUE)

    assert result["claimed"] == 1
    assert len(queue.submit_calls) == 1


@pytest.mark.parametrize(
    "market_session_provider",
    [
        lambda _market, _date: MarketSessionStatus.UNKNOWN,
        lambda _market, _date: (_ for _ in ()).throw(RuntimeError("calendar down")),
    ],
)
def test_unknown_calendar_never_dispatches_financial_work(
    database,
    market_session_provider,
) -> None:
    queue = FakeTaskQueue()
    service = build_service(
        database,
        queue,
        market_session_provider=market_session_provider,
    )
    task = service.create_task(task_contract(policy="skip"), now=NOW)

    result = service.tick(now=DUE)

    assert result == {"reconciled": 0, "claimed": 0, "skipped": 1}
    assert queue.submit_calls == []
    run = service.list_runs(task["id"])["items"][0]
    assert run["status"] == "interrupted"
    assert run["error_code"] == "scheduled_task_calendar_unavailable"


def test_failed_compatible_external_execution_is_resubmitted_not_retried(
    database,
) -> None:
    queue = CoalescingTaskQueue(
        existing_status=TaskStatus.PENDING,
        existing_contract=analysis_contract(),
    )
    service = build_service(database, queue)
    task = service.create_task(task_contract(max_attempts=3), now=NOW)

    service.tick(now=DUE)

    running = service.get_status(task["id"])["latest_run"]
    assert running["status"] == "running"
    assert running["execution_task_ids"] == [queue.existing_task_id]
    assert len(queue.submit_calls) == 1

    queue.set_status(queue.existing_task_id, TaskStatus.FAILED)
    service.tick(now=DUE + timedelta(seconds=1))

    waiting = service.get_status(task["id"])["latest_run"]
    assert waiting["status"] == "retry_wait"
    assert waiting["attempt_count"] == 1
    assert waiting["error_code"] == "scheduled_task_coalesced_execution_failed"
    assert queue.retry_calls == []

    queue.coalesce = False
    service.tick(now=DUE + timedelta(seconds=31))

    running = service.get_status(task["id"])["latest_run"]
    assert running["status"] == "running"
    assert running["attempt_count"] == 2
    assert running["execution_task_ids"] == [
        queue.existing_task_id,
        "execution-1",
    ]
    assert queue.retry_calls == []


@pytest.mark.parametrize(
    ("report_type", "notify"),
    [("brief", False), ("detailed", True)],
)
def test_real_queue_waits_for_mismatched_contract_then_dispatches(
    database,
    real_task_queue,
    report_type,
    notify,
) -> None:
    accepted, duplicates = real_task_queue.submit_tasks_batch(
        ["600519"],
        report_type=report_type,
        notify=notify,
    )
    assert len(accepted) == 1
    assert duplicates == []
    service = build_service(database, real_task_queue)
    task = service.create_task(task_contract(max_attempts=3), now=NOW)

    service.tick(now=DUE)

    waiting = service.get_status(task["id"])["latest_run"]
    assert waiting["status"] == "retry_wait"
    assert waiting["attempt_count"] == 0
    assert waiting["execution_task_ids"] == []
    assert waiting["error_code"] == "scheduled_task_execution_conflict"

    with real_task_queue._data_lock:
        real_task_queue._terminalize_locked(
            real_task_queue._tasks[accepted[0].task_id],
            TaskStatus.COMPLETED,
            result={"stock_code": "600519"},
        )
    service.tick(now=DUE + timedelta(seconds=30))

    running = service.get_status(task["id"])["latest_run"]
    assert running["status"] == "running"
    assert running["attempt_count"] == 1
    assert len(running["execution_task_ids"]) == 1
    assert running["execution_task_ids"][0] != accepted[0].task_id


def test_real_queue_accepts_exact_coalescing_contract_without_owning_retry(
    database,
    real_task_queue,
) -> None:
    accepted, duplicates = real_task_queue.submit_tasks_batch(
        ["600519"],
        report_type="detailed",
        notify=False,
        query_source="scheduled_task",
    )
    assert duplicates == []
    existing_task_id = accepted[0].task_id
    service = build_service(database, real_task_queue)
    task = service.create_task(task_contract(max_attempts=3), now=NOW)

    service.tick(now=DUE)
    running = service.get_status(task["id"])["latest_run"]
    assert running["execution_task_ids"] == [existing_task_id]

    with real_task_queue._data_lock:
        existing = real_task_queue._tasks[existing_task_id]
        existing.status = TaskStatus.COMPLETED
        existing.result_ref = "matched-result"
    service.tick(now=DUE + timedelta(seconds=1))

    succeeded = service.get_status(task["id"])["latest_run"]
    assert succeeded["status"] == "succeeded"
    assert succeeded["result_refs"] == ["matched-result"]


def test_disable_interrupts_conflict_wait_before_any_dispatch(
    database,
    real_task_queue,
) -> None:
    accepted, duplicates = real_task_queue.submit_tasks_batch(
        ["600519"],
        force_refresh=True,
    )
    assert len(accepted) == 1
    assert duplicates == []
    service = build_service(database, real_task_queue)
    task = service.create_task(task_contract(max_attempts=1), now=NOW)
    service.tick(now=DUE)
    waiting = service.get_status(task["id"])["latest_run"]
    assert waiting["status"] == "retry_wait"
    assert waiting["attempt_count"] == 0

    service.set_enabled(task["id"], False, now=DUE + timedelta(seconds=1))
    service.tick(now=DUE + timedelta(seconds=1))

    interrupted = service.get_status(task["id"])["latest_run"]
    assert interrupted["status"] == "interrupted"
    assert interrupted["attempt_count"] == 0
    assert interrupted["execution_task_ids"] == []
    assert interrupted["error_code"] == "scheduled_task_disabled_before_dispatch"
    assert len(real_task_queue._tasks) == 1


def test_same_stock_different_schedules_execute_serially_with_one_attempt(
    database,
    real_task_queue,
) -> None:
    service = build_service(database, real_task_queue)
    brief_contract = task_contract(max_attempts=1)
    brief_contract["payload"]["report_type"] = "brief"
    detailed_contract = task_contract(max_attempts=1)
    detailed_contract["payload"]["notify"] = True
    tasks = [
        service.create_task(brief_contract, now=NOW),
        service.create_task(detailed_contract, now=NOW),
    ]

    service.tick(now=DUE)

    first_states = [service.get_status(item["id"])["latest_run"] for item in tasks]
    running = next(run for run in first_states if run["status"] == "running")
    waiting = next(run for run in first_states if run["status"] == "retry_wait")
    assert running["attempt_count"] == 1
    assert waiting["attempt_count"] == 0
    assert len(real_task_queue._analyzing_stocks) == 1

    with real_task_queue._data_lock:
        real_task_queue._terminalize_locked(
            real_task_queue._tasks[running["execution_task_ids"][0]],
            TaskStatus.COMPLETED,
            result={"stock_code": "600519"},
        )
    service.tick(now=DUE + timedelta(seconds=30))

    second_states = [service.get_status(item["id"])["latest_run"] for item in tasks]
    assert sorted(run["status"] for run in second_states) == ["running", "succeeded"]
    second_running = next(run for run in second_states if run["status"] == "running")
    assert second_running["attempt_count"] == 1
    assert len(real_task_queue._analyzing_stocks) == 1

    with real_task_queue._data_lock:
        real_task_queue._terminalize_locked(
            real_task_queue._tasks[second_running["execution_task_ids"][-1]],
            TaskStatus.COMPLETED,
            result={"stock_code": "600519"},
        )
    service.tick(now=DUE + timedelta(seconds=31))

    assert [
        service.get_status(item["id"])["latest_run"]["status"]
        for item in tasks
    ] == ["succeeded", "succeeded"]


def test_identical_schedules_share_one_canonical_execution(database, real_task_queue) -> None:
    service = build_service(database, real_task_queue)
    tasks = [
        service.create_task(task_contract(max_attempts=1), now=NOW),
        service.create_task(task_contract(max_attempts=1), now=NOW),
    ]

    service.tick(now=DUE)

    runs = [service.get_status(item["id"])["latest_run"] for item in tasks]
    execution_ids = {run["execution_task_ids"][0] for run in runs}
    assert len(execution_ids) == 1
    assert all(run["status"] == "running" for run in runs)
    assert len(real_task_queue._tasks) == 1

    execution_id = execution_ids.pop()
    with real_task_queue._data_lock:
        real_task_queue._terminalize_locked(
            real_task_queue._tasks[execution_id],
            TaskStatus.COMPLETED,
            result={"stock_code": "600519"},
        )
    service.tick(now=DUE + timedelta(seconds=1))

    assert [
        service.get_status(item["id"])["latest_run"]["status"]
        for item in tasks
    ] == ["succeeded", "succeeded"]


def test_service_defers_repository_initialization_until_first_use() -> None:
    calls = []
    repository = SimpleNamespace(has_enabled_tasks=lambda: False)
    service = ScheduledTaskService(
        repository_factory=lambda: calls.append("created") or repository,
    )

    assert calls == []
    assert service.has_enabled_tasks() is False
    assert calls == ["created"]


def test_tick_retries_repository_discovery_after_transient_failure() -> None:
    class FlakyRepository:
        def __init__(self):
            self.calls = 0

        def list_active_runs(self):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("database unavailable")
            return []

        def list_due_tasks(self, *, now):
            return []

    repository = FlakyRepository()
    service = ScheduledTaskService(repository=repository, clock=lambda: NOW)

    assert service.tick(now=NOW) == {"reconciled": 0, "claimed": 0, "skipped": 0}
    assert service.tick(now=NOW) == {"reconciled": 0, "claimed": 0, "skipped": 0}
    assert repository.calls == 2


def test_future_schema_reads_as_opaque_and_mutations_preserve_definition(database) -> None:
    service = build_service(database)
    task = service.create_task(task_contract(), now=NOW)
    with database.get_session() as session:
        row = session.get(ScheduledTaskRecord, task["id"])
        row.schema_version = 2
        row.payload_json = "not-v1-json"
        session.commit()
        expected = definition_values(row)

    listed = service.list_tasks()
    opaque = listed["items"][0]
    assert listed["total"] == 1
    assert opaque == {
        "compatibility": "unsupported_schema",
        "id": task["id"],
        "schema_version": 2,
        "name": "Morning analysis",
        "enabled": True,
        "next_run_at": expected["next_run_at"].replace(tzinfo=timezone.utc),
        "created_at": expected["created_at"].replace(tzinfo=timezone.utc),
        "updated_at": expected["updated_at"].replace(tzinfo=timezone.utc),
    }
    assert service.get_status(task["id"])["task"] == opaque
    with pytest.raises(ScheduledTaskUnsupportedSchemaError):
        service.set_enabled(task["id"], False, now=NOW)
    with database.get_session() as session:
        assert definition_values(session.get(ScheduledTaskRecord, task["id"])) == expected


def test_enablement_cas_never_rewrites_concurrently_upgraded_schema(
    database,
    monkeypatch,
) -> None:
    service = build_service(database)
    task = service.create_task(task_contract(), now=NOW)
    original_set_enabled = service.repository.set_enabled

    def upgrade_then_set_enabled(task_id, **kwargs):
        with database.get_session() as session:
            row = session.get(ScheduledTaskRecord, task_id)
            row.schema_version = 2
            session.commit()
        return original_set_enabled(task_id, **kwargs)

    monkeypatch.setattr(
        service.repository,
        "set_enabled",
        upgrade_then_set_enabled,
    )

    with pytest.raises(ScheduledTaskUnsupportedSchemaError):
        service.set_enabled(task["id"], False, now=NOW)

    with database.get_session() as session:
        persisted = session.get(ScheduledTaskRecord, task["id"])
        assert persisted.schema_version == 2
        assert persisted.enabled is True
        assert persisted.next_run_at == DUE


def test_claim_cas_never_dispatches_concurrently_upgraded_schema(
    database,
    monkeypatch,
) -> None:
    queue = FakeTaskQueue()
    service = build_service(database, queue)
    task = service.create_task(task_contract(), now=NOW)
    original_claim = service.repository.claim_due_occurrence

    def upgrade_then_claim(**kwargs):
        with database.get_session() as session:
            row = session.get(ScheduledTaskRecord, task["id"])
            row.schema_version = 2
            row.payload_json = "not-v1-json"
            session.commit()
        return original_claim(**kwargs)

    monkeypatch.setattr(
        service.repository,
        "claim_due_occurrence",
        upgrade_then_claim,
    )

    first = service.tick(now=DUE)
    second = service.tick(now=DUE + timedelta(seconds=1))

    assert first == {"reconciled": 0, "claimed": 0, "skipped": 1}
    assert second == {"reconciled": 0, "claimed": 0, "skipped": 0}
    assert queue.submit_calls == []
    with database.get_session() as session:
        persisted = session.get(ScheduledTaskRecord, task["id"])
        assert persisted.schema_version == 2
        assert persisted.enabled is True
        assert persisted.next_run_at == DUE
    run = service.list_runs(task["id"])["items"][0]
    assert run["error_code"] == "scheduled_task_schema_unsupported"


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("task_type", "research"),
        ("schedule_kind", "weekly"),
        ("non_trading_day_policy", "unknown"),
        (
            "payload_json",
            '{"notify":false,"report_type":"future","stock_code":"600519"}',
        ),
    ],
)
def test_tick_quarantines_incompatible_definition_once(
    database,
    field_name,
    value,
) -> None:
    queue = FakeTaskQueue()
    service = build_service(database, queue)
    task = service.create_task(task_contract(), now=NOW)
    with database.get_session() as session:
        row = session.get(ScheduledTaskRecord, task["id"])
        setattr(row, field_name, value)
        session.commit()

    first = service.tick(now=DUE)
    second = service.tick(now=DUE + timedelta(seconds=1))

    assert first == {"reconciled": 0, "claimed": 0, "skipped": 1}
    assert second == {"reconciled": 0, "claimed": 0, "skipped": 0}
    assert queue.submit_calls == []
    with database.get_session() as session:
        persisted = session.get(ScheduledTaskRecord, task["id"])
        assert persisted.enabled is False
        assert persisted.next_run_at is None
    runs = service.list_runs(task["id"])
    assert runs["total"] == 1
    assert runs["items"][0]["status"] == "interrupted"
    assert runs["items"][0]["error_code"] == "scheduled_task_definition_invalid"


def test_future_schema_due_slot_is_fenced_once_without_definition_rewrite(
    database,
) -> None:
    queue = FakeTaskQueue()
    service_a = build_service(database, queue)
    task = service_a.create_task(task_contract(), now=NOW)
    with database.get_session() as session:
        row = session.get(ScheduledTaskRecord, task["id"])
        row.schema_version = 2
        row.payload_json = "not-v1-json"
        session.commit()
        expected = definition_values(row)
    service_b = build_service(database, queue)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda service: service.tick(now=DUE), [service_a, service_b]))
    follow_up = service_a.tick(now=DUE + timedelta(seconds=1))

    assert sum(result["skipped"] for result in results) == 1
    assert follow_up == {"reconciled": 0, "claimed": 0, "skipped": 0}
    assert queue.submit_calls == []
    with database.get_session() as session:
        assert definition_values(session.get(ScheduledTaskRecord, task["id"])) == expected
    runs = service_a.list_runs(task["id"])
    assert runs["total"] == 1
    assert runs["items"][0]["status"] == "interrupted"
    assert runs["items"][0]["error_code"] == "scheduled_task_schema_unsupported"


def test_quarantine_cas_never_disables_concurrently_upgraded_schema(
    database,
    monkeypatch,
) -> None:
    queue = FakeTaskQueue()
    service = build_service(database, queue)
    task = service.create_task(task_contract(), now=NOW)
    with database.get_session() as session:
        row = session.get(ScheduledTaskRecord, task["id"])
        row.task_type = "corrupt-v1"
        session.commit()
    original_quarantine = service.repository.quarantine_due_task

    def upgrade_then_quarantine(**kwargs):
        with database.get_session() as session:
            row = session.get(ScheduledTaskRecord, task["id"])
            row.schema_version = 2
            session.commit()
        return original_quarantine(**kwargs)

    monkeypatch.setattr(
        service.repository,
        "quarantine_due_task",
        upgrade_then_quarantine,
    )

    first = service.tick(now=DUE)
    second = service.tick(now=DUE + timedelta(seconds=1))

    assert first == {"reconciled": 0, "claimed": 0, "skipped": 1}
    assert second == {"reconciled": 0, "claimed": 0, "skipped": 0}
    assert queue.submit_calls == []
    with database.get_session() as session:
        persisted = session.get(ScheduledTaskRecord, task["id"])
        assert persisted.schema_version == 2
        assert persisted.enabled is True
        assert persisted.next_run_at == DUE


def test_future_schema_interrupts_active_projection_without_rewriting_definition(
    database,
) -> None:
    queue = FakeTaskQueue()
    service = build_service(database, queue)
    task = service.create_task(task_contract(max_attempts=3), now=NOW)
    service.tick(now=DUE)
    running = service.get_status(task["id"])["latest_run"]
    assert running["status"] == "running"

    with database.get_session() as session:
        row = session.get(ScheduledTaskRecord, task["id"])
        row.schema_version = 2
        session.commit()
        expected = definition_values(row)

    first = service.tick(now=DUE + timedelta(seconds=1))
    second = service.tick(now=DUE + timedelta(seconds=2))

    assert first == {"reconciled": 1, "claimed": 0, "skipped": 0}
    assert second == {"reconciled": 0, "claimed": 0, "skipped": 0}
    assert len(queue.submit_calls) == 1
    with database.get_session() as session:
        persisted = session.get(ScheduledTaskRecord, task["id"])
        assert definition_values(persisted) == expected
    interrupted = service.list_runs(task["id"])["items"][0]
    assert interrupted["status"] == "interrupted"
    assert interrupted["execution_task_ids"] == running["execution_task_ids"]
    assert interrupted["error_code"] == "scheduled_task_schema_unsupported"


def test_active_quarantine_cas_reclassifies_concurrently_upgraded_schema(
    database,
    monkeypatch,
) -> None:
    queue = FakeTaskQueue()
    service = build_service(database, queue)
    task = service.create_task(task_contract(max_attempts=2), now=NOW)
    service.tick(now=DUE)
    with database.get_session() as session:
        row = session.get(ScheduledTaskRecord, task["id"])
        row.task_type = "corrupt-v1"
        session.commit()
    original_set_enabled = service.repository.set_enabled

    def upgrade_then_set_enabled(task_id, **kwargs):
        with database.get_session() as session:
            row = session.get(ScheduledTaskRecord, task_id)
            row.schema_version = 2
            session.commit()
        return original_set_enabled(task_id, **kwargs)

    monkeypatch.setattr(
        service.repository,
        "set_enabled",
        upgrade_then_set_enabled,
    )

    service.tick(now=DUE + timedelta(seconds=1))

    with database.get_session() as session:
        persisted = session.get(ScheduledTaskRecord, task["id"])
        assert persisted.schema_version == 2
        assert persisted.enabled is True
        assert persisted.next_run_at > DUE
    interrupted = service.list_runs(task["id"])["items"][0]
    assert interrupted["status"] == "interrupted"
    assert interrupted["error_code"] == "scheduled_task_schema_unsupported"
    assert len(queue.submit_calls) == 1


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
    assert failed["execution_task_ids"] == ["execution-1", "execution-2"]


def test_disable_after_owned_execution_failure_prevents_new_retry(
    database,
) -> None:
    queue = FakeTaskQueue(initial_status=TaskStatus.PENDING)
    service = build_service(database, queue)
    task = service.create_task(task_contract(max_attempts=2), now=NOW)
    service.tick(now=DUE)
    running = service.get_status(task["id"])["latest_run"]

    service.set_enabled(task["id"], False, now=DUE + timedelta(seconds=1))
    queue.set_status(running["execution_task_ids"][0], TaskStatus.FAILED)
    service.tick(now=DUE + timedelta(seconds=1))

    interrupted = service.get_status(task["id"])["latest_run"]
    assert interrupted["status"] == "interrupted"
    assert interrupted["attempt_count"] == 1
    assert interrupted["error_code"] == "scheduled_task_disabled_before_retry"
    assert queue.retry_calls == []
    assert len(queue.submit_calls) == 1


def test_execution_ids_remain_append_only_across_multiple_retries(database) -> None:
    queue = FakeTaskQueue(
        initial_status=TaskStatus.FAILED,
        retry_status=TaskStatus.FAILED,
    )
    service = build_service(database, queue)
    task = service.create_task(task_contract(max_attempts=3), now=NOW)

    service.tick(now=DUE)
    service.tick(now=DUE + timedelta(seconds=30))
    service.tick(now=DUE + timedelta(seconds=60))

    failed = service.get_status(task["id"])["latest_run"]
    assert failed["status"] == "failed"
    assert failed["attempt_count"] == 3
    assert failed["execution_task_ids"] == [
        "execution-1",
        "execution-2",
        "execution-3",
    ]
    assert queue.retry_calls == ["execution-1", "execution-2"]


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
