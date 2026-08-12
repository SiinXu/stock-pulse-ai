# -*- coding: utf-8 -*-
"""Tests for structured disagreement handling, cross-validation, and split verdict."""

from __future__ import annotations

from types import SimpleNamespace

from src.agent.disagreement_handling import (
    ESCALATION_SPLIT,
    VERDICT_SPLIT,
    apply_disagreement_handling_to_synthesis,
    build_disagreement_handling_record,
    public_disagreement_handling_payload,
)
from src.agent.protocols import AgentOpinion, StrategyConflict
from src.agent.skills.engine import StrategyEngine
from src.agent.skills.defaults import build_skill_agent_name
from src.report_language import get_report_labels, normalize_disagreement_handling_payload


def _skill_opinion(skill_id: str, signal: str, confidence: float) -> AgentOpinion:
    return AgentOpinion(
        agent_name=build_skill_agent_name(skill_id),
        signal=signal,
        confidence=confidence,
        reasoning=f"{skill_id} view",
        raw_data={"skill_id": skill_id, "score_adjustment": 0},
    )


def test_high_directional_opposition_escalates_to_split_not_majority():
    synthesis = {
        "final_signal": "buy",
        "weighted_score": 3.8,
        "confidence": 0.72,
        "original_confidence": 0.72,
        "conflict_count": 1,
        "conflict_severity": "high",
        "conflicts": [
            {
                "conflict_type": "directional_opposition",
                "severity": "high",
                "participants": ["momentum", "mean_reversion"],
                "metadata": {
                    "bullish": ["momentum"],
                    "bearish": ["mean_reversion"],
                    "max_bullish_confidence": 0.9,
                    "max_bearish_confidence": 0.88,
                },
            }
        ],
        "supporting_skills": [
            {"skill_id": "momentum", "signal": "buy", "confidence": 0.9},
        ],
        "opposing_skills": [
            {"skill_id": "mean_reversion", "signal": "sell", "confidence": 0.88},
        ],
        "consensus_level": "low",
        "summary_params": {
            "opinion_count": 2,
            "final_signal": "buy",
            "consensus_level": "low",
            "conflict_severity": "high",
            "conflict_count": 1,
        },
    }
    updated = apply_disagreement_handling_to_synthesis(synthesis)
    handling = updated["disagreement_handling"]

    assert handling["high_disagreement"] is True
    assert handling["verdict_mode"] == VERDICT_SPLIT
    assert handling["escalation"] == ESCALATION_SPLIT
    assert handling["resolution_status"] == "unresolved"
    assert handling["policy"]["majority_vote_used"] is False
    # Escalation forces conservative hold — not the pre-escalation majority buy.
    assert updated["final_signal"] == "hold"
    assert handling["policy"]["pre_escalation_final_signal"] == "buy"
    assert updated["confidence"] <= 0.35
    assert updated["consensus_level"] == "low"
    assert handling["points"], "disagreement points must be recorded"
    assert any(p["kind"] == "directional_opposition" for p in handling["points"])


def test_aligned_opinions_do_not_force_split():
    record = build_disagreement_handling_record(
        role_summary={
            "conflict_type": "aligned_bullish",
            "bullish_agents": [{"agent_name": "technical", "signal": "buy", "confidence": 0.8}],
            "bearish_agents": [],
            "neutral_agents": [],
        },
        strategy_synthesis={
            "final_signal": "buy",
            "conflict_severity": "none",
            "conflict_count": 0,
            "conflicts": [],
            "consensus_level": "high",
            "confidence": 0.8,
        },
    )
    assert record["high_disagreement"] is False
    assert record["verdict_mode"] != VERDICT_SPLIT
    assert record["escalation"] != ESCALATION_SPLIT


