# -*- coding: utf-8 -*-
"""Agent evolution: typed lessons, forecast post-mortems, and error-pattern encyclopedia.

- ``lessons`` — shared ReflectionLesson taxonomy from #1089 / #1103 / #1196
- ``budget`` / ``reflection`` / ``postmortem`` — run-local critique and forecast post-mortem
- ``error_patterns`` — human-editable pattern cards clustered from lessons (#1138)
- ``guards`` — Soul / ToolSurface immutability proofs
- ``adapters`` — gated online adapters wrapping AgentMemory (Issue #1091; default off)

These modules do not mutate Agent Soul charter bytes and never expand ToolSurface
denials. Pattern injection is a read-only, quota-bounded checklist.
"""

from src.agent.evolution.adapters import (
    ADAPTER_INFLUENCE_META_KEY,
    DEFAULT_ONLINE_ADAPTERS_MIN_SAMPLES,
    calibrate_confidence,
    is_online_adapters_enabled,
    prefer_route,
    rank_tools,
    record_adapter_influence,
)
from src.agent.evolution.budget import (
    BUDGET_SKIPPED,
    DEFAULT_META_REVIEW_LLM_BUDGET,
    DEFAULT_POSTMORTEM_BATCH_LLM_BUDGET,
    DEFAULT_STEP_CRITIQUE_LLM_BUDGET,
    DEFAULT_REFLECTION_LLM_BUDGET,
    LlmCallBudget,
)
from src.agent.evolution.error_patterns import (
    DEFAULT_INJECT_CHAR_BUDGET,
    DEFAULT_INJECT_TOP_K,
    DEFAULT_STATE_FILENAME,
    ERROR_PATTERN_IDS_KEY,
    ERROR_PATTERN_PROMPT_KEY,
    MAX_PATTERN_INJECTION,
    ErrorPatternCard,
    ErrorPatternEncyclopedia,
    PatternEditEvent,
    PatternRetrievalResult,
    PatternStats,
    cluster_lessons_into_cards,
    format_error_pattern_checklist,
    inject_error_pattern_checklist,
    inject_error_patterns_into_analysis_context,
    is_error_pattern_enabled,
    retrieve_error_patterns,
    resolve_error_pattern_state_path,
)
from src.agent.evolution.guards import (
    SoulIdentitySnapshot,
    assert_soul_unchanged,
    snapshot_soul_identity,
)
from src.agent.evolution.lessons import (
    LESSON_KINDS,
    EpisodeLessonBundle,
    LessonKind,
    ReflectionLesson,
    ReflectionResult,
    lessons_from_kinds,
    parse_lessons_payload,
)
from src.agent.evolution.postmortem import (
    PostMortemBatchResult,
    ResolvedClaimOutcome,
    ResolvedForecastInput,
    reflect_resolved_forecast,
    run_postmortem_batch,
)
from src.agent.evolution.meta_review import (
    DEFAULT_META_MIN_EPISODES,
    MetaReviewReport,
    is_meta_review_enabled,
    run_meta_review,
    write_meta_review_report,
)
from src.agent.evolution.step_critique import (
    STEP_CRITIQUE_META_KEY,
    critique_step_observations,
    is_step_critique_enabled,
    map_replan_reason_kind,
)
from src.agent.evolution.reflection import (
    REFLECTION_META_KEY,
    is_reflection_enabled,
    parse_reflection_output,
    run_reflection_loop,
)

__all__ = [
    "ADAPTER_INFLUENCE_META_KEY",
    "BUDGET_SKIPPED",
    "DEFAULT_ONLINE_ADAPTERS_MIN_SAMPLES",
    "DEFAULT_INJECT_CHAR_BUDGET",
    "DEFAULT_INJECT_TOP_K",
    "DEFAULT_POSTMORTEM_BATCH_LLM_BUDGET",
    "DEFAULT_REFLECTION_LLM_BUDGET",
    "DEFAULT_STATE_FILENAME",
    "ERROR_PATTERN_IDS_KEY",
    "ERROR_PATTERN_PROMPT_KEY",
    "LESSON_KINDS",
    "MAX_PATTERN_INJECTION",
    "EpisodeLessonBundle",
    "ErrorPatternCard",
    "ErrorPatternEncyclopedia",
    "LessonKind",
    "LlmCallBudget",
    "PatternEditEvent",
    "PatternRetrievalResult",
    "PatternStats",
    "PostMortemBatchResult",
    "REFLECTION_META_KEY",
    "ReflectionLesson",
    "ReflectionResult",
    "ResolvedClaimOutcome",
    "ResolvedForecastInput",
    "SoulIdentitySnapshot",
    "assert_soul_unchanged",
    "calibrate_confidence",
    "cluster_lessons_into_cards",
    "format_error_pattern_checklist",
    "inject_error_pattern_checklist",
    "inject_error_patterns_into_analysis_context",
    "is_error_pattern_enabled",
    "is_online_adapters_enabled",
    "is_reflection_enabled",
    "lessons_from_kinds",
    "parse_lessons_payload",
    "parse_reflection_output",
    "prefer_route",
    "rank_tools",
    "record_adapter_influence",
    "reflect_resolved_forecast",
    "retrieve_error_patterns",
    "resolve_error_pattern_state_path",
    "run_postmortem_batch",
    "run_reflection_loop",
    "DEFAULT_META_MIN_EPISODES",
    "DEFAULT_META_REVIEW_LLM_BUDGET",
    "DEFAULT_STEP_CRITIQUE_LLM_BUDGET",
    "MetaReviewReport",
    "STEP_CRITIQUE_META_KEY",
    "critique_step_observations",
    "is_meta_review_enabled",
    "is_step_critique_enabled",
    "map_replan_reason_kind",
    "run_meta_review",
    "write_meta_review_report",
    "snapshot_soul_identity",
]
