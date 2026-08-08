# -*- coding: utf-8 -*-
"""Mandatory Risk Manager gate — outcomes, exits, and fail-safe (#120)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.agent.committee_mode import META_COMMITTEE_MODE
from src.agent.protocols import AgentContext, AgentOpinion
from src.agent.risk_override import (
    DATA_RISK_GATE_APPLIED,
    EXIT_AGENT_CHAT,
    EXIT_COMMITTEE_MODE,
    EXIT_DELIBERATION_PROJECTION,
    EXIT_ORCHESTRATOR_MULTI_AGENT,
    EXIT_SINGLE_AGENT,
    META_RISK_GATE_RESULT,
    RiskGateOutcome,
    apply_risk_manager_gate,
    apply_risk_manager_gate_from_config,
    evaluate_risk_manager_gate,
    get_risk_gate_result,
)


def _ctx_with_risk(
    *,
    veto: bool = False,
    adjustment: str = "",
    risk_level: str = "",
    high_flag: bool = False,
    risk_signal: str = "hold",
    decision_confidence: float = 0.5,
) -> AgentContext:
    ctx = AgentContext(query="test", stock_code="600519")
    raw: dict = {}
    if veto:
        raw["veto_buy"] = True
    if adjustment:
        raw["signal_adjustment"] = adjustment
    if risk_level:
        raw["risk_level"] = risk_level
    ctx.add_opinion(
        AgentOpinion(
            agent_name="decision",
            signal="buy",
            confidence=decision_confidence,
            reasoning="base",
        )
    )
    ctx.add_opinion(
        AgentOpinion(
            agent_name="risk",
            signal=risk_signal,
            confidence=0.9,
            raw_data=raw,
        )
    )
    if high_flag:
        ctx.add_risk_flag("insider", "major sell-down", severity="high")
    return ctx


# ---------------------------------------------------------------------------
# Gate outcomes
# ---------------------------------------------------------------------------


def test_gate_pass_when_no_risk_evidence():
    ctx = AgentContext()
    ctx.add_opinion(AgentOpinion(agent_name="decision", signal="buy", confidence=0.6))
    result = evaluate_risk_manager_gate(
        ctx,
        current_signal="buy",
        exit_id=EXIT_SINGLE_AGENT,
    )
    assert result.outcome is RiskGateOutcome.PASS
    assert result.final_signal == "buy"
    assert result.warnings == ()


def test_gate_attach_warning_when_override_disabled_but_veto_present():
    ctx = _ctx_with_risk(veto=True, high_flag=True, risk_signal="strong_sell")
    result = evaluate_risk_manager_gate(
        ctx,
        current_signal="buy",
        exit_id=EXIT_ORCHESTRATOR_MULTI_AGENT,
        override_enabled=False,
        gate_enabled=True,
        gate_strict=False,
    )
    assert result.outcome is RiskGateOutcome.ATTACH_WARNING
    assert result.final_signal == "buy"
    assert result.original_signal == "buy"
    assert result.warnings
    assert "risk_veto" in result.evidence_codes
    assert all(result.final_signal for _ in [1])  # never empty


def test_gate_downgrade_when_override_enabled_and_veto():
    ctx = _ctx_with_risk(veto=True, high_flag=True, risk_signal="strong_sell")
    result = evaluate_risk_manager_gate(
        ctx,
        current_signal="buy",
        exit_id=EXIT_ORCHESTRATOR_MULTI_AGENT,
        override_enabled=True,
        gate_strict=False,
    )
    assert result.outcome is RiskGateOutcome.DOWNGRADE
    assert result.final_signal == "hold"
    assert result.original_signal == "buy"


def test_gate_strict_force_downgrade_when_override_disabled():
    ctx = _ctx_with_risk(veto=True, high_flag=True, risk_signal="strong_sell")
    result = evaluate_risk_manager_gate(
        ctx,
        current_signal="buy",
        exit_id=EXIT_ORCHESTRATOR_MULTI_AGENT,
        override_enabled=False,
        gate_strict=True,
    )
    assert result.outcome is RiskGateOutcome.DOWNGRADE
    assert result.final_signal == "hold"


def test_gate_fail_safe_on_internal_error():
    ctx = AgentContext()

    with patch(
        "src.agent.risk_override.evaluate_risk_manager_gate",
        side_effect=RuntimeError("boom"),
    ):
        result = apply_risk_manager_gate(
            ctx,
            current_signal="buy",
            exit_id=EXIT_SINGLE_AGENT,
        )

    assert result.fail_safe is True
    assert result.outcome is RiskGateOutcome.PASS
    assert result.final_signal == "buy"
    assert "gate_internal_failure" in result.evidence_codes
    assert get_risk_gate_result(ctx) is result
    assert isinstance(ctx.get_data(DATA_RISK_GATE_APPLIED), dict)


def test_apply_gate_annotates_warning_without_clearing_signal():
    ctx = _ctx_with_risk(veto=True, high_flag=True)
    dashboard = {
        "decision_type": "buy",
        "operation_advice": "买入",
        "risk_warning": "原提示",
    }
    result = apply_risk_manager_gate(
        ctx,
        current_signal="buy",
        exit_id=EXIT_ORCHESTRATOR_MULTI_AGENT,
        override_enabled=False,
        gate_strict=False,
        dashboard=dashboard,
    )
    assert result.outcome is RiskGateOutcome.ATTACH_WARNING
    assert dashboard["decision_type"] == "buy"
    assert dashboard["operation_advice"] == "买入"
    assert "[Risk Manager]" in dashboard["risk_warning"]
    assert "原提示" in dashboard["risk_warning"]


# ---------------------------------------------------------------------------
# Decision exits (each exit must call the gate)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exit_id",
    [
        EXIT_ORCHESTRATOR_MULTI_AGENT,
        EXIT_SINGLE_AGENT,
        EXIT_COMMITTEE_MODE,
        EXIT_DELIBERATION_PROJECTION,
        EXIT_AGENT_CHAT,
    ],
)
def test_each_decision_exit_records_gate_trace(exit_id):
    ctx = _ctx_with_risk(risk_level="high")
    result = apply_risk_manager_gate_from_config(
        ctx,
        current_signal="buy",
        exit_id=exit_id,
        config=SimpleNamespace(
            risk_gate_enabled=True,
            risk_gate_strict=False,
            agent_risk_override=False,
        ),
    )
    assert result.exit_id == exit_id
    stored = get_risk_gate_result(ctx)
    assert stored is not None
    assert stored.exit_id == exit_id
    assert ctx.get_data(DATA_RISK_GATE_APPLIED)["exit_id"] == exit_id


def test_orchestrator_multi_agent_exit_runs_gate():
    from src.agent.orchestrator import AgentOrchestrator

    orch = AgentOrchestrator(
        tool_registry=MagicMock(),
        llm_adapter=MagicMock(),
        config=SimpleNamespace(
            agent_risk_override=True,
            risk_gate_enabled=True,
            risk_gate_strict=False,
        ),
    )
    ctx = _ctx_with_risk(veto=True, high_flag=True, risk_signal="strong_sell")
    dashboard = {
        "decision_type": "buy",
        "sentiment_score": 76,
        "operation_advice": "买入",
        "analysis_summary": "原始结论",
        "risk_warning": "原风险提示",
        "dashboard": {
            "core_conclusion": {
                "one_sentence": "可以参与",
                "signal_type": "🟢买入信号",
                "position_advice": {
                    "no_position": "分批买入",
                    "has_position": "继续持有",
                },
            }
        },
    }
    ctx.set_data("final_dashboard", dashboard)
    resolved = orch._resolve_dashboard_payload(ctx, dashboard, None)

    assert resolved is not None
    assert resolved["decision_type"] == "hold"
    gate = get_risk_gate_result(ctx)
    assert gate is not None
    assert gate.exit_id == EXIT_ORCHESTRATOR_MULTI_AGENT
    assert gate.outcome is RiskGateOutcome.DOWNGRADE


def test_committee_mode_exit_uses_committee_exit_id():
    from src.agent.orchestrator import AgentOrchestrator

    orch = AgentOrchestrator(
        tool_registry=MagicMock(),
        llm_adapter=MagicMock(),
        config=SimpleNamespace(
            agent_risk_override=False,
            risk_gate_enabled=True,
            risk_gate_strict=False,
        ),
    )
    ctx = _ctx_with_risk(veto=True, high_flag=True, risk_signal="strong_sell")
    ctx.meta[META_COMMITTEE_MODE] = True
    dashboard = {
        "decision_type": "buy",
        "sentiment_score": 70,
        "operation_advice": "买入",
        "analysis_summary": "committee",
        "risk_warning": "",
        "dashboard": {"core_conclusion": {"one_sentence": "buy"}},
    }
    ctx.set_data("final_dashboard", dashboard)
    resolved = orch._resolve_dashboard_payload(ctx, dashboard, None)

    assert resolved is not None
    # Override off + non-strict → warn only, signal stays buy
    assert resolved["decision_type"] == "buy"
    gate = get_risk_gate_result(ctx)
    assert gate is not None
    assert gate.exit_id == EXIT_COMMITTEE_MODE
    assert gate.outcome is RiskGateOutcome.ATTACH_WARNING
    assert "[Risk Manager]" in resolved["risk_warning"]


def test_single_agent_exit_gates_dashboard_without_prior_override():
    """Single-agent analysis path applies gate when multi-agent did not."""
    from src.agent.protocols import AgentContext as Ctx
    from src.agent.risk_override import apply_risk_manager_gate_from_config

    dash = {"decision_type": "buy", "risk_warning": "", "operation_advice": "buy"}
    gate_ctx = Ctx(query="", stock_code="AAPL")
    # Simulate risk evidence available on single-agent context
    gate_ctx.add_risk_flag("insider", "sell", severity="high")
    gate_ctx.add_opinion(
        AgentOpinion(
            agent_name="risk",
            signal="sell",
            confidence=0.9,
            raw_data={"veto_buy": True},
        )
    )
    result = apply_risk_manager_gate_from_config(
        gate_ctx,
        current_signal="buy",
        exit_id=EXIT_SINGLE_AGENT,
        config=SimpleNamespace(
            risk_gate_enabled=True,
            risk_gate_strict=False,
            agent_risk_override=False,
        ),
        dashboard=dash,
    )
    assert result.exit_id == EXIT_SINGLE_AGENT
    assert result.outcome is RiskGateOutcome.ATTACH_WARNING
    assert dash["decision_type"] == "buy"
    assert "[Risk Manager]" in dash["risk_warning"]


def test_deliberation_projection_exit_records_gate():
    ctx = _ctx_with_risk(veto=True, high_flag=True)
    result = apply_risk_manager_gate(
        ctx,
        current_signal="hold",
        exit_id=EXIT_DELIBERATION_PROJECTION,
        override_enabled=True,
    )
    assert result.exit_id == EXIT_DELIBERATION_PROJECTION
    assert get_risk_gate_result(ctx).exit_id == EXIT_DELIBERATION_PROJECTION


def test_agent_chat_exit_unstructured_still_evaluates():
    ctx = AgentContext(query="how is AAPL?", stock_code="AAPL")
    result = apply_risk_manager_gate(
        ctx,
        current_signal="hold",
        exit_id=EXIT_AGENT_CHAT,
    )
    assert result.exit_id == EXIT_AGENT_CHAT
    assert result.outcome is RiskGateOutcome.PASS
    assert result.final_signal == "hold"


def test_gate_disabled_is_explicit_pass():
    ctx = _ctx_with_risk(veto=True)
    result = evaluate_risk_manager_gate(
        ctx,
        current_signal="buy",
        exit_id=EXIT_ORCHESTRATOR_MULTI_AGENT,
        gate_enabled=False,
    )
    assert result.outcome is RiskGateOutcome.PASS
    assert result.enabled is False
    assert result.final_signal == "buy"


def test_override_disabled_still_gets_mandatory_warning_on_multi_agent():
    """Regression: AGENT_RISK_OVERRIDE=false must not skip gate evaluation."""
    from src.agent.orchestrator import AgentOrchestrator

    orch = AgentOrchestrator(
        tool_registry=MagicMock(),
        llm_adapter=MagicMock(),
        config=SimpleNamespace(
            agent_risk_override=False,
            risk_gate_enabled=True,
            risk_gate_strict=False,
        ),
    )
    ctx = _ctx_with_risk(veto=True, high_flag=True, risk_signal="strong_sell")
    dashboard = {
        "decision_type": "buy",
        "sentiment_score": 80,
        "operation_advice": "买入",
        "analysis_summary": "raw",
        "risk_warning": "base",
        "dashboard": {"core_conclusion": {"one_sentence": "buy"}},
    }
    ctx.set_data("final_dashboard", dashboard)
    resolved = orch._resolve_dashboard_payload(ctx, dashboard, None)

    assert resolved["decision_type"] == "buy"
    assert ctx.get_data("risk_override_applied") is None
    gate = ctx.meta.get(META_RISK_GATE_RESULT)
    assert gate is not None
    assert gate.outcome is RiskGateOutcome.ATTACH_WARNING
    assert "[Risk Manager]" in resolved["risk_warning"]
