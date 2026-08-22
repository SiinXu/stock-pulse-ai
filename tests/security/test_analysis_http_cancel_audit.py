# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Fail-closed HTTP analysis-cancel security-audit coverage (#1062 DAG-3)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.api import deps as api_deps
from src.api.v1.endpoints import analysis as analysis_endpoint
from src.api.v1.endpoints import candidate_discovery as discovery_endpoint
from src.api.v1.errors import normalize_error_body
from src.api.v1.services.analysis_api_service import STOCK_ANALYSIS_TASK_KIND
from src.api.v1.services.analysis_cancel_audit import ANALYSIS_CANCEL_EVENT_TYPE
from src.config import Config
from src.repositories.security_audit_repo import SecurityAuditRepository
from src.schemas.security_audit import SecurityAuditEvent, SecurityAuditEventCreate
from src.services.security_audit_service import SecurityAuditService
from src.storage import DatabaseManager
from src.task_execution import TaskStatusEnum
from tests.api.analysis.test_analysis_task_cancel import _stock_analysis_task
from tests.security.test_security_audit_integrations import _RecordingAudit


CANARY = "cancel-audit-canary-secret"
CANARY_QUERY = f"please leak {CANARY} in original_query"


@pytest.fixture
def cancel_database(tmp_path):
    DatabaseManager.reset_instance()
    Config.reset_instance()
    manager = DatabaseManager(db_url=f"sqlite:///{tmp_path / 'analysis-cancel-audit.sqlite'}")
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


def _cancel_events(audit: _RecordingAudit, *, phase: str) -> list[dict]:
    source = audit.attempts if phase == "attempt" else audit.completions
    return [
        event
        for event in source
        if event.get("event_type") == ANALYSIS_CANCEL_EVENT_TYPE
    ]


def _submit_events(audit: _RecordingAudit) -> list[dict]:
    return [
        event
        for event in (*audit.attempts, *audit.completions)
        if event.get("event_type") == "analysis.submit"
    ]


def _apply_cancel(task, task_id: str, status=TaskStatusEnum.CANCEL_REQUESTED):
    task.status = status
    task.message = "任务请求取消"
    task.message_code = "task.cancel_requested"
    task.message_params = {}
    return SimpleNamespace(task_id=task_id, status=status, progress=task.progress)


def _queue_with_task(task, *, on_cancel=None) -> MagicMock:
    fake_queue = MagicMock()
    fake_queue.get_task.return_value = task

    def fake_cancel(task_id: str):
        if on_cancel is not None:
            return on_cancel(task, task_id)
        return _apply_cancel(task, task_id)

    fake_queue.cancel.side_effect = fake_cancel
    return fake_queue


def _call_cancel(task_id: str, audit: _RecordingAudit):
    return analysis_endpoint.cancel_analysis_task(task_id, security_audit=audit)


def _cancel_http_app(audit):
    app = FastAPI()
    app.include_router(analysis_endpoint.router, prefix="/api/v1/analysis")
    app.dependency_overrides[api_deps.require_security_audit_service] = lambda: audit
    return app


