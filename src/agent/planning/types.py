# -*- coding: utf-8 -*-
"""Structured types for the explicit plan-proposal foundation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.agent.planning.config import (
    MAX_AVAILABLE_TOOLS,
    MAX_CRITERIA_CHARS,
    MAX_GOAL_CHARS,
    MAX_PLAN_STEPS,
    MAX_PROMPT_PROJECTION_CHARS,
    MAX_TOOL_NAME_CHARS,
    PLAN_PROPOSAL_MARKER_RE,
    PROJECTION_ENVELOPE_CHARS,
    SURROGATE_CODE_POINT_RE,
)

PLAN_SCHEMA_VERSION = "agent-plan-v1"


def unprojectable_reason(text: str) -> Optional[str]:
    """The single projected-string contract, as a stable value-free reason or ``None``.

    Every string that reaches the canonical JSON — the plan goal, each step goal,
    each success criterion, each expected tool name, and the available tool names
    those are drawn from — must satisfy both halves:

    1. it must not forge the advisory boundary in any whitespace-tolerant spelling;
    2. it must be UTF-8 encodable, so ``plan_id`` / ``to_metadata`` /
       ``format_plan_for_prompt`` cannot raise on an accepted plan.

    Returned as a reason rather than an exception so the engine can fence its
    inputs into a stable degraded outcome without catching its own validator.
    """
    if PLAN_PROPOSAL_MARKER_RE.search(text):
        return "must not contain a plan-proposal boundary marker"
    if SURROGATE_CODE_POINT_RE.search(text):
        return "must not contain unpaired surrogate code points"
    return None


def reject_unprojectable_text(label: str, text: str) -> None:
    """Raise the stable ``unprojectable_reason`` for ``text``, if any.

    Raises:
        ValueError: labelled with the field, never echoing the offending value.
    """
    reason = unprojectable_reason(text)
    if reason is not None:
        raise ValueError(f"{label} {reason}")


def _escape_surrogates(text: str) -> str:
    """Render surrogate code points as JSON escapes so canonical text always encodes.

    ``validate_plan_payload`` already rejects them, so this is a no-op for every
    accepted plan and ``plan_id`` provenance is unchanged. It exists so a
    hand-built ``AgentPlan`` degrades to a stable id instead of raising
    ``UnicodeEncodeError`` out of ``plan_id`` or ``to_metadata``.
    """
    return SURROGATE_CODE_POINT_RE.sub(lambda match: f"\\u{ord(match.group()):04x}", text)


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
        """Canonical JSON text used for both ``plan_id`` and prompt projection.

        The one safe encoding contract for this module: readable non-ASCII text is
        preserved, and the result is always UTF-8 encodable.
        """
        return _escape_surrogates(
            json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, allow_nan=False)
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
    guarantees the plan is projectable by ``format_plan_for_prompt``: it fits the
    projection budget, and every projected string satisfies
    ``reject_unprojectable_text`` — including the tool names, which earlier bounded
    only length and membership.

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
    reject_unprojectable_text("plan goal", goal)

    raw_steps = payload.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ValueError("plan requires a non-empty steps list")

    if len(raw_steps) > max_steps:
        raise ValueError(f"plan step count {len(raw_steps)} exceeds max_steps={max_steps}")

    for name in available_tools:
        if (
            not isinstance(name, str)
            or not name.strip()
            or len(name.strip()) > MAX_TOOL_NAME_CHARS
        ):
            raise ValueError("available tool names must be bounded non-empty strings")
        # Tool names are projected verbatim inside the advisory block, so they are
        # governed by exactly the same contract as the generated prose fields.
        reject_unprojectable_text("available tool name", name.strip())
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
        reject_unprojectable_text(f"plan step {index} goal", step_goal)
        reject_unprojectable_text(f"plan step {index} success_criteria", success)

        tools_raw = raw.get("expected_tools")
        if not isinstance(tools_raw, list):
            raise ValueError(f"plan step {index} expected_tools must be a list")
        tools: List[str] = []
        for tool in tools_raw:
            if not isinstance(tool, str) or not tool.strip():
                raise ValueError(f"plan step {index} has invalid expected tool")
            name = tool.strip()
            reject_unprojectable_text(f"plan step {index} expected tool", name)
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
