# -*- coding: utf-8 -*-
"""Extract and persist DecisionSignal payloads from completed analysis reports.

The pure payload builder lives in ``decision_signal_payload`` so both this
persist path and ``decision_signal_service`` history backfill can reuse it
without an import cycle. ``build_decision_signal_payload_from_report`` and
``ProfileSource`` stay importable from here for backward compatibility.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from src.analyzer import AnalysisResult
from src.services.decision_signal_payload import (
    ProfileSource,
    build_decision_signal_payload_from_report,
)
from src.services.decision_signal_service import DecisionSignalService
from src.utils.sanitize import log_safe_exception


logger = logging.getLogger(__name__)

__all__ = [
    "ProfileSource",
    "build_decision_signal_payload_from_report",
    "extract_and_persist_from_analysis_result",
]


def extract_and_persist_from_analysis_result(
    result: AnalysisResult,
    *,
    context_snapshot: Dict[str, Any] | None = None,
    portfolio_context: Dict[str, Any] | None = None,
    source_report_id: int | None = None,
    trace_id: str,
    query_source: str,
    report_type: str,
    profile_source: ProfileSource,
    service: Optional[DecisionSignalService] = None,
) -> Dict[str, Any] | None:
    """Best-effort extract and persist a DecisionSignal from an analysis result."""

    try:
        payload = build_decision_signal_payload_from_report(
            result,
            context_snapshot=context_snapshot,
            portfolio_context=portfolio_context,
            source_report_id=source_report_id,
            trace_id=trace_id,
            query_source=query_source,
            report_type=report_type,
            profile_source=profile_source,
        )
        if payload is None:
            return None
        writer = service or DecisionSignalService()
        return writer.create_signal(payload)
    except Exception as exc:
        log_safe_exception(
            logger,
            "Decision signal extraction failed",
            exc,
            error_code="decision_signal_extraction_failed",
            level=logging.WARNING,
            trace_id=trace_id,
            context={"stock_code": getattr(result, "code", None) or "unknown"},
        )
        return None