def test_cross_validation_dual_layer_elevates_to_split():
    role_summary = {
        "conflict_type": "mixed_directional_signals",
        "bullish_agents": [{"agent_name": "technical", "signal": "buy", "confidence": 0.8}],
        "bearish_agents": [{"agent_name": "intel", "signal": "sell", "confidence": 0.78}],
        "neutral_agents": [],
    }
    synthesis = {
        "final_signal": "buy",
        "confidence": 0.7,
        "conflict_severity": "medium",
        "conflict_count": 1,
        "conflicts": [
            {
                "conflict_type": "directional_opposition",
                "severity": "medium",
                "participants": ["momentum", "value"],
                "metadata": {"bullish": ["momentum"], "bearish": ["value"]},
            }
        ],
        "supporting_skills": [{"skill_id": "momentum", "signal": "buy", "confidence": 0.8}],
        "opposing_skills": [{"skill_id": "value", "signal": "sell", "confidence": 0.78}],
        "consensus_level": "medium",
        "summary_params": {},
    }
    updated = apply_disagreement_handling_to_synthesis(synthesis, role_summary=role_summary)
    handling = updated["disagreement_handling"]
    assert handling["cross_validation"]["requested"] is True
    assert handling["cross_validation"]["status"] == "completed"
    assert handling["cross_validation"]["dual_layer_confirmed"] is True
    assert handling["high_disagreement"] is True
    assert updated["final_signal"] == "hold"


def test_strategy_engine_applies_handling_when_enabled():
    engine = StrategyEngine(disagreement_handling_enabled=True)
    opinions = [
        _skill_opinion("momentum", "buy", 0.9),
        _skill_opinion("mean_reversion", "sell", 0.88),
    ]
    result = engine.process(opinions)
    synthesis = result.synthesis_dict
    assert synthesis is not None
    handling = synthesis.get("disagreement_handling")
    assert isinstance(handling, dict)
    assert handling.get("enabled") is True
    assert handling.get("high_disagreement") is True
    assert synthesis["final_signal"] == "hold"
    assert result.consensus_opinion is not None
    assert result.consensus_opinion.signal == "hold"


def test_strategy_engine_default_off_leaves_synthesis_without_handling_block():
    engine = StrategyEngine(disagreement_handling_enabled=False)
    opinions = [
        _skill_opinion("momentum", "buy", 0.9),
        _skill_opinion("mean_reversion", "sell", 0.88),
    ]
    result = engine.process(opinions)
    synthesis = result.synthesis_dict
    assert synthesis is not None
    assert "disagreement_handling" not in synthesis


def test_public_payload_strips_and_forbids_majority_vote_claim():
    raw = build_disagreement_handling_record(
        strategy_synthesis={
            "final_signal": "buy",
            "conflict_severity": "high",
            "conflicts": [
                {
                    "conflict_type": "directional_opposition",
                    "severity": "high",
                    "participants": ["a", "b"],
                    "metadata": {"bullish": ["a"], "bearish": ["b"]},
                }
            ],
            "consensus_level": "low",
            "confidence": 0.7,
        }
    )
    raw["policy"]["majority_vote_used"] = True  # adversarial input
    public = public_disagreement_handling_payload(raw)
    assert public is not None
    assert public["policy"]["majority_vote_used"] is False
    assert public["high_disagreement"] is True


