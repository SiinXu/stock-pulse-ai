# -*- coding: utf-8 -*-
"""Build the Investment Committee deliberation report section (#545).

Produces an additive ``dashboard.committee_deliberation`` payload shaped with
report-strata conventions (facts / gaps / inference / risks / disclaimer) so
templates can render a structured committee section without inventing a second
strategy engine. Synthesis still comes from the existing StrategyEngine path.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from src.agent.committee_presets import (
    COMMITTEE_SECTION_SCHEMA_VERSION,
    persona_display_name,
)
from src.agent.protocols import AgentOpinion
from src.agent.skills.defaults import (
    SKILL_CONSENSUS_AGENT_NAME,
    extract_skill_id,
    is_skill_agent_name,
)
from src.schemas.report_strata import default_disclaimer


_REASONING_EXCERPT_MAX = 240


def _truncate(text: str, limit: int = _REASONING_EXCERPT_MAX) -> str:
    cleaned = (text or "").strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 1)].rstrip() + "…"


def _skill_id_from_opinion(opinion: AgentOpinion) -> str:
    raw = opinion.raw_data if isinstance(opinion.raw_data, dict) else {}
    skill_id = raw.get("skill_id") or extract_skill_id(opinion.agent_name)
    return str(skill_id or opinion.agent_name or "").strip()


def _lens_verdict(opinion: AgentOpinion) -> str:
    raw = opinion.raw_data if isinstance(opinion.raw_data, dict) else {}
    for key in ("lens_verdict", "verdict", "stance"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if opinion.signal:
        return str(opinion.signal)
    return "unknown"


def _member_from_opinion(
    opinion: AgentOpinion,
    *,
    language: str,
) -> Dict[str, Any]:
    skill_id = _skill_id_from_opinion(opinion)
    return {
        "persona_id": skill_id,
        "display_name": persona_display_name(skill_id, language),
        "agent_name": opinion.agent_name,
        "signal": opinion.signal or None,
        "confidence": float(opinion.confidence or 0.0),
        "lens_verdict": _lens_verdict(opinion),
        "reasoning_excerpt": _truncate(str(opinion.reasoning or "")),
        "invalid": False,
        "invalid_reason": None,
    }


def _members_from_opinions(
    opinions: Sequence[AgentOpinion],
    *,
    selected: Sequence[str],
    language: str,
) -> List[Dict[str, Any]]:
    selected_set = set(selected)
    by_id: Dict[str, AgentOpinion] = {}
    for opinion in opinions:
        if opinion.agent_name == SKILL_CONSENSUS_AGENT_NAME:
            continue
        if not is_skill_agent_name(opinion.agent_name):
            continue
        skill_id = _skill_id_from_opinion(opinion)
        if selected and skill_id not in selected_set:
            continue
        by_id[skill_id] = opinion

    members: List[Dict[str, Any]] = []
    order = list(selected) if selected else list(by_id.keys())
    for skill_id in order:
        opinion = by_id.get(skill_id)
        if opinion is None:
            members.append(
                {
                    "persona_id": skill_id,
                    "display_name": persona_display_name(skill_id, language),
                    "agent_name": f"skill_{skill_id}",
                    "signal": None,
                    "confidence": 0.0,
                    "lens_verdict": "missing",
                    "reasoning_excerpt": "",
                    "invalid": True,
                    "invalid_reason": "no_opinion",
                }
            )
            continue
        members.append(_member_from_opinion(opinion, language=language))
    return members


def build_committee_deliberation_section(
    *,
    resolution: Optional[Dict[str, Any]] = None,
    opinions: Optional[Sequence[AgentOpinion]] = None,
    invalid_records: Optional[Sequence[Dict[str, Any]]] = None,
    strategy_synthesis: Optional[Dict[str, Any]] = None,
    language: str = "zh",
) -> Dict[str, Any]:
    """Build the structured committee deliberation payload."""
    resolution = dict(resolution or {})
    selected = [
        str(item).strip()
        for item in (resolution.get("selected") or [])
        if isinstance(item, str) and str(item).strip()
    ]
    invalid_ids = [
        str(item).strip()
        for item in (resolution.get("invalid") or [])
        if isinstance(item, str) and str(item).strip()
    ]
    truncated = [
        str(item).strip()
        for item in (resolution.get("truncated") or [])
        if isinstance(item, str) and str(item).strip()
    ]

    members = _members_from_opinions(
        opinions or [],
        selected=selected,
        language=language,
    )

    invalid_by_agent: Dict[str, Dict[str, Any]] = {}
    for record in invalid_records or []:
        if not isinstance(record, dict):
            continue
        agent_name = str(record.get("agent_name") or "").strip()
        if agent_name:
            invalid_by_agent[agent_name] = record

    for member in members:
        agent_name = str(member.get("agent_name") or "")
        record = invalid_by_agent.get(agent_name)
        if record is None:
            continue
        member["invalid"] = True
        member["invalid_reason"] = str(record.get("reason") or "invalid_signal")
        if member.get("signal") is None:
            member["signal"] = record.get("raw_signal")

    missing_or_conflicts: List[Dict[str, str]] = []
    for persona_id in invalid_ids:
        missing_or_conflicts.append(
            {
                "kind": "missing",
                "description": f"invalid persona skill id: {persona_id}",
            }
        )
    for persona_id in truncated:
        missing_or_conflicts.append(
            {
                "kind": "missing",
                "description": (
                    f"persona truncated beyond max={resolution.get('max_count')}: "
                    f"{persona_id}"
                ),
            }
        )
    for member in members:
        if member.get("invalid"):
            missing_or_conflicts.append(
                {
                    "kind": "missing",
                    "description": (
                        f"persona {member.get('persona_id')}: "
                        f"{member.get('invalid_reason') or 'invalid'}"
                    ),
                }
            )

    model_inference: List[str] = []
    for member in members:
        if member.get("invalid"):
            continue
        excerpt = member.get("reasoning_excerpt") or ""
        label = member.get("display_name") or member.get("persona_id")
        signal = member.get("signal") or "n/a"
        conf = member.get("confidence")
        conf_text = f"{float(conf):.0%}" if isinstance(conf, (int, float)) else "n/a"
        line = f"{label}: signal={signal}, confidence={conf_text}"
        if excerpt:
            line = f"{line}; {excerpt}"
        model_inference.append(line)

    if isinstance(strategy_synthesis, dict) and strategy_synthesis:
        final_signal = strategy_synthesis.get("final_signal")
        consensus = strategy_synthesis.get("consensus_level")
        if final_signal or consensus:
            model_inference.append(
                f"committee synthesis: final_signal={final_signal or 'n/a'}, "
                f"consensus={consensus or 'n/a'}"
            )

    risks_counter_evidence: List[str] = []
    for member in members:
        if member.get("invalid"):
            continue
        if str(member.get("signal") or "").lower() in {"sell", "strong_sell"}:
            risks_counter_evidence.append(
                f"{member.get('display_name')}: bearish stance "
                f"({member.get('signal')})"
            )
        if str(member.get("lens_verdict") or "").lower() in {
            "unfavorable",
            "insufficient evidence",
            "insufficient_evidence",
        }:
            risks_counter_evidence.append(
                f"{member.get('display_name')}: {member.get('lens_verdict')}"
            )

    return {
        "schema_version": COMMITTEE_SECTION_SCHEMA_VERSION,
        "mode": resolution.get("mode") or "investment_committee",
        "source": resolution.get("source") or "default",
        "max_count": resolution.get("max_count"),
        "personas_requested": selected + invalid_ids + truncated,
        "personas_selected": selected,
        "personas_invalid": invalid_ids,
        "personas_truncated": truncated,
        "members": members,
        "strategy_synthesis": (
            dict(strategy_synthesis) if isinstance(strategy_synthesis, dict) else None
        ),
        "missing_or_conflicts": missing_or_conflicts,
        "model_inference": model_inference,
        "risks_counter_evidence": risks_counter_evidence,
        "disclaimer": default_disclaimer(language),
    }


def maybe_build_committee_section_for_context(
    ctx: Any,
    *,
    strategy_synthesis: Optional[Dict[str, Any]] = None,
    language: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Build the committee section when the context is in committee mode."""
    from src.agent.committee_mode import committee_active, get_committee_resolution

    if not committee_active(ctx):
        return None

    resolution = get_committee_resolution(ctx) or {}
    report_language = language or (
        str(ctx.meta.get("report_language") or "zh") if hasattr(ctx, "meta") else "zh"
    )
    invalid_records: List[Dict[str, Any]] = []
    if hasattr(ctx, "meta"):
        raw_invalid = ctx.meta.get("invalid_opinions")
        if isinstance(raw_invalid, list):
            invalid_records = raw_invalid

    opinions = list(getattr(ctx, "opinions", None) or [])
    return build_committee_deliberation_section(
        resolution=resolution,
        opinions=opinions,
        invalid_records=invalid_records,
        strategy_synthesis=strategy_synthesis,
        language=report_language,
    )


__all__ = [
    "build_committee_deliberation_section",
    "maybe_build_committee_section_for_context",
]