def test_processing_cancel_records_attempt_then_success_without_secrets() -> None:
    audit = _RecordingAudit()
    task = _stock_analysis_task(original_query=CANARY_QUERY, skills=["secret-skill"])
    fake_queue = _queue_with_task(task)
    with patch(
        "src.api.v1.endpoints.analysis.get_task_queue",
        return_value=fake_queue,
    ):
        payload = _call_cancel("task-analysis-1", audit)

    fake_queue.cancel.assert_called_once_with("task-analysis-1")
    assert payload.status == "cancel_requested"
    attempts = _cancel_events(audit, phase="attempt")
    completions = _cancel_events(audit, phase="completion")
    assert len(attempts) == 1
    assert len(completions) == 1
    assert attempts[0]["action"] == ANALYSIS_CANCEL_EVENT_TYPE
    assert attempts[0]["target_type"] == "analysis_task"
    assert attempts[0]["target_id"] == "task-analysis-1"
    assert attempts[0]["actor_type"] == "api_client"
    assert attempts[0]["actor_id"] == "analysis_canceller"
    assert attempts[0]["correlation_id"] == completions[0]["correlation_id"]
    assert completions[0]["outcome"] == "success"
    assert completions[0]["reason_code"] == "cancel_requested"
    assert completions[0]["metadata"]["kind"] == STOCK_ANALYSIS_TASK_KIND
    assert completions[0]["metadata"]["status_before"] == "processing"
    assert completions[0]["metadata"]["status_after"] == "cancel_requested"
    assert completions[0]["metadata"]["stock_code"] == "600519"
    assert "idempotent" not in completions[0]["metadata"]
    assert "original_query" not in completions[0]["metadata"]
    assert "skills" not in completions[0]["metadata"]
    visible = _visible_audit_payload(audit)
    assert CANARY not in visible
    assert _submit_events(audit) == []


def test_attempt_failure_does_not_call_cancel() -> None:
    audit = _RecordingAudit(fail_attempt=True)
    task = _stock_analysis_task()
    fake_queue = _queue_with_task(task)
    with patch(
        "src.api.v1.endpoints.analysis.get_task_queue",
        return_value=fake_queue,
    ):
        with pytest.raises(HTTPException) as caught:
            _call_cancel("task-analysis-1", audit)
    assert caught.value.status_code == 503
    assert caught.value.detail["operation_completed"] is False
    fake_queue.cancel.assert_not_called()
    assert task.status == TaskStatusEnum.PROCESSING
    assert audit.attempts == []
    assert audit.completions == []


def test_http_attempt_failure_reports_operation_completed_false() -> None:
    audit = _RecordingAudit(fail_attempt=True)
    task = _stock_analysis_task()
    fake_queue = _queue_with_task(task)
    app = _cancel_http_app(audit)
    with patch(
        "src.api.v1.endpoints.analysis.get_task_queue",
        return_value=fake_queue,
    ):
        with TestClient(app) as client:
            response = client.post("/api/v1/analysis/tasks/task-analysis-1/cancel")
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["error"] == "security_audit_unavailable"
    assert detail["operation_completed"] is False
    fake_queue.cancel.assert_not_called()


def test_idempotent_repeat_uses_new_correlation_and_flags_metadata() -> None:
    audit = _RecordingAudit()
    task = _stock_analysis_task(status=TaskStatusEnum.CANCELLED)
    fake_queue = _queue_with_task(
        task,
        on_cancel=lambda current, task_id: _apply_cancel(
            current, task_id, status=TaskStatusEnum.CANCELLED
        ),
    )
    with patch(
        "src.api.v1.endpoints.analysis.get_task_queue",
        return_value=fake_queue,
    ):
        first = _call_cancel("task-analysis-1", audit)
        second = _call_cancel("task-analysis-1", audit)

    assert first.status == "cancelled"
    assert second.status == "cancelled"
    assert fake_queue.cancel.call_count == 2
    attempts = _cancel_events(audit, phase="attempt")
    completions = _cancel_events(audit, phase="completion")
    assert len(attempts) == 2
    assert len(completions) == 2
    assert attempts[0]["correlation_id"] != attempts[1]["correlation_id"]
    assert completions[1]["metadata"]["idempotent"] is True
    assert completions[1]["reason_code"] == "cancelled"
    assert all(event["reason_code"] != "cancel_failed" for event in completions)
    assert all(event["outcome"] != "failure" for event in completions)


