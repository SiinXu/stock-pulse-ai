# -*- coding: utf-8 -*-
"""
===================================
Report Engine - History Comparison Service
===================================

Fetches recent analysis signal changes per stock for report rendering.
Excludes current record via exclude_query_id.

Also provides deterministic multi-dimension deltas between two analysis runs
(``compare_analyses`` / ``get_latest_delta``) for Issue #148 / T17.
"""

from __future__ import annotations

import logging
import math
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from src.report_language import normalize_report_language
from src.schemas.decision_action import display_action_fields
from src.schemas.decision_scale import extract_decision_guardrail_reason
from src.utils.data_processing import parse_json_field
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)


def _database_manager():
    """Lazy import so unit tests of pure diff helpers do not require storage init."""
    from src.storage import DatabaseManager

    return DatabaseManager

# Baseline status values for AnalysisDelta.
BASELINE_OK = "ok"
BASELINE_MISSING_HISTORY = "missing_history"
BASELINE_MISSING_BASE = "missing_base"
BASELINE_MISSING_TARGET = "missing_target"
BASELINE_INCOMPARABLE = "incomparable_structure"

# Direction labels for numeric score / level changes.
DIRECTION_UP = "up"
DIRECTION_DOWN = "down"
DIRECTION_UNCHANGED = "unchanged"
DIRECTION_CHANGED = "changed"
DIRECTION_UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class ValueChange:
    """Single scalar or categorical field change."""

    field: str
    base_value: Any
    target_value: Any
    delta: Optional[float] = None
    direction: str = DIRECTION_UNCHANGED
    comparable: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ListChange:
    """Set-style list diff (evidence items, risk items, data sources)."""

    field: str
    added: Tuple[str, ...] = ()
    removed: Tuple[str, ...] = ()
    unchanged: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field,
            "added": list(self.added),
            "removed": list(self.removed),
            "unchanged": list(self.unchanged),
        }

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.removed)


@dataclass
class AnalysisDelta:
    """
    Deterministic delta between two analysis history runs.

    ``has_baseline`` is False when comparison is impossible (first run, missing
    history, missing run ids, or incomparable structure). That state must never
    be confused with ``has_baseline=True`` and empty change buckets (no material
    change between two valid runs).
    """

    has_baseline: bool
    conclusion_changes: List[ValueChange] = field(default_factory=list)
    score_changes: List[ValueChange] = field(default_factory=list)
    evidence_changes: List[ListChange] = field(default_factory=list)
    risk_changes: List[ListChange] = field(default_factory=list)
    base_run_id: Optional[str] = None
    target_run_id: Optional[str] = None
    stock_code: Optional[str] = None
    baseline_status: str = BASELINE_OK
    baseline_reason: Optional[str] = None
    has_material_changes: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "has_baseline": self.has_baseline,
            "baseline_status": self.baseline_status,
            "baseline_reason": self.baseline_reason,
            "stock_code": self.stock_code,
            "base_run_id": self.base_run_id,
            "target_run_id": self.target_run_id,
            "has_material_changes": self.has_material_changes,
            "conclusion_changes": [c.to_dict() for c in self.conclusion_changes],
            "score_changes": [c.to_dict() for c in self.score_changes],
            "evidence_changes": [c.to_dict() for c in self.evidence_changes],
            "risk_changes": [c.to_dict() for c in self.risk_changes],
        }


def _empty_delta(
    *,
    stock_code: Optional[str],
    base_run_id: Optional[str],
    target_run_id: Optional[str],
    baseline_status: str,
    baseline_reason: str,
) -> AnalysisDelta:
    """Return an explicit no-baseline delta (not an empty 'no change' result)."""
    return AnalysisDelta(
        has_baseline=False,
        conclusion_changes=[],
        score_changes=[],
        evidence_changes=[],
        risk_changes=[],
        base_run_id=base_run_id,
        target_run_id=target_run_id,
        stock_code=stock_code,
        baseline_status=baseline_status,
        baseline_reason=baseline_reason,
        has_material_changes=False,
    )


