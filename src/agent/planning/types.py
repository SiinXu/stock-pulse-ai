# -*- coding: utf-8 -*-
"""Structured types for the explicit plan-proposal foundation."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.agent.planning.config import (
    MAX_AVAILABLE_TOOLS,
    MAX_CRITERIA_CHARS,
    MAX_GOAL_CHARS,
    MAX_PLAN_STEPS,
    MAX_PROMPT_PROJECTION_CHARS,
    MAX_TOOL_NAME_CHARS,
    PROJECTION_ENVELOPE_CHARS,
)

PLAN_SCHEMA_VERSION = "agent-plan-v1"

# Any spelling of the projection delimiter, so generated text cannot close the
# advisory boundary early and have the remainder read as authoritative input.
_PROPOSAL_MARKER_RE = re.compile(r"\[\s*/?\s*NON_AUTHORITATIVE_PLAN_PROPOSAL\s*\]", re.IGNORECASE)


def _reject_marker_forgery(label: str, text: str) -> None:
    if _PROPOSAL_MARKER_RE.search(text):
        raise ValueError(f"{label} must not contain a plan-proposal boundary marker")


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
    """Validated proposal with no implied execution semantics."""

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

    def to_canonical_json(self) -> str:
        """Canonical JSON text used for both ``plan_id`` and prompt projection."""
        return json.dumps(
            self.to_dict(), ensure_ascii=False, sort_keys=True, allow_nan=False
        )

    @property
    def plan_id(self) -> str:
        return hashlib.sha256(self.to_canonical_json().encode("utf-8")).hexdigest()

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
    """Result of attempting to produce a bounded proposal."""

    enabled: bool
    applied: bool
    plan: Optional[AgentPlan] = None
    fallback_reason: Optional[str] = None
    strategy: str = "none"
    #: Strategy the caller asked for. Differs from ``strategy`` when an ``llm``
    #: attempt failed and the retry degraded to ``template``, so billed tokens
    #: and the recorded model stay attributable to the attempt that produced them.
    requested_strategy: str = "none"
    replan_attempts: int = 0
    planning_tokens: int = 0
    planning_model: str = ""
    error_code: Optional[str] = None
    exception_type: Optional[str] = None

    def to_metadata(self) -> Dict[str, Any]:
        """Trace-safe metadata (no free-form model reasoning dump)."""
        payload: Dict[str, Any] = {
            "enabled": self.enabled,
            "applied": self.applied,
            "strategy": self.strategy,
            "requested_strategy": self.requested_strategy,
            "replan_attempts": self.replan_attempts,
            "planning_tokens": self.planning_tokens,
            "planning_model": self.planning_model,
            "schema_version": PLAN_SCHEMA_VERSION,
        }
        if self.fallback_reason:
            payload["fallback_reason"] = self.fallback_reason
        if self.error_code:
            payload["error_code"] = self.error_code
        if self.exception_type:
            payload["exception_type"] = self.exception_type
        if self.plan is not None:
            payload["plan"] = self.plan.to_dict()
            payload["plan_id"] = self.plan.plan_id
            payload["step_count"] = self.plan.step_count
            payload["expected_tools"] = list(self.plan.expected_tool_names)
        return payload


def validate_plan_payload(
    payload: Any,
    *,
    available_tools: Sequence[str],
    max_steps: int,
) -> AgentPlan:
    """Validate and normalize a raw plan payload into ``AgentPlan``.

    ``max_steps`` is a caller cap that may only tighten the absolute
    ``config.MAX_PLAN_STEPS`` authority; it can never raise it. Acceptance
    guarantees the plan is projectable by ``format_plan_for_prompt`` and that no
    generated text can forge the projection boundary marker.

    Raises:
        ValueError: if the payload is not a well-formed plan within limits.
    """
    if type(max_steps) is not int or not 1 <= max_steps <= MAX_PLAN_STEPS:
        raise ValueError(f"max_steps must be an integer within [1, {MAX_PLAN_STEPS}]")
    if isinstance(available_tools, (str, bytes)) or len(available_tools) > MAX_AVAILABLE_TOOLS:
        raise ValueError(f"available tool set must be a sequence of at most {MAX_AVAILABLE_TOOLS} names")
    if not isinstance(payload, dict):
        raise ValueError("plan payload must be an object")
    if set(payload) != {"version", "goal", "max_steps", "steps"}:
        raise ValueError("plan payload fields do not match agent-plan-v1")
    if payload.get("version") != PLAN_SCHEMA_VERSION:
        raise ValueError(f"plan version must be {PLAN_SCHEMA_VERSION}")

    goal_raw = payload.get("goal")
    if not isinstance(goal_raw, str) or not goal_raw.strip():
        raise ValueError("plan requires a non-empty string goal")
    goal = goal_raw.strip()
    if len(goal) > MAX_GOAL_CHARS:
        raise ValueError("plan goal exceeds length limit")
    _reject_marker_forgery("plan goal", goal)

    raw_steps = payload.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ValueError("plan requires a non-empty steps list")

    if len(raw_steps) > max_steps:
        raise ValueError(f"plan step count {len(raw_steps)} exceeds max_steps={max_steps}")

    if any(
        not isinstance(name, str)
        or not name.strip()
        or len(name.strip()) > MAX_TOOL_NAME_CHARS
        for name in available_tools
    ):
        raise ValueError("available tool names must be bounded non-empty strings")
    available = {name.strip() for name in available_tools}
    if len(available) != len(available_tools):
        raise ValueError("available tool names must be unique")
    steps: List[PlanStep] = []
    for index, raw in enumerate(raw_steps, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"plan step {index} must be an object")
        if set(raw) != {"id", "goal", "expected_tools", "success_criteria"}:
            raise ValueError(f"plan step {index} fields do not match schema")
        step_goal_raw = raw.get("goal")
        success_raw = raw.get("success_criteria")
        if not isinstance(step_goal_raw, str) or not step_goal_raw.strip():
            raise ValueError(f"plan step {index} requires a non-empty string goal")
        if not isinstance(success_raw, str) or not success_raw.strip():
            raise ValueError(f"plan step {index} requires success_criteria")
        step_goal = step_goal_raw.strip()
        success = success_raw.strip()
        if len(step_goal) > MAX_GOAL_CHARS or len(success) > MAX_CRITERIA_CHARS:
            raise ValueError(f"plan step {index} text exceeds length limit")
        _reject_marker_forgery(f"plan step {index} goal", step_goal)
        _reject_marker_forgery(f"plan step {index} success_criteria", success)

        tools_raw = raw.get("expected_tools")
        if not isinstance(tools_raw, list):
            raise ValueError(f"plan step {index} expected_tools must be a list")
        tools: List[str] = []
        for tool in tools_raw:
            if not isinstance(tool, str) or not tool.strip():
                raise ValueError(f"plan step {index} has invalid expected tool")
            name = tool.strip()
            if len(name) > MAX_TOOL_NAME_CHARS or name not in available:
                raise ValueError(f"plan step {index} requests unavailable tool {name!r}")
            if name in tools:
                raise ValueError(f"plan step {index} repeats expected tool {name!r}")
            tools.append(name)

        step_id = raw.get("id")
        if type(step_id) is not int or step_id != index:
            raise ValueError("plan step ids must be positive, unique, and sequential")

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

    plan_max = payload.get("max_steps")
    if type(plan_max) is not int or not len(steps) <= plan_max <= max_steps:
        raise ValueError("plan max_steps must bound steps within the caller cap")
    plan = AgentPlan(
        goal=goal,
        steps=tuple(steps),
        max_steps=plan_max,
        version=PLAN_SCHEMA_VERSION,
    )
    # Per-field bounds alone do not bound the whole payload (a step may list many
    # tools). Reject here so an accepted plan is always projectable.
    projected = PROJECTION_ENVELOPE_CHARS + len(plan.to_canonical_json())
    if projected > MAX_PROMPT_PROJECTION_CHARS:
        raise ValueError("plan prompt projection exceeds size limit")
    return plan
