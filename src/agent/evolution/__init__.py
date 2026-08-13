# -*- coding: utf-8 -*-
"""Agent evolution contracts: reflection lessons and forecast post-mortems.

See Issues #1089 (run-local reflection contract) and #1103 (resolved-forecast
post-mortem). These modules do not mutate Agent Soul or ToolSurface denials.
"""

from src.agent.evolution.budget import (
    BUDGET_SKIPPED,
    DEFAULT_POSTMORTEM_BATCH_LLM_BUDGET,
    DEFAULT_REFLECTION_LLM_BUDGET,
    LlmCallBudget,
)
from src.agent.evolution.lessons import (
    LESSON_KINDS,
    EpisodeLessonBundle,
    ReflectionLesson,
    ReflectionResult,
)
from src.agent.evolution.postmortem import (
    PostMortemBatchResult,
    ResolvedClaimOutcome,
    ResolvedForecastInput,
    reflect_resolved_forecast,
    run_postmortem_batch,
)
from src.agent.evolution.reflection import (
    REFLECTION_META_KEY,
    is_reflection_enabled,
    parse_reflection_output,
    run_reflection_loop,
)

__all__ = [
    "BUDGET_SKIPPED",
    "DEFAULT_POSTMORTEM_BATCH_LLM_BUDGET",
    "DEFAULT_REFLECTION_LLM_BUDGET",
    "EpisodeLessonBundle",
    "LESSON_KINDS",
    "LlmCallBudget",
    "PostMortemBatchResult",
    "REFLECTION_META_KEY",
    "ReflectionLesson",
    "ReflectionResult",
    "ResolvedClaimOutcome",
    "ResolvedForecastInput",
    "is_reflection_enabled",
    "parse_reflection_output",
    "reflect_resolved_forecast",
    "run_postmortem_batch",
    "run_reflection_loop",
]
