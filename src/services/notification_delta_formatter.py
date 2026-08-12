"""Render bounded analysis deltas for reports and outbound notifications.

The presentation layer reads structured ``AnalysisDelta`` values from
``history_comparison_service`` only. It never recomputes field diffs.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Callable, Iterable, Optional, Sequence

from src.report_language import normalize_report_language
from src.services.history_comparison_service import (
    AnalysisDelta,
    BASELINE_MISSING_HISTORY,
    get_latest_delta,
)
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

MAX_STOCKS = 50
MAX_LINES_PER_STOCK = 8
MAX_VALUE_LENGTH = 120

_COPY = {
    "en": {
        "heading": "Changes since previous analysis",
        "first": "First analysis: no previous baseline is available.",
        "unchanged": "No material changes since the previous analysis.",
        "unavailable": "Comparison unavailable ({status}).",
        "unsafe": "Material changes were detected, but no safe values are available.",
        "added": "New {field}",
        "removed": "Removed {field}",
        "more": "Additional changes omitted from this compact section.",
    },
    "zh": {
        "heading": "较上次分析的变化",
        "first": "首次分析：暂无可用的历史基线。",
        "unchanged": "与上次分析相比无实质变化。",
        "unavailable": "暂时无法对比（{status}）。",
        "unsafe": "检测到变化，但没有可安全展示的值。",
        "added": "新增{field}",
        "removed": "移除{field}",
        "more": "其余变化已从本次精简段落中省略。",
    },
    "ko": {
        "heading": "이전 분석 대비 변경 사항",
        "first": "첫 분석: 사용할 수 있는 이전 기준이 없습니다.",
        "unchanged": "이전 분석 이후 중요한 변경 사항이 없습니다.",
        "unavailable": "비교할 수 없습니다({status}).",
        "unsafe": "변경 사항이 감지되었지만 안전하게 표시할 값이 없습니다.",
        "added": "새 {field}",
        "removed": "제거된 {field}",
        "more": "추가 변경 사항은 이 요약 섹션에서 생략되었습니다.",
    },
}

_FIELD_LABELS = {
    "en": {
        "operation_advice": "Advice",
        "action": "Action",
        "action_label": "Action label",
        "confidence_level": "Confidence",
        "stop_loss": "Stop loss",
        "take_profit": "Take profit",
        "ideal_buy": "Ideal buy",
        "sentiment_score": "Sentiment score",
        "key_points": "key points",
        "positive_catalysts": "catalysts",
        "verified_facts": "verified facts",
        "data_sources": "data sources",
        "risk_alerts": "risk alerts",
        "risk_warning": "risk warnings",
        "risks_counter_evidence": "risk evidence",
    },
    "zh": {
        "operation_advice": "操作建议",
        "action": "动作",
        "action_label": "动作标签",
        "confidence_level": "置信度",
        "stop_loss": "止损位",
        "take_profit": "止盈位",
        "ideal_buy": "理想买点",
        "sentiment_score": "情绪评分",
        "key_points": "核心要点",
        "positive_catalysts": "催化因素",
        "verified_facts": "已验证事实",
        "data_sources": "数据来源",
        "risk_alerts": "风险提示",
        "risk_warning": "风险警告",
        "risks_counter_evidence": "风险证据",
    },
    "ko": {
        "operation_advice": "투자 의견",
        "action": "조치",
        "action_label": "조치 라벨",
        "confidence_level": "신뢰도",
        "stop_loss": "손절가",
        "take_profit": "목표가",
        "ideal_buy": "적정 매수가",
        "sentiment_score": "심리 점수",
        "key_points": "핵심 포인트",
        "positive_catalysts": "상승 촉매",
        "verified_facts": "검증된 사실",
        "data_sources": "데이터 출처",
        "risk_alerts": "위험 알림",
        "risk_warning": "위험 경고",
        "risks_counter_evidence": "위험 근거",
    },
}


def _safe_text(value: Any) -> Optional[str]:
    if value is None or isinstance(value, bool):
        return str(value) if isinstance(value, bool) else None
    if isinstance(value, (int, float)):
        try:
            numeric = float(value)
        except (OverflowError, TypeError, ValueError):
            return None
        if not math.isfinite(numeric):
            return None
    text = " ".join(str(value).split())
    if not text:
        return None
    return text[:MAX_VALUE_LENGTH]


def _field_label(field: str, language: str) -> str:
    labels = _FIELD_LABELS[language]
    if field.startswith("dimension."):
        dimension = _safe_text(field.removeprefix("dimension.")) or "score"
        return f"Dimension {dimension}" if language == "en" else dimension
    return labels.get(field, _safe_text(field) or "Change")


def _value_change_line(change: Any, language: str) -> Optional[str]:
    if not bool(getattr(change, "comparable", True)):
        return None
    base = _safe_text(getattr(change, "base_value", None))
    target = _safe_text(getattr(change, "target_value", None))
    if base is None or target is None:
        return None
    delta = getattr(change, "delta", None)
    delta_text = ""
    if delta is not None:
        rendered_delta = _safe_text(delta)
        if rendered_delta is None:
            return None
        try:
            numeric_delta = float(delta)
        except (OverflowError, TypeError, ValueError):
            return None
        if not math.isfinite(numeric_delta):
            return None
        prefix = "+" if numeric_delta > 0 else ""
        delta_text = f" ({prefix}{rendered_delta})"
    return f"- {_field_label(str(getattr(change, 'field', '')), language)}: {base} -> {target}{delta_text}"


def _list_change_lines(change: Any, language: str) -> Iterable[str]:
    field = _field_label(str(getattr(change, "field", "")), language)
    copy = _COPY[language]
    for key, template_key in (("added", "added"), ("removed", "removed")):
        values = [text for value in getattr(change, key, ()) if (text := _safe_text(value))]
        if values:
            yield f"- {copy[template_key].format(field=field)}: {', '.join(values[:3])}"


def _render_delta(delta: AnalysisDelta, language: str) -> Sequence[str]:
    copy = _COPY[language]
    if not delta.has_baseline:
        if delta.baseline_status == BASELINE_MISSING_HISTORY:
            return (f"- {copy['first']}",)
        status = _safe_text(delta.baseline_status) or "unknown"
        return (f"- {copy['unavailable'].format(status=status)}",)
    if not delta.has_material_changes:
        return (f"- {copy['unchanged']}",)

    lines = []
    for change in (*delta.conclusion_changes, *delta.score_changes):
        line = _value_change_line(change, language)
        if line:
            lines.append(line)
    for change in (*delta.evidence_changes, *delta.risk_changes):
        lines.extend(_list_change_lines(change, language))
    if not lines:
        return (f"- {copy['unsafe']}",)
    if len(lines) > MAX_LINES_PER_STOCK:
        return (*lines[:MAX_LINES_PER_STOCK], f"- {copy['more']}")
    return tuple(lines)


def _resolve_language(results: Sequence[Any]) -> str:
    first_result = results[0] if results else None
    return normalize_report_language(
        getattr(first_result, "report_language", None) if first_result is not None else None
    )


def build_delta_section_markdown(
    results: Sequence[Any],
    report_type: Any,
    *,
    delta_loader: Optional[Callable[[str, str], AnalysisDelta]] = None,
    error_code: str = "analysis_delta_comparison_unavailable",
    log_message: str = "Analysis delta comparison unavailable",
) -> str:
    """Build the top-of-report delta section from persisted history only."""
    if not results:
        return ""
    loader = delta_loader or get_latest_delta
    language = _resolve_language(results)
    copy = _COPY[language]
    normalized_report_type = str(getattr(report_type, "value", report_type) or "").strip()
    sections = [f"## {copy['heading']}", ""]
    stock_count = 0

    for result in results[:MAX_STOCKS]:
        code = _safe_text(getattr(result, "code", None))
        if not code:
            continue
        stock_count += 1
        sections.extend([f"### {code}", ""])
        try:
            delta = loader(code, normalized_report_type)
            sections.extend(_render_delta(delta, language))
        except Exception as exc:  # broad-exception: fallback_recorded - comparison cannot block report/notification delivery
            log_safe_exception(
                logger,
                log_message,
                exc,
                error_code=error_code,
                level=logging.WARNING,
                context={"stock_code": code},
            )
            sections.append(f"- {copy['unavailable'].format(status='error')}")
        sections.append("")

    if stock_count == 0:
        return ""
    return "\n".join(sections).rstrip() + "\n"


def prepend_report_delta_section(
    report_content: str,
    results: Sequence[Any],
    report_type: Any,
    *,
    delta_loader: Optional[Callable[[str, str], AnalysisDelta]] = None,
    error_code: str = "report_delta_comparison_unavailable",
    log_message: str = "Report delta comparison unavailable",
) -> str:
    """Prepend the report-top delta section without blocking report generation.

    Idempotent when the report already begins with the delta heading (for example
    when opt-in notification delta-first runs after the report body already
    included the section).
    """
    if not report_content or not results:
        return report_content
    language = _resolve_language(results)
    heading = f"## {_COPY[language]['heading']}"
    stripped = report_content.lstrip()
    if stripped.startswith(heading):
        return report_content

    section = build_delta_section_markdown(
        results,
        report_type,
        delta_loader=delta_loader or get_latest_delta,
        error_code=error_code,
        log_message=log_message,
    )
    if not section:
        return report_content
    return f"{section}\n---\n\n{report_content}"


def format_delta_first_notification(
    report_content: str,
    results: Sequence[Any],
    report_type: Any,
    *,
    delta_loader: Optional[Callable[[str, str], AnalysisDelta]] = None,
) -> str:
    """Prepend compact persisted deltas without allowing comparison failure to block delivery."""
    return prepend_report_delta_section(
        report_content,
        results,
        report_type,
        delta_loader=delta_loader or get_latest_delta,
        error_code="notification_delta_comparison_unavailable",
        log_message="Notification delta comparison unavailable",
    )


__all__ = [
    "build_delta_section_markdown",
    "format_delta_first_notification",
    "prepend_report_delta_section",
]
