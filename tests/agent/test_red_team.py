# -*- coding: utf-8 -*-
"""Tests for the optional adversarial red-team second-opinion stage (Issue #1135)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List

from src.agent.orchestrator import AgentOrchestrator
from src.agent.protocols import (
    AgentContext,
    AgentOpinion,
    StageResult,
    StageStatus,
)
from src.agent.red_team import (
    LIMITATIONS_MERGE_POLICY,
    RED_TEAM_SCHEMA_VERSION,
    RED_TEAM_STAGE_NAME,
    STATUS_COMPLETED,
    STATUS_DATA_UNAVAILABLE,
    STATUS_SKIPPED,
    BoundedRedTeamAgent,
    is_red_team_enabled,
    merge_data_limitations_preserving_existing,
    merge_red_team_findings,
    parse_red_team_output,
    public_red_team_payload,
    resolve_red_team_settings,
    snapshot_decision_identity,
)
from src.agent.runtime.mode_budget import ModeBudgetAccount, ModeBudgetLimits
from src.agent.tools.registry import ToolRegistry
from src.core.config_registry import get_field_definition


STRONG_CLAIM_WEAK_EVIDENCE_JSON = (
    '{"counter_thesis":"The buy thesis overstates thin news flow.",'
    '"challenges":[{"claim":"Strong buy with no corroborating volume",'
    '"weak_evidence":"Only one headline and no tape confirmation",'
    '"severity":"high"}],'
    '"missing_evidence":["independent volume confirmation"],'
    '"suggested_confidence_pressure":"strong"}'
)


class _FakeLLMResponse:
    def __init__(
        self,
        content: str,
        *,
        provider: str = "test",
        model: str = "test-model",
        tokens: int = 10,
        cost_usd: float = 0.002,
    ):
        self.content = content
        self.provider = provider
        self.model = model
        self.usage = {"total_tokens": tokens, "response_cost": cost_usd}


class _ScriptedAdapter:
    def __init__(self, responses: List[str]):
        self._responses = list(responses)
        self.calls = 0
        self._config = SimpleNamespace(agent_red_team_enabled=True)

    def call_text(self, messages, *, temperature=None, max_tokens=None, timeout=None):
        if not self._responses:
            return _FakeLLMResponse("", provider="error")
        content = self._responses.pop(0)
        self.calls += 1
        return _FakeLLMResponse(content)


def _cfg(**kwargs):
    base = dict(agent_red_team_enabled=False, agent_orchestrator_mode="full")
    base.update(kwargs)
    return SimpleNamespace(**base)


def _decision_agent():
    class _Decision:
        agent_name = "decision"
        max_steps = 1
        tool_names: List[str] = []

        def run(self, ctx, **_kwargs):
            ctx.add_opinion(
                AgentOpinion(
                    agent_name="decision",
                    signal="buy",
                    confidence=0.92,
                    reasoning="Strong buy despite thin evidence",
                )
            )
            ctx.set_data("final_dashboard_raw", "primary decision")
            return StageResult(
                stage_name="decision",
                status=StageStatus.COMPLETED,
                meta={"raw_text": "primary decision"},
            )

    return _Decision()


def test_default_off_chat_and_mode_gating():
    ctx = AgentContext(query="x")
    ctx.meta["orchestrator_mode"] = "full"
    assert is_red_team_enabled(_cfg(agent_red_team_enabled=False), ctx) is False
    assert is_red_team_enabled(_cfg(agent_red_team_enabled=True), ctx) is True

    standard = AgentContext(query="x")
    standard.meta["orchestrator_mode"] = "standard"
    assert is_red_team_enabled(_cfg(agent_red_team_enabled=True), standard) is False

    standard.meta["enable_red_team"] = True
    assert is_red_team_enabled(_cfg(agent_red_team_enabled=False), standard) is True

    chat = AgentContext(query="x")
    chat.meta["orchestrator_mode"] = "full"
    chat.meta["response_mode"] = "chat"
    chat.meta["enable_red_team"] = True
    assert is_red_team_enabled(_cfg(agent_red_team_enabled=True), chat) is False


def test_request_override_source():
    ctx = AgentContext(query="x")
    ctx.meta["enable_red_team"] = True
    settings = resolve_red_team_settings(_cfg(agent_red_team_enabled=False), ctx)
    assert settings["enabled"] is True
    assert settings["source"] == "meta"


def test_parse_rejects_missing_extra_and_nonfinite_fields():
    assert parse_red_team_output('{"counter_thesis":"x"}') is None
    assert parse_red_team_output(
        '{"counter_thesis":"x","challenges":[],"missing_evidence":[],'
        '"suggested_confidence_pressure":"strong","unexpected":true}'
    ) is None
    parsed = parse_red_team_output(STRONG_CLAIM_WEAK_EVIDENCE_JSON)
    assert parsed is not None
    assert parsed["suggested_confidence_pressure"] == "strong"
    assert parsed["challenges"][0]["severity"] == "high"


def test_ac1_strong_claim_weak_evidence_produces_challenges():
    adapter = _ScriptedAdapter([STRONG_CLAIM_WEAK_EVIDENCE_JSON])
    agent = BoundedRedTeamAgent(
        tool_registry=SimpleNamespace(),
        llm_adapter=adapter,
        red_team_config=adapter._config,
    )
    ctx = AgentContext(query="Analyze AAPL", stock_code="AAPL")
    ctx.meta["orchestrator_mode"] = "full"
    ctx.add_opinion(
        AgentOpinion(
            agent_name="decision",
            signal="buy",
            confidence=0.95,
            reasoning="Strong buy",
        )
    )
    result = agent.run(ctx)
    record = ctx.meta["red_team"]
    assert result.status == StageStatus.COMPLETED
    assert adapter.calls == 1
    assert record["status"] == STATUS_COMPLETED
    assert record["challenges"]
    assert "thin" in record["challenges"][0]["weak_evidence"].lower() or (
        "headline" in record["challenges"][0]["weak_evidence"].lower()
    )
    assert record["missing_evidence"]
    assert record["suggested_confidence_pressure"] == "strong"
    public = public_red_team_payload(record)
    assert public is not None
    assert public["schema_version"] == RED_TEAM_SCHEMA_VERSION


def test_ac2_merge_does_not_replace_primary_decision_payload():
    payload: Dict[str, Any] = {
        "decision_type": "buy",
        "confidence_level": "high",
        "operation_advice": "buy the dip",
        "risk_warning": "none",
        "dashboard": {"phase_decision": {"data_limitations": ["old gap"]}},
    }
    identity = snapshot_decision_identity(payload)
    record = parse_red_team_output(STRONG_CLAIM_WEAK_EVIDENCE_JSON)
    assert record is not None
    merged = merge_red_team_findings(
        payload,
        {
            "enabled": True,
            "schema_version": RED_TEAM_SCHEMA_VERSION,
            "status": STATUS_COMPLETED,
            **record,
            "budget": {"llm_turns_used": 1, "llm_turns_limit": 1, "tokens_used": 10},
            "degradation": {"present": False, "reasons": []},
            "settings": {"source": "config", "mode": "full"},
        },
    )
    assert snapshot_decision_identity(merged) == identity
    assert merged["decision_type"] == "buy"
    assert merged["confidence_level"] == "high"
    assert merged["operation_advice"] == "buy the dip"
    limitations = merged["dashboard"]["phase_decision"]["data_limitations"]
    assert limitations[0] == "old gap"
    assert any("red-team challenge" in item for item in limitations)
    assert any("missing evidence" in item for item in limitations)
    assert "Red-team:" in merged["risk_warning"]
    assert merged["risk_warning"].startswith("none")
    assert merged["dashboard"]["red_team"]["status"] == STATUS_COMPLETED
    merge_stats = merged["dashboard"]["red_team"]["data_limitations_merge"]
    assert merge_stats["policy"] == LIMITATIONS_MERGE_POLICY
    assert merge_stats["preserved_existing"] == 1
    assert merge_stats["appended"] >= 1
    assert merge_stats["omitted"] == 0


def _completed_record(parsed: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "enabled": True,
        "schema_version": RED_TEAM_SCHEMA_VERSION,
        "status": STATUS_COMPLETED,
        **parsed,
        "budget": {"llm_turns_used": 1, "llm_turns_limit": 1, "tokens_used": 10},
        "degradation": {"present": False, "reasons": []},
        "settings": {"source": "config", "mode": "full"},
    }


def test_full_cap_preserves_primary_limitations_and_records_overflow():
    existing = [f"primary limitation {index:02d}" for index in range(1, 13)]
    payload: Dict[str, Any] = {
        "decision_type": "buy",
        "confidence_level": "high",
        "operation_advice": "buy the dip",
        "risk_warning": "phase risk",
        "dashboard": {"phase_decision": {"data_limitations": list(existing)}},
    }
    identity = snapshot_decision_identity(payload)
    parsed = parse_red_team_output(STRONG_CLAIM_WEAK_EVIDENCE_JSON)
    assert parsed is not None
    merged = merge_red_team_findings(payload, _completed_record(parsed))
    limitations = merged["dashboard"]["phase_decision"]["data_limitations"]
    assert snapshot_decision_identity(merged) == identity
    assert limitations == existing
    assert limitations[0] == "primary limitation 01"
    assert limitations[-1] == "primary limitation 12"
    assert not any(item.startswith("red-team ") for item in limitations)
    public = merged["dashboard"]["red_team"]
    assert public["challenges"]
    assert public["missing_evidence"]
    merge_stats = public["data_limitations_merge"]
    assert merge_stats["policy"] == LIMITATIONS_MERGE_POLICY
    assert merge_stats["cap"] == 12
    assert merge_stats["preserved_existing"] == 12
    assert merge_stats["appended"] == 0
    assert merge_stats["omitted"] >= 1
    assert merge_stats["omitted_items"]
    assert any("red-team" in item for item in merge_stats["omitted_items"])
    assert merged["decision_type"] == "buy"
    assert merged["confidence_level"] == "high"
    assert merged["operation_advice"] == "buy the dip"
    assert merged["risk_warning"].startswith("phase risk")


def test_limitations_merge_dedupes_and_fills_remaining_slots_only():
    existing = [f"primary {index}" for index in range(1, 11)] + ["red-team challenge: already present"]
    additions = [
        "red-team challenge: already present",
        "red-team missing evidence: volume",
        "red-team suggested confidence pressure: strong",
    ]
    merged, stats = merge_data_limitations_preserving_existing(existing, additions)
    assert merged[:10] == existing[:10]
    assert "red-team challenge: already present" in merged
    assert "red-team missing evidence: volume" in merged
    assert len(merged) == 12
    assert stats["preserved_existing"] == 11
    assert stats["appended"] == 1
    assert stats["omitted"] == 1
    assert stats["omitted_items"] == ["red-team suggested confidence pressure: strong"]


def test_ac2_orchestrator_keeps_primary_decision_text(monkeypatch):
    adapter = _ScriptedAdapter([STRONG_CLAIM_WEAK_EVIDENCE_JSON])
    config = SimpleNamespace(
        agent_critic_enabled=False,
        agent_red_team_enabled=True,
        agent_mode_budget_enabled=False,
        agent_orchestrator_timeout_s=0,
        agent_risk_override=True,
        debate_enabled=False,
    )
    orchestrator = AgentOrchestrator(
        tool_registry=ToolRegistry(),
        llm_adapter=adapter,
        config=config,
        mode="full",
    )
    monkeypatch.setattr(orchestrator, "_build_agent_chain", lambda _ctx: [_decision_agent()])
    ctx = AgentContext(query="Analyze AAPL", stock_code="AAPL")
    result = orchestrator._execute_pipeline(ctx, parse_dashboard=False)
    assert result.success is True
    assert ctx.data["final_dashboard_raw"] == "primary decision"
    assert ctx.meta["red_team"]["status"] == STATUS_COMPLETED
    assert adapter.calls == 1
    decision = next(op for op in ctx.opinions if op.agent_name == "decision")
    assert decision.signal == "buy"
    assert decision.reasoning == "Strong buy despite thin evidence"


def test_ac3_zero_remaining_turns_skips_llm_and_keeps_primary(monkeypatch):
    adapter = _ScriptedAdapter([STRONG_CLAIM_WEAK_EVIDENCE_JSON])
    config = SimpleNamespace(
        agent_critic_enabled=False,
        agent_red_team_enabled=True,
        agent_mode_budget_enabled=True,
        agent_orchestrator_timeout_s=0,
        agent_risk_override=True,
        debate_enabled=False,
    )
    orchestrator = AgentOrchestrator(
        tool_registry=ToolRegistry(),
        llm_adapter=adapter,
        config=config,
        mode="full",
    )
    monkeypatch.setattr(orchestrator, "_build_agent_chain", lambda _ctx: [_decision_agent()])
    ctx = AgentContext(query="Analyze AAPL", stock_code="AAPL")
    ctx.meta["mode_budget_account"] = ModeBudgetAccount(
        limits=ModeBudgetLimits(mode="full", enabled=True, max_llm_turns=10),
        llm_turns=10,
    )
    result = orchestrator._execute_pipeline(ctx, parse_dashboard=False)
    assert result.success is True
    assert result.failure_reason is None
    assert ctx.data["final_dashboard_raw"] == "primary decision"
    assert adapter.calls == 0
    record = ctx.meta["red_team"]
    assert record["status"] == STATUS_SKIPPED
    assert record["budget"]["terminated_reason"] == "budget_skip"
    assert record["challenges"] == []


def test_provider_failure_is_data_unavailable_without_challenges():
    adapter = _ScriptedAdapter([])
    agent = BoundedRedTeamAgent(
        tool_registry=SimpleNamespace(),
        llm_adapter=adapter,
        red_team_config=adapter._config,
    )
    ctx = AgentContext(query="x", stock_code="AAPL")
    result = agent.run(ctx)
    record = ctx.meta["red_team"]
    assert result.status == StageStatus.FAILED
    assert record["status"] == STATUS_DATA_UNAVAILABLE
    assert record["challenges"] == []
    assert not any(op.agent_name == RED_TEAM_STAGE_NAME for op in ctx.opinions)


def test_standard_mode_does_not_insert_without_override(monkeypatch):
    adapter = _ScriptedAdapter([STRONG_CLAIM_WEAK_EVIDENCE_JSON])
    config = SimpleNamespace(
        agent_critic_enabled=False,
        agent_red_team_enabled=True,
        agent_mode_budget_enabled=False,
        agent_orchestrator_timeout_s=0,
        agent_risk_override=True,
        debate_enabled=False,
    )
    orchestrator = AgentOrchestrator(
        tool_registry=ToolRegistry(),
        llm_adapter=adapter,
        config=config,
        mode="standard",
    )
    monkeypatch.setattr(orchestrator, "_build_agent_chain", lambda _ctx: [_decision_agent()])
    ctx = AgentContext(query="Analyze AAPL", stock_code="AAPL")
    result = orchestrator._execute_pipeline(ctx, parse_dashboard=False)
    assert result.success is True
    assert adapter.calls == 0
    assert "red_team" not in ctx.meta


def test_registry_field_default_off():
    field = get_field_definition("AGENT_RED_TEAM_ENABLED")
    assert field["default_value"] == "false"
    assert field["data_type"] == "boolean"


def test_append_red_team_lines_renders_enabled_payload() -> None:
    from src.report_language import append_red_team_lines

    lines: List[str] = []
    append_red_team_lines(
        lines,
        {
            "red_team": {
                "enabled": True,
                "status": "completed",
                "counter_thesis": "Overconfident buy",
                "suggested_confidence_pressure": "strong",
                "challenges": [
                    {
                        "claim": "Strong buy",
                        "weak_evidence": "thin tape",
                        "severity": "high",
                    }
                ],
                "missing_evidence": ["volume"],
            }
        },
        {},
    )
    assert any("Red-Team Second Opinion" in line for line in lines)
    assert any("Overconfident buy" in line for line in lines)
    assert any("thin tape" in line for line in lines)
    skipped: List[str] = []
    append_red_team_lines(skipped, {"red_team": {"enabled": False}}, {})
    assert skipped == []
    overflow: List[str] = []
    append_red_team_lines(
        overflow,
        {
            "red_team": {
                "enabled": True,
                "status": "completed",
                "suggested_confidence_pressure": "strong",
                "challenges": [],
                "missing_evidence": ["volume"],
                "data_limitations_merge": {
                    "cap": 12,
                    "policy": LIMITATIONS_MERGE_POLICY,
                    "preserved_existing": 12,
                    "appended": 0,
                    "omitted": 3,
                    "omitted_items": ["red-team missing evidence: volume"],
                },
            }
        },
        {},
    )
    assert any("omitted 3 red-team gap" in line for line in overflow)
