# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Stable structured-report contract and projection.

The analysis pipeline already produces phase decisions, signal attribution,
and multi-strategy synthesis under ``dashboard``.  This module exposes only
their bounded, renderer-safe fields so synchronous, task, and history reports
share one additive contract. Historical or malformed payloads remain valid
when the projection is absent.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, Iterable, List, Literal, Optional, cast

from typing_extensions import NotRequired, TypedDict

from src.report_language import normalize_strategy_synthesis_payload
from src.utils.data_processing import (
    normalize_signal_attribution_values,
    signal_attribution_has_content,
)


REPORT_STRUCTURED_INSIGHTS_SCHEMA_VERSION: Literal[
    "report-structured-insights-v1"
] = "report-structured-insights-v1"


class ReportStructuredPhaseContext(TypedDict, total=False):
    """Bounded market-phase context exposed by the report API."""

    phase: str
    market: str
    market_local_time: str
    session_date: str
    effective_daily_bar_date: str
    trigger_source: str
    analysis_intent: str
    is_trading_day: bool
    is_market_open_now: bool
    is_partial_bar: bool
    minutes_to_open: float | int
    minutes_to_close: float | int
    warnings: List[str]


class ReportStructuredPhaseDecision(TypedDict, total=False):
    """Bounded phase-decision fields exposed by the report API."""

    phase_context: ReportStructuredPhaseContext
    action_window: str
    immediate_action: str
    next_check_time: str
    confidence_reason: str
    watch_conditions: List[str]
    data_limitations: List[str]


class ReportStructuredSignalAttribution(TypedDict, total=False):
    """Normalized signal-attribution weights and strongest-signal labels."""

    technical_indicators: int
    news_sentiment: int
    fundamentals: int
    market_conditions: int
    strongest_bullish_signal: str
    strongest_bearish_signal: str


class ReportStructuredStrategySkill(TypedDict, total=False):
    """One bounded supporting or opposing strategy opinion."""

    skill_id: str
    agent_name: str
    signal: str
    reasoning: str
    confidence: float | int
    score_adjustment: float | int
    conditions_met: List[str]
    invalid_signal: bool


class ReportStructuredStrategyConflict(TypedDict, total=False):
    """One bounded conflict between strategy opinions."""

    conflict_type: str
    severity: str
    description_key: str
    participants: List[str]


class ReportStructuredStrategySummary(TypedDict, total=False):
    """Bounded summary parameters for a strategy synthesis."""

    final_signal: str
    consensus_level: str
    conflict_severity: str
    opinion_count: float | int
    total_opinion_count: float | int
    invalid_opinion_count: float | int
    conflict_count: float | int


class ReportStructuredStrategySynthesis(TypedDict, total=False):
    """Bounded multi-strategy synthesis exposed by the report API."""

    final_signal: str
    conflict_severity: str
    consensus_level: str
    summary_key: str
    weighted_score: float | int
    confidence: float | int
    original_confidence: float | int
    conflict_count: float | int
    supporting_skills: List[ReportStructuredStrategySkill]
    opposing_skills: List[ReportStructuredStrategySkill]
    conflicts: List[ReportStructuredStrategyConflict]
    summary_params: ReportStructuredStrategySummary


class ReportStructuredInsights(TypedDict):
    """Versioned structured-insight projection returned by report APIs."""

    schema_version: Literal["report-structured-insights-v1"]
    phase_decision: NotRequired[ReportStructuredPhaseDecision]
    signal_attribution: NotRequired[ReportStructuredSignalAttribution]
    strategy_synthesis: NotRequired[ReportStructuredStrategySynthesis]


_PHASE_CONTEXT_TEXT_FIELDS = (
    "phase",
    "market",
    "market_local_time",
    "session_date",
    "effective_daily_bar_date",
    "trigger_source",
    "analysis_intent",
)
_PHASE_CONTEXT_BOOLEAN_FIELDS = (
    "is_trading_day",
    "is_market_open_now",
    "is_partial_bar",
)
_PHASE_CONTEXT_NUMBER_FIELDS = (
    "minutes_to_open",
    "minutes_to_close",
)
_PHASE_DECISION_TEXT_FIELDS = (
    "action_window",
    "immediate_action",
    "next_check_time",
    "confidence_reason",
)
_SIGNAL_ATTRIBUTION_WEIGHT_FIELDS = (
    "technical_indicators",
    "news_sentiment",
    "fundamentals",
    "market_conditions",
)
_SIGNAL_ATTRIBUTION_TEXT_FIELDS = (
    "strongest_bullish_signal",
    "strongest_bearish_signal",
)
_STRATEGY_TEXT_FIELDS = (
    "final_signal",
    "conflict_severity",
    "consensus_level",
    "summary_key",
)
_STRATEGY_NUMBER_FIELDS = (
    "weighted_score",
    "confidence",
    "original_confidence",
    "conflict_count",
)
_STRATEGY_SUMMARY_NUMBER_FIELDS = (
    "opinion_count",
    "total_opinion_count",
    "invalid_opinion_count",
    "conflict_count",
)