def test_http_completion_failure_reports_operation_completed_true() -> None:
    audit = _RecordingAudit(fail_completion=True)
    task = _stock_analysis_task()
    fake_queue = _queue_with_task(task)
    app = _cancel_http_app(audit)
    with patch(
        "src.api.v1.endpoints.analysis.get_task_queue",
        return_value=fake_queue,
    ):
        with TestClient(app) as client:
            response = client.post("/api/v1/analysis/tasks/task-analysis-1/cancel")
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["error"] == "security_audit_unavailable"
    assert detail["operation_completed"] is True
    assert detail["task_id"] == "task-analysis-1"
    assert detail["status"] == "cancel_requested"
    fake_queue.cancel.assert_called_once_with("task-analysis-1")
    assert task.status == TaskStatusEnum.CANCEL_REQUESTED
    assert _cancel_events(audit, phase="attempt")
    assert _cancel_events(audit, phase="completion") == []


def test_unknown_and_wrong_kind_keep_404_when_reject_completion_fails() -> None:
    cases = (
        (None, "missing-1"),
        ("candidate_discovery", "other-candidate_discovery"),
        ("detailed", "other-detailed"),
        ("local_model_pull", "other-local_model_pull"),
    )
    for kind, task_id in cases:
        audit = _RecordingAudit(fail_completion=True)
        fake_queue = MagicMock()
        if kind is None:
            fake_queue.get_task.return_value = None
        else:
            fake_queue.get_task.return_value = _stock_analysis_task(
                task_id=task_id,
                kind=kind,
                stock_code=kind,
                report_type=kind,
            )
        with patch(
            "src.api.v1.endpoints.analysis.get_task_queue",
            return_value=fake_queue,
        ):
            with pytest.raises(HTTPException) as caught:
                _call_cancel(task_id, audit)
        assert caught.value.status_code == 404
        fake_queue.cancel.assert_not_called()
        attempts = _cancel_events(audit, phase="attempt")
        assert len(attempts) == 1
        assert _cancel_events(audit, phase="completion") == []


def test_http_wrong_kind_keeps_404_when_completion_store_fails() -> None:
    audit = _RecordingAudit(fail_completion=True)
    fake_queue = MagicMock()
    fake_queue.get_task.return_value = _stock_analysis_task(
        task_id="other-candidate_discovery",
        kind="candidate_discovery",
        stock_code="candidate_discovery",
        report_type="candidate_discovery",
    )
    app = _cancel_http_app(audit)
    with patch(
        "src.api.v1.endpoints.analysis.get_task_queue",
        return_value=fake_queue,
    ):
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/analysis/tasks/other-candidate_discovery/cancel"
            )
    assert response.status_code == 404
    fake_queue.cancel.assert_not_called()


def test_cancel_events_are_queryable_from_durable_store(cancel_database) -> None:
    store = SecurityAuditService(repository=SecurityAuditRepository(cancel_database))
    task = _stock_analysis_task(original_query=CANARY_QUERY)
    fake_queue = _queue_with_task(task)
    with patch(
        "src.api.v1.endpoints.analysis.get_task_queue",
        return_value=fake_queue,
    ):
        payload = _call_cancel("task-analysis-1", store)
    assert payload.status == "cancel_requested"
    page = store.list_events(event_type=ANALYSIS_CANCEL_EVENT_TYPE, page_size=20)
    types = {(item.phase, item.action, item.outcome) for item in page.items}
    assert ("attempt", ANALYSIS_CANCEL_EVENT_TYPE, "pending") in types
    assert ("completion", ANALYSIS_CANCEL_EVENT_TYPE, "success") in types
    assert page.total >= 2
    dumped = json.dumps([item.model_dump(mode="json") for item in page.items])
    assert CANARY not in dumped
    assert "original_query" not in dumped
    assert all(item.event_type != "analysis.submit" for item in page.items)


class _FailCompletionAuditRepository(SecurityAuditRepository):
    def __init__(self, db_manager, *, fail_completion: bool = False) -> None:
        super().__init__(db_manager)
        self.fail_completion = fail_completion

    def append(self, event: SecurityAuditEventCreate) -> SecurityAuditEvent:
        if self.fail_completion and event.phase == "completion":
            raise RuntimeError("completion store unavailable")
        return super().append(event)


