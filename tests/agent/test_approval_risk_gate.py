"""Unique runtime gate tests for approved and failed risk bypasses."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.agent.orchestrator_parts.dashboard import _DashboardMethods
from src.agent.protocols import AgentContext, AgentOpinion
from src.schemas.approvals import (
    ApprovalContext,
    ApprovalProposal,
    ApprovalRiskSource,
    ApprovalStatus,
)


def _context() -> AgentContext:
    ctx = AgentContext(stock_code="AAPL")
    ctx.set_data("final_dashboard", {"decision_type": "buy"})
    ctx.add_opinion(
        AgentOpinion(
            agent_name="risk",
            signal="hold",
            raw_data={"veto_buy": True, "risk_level": "high"},
        )
    )
    return ctx


def _approved() -> ApprovalProposal:
    now = datetime.now(timezone.utc)
    return ApprovalProposal(
        id="a" * 32,
        owner="local_admin",
        status=ApprovalStatus.APPROVED,
        version=3,
        expires_at=now + timedelta(minutes=5),
        consumed_at=now,
        context=ApprovalContext(
            stock_code="AAPL",
            original_signal="buy",
            conservative_signal="hold",
            risk_source=ApprovalRiskSource.RISK_VETO,
            risk_summary="A risk veto would replace the original buy signal.",
        ),
    )


def _harness() -> _DashboardMethods:
    harness = _DashboardMethods()
    harness.config = SimpleNamespace(agent_risk_override=True)
    return harness


def test_consumed_approval_preserves_original_signal_at_unique_gate() -> None:
    service = MagicMock()
    service.await_risk_control_bypass.return_value = _approved()
    ctx = _context()

    with patch(
        "src.agent.orchestrator_parts.dashboard._ApprovalService",
        return_value=service,
    ):
        application = _harness()._apply_risk_override(ctx)

    assert application is not None
    assert application.bypassed is True
    assert application.approval_id == "a" * 32
    assert application.applied is False
    assert ctx.get_data("final_dashboard")["decision_type"] == "buy"
    assert ctx.get_data("risk_override_applied") is None
    service.await_risk_control_bypass.assert_called_once()


def test_conservative_timeout_fallback_is_idempotent_for_downgrade() -> None:
    service = MagicMock()
    service.await_risk_control_bypass.return_value = _approved()
    ctx = AgentContext(stock_code="AAPL")
    ctx.set_data("final_dashboard", {"decision_type": "buy"})
    ctx.add_opinion(
        AgentOpinion(
            agent_name="risk",
            signal="hold",
            raw_data={"signal_adjustment": "downgrade_one", "risk_level": "high"},
        )
    )
    harness = _harness()

    with patch(
        "src.agent.orchestrator_parts.dashboard._ApprovalService",
        return_value=service,
    ):
        approved = harness._apply_risk_override(ctx)
        fallback = ctx.meta["_risk_control_bypass_fallback_application"]
        ctx.set_data("final_dashboard", {"decision_type": "hold"})
        ctx.meta["risk_override_application"] = fallback
        reapplied = harness._apply_risk_override(ctx)

    assert approved is not None and approved.bypassed is True
    assert fallback.applied is True
    assert fallback.from_signal.value == "buy"
    assert fallback.to_signal.value == "hold"
    assert reapplied is fallback
    assert ctx.get_data("final_dashboard")["decision_type"] == "hold"
    service.await_risk_control_bypass.assert_called_once()


def test_gate_failure_keeps_existing_conservative_override() -> None:
    service = MagicMock()
    service.await_risk_control_bypass.side_effect = RuntimeError("audit offline")
    ctx = _context()

    with patch(
        "src.agent.orchestrator_parts.dashboard._ApprovalService",
        return_value=service,
    ):
        application = _harness()._apply_risk_override(ctx)

    assert application is not None
    assert application.bypassed is False
    assert application.applied is True
    assert ctx.get_data("final_dashboard")["decision_type"] == "hold"
