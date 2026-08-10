# -*- coding: utf-8 -*-
"""Agent planning: typed proposals and the opt-in plan→act→observe loop.

See ``docs/agent-planning-engine_EN.md`` for semantics, bounds, and rollback.
"""

from src.agent.planning.config import PlanExecutionSettings, PlanningSettings
from src.agent.planning.engine import PlanningEngine, prepare_run_with_planning
from src.agent.planning.loop import default_argument_builder, execute_plan_loop
from src.agent.planning.observations import (
    PlanExecutionResult,
    StepObservation,
    ToolCallObservation,
)
from src.agent.planning.types import AgentPlan, PlanStep, PlanningOutcome, validate_plan_payload

__all__ = [
    "AgentPlan",
    "PlanExecutionResult",
    "PlanExecutionSettings",
    "PlanStep",
    "PlanningEngine",
    "PlanningOutcome",
    "PlanningSettings",
    "StepObservation",
    "ToolCallObservation",
    "default_argument_builder",
    "execute_plan_loop",
    "prepare_run_with_planning",
    "validate_plan_payload",
]