def test_idempotent_completion_failure_does_not_write_failure_row(
    cancel_database,
) -> None:
    repository = _FailCompletionAuditRepository(cancel_database)
    store = SecurityAuditService(repository=repository)
    task = _stock_analysis_task(status=TaskStatusEnum.CANCELLED)
    fake_queue = _queue_with_task(
        task,
        on_cancel=lambda current, task_id: _apply_cancel(
            current, task_id, status=TaskStatusEnum.CANCELLED
        ),
    )
    with patch(
        "src.api.v1.endpoints.analysis.get_task_queue",
        return_value=fake_queue,
    ):
        first = _call_cancel("task-analysis-1", store)
        repository.fail_completion = True
        with pytest.raises(HTTPException) as caught:
            _call_cancel("task-analysis-1", store)

    assert first.status == "cancelled"
    assert caught.value.status_code == 503
    assert caught.value.detail["operation_completed"] is True
    assert task.status == TaskStatusEnum.CANCELLED
    page = store.list_events(event_type=ANALYSIS_CANCEL_EVENT_TYPE, page_size=20)
    assert all(item.outcome != "failure" for item in page.items)
    assert all(item.reason_code != "cancel_failed" for item in page.items)
    second_correlation = [
        item for item in page.items if item.phase == "attempt"
    ]
    assert len(second_correlation) == 2
    completions = [item for item in page.items if item.phase == "completion"]
    assert len(completions) == 1
    assert completions[0].outcome == "success"


def test_discovery_and_direct_queue_cancel_do_not_emit_analysis_cancel() -> None:
    audit = _RecordingAudit()
    fake_queue = MagicMock()
    fake_queue.get_task.return_value = SimpleNamespace(
        task_id="disc-1",
        trace_id="disc-1",
        kind="candidate_discovery",
        report_type="candidate_discovery",
        status=TaskStatusEnum.PROCESSING,
        progress=10,
        message="running",
        message_code="task.status",
        message_params={},
        error=None,
        result=None,
        stock_code="candidate_discovery",
    )
    fake_queue.cancel.return_value = SimpleNamespace(
        task_id="disc-1",
        status=TaskStatusEnum.CANCEL_REQUESTED,
        progress=10,
        message="Cancel requested",
        message_code="task.cancel_requested",
        message_params={},
    )
    with patch(
        "src.api.v1.endpoints.candidate_discovery.get_task_queue",
        return_value=fake_queue,
    ), patch(
        "src.services.security_audit_service.get_security_audit_service",
        return_value=audit,
    ):
        discovery_endpoint.cancel_candidate_discovery_task("disc-1")
        fake_queue.cancel("internal-task")

    assert _cancel_events(audit, phase="attempt") == []
    assert _cancel_events(audit, phase="completion") == []
    assert _submit_events(audit) == []


def test_malformed_recorder_is_rejected_before_get_task() -> None:
    fake_queue = MagicMock()
    app = _cancel_http_app(object())
    with patch(
        "src.api.v1.endpoints.analysis.get_task_queue",
        return_value=fake_queue,
    ):
        with TestClient(app) as client:
            response = client.post("/api/v1/analysis/tasks/task-analysis-1/cancel")
    assert response.status_code == 503
    fake_queue.get_task.assert_not_called()
    fake_queue.cancel.assert_not_called()


def test_production_envelope_keeps_operation_completed_in_params() -> None:
    body = normalize_error_body(
        {
            "error": "security_audit_unavailable",
            "message": (
                "Analysis task cancel was requested, but audit completion "
                "could not be persisted"
            ),
            "operation_completed": True,
            "task_id": "task-analysis-1",
            "status": "cancel_requested",
        },
        default_error="http_error",
        default_message="Request failed",
    )
    assert body["error"] == "security_audit_unavailable"
    assert body["params"]["operation_completed"] is True
    assert body["params"]["task_id"] == "task-analysis-1"
    assert body["params"]["status"] == "cancel_requested"
    assert "operation_completed" not in body


