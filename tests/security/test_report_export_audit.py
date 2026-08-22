# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Fail-closed history report-export security-audit coverage (#1062 DAG-4)."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.api import deps as api_deps
from src.api.middlewares.auth import EXEMPT_PATHS, _path_exempt
from src.api.v1.endpoints import history as history_endpoint
from src.api.v1.endpoints import report_export as export_endpoint
from src.api.v1.endpoints.report_export import REPORT_EXPORT_EVENT_TYPE
from src.api.v1.errors import normalize_error_body
from src.config import Config
from src.repositories.security_audit_repo import SecurityAuditRepository
from src.schemas.security_audit import SecurityAuditEvent, SecurityAuditEventCreate
from src.services.history_service import MarkdownReportGenerationError
from src.services.report_export_service import ReportExportDependencyError
from src.services.security_audit_service import SecurityAuditService
from src.storage import DatabaseManager
from tests.security.test_security_audit_integrations import _RecordingAudit


CANARY = "report-export-audit-canary-secret"
CANARY_MARKDOWN = f"# Report\n\nplease leak {CANARY} in the body"


class _FakeHistoryService:
    def __init__(self, markdown, detail=None, *, raise_gen: bool = False):
        self.markdown = markdown
        self.detail = detail if detail is not None else {"id": 42, "query_id": "q-42"}
        self.raise_gen = raise_gen
        self.markdown_calls = 0
        self.detail_calls = 0

    def resolve_and_get_detail(self, record_id):
        self.detail_calls += 1
        return self.detail

    def get_markdown_report(self, record_id):
        self.markdown_calls += 1
        if self.raise_gen:
            raise MarkdownReportGenerationError("raw provider detail", record_id=record_id)
        return self.markdown


@pytest.fixture
def export_database(tmp_path):
    DatabaseManager.reset_instance()
    Config.reset_instance()
    manager = DatabaseManager(db_url=f"sqlite:///{tmp_path / 'report-export-audit.sqlite'}")
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


def _export_events(audit: _RecordingAudit, *, phase: str) -> list[dict]:
    source = audit.attempts if phase == "attempt" else audit.completions
    return [
        event
        for event in source
        if event.get("event_type") == REPORT_EXPORT_EVENT_TYPE
    ]


def _patch_history(monkeypatch, service: _FakeHistoryService):
    monkeypatch.setattr(export_endpoint, "HistoryService", lambda _db: service)


def _call_export(record_id: str, audit, *, format: str = "md"):
    return export_endpoint.export_history_report(
        record_id,
        format=format,
        db_manager=object(),
        security_audit=audit,
    )


def _export_http_app(audit):
    app = FastAPI()
    app.include_router(export_endpoint.router, prefix="/api/v1/history")
    app.include_router(history_endpoint.router, prefix="/api/v1/history")
    app.dependency_overrides[api_deps.require_security_audit_service] = lambda: audit
    app.dependency_overrides[api_deps.get_database_manager] = lambda: object()
    return app


def test_happy_md_export_records_attempt_then_success_without_secrets(monkeypatch) -> None:
    service = _FakeHistoryService(
        CANARY_MARKDOWN,
        {"id": 42, "query_id": "q-42", "stock_name": f"leaky-{CANARY}"},
    )
    _patch_history(monkeypatch, service)
    audit = _RecordingAudit()

    with patch("src.api.v1.endpoints.report_export.is_auth_enabled", return_value=False):
        response = _call_export("42", audit)

    assert response.status_code == 200
    assert response.body.decode("utf-8") == CANARY_MARKDOWN
    attempts = _export_events(audit, phase="attempt")
    completions = _export_events(audit, phase="completion")
    assert len(attempts) == 1
    assert len(completions) == 1
    assert attempts[0]["action"] == REPORT_EXPORT_EVENT_TYPE
    assert attempts[0]["target_type"] == "analysis_history"
    assert attempts[0]["target_id"] == "42"
    assert attempts[0]["actor_type"] == "administrator"
    assert attempts[0]["actor_id"] == "local_operator"
    assert attempts[0]["correlation_id"] == completions[0]["correlation_id"]
    assert completions[0]["outcome"] == "success"
    assert completions[0]["reason_code"] == "export_completed"
    assert completions[0]["target_id"] == "42"
    assert completions[0]["metadata"]["format"] == "md"
    assert completions[0]["metadata"]["lookup_key"] == "42"
    assert completions[0]["metadata"]["resolved_record_id"] == "42"
    assert completions[0]["metadata"]["lookup_mode"] == "primary_key"
    assert completions[0]["metadata"]["byte_length"] == len(CANARY_MARKDOWN.encode("utf-8"))
    visible = _visible_audit_payload(audit)
    assert CANARY not in visible
    assert CANARY_MARKDOWN not in visible


