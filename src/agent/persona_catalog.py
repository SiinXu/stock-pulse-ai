# -*- coding: utf-8 -*-
"""Structured catalog for investor lenses and research stances (#119, #467)."""

from __future__ import annotations

from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from src.agent.committee_presets import (
    DEFAULT_COMMITTEE_PERSONA_IDS,
    PERSONA_DISPLAY_NAMES,
    persona_display_name,
)
from src.schemas.investor_persona import RESEARCH_PERSONA_PRESET_IDS

LENS_STYLE_REFERENCES: Dict[str, Tuple[str, ...]] = {
    "persona_value_moat": ("buffett-style", "value-owner-style", "巴菲特风格"),
    "persona_mental_models": ("munger-style", "inversion-checklist-style", "芒格风格"),
    "persona_contrarian_deep_value": (
        "burry-style",
        "contrarian-deep-value-style",
        "逆向深度价值风格",
    ),
    "persona_disruptive_growth": (
        "disruptive-growth-style",
        "innovation-adoption-style",
        "颠覆式成长风格",
    ),
    "persona_tail_risk": ("tail-risk-style", "fragility-stress-style", "尾部风险风格"),
}

_RESEARCH_STANCE_DATA: Dict[str, Dict[str, object]] = {
    "rational_analyst": {
        "display_name": {
            "zh": "理性分析师",
            "en": "Rational Analyst",
            "ko": "이성적 분석가",
        },
        "style_references": ("evidence-first", "calm-rational"),
        "tone_rules": (
            "Stay calm and precise. Prefer measured language over hype.",
            "Separate observations, calculations, inferences, and unknowns.",
            "Lower confidence when evidence is missing, stale, or conflicting.",
        ),
        "risk_framing": (
            "Surface material downside and invalidation conditions beside any opportunity.",
            "Do not sugarcoat weak evidence or structural risks.",
        ),
        "conclusion_style": (
            "End with a falsifiable research stance, key uncertainties, and what would change the view.",
            "Never promise or imply guaranteed returns.",
        ),
    },
    "risk_guardian": {
        "display_name": {
            "zh": "风险守护者",
            "en": "Risk Guardian",
            "ko": "리스크 수호자",
        },
        "style_references": ("risk-first", "stress-and-fragility"),
        "tone_rules": (
            "Lead with what can go wrong before what can go right.",
            "Treat leverage, liquidity, concentration, and governance as first-class evidence.",
            "Prefer conservative language when data is incomplete.",
        ),
        "risk_framing": (
            "Require explicit stress cases and thesis-break conditions.",
            "Flag asymmetric downside and path-dependent failures.",
        ),
        "conclusion_style": (
            "State the risk-adjusted research stance and the conditions that would force exit or pass.",
            "Never imply risk-free opportunity.",
        ),
    },
    "long_term_compounder": {
        "display_name": {
            "zh": "长期复利者",
            "en": "Long-term Compounder",
            "ko": "장기 복리 관점",
        },
        "style_references": ("long-duration-owner", "quality-and-reinvestment"),
        "tone_rules": (
            "Prefer multi-year business quality over short-term price noise.",
            "Evaluate reinvestment runway, capital allocation, and durable economics.",
            "Discount narrative catalysts that do not change owner earnings power.",
        ),
        "risk_framing": (
            "Watch dilution, leverage, competitive erosion, and deteriorating unit economics.",
            "A high-quality business can still be an unattractive price.",
        ),
        "conclusion_style": (
            "Frame conclusions as long-horizon research hypotheses with monitoring criteria.",
            "Do not endorse any named investor's historical returns as a forecast.",
        ),
    },
}


def default_lens_skill_ids() -> List[str]:
    return list(DEFAULT_COMMITTEE_PERSONA_IDS)


def lens_style_references(skill_id: str) -> List[str]:
    return list(LENS_STYLE_REFERENCES.get(skill_id, ()))


def research_preset_ids() -> Tuple[str, ...]:
    return RESEARCH_PERSONA_PRESET_IDS


def is_known_research_preset(preset_id: Optional[str]) -> bool:
    if not preset_id:
        return False
    return str(preset_id).strip() in _RESEARCH_STANCE_DATA


def research_preset_display_name(preset_id: str, language: str = "zh") -> str:
    table = _RESEARCH_STANCE_DATA.get(preset_id) or {}
    names = table.get("display_name") if isinstance(table.get("display_name"), dict) else {}
    key = (language or "zh").strip().lower()
    if key.startswith("en"):
        return str(names.get("en") or preset_id)
    if key.startswith("ko"):
        return str(names.get("ko") or preset_id)
    return str(names.get("zh") or preset_id)


def research_preset_style_references(preset_id: str) -> List[str]:
    table = _RESEARCH_STANCE_DATA.get(preset_id) or {}
    refs = table.get("style_references") or ()
    return [str(item) for item in refs if str(item).strip()]


def research_preset_sections(preset_id: str) -> Mapping[str, Sequence[str]]:
    table = _RESEARCH_STANCE_DATA.get(preset_id) or {}
    out: Dict[str, Sequence[str]] = {}
    for key in ("tone_rules", "risk_framing", "conclusion_style"):
        values = table.get(key) or ()
        out[key] = tuple(str(item) for item in values if str(item).strip())
    return out


def lens_display_name(skill_id: str, language: str = "zh") -> str:
    if skill_id in PERSONA_DISPLAY_NAMES:
        return persona_display_name(skill_id, language)
    return skill_id


__all__ = [
    "LENS_STYLE_REFERENCES",
    "default_lens_skill_ids",
    "is_known_research_preset",
    "lens_display_name",
    "lens_style_references",
    "research_preset_display_name",
    "research_preset_ids",
    "research_preset_sections",
    "research_preset_style_references",
]
