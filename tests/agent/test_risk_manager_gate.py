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
    RiskGateProfile,
    RiskGateResult,
    apply_risk_manager_gate,
    apply_risk_manager_gate_from_config,
    build_risk_context_for_exit,
    evaluate_risk_manager_gate,
    get_risk_gate_result,
    render_risk_gate_notice,
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


def test_balanced_gate_downgrades_even_when_legacy_override_disabled():
    ctx = _ctx_with_risk(veto=True, high_flag=True, risk_signal="strong_sell")
    result = evaluate_risk_manager_gate(
        ctx,
        current_signal="buy",
        exit_id=EXIT_ORCHESTRATOR_MULTI_AGENT,
        override_enabled=False,
        profile="balanced",
    )
    assert result.outcome is RiskGateOutcome.DOWNGRADE
    assert result.final_signal == "hold"
    assert result.original_signal == "buy"
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


def test_conservative_profile_rejects_explicit_veto():
    ctx = _ctx_with_risk(veto=True, high_flag=True, risk_signal="strong_sell")
    result = evaluate_risk_manager_gate(
        ctx,
        current_signal="buy",
        exit_id=EXIT_ORCHESTRATOR_MULTI_AGENT,
        override_enabled=False,
        profile="conservative",
    )
    assert result.outcome is RiskGateOutcome.REJECT
    assert result.final_signal == "hold"


@pytest.mark.parametrize(
    ("profile", "verdict"),
    [
        ("conservative", RiskGateOutcome.REJECT),
        ("balanced", RiskGateOutcome.DOWNGRADE),
        ("aggressive", RiskGateOutcome.DOWNGRADE),
    ],
)
def test_every_profile_handles_explicit_veto(profile, verdict):
    ctx = _ctx_with_risk(veto=True, high_flag=True, risk_signal="strong_sell")

    result = evaluate_risk_manager_gate(
        ctx,
        current_signal="buy",
        exit_id=EXIT_SINGLE_AGENT,
        override_enabled=False,
        profile=profile,
    )

    assert result.verdict is verdict
    assert result.final_action == "hold"


@pytest.mark.parametrize(
    ("profile", "verdict", "final_action"),
    [
        ("conservative", RiskGateOutcome.REJECT, "hold"),
        ("balanced", RiskGateOutcome.PASS, "buy"),
        ("aggressive", RiskGateOutcome.PASS, "buy"),
    ],
)
def test_profiles_apply_distinct_portfolio_exposure_thresholds(
    profile,
    verdict,
    final_action,
):
    ctx = AgentContext()
    ctx.set_data("portfolio_exposure", 0.75)

    result = evaluate_risk_manager_gate(
        ctx,
        current_signal="buy",
        exit_id=EXIT_SINGLE_AGENT,
        profile=profile,
    )

    assert result.verdict is verdict
    assert result.final_action == final_action
    assert ("portfolio_exposure_limit" in result.evidence_codes) is (
        profile == "conservative"
    )


@pytest.mark.parametrize(
    ("profile", "verdict"),
    [
        ("conservative", RiskGateOutcome.REJECT),
        ("balanced", RiskGateOutcome.DOWNGRADE),
        ("aggressive", RiskGateOutcome.DOWNGRADE),
    ],
)
def test_extreme_portfolio_facts_block_buy_without_risk_agent(profile, verdict):
    ctx = AgentContext()
    ctx.set_data("portfolio_exposure", 0.99)
    ctx.set_data("volatility", 0.80)
    ctx.set_data("historical_outcomes", {"loss_rate": 0.95})
    ctx.set_data("current_holdings", {"AAPL": 120})

    result = evaluate_risk_manager_gate(
        ctx,
        current_signal="buy",
        exit_id=EXIT_SINGLE_AGENT,
        profile=profile,
    )

    assert result.verdict is verdict
    assert result.final_action == "hold"
    assert set(result.evidence_codes) >= {
        "portfolio_exposure_limit",
        "volatility_limit",
        "historical_loss_rate_limit",
    }
    assert set(result.evidence_provenance) >= {
        "portfolio_exposure",
        "volatility",
        "historical_outcomes",
        "current_holdings",
    }