def test_resolved_identity_uses_lookup_key_on_attempt_and_pk_on_completion(
    monkeypatch,
) -> None:
    service = _FakeHistoryService("# ok", {"id": 999, "query_id": "123"})
    _patch_history(monkeypatch, service)
    audit = _RecordingAudit()

    response = _call_export("123", audit)

    assert response.status_code == 200
    attempts = _export_events(audit, phase="attempt")
    completions = _export_events(audit, phase="completion")
    assert attempts[0]["target_id"] == "123"
    assert attempts[0]["metadata"]["lookup_key"] == "123"
    assert "resolved_record_id" not in attempts[0]["metadata"]
    assert completions[0]["target_id"] == "999"
    assert completions[0]["metadata"]["lookup_key"] == "123"
    assert completions[0]["metadata"]["resolved_record_id"] == "999"
    assert completions[0]["metadata"]["lookup_mode"] == "query_id"


def test_attempt_failure_does_not_load_markdown_or_export(monkeypatch) -> None:
    service = _FakeHistoryService("# ok")
    _patch_history(monkeypatch, service)
    export_calls: list[object] = []
    monkeypatch.setattr(
        export_endpoint,
        "export_report",
        lambda *args, **kwargs: export_calls.append((args, kwargs)),
    )
    audit = _RecordingAudit(fail_attempt=True)

    with pytest.raises(HTTPException) as caught:
        _call_export("1", audit)

    assert caught.value.status_code == 503
    assert caught.value.detail["error"] == "security_audit_unavailable"
    assert caught.value.detail["operation_completed"] is False
    assert service.markdown_calls == 0
    assert service.detail_calls == 0
    assert export_calls == []
    assert audit.attempts == []
    assert audit.completions == []


def test_http_attempt_failure_reports_operation_completed_false(monkeypatch) -> None:
    service = _FakeHistoryService("# ok")
    _patch_history(monkeypatch, service)
    audit = _RecordingAudit(fail_attempt=True)
    app = _export_http_app(audit)
    with TestClient(app) as client:
        response = client.get("/api/v1/history/1/export?format=md")
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["error"] == "security_audit_unavailable"
    assert detail["operation_completed"] is False
    assert service.markdown_calls == 0
    assert response.content == b"" or b"ok" not in response.content


def test_success_completion_failure_does_not_write_export_failed(monkeypatch) -> None:
    service = _FakeHistoryService("# ok", {"id": 7})
    _patch_history(monkeypatch, service)
    audit = _RecordingAudit(fail_completion=True)

    with pytest.raises(HTTPException) as caught:
        _call_export("7", audit)

    assert caught.value.status_code == 503
    assert caught.value.detail["operation_completed"] is True
    assert caught.value.detail["record_id"] == "7"
    assert caught.value.detail["format"] == "md"
    assert _export_events(audit, phase="attempt")
    assert _export_events(audit, phase="completion") == []
    assert all(event.get("reason_code") != "export_failed" for event in audit.completions)
    assert all(event.get("outcome") != "failure" for event in audit.completions)


def test_http_completion_failure_does_not_return_file_bytes(monkeypatch) -> None:
    markdown = "# exported-body"
    service = _FakeHistoryService(markdown, {"id": 8})
    _patch_history(monkeypatch, service)
    audit = _RecordingAudit(fail_completion=True)
    app = _export_http_app(audit)
    with TestClient(app) as client:
        response = client.get("/api/v1/history/8/export?format=md")
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["operation_completed"] is True
    assert detail["record_id"] == "8"
    assert detail["format"] == "md"
    assert markdown.encode("utf-8") not in response.content
    assert "exported-body" not in response.text


