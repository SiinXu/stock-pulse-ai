# -*- coding: utf-8 -*-
"""Facade for the three reflection layers (Issue #1094).

1. Immediate step critique (in-loop)
2. Trajectory / end-of-run reflection
3. Cross-run meta-review (offline, sample-thresholded)

Each layer has explicit trigger conditions and LLM budgets. Outputs are typed
lessons that project into episode storage. Soul / ToolSurface are never mutated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from src.agent.evolution.budget import LlmCallBudget
from src.agent.evolution.episode_lessons import (
    EpisodeLessonSink,
    merge_episode_lessons,
    record_reflection_lessons,
    reflection_result_to_episode_lessons,
)
from src.agent.evolution.meta_review import MetaReviewReport, run_meta_review
from src.agent.evolution.reflection import REFLECTION_META_KEY, run_reflection_loop
from src.agent.evolution.step_critique import (
    STEP_CRITIQUE_META_KEY,
    critique_step_observations,
)

LlmCompleteFn = Callable[[str, str], str]


@dataclass
class MultiLevelReflectionResult:
    """Combined view of the three reflection layers for one orchestration pass."""

    immediate: Optional[Dict[str, Any]] = None
    trajectory: Optional[Dict[str, Any]] = None
    meta: Optional[Dict[str, Any]] = None
    episode_lessons: List[Dict[str, Any]] = field(default_factory=list)
    replan_reason_kinds: List[str] = field(default_factory=list)

    def to_public_dict(self) -> Dict[str, Any]:
        return {
            "immediate": self.immediate,
            "trajectory": self.trajectory,
            "meta": self.meta,
            "episode_lessons": list(self.episode_lessons),
            "replan_reason_kinds": list(self.replan_reason_kinds),
            "mutates_soul": False,
            "mutates_tool_surface": False,
        }


def run_immediate_layer(
    observations: Sequence[Any],
    *,
    config: Any = None,
    ctx: Any = None,
    budget: Optional[LlmCallBudget] = None,
    llm_complete: Optional[LlmCompleteFn] = None,
    sink: Optional[EpisodeLessonSink] = None,
    force: bool = False,
) -> MultiLevelReflectionResult:
    """Layer 1: step critique after tool failure / contradiction."""
    result = critique_step_observations(
        observations,
        config=config,
        ctx=ctx,
        budget=budget,
        llm_complete=llm_complete,
        force=force,
    )
    lessons = record_reflection_lessons(
        sink,
        result,
        layer="immediate",
        run_id=result.run_id,
        episode_id=result.episode_id,
        meta={"layer": "immediate"},
    )
    meta = getattr(ctx, "meta", None) if ctx is not None else None
    replan_reasons: List[str] = []
    if isinstance(meta, dict):
        replan_reasons = list(meta.get("replan_reason_kinds") or [])
        payload = meta.get(STEP_CRITIQUE_META_KEY)
    else:
        payload = result.to_public_dict()
        payload["layer"] = "immediate"
    return MultiLevelReflectionResult(
        immediate=payload if isinstance(payload, dict) else result.to_public_dict(),
        episode_lessons=lessons,
        replan_reason_kinds=replan_reasons,
    )


def run_trajectory_layer(
    ctx: Any,
    *,
    config: Any = None,
    budget: Optional[LlmCallBudget] = None,
    llm_complete: Optional[LlmCompleteFn] = None,
    sink: Optional[EpisodeLessonSink] = None,
    seed_from_immediate: bool = True,
) -> MultiLevelReflectionResult:
    """Layer 2: end-of-run reflection producing full ReflectionResult."""
    seed = None
    meta = getattr(ctx, "meta", None) if ctx is not None else None
    if seed_from_immediate and isinstance(meta, dict):
        step_payload = meta.get(STEP_CRITIQUE_META_KEY)
        if isinstance(step_payload, dict) and step_payload.get("lessons"):
            from src.agent.evolution.lessons import parse_lessons_payload

            try:
                seed = parse_lessons_payload(step_payload.get("lessons") or [])
            except (TypeError, ValueError):
                seed = None

    result = run_reflection_loop(
        ctx,
        config=config,
        llm_complete=llm_complete,
        budget=budget,
        seed_lessons=seed,
    )
    if isinstance(meta, dict) and isinstance(meta.get(REFLECTION_META_KEY), dict):
        meta[REFLECTION_META_KEY]["layer"] = "trajectory"

    lessons = record_reflection_lessons(
        sink,
        result,
        layer="trajectory",
        run_id=result.run_id,
        episode_id=result.episode_id,
        meta={"layer": "trajectory"},
    )
    payload = (
        meta.get(REFLECTION_META_KEY)
        if isinstance(meta, dict)
        else result.to_public_dict()
    )
    if isinstance(payload, dict):
        payload = dict(payload)
        payload.setdefault("layer", "trajectory")

    immediate_lessons: List[Dict[str, Any]] = []
    if isinstance(meta, dict):
        step_payload = meta.get(STEP_CRITIQUE_META_KEY)
        if isinstance(step_payload, dict):
            immediate_lessons = list(step_payload.get("lessons") or [])

    return MultiLevelReflectionResult(
        immediate={"lessons": immediate_lessons} if immediate_lessons else None,
        trajectory=payload if isinstance(payload, dict) else result.to_public_dict(),
        episode_lessons=merge_episode_lessons(
            immediate_lessons,
            reflection_result_to_episode_lessons(result),
        ),
        replan_reason_kinds=list((meta or {}).get("replan_reason_kinds") or [])
        if isinstance(meta, dict)
        else [],
    )


def run_cross_run_layer(
    episodes: Sequence[Dict[str, Any]],
    *,
    config: Any = None,
    min_episodes: Optional[int] = None,
    budget: Optional[LlmCallBudget] = None,
    llm_complete: Optional[LlmCompleteFn] = None,
    force: bool = False,
) -> MultiLevelReflectionResult:
    """Layer 3: offline meta-review with sample threshold."""
    report: MetaReviewReport = run_meta_review(
        episodes,
        config=config,
        min_episodes=min_episodes,
        budget=budget,
        llm_complete=llm_complete,
        force=force,
    )
    return MultiLevelReflectionResult(meta=report.to_dict())


__all__ = [
    "MultiLevelReflectionResult",
    "run_cross_run_layer",
    "run_immediate_layer",
    "run_trajectory_layer",
]