def test_real_orchestrator_entry_carries_portfolio_facts_to_final_gate():
    from src.agent.orchestrator import AgentOrchestrator
    from src.agent.runtime_facts import build_agent_runtime_facts

    orchestrator = AgentOrchestrator(
        tool_registry=MagicMock(),
        llm_adapter=MagicMock(),
        config=SimpleNamespace(investment_committee_enabled=False),
    )
    context = orchestrator._build_context(
        "Analyze AAPL",
        {
            "stock_code": "AAPL",
            "portfolio_context": {
                "portfolio_exposure": 0.99,
                "volatility": 0.80,
                "historical_outcomes": {"loss_rate": 0.95},
                "symbol": "AAPL",
                "quantity": 120,
            },
        },
    )
    runtime_facts = build_agent_runtime_facts(context)
    gate_ctx = build_risk_context_for_exit(
        stock_code="AAPL",
        current_signal="buy",
        runtime_facts=runtime_facts,
    )

    result = evaluate_risk_manager_gate(
        gate_ctx,
        current_signal="buy",
        exit_id=EXIT_SINGLE_AGENT,
        profile="conservative",
    )

    assert runtime_facts.risk_evidence is not None
    assert runtime_facts.risk_evidence.portfolio_exposure == 0.99
    assert '"quantity": 120' in runtime_facts.risk_evidence.current_holdings
    assert result.verdict is RiskGateOutcome.REJECT
    assert result.final_action == "hold"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -0.1, 1.1])
def test_invalid_portfolio_ratios_fail_closed(value):
    from src.agent.orchestrator import AgentOrchestrator
    from src.agent.runtime_facts import build_agent_runtime_facts

    orchestrator = AgentOrchestrator(
        tool_registry=MagicMock(),
        llm_adapter=MagicMock(),
        config=SimpleNamespace(investment_committee_enabled=False),
    )
    context = orchestrator._build_context(
        "Analyze AAPL",
        {"stock_code": "AAPL", "portfolio_exposure": value},
    )
    runtime_facts = build_agent_runtime_facts(context)
    gate_ctx = build_risk_context_for_exit(
        stock_code="AAPL",
        current_signal="buy",
        runtime_facts=runtime_facts,
    )

    result = evaluate_risk_manager_gate(
        gate_ctx,
        current_signal="buy",
        exit_id=EXIT_SINGLE_AGENT,
        profile="balanced",
    )

    assert result.verdict is RiskGateOutcome.DOWNGRADE
    assert result.final_action == "hold"
    assert "invalid_risk_evidence" in result.evidence_codes
    assert runtime_facts.risk_evidence is not None
    assert runtime_facts.risk_evidence.invalid_fields == ("portfolio_exposure",)


def test_invalid_dashboard_risk_evidence_fails_closed_without_truthy_coercion():
    gate_ctx = build_risk_context_for_exit(
        stock_code="AAPL",
        current_signal="buy",
        dashboard={
            "decision_type": "buy",
            "risk_assessment": {"veto_buy": "false"},
        },
    )

    result = evaluate_risk_manager_gate(
        gate_ctx,
        current_signal="buy",
        exit_id=EXIT_SINGLE_AGENT,
        profile="balanced",
    )

    assert result.final_action == "hold"
    assert "invalid_risk_evidence" in result.evidence_codes


def test_stale_runtime_evidence_is_preserved_and_blocks_bullish_publication():
    from src.agent.runtime_facts import AgentRuntimeFacts, RiskEvidenceFact

    runtime_facts = AgentRuntimeFacts(
        risk_evidence=RiskEvidenceFact(
            signal="hold",
            risk_level="low",
            as_of="2020-01-01T00:00:00+00:00",
        )
    )
    gate_ctx = build_risk_context_for_exit(
        stock_code="AAPL",
        current_signal="buy",
        runtime_facts=runtime_facts,
    )

    result = evaluate_risk_manager_gate(
        gate_ctx,
        current_signal="buy",
        exit_id=EXIT_DELIBERATION_PROJECTION,
        profile="balanced",
    )

    assert result.final_action == "hold"
    assert "stale_risk_evidence" in result.evidence_codes
    assert "risk_evidence_as_of" in result.evidence_provenance


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

    assert result.fail_closed is True
    assert result.outcome is RiskGateOutcome.REJECT
    assert result.final_signal == "hold"
    assert "gate_internal_failure" in result.evidence_codes
    assert get_risk_gate_result(ctx) is result
    assert isinstance(ctx.get_data(DATA_RISK_GATE_APPLIED), dict)


def test_invalid_direct_profile_fails_closed_instead_of_escaping_fallback():
    result = apply_risk_manager_gate(
        AgentContext(),
        current_signal="buy",
        exit_id=EXIT_SINGLE_AGENT,
        profile="invalid-profile",
    )

    assert result.verdict is RiskGateOutcome.REJECT
    assert result.final_action == "hold"
    assert result.profile is RiskGateProfile.BALANCED
    assert result.fail_closed is True
    assert dict(result.reason_params)["requested_profile"] == "invalid-profile"


def test_gate_result_rejects_unbounded_or_human_reason_codes():
    common = {
        "outcome": RiskGateOutcome.PASS,
        "original_signal": "hold",
        "final_signal": "hold",
        "warnings": (),
        "evidence_codes": (),
        "enabled": True,
        "strict": False,
        "override_enabled": True,
        "override_would_apply": False,
        "exit_id": EXIT_SINGLE_AGENT,
    }

    with pytest.raises(ValueError, match="stable bounded keys"):
        RiskGateResult(reasons=("human readable sentence",), **common)
    with pytest.raises(ValueError, match="exceeds 20 items"):
        RiskGateResult(reasons=tuple(f"reason_{index}" for index in range(21)), **common)


