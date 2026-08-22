# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Fail-closed scheduled-task create/enable/disable security-audit coverage."""

from __future__ import annotations

import json
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import deps as api_deps
from src.api.v1.endpoints import scheduled_tasks
from src.config import Config
from src.repositories.scheduled_task_repo import ScheduledTaskRepository
from src.services.scheduled_task_service import (
    SCHEDULED_TASK_WRITE_EVENT_TYPE,
    ScheduledTaskMutationAuditCompletionUnavailable,
    ScheduledTaskNotFoundError,
    ScheduledTaskService,
    ScheduledTaskValidationError,
)
from src.services.security_audit_service import (
    SecurityAuditService,
    SecurityAuditUnavailable,
)
from src.storage import DatabaseManager
from tests.security.test_security_audit_integrations import _RecordingAudit
from tests.services.test_scheduled_task_service import NOW, build_service, task_contract


CANARY = "mutation-audit-canary-secret"
PII_NAME = "user-canary-alice"


class FakeRuntimeScheduler:
    def reconcile_scheduled_tasks(self) -> None:
        return None


@pytest.fixture
def mutation_database(tmp_path):
    DatabaseManager.reset_instance()
    Config.reset_instance()
    manager = DatabaseManager(db_url=f"sqlite:///{tmp_path / 'scheduled-mutation-audit.sqlite'}")
    try:
        yield manager
    finally:
        DatabaseManager.reset_instance()
        Config.reset_instance()


def _visible_audit_payload(audit: _RecordingAudit) -> str:
    return json.dumps(
        {"attempts": audit.attempts, "completions": audit.completions},
        ensure_ascii=False,
        default=str,
    )


def _write_events(audit: _RecordingAudit, *, phase: str) -> list[dict]:
    source = audit.attempts if phase == "attempt" else audit.completions
    return [
        event
        for event in source
        if event.get("event_type") == SCHEDULED_TASK_WRITE_EVENT_TYPE
    ]


def _secret_contract() -> dict:
    contract = task_contract()
    contract["name"] = f"{PII_NAME}-{CANARY}"
    return contract


def test_create_records_attempt_and_success_without_payload_secrets(
    mutation_database,
) -> None:
    audit = _RecordingAudit()
    service = build_service(
        mutation_database,
        security_audit_factory=lambda: audit,
    )

    created = service.create_task(
        _secret_contract(),
        now=NOW,
        actor_type="administrator",
        actor_id="authenticated_admin",
    )

    attempts = _write_events(audit, phase="attempt")
    completions = _write_events(audit, phase="completion")
    assert len(attempts) == 1
    assert len(completions) == 1
    assert attempts[0]["action"] == "scheduled_task.create"
    assert attempts[0]["target_type"] == "scheduled_task"
    assert attempts[0]["target_id"] == created["id"]
    assert attempts[0]["actor_type"] == "administrator"
    assert attempts[0]["actor_id"] == "authenticated_admin"
    assert attempts[0]["correlation_id"] == completions[0]["correlation_id"]
    assert completions[0]["outcome"] == "success"
    assert completions[0]["reason_code"] == "scheduled_task_created"
    assert completions[0]["metadata"]["task_type"] == "stock_analysis"
    assert "password" not in completions[0]["metadata"]
    assert "payload" not in completions[0]["metadata"]
    assert "name" not in completions[0]["metadata"]
    visible = _visible_audit_payload(audit)
    assert CANARY not in visible
    assert PII_NAME not in visible


def test_create_attempt_failure_does_not_persist(mutation_database) -> None:
    audit = _RecordingAudit(fail_attempt=True)
    service = build_service(
        mutation_database,
        security_audit_factory=lambda: audit,
    )

    with pytest.raises(SecurityAuditUnavailable):
        service.create_task(task_contract(), now=NOW)

    assert service.list_tasks()["total"] == 0
    assert audit.attempts == []
    assert audit.completions == []


def test_create_validation_failure_records_rejected_completion(
    mutation_database,
) -> None:
    audit = _RecordingAudit()
    service = build_service(
        mutation_database,
        security_audit_factory=lambda: audit,
    )
    contract = task_contract()
    contract["name"] = ""

    with pytest.raises(ScheduledTaskValidationError):
        service.create_task(contract, now=NOW)

    attempts = _write_events(audit, phase="attempt")
    completions = _write_events(audit, phase="completion")
    assert len(attempts) == 1
    assert completions[0]["outcome"] == "rejected"
    assert completions[0]["reason_code"] == "scheduled_task_validation_error"
    assert attempts[0]["correlation_id"] == completions[0]["correlation_id"]
    assert service.list_tasks()["total"] == 0


