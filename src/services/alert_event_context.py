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


def _deep_links(value: Any) -> Optional[Dict[str, str]]:
    if not isinstance(value, Mapping):
        return None
    allowed = ("event_alerts", "signals_rules", "stock_detail", "analysis", "source")
    output: Dict[str, str] = {}
    for key in allowed:
        text = _text(value.get(key), limit=MAX_SOURCE_URL if key == "source" else 256)
        if not text:
            continue
        if key == "source":
            url = _source_url(text)
            if url:
                output[key] = url
            continue
        if text.startswith("/") and "://" not in text and not text.startswith("//"):
            output[key] = text
    return output or None


def _auto_analysis(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, Mapping):
        return None
    status = _text(value.get("status"), limit=64)
    if not status:
        return None
    output: Dict[str, Any] = {
        "status": status,
        "submitted": bool(value.get("submitted")) if isinstance(value.get("submitted"), bool) else False,
    }
    stock_code = _text(value.get("stock_code"), limit=64)
    if stock_code:
        output["stock_code"] = stock_code
    pipeline = _text(value.get("pipeline"), limit=32)
    if pipeline:
        output["pipeline"] = pipeline
    reason = _text(value.get("reason"), limit=MAX_PUBLIC_TEXT)
    if reason:
        output["reason"] = reason
    return output


def _suggested_action(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, Mapping):
        return None
    action_code = _text(value.get("action_code"), limit=64)
    if not action_code:
        return None
    output: Dict[str, Any] = {"action_code": action_code}
    label = _text(value.get("label"), limit=128)
    if label:
        output["label"] = label
    rationale = _text(value.get("rationale"))
    if rationale:
        output["rationale"] = rationale
    deep_links = _deep_links(value.get("deep_links"))
    if deep_links:
        output["deep_links"] = deep_links
    relevance = value.get("relevance")
    if isinstance(relevance, list):
        cleaned = []
        for item in relevance[:5]:
            text = _text(item, limit=32)
            if text and text not in cleaned:
                cleaned.append(text)
        if cleaned:
            output["relevance"] = cleaned
    auto = _auto_analysis(value.get("auto_analysis"))
    if auto:
        output["auto_analysis"] = auto
    return output


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
    suggested = _suggested_action(value.get("suggested_action"))
    if suggested:
        output["suggested_action"] = suggested
    return output or None


def extract_event_display_contexts(diagnostics: Any) -> Dict[str, Optional[Dict[str, Any]]]:
    payload = parse_diagnostics_object(diagnostics) or {}
    top_suggested = _suggested_action(payload.get("suggested_action"))
    top_auto = _auto_analysis(payload.get("auto_analysis"))
    return {
        "impact_context": _impact_context(payload.get("impact_context")),
        "event_context": _event_context(payload.get("event_context")),
        "suggested_action": top_suggested,
        "auto_analysis": top_auto,
    }
