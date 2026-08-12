# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Resolve and inject optional research personas (#119, #467)."""

from __future__ import annotations

import logging
from typing import Any, Dict, Mapping, Optional

from src.agent.persona_catalog import (
    is_known_research_preset,
    lens_style_references,
    research_preset_display_name,
    research_preset_sections,
    research_preset_style_references,
)
from src.report_language import normalize_report_language
from src.schemas.investment_framework import InvestmentFrameworkAnalysisContext
from src.schemas.investor_persona import ActiveResearchPersona, ResearchStanceContent
from src.services.investment_framework_prompt import load_active_framework_context_soft
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

RESEARCH_PERSONA_PROMPT_KEY = "research_persona_prompt"
RESEARCH_PERSONA_CONTEXT_KEY = "active_research_persona"
META_RESEARCH_PERSONA = "active_research_persona"
META_RESEARCH_PERSONA_PROMPT = "research_persona_prompt"
REQUEST_RESEARCH_PERSONA = "research_persona"
REQUEST_RESEARCH_PERSONA_CUSTOM = "research_persona_custom"
_CUSTOM_TEXT_MAX = 2000
_STYLE_REF_MAX = 8

_DISCLAIMER = {
    "en": (
        "Simulated research stance for learning only. Style-reference labels are not "
        "affiliation, endorsement, or performance claims. Not investment advice."
    ),
    "zh": (
        "模拟研究立场，仅供学习研究。人物/风格标签仅为风格参考，"
        "不代表关联、背书或收益承诺。不构成投资建议。"
    ),
    "ko": (
        "학습/연구용 시뮬레이션 스탠스입니다. 스타일 참조 라벨은 제휴·추천·수익 보장이 아닙니다. "
        "투자 권유가 아닙니다."
    ),
}


def _disclaimer(language: str) -> str:
    lang = normalize_report_language(language)
    return _DISCLAIMER.get(lang, _DISCLAIMER["zh"])


def _clip(text: str, limit: int = _CUSTOM_TEXT_MAX) -> str:
    cleaned = (text or "").strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 1)].rstrip() + "…"


def _normalize_preset(raw: Any) -> Optional[str]:
    if raw is None or isinstance(raw, bool):
        return None
    text = str(raw).strip().lower().replace("-", "_").replace(" ", "_")
    if not text or text in {"off", "none", "false", "0", "disable", "disabled"}:
        return None
    if text in {"on", "true", "1", "enable", "enabled", "default"}:
        return None
    return text if is_known_research_preset(text) else None


def _request_force_off(request_context: Optional[Mapping[str, Any]]) -> bool:
    if not isinstance(request_context, dict) or REQUEST_RESEARCH_PERSONA not in request_context:
        return False
    raw = request_context.get(REQUEST_RESEARCH_PERSONA)
    if raw is False:
        return True
    if isinstance(raw, str) and raw.strip().lower() in {
        "off",
        "none",
        "false",
        "0",
        "disable",
        "disabled",
    }:
        return True
    return False


def _custom_from_request(request_context: Optional[Mapping[str, Any]]) -> Optional[str]:
    if not isinstance(request_context, dict):
        return None
    raw = request_context.get(REQUEST_RESEARCH_PERSONA_CUSTOM)
    if not isinstance(raw, str):
        return None
    cleaned = _clip(raw)
    return cleaned or None


def _custom_from_config(config: Any) -> Optional[str]:
    if config is None:
        return None
    raw = getattr(config, "agent_research_persona_custom", None)
    if not isinstance(raw, str):
        return None
    cleaned = _clip(raw)
    return cleaned or None


def _preset_from_config(config: Any) -> Optional[str]:
    if config is None:
        return None
    return _normalize_preset(getattr(config, "agent_research_persona", None))


def _stance_from_framework(
    framework_context: Optional[InvestmentFrameworkAnalysisContext],
) -> Optional[ResearchStanceContent]:
    if framework_context is None:
        return None
    stance = framework_context.content.research_stance
    return stance if isinstance(stance, ResearchStanceContent) else None