def test_high_disagreement_is_annotated_in_markdown_product():
    """E2E product path: high-disagreement block is present in the report template surface."""
    from jinja2 import Environment, BaseLoader
    from src.report_language import (
        localize_conflict_severity,
        localize_disagreement_resolution,
        localize_disagreement_verdict_mode,
        localize_strategy_signal,
        localize_strategy_skill,
        normalize_disagreement_handling_payload,
    )

    synthesis = apply_disagreement_handling_to_synthesis(
        {
            "final_signal": "buy",
            "weighted_score": 3.9,
            "confidence": 0.8,
            "original_confidence": 0.8,
            "conflict_count": 1,
            "conflict_severity": "high",
            "conflicts": [
                {
                    "conflict_type": "directional_opposition",
                    "severity": "high",
                    "participants": ["momentum", "mean_reversion"],
                    "metadata": {"bullish": ["momentum"], "bearish": ["mean_reversion"]},
                }
            ],
            "supporting_skills": [
                {"skill_id": "momentum", "signal": "buy", "confidence": 0.9},
            ],
            "opposing_skills": [
                {"skill_id": "mean_reversion", "signal": "sell", "confidence": 0.88},
            ],
            "consensus_level": "low",
            "summary_params": {
                "opinion_count": 2,
                "final_signal": "buy",
                "consensus_level": "low",
                "conflict_severity": "high",
                "conflict_count": 1,
            },
        }
    )
    assert synthesis["final_signal"] == "hold"
    assert synthesis["disagreement_handling"]["high_disagreement"] is True

    # Product template fragment matching templates/report_markdown.j2 disagreement block.
    fragment = """
{% set strategy_synthesis = synthesis %}
{% set dashboard = {"disagreement_handling": strategy_synthesis.get("disagreement_handling")} %}
{% set disagreement_handling = normalize_disagreement_handling_payload(strategy_synthesis.get("disagreement_handling") or dashboard.get("disagreement_handling")) %}
{% if disagreement_handling and disagreement_handling.get("high_disagreement") %}
- **⚠️ {{ labels.disagreement_high_banner }}**
- {{ labels.disagreement_verdict_label }}: {{ localize_disagreement_verdict_mode(disagreement_handling.get("verdict_mode"), report_language) }} | {{ labels.disagreement_escalation_label }}: {{ disagreement_handling.get("escalation") }} | {{ labels.disagreement_score_label }}: {{ "%.0f%%" | format((disagreement_handling.get("disagreement_score") or 0) * 100) }}
- {{ labels.disagreement_resolution_label }}: {{ localize_disagreement_resolution(disagreement_handling.get("resolution_status"), report_language) }}
- {{ labels.disagreement_no_majority_note }}
{% if disagreement_handling.get("policy") and disagreement_handling.get("policy").get("pre_escalation_final_signal") %}- {{ labels.disagreement_pre_signal_label }}: {{ localize_strategy_signal(disagreement_handling.get("policy").get("pre_escalation_final_signal"), report_language) }} → {{ labels.disagreement_applied_signal_label }}: {{ localize_strategy_signal(disagreement_handling.get("policy").get("applied_final_signal") or "hold", report_language) }}{% endif %}
{% for point in (disagreement_handling.get("points") or [])[:5] %}
- {{ labels.disagreement_points_label }}: [{{ point.get("source") }}] {{ localize_conflict_severity(point.get("severity", "medium"), report_language) }} / {{ point.get("kind") }}{% if point.get("participants") %}（{% for participant in point.get("participants") %}{{ localize_strategy_skill(participant, report_language) }}{{ "、" if not loop.last else "" }}{% endfor %}）{% endif %}
{% endfor %}
{% endif %}
"""
    labels = get_report_labels("en")
    env = Environment(loader=BaseLoader())
    template = env.from_string(fragment)
    text = template.render(
        synthesis=synthesis,
        labels=labels,
        report_language="en",
        normalize_disagreement_handling_payload=normalize_disagreement_handling_payload,
        localize_disagreement_verdict_mode=localize_disagreement_verdict_mode,
        localize_disagreement_resolution=localize_disagreement_resolution,
        localize_strategy_signal=localize_strategy_signal,
        localize_conflict_severity=localize_conflict_severity,
        localize_strategy_skill=localize_strategy_skill,
    )
    assert labels["disagreement_high_banner"] in text
    assert labels["disagreement_no_majority_note"] in text
    assert labels["disagreement_verdict_split"] in text
    assert "directional_opposition" in text
    # Ensure pre-escalation buy is shown rather than silently erased.
    assert "Buy" in text or "buy" in text.lower()



def test_high_disagreement_is_annotated_in_notification_block():
    from src.notification import _append_disagreement_handling_block

    synthesis = apply_disagreement_handling_to_synthesis(
        {
            "final_signal": "sell",
            "confidence": 0.75,
            "conflict_count": 1,
            "conflict_severity": "high",
            "conflicts": [
                {
                    "conflict_type": "directional_opposition",
                    "severity": "high",
                    "participants": ["a", "b"],
                    "metadata": {"bullish": ["a"], "bearish": ["b"]},
                }
            ],
            "supporting_skills": [],
            "opposing_skills": [],
            "consensus_level": "low",
            "summary_params": {},
        }
    )
    lines: list[str] = []
    labels = get_report_labels("en")
    _append_disagreement_handling_block(lines, synthesis, labels, "en")
    joined = "\n".join(lines)
    assert labels["disagreement_high_banner"] in joined
    assert labels["disagreement_no_majority_note"] in joined
    assert normalize_disagreement_handling_payload(synthesis["disagreement_handling"])[
        "high_disagreement"
    ]
