# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Deterministic HITL approve / reject / timeout contracts at the dashboard entry.

Exercises ``_DashboardMethods._apply_risk_override`` with a **real**
``ApprovalService`` (in-memory SQLite, injectable clock and sleeper). The risk
manager gate and approval state machine are not mocked; only construction is
wired to the test database so the fail-closed risk path remains authoritative.

Refs #225, #1079.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Callable
from unittest.mock import patch

import pytest

from src.agent.orchestrator_parts.dashboard import _DashboardMethods
from src.agent.protocols import AgentContext, AgentOpinion
from src.config import Config
from src.repositories.approval_repo import ApprovalRepository
from src.repositories.security_audit_repo import SecurityAuditRepository
from src.schemas.approvals import (
    ApprovalDecision,
    ApprovalRiskSource,
    ApprovalStatus,
)
from src.services.approval_service import ApprovalService
from src.services.security_audit_service import SecurityAuditService
from src.storage import DatabaseManager


FIXED_NOW = datetime(2026, 7, 26, tzinfo=timezone.utc)


@pytest.fixture
def database():
    DatabaseManager.reset_instance()
    Config.reset_instance()
    manager = DatabaseManager(db_url="sqlite:///:memory:")
    yield manager
    DatabaseManager.reset_instance()
    Config.reset_instance()


def _veto_ctx(*, execution_id: str) -> AgentContext:
    """Build a dashboard exit that triggers a conservative risk override."""
    ctx = AgentContext(stock_code="AAPL")
    ctx.set_data(
        "final_dashboard",
        {"decision_type": "buy", "report_language": "zh"},
    )
    ctx.add_opinion(
        AgentOpinion(
            agent_name="risk",
            signal="hold",
            raw_data={"veto_buy": True, "risk_level": "high"},
        )
    )
    ctx.add_risk_flag("insider", "major sell-down", severity="high")
    ctx.meta["approval_execution_id"] = execution_id
    return ctx


def _harness() -> _DashboardMethods:
    harness = _DashboardMethods()
    harness.config = SimpleNamespace(
        agent_risk_override=True,
        risk_gate_profile="balanced",
    )
    return harness


def _build_service(
    database,
    *,
    clock: Callable[[], datetime],
    sleeper: Callable[[float], None],
    expires_in_seconds: int = 300,
) -> ApprovalService:
    service = ApprovalService(
        ApprovalRepository(database),
        SecurityAuditService(SecurityAuditRepository(database)),
        clock=clock,
        sleeper=sleeper,
        poll_interval_seconds=1.0,
    )
    service.put_rule(
        enabled=True,
        risk_sources=[
            ApprovalRiskSource.RISK_VETO,
            ApprovalRiskSource.RISK_DOWNGRADE,
        ],
        expires_in_seconds=expires_in_seconds,
        expected_version=0,
    )
    return service


def _decide_first_pending(
    service: ApprovalService,
    decision: ApprovalDecision,
) -> Callable[[float], None]:
    """Sleeper that applies a single terminal decision during the first poll."""

    done = {"value": False}

    def _sleep(_seconds: float) -> None:
        if done["value"]:
            return
        items = service.list_proposals(
            status=ApprovalStatus.PENDING,
            page=1,
            page_size=10,
        ).items
        if not items:
            return
        done["value"] = True
        service.decide(
            items[0].id,
            decision=decision,
            expected_version=items[0].version,
            owner="local_admin",
        )

    return _sleep


def test_dashboard_approve_path_preserves_original_signal_via_real_service(
    database,
) -> None:
    """Approve + CAS consume at the dashboard entry keeps the original buy."""
    service = _build_service(
        database,
        clock=lambda: FIXED_NOW,
        sleeper=lambda _s: None,
    )
    service._sleep = _decide_first_pending(service, ApprovalDecision.APPROVED)
    ctx = _veto_ctx(execution_id="hitl-dashboard-approve")

    with patch(
        "src.agent.orchestrator_parts.dashboard._ApprovalService",
        lambda *args, **kwargs: service,
    ):
        application = _harness()._apply_risk_override(ctx)

    assert application is not None
    assert application.bypassed is True
    assert application.applied is False
    dashboard = ctx.get_data("final_dashboard")
    assert dashboard["decision_type"] == "buy"
    assert dashboard["risk_manager"]["authorized_bypass_id"]
    assert dashboard["risk_manager"]["final_action"] == "buy"

    proposals = service.list_proposals(page=1, page_size=10).items
    assert len(proposals) == 1
    assert proposals[0].status is ApprovalStatus.APPROVED
    assert proposals[0].consumed_at is not None
    assert ctx.get_data("risk_control_bypass_applied")["approval_id"] == proposals[0].id


