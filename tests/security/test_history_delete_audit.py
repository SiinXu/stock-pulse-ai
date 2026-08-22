# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Fail-closed history-delete security-audit coverage (#1062 DAG-4)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.analyzer import AnalysisResult
from src.api import deps as api_deps
from src.api.middlewares.auth import EXEMPT_PATHS, _path_exempt
from src.api.v1.endpoints import history as history_endpoint
from src.api.v1.endpoints.history import HISTORY_DELETE_EVENT_TYPE
from src.api.v1.errors import normalize_error_body
from src.api.v1.schemas.history import DeleteHistoryRequest
from src.config import Config
from src.repositories.base import RepositoryError
from src.repositories.security_audit_repo import SecurityAuditRepository
from src.schemas.security_audit import SecurityAuditEvent, SecurityAuditEventCreate
from src.services.history_service import HistoryService
from src.services.security_audit_service import SecurityAuditService
from src.storage import AnalysisHistory, DatabaseManager
from tests.security.test_security_audit_integrations import _RecordingAudit


CANARY = "history-delete-audit-canary-secret"


@pytest.fixture
def history_database(tmp_path):
    DatabaseManager.reset_instance()
    Config.reset_instance()
    manager = DatabaseManager(db_url=f"sqlite:///{tmp_path / 'history-delete-audit.sqlite'}")
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


def _delete_events(audit: _RecordingAudit, *, phase: str) -> list[dict]:
    source = audit.attempts if phase == "attempt" else audit.completions
    return [
        event
        for event in source
        if event.get("event_type") == HISTORY_DELETE_EVENT_TYPE
    ]


def _save_history(db: DatabaseManager, query_id: str, *, code: str = "600519", name: str = "贵州茅台") -> int:
    saved = db.save_analysis_history(
        result=AnalysisResult(
            code=code,
            name=name,
            sentiment_score=78,
            trend_prediction="看多",
            operation_advice="持有",
            analysis_summary="基本面稳健，短期震荡",
        ),
        query_id=query_id,
        report_type="simple",
        news_content="新闻摘要",
        context_snapshot=None,
        save_snapshot=False,
    )
    assert saved > 0
    return int(saved)


def _history_row_exists(db: DatabaseManager, record_id: int) -> bool:
    with db.get_session() as session:
        return session.query(AnalysisHistory).filter(AnalysisHistory.id == record_id).first() is not None


def _delete_http_app(audit, db_manager: DatabaseManager):
    app = FastAPI()
    app.include_router(history_endpoint.router, prefix="/api/v1/history")
    app.dependency_overrides[api_deps.require_security_audit_service] = lambda: audit
    app.dependency_overrides[api_deps.get_database_manager] = lambda: db_manager
    return app


def test_happy_by_ids_deletes_selected_rows_and_bounds_id_list(history_database) -> None:
    record_id_1 = _save_history(history_database, "query_delete_api_001", name=f"leaky-{CANARY}")
    record_id_2 = _save_history(history_database, "query_delete_api_002")
    audit = _RecordingAudit()

    with patch("src.api.v1.endpoints.history.is_auth_enabled", return_value=False):
        response = history_endpoint.delete_history_records(
            DeleteHistoryRequest(record_ids=[record_id_1]),
            db_manager=history_database,
            security_audit=audit,
        )

    assert response.deleted == 1
    assert _history_row_exists(history_database, record_id_1) is False
    assert _history_row_exists(history_database, record_id_2) is True
    attempts = _delete_events(audit, phase="attempt")
    completions = _delete_events(audit, phase="completion")
    assert len(attempts) == 1
    assert len(completions) == 1
    assert attempts[0]["action"] == HISTORY_DELETE_EVENT_TYPE
    assert attempts[0]["target_type"] == "analysis_history"
    assert attempts[0]["target_id"] == str(record_id_1)
    assert attempts[0]["actor_type"] == "administrator"
    assert attempts[0]["actor_id"] == "local_operator"
    assert attempts[0]["correlation_id"] == completions[0]["correlation_id"]
    assert completions[0]["outcome"] == "success"
    assert completions[0]["reason_code"] == "delete_completed"
    assert completions[0]["metadata"]["scope"] == "by_ids"
    assert completions[0]["metadata"]["deleted_count"] == 1
    assert completions[0]["metadata"]["id_count"] == 1
    assert completions[0]["metadata"]["id_sample"] == [str(record_id_1)]
    visible = _visible_audit_payload(audit)
    assert CANARY not in visible
    assert "贵州茅台" not in visible
    assert all(event.get("event_type") != "report.export" for event in (*audit.attempts, *audit.completions))
    assert all(event.get("event_type") != "analysis.submit" for event in (*audit.attempts, *audit.completions))


