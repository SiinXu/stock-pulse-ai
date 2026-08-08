# -*- coding: utf-8 -*-
"""Offline tests for Investment Committee mode (#545).

Covers: default-off flag parity, two-persona deliberation section, invalid
persona isolation, truncation policy, and StrategyEngine synthesis of persona
skill opinions without network or real LLM calls.
"""

from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import Any, Dict

from src.agent.committee_mode import (
    META_COMMITTEE_MODE,
    apply_committee_mode,
    is_committee_mode_enabled,
    resolve_committee_personas,
    should_activate_committee,
)
from src.agent.committee_presets import (
    COMMITTEE_MAX_PERSONAS,
    COMMITTEE_SECTION_SCHEMA_VERSION,
    DEFAULT_COMMITTEE_PERSONA_IDS,
)
from src.agent.committee_report import (
    build_committee_deliberation_section,
    maybe_build_committee_section_for_context,
)
from src.agent.orchestrator_parts.dashboard import _DashboardMethods
from src.agent.protocols import AgentContext, AgentOpinion
from src.agent.skills.defaults import SKILL_AGENT_PREFIX
from src.agent.skills.engine import StrategyEngine, StrategyResultStatus
from src.agent.skills.router import SkillRouter
from src.config import Config


P = SKILL_AGENT_PREFIX


def _skill_opinion(
    skill_id: str,
    signal: str,
    confidence: float,
    *,
    reasoning: str = "",
    **raw: Any,
) -> AgentOpinion:
    raw_data = {"skill_id": skill_id, **raw}
    return AgentOpinion(
        agent_name=f"{P}{skill_id}",
        signal=signal,
        confidence=confidence,
        reasoning=reasoning or f"{skill_id} lens",
        raw_data=raw_data,
    )


def _snapshot_context(ctx: AgentContext) -> Dict[str, Any]:
    return {
        "meta": copy.deepcopy(dict(ctx.meta)),
        "opinions": [
            {
                "agent_name": op.agent_name,
                "signal": op.signal,
                "confidence": op.confidence,
                "reasoning": op.reasoning,
                "raw_data": copy.deepcopy(op.raw_data or {}),
            }
            for op in ctx.opinions
        ],
        "data_keys": sorted(ctx.data.keys()),
    }


def test_flag_default_off():
    config = Config.get_instance()
    assert getattr(config, "agent_investment_committee_mode", None) is False
    assert is_committee_mode_enabled(config) is False
    assert is_committee_mode_enabled(None) is False
    assert is_committee_mode_enabled(SimpleNamespace()) is False


def test_flag_off_apply_is_noop_parity():
    """Flag off must not mutate context (byte-identical meta/opinions)."""
    ctx = AgentContext(query="analyze 600519", stock_code="600519")
    ctx.meta["skills_requested"] = []
    ctx.meta["report_language"] = "zh"
    before = _snapshot_context(ctx)

    applied = apply_committee_mode(
        ctx,
        SimpleNamespace(agent_investment_committee_mode=False),
    )
    assert applied is False
    assert _snapshot_context(ctx) == before
    assert maybe_build_committee_section_for_context(ctx) is None


def test_flag_off_skill_router_unchanged():
    """With flag off and no skills_requested, router still uses default path."""
    config = SimpleNamespace(
        agent_investment_committee_mode=False,
        agent_skill_routing="auto",
        agent_skills=[],
    )
    ctx = AgentContext(query="t")
    ctx.meta["skills_requested"] = []
    router = SkillRouter(config=config, skill_manager=None)
    selected = router.select_skills(ctx, max_count=3)
    assert isinstance(selected, list)
    assert all(not sid.startswith("persona_") for sid in selected) or selected == []


def test_request_false_overrides_config_true():
    assert (
        should_activate_committee(
            SimpleNamespace(agent_investment_committee_mode=True),
            {"committee_mode": False},
        )
        is False
    )


def test_personas_request_activates_without_config():
    assert (
        should_activate_committee(
            SimpleNamespace(agent_investment_committee_mode=False),
            {"personas": ["persona_value_moat"]},
        )
        is True
    )


