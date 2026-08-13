# -*- coding: utf-8 -*-
"""Agent evolution: typed lessons (input) and error-pattern encyclopedia (aggregation).

- ``lessons`` — shared ReflectionLesson taxonomy from #1089 / #1103 / #1196
- ``error_patterns`` — human-editable pattern cards clustered from lessons (#1138)
- ``guards`` — Soul / ToolSurface immutability proofs

The encyclopedia never rewrites Agent Soul charter bytes and never expands
ToolSurface denials. Pattern injection is a read-only, quota-bounded checklist.
"""

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

__all__ = [
    "DEFAULT_INJECT_CHAR_BUDGET",
    "DEFAULT_INJECT_TOP_K",
    "DEFAULT_STATE_FILENAME",
    "ERROR_PATTERN_IDS_KEY",
    "ERROR_PATTERN_PROMPT_KEY",
    "LESSON_KINDS",
    "MAX_PATTERN_INJECTION",
    "EpisodeLessonBundle",
    "ErrorPatternCard",
    "ErrorPatternEncyclopedia",
    "LessonKind",
    "PatternEditEvent",
    "PatternRetrievalResult",
    "PatternStats",
    "ReflectionLesson",
    "ReflectionResult",
    "SoulIdentitySnapshot",
    "assert_soul_unchanged",
    "cluster_lessons_into_cards",
    "format_error_pattern_checklist",
    "inject_error_pattern_checklist",
    "inject_error_patterns_into_analysis_context",
    "is_error_pattern_enabled",
    "lessons_from_kinds",
    "parse_lessons_payload",
    "retrieve_error_patterns",
    "resolve_error_pattern_state_path",
    "snapshot_soul_identity",
]
