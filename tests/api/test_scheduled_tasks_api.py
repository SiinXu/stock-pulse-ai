"""HTTP contract tests for scheduled-task CRUD and status routes."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api.v1.endpoints import scheduled_tasks
from src.config import Config
from src.repositories.scheduled_task_repo import ScheduledTaskRepository
from src.services.scheduled_task_service import ScheduledTaskService
from src.storage import DatabaseManager


class FakeRuntimeScheduler:
    def __init__(self) -> None:
        self.reconcile_calls = 0

    def reconcile_scheduled_tasks(self) -> None:
        self.reconcile_calls += 1


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
            yield test_client, runtime_scheduler
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
    test_client, runtime_scheduler = client

    created_response = test_client.post(
        "/api/v1/scheduled-tasks",
        json=create_payload(),
    )
    assert created_response.status_code == 201, created_response.text
    created = created_response.json()
    task_id = created["id"]
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
    test_client, runtime_scheduler = client
    payload = create_payload()
    payload["schedule"]["timezone"] = "Mars/Olympus"

    response = test_client.post("/api/v1/scheduled-tasks", json=payload)

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "scheduled_task_validation_error"
    assert test_client.get("/api/v1/scheduled-tasks").json()["total"] == 0
    assert runtime_scheduler.reconcile_calls == 0


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
    ]
    for path in paths:
        assert static["paths"][path] == runtime["paths"][path]
    for schema in schemas:
        assert static["components"]["schemas"][schema] == (
            runtime["components"]["schemas"][schema]
        )