def test_service_completion_unavailable_does_not_emit_failure_row() -> None:
    audit = _RecordingAudit(fail_completion=True)
    task = _stock_analysis_task()
    fake_queue = _queue_with_task(task)
    with patch(
        "src.api.v1.endpoints.analysis.get_task_queue",
        return_value=fake_queue,
    ):
        with pytest.raises(HTTPException) as caught:
            _call_cancel("task-analysis-1", audit)
    assert caught.value.status_code == 503
    assert caught.value.detail["operation_completed"] is True
    assert caught.value.detail["status"] == "cancel_requested"
    assert _cancel_events(audit, phase="completion") == []
    assert all(event.get("reason_code") != "cancel_failed" for event in audit.completions)


def _queue_that_evicts_after_cancel(task, *, status=TaskStatusEnum.CANCELLED):
    fake_queue = MagicMock()
    fake_queue.get_task.return_value = task

    def fake_cancel(task_id: str):
        snapshot = _apply_cancel(task, task_id, status=status)
        fake_queue.get_task.return_value = None
        return snapshot

    fake_queue.cancel.side_effect = fake_cancel
    return fake_queue


@pytest.mark.parametrize("status_lookup", ("missing", "db_error"))
def test_post_cancel_status_failure_records_completion_and_reports_operation_completed(
    status_lookup: str,
) -> None:
    audit = _RecordingAudit()
    task = _stock_analysis_task()
    fake_queue = _queue_that_evicts_after_cancel(task)
    empty_db = MagicMock()
    empty_db.get_analysis_history.return_value = []
    db_patch = (
        {"side_effect": RuntimeError("status store unavailable")}
        if status_lookup == "db_error"
        else {"return_value": empty_db}
    )
    with patch(
        "src.api.v1.endpoints.analysis.get_task_queue",
        return_value=fake_queue,
    ), patch(
        "src.storage.DatabaseManager.get_instance",
        **db_patch,
    ):
        with pytest.raises(HTTPException) as caught:
            _call_cancel("task-analysis-1", audit)

    assert caught.value.status_code == 503
    assert caught.value.detail["error"] == "security_audit_unavailable"
    assert caught.value.detail["operation_completed"] is True
    assert caught.value.detail["task_id"] == "task-analysis-1"
    assert caught.value.detail["status"] == "cancelled"
    fake_queue.cancel.assert_called_once_with("task-analysis-1")
    attempts = _cancel_events(audit, phase="attempt")
    completions = _cancel_events(audit, phase="completion")
    assert len(attempts) == 1
    assert len(completions) == 1
    assert completions[0]["outcome"] == "success"
    assert completions[0]["reason_code"] == "cancelled"
    assert completions[0]["metadata"]["status_after"] == "cancelled"
    assert all(event.get("reason_code") != "cancel_failed" for event in audit.completions)


def test_http_post_cancel_status_failure_reports_operation_completed_true() -> None:
    audit = _RecordingAudit()
    task = _stock_analysis_task()
    fake_queue = _queue_that_evicts_after_cancel(task)
    empty_db = MagicMock()
    empty_db.get_analysis_history.return_value = []
    app = _cancel_http_app(audit)
    with patch(
        "src.api.v1.endpoints.analysis.get_task_queue",
        return_value=fake_queue,
    ), patch(
        "src.storage.DatabaseManager.get_instance",
        return_value=empty_db,
    ):
        with TestClient(app) as client:
            response = client.post("/api/v1/analysis/tasks/task-analysis-1/cancel")
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["error"] == "security_audit_unavailable"
    assert detail["operation_completed"] is True
    assert detail["task_id"] == "task-analysis-1"
    assert detail["status"] == "cancelled"
    fake_queue.cancel.assert_called_once_with("task-analysis-1")
    assert _cancel_events(audit, phase="completion")
