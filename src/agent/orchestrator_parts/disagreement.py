"""Decision-stage disagreement context preparation."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable, Optional

from src.agent.disagreement_handling import (
    apply_disagreement_handling_to_synthesis,
    disagreement_handling_thresholds,
    merge_role_disagreement_into_handling,
    public_disagreement_handling_payload,
)
from src.agent.protocols import AgentContext


DisagreementSummaryBuilder = Callable[..., dict[str, Any]]


def prepare_decision_disagreement_context(
    ctx: AgentContext,
    config: Any,
    *,
    summary_builder: DisagreementSummaryBuilder,
) -> None:
    """Attach bounded disagreement context before the Decision stage."""

    ctx.meta["agent_disagreement_summary"] = summary_builder(
        ctx,
        risk_override_enabled=getattr(config, "agent_risk_override", True),
    )
    if not getattr(config, "agent_disagreement_handling", False):
        return

    high_threshold, medium_threshold = disagreement_handling_thresholds(config)
    role_summary = ctx.meta.get("agent_disagreement_summary")
    if not isinstance(role_summary, dict):
        role_summary = None

    consensus_data = ctx.get_data("skill_consensus")
    synthesis = _strategy_synthesis_from_consensus(consensus_data)
    handling: Optional[dict[str, Any]]
    if synthesis:
        updated = apply_disagreement_handling_to_synthesis(
            synthesis,
            role_summary=role_summary,
            high_confidence_threshold=high_threshold,
            medium_confidence_threshold=medium_threshold,
        )
        handling = updated.get("disagreement_handling")
        _store_updated_consensus(ctx, consensus_data, updated)
        _replace_split_consensus_opinion(ctx, handling, updated)
    else:
        handling = merge_role_disagreement_into_handling(
            None,
            role_summary,
            high_confidence_threshold=high_threshold,
            medium_confidence_threshold=medium_threshold,
        )

    public = public_disagreement_handling_payload(handling)
    if public is not None:
        ctx.meta["disagreement_handling"] = public


def _strategy_synthesis_from_consensus(value: Any) -> Optional[dict[str, Any]]:
    if not isinstance(value, dict):
        return None
    candidate = value.get("strategy_synthesis")
    if isinstance(candidate, dict) and candidate:
        return candidate
    raw_data = value.get("raw_data")
    if isinstance(raw_data, dict):
        candidate = raw_data.get("strategy_synthesis")
        if isinstance(candidate, dict) and candidate:
            return candidate
    return None


def _store_updated_consensus(
    ctx: AgentContext,
    consensus_data: Any,
    updated: dict[str, Any],
) -> None:
    if not isinstance(consensus_data, dict):
        return
    stored = dict(consensus_data)
    stored["strategy_synthesis"] = updated
    if updated.get("final_signal"):
        stored["signal"] = updated["final_signal"]
    if isinstance(updated.get("confidence"), (int, float)):
        stored["confidence"] = updated["confidence"]
    raw_data = stored.get("raw_data")
    if isinstance(raw_data, dict):
        raw_data = dict(raw_data)
        raw_data["strategy_synthesis"] = updated
        stored["raw_data"] = raw_data
    ctx.set_data("skill_consensus", stored)


def _replace_split_consensus_opinion(
    ctx: AgentContext,
    handling: Any,
    updated: dict[str, Any],
) -> None:
    if not (
        isinstance(handling, dict)
        and handling.get("verdict_mode") == "split"
        and updated.get("final_signal")
    ):
        return
    for index, opinion in enumerate(list(ctx.opinions)):
        if getattr(opinion, "agent_name", "") != "skill_consensus":
            continue
        raw_data = dict(opinion.raw_data) if isinstance(opinion.raw_data, dict) else {}
        raw_data["strategy_synthesis"] = updated
        ctx.opinions[index] = replace(
            opinion,
            signal=str(updated["final_signal"]),
            confidence=float(updated.get("confidence") or opinion.confidence or 0.0),
            raw_data=raw_data,
        )
        return


__all__ = ["prepare_decision_disagreement_context"]