def _record_to_signal(
    record: Any,
    *,
    report_language: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Convert AnalysisHistory record to signal dict. Skip on parse error."""
    raw_result = parse_json_field(getattr(record, "raw_result", None))
    if not isinstance(raw_result, dict):
        raw_result = {}

    operation_advice = raw_result.get("operation_advice") or getattr(record, "operation_advice", None)
    explicit_action = raw_result.get("action")
    action_label = raw_result.get("action_label")
    resolved_report_language = normalize_report_language(
        report_language
        or raw_result.get("report_language")
        or getattr(record, "report_language", None)
    )
    action_fields = display_action_fields(
        operation_advice=operation_advice,
        explicit_action=explicit_action,
        action_label=action_label,
        report_type=getattr(record, "report_type", None),
        report_language=resolved_report_language,
        sentiment_score=getattr(record, "sentiment_score", None),
        guardrail_reason=extract_decision_guardrail_reason(raw_result),
    )

    try:
        return {
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "query_id": record.query_id,
            "sentiment_score": record.sentiment_score,
            "operation_advice": record.operation_advice,
            "action": action_fields["action"],
            "action_label": action_fields["action_label"],
            "trend_prediction": record.trend_prediction,
        }
    except Exception as exc:
        log_safe_exception(
            logger,
            "History comparison record skipped",
            exc,
            error_code="history_comparison_record_invalid",
            level=logging.DEBUG,
            context={"query_id": getattr(record, "query_id", None) or "unknown"},
        )
        return None


def get_signal_changes(
    code: str,
    limit: int = 5,
    exclude_query_id: Optional[str] = None,
    *,
    report_language: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Get recent signal changes for a single stock.

    Args:
        code: Stock code
        limit: Max records to return
        exclude_query_id: Exclude record with this query_id (e.g. current run)

    Returns:
        List of signal dicts (created_at, sentiment_score, operation_advice, trend_prediction)
    """
    db = _database_manager().get_instance()
    records = db.get_analysis_history(
        code=code,
        days=90,
        limit=limit,
        exclude_query_id=exclude_query_id,
    )
    out = []
    for r in records:
        sig = _record_to_signal(r, report_language=report_language)
        if sig:
            out.append(sig)
    return out


def get_signal_changes_batch(
    codes: List[str],
    limit: int = 5,
    exclude_query_ids: Optional[Dict[str, str]] = None,
    *,
    report_language: Optional[str] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Get recent signal changes for multiple stocks.

    Args:
        codes: Stock codes
        limit: Max records per stock
        exclude_query_ids: Map code -> query_id to exclude per stock

    Returns:
        Dict mapping code -> list of signal dicts
    """
    exclude_query_ids = exclude_query_ids or {}
    db = _database_manager().get_instance()
    result: Dict[str, List[Dict[str, Any]]] = {c: [] for c in codes}
    for code in codes:
        exclude = exclude_query_ids.get(code)
        records = db.get_analysis_history(
            code=code,
            days=90,
            limit=limit,
            exclude_query_id=exclude,
        )
        for r in records:
            sig = _record_to_signal(r, report_language=report_language)
            if sig:
                result[code].append(sig)
    return result


def _as_mapping(value: Any) -> Dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _finite_number(value: Any) -> Optional[float]:
    """
    Coerce a value to a finite float.

    Non-finite floats (NaN, ±Inf) and non-numeric inputs return None so callers
    can treat them as missing rather than inventing a numeric delta.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text:
            return None
        try:
            number = float(text)
        except ValueError:
            return None
        return number if math.isfinite(number) else None
    return None


def _normalize_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _split_text_items(value: Any) -> List[str]:
    """Split key_points / data_sources style free text into stable tokens."""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        items: List[str] = []
        for item in value:
            text = _normalize_text(item)
            if text:
                items.append(text)
        return items
    text = _normalize_text(value)
    if not text:
        return []
    # Prefer common list separators used in persisted analysis text.
    for separator in ("\n", "；", ";", "，", ","):
        if separator in text:
            parts = [p.strip() for p in text.split(separator)]
            return [p for p in parts if p]
    return [text]


def _string_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned] if cleaned else []
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        out: List[str] = []
        for item in value:
            if item is None:
                continue
            if isinstance(item, Mapping):
                # VerifiedFact-like dicts: prefer statement text.
                statement = (
                    item.get("statement")
                    or item.get("text")
                    or item.get("fact")
                    or item.get("summary")
                )
                text = _normalize_text(statement)
            else:
                text = _normalize_text(item)
            if text:
                out.append(text)
        return out
    text = _normalize_text(value)
    return [text] if text else []


def _resolve_sniper_value(record: Any, raw: Mapping[str, Any], key: str) -> Any:
    """Prefer denormalized AnalysisHistory columns, then dashboard sniper points."""
    column_value = getattr(record, key, None)
    if column_value is not None:
        return column_value
    dashboard = _as_mapping(raw.get("dashboard"))
    battle_plan = _as_mapping(dashboard.get("battle_plan"))
    sniper = _as_mapping(battle_plan.get("sniper_points"))
    if key in sniper:
        return sniper.get(key)
    # Some payloads nest sniper points under dashboard root.
    root_sniper = _as_mapping(dashboard.get("sniper_points"))
    if key in root_sniper:
        return root_sniper.get(key)
    return raw.get(key)


def _extract_report_strata(raw: Mapping[str, Any]) -> Dict[str, Any]:
    dashboard = _as_mapping(raw.get("dashboard"))
    strata = dashboard.get("report_strata")
    if not isinstance(strata, Mapping):
        strata = raw.get("report_strata")
    return _as_mapping(strata)


def _extract_comparable_snapshot(record: Any) -> Optional[Dict[str, Any]]:
    """
    Project an AnalysisHistory row into the fields this service can compare.

    Returns None when the row cannot yield a usable comparison surface
    (for example missing code identity).
    """
    if record is None:
        return None

    code = _normalize_text(getattr(record, "code", None))
    query_id = _normalize_text(getattr(record, "query_id", None))
    if not code or not query_id:
        return None

    raw = parse_json_field(getattr(record, "raw_result", None))
    if not isinstance(raw, dict):
        raw = {}

    dashboard = _as_mapping(raw.get("dashboard"))
    intelligence = _as_mapping(dashboard.get("intelligence"))
    data_perspective = _as_mapping(dashboard.get("data_perspective"))
    trend_status = _as_mapping(data_perspective.get("trend_status"))
    strata = _extract_report_strata(raw)

    operation_advice = raw.get("operation_advice") or getattr(record, "operation_advice", None)
    explicit_action = raw.get("action")
    action_label = raw.get("action_label")
    report_language = normalize_report_language(
        raw.get("report_language") or getattr(record, "report_language", None)
    )

    raw_sentiment = getattr(record, "sentiment_score", None)
    if raw_sentiment is None:
        raw_sentiment = raw.get("sentiment_score")
    # Action resolution expects a finite score; non-finite values are treated as missing.
    finite_sentiment = _finite_number(raw_sentiment)
    action_fields = display_action_fields(
        operation_advice=operation_advice,
        explicit_action=explicit_action,
        action_label=action_label,
        report_type=getattr(record, "report_type", None),
        report_language=report_language,
        sentiment_score=finite_sentiment,
        guardrail_reason=extract_decision_guardrail_reason(raw),
    )

    # Preserve the raw sentiment for numeric delta comparison (finite coercion happens later).
    sentiment = raw_sentiment

    confidence = raw.get("confidence_level")
    if confidence is None:
        confidence = getattr(record, "confidence_level", None)

    stop_loss = _resolve_sniper_value(record, raw, "stop_loss")
    take_profit = _resolve_sniper_value(record, raw, "take_profit")
    ideal_buy = _resolve_sniper_value(record, raw, "ideal_buy")

    key_points = raw.get("key_points")
    if key_points is None:
        key_points = getattr(record, "key_points", None)

    risk_warning = raw.get("risk_warning")
    if risk_warning is None:
        risk_warning = getattr(record, "risk_warning", None)

    data_sources = raw.get("data_sources")
    if data_sources is None:
        data_sources = getattr(record, "data_sources", None)

    risk_alerts = intelligence.get("risk_alerts")
    positive_catalysts = intelligence.get("positive_catalysts")
    verified_facts = strata.get("verified_facts")
    risks_counter_evidence = strata.get("risks_counter_evidence")

    trend_score = trend_status.get("trend_score")
    # Optional multi-dimension scores when present on dashboard.
    dimension_scores: Dict[str, Any] = {}
    for dim_key in ("trend_score", "volume_score", "momentum_score", "fundamental_score"):
        if dim_key == "trend_score" and trend_score is not None:
            dimension_scores[dim_key] = trend_score
            continue
        candidate = data_perspective.get(dim_key)
        if candidate is None:
            nested = _as_mapping(data_perspective.get(dim_key.replace("_score", "_status")))
            candidate = nested.get("score") or nested.get(dim_key)
        if candidate is not None:
            dimension_scores[dim_key] = candidate

    return {
        "code": code,
        "query_id": query_id,
        "operation_advice": _normalize_text(operation_advice),
        "action": _normalize_text(action_fields.get("action")),
        "action_label": _normalize_text(action_fields.get("action_label")),
        "confidence_level": _normalize_text(confidence),
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "ideal_buy": ideal_buy,
        "sentiment_score": sentiment,
        "dimension_scores": dimension_scores,
        "key_points": _split_text_items(key_points),
        "positive_catalysts": _string_list(positive_catalysts),
        "verified_facts": _string_list(verified_facts),
        "data_sources": _split_text_items(data_sources),
        "risk_alerts": _string_list(risk_alerts),
        "risk_warning": _split_text_items(risk_warning),
        "risks_counter_evidence": _string_list(risks_counter_evidence),
    }


def _value_change(
    field_name: str,
    base_value: Any,
    target_value: Any,
    *,
    numeric: bool = False,
) -> Optional[ValueChange]:
    if numeric:
        base_num = _finite_number(base_value)
        target_num = _finite_number(target_value)
        # Both missing after finite coercion: treat as no material change and skip.
        if base_num is None and target_num is None:
            # If either side had a non-empty raw value that failed finite checks,
            # surface an unavailable comparison rather than silent equality.
            base_present = base_value is not None and _normalize_text(base_value) is not None
            target_present = target_value is not None and _normalize_text(target_value) is not None
            if base_present or target_present:
                return ValueChange(
                    field=field_name,
                    base_value=base_value,
                    target_value=target_value,
                    delta=None,
                    direction=DIRECTION_UNAVAILABLE,
                    comparable=False,
                )
            return None
        if base_num is None or target_num is None:
            # One side missing/non-finite: change is reported but not numeric-delta capable.
            if base_num == target_num:
                return None
            return ValueChange(
                field=field_name,
                base_value=base_num if base_num is not None else base_value,
                target_value=target_num if target_num is not None else target_value,
                delta=None,
                direction=DIRECTION_UNAVAILABLE,
                comparable=False,
            )
        delta = target_num - base_num
        if delta > 0:
            direction = DIRECTION_UP
        elif delta < 0:
            direction = DIRECTION_DOWN
        else:
            return None
        return ValueChange(
            field=field_name,
            base_value=base_num,
            target_value=target_num,
            delta=delta,
            direction=direction,
            comparable=True,
        )

    base_norm = base_value
    target_norm = target_value
    if isinstance(base_value, str) or isinstance(target_value, str) or base_value is None or target_value is None:
        base_norm = _normalize_text(base_value)
        target_norm = _normalize_text(target_value)
    if base_norm == target_norm:
        return None
    return ValueChange(
        field=field_name,
        base_value=base_norm,
        target_value=target_norm,
        delta=None,
        direction=DIRECTION_CHANGED,
        comparable=True,
    )


def _list_change(field_name: str, base_items: Sequence[str], target_items: Sequence[str]) -> Optional[ListChange]:
    base_set = {item for item in base_items if item}
    target_set = {item for item in target_items if item}
    added = tuple(sorted(target_set - base_set))
    removed = tuple(sorted(base_set - target_set))
    unchanged = tuple(sorted(base_set & target_set))
    if not added and not removed:
        return None
    return ListChange(
        field=field_name,
        added=added,
        removed=removed,
        unchanged=unchanged,
    )


def _diff_snapshots(base: Mapping[str, Any], target: Mapping[str, Any]) -> AnalysisDelta:
    conclusion_fields = (
        ("operation_advice", False),
        ("action", False),
        ("action_label", False),
        ("confidence_level", False),
        ("stop_loss", True),
        ("take_profit", True),
        ("ideal_buy", True),
    )
    conclusion_changes: List[ValueChange] = []
    for name, numeric in conclusion_fields:
        change = _value_change(name, base.get(name), target.get(name), numeric=numeric)
        if change is not None:
            conclusion_changes.append(change)

    score_changes: List[ValueChange] = []
    score_change = _value_change(
        "sentiment_score",
        base.get("sentiment_score"),
        target.get("sentiment_score"),
        numeric=True,
    )
    if score_change is not None:
        score_changes.append(score_change)

    base_dims = _as_mapping(base.get("dimension_scores"))
    target_dims = _as_mapping(target.get("dimension_scores"))
    dim_keys = sorted(set(base_dims) | set(target_dims))
    for dim_key in dim_keys:
        change = _value_change(
            f"dimension.{dim_key}",
            base_dims.get(dim_key),
            target_dims.get(dim_key),
            numeric=True,
        )
        if change is not None:
            score_changes.append(change)

    evidence_changes: List[ListChange] = []
    for name in ("key_points", "positive_catalysts", "verified_facts", "data_sources"):
        change = _list_change(name, base.get(name) or [], target.get(name) or [])
        if change is not None:
            evidence_changes.append(change)

    risk_changes: List[ListChange] = []
    for name in ("risk_alerts", "risk_warning", "risks_counter_evidence"):
        change = _list_change(name, base.get(name) or [], target.get(name) or [])
        if change is not None:
            risk_changes.append(change)

    has_material = bool(conclusion_changes or score_changes or evidence_changes or risk_changes)
    return AnalysisDelta(
        has_baseline=True,
        conclusion_changes=conclusion_changes,
        score_changes=score_changes,
        evidence_changes=evidence_changes,
        risk_changes=risk_changes,
        base_run_id=str(base.get("query_id") or "") or None,
        target_run_id=str(target.get("query_id") or "") or None,
        stock_code=str(base.get("code") or target.get("code") or "") or None,
        baseline_status=BASELINE_OK,
        baseline_reason=None,
        has_material_changes=has_material,
    )


def _lookup_history_record(stock_code: str, run_id: str) -> Optional[Any]:
    """Load one AnalysisHistory row by stock code + query_id (run id)."""
    code = _normalize_text(stock_code)
    query_id = _normalize_text(run_id)
    if not code or not query_id:
        return None
    db = _database_manager().get_instance()
    records = db.get_analysis_history(code=code, query_id=query_id, limit=1)
    if not records:
        return None
    return records[0]


def compare_analyses(stock_code: str, base_run_id: str, target_run_id: str) -> AnalysisDelta:
    """
    Compare two analysis history runs for the same stock.

    Run ids are ``AnalysisHistory.query_id`` values. Comparison is deterministic
    (field-level diff only; no LLM summary). When either run is missing or a
    usable snapshot cannot be built, returns ``has_baseline=False`` with an
    explicit ``baseline_status`` — never a silent empty "no change" delta.
    """
    code = _normalize_text(stock_code)
    base_id = _normalize_text(base_run_id)
    target_id = _normalize_text(target_run_id)

    if not code:
        return _empty_delta(
            stock_code=stock_code,
            base_run_id=base_run_id,
            target_run_id=target_run_id,
            baseline_status=BASELINE_INCOMPARABLE,
            baseline_reason="stock_code is required",
        )
    if not base_id or not target_id:
        return _empty_delta(
            stock_code=code,
            base_run_id=base_id,
            target_run_id=target_id,
            baseline_status=BASELINE_INCOMPARABLE,
            baseline_reason="base_run_id and target_run_id are required",
        )

    base_record = _lookup_history_record(code, base_id)
    if base_record is None:
        return _empty_delta(
            stock_code=code,
            base_run_id=base_id,
            target_run_id=target_id,
            baseline_status=BASELINE_MISSING_BASE,
            baseline_reason=f"base run not found for stock_code={code!r} run_id={base_id!r}",
        )

    target_record = _lookup_history_record(code, target_id)
    if target_record is None:
        return _empty_delta(
            stock_code=code,
            base_run_id=base_id,
            target_run_id=target_id,
            baseline_status=BASELINE_MISSING_TARGET,
            baseline_reason=f"target run not found for stock_code={code!r} run_id={target_id!r}",
        )

    base_snap = _extract_comparable_snapshot(base_record)
    target_snap = _extract_comparable_snapshot(target_record)
    if base_snap is None or target_snap is None:
        return _empty_delta(
            stock_code=code,
            base_run_id=base_id,
            target_run_id=target_id,
            baseline_status=BASELINE_INCOMPARABLE,
            baseline_reason="one or both runs lack a comparable analysis snapshot",
        )

    return _diff_snapshots(base_snap, target_snap)


def get_latest_delta(stock_code: str) -> AnalysisDelta:
    """
    Compare the two most recent analysis runs for a stock.

    Convenience wrapper around ``compare_analyses``. When fewer than two history
    rows exist, returns an explicit no-baseline result (first analysis / missing
    history) rather than an empty no-change delta.
    """
    code = _normalize_text(stock_code)
    if not code:
        return _empty_delta(
            stock_code=stock_code,
            base_run_id=None,
            target_run_id=None,
            baseline_status=BASELINE_INCOMPARABLE,
            baseline_reason="stock_code is required",
        )

    db = _database_manager().get_instance()
    # days window wide enough for typical re-analysis cadence; still only needs 2 rows.
    records = db.get_analysis_history(code=code, days=365, limit=2)
    if not records:
        return _empty_delta(
            stock_code=code,
            base_run_id=None,
            target_run_id=None,
            baseline_status=BASELINE_MISSING_HISTORY,
            baseline_reason="no analysis history for stock",
        )
    if len(records) < 2:
        only_id = _normalize_text(getattr(records[0], "query_id", None))
        return _empty_delta(
            stock_code=code,
            base_run_id=None,
            target_run_id=only_id,
            baseline_status=BASELINE_MISSING_HISTORY,
            baseline_reason="only one analysis history row; no prior baseline",
        )

    # get_analysis_history orders by created_at desc → [latest, previous, ...]
    target_record, base_record = records[0], records[1]
    target_id = _normalize_text(getattr(target_record, "query_id", None))
    base_id = _normalize_text(getattr(base_record, "query_id", None))
    if not target_id or not base_id:
        return _empty_delta(
            stock_code=code,
            base_run_id=base_id,
            target_run_id=target_id,
            baseline_status=BASELINE_INCOMPARABLE,
            baseline_reason="latest history rows missing query_id",
        )
    return compare_analyses(code, base_id, target_id)


# Public surface for T17 / T18 consumers.
__all__ = [
    "AnalysisDelta",
    "BASELINE_INCOMPARABLE",
    "BASELINE_MISSING_BASE",
    "BASELINE_MISSING_HISTORY",
    "BASELINE_MISSING_TARGET",
    "BASELINE_OK",
    "ListChange",
    "ValueChange",
    "compare_analyses",
    "get_latest_delta",
    "get_signal_changes",
    "get_signal_changes_batch",
]
