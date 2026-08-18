# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""HTTP contract tests for the read-only research API (#1143)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import deps as api_deps
from src.api.middlewares.auth import add_auth_middleware
from src.api.middlewares.error_handler import add_error_handlers
from src.api.v1.endpoints import research as endpoint
from src.services.research_api_service import (
    ResearchApiNotFoundError,
    ResearchApiService,
)
from src.services.security_audit_service import SecurityAuditUnavailable
from tests.security_audit_test_utils import SecurityAuditRecorderStub


def _sample_payload() -> dict[str, Any]:
    return {
        "schema_version": "research-conclusion-v1",
        "mode": "standard",
        "metadata": {
            "record_id": 7,
            "query_id": "q-1",
            "stock_code": "600519",
            "stock_name": "Test",
            "report_type": "detailed",
            "created_at": "2026-07-25T16:00:00+08:00",
            "as_of": "2026-07-25T15:00:00+08:00",
            "confidence_level": "中",
            "evidence_counts": {
                "verified_facts": 2,
                "missing_or_conflicts": 1,
                "model_inference": 2,
                "risks_counter_evidence": 2,
                "evidence_refs": 3,
            },
            "evidence_refs": ["ohlcv:daily:600519", "fundamentals:pe_ttm"],
            "report_language": "en",
        },
        "conclusion": {
            "one_sentence": "Hold with confirmation.",
            "signal_type": "hold",
            "position_advice": "Keep core",
            "time_sensitivity": "days",
            "operation_advice": "Hold",
            "action": "hold",
            "action_label": "Hold",
            "risks": ["Valuation elevated"],
            "gaps": [
                {
                    "kind": "conflict",
                    "description": "Providers disagree on volume.",
                    "source_ids": ["ohlcv:provider_a"],
                }
            ],
            "report_strata": {
                "schema_version": "report-strata-v1",
                "verified_facts": [],
                "missing_or_conflicts": [],
                "model_inference": [],
                "risks_counter_evidence": [],
                "framework_alignment": {
                    "status": "not_configured",
                    "summary": "not configured",
                },
                "disclaimer": "Not investment advice.",
            },
            "omitted_count": 0,
            "truncation_notice": None,
            "confidence_reason": "Data quality good",
            "positive_catalysts": ["Holiday demand"],
        },
        "disclaimer": "Not investment advice.",
    }


def _client(
    *,
    enabled: bool = True,
    rate_limit: int = 60,
    audit: Any = None,
    service: ResearchApiService | None = None,
) -> TestClient:
    endpoint.reset_research_rate_limiter_for_tests()
    app = FastAPI()
    app.include_router(endpoint.router, prefix="/api/v1/research")
    add_error_handlers(app)

    config = SimpleNamespace(
        research_api_enabled=enabled,
        research_api_rate_limit_per_minute=rate_limit,
    )
    app.dependency_overrides[api_deps.get_config_dep] = lambda: config
    app.dependency_overrides[api_deps.require_security_audit_service] = (
        lambda: audit if audit is not None else SecurityAuditRecorderStub()
    )
    if service is not None:
        app.dependency_overrides[endpoint._get_research_service] = lambda: service
    return TestClient(app)


def test_disabled_returns_404() -> None:
    client = _client(enabled=False)
    resp = client.get("/api/v1/research/conclusions/1")
    assert resp.status_code == 404
    assert resp.json()["error"] == "not_found"


def test_get_by_record_id_success_and_audit() -> None:
    audit = SecurityAuditRecorderStub()
    service = MagicMock(spec=ResearchApiService)
    service.get_conclusion_by_record_id.return_value = _sample_payload()
    client = _client(audit=audit, service=service)

    resp = client.get("/api/v1/research/conclusions/7?mode=standard")
    assert resp.status_code == 200
    body = resp.json()
    assert body["schema_version"] == "research-conclusion-v1"
    assert body["metadata"]["record_id"] == 7
    assert body["metadata"]["evidence_counts"]["evidence_refs"] == 3
    assert body["conclusion"]["gaps"]
    assert "raw_result" not in body
    service.get_conclusion_by_record_id.assert_called_once()
    assert any(e.get("action") == "research.conclusions.get" for e in audit.attempts)
    assert any(e.get("action") == "research.conclusions.get" for e in audit.completions)
    assert any(e.get("outcome") == "success" for e in audit.completions)


