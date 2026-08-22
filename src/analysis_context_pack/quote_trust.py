# -*- coding: utf-8 -*-
"""Bounded field-trust analysis_input projection for AnalysisContextPack.

Issue #1129 remaining consumer slice: analysis reads the existing
``field_trust_analysis_input/1.0`` contract instead of treating a fresh but
conflicted quote as High-eligible ``available``. The full ``field_trust`` blob
is never copied as a quote item value.

This module maps upstream analysis_input only. It does not fetch quotes,
does not rewrite prices, and does not invent a second trust schema.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, Dict, List, Optional

from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

ANALYSIS_INPUT_SCHEMA_VERSION = "field_trust_analysis_input/1.0"
CONFIDENCE_HIGH = "high"
CONFIDENCE_LOW = "low"
METADATA_ABSENT_GAP = "metadata_absent"

QUOTE_TRUST_ITEM_SKIP_KEYS = frozenset({"field_trust", "analysis_input"})

_WARNING_PREFIX = "quote_trust_"


def missing_analysis_input() -> Dict[str, Any]:
    """Fail-closed projection when quote metadata is absent or unreadable."""
    return {
        "schema_version": ANALYSIS_INPUT_SCHEMA_VERSION,
        "confidence": CONFIDENCE_LOW,
        "gaps": [
            {
                "code": METADATA_ABSENT_GAP,
                "field": None,
                "detail": "quote carried no field-level trust metadata",
            }
        ],
        "conflict_count": 0,
        "failed_provider_count": 0,
    }


def is_analysis_input_payload(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    confidence = str(value.get("confidence") or "").strip().lower()
    return bool(confidence)


def resolve_quote_analysis_input(
    quote: Mapping[str, Any],
    quote_obj: Any = None,
) -> Dict[str, Any]:
    """Return the 1359 analysis_input contract for a quote dict or object.

    Preference order:
    1. ``field_trust.analysis_input`` already attached by finalize()
    2. legacy ``field_trust`` blob without analysis_input → rebuild via
       ``build_analysis_input`` (same producer as GET /trust)
    3. top-level ``analysis_input`` already projected onto the quote dict
    4. missing / unreadable payload → ``metadata_absent``
    """
    trust = quote.get("field_trust") if isinstance(quote, Mapping) else None
    if not isinstance(trust, dict) and quote_obj is not None:
        raw = getattr(quote_obj, "field_trust", None)
        if isinstance(raw, dict):
            trust = raw

    if isinstance(trust, dict):
        attached = trust.get("analysis_input")
        if is_analysis_input_payload(attached):
            return dict(attached)
        rebuilt = _rebuild_legacy_analysis_input(trust, quote_obj)
        if rebuilt is not None:
            return rebuilt
        return missing_analysis_input()

    top_level = quote.get("analysis_input") if isinstance(quote, Mapping) else None
    if is_analysis_input_payload(top_level):
        return dict(top_level)

    if quote_obj is not None and not isinstance(quote_obj, Mapping):
        projected = _project_from_quote_object(quote_obj)
        if projected is not None:
            return projected
    return missing_analysis_input()


def bound_analysis_input_metadata(analysis: Mapping[str, Any]) -> Dict[str, Any]:
    """Low-sensitivity pack metadata. Never includes provider/circuit blobs."""
    gaps = analysis.get("gaps") if isinstance(analysis.get("gaps"), list) else []
    gap_codes: List[str] = []
    for gap in gaps:
        if not isinstance(gap, Mapping):
            continue
        code = str(gap.get("code") or "").strip()
        if code and code not in gap_codes:
            gap_codes.append(code)
    confidence = str(analysis.get("confidence") or CONFIDENCE_LOW).strip().lower()
    return {
        "confidence": confidence or CONFIDENCE_LOW,
        "conflict_count": _non_negative_int(analysis.get("conflict_count")),
        "gap_codes": gap_codes,
        "failed_provider_count": _non_negative_int(
            analysis.get("failed_provider_count")
        ),
    }


def bound_analysis_input_from_quote(quote: Any) -> Optional[Dict[str, Any]]:
    """Project bounded analysis_input from a realtime quote object or dict."""
    if quote is None:
        return None
    if isinstance(quote, Mapping):
        quote_dict = dict(quote)
        quote_obj = None
    else:
        to_dict = getattr(quote, "to_dict", None)
        quote_dict = dict(to_dict()) if callable(to_dict) else {}
        quote_obj = quote
    return bound_analysis_input_metadata(
        resolve_quote_analysis_input(quote_dict, quote_obj)
    )


def analysis_input_is_high(analysis: Mapping[str, Any]) -> bool:
    confidence = str(analysis.get("confidence") or "").strip().lower()
    return confidence == CONFIDENCE_HIGH


def quote_trust_warning_codes(analysis: Mapping[str, Any]) -> List[str]:
    """Stable warning tokens for pack/prompt. No provider identities."""
    if analysis_input_is_high(analysis):
        return []
    warnings: List[str] = []
    metadata = bound_analysis_input_metadata(analysis)
    for code in metadata["gap_codes"]:
        token = _warning_token(code)
        if token not in warnings:
            warnings.append(token)
    if not warnings:
        warnings.append("quote_trust_confidence_not_high")
    return warnings


def _warning_token(code: str) -> str:
    cleaned = "".join(
        ch if ch.isalnum() or ch == "_" else "_"
        for ch in str(code).strip().lower()
    ).strip("_")
    return f"{_WARNING_PREFIX}{cleaned or 'degraded'}"


def _non_negative_int(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return number if number > 0 else 0


def _rebuild_legacy_analysis_input(
    trust: Mapping[str, Any],
    quote_obj: Any,
) -> Optional[Dict[str, Any]]:
    try:
        from src.data_provider.field_trust import build_analysis_input
    except ImportError:
        return None
    try:
        rebuilt = build_analysis_input(dict(trust), quote_obj)
    except Exception as exc:  # broad-exception: fallback_recorded - unreadable legacy payload is unknown, never high
        log_safe_exception(
            logger,
            "Legacy field-trust analysis_input rebuild failed",
            exc,
            error_code="quote_trust_legacy_rebuild_failed",
            level=logging.DEBUG,
        )
        return None
    if is_analysis_input_payload(rebuilt):
        return dict(rebuilt)
    return None


def _project_from_quote_object(quote_obj: Any) -> Optional[Dict[str, Any]]:
    try:
        from src.data_provider.field_trust import project_analysis_input
    except ImportError:
        return None
    try:
        projected = project_analysis_input(quote_obj)
    except Exception as exc:  # broad-exception: fallback_recorded - projection failure is unknown, never high
        log_safe_exception(
            logger,
            "Quote analysis_input projection failed",
            exc,
            error_code="quote_trust_project_failed",
            level=logging.DEBUG,
        )
        return None
    if is_analysis_input_payload(projected):
        return dict(projected)
    return None
