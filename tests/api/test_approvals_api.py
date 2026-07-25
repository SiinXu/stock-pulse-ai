"""Authentication and additive DTO tests for the approval API."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import deps as api_deps
from api.middlewares.error_handler import add_error_handlers
from api.v1.endpoints import approvals as endpoint
from src.schemas.approvals import (
    ApprovalContext,
    ApprovalProposal,
    ApprovalProposalPage,
    ApprovalRiskSource,
    ApprovalRule,
    ApprovalStatus,
)
from src.services.approval_service import ApprovalServiceVersionConflictError


def _client(service) -> TestClient:
    app = FastAPI()
    app.include_router(endpoint.router, prefix="/api/v1/approvals")
    app.dependency_overrides[api_deps.get_approval_service] = lambda: service
    add_error_handlers(app)
    return TestClient(app)


def _proposal() -> ApprovalProposal:
    now = datetime(2026, 7, 25, tzinfo=timezone.utc)
    return ApprovalProposal(
        id="a" * 32,
        owner="local_admin",
        status=ApprovalStatus.PENDING,
        version=1,
        expires_at=now + timedelta(minutes=5),
        context=ApprovalContext(
            stock_code="AAPL",
            original_signal="buy",
            conservative_signal="hold",
            risk_source=ApprovalRiskSource.RISK_VETO,
            risk_summary="A risk veto would replace the original buy signal.",
        ),
    )


def test_all_endpoints_require_auth_enabled_and_valid_session() -> None:
    service = MagicMock()
    with patch.object(endpoint, "is_auth_enabled", return_value=False):
        response = _client(service).get(
            "/api/v1/approvals",
            cookies={"dsa_session": "ignored"},
        )
    assert response.status_code == 403
    assert response.json()["error"] == "approval_auth_required"

    with patch.object(endpoint, "is_auth_enabled", return_value=True), patch.object(
        endpoint, "verify_session", return_value=False
    ):
        response = _client(service).get(
            "/api/v1/approvals/rules/risk-control-bypass",
            cookies={"dsa_session": "invalid"},
        )
    assert response.status_code == 401
    service.get_rule.assert_not_called()


def test_list_filters_and_decision_are_owner_implicit_and_strict() -> None:
    service = MagicMock()
    proposal = _proposal()
    service.list_proposals.return_value = ApprovalProposalPage(
        items=[proposal],
        page=2,
        page_size=10,
        total=11,
    )
    service.decide.return_value = proposal.model_copy(
        update={"status": ApprovalStatus.APPROVED, "version": 2}
    )
    auth = (
        patch.object(endpoint, "is_auth_enabled", return_value=True),
        patch.object(endpoint, "verify_session", return_value=True),
    )
    with auth[0], auth[1]:
        response = _client(service).get(
            "/api/v1/approvals",
            params={"page": 2, "page_size": 10, "status": "pending"},
            cookies={"dsa_session": "valid"},
        )
        decided = _client(service).post(
            f"/api/v1/approvals/{proposal.id}/decision",
            json={"decision": "approved", "expectedVersion": 1},
            cookies={"dsa_session": "valid"},
        )
    assert response.status_code == 200
    assert response.json()["items"][0]["owner"] == "local_admin"
    service.list_proposals.assert_called_with(
        page=2,
        page_size=10,
        status=ApprovalStatus.PENDING,
    )
    assert decided.status_code == 200
    assert decided.json()["status"] == "approved"
    service.decide.assert_called_with(
        proposal.id,
        decision=endpoint.ApprovalDecisionRequest(
            decision="approved",
            expected_version=1,
        ).decision,
        expected_version=1,
    )


def test_rule_update_and_version_conflict_contract() -> None:
    service = MagicMock()
    service.put_rule.return_value = ApprovalRule(
        owner="local_admin",
        action="risk_control_bypass",
        enabled=True,
        risk_sources=[ApprovalRiskSource.RISK_VETO],
        expires_in_seconds=300,
        version=1,
        updated_at=datetime(2026, 7, 25, tzinfo=timezone.utc),
    )
    with patch.object(endpoint, "is_auth_enabled", return_value=True), patch.object(
        endpoint, "verify_session", return_value=True
    ):
        client = _client(service)
        response = client.put(
            "/api/v1/approvals/rules/risk-control-bypass",
            json={
                "enabled": True,
                "risk_sources": ["risk_veto"],
                "expires_in_seconds": 300,
                "expected_version": 0,
            },
            cookies={"dsa_session": "valid"},
        )
        invalid = client.put(
            "/api/v1/approvals/rules/risk-control-bypass",
            json={
                "enabled": True,
                "risk_sources": ["unknown"],
                "expires_in_seconds": 5,
                "expected_version": 0,
                "owner": "other",
            },
            cookies={"dsa_session": "valid"},
        )
        duplicate_sources = client.put(
            "/api/v1/approvals/rules/risk-control-bypass",
            json={
                "enabled": True,
                "risk_sources": ["risk_veto", "risk_veto"],
                "expires_in_seconds": 300,
                "expected_version": 0,
            },
            cookies={"dsa_session": "valid"},
        )
    assert response.status_code == 200
    assert response.json()["version"] == 1
    assert invalid.status_code == 422
    assert duplicate_sources.status_code == 422
    assert service.put_rule.call_count == 1

    service.put_rule.side_effect = ApprovalServiceVersionConflictError(4)
    with patch.object(endpoint, "is_auth_enabled", return_value=True), patch.object(
        endpoint, "verify_session", return_value=True
    ):
        conflict = _client(service).put(
            "/api/v1/approvals/rules/risk-control-bypass",
            json={
                "enabled": False,
                "risk_sources": ["risk_veto"],
                "expires_in_seconds": 300,
                "expected_version": 1,
            },
            cookies={"dsa_session": "valid"},
        )
    assert conflict.status_code == 409
    assert conflict.json()["params"]["current_version"] == 4


def test_static_openapi_contains_strict_additive_approval_contract() -> None:
    spec = json.loads(
        (Path(__file__).resolve().parents[2] / "docs/architecture/api_spec.json")
        .read_text(encoding="utf-8")
    )
    assert {
        "/api/v1/approvals",
        "/api/v1/approvals/{proposal_id}",
        "/api/v1/approvals/{proposal_id}/decision",
        "/api/v1/approvals/rules/risk-control-bypass",
    } <= set(spec["paths"])
    decision = spec["components"]["schemas"]["ApprovalDecisionRequest"]
    rule = spec["components"]["schemas"]["ApprovalRuleUpdateRequest"]
    proposal = spec["components"]["schemas"]["ApprovalProposal"]
    assert decision["additionalProperties"] is False
    assert rule["additionalProperties"] is False
    assert set(proposal["properties"]) == {
        "id",
        "owner",
        "status",
        "version",
        "expires_at",
        "consumed_at",
        "context",
    }
    assert "prompt" not in json.dumps(proposal).lower()