def test_resolve_default_pack_truncated_to_max():
    resolution = resolve_committee_personas(
        None,
        available_skill_ids=list(DEFAULT_COMMITTEE_PERSONA_IDS),
        max_count=COMMITTEE_MAX_PERSONAS,
    )
    assert resolution.source == "default"
    assert len(resolution.selected) == COMMITTEE_MAX_PERSONAS
    assert resolution.selected == list(DEFAULT_COMMITTEE_PERSONA_IDS)[:COMMITTEE_MAX_PERSONAS]
    assert resolution.truncated == list(DEFAULT_COMMITTEE_PERSONA_IDS)[COMMITTEE_MAX_PERSONAS:]
    assert resolution.invalid == []


def test_resolve_invalid_persona_isolated():
    available = {
        "persona_value_moat",
        "persona_mental_models",
        "persona_tail_risk",
    }
    resolution = resolve_committee_personas(
        ["persona_value_moat", "persona_not_real", "persona_mental_models"],
        available_skill_ids=available,
        max_count=3,
        source="request",
    )
    assert resolution.selected == ["persona_value_moat", "persona_mental_models"]
    assert resolution.invalid == ["persona_not_real"]
    assert resolution.truncated == []


def test_resolve_without_catalog_keeps_requested_ids():
    resolution = resolve_committee_personas(
        ["persona_value_moat", "custom_persona"],
        available_skill_ids=None,
        max_count=3,
    )
    assert resolution.selected == ["persona_value_moat", "custom_persona"]
    assert resolution.invalid == []


def test_apply_committee_sets_skills_requested():
    ctx = AgentContext(query="t", stock_code="600519")
    ctx.meta["skills_requested"] = []
    config = SimpleNamespace(agent_investment_committee_mode=True)
    available = list(DEFAULT_COMMITTEE_PERSONA_IDS)
    assert apply_committee_mode(
        ctx,
        config,
        available_skill_ids=available,
    ) is True
    assert ctx.meta[META_COMMITTEE_MODE] is True
    assert ctx.meta["skills_requested"] == list(DEFAULT_COMMITTEE_PERSONA_IDS)[
        :COMMITTEE_MAX_PERSONAS
    ]
    assert ctx.meta["strategies_requested"] == ctx.meta["skills_requested"]
    resolution = ctx.meta["committee_resolution"]
    assert resolution["invalid"] == []
    assert len(resolution["truncated"]) == len(DEFAULT_COMMITTEE_PERSONA_IDS) - COMMITTEE_MAX_PERSONAS


def test_apply_with_two_personas_request():
    ctx = AgentContext(query="t")
    applied = apply_committee_mode(
        ctx,
        SimpleNamespace(agent_investment_committee_mode=False),
        request_context={
            "personas": ["persona_value_moat", "persona_tail_risk"],
        },
        available_skill_ids=list(DEFAULT_COMMITTEE_PERSONA_IDS),
    )
    assert applied is True
    assert ctx.meta["skills_requested"] == [
        "persona_value_moat",
        "persona_tail_risk",
    ]


def test_two_personas_deliberation_and_synthesis():
    opinions = [
        _skill_opinion(
            "persona_value_moat",
            "buy",
            0.8,
            reasoning="Moat looks durable.",
            lens_verdict="favorable",
        ),
        _skill_opinion(
            "persona_tail_risk",
            "sell",
            0.75,
            reasoning="Balance sheet fragile.",
            lens_verdict="unfavorable",
        ),
        AgentOpinion(
            agent_name="technical",
            signal="hold",
            confidence=0.5,
            reasoning="neutral tape",
        ),
    ]
    engine = StrategyEngine()
    result = engine.process(opinions)
    assert result.status == StrategyResultStatus.CONSENSUS
    assert result.synthesis_dict is not None
    assert result.invalid_count == 0

    section = build_committee_deliberation_section(
        resolution={
            "mode": "investment_committee",
            "source": "request",
            "max_count": 3,
            "selected": ["persona_value_moat", "persona_tail_risk"],
            "invalid": [],
            "truncated": [],
        },
        opinions=opinions,
        invalid_records=result.invalid_records,
        strategy_synthesis=result.synthesis_dict,
        language="en",
    )
    assert section["schema_version"] == COMMITTEE_SECTION_SCHEMA_VERSION
    assert len(section["members"]) == 2
    assert section["members"][0]["persona_id"] == "persona_value_moat"
    assert section["members"][0]["signal"] == "buy"
    assert section["members"][1]["persona_id"] == "persona_tail_risk"
    assert section["members"][1]["invalid"] is False
    assert section["strategy_synthesis"]["final_signal"]
    assert section["disclaimer"]
    assert any("Value" in line or "Moat" in line for line in section["model_inference"])
    assert section["risks_counter_evidence"]