def test_happy_by_code_deletes_variants_with_identifier_only(history_database) -> None:
    first = _save_history(history_database, "query_code_001", code="600519")
    second = _save_history(history_database, "query_code_002", code="600519")
    other = _save_history(history_database, "query_code_other", code="000001", name="平安银行")
    audit = _RecordingAudit()

    response = history_endpoint.delete_history_by_code(
        "600519",
        db_manager=history_database,
        security_audit=audit,
    )

    assert response.deleted >= 2
    assert _history_row_exists(history_database, first) is False
    assert _history_row_exists(history_database, second) is False
    assert _history_row_exists(history_database, other) is True
    completions = _delete_events(audit, phase="completion")
    assert completions[0]["metadata"]["scope"] == "by_code"
    assert completions[0]["metadata"]["stock_code"] == "600519"
    assert completions[0]["metadata"]["deleted_count"] == response.deleted
    assert completions[0]["target_id"] == "600519"
    assert "stock_name" not in completions[0]["metadata"]
    assert "贵州茅台" not in _visible_audit_payload(audit)


def test_zero_delete_is_success_not_404(history_database) -> None:
    audit = _RecordingAudit()
    by_code = history_endpoint.delete_history_by_code(
        "999999",
        db_manager=history_database,
        security_audit=audit,
    )
    by_ids = history_endpoint.delete_history_records(
        DeleteHistoryRequest(record_ids=[987654]),
        db_manager=history_database,
        security_audit=audit,
    )
    assert by_code.deleted == 0
    assert by_ids.deleted == 0
    completions = _delete_events(audit, phase="completion")
    assert len(completions) == 2
    assert all(item["outcome"] == "success" for item in completions)
    assert all(item["reason_code"] == "delete_completed" for item in completions)
    assert all(item["metadata"]["deleted_count"] == 0 for item in completions)


def test_attempt_failure_does_not_delete_rows(history_database) -> None:
    record_id = _save_history(history_database, "query_fail_closed")
    audit = _RecordingAudit(fail_attempt=True)
    with patch("src.api.v1.endpoints.history.HistoryService") as service_class:
        with pytest.raises(HTTPException) as caught:
            history_endpoint.delete_history_records(
                DeleteHistoryRequest(record_ids=[record_id]),
                db_manager=history_database,
                security_audit=audit,
            )
    assert caught.value.status_code == 503
    assert caught.value.detail["operation_completed"] is False
    service_class.assert_not_called()
    assert _history_row_exists(history_database, record_id) is True
    assert audit.attempts == []
    assert audit.completions == []


def test_http_attempt_failure_reports_operation_completed_false(history_database) -> None:
    record_id = _save_history(history_database, "query_http_fail_closed")
    audit = _RecordingAudit(fail_attempt=True)
    app = _delete_http_app(audit, history_database)
    with TestClient(app) as client:
        response = client.request(
            "DELETE",
            "/api/v1/history",
            json={"record_ids": [record_id]},
        )
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["error"] == "security_audit_unavailable"
    assert detail["operation_completed"] is False
    assert _history_row_exists(history_database, record_id) is True


