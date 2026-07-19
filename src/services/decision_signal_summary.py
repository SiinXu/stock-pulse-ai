# -*- coding: utf-8 -*-
"""Low-sensitive DecisionSignal summaries for notifications and risk views."""

from __future__ import annotations

import math
from typing import Any, Dict, Optional

from src.report_language import normalize_report_language
from src.schemas.decision_signal_presentation import build_decision_signal_presentation
from src.utils.sanitize import sanitize_decision_signal_payload, sanitize_decision_signal_text


SUMMARY_FIELDS = (
    "id",
    "stock_code",
    "stock_name",
    "market",
    "action",
    "action_label",
    "confidence",
    "horizon",
    "status",
    "source_type",
    "source_report_id",
    "reason",
    "watch_conditions",
    "risk_summary",
    "created_at",
    "expires_at",
)


def summarize_decision_signal(
    item: Any,
    report_language: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Return a low-sensitive summary from a serialized DecisionSignal item."""

    if not isinstance(item, dict):
        return None
    summary: Dict[str, Any] = {}
    for field_name in SUMMARY_FIELDS:
        value = item.get(field_name)
        if value in (None, "", [], {}):
            continue
        summary[field_name] = sanitize_decision_signal_payload(value)
    presentation = build_decision_signal_presentation(
        item,
        report_language=report_language,
    )
    if presentation is not None:
        summary["presentation"] = sanitize_decision_signal_payload(presentation)
    return summary or None


def format_decision_signal_excerpt(summary: Any, report_language: str = "zh") -> str:
    """Format a compact public DecisionSignal excerpt for notification text."""

    if not isinstance(summary, dict) or not summary:
        return ""
    language = normalize_report_language(report_language)
    labels = {
        "zh": {
            "heading": "AI 决策信号",
            "action": "动作",
            "confidence": "置信度",
            "timestamp": "时间",
            "horizon": "周期",
            "reason": "理由",
            "watch_conditions": "观察条件",
            "risk_summary": "风险",
            "source_report_id": "报告",
        },
        "en": {
            "heading": "AI decision signal",
            "action": "Action",
            "confidence": "Confidence",
            "timestamp": "Time",
            "horizon": "Horizon",
            "reason": "Reason",
            "watch_conditions": "Watch",
            "risk_summary": "Risk",
            "source_report_id": "Report",
        },
        "ko": {
            "heading": "AI 의사결정 신호",
            "action": "조치",
            "confidence": "신뢰도",
            "timestamp": "생성일",
            "horizon": "투자 기간",
            "reason": "이유",
            "watch_conditions": "감시 조건",
            "risk_summary": "위험",
            "source_report_id": "출처 보고서",
        },
    }[language]

    presentation = _presentation_for_excerpt(summary, report_language=language)
    parts = []
    action_label = _public_scalar(
        presentation.get("label") if presentation else summary.get("action_label") or summary.get("action"),
        max_length=32,
    )
    if action_label:
        parts.append(f"{labels['action']}: {action_label}")
    confidence = _public_confidence(
        presentation.get("confidence") if presentation else summary.get("confidence")
    )
    if confidence:
        parts.append(f"{labels['confidence']}: {confidence}")
    timestamp = _public_scalar(
        presentation.get("timestamp") if presentation else summary.get("created_at"),
        max_length=64,
    )
    if timestamp:
        parts.append(f"{labels['timestamp']}: {timestamp}")
    horizon = _public_scalar(summary.get("horizon"), max_length=16)
    if horizon:
        parts.append(f"{labels['horizon']}: {horizon}")
    source_report_id = _public_scalar(summary.get("source_report_id"), max_length=24)
    if source_report_id:
        parts.append(f"{labels['source_report_id']}: #{source_report_id}")

    lines = [f"**{labels['heading']}**"]
    if parts:
        lines.append(" | ".join(parts))
    presentation_fields = {
        "reason": presentation.get("summary") if presentation else summary.get("reason"),
        "risk_summary": presentation.get("risk") if presentation else summary.get("risk_summary"),
    }
    for key in ("reason", "watch_conditions", "risk_summary"):
        max_length = None if key == "reason" else 120
        text = _public_text(presentation_fields.get(key, summary.get(key)), max_length=max_length)
        if text:
            lines.append(f"- {labels[key]}: {text}")
    return "\n".join(lines)


def _presentation_for_excerpt(
    summary: Dict[str, Any],
    *,
    report_language: str,
) -> Optional[Dict[str, Any]]:
    return build_decision_signal_presentation(summary, report_language=report_language)


def _public_scalar(value: Any, *, max_length: int) -> str:
    if value in (None, ""):
        return ""
    return sanitize_decision_signal_text(value)[:max_length]


def _public_confidence(value: Any) -> str:
    if value in (None, "") or isinstance(value, bool):
        return ""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return ""
    if not math.isfinite(parsed) or not 0.0 <= parsed <= 1.0:
        return ""
    return f"{parsed * 100:.0f}%"


def _public_text(value: Any, *, max_length: Optional[int]) -> str:
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, (list, tuple)):
        text = "；".join(str(item).strip() for item in value if str(item or "").strip())
    elif isinstance(value, dict):
        text = "；".join(
            f"{key}: {item}"
            for key, item in value.items()
            if str(key or "").strip() and str(item or "").strip()
        )
    else:
        text = str(value).strip()
    sanitized = sanitize_decision_signal_text(text)
    return sanitized if max_length is None else sanitized[:max_length]