def test_not_found_record() -> None:
    service = MagicMock(spec=ResearchApiService)
    service.get_conclusion_by_record_id.side_effect = ResearchApiNotFoundError(
        "Analysis record not found: 99"
    )
    client = _client(service=service)
    resp = client.get("/api/v1/research/conclusions/99")
    assert resp.status_code == 404
    assert resp.json()["error"] == "not_found"


def test_latest_by_stock_code() -> None:
    service = MagicMock(spec=ResearchApiService)
    service.get_latest_conclusion_for_stock.return_value = _sample_payload()
    client = _client(service=service)
    resp = client.get("/api/v1/research/conclusions?stock_code=600519&mode=brief")
    assert resp.status_code == 200
    service.get_latest_conclusion_for_stock.assert_called_once()
    assert service.get_latest_conclusion_for_stock.call_args.kwargs["mode"] == "brief"


def test_rate_limit_returns_429() -> None:
    service = MagicMock(spec=ResearchApiService)
    service.get_conclusion_by_record_id.return_value = _sample_payload()
    client = _client(service=service, rate_limit=1)
    assert client.get("/api/v1/research/conclusions/7").status_code == 200
    second = client.get("/api/v1/research/conclusions/7")
    assert second.status_code == 429
    assert second.json()["error"] == "rate_limited"


def test_audit_unavailable_on_attempt_returns_503() -> None:
    class _FailAudit(SecurityAuditRecorderStub):
        def record_attempt(self, **fields: Any) -> Any:
            raise SecurityAuditUnavailable()

    service = MagicMock(spec=ResearchApiService)
    service.get_conclusion_by_record_id.return_value = _sample_payload()
    client = _client(audit=_FailAudit(), service=service)
    resp = client.get("/api/v1/research/conclusions/7")
    assert resp.status_code == 503
    assert resp.json()["error"] == "security_audit_unavailable"
    service.get_conclusion_by_record_id.assert_not_called()


def test_router_exposes_only_get_methods() -> None:
    """Write methods must not be registered on the research surface."""
    flattened: set[str] = set()
    for route in endpoint.router.routes:
        route_methods = getattr(route, "methods", None)
        if route_methods:
            flattened.update(route_methods)
    assert flattened <= {"GET", "HEAD"}
    assert "POST" not in flattened
    assert "PUT" not in flattened
    assert "DELETE" not in flattened
    assert "PATCH" not in flattened


def test_auth_middleware_requires_session_when_enabled() -> None:
    """Research routes sit behind AuthMiddleware when ADMIN_AUTH is on."""
    from src.auth import COOKIE_NAME

    endpoint.reset_research_rate_limiter_for_tests()
    service = MagicMock(spec=ResearchApiService)
    service.get_conclusion_by_record_id.return_value = _sample_payload()

    app = FastAPI()
    add_auth_middleware(app)
    app.include_router(endpoint.router, prefix="/api/v1/research")
    add_error_handlers(app)
    app.dependency_overrides[api_deps.get_config_dep] = lambda: SimpleNamespace(
        research_api_enabled=True,
        research_api_rate_limit_per_minute=60,
    )
    app.dependency_overrides[api_deps.require_security_audit_service] = (
        lambda: SecurityAuditRecorderStub()
    )
    app.dependency_overrides[endpoint._get_research_service] = lambda: service

    with patch("src.api.middlewares.auth.is_auth_enabled", return_value=True), patch(
        "src.api.middlewares.auth.verify_session", return_value=False
    ):
        client = TestClient(app)
        denied = client.get("/api/v1/research/conclusions/7")
        assert denied.status_code == 401
        assert denied.json()["error"] == "unauthorized"
        service.get_conclusion_by_record_id.assert_not_called()

    with patch("src.api.middlewares.auth.is_auth_enabled", return_value=True), patch(
        "src.api.middlewares.auth.verify_session", return_value=True
    ):
        client = TestClient(app)
        ok = client.get(
            "/api/v1/research/conclusions/7",
            cookies={COOKIE_NAME: "valid-session-token"},
        )
        assert ok.status_code == 200
        service.get_conclusion_by_record_id.assert_called()
