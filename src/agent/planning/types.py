# -*- coding: utf-8 -*-
"""Structured plan types for the optional agent planning pre-step."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple


PLAN_SCHEMA_VERSION = "agent-plan-v1"


@dataclass(frozen=True)
class PlanStep:
    """One explicit execution step in a structured agent plan."""

    id: int
    goal: str
    expected_tools: Tuple[str, ...]
    success_criteria: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "goal": self.goal,
            "expected_tools": list(self.expected_tools),
            "success_criteria": self.success_criteria,
        }


@dataclass(frozen=True)
class AgentPlan:
    """Structured plan produced before the existing ReAct execution loop."""

    goal: str
    steps: Tuple[PlanStep, ...]
    max_steps: int
    version: str = PLAN_SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "goal": self.goal,
            "max_steps": self.max_steps,
            "steps": [step.to_dict() for step in self.steps],
        }

    @property
    def step_count(self) -> int:
        return len(self.steps)

    @property
    def expected_tool_names(self) -> Tuple[str, ...]:
        names: List[str] = []
        seen = set()
        for step in self.steps:
            for tool in step.expected_tools:
                if tool not in seen:
                    seen.add(tool)
                    names.append(tool)
        return tuple(names)


@dataclass
class PlanningOutcome:
    """Result of attempting the planning pre-step (applied or degraded)."""

    enabled: bool
    applied: bool
    plan: Optional[AgentPlan] = None
    fallback_reason: Optional[str] = None
    strategy: str = "none"
    replan_attempts: int = 0
    planning_tokens: int = 0
    planning_model: str = ""
    error: Optional[str] = None
    attrs: Dict[str, Any] = field(default_factory=dict)

    def to_metadata(self) -> Dict[str, Any]:
        """Trace-safe metadata (no free-form model reasoning dump)."""
        payload: Dict[str, Any] = {
            "enabled": self.enabled,
            "applied": self.applied,
            "strategy": self.strategy,
            "replan_attempts": self.replan_attempts,
            "planning_tokens": self.planning_tokens,
            "planning_model": self.planning_model,
            "schema_version": PLAN_SCHEMA_VERSION,
        }
        if self.fallback_reason:
            payload["fallback_reason"] = self.fallback_reason
        if self.error:
            payload["error"] = self.error
        if self.plan is not None:
            payload["plan"] = self.plan.to_dict()
            payload["step_count"] = self.plan.step_count
            payload["expected_tools"] = list(self.plan.expected_tool_names)
        if self.attrs:
            payload["attrs"] = dict(self.attrs)
        return payload


def validate_plan_payload(
    payload: Any,
    *,
    available_tools: Sequence[str],
    max_steps: int,
) -> AgentPlan:
    """Validate and normalize a raw plan payload into ``AgentPlan``.

    Raises:
        ValueError: if the payload is not a well-formed plan within limits.
    """
    if not isinstance(payload, dict):
        raise ValueError("plan payload must be an object")

    goal = str(payload.get("goal") or "").strip()
    if not goal:
        raise ValueError("plan requires a non-empty goal")

    raw_steps = payload.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ValueError("plan requires a non-empty steps list")

    if len(raw_steps) > max_steps:
        raise ValueError(f"plan step count {len(raw_steps)} exceeds max_steps={max_steps}")

    available = {str(name) for name in available_tools}
    steps: List[PlanStep] = []
    for index, raw in enumerate(raw_steps, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"plan step {index} must be an object")
        step_goal = str(raw.get("goal") or "").strip()
        if not step_goal:
            raise ValueError(f"plan step {index} requires a non-empty goal")
        success = str(raw.get("success_criteria") or raw.get("success") or "").strip()
        if not success:
            raise ValueError(f"plan step {index} requires success_criteria")

        tools_raw = raw.get("expected_tools") or raw.get("tools") or []
        if not isinstance(tools_raw, list):
            raise ValueError(f"plan step {index} expected_tools must be a list")
        tools: List[str] = []
        for tool in tools_raw:
            name = str(tool or "").strip()
            if not name:
                continue
            if available and name not in available:
                # Unknown tools are dropped rather than inventing calls.
                continue
            if name not in tools:
                tools.append(name)

        step_id_raw = raw.get("id", index)
        try:
            step_id = int(step_id_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"plan step {index} has invalid id") from exc

        steps.append(
            PlanStep(
                id=step_id,
                goal=step_goal,
                expected_tools=tuple(tools),
                success_criteria=success,
            )
        )

    if not steps:
        raise ValueError("plan produced no valid steps after validation")

    declared_max = payload.get("max_steps", max_steps)
    try:
        plan_max = int(declared_max)
    except (TypeError, ValueError) as exc:
        raise ValueError("plan max_steps must be an integer") from exc
    plan_max = max(1, min(plan_max, max_steps))

    version = str(payload.get("version") or PLAN_SCHEMA_VERSION).strip() or PLAN_SCHEMA_VERSION
    return AgentPlan(
        goal=goal,
        steps=tuple(steps),
        max_steps=plan_max,
        version=version,
    )
