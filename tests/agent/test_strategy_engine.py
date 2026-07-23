# -*- coding: utf-8 -*-
"""Contract tests for the multi-strategy evidence engine (compute + wiring).

Rendering/localization of the synthesis lives in a separate slice; these tests
cover only the deterministic contract: signal normalization, synthesis,
conflict detection, partitioning, orchestrator wiring, and the guarantee that
invalid skill opinions never re-enter the evidence chain.
"""
from __future__ import annotations

import pytest

from src.agent.protocols import (
    AgentContext,
    AgentOpinion,
    is_valid_strategy_signal,
    normalize_strategy_signal,
    strategy_signal_score,
)
from src.agent.disagreement import build_agent_disagreement_summary
from src.agent.orchestrator import AgentOrchestrator
from src.agent.skills.aggregator import AggregationData, SkillAggregator
from src.agent.skills.defaults import SKILL_AGENT_PREFIX
from src.agent.skills.engine import StrategyEngine, StrategyResultStatus
from src.agent.skills.synthesis import (
    ConflictDetector,
    StrategySynthesizer,
    strategy_opinion_from_agent_opinion,
)

P = SKILL_AGENT_PREFIX


def _skill(name: str, signal, confidence: float, **raw) -> AgentOpinion:
    return AgentOpinion(agent_name=f"{P}{name}", signal=signal, confidence=confidence, raw_data=dict(raw))


class TestSignalNormalization:
    @pytest.mark.parametrize(
        ("value", "canonical", "invalid"),
        [
            ("strong buy", "strong_buy", False),
            ("STRONG-BUY", "strong_buy", False),
            ("buy", "buy", False),
            ("neutral", "hold", False),
            ("strong/sell", "strong_sell", False),
            ("", "hold", True),
            (None, "hold", True),
            ("wobble", "hold", True),
        ],
    )
    def test_normalize_strategy_signal(self, value, canonical, invalid):
        got_canonical, got_invalid, _original = normalize_strategy_signal(value)
        assert got_canonical == canonical
        assert got_invalid is invalid

    def test_is_valid_strategy_signal(self):
        assert is_valid_strategy_signal("BUY") is True
        assert is_valid_strategy_signal("wobble") is False

    def test_strategy_signal_score_ordinal_and_unknown(self):
        assert strategy_signal_score("strong_buy") == 5.0
        assert strategy_signal_score("hold") == 3.0
        assert strategy_signal_score("strong_sell") == 1.0
        with pytest.raises(ValueError):
            strategy_signal_score("wobble")


class TestStrategyOpinionNormalization:
    def test_missing_signal_marked_invalid(self):
        op = AgentOpinion(agent_name=f"{P}x", signal="", confidence=0.5)
        strat = strategy_opinion_from_agent_opinion(op)
        assert strat.invalid_signal is True
        assert strat.signal == "hold"

    def test_alias_normalized_and_valid(self):
        op = AgentOpinion(agent_name=f"{P}x", signal="strong buy", confidence=0.5)
        strat = strategy_opinion_from_agent_opinion(op)
        assert strat.invalid_signal is False
        assert strat.signal == "strong_buy"
        assert strat.original_signal == "strong buy"


class TestConflictDetector:
    def test_directional_opposition_high_severity(self):
        ops = [
            strategy_opinion_from_agent_opinion(_skill("a", "strong_buy", 0.8)),
            strategy_opinion_from_agent_opinion(_skill("b", "strong_sell", 0.8)),
        ]
        conflicts = ConflictDetector().detect(ops, final_signal="hold")
        types = {c.conflict_type for c in conflicts}
        assert "directional_opposition" in types
        opposition = next(c for c in conflicts if c.conflict_type == "directional_opposition")
        assert opposition.severity == "high"

    def test_adjustment_contradiction(self):
        ops = [
            strategy_opinion_from_agent_opinion(_skill("a", "buy", 0.6, score_adjustment=16)),
            strategy_opinion_from_agent_opinion(_skill("b", "sell", 0.6, score_adjustment=-16)),
        ]
        conflicts = ConflictDetector().detect(ops, final_signal="hold")
        assert any(c.conflict_type == "adjustment_contradiction" and c.severity == "high" for c in conflicts)

    def test_single_opinion_yields_no_conflict(self):
        ops = [strategy_opinion_from_agent_opinion(_skill("a", "buy", 0.6))]
        assert ConflictDetector().detect(ops, final_signal="buy") == []


class TestSynthesizer:
    def test_consensus_high_when_aligned_and_no_conflict(self):
        ops = [
            strategy_opinion_from_agent_opinion(_skill("a", "buy", 0.8)),
            strategy_opinion_from_agent_opinion(_skill("b", "buy", 0.7)),
            strategy_opinion_from_agent_opinion(_skill("c", "strong_buy", 0.6)),
        ]
        synthesis = StrategySynthesizer().synthesize(
            ops, weighted_score=4.2, final_signal="buy", weighted_confidence=0.7,
            conflicts=[], insufficient_evidence=False, invalid_count=0,
        )
        assert synthesis["consensus_level"] == "high"
        assert synthesis["conflict_severity"] == "none"
        assert [s["skill_id"] for s in synthesis["opposing_skills"]] == []

    def test_consensus_insufficient_when_flagged(self):
        ops = [strategy_opinion_from_agent_opinion(_skill("a", "buy", 0.8))]
        synthesis = StrategySynthesizer().synthesize(
            ops, weighted_score=3.0, final_signal="hold", weighted_confidence=0.0,
            conflicts=[], insufficient_evidence=True, invalid_count=2,
        )
        assert synthesis["consensus_level"] == "insufficient"
        assert synthesis["summary_params"]["invalid_opinion_count"] == 2

    def test_adjust_confidence_dampens_on_conflict(self):
        assert StrategySynthesizer.adjust_confidence(1.0, "high") == pytest.approx(0.85)
        assert StrategySynthesizer.adjust_confidence(1.0, "medium") == pytest.approx(0.93)
        assert StrategySynthesizer.adjust_confidence(1.0, "none") == pytest.approx(1.0)