def test_invalid_format_does_not_record_attempt(monkeypatch) -> None:
    service = _FakeHistoryService("# ok")
    _patch_history(monkeypatch, service)
    audit = _RecordingAudit()
    with pytest.raises(HTTPException) as caught:
        _call_export("1", audit, format="xlsx")
    assert caught.value.status_code == 400
    assert caught.value.detail["error"] == "export_format_invalid"
    assert audit.attempts == []
    assert audit.completions == []
    assert service.markdown_calls == 0


def test_domain_export_503_is_preserved_when_reject_completion_fails(
    monkeypatch,
) -> None:
    service = _FakeHistoryService("# ok", {"id": 1})
    _patch_history(monkeypatch, service)
    monkeypatch.setattr(
        export_endpoint,
        "export_report",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ReportExportDependencyError("/secret/backend parser")
        ),
    )
    audit = _RecordingAudit(fail_completion=True)

    with pytest.raises(HTTPException) as caught:
        _call_export("1", audit, format="pdf")

    assert caught.value.status_code == 503
    assert caught.value.detail["error"] == "export_dependency_missing"
    assert caught.value.detail.get("error") != "security_audit_unavailable"
    assert "operation_completed" not in caught.value.detail
    payload = json.dumps(caught.value.detail)
    assert "/secret/" not in payload
    assert service.markdown_calls == 1
    assert _export_events(audit, phase="attempt")
    assert _export_events(audit, phase="completion") == []


def test_not_found_stays_404_when_reject_completion_fails(monkeypatch) -> None:
    service = _FakeHistoryService(None, detail=None)
    _patch_history(monkeypatch, service)
    audit = _RecordingAudit(fail_completion=True)
    with pytest.raises(HTTPException) as caught:
        _call_export("missing", audit)
    assert caught.value.status_code == 404
    assert caught.value.detail["error"] == "not_found"
    assert _export_events(audit, phase="attempt")
    assert _export_events(audit, phase="completion") == []


def test_capabilities_does_not_emit_report_export(monkeypatch) -> None:
    audit = _RecordingAudit()
    app = _export_http_app(audit)
    monkeypatch.setattr(
        export_endpoint,
        "get_export_capabilities",
        lambda language: {
            "formats": {
                "md": {
                    "available": True,
                    "status": "ready",
                    "media_type": "text/markdown; charset=utf-8",
                    "dependency": None,
                    "dependency_installed": True,
                    "font_validated": None,
                    "missing_glyph_count": 0,
                },
                "html": {
                    "available": False,
                    "status": "dependency_missing",
                    "media_type": "text/html; charset=utf-8",
                    "dependency": "markdown-it-py",
                    "dependency_installed": False,
                    "font_validated": None,
                    "missing_glyph_count": 0,
                },
                "pdf": {
                    "available": False,
                    "status": "dependency_missing",
                    "media_type": "application/pdf",
                    "dependency": "fpdf2",
                    "dependency_installed": False,
                    "font_validated": None,
                    "missing_glyph_count": 0,
                },
            },
            "requested_language": language,
            "supported_query_formats": ["md", "html", "pdf"],
            "office_formats_status": "html_only",
            "chart_handling": "markdown_images_omitted_without_destinations",
            "pdf_limits": {
                "max_input_bytes": 1_000_000,
                "max_pages": 100,
                "max_table_rows": 500,
                "max_table_columns": 12,
                "max_output_bytes": 25_165_824,
                "max_render_seconds": 20.0,
                "max_concurrency": 2,
            },
        },
    )
    with TestClient(app) as client:
        response = client.get("/api/v1/history/export/capabilities")
    assert response.status_code == 200
    assert _export_events(audit, phase="attempt") == []
    assert _export_events(audit, phase="completion") == []


