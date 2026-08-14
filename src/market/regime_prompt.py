# -*- coding: utf-8 -*-
"""Prompt rendering for explainable market-regime context (Issue #220)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, List

from src.report_language import normalize_report_language
from src.schemas.market_regime import MARKET_REGIME_SCHEMA_VERSION


_REGIME_LABELS_ZH = {
    "trending_up": "上升趋势",
    "trending_down": "下降趋势",
    "sideways": "震荡/区间",
    "volatile": "高波动",
    "unknown": "未知/不明确",
}

_REGIME_LABELS_EN = {
    "trending_up": "Trending up",
    "trending_down": "Trending down",
    "sideways": "Sideways / range",
    "volatile": "High volatility",
    "unknown": "Unknown / unclear",
}

_RISK_LABELS_ZH = {
    "risk_on": "偏进攻",
    "risk_off": "偏防守",
    "neutral": "中性",
    "unknown": "未知",
}

_RISK_LABELS_EN = {
    "risk_on": "risk-on",
    "risk_off": "risk-off",
    "neutral": "neutral",
    "unknown": "unknown",
}


def format_market_regime_prompt_section(
    context: Any,
    report_language: str = "zh",
) -> str:
    """Render a compact regime section with traceable rule evidence for the LLM."""
    if not isinstance(context, Mapping):
        return ""
    if context.get("schema_version") != MARKET_REGIME_SCHEMA_VERSION:
        return ""

    language = normalize_report_language(report_language)
    regime = str(context.get("regime") or "unknown").strip() or "unknown"
    status = str(context.get("status") or "unknown").strip() or "unknown"
    source = str(context.get("source") or "rules").strip() or "rules"
    confidence = context.get("confidence")
    risk = str(context.get("risk_posture") or "unknown").strip() or "unknown"
    method = str(context.get("method") or "deterministic_rules_v1").strip()
    rules_fired = _string_list(context.get("rules_fired"))
    focus_hints = _string_list(context.get("focus_hints"))
    missing = _string_list(context.get("missing_inputs"))
    evidence_ids = _evidence_rule_ids(context.get("evidence"))

    if language in ("en", "ko"):
        regime_label = _REGIME_LABELS_EN.get(regime, regime)
        risk_label = _RISK_LABELS_EN.get(risk, risk)
        lines = [
            "\n## Market Regime Context",
            f"- Regime: {regime_label} (`{regime}`)",
            f"- Status: {status}",
            f"- Source: {source}",
            f"- Method: {method}",
            f"- Risk posture: {risk_label}",
        ]
        if confidence is not None:
            lines.append(f"- Confidence: {confidence}")
        if rules_fired:
            lines.append(f"- Rules fired: {', '.join(rules_fired)}")
        if evidence_ids:
            lines.append(f"- Evidence rule ids: {', '.join(evidence_ids)}")
        if missing:
            lines.append(f"- Missing inputs: {', '.join(missing)}")
        if focus_hints:
            lines.append("- Analysis focus adjustments:")
            for hint in focus_hints[:5]:
                lines.append(f"  - {hint}")
        lines.append(
            "- Guardrail: regime labels are rule-based; if regime is `unknown`, "
            "state uncertainty explicitly and do not invent a directional regime."
        )
        return "\n".join(lines) + "\n"

    regime_label = _REGIME_LABELS_ZH.get(regime, regime)
    risk_label = _RISK_LABELS_ZH.get(risk, risk)
    lines = [
        "\n## 市场状态（Regime）上下文",
        f"- 状态标签: {regime_label}（`{regime}`）",
        f"- 判定状态: {status}",
        f"- 来源: {source}",
        f"- 方法: {method}",
        f"- 风险姿态: {risk_label}",
    ]
    if confidence is not None:
        lines.append(f"- 置信度: {confidence}")
    if rules_fired:
        lines.append(f"- 命中规则: {', '.join(rules_fired)}")
    if evidence_ids:
        lines.append(f"- 证据规则 ID: {', '.join(evidence_ids)}")
    if missing:
        lines.append(f"- 缺失输入: {', '.join(missing)}")
    if focus_hints:
        lines.append("- 分析侧重调整:")
        for hint in focus_hints[:5]:
            lines.append(f"  - {hint}")
    lines.append(
        "- 护栏: 状态由可解释规则判定；若为 `unknown`，必须显式说明不确定，禁止强行归类。"
    )
    return "\n".join(lines) + "\n"


def _string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    out: List[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            out.append(text)
    return out


def _evidence_rule_ids(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    ids: List[str] = []
    for item in value:
        if isinstance(item, Mapping):
            rule_id = str(item.get("rule_id") or "").strip()
            if rule_id:
                ids.append(rule_id)
    return list(dict.fromkeys(ids))
