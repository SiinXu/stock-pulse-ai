# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""HTTP and OpenAPI contracts for evidence-chain and audit-package export."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.middlewares.error_handler import add_error_handlers
from api.v1.endpoints import evidence_pack as endpoint
from api.v1.schemas.evidence_pack import AuditPackageJsonEnvelope
from src.services.audit_package_export_service import AuditPackageExportResult
from tests.security_audit_test_utils import SecurityAuditRecorderStub


def _client(audit: SecurityAuditRecorderStub | None = None) -> TestClient:
    app = FastAPI()
    app.include_router(endpoint.router, prefix="/api/v1/history")
    app.include_router(endpoint.analysis_alias_router, prefix="/api/v1/analysis")
    add_error_handlers(app)
    from api import deps as api_deps

    app.dependency_overrides[api_deps.get_database_manager] = lambda: MagicMock()
    app.dependency_overrides[api_deps.require_security_audit_service] = (
        lambda: audit or SecurityAuditRecorderStub()
    )
    return TestClient(app)


def _config(*, chain: bool = True, audit: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        evidence_chain_enabled=chain,
        audit_export_enabled=audit,
        audit_include_raw_artifacts=False,
    )


def _patch_config(*, chain: bool = True, audit: bool = True):
    return patch.object(
        endpoint,
        "get_application_services",
        return_value=SimpleNamespace(config=_config(chain=chain, audit=audit)),
    )


def _result() -> AuditPackageExportResult:
    run = {
        "record_id": "42",
        "query_id": None,
        "trace_id": None,
        "run_id": "run-42",
        "lookup_key": "42",
        "lookup_mode": "primary_key",
        "stock_code": None,
        "stock_name": None,
        "market": None,
        "model": None,
        "started_at": None,
        "exported_at": "2026-08-12T00:00:00Z",
        "config_fingerprint": "12345678",
    }
    evidence_chain = {
        "schema_version": "evidence-chain-v1",
        "run": run,
        "conclusions": [],
        "evidence_items": [],
        "reasoning_steps": [],
        "gaps": [],
        "coverage": {"sources": [], "not_recorded": [], "notes": ""},
        "truncated": False,
    }
    return AuditPackageExportResult(
        zip_bytes=b"PK-test-package",
        manifest={
            "schema_version": "audit-package-v1",
            "run": run,
            "artifacts": [],
            "evidence_chain_schema": "evidence-chain-v1",
            "reasoning_trace_schema": None,
            "redacted": True,
            "include_raw_artifacts": False,
            "truncated": False,
            "notes": "",
        },
        evidence_chain=evidence_chain,
        artifact_payloads={
            "evidence_chain.json": {"$ref": "evidence_chain"},
            "report.md": "# Report",
        },
        truncated=False,
        resolved_record_id="42",
        lookup_mode="primary_key",
    )


def test_audit_json_export_has_artifact_parity_and_audit_completion() -> None:
    audit = SecurityAuditRecorderStub()
    service = MagicMock()
    service.export_for_record.return_value = _result()
    with _patch_config(), patch.object(endpoint, "is_auth_enabled", return_value=True), patch.object(
        endpoint, "verify_session", return_value=True
    ), patch.object(endpoint, "HistoryService", return_value=MagicMock()), patch.object(
        endpoint, "AuditPackageExportService", return_value=service
    ):
        response = _client(audit).get(
            "/api/v1/history/42/evidence-pack",
            params={"format": "json"},
            cookies={"dsa_session": "valid"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "audit-package-v1"
    assert body["artifacts"]["report.md"] == "# Report"
    assert body["artifacts"]["evidence_chain.json"] == {"$ref": "evidence_chain"}
    assert response.headers["x-audit-package-truncated"] == "0"
    assert len(audit.attempts) == 1
    assert audit.completions[0]["outcome"] == "success"
    assert audit.completions[0]["target_id"] == "42"


def test_export_requires_admin_authentication() -> None:
    with _patch_config(), patch.object(endpoint, "is_auth_enabled", return_value=False):
        response = _client().get("/api/v1/history/42/evidence-pack")
    assert response.status_code == 403
    assert response.json()["error"] == "audit_export_auth_required"


def test_disabled_export_fails_before_history_access() -> None:
    with _patch_config(audit=False), patch.object(endpoint, "HistoryService") as history:
        response = _client().get("/api/v1/history/42/evidence-pack")
    assert response.status_code == 404
    assert response.json()["error"] == "audit_export_disabled"
    history.assert_not_called()


def test_analysis_aliases_have_unique_typed_openapi_operations() -> None:
    schema = _client().app.openapi()
    history_chain = schema["paths"]["/api/v1/history/{record_id}/evidence-chain"]["get"]
    analysis_chain = schema["paths"]["/api/v1/analysis/{record_id}/evidence-chain"]["get"]
    history_pack = schema["paths"]["/api/v1/history/{record_id}/evidence-pack"]["get"]
    analysis_pack = schema["paths"]["/api/v1/analysis/{record_id}/evidence-pack"]["get"]

    operation_ids = {
        history_chain["operationId"], analysis_chain["operationId"],
        history_pack["operationId"], analysis_pack["operationId"],
    }
    assert operation_ids == {
        "exportEvidenceChain", "exportAnalysisEvidenceChain",
        "exportAuditPackage", "exportAnalysisAuditPackage",
    }
    for operation in (history_chain, analysis_chain, history_pack, analysis_pack):
        path_parameters = [item for item in operation["parameters"] if item["in"] == "path"]
        assert path_parameters[0]["name"] == "record_id"
        assert path_parameters[0]["required"] is True
    for operation in (history_pack, analysis_pack):
        content = operation["responses"]["200"]["content"]
        assert content["application/json"]["schema"] == {
            "$ref": "#/components/schemas/AuditPackageJsonEnvelope"
        }
        assert content["application/zip"]["schema"] == {
            "type": "string", "format": "binary"
        }


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), float("-inf")])
def test_audit_json_contract_rejects_non_finite_artifact_values(invalid: float) -> None:
    envelope = _result().to_json_envelope()
    envelope["artifacts"]["unsafe.json"] = {"value": invalid}
    with pytest.raises(ValueError):
        AuditPackageJsonEnvelope.model_validate(envelope)


def test_audit_json_endpoint_fails_closed_for_non_finite_artifact_value() -> None:
    audit = SecurityAuditRecorderStub()
    result = _result()
    result.artifact_payloads["unsafe.json"] = {"value": float("nan")}
    service = MagicMock()
    service.export_for_record.return_value = result
    with _patch_config(), patch.object(endpoint, "is_auth_enabled", return_value=True), patch.object(
        endpoint, "verify_session", return_value=True
    ), patch.object(endpoint, "HistoryService", return_value=MagicMock()), patch.object(
        endpoint, "AuditPackageExportService", return_value=service
    ):
        response = _client(audit).get(
            "/api/v1/history/42/evidence-pack",
            params={"format": "json"},
            cookies={"dsa_session": "valid"},
        )

    assert response.status_code == 500
    assert response.json()["error"] == "internal_error"
    assert audit.completions[0]["outcome"] == "failure"
    assert audit.completions[0]["reason_code"] == "response_contract_invalid"