def test_enable_and_disable_share_correlation_per_mutation(mutation_database) -> None:
    audit = _RecordingAudit()
    service = build_service(
        mutation_database,
        security_audit_factory=lambda: audit,
    )
    created = service.create_task(task_contract(), now=NOW)

    disabled = service.set_enabled(
        created["id"],
        False,
        now=NOW,
        actor_id="local_operator",
    )
    enabled = service.set_enabled(
        created["id"],
        True,
        now=NOW,
        actor_id="local_operator",
    )

    assert disabled["enabled"] is False
    assert enabled["enabled"] is True
    mutations = [
        event
        for event in audit.attempts
        if event["action"] in {"scheduled_task.enable", "scheduled_task.disable"}
    ]
    completions = [
        event
        for event in audit.completions
        if event["action"] in {"scheduled_task.enable", "scheduled_task.disable"}
    ]
    assert [event["action"] for event in mutations] == [
        "scheduled_task.disable",
        "scheduled_task.enable",
    ]
    assert completions[0]["reason_code"] == "scheduled_task_disabled"
    assert completions[1]["reason_code"] == "scheduled_task_enabled"
    assert mutations[0]["correlation_id"] == completions[0]["correlation_id"]
    assert mutations[1]["correlation_id"] == completions[1]["correlation_id"]
    assert mutations[0]["correlation_id"] != mutations[1]["correlation_id"]
    assert mutations[0]["target_id"] == created["id"]


def test_idempotent_enable_records_already_enabled(mutation_database) -> None:
    audit = _RecordingAudit()
    service = build_service(
        mutation_database,
        security_audit_factory=lambda: audit,
    )
    created = service.create_task(task_contract(), now=NOW)
    audit.attempts.clear()
    audit.completions.clear()

    same = service.set_enabled(created["id"], True, now=NOW)

    assert same["enabled"] is True
    completions = _write_events(audit, phase="completion")
    assert completions[0]["outcome"] == "success"
    assert completions[0]["reason_code"] == "already_enabled"
    assert completions[0]["metadata"]["idempotent"] is True


def test_enable_missing_task_records_rejected_and_does_not_create(
    mutation_database,
) -> None:
    audit = _RecordingAudit()
    service = build_service(
        mutation_database,
        security_audit_factory=lambda: audit,
    )

    with pytest.raises(ScheduledTaskNotFoundError):
        service.set_enabled("missingtaskid00000000000000000000", True, now=NOW)

    completions = _write_events(audit, phase="completion")
    assert completions[0]["outcome"] == "rejected"
    assert completions[0]["reason_code"] == "scheduled_task_not_found"
    assert service.list_tasks()["total"] == 0


def test_enable_attempt_failure_does_not_change_enabled_state(
    mutation_database,
) -> None:
    audit = _RecordingAudit()
    service = build_service(
        mutation_database,
        security_audit_factory=lambda: audit,
    )
    created = service.create_task(task_contract(), now=NOW)
    audit.fail_attempt = True

    with pytest.raises(SecurityAuditUnavailable):
        service.set_enabled(created["id"], False, now=NOW)

    assert service.get_task(created["id"])["enabled"] is True


def test_create_completion_failure_keeps_persisted_task(mutation_database) -> None:
    audit = _RecordingAudit(fail_completion=True)
    service = build_service(
        mutation_database,
        security_audit_factory=lambda: audit,
    )

    with pytest.raises(ScheduledTaskMutationAuditCompletionUnavailable) as exc_info:
        service.create_task(task_contract(), now=NOW)

    assert service.list_tasks()["total"] == 1
    assert exc_info.value.item["id"] == service.list_tasks()["items"][0]["id"]
    assert len(_write_events(audit, phase="attempt")) == 1
    assert _write_events(audit, phase="completion") == []


