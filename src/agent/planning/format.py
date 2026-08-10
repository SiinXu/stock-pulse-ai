# -*- coding: utf-8 -*-
"""Prompt formatting helpers for structured agent plans."""

from __future__ import annotations

from typing import Any, Dict, Optional

from src.agent.planning.config import (
    MAX_PROMPT_PROJECTION_CHARS,
    PLAN_PROPOSAL_CLOSE_MARKER,
    PLAN_PROPOSAL_NOTICE,
    PLAN_PROPOSAL_OPEN_MARKER,
)
from src.agent.planning.types import AgentPlan


def format_plan_for_prompt(plan: AgentPlan) -> str:
    """Project a typed plan inside a bounded, non-authoritative data boundary.

    No runtime consumes this projection in this PR; it is available only to an
    explicit caller that preserves the original user/system authority.

    ``validate_plan_payload`` already rejects oversized and marker-forging plans,
    so the checks below are defense in depth for hand-built ``AgentPlan`` values
    and must stay in sync with the same ``config`` limit authority.
    """
    proposal = plan.to_canonical_json()
    rendered = (
        f"{PLAN_PROPOSAL_OPEN_MARKER}\n"
        f"{PLAN_PROPOSAL_NOTICE}\n"
        f"{proposal}\n"
        f"{PLAN_PROPOSAL_CLOSE_MARKER}"
    )
    if len(rendered) > MAX_PROMPT_PROJECTION_CHARS:
        raise ValueError("plan prompt projection exceeds size limit")
    if (
        rendered.count(PLAN_PROPOSAL_OPEN_MARKER) != 1
        or rendered.count(PLAN_PROPOSAL_CLOSE_MARKER) != 1
    ):
        raise ValueError("plan projection boundary markers are not unique")
    return rendered


def inject_plan_into_task(task: str, plan: AgentPlan) -> str:
    """Return task text with the structured plan section appended."""
    base = (task or "").rstrip()
    plan_text = format_plan_for_prompt(plan)
    if not base:
        return plan_text
    return f"{base}\n\n{plan_text}"


def inject_plan_into_context(
    context: Optional[Dict[str, Any]],
    plan: AgentPlan,
    *,
    planning_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Copy context and attach structured plan metadata (not report schema)."""
    merged: Dict[str, Any] = dict(context or {})
    merged["agent_execution_plan"] = plan.to_dict()
    if planning_meta is not None:
        merged["agent_planning_meta"] = dict(planning_meta)
    return merged
