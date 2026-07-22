# -*- coding: utf-8 -*-
"""Dashboard parsing functions rebound through the legacy runner facade."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any, Dict, Optional

from src.agent.dashboard_payload import (
    has_reserved_explanation_field,
    sanitize_agent_dashboard_payload,
)
from src.utils.data_processing import normalize_report_signal_attribution

if TYPE_CHECKING:
    from src.agent.runner import (
        DashboardParseResult,
        _try_parse_json,
        _try_repair_json,
    )

logger = logging.getLogger("src.agent.runner")


def parse_dashboard_json(content: str) -> Optional[Dict[str, Any]]:
    """Extract and parse a canonical Decision Dashboard JSON."""
    result = parse_dashboard_json_result(content)
    return result.payload if result is not None else None


def parse_dashboard_json_result(content: str) -> Optional[DashboardParseResult]:
    """Extract a dashboard and report whether a reserved field was removed.

    Tries multiple strategies:
    1. Markdown code blocks (```json ... ```)
    2. Raw JSON parse
    3. ``json_repair`` library
    4. Brace-delimited substring
    """
    if not content:
        return None

    from json_repair import repair_json

    # Strategy 1: markdown code blocks
    json_blocks = re.findall(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
    if json_blocks:
        for block in json_blocks:
            parsed = _try_parse_json(block)
            if parsed is not None:
                return _finalize_dashboard_parse_result(parsed)
            parsed = _try_repair_json(block, repair_json)
            if parsed is not None:
                return _finalize_dashboard_parse_result(parsed)

    # Strategy 2: raw parse
    parsed = _try_parse_json(content)
    if parsed is not None:
        return _finalize_dashboard_parse_result(parsed)

    # Strategy 3: json_repair on full content
    parsed = _try_repair_json(content, repair_json)
    if parsed is not None:
        return _finalize_dashboard_parse_result(parsed)

    # Strategy 4: brace-delimited
    brace_start = content.find("{")
    brace_end = content.rfind("}")
    if brace_start >= 0 and brace_end > brace_start:
        candidate = content[brace_start : brace_end + 1]
        parsed = _try_parse_json(candidate)
        if parsed is not None:
            return _finalize_dashboard_parse_result(parsed)
        parsed = _try_repair_json(candidate, repair_json)
        if parsed is not None:
            return _finalize_dashboard_parse_result(parsed)

    logger.warning("Failed to parse dashboard JSON from agent response")
    return None


def _finalize_dashboard_parse_result(payload: Dict[str, Any]) -> DashboardParseResult:
    """Sanitize reserved fields before normal dashboard normalization."""
    reserved_field_removed = has_reserved_explanation_field(payload)
    sanitized = sanitize_agent_dashboard_payload(payload)
    normalize_report_signal_attribution(sanitized)
    return DashboardParseResult(
        payload=sanitized,
        reserved_field_removed=reserved_field_removed,
    )