def test_mutation_events_are_queryable_from_durable_store(mutation_database) -> None:
    store = SecurityAuditService()
    service = build_service(
        mutation_database,
        security_audit_factory=lambda: store,
    )

    created = service.create_task(task_contract(), now=NOW)
    service.set_enabled(created["id"], False, now=NOW)

    page = store.list_events(event_type=SCHEDULED_TASK_WRITE_EVENT_TYPE, page_size=20)
    types = {(item.phase, item.action, item.outcome) for item in page.items}
    assert ("attempt", "scheduled_task.create", "pending") in types
    assert ("completion", "scheduled_task.create", "success") in types
    assert ("attempt", "scheduled_task.disable", "pending") in types
    assert ("completion", "scheduled_task.disable", "success") in types
    assert page.total >= 4
    for item in page.items:
        assert item.target.id == created["id"]
        assert "password" not in json.dumps(item.metadata)


def test_http_create_enable_disable_use_local_operator_actor(mutation_database) -> None:
    audit = _RecordingAudit()
    service = ScheduledTaskService(
        repository=ScheduledTaskRepository(mutation_database),
        clock=lambda: datetime(2026, 7, 25, 12, 0),
        security_audit_factory=lambda: audit,
    )
    app = FastAPI()
    app.include_router(scheduled_tasks.router, prefix="/api/v1/scheduled-tasks")
    app.state.scheduled_task_service = service
    app.state.runtime_scheduler_service = FakeRuntimeScheduler()
    app.dependency_overrides[api_deps.require_security_audit_service] = lambda: audit

    payload = {
        "schema_version": 1,
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
        "name": f"US close {PII_NAME} {CANARY}",
        "enabled": True,
        "max_attempts": 2,
    }
    with TestClient(app) as client:
        created = client.post("/api/v1/scheduled-tasks", json=payload)
        assert created.status_code == 201, created.text
        task_id = created.json()["id"]
        disabled = client.post(f"/api/v1/scheduled-tasks/{task_id}/disable")
        assert disabled.status_code == 200, disabled.text
        enabled = client.post(f"/api/v1/scheduled-tasks/{task_id}/enable")
        assert enabled.status_code == 200, enabled.text

    actions = [event["action"] for event in _write_events(audit, phase="attempt")]
    assert actions == [
        "scheduled_task.create",
        "scheduled_task.disable",
        "scheduled_task.enable",
    ]
    for event in _write_events(audit, phase="attempt"):
        assert event["actor_type"] == "administrator"
        assert event["actor_id"] == "local_operator"
        assert event["target_id"] == task_id
    visible = _visible_audit_payload(audit)
    assert CANARY not in visible


def test_http_create_fails_closed_when_audit_attempt_unavailable(
    mutation_database,
) -> None:
    audit = _RecordingAudit(fail_attempt=True)
    service = ScheduledTaskService(
        repository=ScheduledTaskRepository(mutation_database),
        clock=lambda: datetime(2026, 7, 25, 12, 0),
        security_audit_factory=lambda: audit,
    )
    app = FastAPI()
    app.include_router(scheduled_tasks.router, prefix="/api/v1/scheduled-tasks")
    app.state.scheduled_task_service = service
    app.state.runtime_scheduler_service = FakeRuntimeScheduler()
    app.dependency_overrides[api_deps.require_security_audit_service] = lambda: audit

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/scheduled-tasks",
            json={
                "name": "Blocked create",
                "schedule": {
                    "time": "16:30",
                    "timezone": "America/New_York",
                    "calendar_market": "us",
                },
                "payload": {"stock_code": "AAPL"},
            },
        )

    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "security_audit_unavailable"
    assert response.json()["detail"]["operation_completed"] is False
    assert service.list_tasks()["total"] == 0


def test_idempotent_enable_completion_failure_is_not_rewritten_as_mutation_failure(
    mutation_database,
) -> None:
    audit = _RecordingAudit()
    service = build_service(
        mutation_database,
        security_audit_factory=lambda: audit,
    )
    created = service.create_task(task_contract(), now=NOW)

    class _FailFirstCompletion:
        def __init__(self, inner: _RecordingAudit) -> None:
            self.inner = inner
            self.failed = False

        def record_attempt(self, **fields):
            return self.inner.record_attempt(**fields)

        def record_completion(self, **fields):
            if not self.failed:
                self.failed = True
                raise SecurityAuditUnavailable()
            return self.inner.record_completion(**fields)

    with pytest.raises(ScheduledTaskMutationAuditCompletionUnavailable) as exc_info:
        service.set_enabled(
            created["id"],
            True,
            now=NOW,
            security_audit=_FailFirstCompletion(audit),
        )

    assert exc_info.value.item["id"] == created["id"]
    assert service.get_task(created["id"])["enabled"] is True
    enable_completions = [
        event
        for event in _write_events(audit, phase="completion")
        if event["action"] == "scheduled_task.enable"
    ]
    assert enable_completions == []
    assert all(
        event["reason_code"] != "scheduled_task_mutation_failed"
        for event in audit.completions
    )


