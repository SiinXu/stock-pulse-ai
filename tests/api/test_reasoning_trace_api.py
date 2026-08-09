# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""HTTP contract tests for reasoning-trace export endpoint."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.middlewares.error_handler import add_error_handlers
from api.v1.endpoints import reasoning_trace as endpoint
from src.services.reasoning_trace_export_service import (
    ReasoningTraceNotFound,
    build_reasoning_trace_package,
)
from tests.security_audit_test_utils import SecurityAuditRecorderStub


def _client(audit: SecurityAuditRecorderStub | None = None) -> TestClient:
    app = FastAPI()
    app.include_router(endpoint.router, prefix="/api/v1/reasoning-trace")
    add_error_handlers(app)
    from api import deps as api_deps

    app.dependency_overrides[api_deps.get_database_manager] = lambda: MagicMock()
    app.dependency_overrides[api_deps.require_security_audit_service] = (
        lambda: audit or SecurityAuditRecorderStub()
    )
    return TestClient(app)


def _enabled_config(*, enabled: bool = True) -> SimpleNamespace:
    return SimpleNamespace(reasoning_trace_export_enabled=enabled)


def _patch_services_config(enabled: bool = True):
    services = SimpleNamespace(config=_enabled_config(enabled=enabled))
    return patch.object(endpoint, "get_application_services", return_value=services)


def _valid_result(*, include_markdown: bool = False, output_format: str = "json"):
    return build_reasoning_trace_package(
        run_id="trace-1",
        record_id="42",
        query_id="q-1",
        lookup_key="42",
        lookup_mode="primary_key",
        stock_code="600519",
        diagnostics={"trace_id": "trace-1"},
        raw_result={"decision_type": "buy"},
        include_markdown=include_markdown,
        output_format=output_format,
    )


def test_export_disabled_returns_404_without_side_effects() -> None:
    with _patch_services_config(enabled=False):
        response = _client().get("/api/v1/reasoning-trace/1")
    assert response.status_code == 404
    body = response.json()
    assert body["error"] == "reasoning_trace_export_disabled"


def test_export_requires_auth_enabled() -> None:
    with _patch_services_config(enabled=True), patch.object(
        endpoint, "is_auth_enabled", return_value=False
    ):
        response = _client().get("/api/v1/reasoning-trace/1")
    assert response.status_code == 403
    assert response.json()["error"] == "reasoning_trace_auth_required"


def test_export_requires_admin_session_when_auth_enabled() -> None:
    with _patch_services_config(enabled=True), patch.object(
        endpoint, "is_auth_enabled", return_value=True
    ), patch.object(endpoint, "verify_session", return_value=False):
        response = _client().get(
            "/api/v1/reasoning-trace/1",
            cookies={"dsa_session": "invalid"},
        )
    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"


def test_export_json_success() -> None:
    audit = SecurityAuditRecorderStub()
    service = MagicMock()
    service.export_for_record.return_value = _valid_result()
    with _patch_services_config(enabled=True), patch.object(
        endpoint, "is_auth_enabled", return_value=True
    ), patch.object(endpoint, "verify_session", return_value=True), patch.object(
        endpoint, "HistoryService", return_value=MagicMock()
    ), patch.object(endpoint, "ReasoningTraceExportService", return_value=service):
        client = _client(audit)
        response = client.get(
            "/api/v1/reasoning-trace/42",
            cookies={"dsa_session": "valid"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "reasoning-trace-v1"
    assert body["run"]["stock_code"] == "600519"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["content-disposition"].endswith('reasoning-trace-42.json"')
    assert len(audit.attempts) == 1
    assert len(audit.completions) == 1
    assert audit.completions[0]["outcome"] == "success"
    service.export_for_record.assert_called_once()


def test_export_not_found() -> None:
    audit = SecurityAuditRecorderStub()
    service = MagicMock()
    service.export_for_record.side_effect = ReasoningTraceNotFound()
    with _patch_services_config(enabled=True), patch.object(
        endpoint, "is_auth_enabled", return_value=True
    ), patch.object(endpoint, "verify_session", return_value=True), patch.object(
        endpoint, "HistoryService", return_value=MagicMock()
    ), patch.object(endpoint, "ReasoningTraceExportService", return_value=service):
        response = _client(audit).get(
            "/api/v1/reasoning-trace/999",
            cookies={"dsa_session": "valid"},
        )
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"
    assert audit.completions[0]["outcome"] == "denied"


def test_export_markdown_format() -> None:
    audit = SecurityAuditRecorderStub()
    service = MagicMock()
    service.export_for_record.return_value = _valid_result(
        include_markdown=True,
        output_format="markdown",
    )
    with _patch_services_config(enabled=True), patch.object(
        endpoint, "is_auth_enabled", return_value=True
    ), patch.object(endpoint, "verify_session", return_value=True), patch.object(
        endpoint, "HistoryService", return_value=MagicMock()
    ), patch.object(endpoint, "ReasoningTraceExportService", return_value=service):
        response = _client(audit).get(
            "/api/v1/reasoning-trace/1",
            params={"format": "markdown"},
            cookies={"dsa_session": "valid"},
        )
    assert response.status_code == 200
    assert "text/markdown" in response.headers.get("content-type", "")
    assert response.text.startswith("# Reasoning Trace")
    assert response.headers["cache-control"] == "private, no-store"


def test_openapi_declares_negotiated_content_and_errors() -> None:
    schema = _client().app.openapi()
    operation = schema["paths"]["/api/v1/reasoning-trace/{record_id}"]["get"]
    success_content = operation["responses"]["200"]["content"]
    assert "application/json" in success_content
    assert "text/markdown" in success_content
    for status in ("400", "401", "403", "404", "422", "500", "503"):
        assert status in operation["responses"]


def test_real_service_path_accepts_signed_admin_session() -> None:
    from src import auth

    audit = SecurityAuditRecorderStub()
    record = SimpleNamespace(
        id=7,
        query_id="duplicate-query",
        code="AAPL",
        name="Apple",
        model_used="gpt-test",
        created_at=None,
        context_snapshot=json.dumps(
            {"diagnostics": {"trace_id": "trace-real", "agent_events": []}}
        ),
        raw_result=json.dumps({"decision_type": "hold"}),
    )
    history = SimpleNamespace(
        _resolve_record=lambda value: record,
        _parse_diagnostic_json_field=lambda value, field: json.loads(value),
    )
    with _patch_services_config(enabled=True), patch.object(
        endpoint, "is_auth_enabled", return_value=True
    ), patch.object(endpoint, "HistoryService", return_value=history), patch.object(
        auth, "_session_secret", b"reasoning-trace-test-secret"
    ), patch.object(
        auth, "is_auth_enabled", return_value=True
    ):
        session = auth.create_session()
        response = _client(audit).get(
            "/api/v1/reasoning-trace/7",
            cookies={"dsa_session": session},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["run"]["record_id"] == "7"
    assert body["run"]["query_id"] == "duplicate-query"
    assert body["run"]["trace_id"] == "trace-real"
    assert body["run"]["lookup_mode"] == "primary_key"
    assert audit.completions[0]["reason_code"] == "export_completed"
