# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Prompt and report-strata helpers for active personal investment framework context."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from src.report_language import normalize_report_language
from src.schemas.investment_framework import InvestmentFrameworkAnalysisContext
from src.schemas.report_strata import (
    FrameworkAlignment,
    default_framework_not_configured_summary,
)
from src.services.investment_framework_context import InvestmentFrameworkContextReader
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

PERSONAL_INVESTMENT_FRAMEWORK_PROMPT_KEY = "personal_investment_framework_prompt"
PERSONAL_INVESTMENT_FRAMEWORK_CONTEXT_KEY = "personal_investment_framework"


def format_investment_framework_prompt_section(
    context: Optional[InvestmentFrameworkAnalysisContext],
    *,
    report_language: str = "zh",
) -> str:
    """Render a bounded read-only framework section for analysis prompts."""
    if context is None:
        return ""
    lang = normalize_report_language(report_language)
    content = context.content
    title = content.title
    version = context.framework_version
    framework_id = context.framework_id

    if lang in {"en", "ko"}:
        lines = [
            "## Personal Investment Framework (read-only)",
            "",
            f"- Title: {title}",
            f"- Framework ID: {framework_id}",
            f"- Content version: {version}",
            "",
            "Use this framework only as research context. Do not treat it as live "
            "trading authority or investment advice.",
            "",
        ]
        if content.description:
            lines.extend(["### Description", content.description, ""])
        if content.free_form_rules:
            lines.extend(["### Free-form rules", content.free_form_rules, ""])
        if content.risk_rules:
            lines.append("### Risk rules")
            lines.extend(f"- {rule}" for rule in content.risk_rules)
            lines.append("")
        if content.tracking_criteria:
            lines.append("### Tracking criteria")
            lines.extend(f"- {item}" for item in content.tracking_criteria)
            lines.append("")
        if content.evaluation_dimensions:
            lines.append("### Evaluation dimensions")
            for dimension in content.evaluation_dimensions:
                criteria = "; ".join(dimension.criteria) if dimension.criteria else ""
                lines.append(
                    f"- {dimension.name} (weight {dimension.weight})"
                    + (f": {criteria}" if criteria else "")
                )
            lines.append("")
        return "\n".join(lines)

    lines = [
        "## 个人投资框架（只读）",
        "",
        f"- 名称：{title}",
        f"- 框架 ID：{framework_id}",
        f"- 内容版本：{version}",
        "",
        "以下内容仅作为研究上下文参考，不构成投资建议，也不授权自动交易。",
        "",
    ]
    if content.description:
        lines.extend(["### 说明", content.description, ""])
    if content.free_form_rules:
        lines.extend(["### 自由规则", content.free_form_rules, ""])
    if content.risk_rules:
        lines.append("### 风险规则")
        lines.extend(f"- {rule}" for rule in content.risk_rules)
        lines.append("")
    if content.tracking_criteria:
        lines.append("### 跟踪条件")
        lines.extend(f"- {item}" for item in content.tracking_criteria)
        lines.append("")
    if content.evaluation_dimensions:
        lines.append("### 评估维度")
        for dimension in content.evaluation_dimensions:
            criteria = "；".join(dimension.criteria) if dimension.criteria else ""
            lines.append(
                f"- {dimension.name}（权重 {dimension.weight}）"
                + (f"：{criteria}" if criteria else "")
            )
        lines.append("")
    return "\n".join(lines)


def framework_alignment_from_context(
    context: Optional[InvestmentFrameworkAnalysisContext],
    *,
    report_language: str = "zh",
) -> FrameworkAlignment:
    """Map active framework context into the report strata alignment slot."""
    lang = normalize_report_language(report_language)
    if context is None:
        return FrameworkAlignment(
            status="not_configured",
            summary=default_framework_not_configured_summary(lang),
        )
    title = context.content.title
    if lang in {"en", "ko"}:
        summary = (
            f"Active personal investment framework “{title}” "
            f"(v{context.framework_version}) is available as read-only research context."
        )
    else:
        summary = (
            f"已加载个人投资框架「{title}」"
            f"（v{context.framework_version}）作为只读研究上下文。"
        )
    return FrameworkAlignment(
        status="partial",
        summary=summary,
        framework_title=title,
        framework_version=context.framework_version,
        framework_id=str(context.framework_id),
    )


def load_active_framework_context_soft() -> Optional[InvestmentFrameworkAnalysisContext]:
    """Read active framework context; fail soft for analysis continuity."""
    try:
        return InvestmentFrameworkContextReader().read()
    except Exception as exc:  # broad-exception: fallback_recorded - analysis must continue without framework
        log_safe_exception(
            logger,
            "Failed to load personal investment framework context",
            exc,
            error_code="investment_framework_context_load_failed",
            level=logging.WARNING,
        )
        return None


def inject_framework_into_analysis_context(
    enhanced_context: Dict[str, Any],
    *,
    report_language: str = "zh",
) -> Dict[str, Any]:
    """Attach prompt section and serializable context when a framework is active."""
    context = load_active_framework_context_soft()
    prompt = format_investment_framework_prompt_section(
        context,
        report_language=report_language,
    )
    if prompt:
        enhanced_context[PERSONAL_INVESTMENT_FRAMEWORK_PROMPT_KEY] = prompt
    if context is not None:
        enhanced_context[PERSONAL_INVESTMENT_FRAMEWORK_CONTEXT_KEY] = context.model_dump(
            mode="json"
        )
    return enhanced_context


def enrich_dashboard_framework_alignment(
    dashboard: Optional[Dict[str, Any]],
    *,
    report_language: str = "zh",
    framework_context: Optional[InvestmentFrameworkAnalysisContext] = None,
) -> Dict[str, Any]:
    """Fill report_strata.framework_alignment from the active framework when present."""
    dash: Dict[str, Any] = dict(dashboard) if isinstance(dashboard, dict) else {}
    strata = dash.get("report_strata")
    if not isinstance(strata, dict):
        return dash
    existing = strata.get("framework_alignment")
    if isinstance(existing, dict):
        status = existing.get("status")
        # Preserve model-produced alignment when the LLM already filled a richer status.
        if status in {"aligned", "conflict"} and (
            existing.get("summary") or existing.get("framework_title")
        ):
            return dash
    ctx = framework_context
    if ctx is None:
        ctx = load_active_framework_context_soft()
    alignment = framework_alignment_from_context(ctx, report_language=report_language)
    strata = dict(strata)
    strata["framework_alignment"] = alignment.model_dump(mode="python")
    dash["report_strata"] = strata
    return dash


__all__ = [
    "PERSONAL_INVESTMENT_FRAMEWORK_CONTEXT_KEY",
    "PERSONAL_INVESTMENT_FRAMEWORK_PROMPT_KEY",
    "enrich_dashboard_framework_alignment",
    "format_investment_framework_prompt_section",
    "framework_alignment_from_context",
    "inject_framework_into_analysis_context",
    "load_active_framework_context_soft",
]
