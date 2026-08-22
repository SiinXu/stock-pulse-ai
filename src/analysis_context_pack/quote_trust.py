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
QUOTE_UNAVAILABLE_GAP = "quote_unavailable"

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


def unavailable_quote_analysis_input() -> Dict[str, Any]:
    """Fail-closed projection when realtime quote data never arrived."""
    return {
        "schema_version": ANALYSIS_INPUT_SCHEMA_VERSION,
        "confidence": CONFIDENCE_LOW,
        "gaps": [
            {
                "code": QUOTE_UNAVAILABLE_GAP,
                "field": None,
                "detail": "No realtime quote available from any provider",
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


def gap_codes_from_trust_warnings(warnings: Any) -> List[str]:
    """Recover bounded gap codes from public ``quote_trust_*`` warning tokens."""
    codes: List[str] = []
    if not isinstance(warnings, list):
        return codes
    for warning in warnings:
        token = str(warning or "").strip().lower()
        if not token.startswith(_WARNING_PREFIX):
            continue
        code = token[len(_WARNING_PREFIX) :].strip("_")
        if code and code not in codes:
            codes.append(code)
    return codes


def report_summary_from_analysis_input(
    analysis: Mapping[str, Any],
    *,
    source: Optional[str] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    """Low-sensitivity report summary. Never includes provider/circuit blobs.

    Accepts either the producer ``analysis_input`` (``gaps[]``) or the bounded
    pack metadata already stored on the quote block (``gap_codes``).
    """
    metadata = bound_analysis_input_metadata(analysis)
    gap_codes = list(metadata.get("gap_codes") or [])
    existing_codes = analysis.get("gap_codes")
    if not gap_codes and isinstance(existing_codes, list):
        for code in existing_codes:
            text = str(code or "").strip()
            if text and text not in gap_codes:
                gap_codes.append(text)
        metadata = dict(metadata)
        metadata["gap_codes"] = gap_codes
    confidence = str(metadata.get("confidence") or CONFIDENCE_LOW).strip().lower()
    return {
        "source": _optional_text(source),
        "status": _optional_text(status),
        "confidence": confidence or CONFIDENCE_LOW,
        "gap_codes": gap_codes,
        "conflict_count": _non_negative_int(metadata.get("conflict_count")),
        "failed_provider_count": _non_negative_int(
            metadata.get("failed_provider_count")
        ),
        "degraded": (confidence != CONFIDENCE_HIGH) or bool(gap_codes),
    }


def report_summary_from_pack(pack: Any) -> Optional[Dict[str, Any]]:
    """Build a report summary from pack quote metadata ``analysis_input``."""
    quote = _quote_block_from_pack(pack)
    if quote is None:
        return None
    source, status, analysis = quote
    if not isinstance(analysis, Mapping):
        status_text = str(status or "").strip().lower()
        analysis = (
            unavailable_quote_analysis_input()
            if status_text == "missing"
            else missing_analysis_input()
        )
    return report_summary_from_analysis_input(
        analysis,
        source=source,
        status=status,
    )


def report_summary_from_overview(overview: Any) -> Optional[Dict[str, Any]]:
    """Build a report summary from the public overview quote block.

    Prefers bounded ``metadata.analysis_input`` when a pack block leaked it
    into a test double. Production overview only carries source, status, and
    ``quote_trust_*`` warnings, which reconstruct the same gap codes without
    exposing ``field_trust`` or provider/circuit blobs.
    """
    snapshot = overview if isinstance(overview, Mapping) else None
    if snapshot is None:
        return None
    blocks = snapshot.get("blocks")
    if not isinstance(blocks, list):
        return None
    quote = None
    for block in blocks:
        if isinstance(block, Mapping) and str(block.get("key") or "") == "quote":
            quote = block
            break
    if quote is None:
        return None

    metadata = quote.get("metadata") if isinstance(quote.get("metadata"), Mapping) else {}
    analysis = metadata.get("analysis_input") if isinstance(metadata, Mapping) else None
    if isinstance(analysis, Mapping) and str(analysis.get("confidence") or "").strip():
        return report_summary_from_analysis_input(
            analysis,
            source=quote.get("source"),
            status=quote.get("status"),
        )

    gap_codes = gap_codes_from_trust_warnings(quote.get("warnings"))
    status = str(quote.get("status") or "").strip().lower()
    high_eligible = not gap_codes and status in ("", "available")
    if status == "stale" and "stale" not in gap_codes:
        gap_codes = [*gap_codes, "stale"]
    if status == "missing" and QUOTE_UNAVAILABLE_GAP not in gap_codes:
        gap_codes = [*gap_codes, QUOTE_UNAVAILABLE_GAP]
    confidence = CONFIDENCE_HIGH if high_eligible else CONFIDENCE_LOW
    return {
        "source": _optional_text(quote.get("source")),
        "status": _optional_text(quote.get("status")),
        "confidence": confidence,
        "gap_codes": gap_codes,
        "conflict_count": 1 if "conflict" in gap_codes else 0,
        "failed_provider_count": 1 if "provider_failed" in gap_codes else 0,
        "degraded": (confidence != CONFIDENCE_HIGH) or bool(gap_codes),
    }


def _optional_text(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


def _quote_block_from_pack(
    pack: Any,
) -> Optional[tuple[Optional[str], Optional[str], Optional[Mapping[str, Any]]]]:
    blocks = getattr(pack, "blocks", None)
    if isinstance(pack, Mapping):
        blocks = pack.get("blocks")
    if not isinstance(blocks, Mapping):
        return None
    quote = blocks.get("quote")
    if quote is None:
        return None
    if isinstance(quote, Mapping):
        metadata = quote.get("metadata") if isinstance(quote.get("metadata"), Mapping) else {}
        analysis = metadata.get("analysis_input") if isinstance(metadata, Mapping) else None
        status = quote.get("status")
        return (
            _optional_text(quote.get("source")),
            _optional_text(getattr(status, "value", status)),
            analysis if isinstance(analysis, Mapping) else None,
        )
    metadata = getattr(quote, "metadata", None)
    analysis = metadata.get("analysis_input") if isinstance(metadata, Mapping) else None
    status = getattr(quote, "status", None)
    return (
        _optional_text(getattr(quote, "source", None)),
        _optional_text(getattr(status, "value", status)),
        analysis if isinstance(analysis, Mapping) else None,
    )


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