def test_gate_notice_localizes_korean_and_keeps_structured_reason_codes():
    result = evaluate_risk_manager_gate(
        _ctx_with_risk(veto=True),
        current_signal="buy",
        exit_id=EXIT_SINGLE_AGENT,
    )

    assert "리스크 매니저 하향 조정" in render_risk_gate_notice(result, "ko")
    assert result.reasons == result.evidence_codes
    assert all(" " not in code for code in result.to_trace_dict()["reason_codes"])


def test_apply_gate_annotates_and_mutates_the_authoritative_signal():
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
        profile="balanced",
        dashboard=dashboard,
    )
    assert result.outcome is RiskGateOutcome.DOWNGRADE
    assert dashboard["decision_type"] == "hold"
    assert dashboard["operation_advice"] == "买入"
    assert "风控经理已下调" in dashboard["risk_warning"]
    assert dashboard["risk_manager"]["final_action"] == "hold"
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
            risk_gate_profile="balanced",
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
            risk_gate_profile="balanced",
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
            risk_gate_profile="balanced",
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
    assert resolved["decision_type"] == "hold"
    gate = get_risk_gate_result(ctx)
    assert gate is not None
    assert gate.exit_id == EXIT_COMMITTEE_MODE
    assert gate.outcome is RiskGateOutcome.DOWNGRADE
    assert "风控经理已下调" in resolved["risk_warning"]


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
            risk_gate_profile="balanced",
            agent_risk_override=False,
        ),
        dashboard=dash,
    )
    assert result.exit_id == EXIT_SINGLE_AGENT
    assert result.outcome is RiskGateOutcome.DOWNGRADE
    assert dash["decision_type"] == "hold"
    assert "风控经理已下调" in dash["risk_warning"]


def test_real_single_agent_conversion_uses_dashboard_risk_evidence():
    from src.core.stages.analysis_results import _AnalysisResultStageMixin
    from src.enums import ReportType

    class Stage(_AnalysisResultStageMixin):
        config = SimpleNamespace(
            report_language="en",
            risk_gate_profile="balanced",
            agent_risk_override=False,
        )

    agent_result = SimpleNamespace(
        success=True,
        error=None,
        provider="test",
        model="test/model",
        runtime_facts=None,
        dashboard={
            "stock_name": "Apple",
            "decision_type": "buy",
            "operation_advice": "Buy",
            "analysis_summary": "Buy now",
            "risk_warning": "",
            "risk_assessment": {
                "veto_buy": True,
                "risk_level": "high",
                "risk_flags": [
                    {
                        "category": "exposure",
                        "description": "Exposure limit breached",
                        "severity": "high",
                    }
                ],
            },
        },
    )

    result = Stage()._agent_result_to_analysis_result(
        agent_result,
        "AAPL",
        "Apple",
        ReportType.FULL,
        "query-risk",
    )

    assert result.decision_type == "hold"
    assert agent_result.dashboard["decision_type"] == "hold"
    assert result.risk_gate_result["final_action"] == "hold"
    assert agent_result.runtime_facts.risk_gate_result.final_action == "hold"
    assert agent_result.runtime_facts.risk_evidence.risk_level == "high"
    assert agent_result.runtime_facts.risk_evidence.flags[0][0] == "exposure"


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


def test_gate_disable_attempt_fails_closed():
    ctx = _ctx_with_risk(veto=True)
    result = evaluate_risk_manager_gate(
        ctx,
        current_signal="buy",
        exit_id=EXIT_ORCHESTRATOR_MULTI_AGENT,
        gate_enabled=False,
    )
    assert result.outcome is RiskGateOutcome.REJECT
    assert result.enabled is True
    assert result.final_signal == "hold"
    assert result.fail_closed is True


def test_override_disabled_still_gets_mandatory_warning_on_multi_agent():
    """Regression: AGENT_RISK_OVERRIDE=false must not skip gate evaluation."""
    from src.agent.orchestrator import AgentOrchestrator

    orch = AgentOrchestrator(
        tool_registry=MagicMock(),
        llm_adapter=MagicMock(),
        config=SimpleNamespace(
            agent_risk_override=False,
            risk_gate_profile="balanced",
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

    assert resolved["decision_type"] == "hold"
    assert ctx.get_data("risk_override_applied")["to"] == "hold"
    gate = ctx.meta.get(META_RISK_GATE_RESULT)
    assert gate is not None
    assert gate.outcome is RiskGateOutcome.DOWNGRADE
    assert "风控经理已下调" in resolved["risk_warning"]
