# -*- coding: utf-8 -*-
"""Pipeline glue for the optional post-Decision red-team stage."""

from __future__ import annotations

from typing import Any, Callable, Optional

from src.agent import bull_bear_debate as _debate
from src.agent import red_team as _red_team
from src.agent.protocols import AgentContext, AgentRunStats, StageResult

RED_TEAM_STAGE_NAME = _red_team.RED_TEAM_STAGE_NAME


def is_non_critical_pipeline_stage(
    agent_name: Any,
    base_stages: Any,
    skill_agent_names: Any = None,
) -> bool:
    """Return whether a failed stage should degrade instead of aborting."""
    name = str(agent_name or "").strip()
    if name in (base_stages or ()):
        return True
    if _red_team.is_red_team_stage(name):
        return True
    extra = skill_agent_names if isinstance(skill_agent_names, (set, frozenset, list, tuple)) else ()
    return name in extra


def maybe_skip_current_agent(
    pipeline: Any,
    agents: list,
    index: int,
    ctx: AgentContext,
    stats: AgentRunStats,
    timeout_s: Optional[float],
    remaining_budget: Optional[float],
    min_stage_budget_s: float,
    progress_callback: Optional[Callable],
) -> bool:
    """Fail-soft skip the current red-team agent. True means ``continue`` at ``index``."""
    if index < 0 or index >= len(agents):
        return False
    skipped = _red_team.maybe_skip_for_budget(
        pipeline,
        agents[index],
        ctx,
        stats,
        timeout_s,
        remaining_budget,
        min_stage_budget_s,
        progress_callback,
    )
    if not skipped:
        return False
    del agents[index]
    return True


def maybe_insert_review_stages(
    pipeline: Any,
    agents: list,
    index: int,
    ctx: AgentContext,
    stats: AgentRunStats,
    timeout_s: Optional[float],
    remaining_budget: Optional[float],
    required_budget_s: float,
    progress_callback: Optional[Callable],
) -> bool:
    """Insert debate before Decision and red-team after it. True means ``continue``."""
    if _debate.maybe_insert_before_decision(
        pipeline,
        agents,
        index,
        ctx,
        stats,
        timeout_s,
        remaining_budget,
        required_budget_s,
        progress_callback,
    ):
        return True
    _red_team.maybe_insert_after_decision(pipeline, agents, index, ctx)
    return False


def commit_pipeline_stage_result(
    ctx: AgentContext,
    result: StageResult,
    stage_name: str,
) -> None:
    """Persist debate and red-team evidence onto the stage result."""
    _debate.commit_pipeline_stage_result(ctx, result, stage_name)
    _red_team.commit_pipeline_stage_result(ctx, result, stage_name)