def resolve_active_research_persona(
    *,
    config: Any = None,
    request_context: Optional[Mapping[str, Any]] = None,
    framework_context: Optional[InvestmentFrameworkAnalysisContext] = None,
    report_language: str = "zh",
) -> ActiveResearchPersona:
    lang = normalize_report_language(report_language)
    empty = ActiveResearchPersona(enabled=False, source="off", disclaimer=_disclaimer(lang))
    if _request_force_off(request_context):
        return empty

    preset_id: Optional[str] = None
    custom_text: Optional[str] = None
    preferred_lenses: list[str] = []
    source = "off"

    if isinstance(request_context, dict) and REQUEST_RESEARCH_PERSONA in request_context:
        request_preset = _normalize_preset(request_context.get(REQUEST_RESEARCH_PERSONA))
        request_custom = _custom_from_request(request_context)
        if request_preset or request_custom:
            source = "request"
            preset_id = request_preset
            custom_text = request_custom
    elif isinstance(request_context, dict) and _custom_from_request(request_context):
        source = "request"
        custom_text = _custom_from_request(request_context)

    if source == "off":
        if framework_context is None:
            framework_context = load_active_framework_context_soft()
        stance = _stance_from_framework(framework_context)
        if stance is not None:
            source = "framework"
            preset_id = stance.preset_id
            custom_text = _clip(stance.custom_text or "") or None
            preferred_lenses = list(stance.preferred_lens_skill_ids or [])

    if source == "off":
        config_preset = _preset_from_config(config)
        config_custom = _custom_from_config(config)
        if config_preset or config_custom:
            source = "config"
            preset_id = config_preset
            custom_text = config_custom

    if source == "off" or (not preset_id and not custom_text and not preferred_lenses):
        return empty

    style_refs: list[str] = []
    if preset_id and is_known_research_preset(preset_id):
        display_name = research_preset_display_name(preset_id, lang)
        style_refs.extend(research_preset_style_references(preset_id))
    elif custom_text:
        display_name = "Custom research stance" if lang in {"en", "ko"} else "自定义研究立场"
    else:
        display_name = "Preferred investment lenses" if lang in {"en", "ko"} else "偏好投资视角"

    for skill_id in preferred_lenses:
        for label in lens_style_references(skill_id):
            if label not in style_refs:
                style_refs.append(label)
            if len(style_refs) >= _STYLE_REF_MAX:
                break
        if len(style_refs) >= _STYLE_REF_MAX:
            break

    return ActiveResearchPersona(
        enabled=True,
        preset_id=preset_id,
        display_name=display_name,
        source=source,  # type: ignore[arg-type]
        style_references=style_refs[:_STYLE_REF_MAX],
        preferred_lens_skill_ids=list(preferred_lenses),
        has_custom_text=bool(custom_text),
        disclaimer=_disclaimer(lang),
    )


def format_research_persona_prompt_section(
    persona: Optional[ActiveResearchPersona],
    *,
    custom_text: Optional[str] = None,
    report_language: str = "zh",
) -> str:
    if persona is None or not persona.enabled:
        return ""
    lang = normalize_report_language(report_language)
    english = lang in {"en", "ko"}
    lines = [
        "## Research Persona (optional, data-defined)" if english else "## 研究立场（可选，数据定义）",
        (
            f"- Active: {persona.display_name} (source={persona.source})"
            if english
            else f"- 当前立场：{persona.display_name}（来源={persona.source}）"
        ),
    ]
    if persona.preset_id:
        lines.append(
            f"- Preset id: `{persona.preset_id}`"
            if english
            else f"- 预设 id：`{persona.preset_id}`"
        )
    if persona.style_references:
        joined = ", ".join(persona.style_references)
        lines.append(
            f"- Style references only (not affiliation/endorsement): {joined}"
            if english
            else f"- 风格参考标签（非关联/背书）：{joined}"
        )
    if persona.preferred_lens_skill_ids:
        joined = ", ".join(persona.preferred_lens_skill_ids)
        lines.append(
            f"- Preferred investment-lens Skill ids (opt-in Skills/committee): {joined}"
            if english
            else f"- 偏好投资视角 Skill id（需显式 Skills/委员会启用）：{joined}"
        )
    if persona.preset_id and is_known_research_preset(persona.preset_id):
        sections = research_preset_sections(persona.preset_id)
        for key, heading_en, heading_zh in (
            ("tone_rules", "Tone", "语气"),
            ("risk_framing", "Risk framing", "风险表述"),
            ("conclusion_style", "Conclusion style", "结论风格"),
        ):
            items = sections.get(key) or ()
            if not items:
                continue
            lines.append(f"### {heading_en if english else heading_zh}")
            for item in items:
                lines.append(f"- {item}")
    if custom_text:
        lines.append("### Custom stance" if english else "### 自定义立场")
        lines.append(_clip(custom_text))
    lines.append("### Compliance" if english else "### 合规边界")
    lines.append(f"- {persona.disclaimer}")
    lines.append("")
    return "\n".join(lines)


def _resolve_custom_text_for_prompt(
    *,
    persona: ActiveResearchPersona,
    config: Any,
    request_context: Optional[Mapping[str, Any]],
    framework_context: Optional[InvestmentFrameworkAnalysisContext],
) -> Optional[str]:
    if persona.source == "request":
        return _custom_from_request(request_context)
    if persona.source == "framework":
        if framework_context is None:
            framework_context = load_active_framework_context_soft()
        stance = _stance_from_framework(framework_context)
        return _clip(stance.custom_text or "") if stance else None
    if persona.source == "config":
        return _custom_from_config(config)
    return None