def test_create_validation_failure_is_not_masked_by_completion_unavailable(
    mutation_database,
) -> None:
    audit = _RecordingAudit(fail_completion=True)
    service = build_service(
        mutation_database,
        security_audit_factory=lambda: audit,
    )
    contract = task_contract()
    contract["name"] = ""

    with pytest.raises(ScheduledTaskValidationError):
        service.create_task(contract, now=NOW)

    assert service.list_tasks()["total"] == 0
    assert len(_write_events(audit, phase="attempt")) == 1
    assert _write_events(audit, phase="completion") == []


def test_enable_missing_task_is_not_masked_by_completion_unavailable(
    mutation_database,
) -> None:
    audit = _RecordingAudit(fail_completion=True)
    service = build_service(
        mutation_database,
        security_audit_factory=lambda: audit,
    )

    with pytest.raises(ScheduledTaskNotFoundError):
        service.set_enabled("missingtaskid00000000000000000000", True, now=NOW)

    assert service.list_tasks()["total"] == 0
    assert len(_write_events(audit, phase="attempt")) == 1
    assert _write_events(audit, phase="completion") == []


def _mutation_http_app(mutation_database, audit):
    service = ScheduledTaskService(
        repository=ScheduledTaskRepository(mutation_database),
        clock=lambda: datetime(2026, 7, 25, 12, 0),
        security_audit_factory=lambda: audit,
    )
    app = FastAPI()
    app.include_router(scheduled_tasks.router, prefix="/api/v1/scheduled-tasks")
    app.state.scheduled_task_service = service
    app.state.runtime_scheduler_service = FakeRuntimeScheduler()
    app.dependency_overrides[api_deps.require_security_audit_service] = lambda: audit
    return app, service


def test_http_create_completion_failure_reports_operation_completed(
    mutation_database,
) -> None:
    audit = _RecordingAudit(fail_completion=True)
    app, service = _mutation_http_app(mutation_database, audit)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/scheduled-tasks",
            json={
                "name": "Completed write",
                "schedule": {
                    "time": "16:30",
                    "timezone": "America/New_York",
                    "calendar_market": "us",
                },
                "payload": {"stock_code": "AAPL"},
            },
        )

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["error"] == "security_audit_unavailable"
    assert detail["operation_completed"] is True
    assert service.list_tasks()["total"] == 1
    assert detail["task_id"] == service.list_tasks()["items"][0]["id"]
    assert detail["enabled"] is True


def test_http_enable_completion_failure_reports_operation_completed(
    mutation_database,
) -> None:
    audit = _RecordingAudit()
    app, service = _mutation_http_app(mutation_database, audit)
    created = service.create_task(task_contract(), now=datetime(2026, 7, 25, 12, 0))
    audit.fail_completion = True

    with TestClient(app) as client:
        response = client.post(f"/api/v1/scheduled-tasks/{created['id']}/disable")

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["error"] == "security_audit_unavailable"
    assert detail["operation_completed"] is True
    assert detail["task_id"] == created["id"]
    assert detail["enabled"] is False
    assert service.get_task(created["id"])["enabled"] is False


def test_http_validation_failure_is_not_masked_by_completion_unavailable(
    mutation_database,
) -> None:
    audit = _RecordingAudit(fail_completion=True)
    app, service = _mutation_http_app(mutation_database, audit)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/scheduled-tasks",
            json={
                "name": "Invalid timezone",
                "schedule": {
                    "time": "16:30",
                    "timezone": "Mars/Olympus",
                    "calendar_market": "us",
                },
                "payload": {"stock_code": "AAPL"},
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "scheduled_task_validation_error"
    assert service.list_tasks()["total"] == 0


def test_http_enable_missing_task_is_not_masked_by_completion_unavailable(
    mutation_database,
) -> None:
    audit = _RecordingAudit(fail_completion=True)
    app, service = _mutation_http_app(mutation_database, audit)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/scheduled-tasks/missingtaskid00000000000000000000/enable"
        )

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "scheduled_task_not_found"
    assert service.list_tasks()["total"] == 0
