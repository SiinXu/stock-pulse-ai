# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Data contracts for optional investor / research personas (#119, #467).

Personas are structured data — not free-floating prompt strings. Investment
lenses are ordinary Skill ids under ``strategies/personas/``. Research stances
compose with the personal investment framework. Famous names are style labels
only, never affiliation or return endorsement.
"""

from __future__ import annotations

from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


RESEARCH_PERSONA_PRESET_IDS: tuple[str, ...] = (
    "rational_analyst",
    "risk_guardian",
    "long_term_compounder",
)

ResearchPersonaPresetId = Literal[
    "rational_analyst",
    "risk_guardian",
    "long_term_compounder",
]

ResearchPersonaSource = Literal["off", "config", "request", "framework"]

ACTIVE_RESEARCH_PERSONA_SCHEMA_VERSION: Literal["active-research-persona-v1"] = (
    "active-research-persona-v1"
)

FrameworkSkillId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    ),
]


class ResearchStanceContent(BaseModel):
    """Optional research-tone stance on the personal investment framework."""

    preset_id: Optional[ResearchPersonaPresetId] = None
    custom_text: Optional[
        Annotated[
            str,
            StringConstraints(strip_whitespace=True, min_length=1, max_length=2000),
        ]
    ] = None
    preferred_lens_skill_ids: List[FrameworkSkillId] = Field(
        default_factory=list,
        max_length=5,
    )

    model_config = ConfigDict(
        extra="forbid",
        revalidate_instances="always",
        strict=True,
    )

    @model_validator(mode="after")
    def _require_payload(self) -> "ResearchStanceContent":
        if not any((self.preset_id, self.custom_text, self.preferred_lens_skill_ids)):
            raise ValueError(
                "research_stance requires preset_id, custom_text, or preferred_lens_skill_ids"
            )
        seen: set[str] = set()
        ordered: list[str] = []
        for skill_id in self.preferred_lens_skill_ids:
            if skill_id in seen:
                continue
            seen.add(skill_id)
            ordered.append(skill_id)
        self.preferred_lens_skill_ids = ordered
        return self


class ActiveResearchPersona(BaseModel):
    """Resolved active research persona for prompts and product labels."""

    schema_version: Literal["active-research-persona-v1"] = (
        ACTIVE_RESEARCH_PERSONA_SCHEMA_VERSION
    )
    enabled: bool = False
    preset_id: Optional[str] = None
    display_name: str = ""
    source: ResearchPersonaSource = "off"
    style_references: List[str] = Field(default_factory=list, max_length=10)
    preferred_lens_skill_ids: List[str] = Field(default_factory=list, max_length=5)
    has_custom_text: bool = False
    disclaimer: str = (
        "Simulated research stance for learning only. Style-reference labels are "
        "not affiliation, endorsement, or performance claims. Not investment advice."
    )

    model_config = ConfigDict(
        extra="forbid",
        revalidate_instances="always",
        strict=True,
    )


__all__ = [
    "ACTIVE_RESEARCH_PERSONA_SCHEMA_VERSION",
    "ActiveResearchPersona",
    "RESEARCH_PERSONA_PRESET_IDS",
    "ResearchPersonaPresetId",
    "ResearchPersonaSource",
    "ResearchStanceContent",
]
