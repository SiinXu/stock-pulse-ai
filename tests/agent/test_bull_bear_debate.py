# -*- coding: utf-8 -*-
"""Tests for optional structured Bull-Bear debate stage (Issue #117)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from src.agent.bull_bear_debate import (
    DEBATE_SCHEMA_VERSION,
    DEBATE_STAGE_NAME,
    BoundedBullBearDebateAgent,
    build_contention_point,
    decision_signal_debate_metadata,
    empty_debate_record,
    extract_contention_points,
    is_debate_enabled,
    parse_stance_output,
    parse_synthesis_output,
    public_debate_payload,
    resolve_debate_settings,
    synthesize_debate_deterministic,
)
from src.agent.protocols import AgentContext, AgentOpinion
from src.core.config_registry import get_field_definition
from src.services.decision_signal_payload import build_decision_signal_payload_from_report


class _FakeLLMResponse:
    def __init__(self, content: str, *, provider: str = "test", model: str = "test-model", tokens: int = 10):
        self.content = content
        self.provider = provider
        self.model = model
        self.usage = {"total_tokens": tokens}


class _ScriptedAdapter:
    def __init__(self, responses: List[str]):
        self._responses = list(responses)
        self.calls = 0
        self._config = SimpleNamespace(
            debate_enabled=True,
            debate_max_rounds=1,
            debate_temperature=0.4,
            debate_model="",
        )

    def call_text(self, messages, *, temperature=None, max_tokens=None, timeout=None):
        if not self._responses:
            return _FakeLLMResponse("", provider="error")
        content = self._responses.pop(0)
        self.calls += 1
        return _FakeLLMResponse(content)


def _cfg(**kwargs):
    base = dict(
        debate_enabled=False,
        debate_max_rounds=2,
        debate_temperature=0.4,
        debate_model="",
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_default_off_and_chat_gated():
    ctx = AgentContext(query="x")
    assert is_debate_enabled(_cfg(debate_enabled=False), ctx) is False
    assert is_debate_enabled(_cfg(debate_enabled=True), ctx) is True
    ctx.meta["response_mode"] = "chat"
    assert is_debate_enabled(_cfg(debate_enabled=True), ctx) is False


def test_request_override_enable_and_rounds():
    ctx = AgentContext(query="x")
    ctx.meta["enable_debate"] = True
    ctx.meta["debate_max_rounds"] = 3
    settings = resolve_debate_settings(_cfg(debate_enabled=False, debate_max_rounds=1), ctx)
    assert settings["enabled"] is True
    assert settings["max_rounds"] == 3
    assert settings["source"] == "meta"


def test_parse_stance_and_synthesis():
    bull = parse_stance_output(
        '{"stance":"buy","confidence":0.8,"arguments":["momentum"],"evidence_refs":["macd"],"contention_topics":["valuation"]}',
        side="bull",
    )
    assert bull is not None
    assert bull["stance"] == "buy"
    synth = parse_synthesis_output(
        '{"final_lean":"hold","confidence":0.4,"summary":"opposed","winner":"draw","resolution_status":"unresolved","key_contentions":["valuation"]}'
    )
    assert synth is not None
    assert synth["majority_vote_used"] is False
    assert synth["resolution_status"] == "unresolved"


def test_contention_points_align_with_disagreement_vocabulary():
    points = extract_contention_points(
        round_index=1,
        bull={"stance": "buy", "confidence": 0.9, "arguments": ["A"], "contention_topics": ["growth"]},
        bear={"stance": "sell", "confidence": 0.85, "arguments": ["B"], "contention_topics": ["growth"]},
    )
    assert points
    assert any(p["kind"] == "directional_opposition" for p in points)
    for point in points:
        assert point["source"] == "debate"
        assert "participants" in point
        assert "sides" in point
        assert point["summary_key"].startswith("debate.point.")


def test_deterministic_synthesis_no_majority_on_opposition():
    rounds = [
        {
            "round": 1,
            "bull": {"stance": "buy", "confidence": 0.9},
            "bear": {"stance": "sell", "confidence": 0.88},
            "incomplete": False,
        }
    ]
    points = [
        build_contention_point(topic="directional_opposition", round_index=1, kind="directional_opposition", severity="high")
    ]
    synthesis = synthesize_debate_deterministic(rounds, contention_points=points)
    assert synthesis["final_lean"] == "hold"
    assert synthesis["majority_vote_used"] is False
    assert synthesis["resolution_status"] == "unresolved"


def test_public_payload_and_decision_signal_metadata():
    record = empty_debate_record(
        status="completed",
        settings={"max_rounds": 2, "temperature": 0.4, "model": "", "source": "config"},
    )
    record["status"] = "completed"
    record["rounds_completed"] = 1
    record["synthesis"]["summary"] = "Bull vs Bear remain split"
    record["contention_points"] = [
        build_contention_point(topic="valuation", round_index=1)
    ]
    record["disagreement_points"] = record["contention_points"]
    public = public_debate_payload(record)
    assert public is not None
    assert public["schema_version"] == DEBATE_SCHEMA_VERSION
    meta = decision_signal_debate_metadata(public)
    assert meta["debate_rounds"] == 1
    assert meta["debate_summary"]


def test_agent_run_produces_non_silent_record_and_opinion():
    bull_json = '{"stance":"buy","confidence":0.8,"arguments":["trend up"],"evidence_refs":["ma"],"contention_topics":["valuation"]}'
    bear_json = '{"stance":"sell","confidence":0.75,"arguments":["rich valuation"],"evidence_refs":["pe"],"contention_topics":["valuation"]}'
    synth_json = '{"final_lean":"hold","confidence":0.4,"summary":"split views","winner":"draw","resolution_status":"unresolved","key_contentions":["valuation"]}'
    adapter = _ScriptedAdapter([bull_json, bear_json, synth_json])
    agent = BoundedBullBearDebateAgent(
        tool_registry=SimpleNamespace(),
        llm_adapter=adapter,
        debate_config=adapter._config,
    )
    ctx = AgentContext(query="analyze 600519")
    ctx.stock_code = "600519"
    ctx.add_opinion(AgentOpinion(agent_name="technical", signal="buy", confidence=0.7, reasoning="up"))
    result = agent.run(ctx)
    assert result.success or result.status.value in {"completed", "failed"}
    record = ctx.meta.get("bull_bear_debate")
    assert isinstance(record, dict)
    assert record.get("enabled") is True
    assert record.get("schema_version") == DEBATE_SCHEMA_VERSION
    assert record.get("rounds_completed") >= 1
    assert any(op.agent_name == DEBATE_STAGE_NAME for op in ctx.opinions)
    public = public_debate_payload(record)
    assert public is not None
    assert public["synthesis"]["majority_vote_used"] is False


def test_graceful_degradation_on_llm_failure_still_records():
    adapter = _ScriptedAdapter([])  # all calls error
    adapter._config.debate_max_rounds = 1
    agent = BoundedBullBearDebateAgent(
        tool_registry=SimpleNamespace(),
        llm_adapter=adapter,
        debate_config=adapter._config,
    )
    ctx = AgentContext(query="x")
    ctx.stock_code = "AAPL"
    result = agent.run(ctx)
    record = ctx.meta.get("bull_bear_debate")
    assert record is not None
    assert record["enabled"] is True
    # Failed mid-debate still leaves a product record (not silent drop).
    assert record["status"] in {"failed", "degraded", "budget_exhausted"}


def test_mode_budget_turn_accounting_when_present():
    class _Account:
        def __init__(self):
            self.turns = 0
            self.breach = None

        def check(self):
            return self.breach

        def record_llm_turn(self, *, tokens=0, cost_usd=0.0, model=""):
            self.turns += 1
            return None

    bull_json = '{"stance":"buy","confidence":0.7,"arguments":["a"],"evidence_refs":[],"contention_topics":[]}'
    bear_json = '{"stance":"hold","confidence":0.5,"arguments":["b"],"evidence_refs":[],"contention_topics":[]}'
    synth_json = '{"final_lean":"buy","confidence":0.55,"summary":"mild bull","winner":"bull","resolution_status":"partially_resolved","key_contentions":[]}'
    adapter = _ScriptedAdapter([bull_json, bear_json, synth_json])
    agent = BoundedBullBearDebateAgent(
        tool_registry=SimpleNamespace(),
        llm_adapter=adapter,
        debate_config=adapter._config,
    )
    ctx = AgentContext(query="x")
    account = _Account()
    ctx.meta["mode_budget_account"] = account
    agent.run(ctx)
    assert account.turns >= 2  # bull + bear at minimum


def test_registry_fields_present():
    field = get_field_definition("DEBATE_ENABLED")
    assert field["default_value"] == "false"
    assert get_field_definition("DEBATE_MAX_ROUNDS")["validation"]["max"] == 3


def test_decision_signal_payload_includes_debate_metadata():
    class _Result:
        success = True
        code = "600519"
        name = "Moutai"
        sentiment_score = 55
        operation_advice = "hold"
        action = "hold"
        decision_type = "hold"
        confidence_level = "medium"
        report_language = "en"
        analysis_summary = "hold for now"
        buy_reason = None
        key_points = ["debate"]
        risk_warning = "none"
        risk_gate_result = None
        dashboard = {
            "bull_bear_debate": {
                "enabled": True,
                "schema_version": DEBATE_SCHEMA_VERSION,
                "status": "completed",
                "max_rounds": 2,
                "rounds_completed": 1,
                "rounds": [],
                "contention_points": [],
                "disagreement_points": [],
                "synthesis": {
                    "final_lean": "hold",
                    "confidence": 0.4,
                    "summary": "Debate summary for signal",
                    "winner": "draw",
                    "resolution_status": "unresolved",
                    "majority_vote_used": False,
                    "key_contentions": [],
                },
                "budget": {"llm_turns_used": 3, "llm_turns_limit": 3, "tokens_used": 0, "terminated_reason": None},
                "degradation": {"present": False, "reasons": []},
                "settings": {"temperature": 0.4, "model": "", "source": "config"},
            }
        }

    payload = build_decision_signal_payload_from_report(
        _Result(),
        context_snapshot={},
        portfolio_context=None,
        source_report_id=1,
        trace_id="trace-debate-1",
        query_source="test",
        report_type="manual",
        profile_source="auto_default",
    )
    assert payload is not None
    metadata = payload.get("metadata") or {}
    assert metadata.get("debate_summary") == "Debate summary for signal"
    assert metadata.get("debate_rounds") == 1


def test_analysis_service_applies_debate_request_overrides(monkeypatch):
    """Per-request enable_debate/debate_max_rounds must mutate a config copy only."""
    import copy
    from types import SimpleNamespace
    from src.services.analysis_service import AnalysisService

    calls = {}

    class _FakePipeline:
        def __init__(self, config=None, **kwargs):
            calls["config"] = config
            calls["kwargs"] = kwargs

        def process_single_stock(self, **kwargs):
            return None

    shared = SimpleNamespace(
        debate_enabled=False,
        debate_max_rounds=2,
        report_language="zh",
        decision_memory_enabled=False,
        validate=lambda: [],
    )
    # analysis_service imports get_config inside method
    monkeypatch.setattr("src.config.get_config", lambda: shared)
    monkeypatch.setattr("src.core.pipeline.StockAnalysisPipeline", _FakePipeline)

    service = AnalysisService()
    # Force early return path by making pipeline return None and swallow errors
    try:
        service.analyze_stock(
            stock_code="600519",
            enable_debate=True,
            debate_max_rounds=3,
            send_notification=False,
        )
    except Exception:
        pass

    # Shared singleton must remain unchanged
    assert shared.debate_enabled is False
    assert shared.debate_max_rounds == 2
    # Pipeline received a mutated copy
    cfg = calls.get("config")
    assert cfg is not None
    assert cfg is not shared
    assert cfg.debate_enabled is True
    assert cfg.debate_max_rounds == 3
