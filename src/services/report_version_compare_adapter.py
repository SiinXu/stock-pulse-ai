# -*- coding: utf-8 -*-
"""Adapter that optionally consumes T17 ``compare_analyses`` (issue #188 / T18).

T18 owns version selection and presentation. Comparison logic lives only in
``src/services/history_comparison_service.py`` (T17). This module never
implements deltas; it only resolves and invokes the T17 entrypoint when present.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping, MutableMapping, Optional

CompareAnalysesFn = Callable[[str, str, str], Any]


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
    base_run_id: str,
    target_run_id: str,
) -> MutableMapping[str, Any]:
    """Normalize a T17 AnalysisDelta-like object into a stable presentation dict."""
    if raw is None:
        return {
            "has_baseline": False,
            "conclusion_changes": [],
            "score_changes": [],
            "evidence_changes": [],
            "risk_changes": [],
            "base_run_id": base_run_id,
            "target_run_id": target_run_id,
        }

    if hasattr(raw, "model_dump") and callable(raw.model_dump):
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
            "base_run_id": getattr(raw, "base_run_id", base_run_id),
            "target_run_id": getattr(raw, "target_run_id", target_run_id),
        }

    def _as_list(value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, tuple):
            return list(value)
        return [value]

    return {
        "has_baseline": bool(data.get("has_baseline")),
        "conclusion_changes": _as_list(data.get("conclusion_changes")),
        "score_changes": _as_list(data.get("score_changes")),
        "evidence_changes": _as_list(data.get("evidence_changes")),
        "risk_changes": _as_list(data.get("risk_changes")),
        "base_run_id": str(data.get("base_run_id") or base_run_id),
        "target_run_id": str(data.get("target_run_id") or target_run_id),
    }


def invoke_compare_analyses(
    stock_code: str,
    base_run_id: str,
    target_run_id: str,
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
    raw = fn(stock_code, base_run_id, target_run_id)
    return "ok", normalize_analysis_delta(
        raw,
        base_run_id=base_run_id,
        target_run_id=target_run_id,
    )