def test_success_completion_failure_does_not_write_delete_failed(history_database) -> None:
    record_id = _save_history(history_database, "query_completion_fail")
    audit = _RecordingAudit(fail_completion=True)
    with pytest.raises(HTTPException) as caught:
        history_endpoint.delete_history_records(
            DeleteHistoryRequest(record_ids=[record_id]),
            db_manager=history_database,
            security_audit=audit,
        )
    assert caught.value.status_code == 503
    assert caught.value.detail["operation_completed"] is True
    assert caught.value.detail["scope"] == "by_ids"
    assert caught.value.detail["deleted"] == 1
    assert _history_row_exists(history_database, record_id) is False
    assert _delete_events(audit, phase="attempt")
    assert _delete_events(audit, phase="completion") == []
    assert all(event.get("reason_code") != "delete_failed" for event in audit.completions)
    assert all(event.get("outcome") != "failure" for event in audit.completions)


def test_http_completion_failure_keeps_rows_deleted(history_database) -> None:
    record_id = _save_history(history_database, "query_http_completion_fail")
    audit = _RecordingAudit(fail_completion=True)
    app = _delete_http_app(audit, history_database)
    with TestClient(app) as client:
        response = client.request(
            "DELETE",
            "/api/v1/history",
            json={"record_ids": [record_id]},
        )
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["operation_completed"] is True
    assert detail["scope"] == "by_ids"
    assert detail["deleted"] == 1
    assert _history_row_exists(history_database, record_id) is False


def test_blank_code_and_empty_ids_are_400_without_attempt(history_database) -> None:
    record_id = _save_history(history_database, "query_validation")
    audit = _RecordingAudit()
    with pytest.raises(HTTPException) as blank:
        history_endpoint.delete_history_by_code(
            " ",
            db_manager=history_database,
            security_audit=audit,
        )
    with pytest.raises(HTTPException) as empty:
        history_endpoint.delete_history_records(
            DeleteHistoryRequest(record_ids=[]),
            db_manager=history_database,
            security_audit=audit,
        )
    assert blank.value.status_code == 400
    assert blank.value.detail["error"] == "invalid_request"
    assert empty.value.status_code == 400
    assert empty.value.detail["error"] == "invalid_request"
    assert audit.attempts == []
    assert audit.completions == []
    assert _history_row_exists(history_database, record_id) is True


def test_repository_500_is_preserved_when_failure_completion_fails() -> None:
    audit = _RecordingAudit(fail_completion=True)
    db = MagicMock()
    with patch("src.api.v1.endpoints.history.HistoryService") as service_class:
        service_class.return_value.delete_history_by_code.side_effect = RepositoryError(
            "history deletion made no progress",
            error_code="analysis_history_delete_no_progress",
        )
        with pytest.raises(HTTPException) as raised:
            history_endpoint.delete_history_by_code(
                "600519",
                db_manager=db,
                security_audit=audit,
            )
    assert raised.value.status_code == 500
    assert raised.value.detail.get("error") == "internal_error"
    assert _delete_events(audit, phase="attempt")
    assert _delete_events(audit, phase="completion") == []


def test_metadata_truncates_id_sample_after_64_ids(history_database) -> None:
    ids = list(range(1, 70))
    audit = _RecordingAudit()
    response = history_endpoint.delete_history_records(
        DeleteHistoryRequest(record_ids=ids),
        db_manager=history_database,
        security_audit=audit,
    )
    assert response.deleted == 0
    completions = _delete_events(audit, phase="completion")
    sample = completions[0]["metadata"]["id_sample"]
    assert completions[0]["target_id"] == "batch"
    assert completions[0]["metadata"]["id_count"] == 69
    assert len(sample) == 64
    assert completions[0]["metadata"]["ids_truncated"] is True
    assert "65" not in sample
    assert "69" not in sample


def test_internal_history_service_delete_does_not_emit_history_delete(
    history_database,
) -> None:
    record_id = _save_history(history_database, "query_internal_delete")
    audit = _RecordingAudit()
    with patch(
        "src.services.security_audit_service.get_security_audit_service",
        return_value=audit,
    ):
        deleted = HistoryService(history_database).delete_history_records([record_id])
    assert deleted == 1
    assert _delete_events(audit, phase="attempt") == []
    assert _delete_events(audit, phase="completion") == []


