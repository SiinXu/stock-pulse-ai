# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Transport-neutral projection for analysis reports.

This private module is the single owner of report field projection and
normalization. API endpoints remain responsible for data access, task/history
authority, and validation against their public transport schemas.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any, Dict, Optional

from src.analysis_context_pack.overview import (
    extract_analysis_context_pack_overview,
    sanitize_context_snapshot_for_api,
)
from src.market.phase_summary import (
    extract_market_phase_summary,
    rebuild_market_phase_summary_for_stock_code,
)
from src.report_language import (
    get_localized_stock_name,
    get_sentiment_label,
    localize_operation_advice,
    localize_trend_prediction,
    normalize_report_language,
)
from src.schemas.decision_action import build_action_fields
from src.schemas.report_strata import project_report_strata_for_api
from src.schemas.report_structured_insights import (
    project_report_structured_insights_for_api,
)
from src.utils.data_processing import (
    extract_board_detail_fields,
    extract_fundamental_detail_fields,
    extract_market_structure_detail_field,
    extract_realtime_detail_fields,
    normalize_model_used,
    parse_json_field,
)


DisplayStockCode = Callable[[Any], str]


def _identity_stock_code(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _source_value(source: Any, key: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(key, default)
    return getattr(source, key, default)


def _datetime_to_iso(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str) and value.strip():
        return value
    return None


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _extract_guardrail_reason(raw_result: Any) -> Optional[str]:
    if not isinstance(raw_result, Mapping):
        return None
    for reason in (
        raw_result.get("guardrail_reason"),
        raw_result.get("downgrade_reason"),
        raw_result.get("decision_score_guardrail_reason"),
    ):
        if reason is not None:
            text = str(reason).strip()
            if text:
                return text

    metadata = raw_result.get("metadata")
    if isinstance(metadata, Mapping):
        metadata_reason = metadata.get("guardrail_reason") or metadata.get(
            "downgrade_reason"
        )
        if metadata_reason is not None:
            text = str(metadata_reason).strip()
            if text:
                return text
    return None


def _stringify_strategy_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _looks_like_raw_result_payload(candidate: Any) -> bool:
    return isinstance(candidate, Mapping) and any(
        key in candidate
        for key in (
            "analysis_summary",
            "operation_advice",
            "trend_prediction",
            "sentiment_score",
            "market_structure_context",
            "model_used",
            "dashboard",
            "action",
        )
    )


def _display_market_phase_summary(
    stock_code: Any,
    context_snapshot: Any,
    *,
    display_stock_code: DisplayStockCode,
) -> Any:
    return rebuild_market_phase_summary_for_stock_code(
        display_stock_code(stock_code),
        context_snapshot,
    )


def _project_market_phase_summary(
    stock_code: Any,
    context_snapshot: Any,
    fallback_summary: Any,
    *,
    display_stock_code: DisplayStockCode,
    prefer_fallback_summary: bool = False,
) -> Any:
    if prefer_fallback_summary and fallback_summary is not None:
        return fallback_summary
    if prefer_fallback_summary:
        return extract_market_phase_summary(context_snapshot)

    summary = _display_market_phase_summary(
        stock_code,
        context_snapshot,
        display_stock_code=display_stock_code,
    )
    if summary is None and fallback_summary is not None:
        summary = _display_market_phase_summary(
            stock_code,
            {"market_phase_summary": fallback_summary},
            display_stock_code=display_stock_code,
        )
    return summary


def prepare_analysis_report_for_enrichment(
    report_data: Mapping[str, Any],
    created_at: Any,
) -> Dict[str, Any]:
    """Supply task-owned creation time before canonical report projection."""

    enriched_report = dict(report_data)
    meta = dict(_mapping(enriched_report.get("meta")))
    if created_at and _datetime_to_iso(meta.get("created_at")) is None:
        meta["created_at"] = created_at
    enriched_report["meta"] = meta
    return enriched_report


def project_analysis_report(
    report_data: Mapping[str, Any],
    *,
    query_id: str,
    stock_code: str,
    stock_name: Optional[str] = None,
    context_snapshot: Any = None,
    fallback_fundamental_payload: Optional[Mapping[str, Any]] = None,
    fallback_raw_result_payload: Any = None,
    default_report_language: Optional[str] = "zh",
    display_stock_code: DisplayStockCode = _identity_stock_code,
    log_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Project one AnalysisService report payload into the canonical report dict."""

    meta_data = _mapping(report_data.get("meta"))
    summary_data = _mapping(report_data.get("summary"))
    strategy_data = _mapping(report_data.get("strategy"))
    details_data = _mapping(report_data.get("details"))
    parsed_context = parse_json_field(context_snapshot)
    context_data = _mapping(parsed_context)

    report_language = normalize_report_language(
        meta_data.get("report_language")
        or context_data.get("report_language")
        or default_report_language
    )
    raw_stock_code = meta_data.get("stock_code", stock_code)
    projected_stock_code = display_stock_code(raw_stock_code)
    localized_stock_name = get_localized_stock_name(
        meta_data.get("stock_name", stock_name),
        projected_stock_code,
        report_language,
    )

    realtime_fields = extract_realtime_detail_fields(context_snapshot)
    current_price = meta_data.get("current_price")
    if current_price is None:
        current_price = realtime_fields.get("current_price")
    change_pct = meta_data.get("change_pct")
    if change_pct is None:
        change_pct = realtime_fields.get("change_pct")

    market_phase_summary = _project_market_phase_summary(
        raw_stock_code,
        context_snapshot,
        meta_data.get("market_phase_summary"),
        display_stock_code=display_stock_code,
    )
    created_at = meta_data.get("created_at", datetime.now().isoformat())

    raw_result_data = details_data.get("raw_result")
    if not isinstance(raw_result_data, Mapping):
        raw_result_data = {}
        if isinstance(fallback_raw_result_payload, Mapping):
            nested_raw_result = fallback_raw_result_payload.get("raw_result")
            if isinstance(nested_raw_result, Mapping):
                raw_result_data = nested_raw_result
            elif _looks_like_raw_result_payload(fallback_raw_result_payload):
                raw_result_data = fallback_raw_result_payload
        if not raw_result_data:
            raw_result_data = details_data

    action_fields = build_action_fields(
        operation_advice=(
            raw_result_data.get("operation_advice")
            or details_data.get("operation_advice")
            or summary_data.get("operation_advice")
        ),
        explicit_action=(
            raw_result_data.get("action")
            or details_data.get("action")
            or summary_data.get("action")
        ),
        report_type=meta_data.get("report_type", "detailed"),
        report_language=report_language,
        sentiment_score=_first_non_empty(
            summary_data.get("sentiment_score"),
            raw_result_data.get("sentiment_score"),
            details_data.get("sentiment_score"),
        ),
        guardrail_reason=_extract_guardrail_reason(raw_result_data),
        align_with_score=True,
    )

    strategy = None
    if strategy_data:
        strategy = {
            "ideal_buy": _stringify_strategy_value(strategy_data.get("ideal_buy")),
            "secondary_buy": _stringify_strategy_value(
                strategy_data.get("secondary_buy")
            ),
            "stop_loss": _stringify_strategy_value(strategy_data.get("stop_loss")),
            "take_profit": _stringify_strategy_value(strategy_data.get("take_profit")),
        }

    extracted_fundamental = extract_fundamental_detail_fields(
        context_snapshot=context_snapshot,
        fallback_fundamental_payload=fallback_fundamental_payload,
    )
    extracted_boards = extract_board_detail_fields(
        context_snapshot=context_snapshot,
        fallback_fundamental_payload=fallback_fundamental_payload,
    )
    market_structure = None
    for raw_candidate in (
        fallback_raw_result_payload,
        raw_result_data,
        details_data,
    ):
        if raw_candidate is None:
            continue
        market_structure = extract_market_structure_detail_field(
            context_snapshot,
            raw_candidate,
        )
        if market_structure is not None:
            break

    analysis_context_pack_overview = extract_analysis_context_pack_overview(
        context_snapshot
    )
    api_context_snapshot = sanitize_context_snapshot_for_api(context_snapshot)
    projection_context = dict(log_context or {})
    projection_context.setdefault("path", "project_analysis_report")
    report_strata = project_report_strata_for_api(
        raw_result_data or details_data or fallback_raw_result_payload,
        language=report_language,
        log_context=projection_context,
    )
    structured_insights = project_report_structured_insights_for_api(
        raw_result_data,
        details_data,
        fallback_raw_result_payload,
        log_context=projection_context,
    )

    has_board_details = (
        bool(extracted_boards.get("belong_boards"))
        or extracted_boards.get("sector_rankings") is not None
        or extracted_boards.get("concept_rankings") is not None
    )
    details = None
    if (
        details_data
        or any(extracted_fundamental.values())
        or has_board_details
        or market_structure is not None
        or context_snapshot is not None
        or analysis_context_pack_overview is not None
        or report_strata is not None
        or structured_insights is not None
    ):
        details = {
            "news_content": details_data.get("news_summary")
            or details_data.get("news_content"),
            "raw_result": raw_result_data,
            "context_snapshot": api_context_snapshot,
            "analysis_context_pack_overview": analysis_context_pack_overview,
            "financial_report": extracted_fundamental.get("financial_report"),
            "dividend_metrics": extracted_fundamental.get("dividend_metrics"),
            "belong_boards": extracted_boards.get("belong_boards"),
            "sector_rankings": extracted_boards.get("sector_rankings"),
            "concept_rankings": extracted_boards.get("concept_rankings"),
            "market_structure": market_structure,
            "report_strata": report_strata,
            "structured_insights": structured_insights,
        }

    return {
        "meta": {
            "id": None,
            "query_id": meta_data.get("query_id", query_id),
            "stock_code": projected_stock_code,
            "stock_name": localized_stock_name,
            "report_type": meta_data.get("report_type", "detailed"),
            "report_language": report_language,
            "created_at": created_at,
            "current_price": current_price,
            "change_pct": change_pct,
            "model_used": normalize_model_used(meta_data.get("model_used")),
            "market_phase_summary": market_phase_summary,
        },
        "summary": {
            "analysis_summary": summary_data.get("analysis_summary"),
            "operation_advice": summary_data.get("operation_advice"),
            "action": action_fields["action"],
            "action_label": action_fields["action_label"],
            "trend_prediction": summary_data.get("trend_prediction"),
            "sentiment_score": summary_data.get("sentiment_score"),
            "sentiment_label": summary_data.get("sentiment_label"),
        },
        "strategy": strategy,
        "details": details,
    }


def project_persisted_analysis_report(
    source: Any,
    *,
    query_id: Optional[str] = None,
    context_snapshot: Any = None,
    raw_result: Any = None,
    fallback_fundamental_payload: Optional[Mapping[str, Any]] = None,
    resolved_action_authority: bool = False,
    resolved_language_authority: bool = False,
    localized_name_uses_display_code: bool = False,
    localize_summary_fields: bool = False,
    prefer_source_market_phase_summary: bool = False,
    always_include_details: bool = False,
    display_stock_code: DisplayStockCode = _identity_stock_code,
    log_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Project one persisted history/status source into the canonical report dict."""

    if context_snapshot is None:
        context_snapshot = _source_value(source, "context_snapshot")
    if raw_result is None:
        raw_result = _source_value(source, "raw_result")
    raw_result = parse_json_field(raw_result)
    raw_data = _mapping(raw_result)
    context_data = _mapping(parse_json_field(context_snapshot))

    source_stock_code = _source_value(source, "stock_code")
    if source_stock_code is None:
        source_stock_code = _source_value(source, "code", "")
    projected_stock_code = display_stock_code(source_stock_code)
    if resolved_language_authority:
        language_candidate = (
            _source_value(source, "report_language")
            or raw_data.get("report_language")
            or context_data.get("report_language")
        )
    else:
        language_candidate = raw_data.get("report_language")
    report_language = normalize_report_language(language_candidate)
    localized_name_code = (
        projected_stock_code
        if localized_name_uses_display_code
        else source_stock_code
    )
    localized_stock_name = get_localized_stock_name(
        _source_value(source, "stock_name", _source_value(source, "name")),
        localized_name_code,
        report_language,
    )
    realtime_fields = extract_realtime_detail_fields(context_snapshot)
    source_market_phase_summary = (
        _source_value(source, "market_phase_summary")
        if prefer_source_market_phase_summary
        else None
    )
    market_phase_summary = _project_market_phase_summary(
        source_stock_code,
        context_snapshot,
        source_market_phase_summary,
        display_stock_code=display_stock_code,
        prefer_fallback_summary=prefer_source_market_phase_summary,
    )

    sentiment_score = _source_value(source, "sentiment_score")
    operation_advice = _source_value(source, "operation_advice")
    if resolved_action_authority:
        action = _source_value(source, "action")
        action_label = _source_value(source, "action_label")
    else:
        action_fields = build_action_fields(
            operation_advice=raw_data.get("operation_advice")
            or operation_advice,
            explicit_action=raw_data.get("action"),
            report_type=_source_value(source, "report_type"),
            report_language=report_language,
            sentiment_score=(
                sentiment_score
                if sentiment_score is not None
                else raw_data.get("sentiment_score")
            ),
            guardrail_reason=_extract_guardrail_reason(raw_data),
            align_with_score=True,
        )
        action = action_fields["action"]
        action_label = action_fields["action_label"]

    extracted_fundamental = extract_fundamental_detail_fields(
        context_snapshot=context_snapshot,
        fallback_fundamental_payload=fallback_fundamental_payload,
    )
    extracted_boards = extract_board_detail_fields(
        context_snapshot=context_snapshot,
        fallback_fundamental_payload=fallback_fundamental_payload,
    )
    market_structure = extract_market_structure_detail_field(
        context_snapshot,
        raw_result,
    )
    analysis_context_pack_overview = extract_analysis_context_pack_overview(
        context_snapshot
    )
    api_context_snapshot = sanitize_context_snapshot_for_api(context_snapshot)
    projection_context = dict(log_context or {})
    projection_context.setdefault("path", "project_persisted_analysis_report")
    report_strata = project_report_strata_for_api(
        raw_result,
        language=report_language,
        log_context=projection_context,
    )
    structured_insights = project_report_structured_insights_for_api(
        raw_result,
        log_context=projection_context,
    )

    has_board_details = (
        bool(extracted_boards.get("belong_boards"))
        or extracted_boards.get("sector_rankings") is not None
        or extracted_boards.get("concept_rankings") is not None
    )
    details = None
    if (
        always_include_details
        or any(extracted_fundamental.values())
        or has_board_details
        or market_structure is not None
        or context_snapshot is not None
        or analysis_context_pack_overview is not None
        or report_strata is not None
        or structured_insights is not None
        or raw_result is not None
    ):
        details = {
            "news_content": _source_value(source, "news_content"),
            "raw_result": raw_result,
            "context_snapshot": api_context_snapshot,
            "analysis_context_pack_overview": analysis_context_pack_overview,
            "financial_report": extracted_fundamental.get("financial_report"),
            "dividend_metrics": extracted_fundamental.get("dividend_metrics"),
            "belong_boards": extracted_boards.get("belong_boards"),
            "sector_rankings": extracted_boards.get("sector_rankings"),
            "concept_rankings": extracted_boards.get("concept_rankings"),
            "market_structure": market_structure,
            "report_strata": report_strata,
            "structured_insights": structured_insights,
        }

    model_used = _source_value(source, "model_used")
    if model_used is None:
        model_used = raw_data.get("model_used")
    source_created_at = _source_value(source, "created_at")
    created_at = _datetime_to_iso(source_created_at)
    source_query_id = _source_value(source, "query_id", "")

    if localize_summary_fields:
        projected_operation_advice = localize_operation_advice(
            operation_advice,
            report_language,
        )
        projected_trend_prediction = localize_trend_prediction(
            _source_value(source, "trend_prediction"),
            report_language,
        )
        sentiment_label = (
            get_sentiment_label(sentiment_score, report_language)
            if sentiment_score is not None
            else _source_value(source, "sentiment_label")
        )
    else:
        projected_operation_advice = operation_advice
        projected_trend_prediction = _source_value(source, "trend_prediction")
        sentiment_label = None

    return {
        "meta": {
            "id": _source_value(source, "id"),
            "query_id": query_id if query_id is not None else source_query_id,
            "stock_code": projected_stock_code,
            "stock_name": localized_stock_name,
            "report_type": _source_value(source, "report_type"),
            "report_language": report_language,
            "created_at": created_at,
            "current_price": realtime_fields.get("current_price"),
            "change_pct": realtime_fields.get("change_pct"),
            "model_used": normalize_model_used(model_used),
            "market_phase_summary": market_phase_summary,
        },
        "summary": {
            "analysis_summary": _source_value(source, "analysis_summary"),
            "operation_advice": projected_operation_advice,
            "action": action,
            "action_label": action_label,
            "trend_prediction": projected_trend_prediction,
            "sentiment_score": sentiment_score,
            "sentiment_label": sentiment_label,
        },
        "strategy": {
            "ideal_buy": _stringify_strategy_value(
                _source_value(source, "ideal_buy")
            ),
            "secondary_buy": _stringify_strategy_value(
                _source_value(source, "secondary_buy")
            ),
            "stop_loss": _stringify_strategy_value(
                _source_value(source, "stop_loss")
            ),
            "take_profit": _stringify_strategy_value(
                _source_value(source, "take_profit")
            ),
        },
        "details": details,
    }


def normalize_fallback_analysis_report(
    report_data: Mapping[str, Any],
    *,
    stock_code: Any,
    display_stock_code: DisplayStockCode = _identity_stock_code,
) -> Dict[str, Any]:
    """Preserve the existing fail-open report while normalizing public fields."""

    normalized_report = dict(report_data)
    has_mapping_meta = isinstance(normalized_report.get("meta"), Mapping)
    meta = dict(_mapping(normalized_report.get("meta")))
    summary = dict(_mapping(normalized_report.get("summary")))
    details = _mapping(normalized_report.get("details"))
    raw_result = _mapping(details.get("raw_result"))
    report_language = normalize_report_language(
        meta.get("report_language") or raw_result.get("report_language")
    )
    action_fields = build_action_fields(
        operation_advice=raw_result.get("operation_advice")
        or summary.get("operation_advice"),
        explicit_action=raw_result.get("action") or summary.get("action"),
        report_type=meta.get("report_type"),
        report_language=report_language,
        sentiment_score=_first_non_empty(
            summary.get("sentiment_score"),
            raw_result.get("sentiment_score"),
        ),
        guardrail_reason=_extract_guardrail_reason(raw_result),
        align_with_score=True,
    )
    summary["action"] = action_fields["action"]
    summary["action_label"] = action_fields["action_label"]

    projected_stock_code = display_stock_code(stock_code)
    if has_mapping_meta and projected_stock_code:
        raw_meta_code = meta.get("stock_code") or stock_code
        meta["stock_code"] = projected_stock_code
        meta["market_phase_summary"] = _project_market_phase_summary(
            raw_meta_code,
            None,
            meta.get("market_phase_summary"),
            display_stock_code=display_stock_code,
        )

    if has_mapping_meta:
        normalized_report["meta"] = meta
    normalized_report["summary"] = summary
    return normalized_report