def test_invalid_skill_signal_isolated_in_section():
    opinions = [
        _skill_opinion("persona_value_moat", "buy", 0.7),
        _skill_opinion("persona_mental_models", "", 0.4),
    ]
    engine = StrategyEngine()
    result = engine.process(opinions)
    assert result.invalid_count >= 1
    assert len(result.valid_skill_opinions) == 1

    section = build_committee_deliberation_section(
        resolution={
            "selected": ["persona_value_moat", "persona_mental_models"],
            "invalid": [],
            "truncated": [],
            "max_count": 3,
            "source": "request",
        },
        opinions=opinions,
        invalid_records=result.invalid_records,
        strategy_synthesis=result.synthesis_dict,
        language="zh",
    )
    by_id = {m["persona_id"]: m for m in section["members"]}
    assert by_id["persona_value_moat"]["invalid"] is False
    assert by_id["persona_mental_models"]["invalid"] is True
    assert by_id["persona_mental_models"]["invalid_reason"] in {
        "missing_signal",
        "invalid_signal",
        "unrecognized_signal",
    }
    assert section["missing_or_conflicts"]


def test_flag_off_section_builder_is_none():
    """Without committee meta, report builder returns None (finalize stays quiet)."""
    ctx = AgentContext(query="t", stock_code="600519")
    ctx.meta["report_language"] = "zh"
    ctx.opinions = [_skill_opinion("persona_value_moat", "buy", 0.8)]
    assert maybe_build_committee_section_for_context(ctx) is None


def test_section_builder_attaches_when_committee_active():
    ctx = AgentContext(query="t", stock_code="600519")
    apply_committee_mode(
        ctx,
        SimpleNamespace(agent_investment_committee_mode=True),
        request_context={"personas": ["persona_value_moat", "persona_tail_risk"]},
        available_skill_ids=list(DEFAULT_COMMITTEE_PERSONA_IDS),
    )
    ctx.opinions = [
        _skill_opinion("persona_value_moat", "buy", 0.8),
        _skill_opinion("persona_tail_risk", "hold", 0.55),
    ]
    ctx.meta["report_language"] = "en"
    section = maybe_build_committee_section_for_context(
        ctx,
        strategy_synthesis={
            "final_signal": "buy",
            "consensus_level": "medium",
            "conflict_severity": "none",
            "conflict_count": 0,
            "confidence": 0.7,
        },
    )
    assert section is not None
    assert section["schema_version"] == COMMITTEE_SECTION_SCHEMA_VERSION
    assert len(section["members"]) == 2
    assert section["strategy_synthesis"]["final_signal"] == "buy"


def test_build_context_flag_off_parity():
    host = SimpleNamespace(
        config=SimpleNamespace(agent_investment_committee_mode=False),
        skill_manager=None,
    )
    ctx_a = _DashboardMethods._build_context(host, "分析 600519", {"stock_code": "600519"})  # type: ignore[arg-type]
    ctx_b = _DashboardMethods._build_context(host, "分析 600519", {"stock_code": "600519"})  # type: ignore[arg-type]
    assert ctx_a.meta.get(META_COMMITTEE_MODE) is None
    assert ctx_b.meta.get(META_COMMITTEE_MODE) is None
    assert ctx_a.meta.get("skills_requested") == ctx_b.meta.get("skills_requested") == []


def test_build_context_flag_on_injects_personas():
    host = SimpleNamespace(
        config=SimpleNamespace(agent_investment_committee_mode=True),
        skill_manager=None,
    )
    ctx = _DashboardMethods._build_context(  # type: ignore[arg-type]
        host,
        "analyze",
        {"stock_code": "AAPL", "report_language": "en"},
    )
    assert ctx.meta.get(META_COMMITTEE_MODE) is True
    assert len(ctx.meta.get("skills_requested") or []) == COMMITTEE_MAX_PERSONAS
    assert all(
        sid.startswith("persona_") for sid in ctx.meta["skills_requested"]
    )
