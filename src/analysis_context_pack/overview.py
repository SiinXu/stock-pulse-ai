# -*- coding: utf-8 -*-
"""Low-sensitivity public overview for Issue #1389 AnalysisContextPack P4."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Any, Dict, List, Optional

from src.analysis_context_pack.prompt import (
    SENSITIVE_MARKERS,
    analysis_context_pack_to_dict,
    get_analysis_context_pack_block_labels,
    iter_analysis_context_pack_block_keys,
)
from src.market_phase_summary import MARKET_PHASE_SUMMARY_KEY
from src.schemas.analysis_context_pack import ContextFieldStatus
from src.utils.sanitize import log_safe_exception


ANALYSIS_CONTEXT_PACK_OVERVIEW_KEY = "analysis_context_pack_overview"
_ALL_STATUSES = tuple(status.value for status in ContextFieldStatus)
_DATA_QUALITY_BLOCK_KEYS = {"quote", "daily_bars", "technical", "news", "fundamentals", "chip"}
logger = logging.getLogger(__name__)


def render_analysis_context_pack_overview(
    pack: Any,
    *,
    report_language: str = "zh",
) -> Optional[Dict[str, Any]]:
    """Project an AnalysisContextPack into a public, low-sensitivity overview."""
    try:
        payload = analysis_context_pack_to_dict(pack)
        subject = payload.get("subject")
        blocks = payload.get("blocks")
        if not isinstance(subject, Mapping) or not isinstance(blocks, Mapping):
            return None

        labels = get_analysis_context_pack_block_labels(report_language)
        overview_blocks: List[Dict[str, Any]] = []
        counts = {status: 0 for status in _ALL_STATUSES}

        for key in iter_analysis_context_pack_block_keys(blocks):
            block = blocks.get(key)
            if not isinstance(block, Mapping):
                continue
            status = _safe_status(block.get("status"))
            if status is None:
                continue

            counts[status] += 1
            overview_blocks.append(
                {
                    "key": _safe_text(key),
                    "label": labels.get(key, _safe_text(key)),
                    "status": status,
                    "source": _first_non_empty(
                        block.get("source"),
                        _first_item_field(block.get("items"), "source"),
                    ),
                    "warnings": _list_strings(block.get("warnings")),
                    "missing_reasons": _item_missing_reasons(block.get("items")),
                }
            )

        if not overview_blocks:
            return None

        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {}
        return {
            "pack_version": _safe_text(payload.get("pack_version")) or "1.0",
            "snapshot_id": _safe_text(payload.get("snapshot_id")) or None,
            "snapshot_revision": _safe_int(payload.get("snapshot_revision")),
            "as_of": _safe_text(payload.get("as_of")) or None,
            "created_at": _safe_text(payload.get("created_at")) or None,
            "subject": {
                "code": _safe_text(subject.get("code")),
                "stock_name": _safe_text(subject.get("stock_name")) or None,
                "market": _safe_text(subject.get("market")) or None,
            },
            "blocks": overview_blocks,
            "counts": counts,
            "data_quality": _sanitize_data_quality(payload.get("data_quality")),
            "warnings": _list_strings(_nested(payload, "data_quality", "warnings")),
            "metadata": {
                "trigger_source": _safe_text(metadata.get("trigger_source")) or None,
                "news_result_count": _safe_int(metadata.get("news_result_count")),
                "content_digest": _safe_text(metadata.get("content_digest")) or None,
                "snapshot_sealed": bool(metadata.get("snapshot_sealed"))
                if "snapshot_sealed" in metadata
                else None,
            },
        }
    except Exception as exc:  # broad-exception: fallback_recorded - rendering failure is logged before fallback
        log_safe_exception(
            logger,
            "Analysis context pack overview rendering failed",
            exc,
            error_code="analysis_context_pack_overview_render_failed",
            level=logging.DEBUG,
        )
        return None


def extract_analysis_context_pack_overview(context_snapshot: Any) -> Optional[Dict[str, Any]]:
    """Extract the persisted public overview from a context snapshot."""
    snapshot = _as_mapping(context_snapshot)
    if not snapshot:
        return None
    overview = snapshot.get(ANALYSIS_CONTEXT_PACK_OVERVIEW_KEY)
    if not isinstance(overview, Mapping):
        return None
    return _sanitize_persisted_overview(overview)


def sanitize_context_snapshot_for_api(context_snapshot: Any) -> Any:
    """Return a context snapshot without separately exposed public summary fields."""
    snapshot = _as_mapping(context_snapshot)
    if snapshot is not None:
        sanitized = dict(snapshot)
        sanitized.pop(ANALYSIS_CONTEXT_PACK_OVERVIEW_KEY, None)
        sanitized.pop(MARKET_PHASE_SUMMARY_KEY, None)
        sanitized.pop("daily_market_context_summary", None)
        sanitized.pop("portfolio_context", None)
        enhanced_context = sanitized.get("enhanced_context")
        if isinstance(enhanced_context, Mapping):
            safe_enhanced_context = dict(enhanced_context)
            safe_enhanced_context.pop("daily_market_context_summary", None)
            safe_enhanced_context.pop("portfolio_context", None)
            sanitized["enhanced_context"] = safe_enhanced_context
        return sanitized
    return context_snapshot


def _as_mapping(value: Any) -> Optional[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
        return parsed if isinstance(parsed, Mapping) else None
    return None


def _sanitize_persisted_overview(overview: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    subject = overview.get("subject")
    blocks = overview.get("blocks")
    if not isinstance(subject, Mapping) or not isinstance(blocks, list):
        return None

    subject_code = _safe_text(subject.get("code"))
    if not subject_code:
        return None

    overview_blocks: List[Dict[str, Any]] = []
    counts = {status: 0 for status in _ALL_STATUSES}
    for block in blocks:
        if not isinstance(block, Mapping):
            return None

        key = _safe_text(block.get("key"))
        status = _safe_status(block.get("status"))
        if not key or status is None:
            return None

        counts[status] += 1
        overview_blocks.append(
            {
                "key": key,
                "label": _safe_text(block.get("label")) or key,
                "status": status,
                "source": _safe_text(block.get("source")) or None,
                "warnings": _list_strings(block.get("warnings")),
                "missing_reasons": _list_strings(block.get("missing_reasons"), limit=3),
            }
        )

    if not overview_blocks:
        return None

    metadata = overview.get("metadata") if isinstance(overview.get("metadata"), Mapping) else {}
    sanitized = {
        "pack_version": _safe_text(overview.get("pack_version")) or "1.0",
        "snapshot_id": _safe_text(overview.get("snapshot_id")) or None,
        "snapshot_revision": _safe_int(overview.get("snapshot_revision")),
        "as_of": _safe_text(overview.get("as_of")) or None,
        "created_at": _safe_text(overview.get("created_at")) or None,
        "subject": {
            "code": subject_code,
            "stock_name": _safe_text(subject.get("stock_name")) or None,
            "market": _safe_text(subject.get("market")) or None,
        },
        "blocks": overview_blocks,
        "counts": counts,
        "warnings": _list_strings(overview.get("warnings")),
        "metadata": {
            "trigger_source": _safe_text(metadata.get("trigger_source")) or None,
            "news_result_count": _safe_int(metadata.get("news_result_count")),
            "content_digest": _safe_text(metadata.get("content_digest")) or None,
            "snapshot_sealed": bool(metadata.get("snapshot_sealed"))
            if "snapshot_sealed" in metadata
            else None,
        },
    }
    if "data_quality" in overview:
        sanitized["data_quality"] = _sanitize_data_quality(overview.get("data_quality"))
    return sanitized


def _sanitize_data_quality(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, Mapping):
        return None
    metadata = value.get("metadata")
    evidence = (
        metadata.get("validation_evidence")
        if isinstance(metadata, Mapping)
        else None
    )
    info_quality = None
    if isinstance(metadata, Mapping):
        raw_info = metadata.get("info_quality")
        if isinstance(raw_info, Mapping):
            info_quality = _sanitize_info_quality(raw_info)
    payload: Dict[str, Any] = {
        "overall_score": _safe_score(value.get("overall_score")),
        "level": _safe_quality_level(value.get("level")),
        "block_scores": _safe_block_scores(value.get("block_scores")),
        "limitations": _list_strings(value.get("limitations"), limit=5),
        "validation_evidence": _sanitize_validation_evidence(evidence),
    }
    if info_quality is not None:
        payload["info_quality"] = info_quality
        payload["info_quality_grade"] = info_quality.get("grade")
    return payload


def _sanitize_info_quality(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, Mapping):
        return None
    if value.get("schema_version") != "info-quality-v1":
        return None
    grade = _safe_text(value.get("grade")).upper()
    if grade not in {"A", "B", "C"}:
        return None
    dimensions_raw = value.get("dimensions")
    dimensions: Dict[str, str] = {}
    if isinstance(dimensions_raw, Mapping):
        for key in ("source_reliability", "timeliness", "consistency"):
            dim = _safe_text(dimensions_raw.get(key)).upper()
            if dim in {"A", "B", "C"}:
                dimensions[key] = dim
    if set(dimensions) != {"source_reliability", "timeliness", "consistency"}:
        return None
    if type(value.get("evidence_backed")) is not bool:
        return None
    return {
        "schema_version": "info-quality-v1",
        "grade": grade,
        "dimensions": dimensions,
        "evidence_backed": value.get("evidence_backed") is True,
        "reasons": [
            reason[:96]
            for reason in _list_strings(value.get("reasons"), limit=8)
        ],
        "source": _safe_text(value.get("source"))[:96] or None,
    }


def _sanitize_validation_evidence(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    overflow = len(value) > 24
    sanitized: List[Dict[str, Any]] = (
        [_invalid_validation_evidence()] if overflow else []
    )
    retained = 23 if overflow else 24
    for item in value[-retained:]:
        if not isinstance(item, Mapping):
            sanitized.append(_invalid_validation_evidence())
            continue
        if _safe_text(item.get("schema_version")) != "data_quality_evidence.v1":
            sanitized.append(_invalid_validation_evidence())
            continue
        data_type = _safe_text(item.get("data_type"))[:64]
        severity = _safe_text(item.get("severity"))
        rejected = item.get("rejected", False)
        issues = item.get("issues")
        reason_codes = []
        invalid = (
            not data_type
            or severity not in {"pass", "warn", "reject"}
            or type(rejected) is not bool
            or not isinstance(issues, list)
        )
        if isinstance(issues, list):
            for issue in issues[:24]:
                if not isinstance(issue, Mapping):
                    invalid = True
                    continue
                code = _safe_text(issue.get("code"))[:96]
                issue_severity = _safe_text(issue.get("severity"))
                if issue_severity not in {"pass", "warn", "reject"}:
                    invalid = True
                    continue
                if code and code not in reason_codes:
                    reason_codes.append(code)
                elif not code:
                    invalid = True
            if len(issues) > 24:
                invalid = True
        if invalid:
            sanitized.append(_invalid_validation_evidence())
            continue
        sanitized.append(
            {
                "schema_version": "data_quality_evidence.v1",
                "data_type": data_type,
                "severity": severity,
                "symbol": _safe_text(item.get("symbol"))[:64] or None,
                "provider": _safe_text(item.get("provider"))[:64] or None,
                "market": _safe_text(item.get("market"))[:32] or "unknown",
                "instrument_type": _safe_text(item.get("instrument_type"))[:32]
                or "equity",
                "rejected": rejected,
                "reason_codes": reason_codes,
            }
        )
    return sanitized


def _invalid_validation_evidence() -> Dict[str, Any]:
    return {
        "schema_version": "data_quality_evidence.v1",
        "data_type": "invalid",
        "severity": "reject",
        "symbol": None,
        "provider": None,
        "market": "unknown",
        "instrument_type": "equity",
        "rejected": True,
        "reason_codes": ["invalid_validation_evidence"],
    }


def _safe_status(value: Any) -> Optional[str]:
    text = _safe_text(value)
    return text if text in _ALL_STATUSES else None


def _safe_quality_level(value: Any) -> Optional[str]:
    text = _safe_text(value)
    return text if text in {"good", "usable", "limited", "poor"} else None


def _safe_score(value: Any) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if 0 <= value <= 100:
        return value
    return None


def _safe_block_scores(value: Any) -> Dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    result: Dict[str, int] = {}
    for key, score in value.items():
        text_key = _safe_text(key)
        safe_score = _safe_score(score)
        if text_key in _DATA_QUALITY_BLOCK_KEYS and safe_score is not None:
            result[text_key] = safe_score
    return result


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    lowered = text.lower()
    if any(marker in lowered for marker in SENSITIVE_MARKERS):
        return "[REDACTED]"
    return text


def _list_strings(value: Any, *, limit: int = 5) -> List[str]:
    if not isinstance(value, list):
        return []
    result: List[str] = []
    for item in value:
        text = _safe_text(item)
        if text and text not in result:
            result.append(text)
    return result[:limit]


def _first_non_empty(*values: Any) -> Optional[str]:
    for value in values:
        text = _safe_text(value)
        if text:
            return text
    return None


def _first_item_field(items: Any, field: str) -> Optional[str]:
    if not isinstance(items, Mapping):
        return None
    for item in items.values():
        if not isinstance(item, Mapping):
            continue
        value = _safe_text(item.get(field))
        if value:
            return value
    return None


def _item_missing_reasons(items: Any) -> List[str]:
    if not isinstance(items, Mapping):
        return []
    reasons: List[str] = []
    for item in items.values():
        if not isinstance(item, Mapping):
            continue
        reason = _safe_text(item.get("missing_reason"))
        if reason and reason not in reasons:
            reasons.append(reason)
    return reasons[:3]


def _nested(value: Any, *keys: str) -> Any:
    current = value
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _safe_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None