def inject_research_persona_into_analysis_context(
    enhanced_context: Dict[str, Any],
    *,
    config: Any = None,
    request_context: Optional[Mapping[str, Any]] = None,
    framework_context: Optional[InvestmentFrameworkAnalysisContext] = None,
    report_language: str = "zh",
) -> Dict[str, Any]:
    try:
        persona = resolve_active_research_persona(
            config=config,
            request_context=request_context or enhanced_context,
            framework_context=framework_context,
            report_language=report_language,
        )
        if not persona.enabled:
            return enhanced_context
        custom = _resolve_custom_text_for_prompt(
            persona=persona,
            config=config,
            request_context=request_context or enhanced_context,
            framework_context=framework_context,
        )
        prompt = format_research_persona_prompt_section(
            persona, custom_text=custom, report_language=report_language
        )
        if prompt:
            enhanced_context[RESEARCH_PERSONA_PROMPT_KEY] = prompt
        enhanced_context[RESEARCH_PERSONA_CONTEXT_KEY] = persona.model_dump(mode="json")
    except Exception as exc:  # broad-exception: fallback_recorded
        log_safe_exception(
            logger,
            "Research persona inject failed",
            exc,
            error_code="research_persona_inject_failed",
            level=logging.WARNING,
        )
    return enhanced_context


def apply_research_persona_to_agent_context(
    ctx: Any,
    *,
    config: Any = None,
    request_context: Optional[Mapping[str, Any]] = None,
    report_language: Optional[str] = None,
) -> bool:
    meta = getattr(ctx, "meta", None)
    if not isinstance(meta, dict):
        return False
    lang = normalize_report_language(
        report_language
        or meta.get("report_language")
        or (request_context or {}).get("report_language")
        or "zh"
    )
    persona = resolve_active_research_persona(
        config=config, request_context=request_context, report_language=lang
    )
    if not persona.enabled:
        return False
    custom = _resolve_custom_text_for_prompt(
        persona=persona,
        config=config,
        request_context=request_context,
        framework_context=None,
    )
    prompt = format_research_persona_prompt_section(
        persona, custom_text=custom, report_language=lang
    )
    meta[META_RESEARCH_PERSONA] = persona.model_dump(mode="json")
    if prompt:
        meta[META_RESEARCH_PERSONA_PROMPT] = prompt
    return True


def append_research_persona_to_system_prompt(
    system_prompt: str,
    *,
    persona_prompt: Optional[str] = None,
    ctx_meta: Optional[Mapping[str, Any]] = None,
    context: Optional[Mapping[str, Any]] = None,
) -> str:
    section = persona_prompt
    if not section and isinstance(ctx_meta, Mapping):
        raw = ctx_meta.get(META_RESEARCH_PERSONA_PROMPT)
        if isinstance(raw, str) and raw.strip():
            section = raw
    if not section and isinstance(context, Mapping):
        raw = context.get(RESEARCH_PERSONA_PROMPT_KEY)
        if isinstance(raw, str) and raw.strip():
            section = raw
    if not isinstance(section, str) or not section.strip():
        return system_prompt
    base = (system_prompt or "").rstrip()
    if not base:
        return section.strip()
    if section.strip() in base:
        return system_prompt
    return base + "\n\n" + section.strip()


def enrich_dashboard_research_persona(
    dashboard: Optional[Dict[str, Any]],
    *,
    config: Any = None,
    request_context: Optional[Mapping[str, Any]] = None,
    analysis_context: Optional[Mapping[str, Any]] = None,
    agent_meta: Optional[Mapping[str, Any]] = None,
    report_language: str = "zh",
) -> Dict[str, Any]:
    dash: Dict[str, Any] = dict(dashboard) if isinstance(dashboard, dict) else {}
    existing = dash.get(RESEARCH_PERSONA_CONTEXT_KEY)
    if isinstance(existing, dict) and existing.get("enabled"):
        return dash
    for source in (analysis_context, agent_meta):
        if isinstance(source, Mapping):
            payload = source.get(RESEARCH_PERSONA_CONTEXT_KEY) or source.get(META_RESEARCH_PERSONA)
            if isinstance(payload, dict) and payload.get("enabled"):
                dash[RESEARCH_PERSONA_CONTEXT_KEY] = dict(payload)
                return dash
    persona = resolve_active_research_persona(
        config=config,
        request_context=request_context or analysis_context,
        report_language=report_language,
    )
    if persona.enabled:
        dash[RESEARCH_PERSONA_CONTEXT_KEY] = persona.model_dump(mode="json")
    return dash


__all__ = [
    "META_RESEARCH_PERSONA",
    "META_RESEARCH_PERSONA_PROMPT",
    "REQUEST_RESEARCH_PERSONA",
    "REQUEST_RESEARCH_PERSONA_CUSTOM",
    "RESEARCH_PERSONA_CONTEXT_KEY",
    "RESEARCH_PERSONA_PROMPT_KEY",
    "append_research_persona_to_system_prompt",
    "apply_research_persona_to_agent_context",
    "enrich_dashboard_research_persona",
    "format_research_persona_prompt_section",
    "inject_research_persona_into_analysis_context",
    "resolve_active_research_persona",
]