class TestAggregator:
    def test_calculate_returns_aggregation_data(self):
        ops = [_skill("a", "buy", 0.8), _skill("b", "strong_buy", 0.6)]
        agg = SkillAggregator().calculate(ops)
        assert isinstance(agg, AggregationData)
        assert agg.final_signal in {"buy", "strong_buy"}
        assert agg.insufficient_evidence is False
        assert set(agg.individual_signals) == {f"{P}a", f"{P}b"}

    def test_calculate_none_without_skills(self):
        assert SkillAggregator().calculate([AgentOpinion(agent_name="news", signal="hold", confidence=0.5)]) is None

    def test_all_invalid_is_insufficient(self):
        agg = SkillAggregator().calculate([_skill("a", "wobble", 0.8), _skill("b", "", 0.6)])
        assert agg is not None
        assert agg.insufficient_evidence is True
        assert agg.final_signal == "hold"


class TestStrategyEngine:
    def test_process_consensus_moves_invalid_to_diagnostics(self):
        ops = [
            AgentOpinion(agent_name="news", signal="hold", confidence=0.5),
            _skill("a", "buy", 0.8),
            _skill("b", "strong_buy", 0.7),
            _skill("bad", "wobble", 0.4),
        ]
        result = StrategyEngine().process(ops)
        assert result.status == StrategyResultStatus.CONSENSUS
        assert result.invalid_count == 1
        assert [r["agent_name"] for r in result.invalid_records] == [f"{P}bad"]
        valid_names = {o.agent_name for o in result.valid_skill_opinions}
        assert f"{P}bad" not in valid_names

    def test_process_no_skills(self):
        result = StrategyEngine().process([AgentOpinion(agent_name="news", signal="hold", confidence=0.5)])
        assert result.status == StrategyResultStatus.NO_SKILLS
        assert result.consensus_opinion is None

    def test_process_no_consensus_when_all_invalid(self):
        result = StrategyEngine().process([_skill("a", "wobble", 0.5), _skill("b", "", 0.5)])
        assert result.status == StrategyResultStatus.NO_CONSENSUS
        assert result.invalid_count == 2
        assert result.synthesis_dict["consensus_level"] == "insufficient"


class TestOrchestratorWiring:
    def _orch(self) -> AgentOrchestrator:
        orch = AgentOrchestrator.__new__(AgentOrchestrator)
        orch.strategy_engine = StrategyEngine()
        return orch

    def test_run_engine_keeps_invalid_out_of_evidence_chain(self):
        orch = self._orch()
        ctx = AgentContext(stock_code="600519")
        ctx.opinions = [
            AgentOpinion(agent_name="news", signal="hold", confidence=0.5),
            _skill("a", "buy", 0.8),
            _skill("bad", "???", 0.4),
        ]
        orch._run_strategy_engine(ctx)
        names = [o.agent_name for o in ctx.opinions]
        # Risk: invalid skill opinion must never re-enter the evidence chain.
        assert f"{P}bad" not in names
        assert "skill_consensus" in names
        assert ctx.meta["invalid_opinions"][0]["agent_name"] == f"{P}bad"
        assert isinstance(ctx.get_data("skill_consensus")["strategy_synthesis"], dict)

    def test_partition_fallback_preserves_invalid_without_aggregating(self):
        orch = self._orch()
        ctx = AgentContext(stock_code="X")
        ctx.opinions = [_skill("a", "sell", 0.6), _skill("bad", "zzz", 0.3)]
        orch._apply_partition_fallback(ctx)
        names = [o.agent_name for o in ctx.opinions]
        assert "skill_consensus" not in names
        assert f"{P}bad" not in names
        assert len(ctx.meta["invalid_opinions"]) == 1

    def test_partition_fallback_idempotent_after_full_run(self):
        orch = self._orch()
        ctx = AgentContext(stock_code="X")
        ctx.opinions = [_skill("a", "buy", 0.8), _skill("b", "buy", 0.7)]
        orch._run_strategy_engine(ctx)
        before = list(ctx.opinions)
        orch._apply_partition_fallback(ctx)
        assert ctx.opinions == before  # skipped because consensus already present

    def test_collect_synthesis_prefers_deterministic_over_llm(self):
        orch = self._orch()
        ctx = AgentContext(stock_code="X")
        ctx.opinions = [_skill("a", "buy", 0.8), _skill("b", "buy", 0.7)]
        orch._run_strategy_engine(ctx)
        # An LLM-written synthesis in the dashboard must be ignored.
        collected = orch._collect_strategy_synthesis(ctx, {"strategy_synthesis": {"final_signal": "sell"}})
        assert collected["final_signal"] in {"buy", "strong_buy"}


class TestDisagreementDiagnostics:
    def test_valid_invalid_split_and_diagnostics(self):
        ctx = AgentContext(stock_code="X")
        ctx.opinions = [
            _skill("a", "buy", 0.8),
            _skill("b", "sell", 0.7),
            AgentOpinion(agent_name="ghost", signal="", confidence=0.5),
        ]
        ctx.meta["invalid_opinions"] = [{"agent_name": f"{P}bad", "reason": "unrecognized_signal"}]
        summary = build_agent_disagreement_summary(ctx, risk_override_enabled=True)
        assert summary["valid_opinion_count"] == 2
        assert summary["conflict_type"] == "mixed_directional_signals"
        assert summary["diagnostics"]["invalid_count"] == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
