# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Public API exports for the structured report-insights contract."""

from src.schemas.report_structured_insights import (
    REPORT_STRUCTURED_INSIGHTS_SCHEMA_VERSION,
    ReportStructuredInsights,
    ReportStructuredPhaseContext,
    ReportStructuredPhaseDecision,
    ReportStructuredSignalAttribution,
    ReportStructuredStrategyConflict,
    ReportStructuredStrategySkill,
    ReportStructuredStrategySummary,
    ReportStructuredStrategySynthesis,
    project_report_structured_insights_for_api,
)

__all__ = [
    "REPORT_STRUCTURED_INSIGHTS_SCHEMA_VERSION",
    "ReportStructuredInsights",
    "ReportStructuredPhaseContext",
    "ReportStructuredPhaseDecision",
    "ReportStructuredSignalAttribution",
    "ReportStructuredStrategyConflict",
    "ReportStructuredStrategySkill",
    "ReportStructuredStrategySummary",
    "ReportStructuredStrategySynthesis",
    "project_report_structured_insights_for_api",
]