def test_markdown_get_does_not_emit_report_export(monkeypatch) -> None:
    audit = _RecordingAudit()
    app = _export_http_app(audit)

    class _MarkdownService:
        def get_markdown_report(self, record_id):
            return "# markdown-only"

    monkeypatch.setattr(history_endpoint, "HistoryService", lambda _db: _MarkdownService())
    with TestClient(app) as client:
        response = client.get("/api/v1/history/42/markdown")
    assert response.status_code == 200
    assert response.json()["content"] == "# markdown-only"
    assert _export_events(audit, phase="attempt") == []
    assert _export_events(audit, phase="completion") == []


class _FailCompletionAuditRepository(SecurityAuditRepository):
    def __init__(self, db_manager, *, fail_completion: bool = False) -> None:
        super().__init__(db_manager)
        self.fail_completion = fail_completion

    def append(self, event: SecurityAuditEventCreate) -> SecurityAuditEvent:
        if self.fail_completion and event.phase == "completion":
            raise RuntimeError("completion store unavailable")
        return super().append(event)


def test_export_events_are_queryable_from_durable_store(monkeypatch, export_database) -> None:
    service = _FakeHistoryService(CANARY_MARKDOWN, {"id": 42, "query_id": "q-42"})
    _patch_history(monkeypatch, service)
    store = SecurityAuditService(repository=SecurityAuditRepository(export_database))
    response = _call_export("42", store)
    assert response.status_code == 200
    page = store.list_events(event_type=REPORT_EXPORT_EVENT_TYPE, page_size=20)
    types = {(item.phase, item.action, item.outcome) for item in page.items}
    assert ("attempt", REPORT_EXPORT_EVENT_TYPE, "pending") in types
    assert ("completion", REPORT_EXPORT_EVENT_TYPE, "success") in types
    assert page.total >= 2
    dumped = json.dumps([item.model_dump(mode="json") for item in page.items])
    assert CANARY not in dumped
    assert "please leak" not in dumped
    assert all(item.event_type != "analysis.submit" for item in page.items)


def test_durable_completion_failure_does_not_write_failure_row(
    monkeypatch,
    export_database,
) -> None:
    repository = _FailCompletionAuditRepository(export_database, fail_completion=True)
    store = SecurityAuditService(repository=repository)
    service = _FakeHistoryService("# ok", {"id": 5})
    _patch_history(monkeypatch, service)
    with pytest.raises(HTTPException) as caught:
        _call_export("5", store)
    assert caught.value.status_code == 503
    assert caught.value.detail["operation_completed"] is True
    page = store.list_events(event_type=REPORT_EXPORT_EVENT_TYPE, page_size=20)
    assert all(item.outcome != "failure" for item in page.items)
    assert all(item.reason_code != "export_failed" for item in page.items)
    assert [item.phase for item in page.items] == ["attempt"]


def test_route_is_not_auth_exempt_and_still_exports_when_auth_disabled(
    monkeypatch,
) -> None:
    assert not _path_exempt("/api/v1/history/42/export")
    assert "/api/v1/history/{record_id}/export" not in EXEMPT_PATHS
    service = _FakeHistoryService("# ok", {"id": 42})
    _patch_history(monkeypatch, service)
    audit = _RecordingAudit()
    with patch("src.api.v1.endpoints.report_export.is_auth_enabled", return_value=False):
        response = _call_export("42", audit)
    assert response.status_code == 200
    assert _export_events(audit, phase="completion")[0]["actor_id"] == "local_operator"


def test_malformed_recorder_is_rejected_before_markdown_load(monkeypatch) -> None:
    service = _FakeHistoryService("# ok")
    _patch_history(monkeypatch, service)
    app = _export_http_app(object())
    with TestClient(app) as client:
        response = client.get("/api/v1/history/1/export?format=md")
    assert response.status_code == 503
    assert service.markdown_calls == 0


def test_production_envelope_keeps_operation_completed_in_params() -> None:
    body = normalize_error_body(
        {
            "error": "security_audit_unavailable",
            "message": (
                "Report export was generated, but audit completion could not be persisted"
            ),
            "operation_completed": True,
            "record_id": "42",
            "format": "md",
        },
        default_error="http_error",
        default_message="Request failed",
    )
    assert body["error"] == "security_audit_unavailable"
    assert body["params"]["operation_completed"] is True
    assert body["params"]["record_id"] == "42"
    assert body["params"]["format"] == "md"
    assert "operation_completed" not in body
