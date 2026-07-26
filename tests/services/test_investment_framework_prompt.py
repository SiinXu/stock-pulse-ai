# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Offline tests for investment framework analysis injection helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from src.schemas.investment_framework import (
    InvestmentFrameworkAnalysisContext,
    InvestmentFrameworkContent,
)
from src.services.investment_framework_prompt import (
    PERSONAL_INVESTMENT_FRAMEWORK_PROMPT_KEY,
    enrich_dashboard_framework_alignment,
    format_investment_framework_prompt_section,
    inject_framework_into_analysis_context,
)


def _context() -> InvestmentFrameworkAnalysisContext:
    content = InvestmentFrameworkContent.model_validate(
        {
            "title": "Quality first",
            "free_form_rules": "Prefer durable cash flow",
            "risk_rules": ["Cap single-name size at 10%"],
            "tracking_criteria": ["Review earnings revisions"],
        }
    )
    return InvestmentFrameworkAnalysisContext(
        framework_id=7,
        framework_version=3,
        content=content,
        updated_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
    )


def test_format_prompt_section_includes_title_and_rules() -> None:
    section = format_investment_framework_prompt_section(_context(), report_language="en")
    assert "Personal Investment Framework" in section
    assert "Quality first" in section
    assert "Prefer durable cash flow" in section
    assert "Cap single-name size at 10%" in section


def test_inject_framework_into_analysis_context_when_active() -> None:
    with patch(
        "src.services.investment_framework_prompt.load_active_framework_context_soft",
        return_value=_context(),
    ):
        enhanced = inject_framework_into_analysis_context({}, report_language="zh")
    assert PERSONAL_INVESTMENT_FRAMEWORK_PROMPT_KEY in enhanced
    assert "个人投资框架" in enhanced[PERSONAL_INVESTMENT_FRAMEWORK_PROMPT_KEY]
    assert enhanced["personal_investment_framework"]["framework_id"] == 7


def test_inject_framework_is_noop_when_not_configured() -> None:
    with patch(
        "src.services.investment_framework_prompt.load_active_framework_context_soft",
        return_value=None,
    ):
        enhanced = inject_framework_into_analysis_context({"code": "600519"}, report_language="zh")
    assert PERSONAL_INVESTMENT_FRAMEWORK_PROMPT_KEY not in enhanced
    assert enhanced == {"code": "600519"}


def test_enrich_dashboard_framework_alignment_fills_slot() -> None:
    dashboard = {
        "report_strata": {
            "schema_version": "report-strata-v1",
            "verified_facts": [],
            "missing_or_conflicts": [],
            "model_inference": [],
            "risks_counter_evidence": [],
            "framework_alignment": {
                "status": "not_configured",
                "summary": "个人投资框架未配置或已停用",
            },
            "disclaimer": "AI生成，仅供参考，不构成投资建议",
        }
    }
    with patch(
        "src.services.investment_framework_prompt.load_active_framework_context_soft",
        return_value=_context(),
    ):
        enriched = enrich_dashboard_framework_alignment(dashboard, report_language="zh")
    alignment = enriched["report_strata"]["framework_alignment"]
    assert alignment["status"] == "partial"
    assert alignment["framework_title"] == "Quality first"
    assert alignment["framework_version"] == 3
    assert alignment["framework_id"] == "7"


def test_format_prompt_clips_oversized_free_form() -> None:
    ctx = _context()
    huge = "A" * 5000
    oversized = InvestmentFrameworkAnalysisContext(
        framework_id=ctx.framework_id,
        framework_version=ctx.framework_version,
        content=InvestmentFrameworkContent.model_validate(
            {
                "title": "Huge",
                "free_form_rules": huge,
            }
        ),
        updated_at=ctx.updated_at,
    )
    section = format_investment_framework_prompt_section(oversized, report_language="en")
    assert huge not in section
    assert "…" in section
    assert len(section) < 4000


def test_enrich_preserves_model_aligned_status() -> None:
    dashboard = {
        "report_strata": {
            "framework_alignment": {
                "status": "aligned",
                "summary": "Model already scored alignment",
                "framework_title": "Quality first",
            }
        }
    }
    with patch(
        "src.services.investment_framework_prompt.load_active_framework_context_soft",
        return_value=_context(),
    ):
        enriched = enrich_dashboard_framework_alignment(dashboard, report_language="en")
    assert enriched["report_strata"]["framework_alignment"]["status"] == "aligned"
    assert (
        enriched["report_strata"]["framework_alignment"]["summary"]
        == "Model already scored alignment"
    )
