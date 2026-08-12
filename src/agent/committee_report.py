# -*- coding: utf-8 -*-
"""Build the Investment Committee deliberation report section (#545 / #546 / #985).

Produces an additive ``dashboard.committee_deliberation`` payload shaped with
report-strata conventions (facts / gaps / inference / risks / disclaimer) so
templates can render a structured committee section without inventing a second
strategy engine. Synthesis still comes from the existing StrategyEngine path.

All positions, dissent, and divergence points are derived from real specialist
opinions and ``strategy_synthesis`` — never model-authored free text.
Divergence point shape reuses multi-strategy conflict fields so consumers stay
aligned with structured disagreement product contracts (#1205).
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

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
_MAX_TRACE_ITEMS = 12


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


def _skill_id_from_mapping(item: Mapping[str, Any]) -> str:
    for key in ("skill_id", "persona_id", "agent_name"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            text = value.strip()
            if key == "agent_name":
                extracted = extract_skill_id(text)
                return str(extracted or text)
            return text
    return ""


def _opinion_trace_from_skill(
    item: Any,
    *,
    language: str,
) -> Optional[Dict[str, Any]]:
    """Project one strategy_synthesis skill row into a bounded persona stance."""
    if not isinstance(item, Mapping):
        return None
    skill_id = _skill_id_from_mapping(item)
    if not skill_id:
        return None
    confidence = item.get("confidence")
    try:
        confidence_value = float(confidence) if confidence is not None else None
    except (TypeError, ValueError):
        confidence_value = None
    reasoning = item.get("reasoning")
    return {
        "persona_id": skill_id,
        "display_name": persona_display_name(skill_id, language),
        "agent_name": item.get("agent_name") or f"skill_{skill_id}",
        "signal": item.get("signal") if isinstance(item.get("signal"), str) else None,
        "confidence": confidence_value,
        "reasoning_excerpt": _truncate(str(reasoning or "")),
    }


def _build_conclusion(
    strategy_synthesis: Optional[Mapping[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Authoritative committee conclusion from strategy_synthesis only."""
    if not isinstance(strategy_synthesis, Mapping) or not strategy_synthesis:
        return None
    conclusion: Dict[str, Any] = {}
    for key in ("final_signal", "consensus_level", "conflict_severity"):
        value = strategy_synthesis.get(key)
        if isinstance(value, str) and value.strip():
            conclusion[key] = value.strip()
    for key in ("confidence", "conflict_count", "weighted_score"):
        value = strategy_synthesis.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            conclusion[key] = value
    return conclusion or None


