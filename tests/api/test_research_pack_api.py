# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""HTTP contract tests for research-pack export endpoint."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.middlewares.error_handler import add_error_handlers
from src.api.v1.endpoints import research_pack as endpoint
from src.services.research_pack_export_service import (
    ResearchPackExportResult,
    ResearchPackLimitError,
    ResearchPackNotFound,
)
from tests.security_audit_test_utils import SecurityAuditRecorderStub


def _client(audit: SecurityAuditRecorderStub | None = None) -> TestClient:
    app = FastAPI()
    app.include_router(endpoint.router, prefix="/api/v1/history")
    add_error_handlers(app)
    from src.api import deps as api_deps

    app.dependency_overrides[api_deps.get_database_manager] = lambda: MagicMock()
    app.dependency_overrides[api_deps.require_security_audit_service] = (
        lambda: audit or SecurityAuditRecorderStub()
    )
    return TestClient(app)


def _enabled_config(*, enabled: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        research_pack_export_enabled=enabled,
        research_pack_max_zip_bytes=24 * 1024 * 1024,
        report_language="en",
    )


def _patch_services_config(enabled: bool = True):
    services = SimpleNamespace(config=_enabled_config(enabled=enabled))
    return patch.object(endpoint, "get_application_services", return_value=services)


def _result(*, include_zip: bool = True) -> ResearchPackExportResult:
    zip_bytes = b"PK\x03\x04fake-zip" if include_zip else b""
    meta = {
        "schema_version": "research-pack-v1",
        "record_id": "42",
        "share_mode": True,
        "progress": [{"name": "assemble_zip", "status": "completed", "detail": "ok"}],
        "zip_included": include_zip,
        "content_byte_length": 128,
    }
    if include_zip:
        meta["zip_byte_length"] = len(zip_bytes)
    return ResearchPackExportResult(
        zip_bytes=zip_bytes,
        meta=meta,
        truncated=False,
        resolved_record_id="42",
        lookup_mode="by_record_id",
        progress=meta["progress"],
        root_dirname="research-pack-600519-20260812",
        content_byte_length=128,
        zip_included=include_zip,
    )


def test_export_disabled_returns_404_without_auth_side_effects() -> None:
    with _patch_services_config(enabled=False):
        response = _client().get("/api/v1/history/1/research-pack")
    assert response.status_code == 404
    assert response.json()["error"] == "research_pack_export_disabled"


def test_export_requires_auth_enabled() -> None:
    with _patch_services_config(enabled=True), patch.object(
        endpoint, "is_auth_enabled", return_value=False
    ):
        response = _client().get("/api/v1/history/1/research-pack")
    assert response.status_code == 403
    assert response.json()["error"] == "research_pack_auth_required"


def test_export_requires_admin_session_when_auth_enabled() -> None:
    with _patch_services_config(enabled=True), patch.object(
        endpoint, "is_auth_enabled", return_value=True
    ), patch.object(endpoint, "verify_session", return_value=False):
        response = _client().get(
            "/api/v1/history/1/research-pack",
            cookies={"dsa_session": "invalid"},
        )
    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"


def test_export_zip_success_audits_and_headers() -> None:
    audit = SecurityAuditRecorderStub()
    service = MagicMock()
    service.export_for_record.return_value = _result(include_zip=True)
    with _patch_services_config(enabled=True), patch.object(
        endpoint, "is_auth_enabled", return_value=True
    ), patch.object(endpoint, "verify_session", return_value=True), patch.object(
        endpoint, "HistoryService", return_value=MagicMock()
    ), patch.object(endpoint, "ResearchPackExportService", return_value=service):
        response = _client(audit).get(
            "/api/v1/history/42/research-pack",
            cookies={"dsa_session": "valid"},
        )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-research-pack-schema"] == "research-pack-v1"
    assert response.headers["x-research-pack-zip-included"] == "1"
    assert 'research-pack-42.zip"' in response.headers["content-disposition"]
    assert len(audit.attempts) == 1
    assert len(audit.completions) == 1
    assert audit.completions[0]["outcome"] == "success"
    service.export_for_record.assert_called_once()
    kwargs = service.export_for_record.call_args.kwargs
    assert kwargs.get("include_zip") is True


