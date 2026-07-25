"""HTTP contract tests for scheduled-task CRUD and status routes."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from api.v1.endpoints import scheduled_tasks
from api.v1.schemas.scheduled_tasks import (
    DailyScheduleRequest,
    ScheduledTaskCreateRequest,
    ScheduledTaskItem,
    ScheduledTaskListResponse,
    ScheduledTaskRunItem,
    ScheduledTaskRunListResponse,
    ScheduledTaskStatusResponse,
    StockAnalysisScheduledPayload,
    UnsupportedScheduledTaskItem,
)
from src.config import Config
from src.repositories.scheduled_task_repo import ScheduledTaskRepository
from src.services.scheduled_task_service import ScheduledTaskService
from src.storage import DatabaseManager, ScheduledTaskRecord


class FakeRuntimeScheduler:
    def __init__(self) -> None:
        self.reconcile_calls = 0
        self.error = None

    def reconcile_scheduled_tasks(self) -> None:
        self.reconcile_calls += 1
        if self.error is not None:
            raise self.error


@pytest.fixture
def client(tmp_path):
    DatabaseManager.reset_instance()
    Config.reset_instance()
    database = DatabaseManager(db_url=f"sqlite:///{tmp_path / 'api.sqlite'}")
    service = ScheduledTaskService(
        repository=ScheduledTaskRepository(database),
    )
    runtime_scheduler = FakeRuntimeScheduler()
    app = FastAPI()
    app.include_router(
        scheduled_tasks.router,
        prefix="/api/v1/scheduled-tasks",
    )
    app.state.scheduled_task_service = service
    app.state.runtime_scheduler_service = runtime_scheduler
    try:
        with TestClient(app) as test_client:
            yield test_client, runtime_scheduler, service
    finally:
        DatabaseManager.reset_instance()
        Config.reset_instance()


def create_payload():
    return {
        "schema_version": 1,
        "name": "US close analysis",
        "task_type": "stock_analysis",
        "schedule": {
            "kind": "daily",
            "time": "16:30",
            "timezone": "America/New_York",
            "calendar_market": "us",
            "non_trading_day_policy": "skip",
        },
        "payload": {
            "stock_code": "AAPL",
            "report_type": "brief",
            "notify": True,
        },
        "enabled": True,
        "max_attempts": 2,
    }


def test_create_list_status_toggle_and_run_history(client) -> None:
    test_client, runtime_scheduler, _service = client

    created_response = test_client.post(
        "/api/v1/scheduled-tasks",
        json=create_payload(),
    )
    assert created_response.status_code == 201, created_response.text
    created = created_response.json()
    task_id = created["id"]
    assert created["compatibility"] == "supported"
    assert created["schema_version"] == 1
    assert created["next_run_at"].endswith("Z")

    listed = test_client.get("/api/v1/scheduled-tasks").json()
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == task_id

    status = test_client.get(
        f"/api/v1/scheduled-tasks/{task_id}/status"
    ).json()
    assert status["task"]["id"] == task_id
    assert status["latest_run"] is None

    disabled = test_client.post(
        f"/api/v1/scheduled-tasks/{task_id}/disable"
    ).json()
    assert disabled["enabled"] is False
    assert disabled["next_run_at"] is None

    enabled = test_client.post(
        f"/api/v1/scheduled-tasks/{task_id}/enable"
    ).json()
    assert enabled["enabled"] is True
    assert enabled["next_run_at"] is not None

    runs = test_client.get(
        f"/api/v1/scheduled-tasks/{task_id}/runs"
    ).json()
    assert runs == {"items": [], "total": 0}
    assert runtime_scheduler.reconcile_calls == 3


def test_invalid_iana_timezone_is_rejected_without_creating_task(client) -> None:
    test_client, runtime_scheduler, _service = client
    payload = create_payload()
    payload["schedule"]["timezone"] = "Mars/Olympus"

    response = test_client.post("/api/v1/scheduled-tasks", json=payload)

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "scheduled_task_validation_error"
    assert test_client.get("/api/v1/scheduled-tasks").json()["total"] == 0
    assert runtime_scheduler.reconcile_calls == 0


def test_create_request_applies_declared_defaults(client) -> None:
    test_client, _runtime_scheduler, _service = client

    response = test_client.post(
        "/api/v1/scheduled-tasks",
        json={
            "name": "Default contract",
            "schedule": {
                "time": "16:30",
                "timezone": "America/New_York",
                "calendar_market": "us",
            },
            "payload": {"stock_code": "AAPL"},
        },
    )

    assert response.status_code == 201, response.text
    created = response.json()
    assert created["schema_version"] == 1
    assert created["task_type"] == "stock_analysis"
    assert created["schedule"]["kind"] == "daily"
    assert created["schedule"]["non_trading_day_policy"] == "skip"
    assert created["payload"]["report_type"] == "detailed"
    assert created["payload"]["notify"] is True
    assert created["enabled"] is True
    assert created["max_attempts"] == 1


@pytest.mark.parametrize("section", ["task", "schedule", "payload"])
def test_create_request_forbids_extra_fields_at_every_object_boundary(
    client,
    section: str,
) -> None:
    test_client, runtime_scheduler, _service = client
    payload = create_payload()
    target = payload if section == "task" else payload[section]
    target["unexpected"] = "value"

    response = test_client.post("/api/v1/scheduled-tasks", json=payload)

    assert response.status_code == 422
    assert test_client.get("/api/v1/scheduled-tasks").json()["total"] == 0
    assert runtime_scheduler.reconcile_calls == 0


@pytest.mark.parametrize(
    ("path", "coerced_value"),
    [
        (("schema_version",), "1"),
        (("enabled",), "true"),
        (("max_attempts",), "2"),
        (("payload", "notify"), "false"),
    ],
)
def test_create_request_rejects_scalar_coercion(
    client,
    path: tuple[str, ...],
    coerced_value: str,
) -> None:
    test_client, runtime_scheduler, _service = client
    payload = create_payload()
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = coerced_value

    response = test_client.post("/api/v1/scheduled-tasks", json=payload)

    assert response.status_code == 422
    assert test_client.get("/api/v1/scheduled-tasks").json()["total"] == 0
    assert runtime_scheduler.reconcile_calls == 0


def test_scheduled_task_dtos_publish_explicit_strict_extra_policy() -> None:
    models = (
        DailyScheduleRequest,
        StockAnalysisScheduledPayload,
        ScheduledTaskCreateRequest,
        ScheduledTaskItem,
        UnsupportedScheduledTaskItem,
        ScheduledTaskListResponse,
        ScheduledTaskRunItem,
        ScheduledTaskRunListResponse,
        ScheduledTaskStatusResponse,
    )

    for model in models:
        assert model.model_config["strict"] is True
        assert model.model_config["extra"] == "forbid"


def test_scheduled_task_response_rejects_coercion_and_extra_fields(client) -> None:
    test_client, _runtime_scheduler, service = client
    task_id = test_client.post(
        "/api/v1/scheduled-tasks",
        json=create_payload(),
    ).json()["id"]
    service_payload = service.get_task(task_id)

    assert ScheduledTaskItem.model_validate(service_payload).id == task_id

    wrong_scalar = deepcopy(service_payload)
    wrong_scalar["enabled"] = "true"
    with pytest.raises(ValidationError):
        ScheduledTaskItem.model_validate(wrong_scalar)

    nested_coercion = deepcopy(service_payload)
    nested_coercion["payload"]["notify"] = "true"
    with pytest.raises(ValidationError):
        ScheduledTaskItem.model_validate(nested_coercion)

    undeclared = deepcopy(service_payload)
    undeclared["unexpected"] = "value"
    with pytest.raises(ValidationError):
        ScheduledTaskItem.model_validate(undeclared)


def test_committed_create_remains_successful_when_runtime_reconcile_is_deferred(
    client,
) -> None:
    test_client, runtime_scheduler, _service = client
    runtime_scheduler.error = RuntimeError("scheduler thread unavailable")

    response = test_client.post(
        "/api/v1/scheduled-tasks",
        json=create_payload(),
    )

    assert response.status_code == 201, response.text
    assert response.json()["enabled"] is True
    assert runtime_scheduler.reconcile_calls == 1
    listed = test_client.get("/api/v1/scheduled-tasks").json()
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == response.json()["id"]


def test_future_schema_is_opaque_and_mutation_returns_conflict(client) -> None:
    test_client, runtime_scheduler, service = client
    created = test_client.post(
        "/api/v1/scheduled-tasks",
        json=create_payload(),
    ).json()
    with service.repository.db.get_session() as session:
        row = session.get(ScheduledTaskRecord, created["id"])
        row.schema_version = 2
        row.payload_json = "not-v1-json"
        session.commit()

    response = test_client.get("/api/v1/scheduled-tasks")
    status_response = test_client.get(
        f"/api/v1/scheduled-tasks/{created['id']}/status"
    )
    mutation_response = test_client.post(
        f"/api/v1/scheduled-tasks/{created['id']}/disable"
    )

    assert response.status_code == 200
    opaque = response.json()["items"][0]
    assert opaque["compatibility"] == "unsupported_schema"
    assert opaque["schema_version"] == 2
    assert "payload" not in opaque
    assert "schedule" not in opaque
    assert status_response.status_code == 200
    assert status_response.json()["task"] == opaque
    assert mutation_response.status_code == 409
    assert mutation_response.json()["detail"]["error"] == (
        "scheduled_task_schema_unsupported"
    )
    assert runtime_scheduler.reconcile_calls == 1
    with service.repository.db.get_session() as session:
        persisted = session.get(ScheduledTaskRecord, created["id"])
        assert persisted.schema_version == 2
        assert persisted.payload_json == "not-v1-json"
        assert persisted.enabled is True


def test_static_openapi_contains_exact_scheduled_task_contract() -> None:
    from api.app import create_app

    runtime = create_app().openapi()
    static = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "docs"
            / "architecture"
            / "api_spec.json"
        ).read_text(encoding="utf-8")
    )
    paths = [
        "/api/v1/scheduled-tasks",
        "/api/v1/scheduled-tasks/{task_id}/status",
        "/api/v1/scheduled-tasks/{task_id}/enable",
        "/api/v1/scheduled-tasks/{task_id}/disable",
        "/api/v1/scheduled-tasks/{task_id}/runs",
    ]
    schemas = [
        "DailyScheduleRequest",
        "ScheduledTaskCreateRequest",
        "ScheduledTaskItem",
        "ScheduledTaskListResponse",
        "ScheduledTaskRunItem",
        "ScheduledTaskRunListResponse",
        "ScheduledTaskStatusResponse",
        "StockAnalysisScheduledPayload",
        "UnsupportedScheduledTaskItem",
    ]
    for path in paths:
        assert static["paths"][path] == runtime["paths"][path]
    for schema in schemas:
        assert static["components"]["schemas"][schema] == (
            runtime["components"]["schemas"][schema]
        )
