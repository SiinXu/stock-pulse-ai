# -*- coding: utf-8 -*-
"""Prompt formatting helpers for structured agent plans."""

from __future__ import annotations

from typing import Any, Dict, Optional

from src.agent.planning.types import AgentPlan


def format_plan_for_prompt(plan: AgentPlan) -> str:
    """Render a structured plan as guidance prepended to the user task.

    The existing ReAct loop remains the executor; this text is advisory
    structure so the model prefers the planned tool sequence.
    """
    lines = [
        "[Execution Plan — follow step order; call tools listed for each step before advancing]",
        f"Overall goal: {plan.goal}",
        f"Plan budget: at most {plan.max_steps} plan steps (execution still respects AGENT_MAX_STEPS).",
        "",
    ]
    for step in plan.steps:
        tools = ", ".join(step.expected_tools) if step.expected_tools else "(no specific tool)"
        lines.append(f"Step {step.id}: {step.goal}")
        lines.append(f"  Expected tools: {tools}")
        lines.append(f"  Success criteria: {step.success_criteria}")
    lines.append("")
    lines.append(
        "After all plan steps succeed, produce the final decision-dashboard JSON. "
        "Do not invent tools that are not available. If a planned tool is unavailable, "
        "skip it and continue with the next best available evidence."
    )
    return "\n".join(lines)


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
