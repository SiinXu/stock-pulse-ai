# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""HTTP access-control and bounded-query contract for security audit events."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import deps as api_deps
from api.middlewares.error_handler import add_error_handlers
from api.v1.endpoints import security_audit as endpoint
from src.schemas.security_audit import SecurityAuditEventPage
from src.services.security_audit_service import SecurityAuditUnavailable


def _client(service) -> TestClient:
    app = FastAPI()
    app.include_router(endpoint.router, prefix="/api/v1/security")
    app.dependency_overrides[api_deps.get_security_audit_service] = lambda: service
    add_error_handlers(app)
    return TestClient(app)


def test_query_denies_auth_disabled_even_with_cookie() -> None:
    service = MagicMock()
    with patch.object(endpoint, "is_auth_enabled", return_value=False):
        response = _client(service).get(
            "/api/v1/security/audit-events",
            cookies={"dsa_session": "ignored"},
        )

    assert response.status_code == 403
    assert response.json()["error"] == "security_audit_auth_required"
    service.list_events.assert_not_called()


def test_query_requires_valid_admin_session() -> None:
    service = MagicMock()
    with patch.object(endpoint, "is_auth_enabled", return_value=True), patch.object(
        endpoint, "verify_session", return_value=False
    ):
        response = _client(service).get(
            "/api/v1/security/audit-events",
            cookies={"dsa_session": "invalid"},
        )

    assert response.status_code == 401
    service.list_events.assert_not_called()


def test_query_passes_bounded_filters_to_service() -> None:
    service = MagicMock()
    service.list_events.return_value = SecurityAuditEventPage(
        items=[], page=2, page_size=25, total=0
    )
    with patch.object(endpoint, "is_auth_enabled", return_value=True), patch.object(
        endpoint, "verify_session", return_value=True
    ):
        response = _client(service).get(
            "/api/v1/security/audit-events",
            params={
                "page": 2,
                "page_size": 25,
                "event_type": "auth.login",
                "outcome": "denied",
                "correlation_id": "0123456789abcdef0123456789abcdef",
                "occurred_from": "2026-07-01T00:00:00Z",
                "occurred_to": "2026-07-24T23:59:59Z",
            },
            cookies={"dsa_session": "valid"},
        )

    assert response.status_code == 200
    assert response.json() == {"items": [], "page": 2, "page_size": 25, "total": 0}
    kwargs = service.list_events.call_args.kwargs
    assert kwargs["event_type"] == "auth.login"
    assert kwargs["outcome"] == "denied"
    assert kwargs["occurred_from"].utcoffset().total_seconds() == 0


def test_query_surfaces_storage_failure() -> None:
    service = MagicMock()
    service.list_events.side_effect = SecurityAuditUnavailable()
    with patch.object(endpoint, "is_auth_enabled", return_value=True), patch.object(
        endpoint, "verify_session", return_value=True
    ):
        response = _client(service).get(
            "/api/v1/security/audit-events",
            cookies={"dsa_session": "valid"},
        )

    assert response.status_code == 503
    assert response.json()["error"] == "security_audit_unavailable"


def test_query_rejects_malformed_dependency_with_stable_503() -> None:
    response = _client(None).get("/api/v1/security/audit-events")

    assert response.status_code == 503
    assert response.json()["error"] == "security_audit_unavailable"


def test_static_openapi_artifact_carries_security_audit_v1_contract() -> None:
    spec = json.loads(
        (Path(__file__).resolve().parents[2] / "docs/architecture/api_spec.json")
        .read_text(encoding="utf-8")
    )

    operation = spec["paths"]["/api/v1/security/audit-events"]["get"]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/SecurityAuditEventPage"
    }
    assert operation["responses"]["503"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }
    event = spec["components"]["schemas"]["SecurityAuditEvent"]
    assert event["properties"]["schema_version"]["const"] == "security-audit-v1"
    assert event["properties"]["phase"]["enum"] == ["attempt", "completion"]