def test_export_json_skips_zip_and_validates_before_success_audit() -> None:
    audit = SecurityAuditRecorderStub()
    service = MagicMock()
    service.export_for_record.return_value = _result(include_zip=False)
    with _patch_services_config(enabled=True), patch.object(
        endpoint, "is_auth_enabled", return_value=True
    ), patch.object(endpoint, "verify_session", return_value=True), patch.object(
        endpoint, "HistoryService", return_value=MagicMock()
    ), patch.object(endpoint, "ResearchPackExportService", return_value=service):
        response = _client(audit).get(
            "/api/v1/history/42/research-pack",
            params={"format": "json"},
            cookies={"dsa_session": "valid"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "research-pack-v1"
    assert body["zip_included"] is False
    assert body["byte_length"] == 128
    assert response.headers["x-research-pack-zip-included"] == "0"
    assert audit.completions[0]["outcome"] == "success"
    kwargs = service.export_for_record.call_args.kwargs
    assert kwargs.get("include_zip") is False


def test_export_json_rejects_non_finite_meta_before_success_audit() -> None:
    audit = SecurityAuditRecorderStub()
    service = MagicMock()
    result = _result(include_zip=False)
    result.meta["metric"] = float("nan")
    service.export_for_record.return_value = result
    with _patch_services_config(enabled=True), patch.object(
        endpoint, "is_auth_enabled", return_value=True
    ), patch.object(endpoint, "verify_session", return_value=True), patch.object(
        endpoint, "HistoryService", return_value=MagicMock()
    ), patch.object(endpoint, "ResearchPackExportService", return_value=service):
        response = _client(audit).get(
            "/api/v1/history/42/research-pack",
            params={"format": "json"},
            cookies={"dsa_session": "valid"},
        )
    assert response.status_code == 500
    assert response.json()["error"] == "internal_error"
    assert len(audit.completions) == 1
    assert audit.completions[0]["outcome"] == "failure"
    assert audit.completions[0]["reason_code"] == "response_contract_invalid"


def test_export_json_rejects_non_json_meta_before_success_audit() -> None:
    audit = SecurityAuditRecorderStub()
    service = MagicMock()
    result = _result(include_zip=False)
    result.meta["unsupported"] = {"set-value"}
    service.export_for_record.return_value = result
    with _patch_services_config(enabled=True), patch.object(
        endpoint, "is_auth_enabled", return_value=True
    ), patch.object(endpoint, "verify_session", return_value=True), patch.object(
        endpoint, "HistoryService", return_value=MagicMock()
    ), patch.object(endpoint, "ResearchPackExportService", return_value=service):
        response = _client(audit).get(
            "/api/v1/history/42/research-pack",
            params={"format": "json"},
            cookies={"dsa_session": "valid"},
        )
    assert response.status_code == 500
    assert len(audit.completions) == 1
    assert audit.completions[0]["outcome"] == "failure"
    assert audit.completions[0]["reason_code"] == "response_contract_invalid"


def test_export_not_found_audits_denied() -> None:
    audit = SecurityAuditRecorderStub()
    service = MagicMock()
    service.export_for_record.side_effect = ResearchPackNotFound()
    with _patch_services_config(enabled=True), patch.object(
        endpoint, "is_auth_enabled", return_value=True
    ), patch.object(endpoint, "verify_session", return_value=True), patch.object(
        endpoint, "HistoryService", return_value=MagicMock()
    ), patch.object(endpoint, "ResearchPackExportService", return_value=service):
        response = _client(audit).get(
            "/api/v1/history/999/research-pack",
            cookies={"dsa_session": "valid"},
        )
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"
    assert audit.completions[0]["outcome"] == "denied"


def test_export_limit_returns_413() -> None:
    audit = SecurityAuditRecorderStub()
    service = MagicMock()
    service.export_for_record.side_effect = ResearchPackLimitError(
        "too large",
        error_code="research_pack_limit_exceeded",
    )
    with _patch_services_config(enabled=True), patch.object(
        endpoint, "is_auth_enabled", return_value=True
    ), patch.object(endpoint, "verify_session", return_value=True), patch.object(
        endpoint, "HistoryService", return_value=MagicMock()
    ), patch.object(endpoint, "ResearchPackExportService", return_value=service):
        response = _client(audit).get(
            "/api/v1/history/42/research-pack",
            cookies={"dsa_session": "valid"},
        )
    assert response.status_code == 413
    assert response.json()["error"] == "research_pack_limit_exceeded"
    assert audit.completions[0]["outcome"] == "failure"


def test_openapi_declares_zip_and_json() -> None:
    schema = _client().app.openapi()
    operation = schema["paths"]["/api/v1/history/{record_id}/research-pack"]["get"]
    success_content = operation["responses"]["200"]["content"]
    assert "application/zip" in success_content
    assert "application/json" in success_content
    for status in ("401", "403", "404", "413", "500", "503"):
        assert status in operation["responses"]
