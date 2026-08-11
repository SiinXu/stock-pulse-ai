# -*- coding: utf-8 -*-
"""Bounded public projection for corporate-event alert diagnostics."""

from __future__ import annotations

import json
import math
from typing import Any, Dict, Mapping, Optional
from urllib.parse import urlsplit


CORPORATE_EVENT_CATEGORIES = frozenset(
    {"earnings", "shareholder", "mna", "regulatory", "analyst"}
)
MAX_DIAGNOSTICS_BYTES = 65_536
MAX_PUBLIC_TEXT = 512
MAX_SOURCE_NAME = 100
MAX_SOURCE_URL = 2_048
MAX_SOURCE_ITEM_ID = 64


def _reject_non_finite_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def parse_diagnostics_object(diagnostics: Any) -> Optional[Dict[str, Any]]:
    """Parse only bounded strict-JSON diagnostic objects."""
    if isinstance(diagnostics, Mapping):
        return dict(diagnostics)
    if not isinstance(diagnostics, str):
        return None
    text = diagnostics.strip()
    if not text or not text.startswith("{") or len(text.encode("utf-8")) > MAX_DIAGNOSTICS_BYTES:
        return None
    try:
        parsed = json.loads(text, parse_constant=_reject_non_finite_constant)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return dict(parsed) if isinstance(parsed, dict) else None


def _text(value: Any, *, limit: int = MAX_PUBLIC_TEXT) -> Optional[str]:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split()).strip()
    return normalized[:limit] or None


def _finite_number(value: Any, *, minimum: float, maximum: float) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number) or number < minimum or number > maximum:
        return None
    return number


def _non_negative_int(value: Any, *, maximum: int = 100_000) -> Optional[int]:
    number = _finite_number(value, minimum=0, maximum=maximum)
    if number is None or not number.is_integer():
        return None
    return int(number)


def _category(value: Any) -> Optional[str]:
    normalized = _text(value, limit=32)
    return normalized if normalized in CORPORATE_EVENT_CATEGORIES else None


def _categories(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    output: list[str] = []
    for item in value[: len(CORPORATE_EVENT_CATEGORIES)]:
        normalized = _category(item)
        if normalized and normalized not in output:
            output.append(normalized)
    return output


def _source_url(value: Any) -> Optional[str]:
    normalized = _text(value, limit=MAX_SOURCE_URL)
    if not normalized:
        return None
    parsed = urlsplit(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return normalized


def _source_item_id(value: Any) -> Optional[str]:
    if isinstance(value, bool) or value is None:
        return None
    return _text(str(value), limit=MAX_SOURCE_ITEM_ID)


def _affected(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, Mapping):
        return None
    output: Dict[str, Any] = {
        "symbol": _text(value.get("symbol"), limit=64),
        "in_watchlist": value.get("in_watchlist") if isinstance(value.get("in_watchlist"), bool) else False,
        "in_portfolio": value.get("in_portfolio") if isinstance(value.get("in_portfolio"), bool) else False,
    }
    weight = _finite_number(value.get("weight_pct"), minimum=0, maximum=100)
    if weight is not None:
        output["weight_pct"] = weight
    return output


def _event_context(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, Mapping):
        return None
    output: Dict[str, Any] = {
        "what_happened": _text(value.get("what_happened")),
        "why_it_matters": _text(value.get("why_it_matters")),
        "event_category": _category(value.get("event_category")),
        "event_categories": _categories(value.get("event_categories")),
        "matched_count": _non_negative_int(value.get("matched_count")),
        "source_item_id": _source_item_id(value.get("source_item_id")),
        "source_name": _text(value.get("source_name"), limit=MAX_SOURCE_NAME),
        "source_url": _source_url(value.get("source_url")),
    }
    return {key: item for key, item in output.items() if item not in (None, [])} or None


def _impact_context(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, Mapping):
        return None
    output = _event_context(value) or {}
    output["degraded"] = bool(value.get("degraded")) if isinstance(value.get("degraded"), bool) else False
    affected = _affected(value.get("affected"))
    if affected is not None:
        output["affected"] = affected
    related_analysis = _text(value.get("related_analysis"))
    if related_analysis:
        output["related_analysis"] = related_analysis
    return output or None


def extract_event_display_contexts(diagnostics: Any) -> Dict[str, Optional[Dict[str, Any]]]:
    payload = parse_diagnostics_object(diagnostics) or {}
    return {
        "impact_context": _impact_context(payload.get("impact_context")),
        "event_context": _event_context(payload.get("event_context")),
    }
