# -*- coding: utf-8 -*-
"""Investment Committee persona presets (issue #545).

Curated Skill ids used when committee mode is enabled. Personas are ordinary
Skill definitions under ``strategies/personas/``; this module only names the
default committee pack and report metadata.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

COMMITTEE_MODE_NAME = "investment_committee"
COMMITTEE_SECTION_SCHEMA_VERSION = "committee-deliberation-v1"
COMMITTEE_MAX_PERSONAS = 3

DEFAULT_COMMITTEE_PERSONA_IDS: Tuple[str, ...] = (
    "persona_value_moat",
    "persona_mental_models",
    "persona_contrarian_deep_value",
    "persona_disruptive_growth",
    "persona_tail_risk",
)

PERSONA_DISPLAY_NAMES: Dict[str, Dict[str, str]] = {
    "persona_value_moat": {
        "zh": "价值与护城河",
        "en": "Value & Moat",
        "ko": "가치와 해자",
    },
    "persona_mental_models": {
        "zh": "心智模型与反演",
        "en": "Mental Models",
        "ko": "멘탈 모델",
    },
    "persona_contrarian_deep_value": {
        "zh": "逆向深度价值",
        "en": "Contrarian Deep Value",
        "ko": "역발상 심층가치",
    },
    "persona_disruptive_growth": {
        "zh": "颠覆式成长",
        "en": "Disruptive Growth",
        "ko": "파괴적 성장",
    },
    "persona_tail_risk": {
        "zh": "尾部风险与脆弱性",
        "en": "Tail Risk",
        "ko": "테일 리스크",
    },
}


def default_committee_persona_ids() -> List[str]:
    """Return a fresh list of the default committee persona skill ids."""
    return list(DEFAULT_COMMITTEE_PERSONA_IDS)


def persona_display_name(persona_id: str, language: str = "zh") -> str:
    """Return a localized display name, falling back to the skill id."""
    table = PERSONA_DISPLAY_NAMES.get(persona_id) or {}
    key = (language or "zh").strip().lower()
    if key.startswith("en"):
        return table.get("en") or persona_id
    if key.startswith("ko"):
        return table.get("ko") or persona_id
    return table.get("zh") or persona_id


__all__ = [
    "COMMITTEE_MAX_PERSONAS",
    "COMMITTEE_MODE_NAME",
    "COMMITTEE_SECTION_SCHEMA_VERSION",
    "DEFAULT_COMMITTEE_PERSONA_IDS",
    "PERSONA_DISPLAY_NAMES",
    "default_committee_persona_ids",
    "persona_display_name",
]