def _build_divergence_points(
    strategy_synthesis: Optional[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Deterministic divergence points from synthesis conflicts (#1205-aligned)."""
    if not isinstance(strategy_synthesis, Mapping):
        return []
    points: List[Dict[str, Any]] = []
    conflicts = strategy_synthesis.get("conflicts") or []
    if not isinstance(conflicts, list):
        return []
    for raw in conflicts[:_MAX_TRACE_ITEMS]:
        if not isinstance(raw, Mapping):
            continue
        conflict_type = raw.get("conflict_type")
        if not isinstance(conflict_type, str) or not conflict_type.strip():
            continue
        participants_raw = raw.get("participants") or []
        participants: List[str] = []
        if isinstance(participants_raw, list):
            for item in participants_raw:
                text = str(item or "").strip()
                if text and text not in participants:
                    participants.append(text)
        point: Dict[str, Any] = {
            "source": "strategy_conflict",
            "conflict_type": conflict_type.strip(),
            "severity": (
                str(raw.get("severity")).strip()
                if raw.get("severity") is not None
                else "medium"
            ),
            "participants": participants,
        }
        description_key = raw.get("description_key")
        if isinstance(description_key, str) and description_key.strip():
            point["description_key"] = description_key.strip()
        points.append(point)
    return points


def _derive_status(
    *,
    conclusion: Optional[Mapping[str, Any]],
    members: Sequence[Mapping[str, Any]],
    divergence_points: Sequence[Mapping[str, Any]],
    dissenting: Sequence[Mapping[str, Any]],
) -> str:
    """Compact status for trace export / UI badges (not LLM text)."""
    valid_members = [
        m for m in members if isinstance(m, Mapping) and not m.get("invalid")
    ]
    if not valid_members and not conclusion:
        return "insufficient"
    consensus = str((conclusion or {}).get("consensus_level") or "").lower()
    if consensus == "insufficient":
        return "insufficient"
    if divergence_points or dissenting:
        if consensus in {"low", "medium"}:
            return "split"
        return "deliberated"
    if consensus == "high":
        return "consensus"
    return "deliberated"


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

    synthesis_map: Optional[Dict[str, Any]] = (
        dict(strategy_synthesis) if isinstance(strategy_synthesis, Mapping) else None
    )
    conclusion = _build_conclusion(synthesis_map)
    supporting_opinions = [
        item
        for item in (
            _opinion_trace_from_skill(raw, language=language)
            for raw in (
                (synthesis_map or {}).get("supporting_skills") or []
            )[:_MAX_TRACE_ITEMS]
        )
        if item is not None
    ]
    dissenting_opinions = [
        item
        for item in (
            _opinion_trace_from_skill(raw, language=language)
            for raw in (
                (synthesis_map or {}).get("opposing_skills") or []
            )[:_MAX_TRACE_ITEMS]
        )
        if item is not None
    ]
    if not dissenting_opinions and conclusion and conclusion.get("final_signal"):
        final_signal = str(conclusion.get("final_signal") or "").lower()
        if final_signal and final_signal != "hold":
            for member in members:
                if member.get("invalid"):
                    continue
                member_signal = str(member.get("signal") or "").lower()
                if not member_signal or member_signal == final_signal:
                    continue
                bullish = {"buy", "strong_buy", "add"}
                bearish = {"sell", "strong_sell", "reduce"}
                final_side = (
                    "bull"
                    if final_signal in bullish
                    else "bear"
                    if final_signal in bearish
                    else "other"
                )
                member_side = (
                    "bull"
                    if member_signal in bullish
                    else "bear"
                    if member_signal in bearish
                    else "other"
                )
                if final_side != "other" and member_side != "other" and final_side != member_side:
                    dissenting_opinions.append(
                        {
                            "persona_id": member.get("persona_id"),
                            "display_name": member.get("display_name"),
                            "agent_name": member.get("agent_name"),
                            "signal": member.get("signal"),
                            "confidence": member.get("confidence"),
                            "reasoning_excerpt": member.get("reasoning_excerpt") or "",
                        }
                    )

    divergence_points = _build_divergence_points(synthesis_map)
    status = _derive_status(
        conclusion=conclusion,
        members=members,
        divergence_points=divergence_points,
        dissenting=dissenting_opinions,
    )
    outcome = None
    if conclusion and conclusion.get("final_signal"):
        outcome = str(conclusion["final_signal"])
    elif status:
        outcome = status

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

    if conclusion:
        final_signal = conclusion.get("final_signal")
        consensus = conclusion.get("consensus_level")
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
    for dissent in dissenting_opinions:
        label = dissent.get("display_name") or dissent.get("persona_id")
        signal = dissent.get("signal") or "n/a"
        line = f"{label}: reserved opinion signal={signal}"
        excerpt = dissent.get("reasoning_excerpt") or ""
        if excerpt:
            line = f"{line}; {excerpt}"
        if line not in risks_counter_evidence:
            risks_counter_evidence.append(line)

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
        "conclusion": conclusion,
        "supporting_opinions": supporting_opinions,
        "dissenting_opinions": dissenting_opinions,
        "divergence_points": divergence_points,
        "status": status,
        "outcome": outcome,
        "strategy_synthesis": synthesis_map,
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
