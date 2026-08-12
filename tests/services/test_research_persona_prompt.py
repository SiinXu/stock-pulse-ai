# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Offline tests for research persona resolution and inject (#119, #467)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from src.schemas.investment_framework import (
    InvestmentFrameworkAnalysisContext,
    InvestmentFrameworkContent,
)
from src.schemas.investor_persona import ResearchStanceContent
from src.services.research_persona_prompt import (
    RESEARCH_PERSONA_CONTEXT_KEY,
    RESEARCH_PERSONA_PROMPT_KEY,
    append_research_persona_to_system_prompt,
    enrich_dashboard_research_persona,
    format_research_persona_prompt_section,
    inject_research_persona_into_analysis_context,
    resolve_active_research_persona,
)


def _framework_with_stance() -> InvestmentFrameworkAnalysisContext:
    content = InvestmentFrameworkContent.model_validate(
        {
            "title": "Quality first",
            "free_form_rules": "Prefer durable cash flow",
            "research_stance": {
                "preset_id": "risk_guardian",
                "custom_text": "Prefer drawdown-first language.",
                "preferred_lens_skill_ids": ["persona_tail_risk"],
            },
        }
    )
    return InvestmentFrameworkAnalysisContext(
        framework_id=3,
        framework_version=2,
        content=content,
        updated_at=datetime(2026, 8, 12, tzinfo=timezone.utc),
    )


def test_default_off_when_empty_config_and_no_framework() -> None:
    with patch(
        "src.services.research_persona_prompt.load_active_framework_context_soft",
        return_value=None,
    ):
        persona = resolve_active_research_persona(
            config=SimpleNamespace(agent_research_persona="", agent_research_persona_custom=""),
            report_language="en",
        )
    assert persona.enabled is False
    assert persona.source == "off"
    assert format_research_persona_prompt_section(persona) == ""


def test_config_preset_enables_stance_and_prompt() -> None:
    with patch(
        "src.services.research_persona_prompt.load_active_framework_context_soft",
        return_value=None,
    ):
        persona = resolve_active_research_persona(
            config=SimpleNamespace(
                agent_research_persona="rational_analyst",
                agent_research_persona_custom="",
            ),
            report_language="en",
        )
    assert persona.enabled is True
    assert persona.preset_id == "rational_analyst"
    assert persona.source == "config"
    assert persona.display_name == "Rational Analyst"
    section = format_research_persona_prompt_section(persona, report_language="en")
    assert "Research Persona" in section
    assert "Rational Analyst" in section


def test_request_overrides_config_and_can_force_off() -> None:
    config = SimpleNamespace(
        agent_research_persona="rational_analyst",
        agent_research_persona_custom="",
    )
    with patch(
        "src.services.research_persona_prompt.load_active_framework_context_soft",
        return_value=None,
    ):
        on = resolve_active_research_persona(
            config=config,
            request_context={"research_persona": "risk_guardian"},
            report_language="en",
        )
        off = resolve_active_research_persona(
            config=config,
            request_context={"research_persona": "off"},
            report_language="en",
        )
    assert on.enabled is True
    assert on.preset_id == "risk_guardian"
    assert on.source == "request"
    assert off.enabled is False


def test_framework_research_stance_resolution() -> None:
    ctx = _framework_with_stance()
    persona = resolve_active_research_persona(
        config=SimpleNamespace(agent_research_persona="", agent_research_persona_custom=""),
        framework_context=ctx,
        report_language="zh",
    )
    assert persona.enabled is True
    assert persona.source == "framework"
    assert persona.preset_id == "risk_guardian"
    assert persona.preferred_lens_skill_ids == ["persona_tail_risk"]
    assert persona.has_custom_text is True


def test_inject_analysis_context_default_noop() -> None:
    enhanced: dict = {}
    with patch(
        "src.services.research_persona_prompt.load_active_framework_context_soft",
        return_value=None,
    ):
        inject_research_persona_into_analysis_context(
            enhanced,
            config=SimpleNamespace(agent_research_persona="", agent_research_persona_custom=""),
            report_language="en",
        )
    assert RESEARCH_PERSONA_PROMPT_KEY not in enhanced
    assert RESEARCH_PERSONA_CONTEXT_KEY not in enhanced


def test_inject_analysis_context_writes_prompt_and_label() -> None:
    enhanced: dict = {}
    with patch(
        "src.services.research_persona_prompt.load_active_framework_context_soft",
        return_value=None,
    ):
        inject_research_persona_into_analysis_context(
            enhanced,
            config=SimpleNamespace(
                agent_research_persona="long_term_compounder",
                agent_research_persona_custom="",
            ),
            report_language="en",
        )
    assert RESEARCH_PERSONA_PROMPT_KEY in enhanced
    assert enhanced[RESEARCH_PERSONA_CONTEXT_KEY]["enabled"] is True
    assert enhanced[RESEARCH_PERSONA_CONTEXT_KEY]["preset_id"] == "long_term_compounder"


def test_append_to_system_prompt_idempotent() -> None:
    base = "You are an analyst."
    section = "## Research Persona (optional, data-defined)\n- Active: X\n"
    once = append_research_persona_to_system_prompt(base, persona_prompt=section)
    twice = append_research_persona_to_system_prompt(once, persona_prompt=section)
    assert once.count("Research Persona") == 1
    assert twice == once


def test_enrich_dashboard_label() -> None:
    with patch(
        "src.services.research_persona_prompt.load_active_framework_context_soft",
        return_value=None,
    ):
        dash = enrich_dashboard_research_persona(
            {},
            config=SimpleNamespace(
                agent_research_persona="rational_analyst",
                agent_research_persona_custom="",
            ),
            report_language="en",
        )
    assert dash[RESEARCH_PERSONA_CONTEXT_KEY]["enabled"] is True


def test_research_stance_content_schema_requires_payload() -> None:
    try:
        ResearchStanceContent.model_validate({})
        raised = False
    except Exception:
        raised = True
    assert raised is True


def test_framework_content_accepts_research_stance_only() -> None:
    content = InvestmentFrameworkContent.model_validate(
        {
            "title": "Stance only",
            "research_stance": {
                "custom_text": "Be blunt about missing evidence.",
            },
        }
    )
    assert content.research_stance is not None
    assert content.research_stance.custom_text is not None