def _clean_text(value: Any) -> Optional[str]:
    """Return trimmed non-empty text, or ``None`` for unsupported values."""

    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _clean_number(value: Any) -> Optional[float | int]:
    """Return one finite numeric value while excluding booleans."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return value


def _clean_string_list(value: Any, *, limit: int = 30) -> List[str]:
    """Return a bounded, de-duplicated list of non-empty strings."""

    if isinstance(value, str):
        values: Iterable[Any] = (value,)
    elif isinstance(value, list):
        values = value
    else:
        return []

    result: List[str] = []
    for item in values:
        text = _clean_text(item)
        if text and text not in result:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _candidate_containers(source: Any) -> List[Dict[str, Any]]:
    """Return ordered containers that may hold structured report sections."""

    if not isinstance(source, dict):
        return []

    containers: List[Dict[str, Any]] = []

    def add(value: Any) -> None:
        """Append one distinct dictionary container while preserving order."""

        if isinstance(value, dict) and value not in containers:
            containers.append(value)

    add(source.get("structured_insights"))
    details = source.get("details")
    if isinstance(details, dict):
        add(details.get("structured_insights"))
    add(source.get("dashboard"))
    add(source)

    raw_result = source.get("raw_result")
    if isinstance(raw_result, dict):
        add(raw_result.get("structured_insights"))
        add(raw_result.get("dashboard"))
        add(raw_result)

    if isinstance(details, dict):
        details_raw_result = details.get("raw_result")
        if isinstance(details_raw_result, dict):
            add(details_raw_result.get("structured_insights"))
            add(details_raw_result.get("dashboard"))
            add(details_raw_result)

    return containers


def _project_phase_decision(
    value: Any,
) -> Optional[ReportStructuredPhaseDecision]:
    """Project one phase decision onto the bounded API transport fields."""

    if not isinstance(value, dict):
        return None

    projected: Dict[str, Any] = {}
    phase_context = value.get("phase_context")
    if isinstance(phase_context, dict):
        projected_context: Dict[str, Any] = {}
        for field in _PHASE_CONTEXT_TEXT_FIELDS:
            text = _clean_text(phase_context.get(field))
            if text is not None:
                projected_context[field] = text
        for field in _PHASE_CONTEXT_BOOLEAN_FIELDS:
            flag = phase_context.get(field)
            if isinstance(flag, bool):
                projected_context[field] = flag
        for field in _PHASE_CONTEXT_NUMBER_FIELDS:
            number = _clean_number(phase_context.get(field))
            if number is not None:
                projected_context[field] = number
        warnings = _clean_string_list(phase_context.get("warnings"))
        if warnings:
            projected_context["warnings"] = warnings
        if projected_context:
            projected["phase_context"] = cast(
                ReportStructuredPhaseContext, projected_context
            )

    for field in _PHASE_DECISION_TEXT_FIELDS:
        text = _clean_text(value.get(field))
        if text is not None:
            projected[field] = text

    watch_conditions = _clean_string_list(value.get("watch_conditions"))
    if watch_conditions:
        projected["watch_conditions"] = watch_conditions
    data_limitations = _clean_string_list(value.get("data_limitations"))
    if data_limitations:
        projected["data_limitations"] = data_limitations

    return cast(ReportStructuredPhaseDecision, projected) if projected else None


def _project_signal_attribution(
    value: Any,
) -> Optional[ReportStructuredSignalAttribution]:
    """Normalize and project signal-attribution values for API transport."""

    if not isinstance(value, dict):
        return None

    normalized = normalize_signal_attribution_values(dict(value))
    if not normalized or not signal_attribution_has_content(normalized):
        return None

    projected: Dict[str, Any] = {}
    for field in _SIGNAL_ATTRIBUTION_WEIGHT_FIELDS:
        number = _clean_number(normalized.get(field))
        if number is not None:
            projected[field] = int(round(float(number)))
    for field in _SIGNAL_ATTRIBUTION_TEXT_FIELDS:
        text = _clean_text(normalized.get(field))
        if text is not None:
            projected[field] = text
    return cast(ReportStructuredSignalAttribution, projected) if projected else None


def _project_strategy_skill(
    value: Any,
) -> Optional[ReportStructuredStrategySkill]:
    """Project one strategy opinion without unbounded metadata."""

    if not isinstance(value, dict):
        return None

    projected: Dict[str, Any] = {}
    for field in ("skill_id", "agent_name", "signal", "reasoning"):
        text = _clean_text(value.get(field))
        if text is not None:
            projected[field] = text
    for field in ("confidence", "score_adjustment"):
        number = _clean_number(value.get(field))
        if number is not None:
            projected[field] = number
    conditions_met = _clean_string_list(value.get("conditions_met"))
    if conditions_met:
        projected["conditions_met"] = conditions_met
    if isinstance(value.get("invalid_signal"), bool):
        projected["invalid_signal"] = value["invalid_signal"]
    return cast(ReportStructuredStrategySkill, projected) if projected else None


def _project_strategy_conflict(
    value: Any,
) -> Optional[ReportStructuredStrategyConflict]:
    """Project one strategy conflict without internal metadata."""

    if not isinstance(value, dict):
        return None

    projected: Dict[str, Any] = {}
    for field in ("conflict_type", "severity", "description_key"):
        text = _clean_text(value.get(field))
        if text is not None:
            projected[field] = text
    participants = _clean_string_list(value.get("participants"))
    if participants:
        projected["participants"] = participants
    return cast(ReportStructuredStrategyConflict, projected) if projected else None


def _project_strategy_synthesis(
    value: Any,
) -> Optional[ReportStructuredStrategySynthesis]:
    """Normalize and project a bounded multi-strategy synthesis."""

    normalized = normalize_strategy_synthesis_payload(value)
    if not normalized:
        return None

    projected: Dict[str, Any] = {}
    for field in _STRATEGY_TEXT_FIELDS:
        text = _clean_text(normalized.get(field))
        if text is not None:
            projected[field] = text
    for field in _STRATEGY_NUMBER_FIELDS:
        number = _clean_number(normalized.get(field))
        if number is not None:
            projected[field] = number

    for field in ("supporting_skills", "opposing_skills"):
        items = [
            item
            for item in (
                _project_strategy_skill(raw_item)
                for raw_item in normalized.get(field, [])
            )
            if item is not None
        ][:30]
        if items:
            projected[field] = items

    conflicts = [
        item
        for item in (
            _project_strategy_conflict(raw_item)
            for raw_item in normalized.get("conflicts", [])
        )
        if item is not None
    ][:30]
    if conflicts:
        projected["conflicts"] = conflicts

    summary_params = normalized.get("summary_params")
    if isinstance(summary_params, dict):
        projected_summary: Dict[str, Any] = {}
        for field in ("final_signal", "consensus_level", "conflict_severity"):
            text = _clean_text(summary_params.get(field))
            if text is not None:
                projected_summary[field] = text
        for field in _STRATEGY_SUMMARY_NUMBER_FIELDS:
            number = _clean_number(summary_params.get(field))
            if number is not None:
                projected_summary[field] = number
        if projected_summary:
            projected["summary_params"] = cast(
                ReportStructuredStrategySummary, projected_summary
            )

    meaningful = (
        bool(projected.get("final_signal"))
        or bool(projected.get("consensus_level"))
        or bool(projected.get("supporting_skills"))
        or bool(projected.get("opposing_skills"))
        or bool(projected.get("conflicts"))
    )
    return cast(ReportStructuredStrategySynthesis, projected) if meaningful else None


def _first_projected_section(
    sources: Iterable[Any],
    key: str,
    projector: Any,
) -> Optional[Dict[str, Any]]:
    """Return the first non-empty projection for one named section."""

    for source in sources:
        for container in _candidate_containers(source):
            projected = projector(container.get(key))
            if projected is not None:
                return projected
    return None


def project_report_structured_insights_for_api(
    *sources: Any,
    log_context: Optional[Dict[str, Any]] = None,
) -> Optional[ReportStructuredInsights]:
    """Return one bounded optional contract for structured report sections."""
    from src.utils.sanitize import log_safe_exception

    try:
        phase_decision = _first_projected_section(
            sources,
            "phase_decision",
            _project_phase_decision,
        )
        signal_attribution = _first_projected_section(
            sources,
            "signal_attribution",
            _project_signal_attribution,
        )
        strategy_synthesis = _first_projected_section(
            sources,
            "strategy_synthesis",
            _project_strategy_synthesis,
        )
        if not any((phase_decision, signal_attribution, strategy_synthesis)):
            return None

        result: ReportStructuredInsights = {
            "schema_version": REPORT_STRUCTURED_INSIGHTS_SCHEMA_VERSION,
        }
        if phase_decision is not None:
            result["phase_decision"] = cast(
                ReportStructuredPhaseDecision, phase_decision
            )
        if signal_attribution is not None:
            result["signal_attribution"] = cast(
                ReportStructuredSignalAttribution, signal_attribution
            )
        if strategy_synthesis is not None:
            result["strategy_synthesis"] = cast(
                ReportStructuredStrategySynthesis, strategy_synthesis
            )
        return result
    except Exception as exc:  # broad-exception: fallback_recorded - projection failure must not break report delivery
        log_safe_exception(
            logging.getLogger(__name__),
            "Structured report insight projection failed",
            exc,
            error_code="report_structured_insights_projection_failed",
            level=logging.WARNING,
            context=log_context or {},
        )
        return None