def test_dashboard_reject_path_applies_conservative_signal_via_real_service(
    database,
) -> None:
    """Reject is terminal: dashboard applies the conservative hold, no consume."""
    service = _build_service(
        database,
        clock=lambda: FIXED_NOW,
        sleeper=lambda _s: None,
    )
    service._sleep = _decide_first_pending(service, ApprovalDecision.REJECTED)
    ctx = _veto_ctx(execution_id="hitl-dashboard-reject")

    with patch(
        "src.agent.orchestrator_parts.dashboard._ApprovalService",
        lambda *args, **kwargs: service,
    ):
        application = _harness()._apply_risk_override(ctx)

    assert application is not None
    assert application.bypassed is False
    assert application.applied is True
    assert ctx.get_data("final_dashboard")["decision_type"] == "hold"
    assert ctx.get_data("risk_control_bypass_applied") is None

    proposals = service.list_proposals(page=1, page_size=10).items
    assert len(proposals) == 1
    assert proposals[0].status is ApprovalStatus.REJECTED
    assert proposals[0].consumed_at is None


def test_dashboard_proposal_lifetime_timeout_fails_closed(database) -> None:
    """Proposal lifetime expiry during await returns None; conservative holds."""
    clock = [FIXED_NOW]

    def advance_past_lifetime(_seconds: float) -> None:
        # Lifetime is 30s; jump past expires_at so the next loop expires.
        clock[0] = clock[0] + timedelta(seconds=31)

    service = _build_service(
        database,
        clock=lambda: clock[0],
        sleeper=advance_past_lifetime,
        expires_in_seconds=30,
    )
    ctx = _veto_ctx(execution_id="hitl-dashboard-lifetime-timeout")

    with patch(
        "src.agent.orchestrator_parts.dashboard._ApprovalService",
        lambda *args, **kwargs: service,
    ):
        application = _harness()._apply_risk_override(ctx)

    assert application is not None
    assert application.bypassed is False
    assert application.applied is True
    assert ctx.get_data("final_dashboard")["decision_type"] == "hold"

    proposals = service.list_proposals(page=1, page_size=10).items
    assert len(proposals) == 1
    assert proposals[0].status is ApprovalStatus.EXPIRED
    assert proposals[0].consumed_at is None


def test_dashboard_pipeline_deadline_timeout_stops_wait_without_bypass(
    database,
) -> None:
    """Pipeline deadline is independent of proposal lifetime (docs contract)."""
    service = _build_service(
        database,
        clock=lambda: FIXED_NOW,
        sleeper=lambda _s: None,
        expires_in_seconds=300,
    )
    ctx = _veto_ctx(execution_id="hitl-dashboard-pipeline-deadline")
    # Already past: stop_waiting_check uses time.time() >= deadline_epoch.
    ctx.meta["_approval_deadline_epoch"] = 0.0

    with patch(
        "src.agent.orchestrator_parts.dashboard._ApprovalService",
        lambda *args, **kwargs: service,
    ):
        application = _harness()._apply_risk_override(ctx)

    assert application is not None
    assert application.bypassed is False
    assert application.applied is True
    assert ctx.get_data("final_dashboard")["decision_type"] == "hold"

    proposals = service.list_proposals(page=1, page_size=10).items
    assert len(proposals) == 1
    # Deadline abort leaves the proposal pending until natural expiry.
    assert proposals[0].status is ApprovalStatus.PENDING
    assert proposals[0].consumed_at is None
    assert proposals[0].expires_at > FIXED_NOW