def test_route_is_not_auth_exempt_and_still_deletes_when_auth_disabled(
    history_database,
) -> None:
    assert not _path_exempt("/api/v1/history")
    assert not _path_exempt("/api/v1/history/by-code/600519")
    assert "/api/v1/history" not in EXEMPT_PATHS
    assert "/api/v1/history/by-code/{stock_code}" not in EXEMPT_PATHS
    record_id = _save_history(history_database, "query_auth_overlay")
    audit = _RecordingAudit()
    with patch("src.api.v1.endpoints.history.is_auth_enabled", return_value=False):
        response = history_endpoint.delete_history_records(
            DeleteHistoryRequest(record_ids=[record_id]),
            db_manager=history_database,
            security_audit=audit,
        )
    assert response.deleted == 1
    assert _delete_events(audit, phase="completion")[0]["actor_id"] == "local_operator"


class _FailCompletionAuditRepository(SecurityAuditRepository):
    def __init__(self, db_manager, *, fail_completion: bool = False) -> None:
        super().__init__(db_manager)
        self.fail_completion = fail_completion

    def append(self, event: SecurityAuditEventCreate) -> SecurityAuditEvent:
        if self.fail_completion and event.phase == "completion":
            raise RuntimeError("completion store unavailable")
        return super().append(event)


def test_delete_events_are_queryable_from_durable_store(history_database) -> None:
    record_id = _save_history(history_database, "query_durable", name=f"leaky-{CANARY}")
    store = SecurityAuditService(repository=SecurityAuditRepository(history_database))
    response = history_endpoint.delete_history_records(
        DeleteHistoryRequest(record_ids=[record_id]),
        db_manager=history_database,
        security_audit=store,
    )
    assert response.deleted == 1
    page = store.list_events(event_type=HISTORY_DELETE_EVENT_TYPE, page_size=20)
    types = {(item.phase, item.action, item.outcome) for item in page.items}
    assert ("attempt", HISTORY_DELETE_EVENT_TYPE, "pending") in types
    assert ("completion", HISTORY_DELETE_EVENT_TYPE, "success") in types
    dumped = json.dumps([item.model_dump(mode="json") for item in page.items])
    assert CANARY not in dumped
    assert all(item.event_type != "report.export" for item in page.items)
    assert all(item.event_type != "analysis.submit" for item in page.items)


def test_durable_completion_failure_does_not_write_failure_row(history_database) -> None:
    record_id = _save_history(history_database, "query_durable_completion_fail")
    repository = _FailCompletionAuditRepository(history_database, fail_completion=True)
    store = SecurityAuditService(repository=repository)
    with pytest.raises(HTTPException) as caught:
        history_endpoint.delete_history_records(
            DeleteHistoryRequest(record_ids=[record_id]),
            db_manager=history_database,
            security_audit=store,
        )
    assert caught.value.status_code == 503
    assert caught.value.detail["operation_completed"] is True
    assert _history_row_exists(history_database, record_id) is False
    page = store.list_events(event_type=HISTORY_DELETE_EVENT_TYPE, page_size=20)
    assert all(item.outcome != "failure" for item in page.items)
    assert all(item.reason_code != "delete_failed" for item in page.items)
    assert [item.phase for item in page.items] == ["attempt"]


def test_malformed_recorder_is_rejected_before_delete(history_database) -> None:
    record_id = _save_history(history_database, "query_malformed")
    app = _delete_http_app(object(), history_database)
    with TestClient(app) as client:
        response = client.request(
            "DELETE",
            "/api/v1/history",
            json={"record_ids": [record_id]},
        )
    assert response.status_code == 503
    assert _history_row_exists(history_database, record_id) is True


def test_production_envelope_keeps_operation_completed_in_params() -> None:
    body = normalize_error_body(
        {
            "error": "security_audit_unavailable",
            "message": (
                "History records were deleted, but audit completion could not be persisted"
            ),
            "operation_completed": True,
            "scope": "by_ids",
            "deleted": 1,
        },
        default_error="http_error",
        default_message="Request failed",
    )
    assert body["error"] == "security_audit_unavailable"
    assert body["params"]["operation_completed"] is True
    assert body["params"]["scope"] == "by_ids"
    assert body["params"]["deleted"] == 1
    assert "operation_completed" not in body
