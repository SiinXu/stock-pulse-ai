# -*- coding: utf-8 -*-
"""Adapter that optionally consumes T17 ``compare_analyses`` (issue #188 / T18).

T18 owns version selection and presentation. Comparison logic lives only in
``src/services/history_comparison_service.py`` (T17). This module never
implements deltas; it only resolves and invokes the T17 entrypoint when present.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Mapping, MutableMapping, Optional, Sequence

CompareAnalysesFn = Callable[[str, int, int], Any]


def resolve_compare_analyses() -> Optional[CompareAnalysesFn]:
    """Return T17 ``compare_analyses`` when the merged implementation is available."""
    try:
        from src.services import history_comparison_service as hcs
    except ImportError:
        return None
    fn = getattr(hcs, "compare_analyses", None)
    return fn if callable(fn) else None


def normalize_analysis_delta(
    raw: Any,
    *,
    base_record_id: int,
    target_record_id: int,
) -> MutableMapping[str, Any]:
    """Normalize a T17 AnalysisDelta-like object into a stable presentation dict."""
    if raw is None:
        raise TypeError("compare_analyses returned no AnalysisDelta")

    if hasattr(raw, "to_dict") and callable(raw.to_dict):
        data = raw.to_dict()
    elif hasattr(raw, "model_dump") and callable(raw.model_dump):
        data = raw.model_dump()
    elif hasattr(raw, "dict") and callable(raw.dict):
        data = raw.dict()
    elif isinstance(raw, Mapping):
        data = dict(raw)
    else:
        data = {
            "has_baseline": getattr(raw, "has_baseline", False),
            "conclusion_changes": getattr(raw, "conclusion_changes", None),
            "score_changes": getattr(raw, "score_changes", None),
            "evidence_changes": getattr(raw, "evidence_changes", None),
            "risk_changes": getattr(raw, "risk_changes", None),
            "base_record_id": getattr(raw, "base_record_id", base_record_id),
            "target_record_id": getattr(raw, "target_record_id", target_record_id),
            "base_query_id": getattr(raw, "base_query_id", None),
            "target_query_id": getattr(raw, "target_query_id", None),
            "stock_code": getattr(raw, "stock_code", None),
            "report_type": getattr(raw, "report_type", None),
            "baseline_status": getattr(raw, "baseline_status", None),
            "baseline_reason": getattr(raw, "baseline_reason", None),
            "has_material_changes": getattr(raw, "has_material_changes", False),
        }

    if not isinstance(data, Mapping):
        raise TypeError("compare_analyses returned an unsupported AnalysisDelta payload")

    def _optional_text(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _record_id(value: Any, fallback: int) -> int:
        try:
            normalized = int(value)
        except (TypeError, ValueError):
            normalized = fallback
        return normalized if normalized > 0 else fallback

    def _strict_scalar(value: Any) -> Any:
        if value is None or isinstance(value, (bool, int, str)):
            return value
        if isinstance(value, float):
            return value if math.isfinite(value) else None
        return _optional_text(value)

    def _nonnegative_int(value: Any) -> int:
        if value is None or isinstance(value, bool):
            return 0
        try:
            normalized = int(value)
        except (TypeError, ValueError, OverflowError):
            return 0
        return max(0, normalized)

    def _mapping(item: Any) -> Mapping[str, Any]:
        if hasattr(item, "to_dict") and callable(item.to_dict):
            item = item.to_dict()
        elif hasattr(item, "model_dump") and callable(item.model_dump):
            item = item.model_dump()
        if not isinstance(item, Mapping):
            raise TypeError("AnalysisDelta change items must be mappings")
        return item

    def _sequence(value: Any) -> Sequence[Any]:
        if value is None:
            return ()
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return value
        raise TypeError("AnalysisDelta change buckets must be sequences")

    def _value_changes(value: Any) -> list[dict[str, Any]]:
        projected: list[dict[str, Any]] = []
        for item in _sequence(value):
            change = _mapping(item)
            unavailable = change.get("unavailability")
            unavailable_map = unavailable if isinstance(unavailable, Mapping) else {}
            projected.append(
                {
                    "field": str(change.get("field") or "unknown"),
                    "base_value": _strict_scalar(change.get("base_value")),
                    "target_value": _strict_scalar(change.get("target_value")),
                    "delta": _strict_scalar(change.get("delta")),
                    "direction": str(change.get("direction") or "changed"),
                    "comparable": bool(change.get("comparable", True)),
                    "unavailability": (
                        {
                            "base": _optional_text(unavailable_map.get("base")),
                            "target": _optional_text(unavailable_map.get("target")),
                        }
                        if unavailable_map
                        else None
                    ),
                }
            )
        return projected

    def _list_changes(value: Any) -> list[dict[str, Any]]:
        projected: list[dict[str, Any]] = []
        for item in _sequence(value):
            change = _mapping(item)

            def _text_items(key: str) -> list[str]:
                values = _sequence(change.get(key))
                return [text for raw_value in values if (text := _optional_text(raw_value))]

            projected.append(
                {
                    "field": str(change.get("field") or "unknown"),
                    "added": _text_items("added"),
                    "removed": _text_items("removed"),
                    "unchanged": _text_items("unchanged"),
                    "added_total": _nonnegative_int(change.get("added_total")),
                    "removed_total": _nonnegative_int(change.get("removed_total")),
                    "unchanged_total": _nonnegative_int(change.get("unchanged_total")),
                    "output_truncated": bool(change.get("output_truncated", False)),
                }
            )
        return projected

    return {
        "has_baseline": bool(data.get("has_baseline")),
        "baseline_status": str(data.get("baseline_status") or "incomparable_structure"),
        "baseline_reason": _optional_text(data.get("baseline_reason")),
        "stock_code": _optional_text(data.get("stock_code")),
        "base_record_id": _record_id(data.get("base_record_id"), base_record_id),
        "target_record_id": _record_id(data.get("target_record_id"), target_record_id),
        "base_query_id": _optional_text(data.get("base_query_id")),
        "target_query_id": _optional_text(data.get("target_query_id")),
        "report_type": _optional_text(data.get("report_type")),
        "has_material_changes": bool(data.get("has_material_changes")),
        "conclusion_changes": _value_changes(data.get("conclusion_changes")),
        "score_changes": _value_changes(data.get("score_changes")),
        "evidence_changes": _list_changes(data.get("evidence_changes")),
        "risk_changes": _list_changes(data.get("risk_changes")),
    }


def invoke_compare_analyses(
    stock_code: str,
    base_record_id: int,
    target_record_id: int,
    *,
    compare_fn: Optional[CompareAnalysesFn] = None,
) -> tuple[str, Optional[MutableMapping[str, Any]]]:
    """Invoke T17 comparison when available.

    Returns:
        (engine_status, delta_or_none) where engine_status is ``ok`` or ``engine_pending``.
    """
    fn = compare_fn if compare_fn is not None else resolve_compare_analyses()
    if fn is None:
        return "engine_pending", None
    raw = fn(stock_code, base_record_id, target_record_id)
    return "ok", normalize_analysis_delta(
        raw,
        base_record_id=base_record_id,
        target_record_id=target_record_id,
    )
