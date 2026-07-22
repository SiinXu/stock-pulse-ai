"""Deterministic sector analysis for structured market-review reports."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional


def build_sector_analysis_payload(
    *,
    as_of: str,
    indices: Any,
    top_sectors: Any,
    bottom_sectors: Any,
    top_concepts: Any,
    bottom_concepts: Any,
    rankings_supported: bool,
) -> Dict[str, Any]:
    """Build additive sector analysis from existing session ranking data."""
    benchmark_values = [
        value
        for value in (
            _coerce_number(getattr(index, "change_pct", None))
            for index in (indices or [])
        )
        if value is not None
    ]
    benchmark_change_pct = (
        round(sum(benchmark_values) / len(benchmark_values), 4)
        if benchmark_values
        else None
    )
    industries = (
        _build_analysis_items(
            top_sectors,
            bottom_sectors,
            category="industry",
            benchmark_change_pct=benchmark_change_pct,
        )
        if rankings_supported
        else []
    )
    concepts = (
        _build_analysis_items(
            top_concepts,
            bottom_concepts,
            category="concept",
            benchmark_change_pct=benchmark_change_pct,
        )
        if rankings_supported
        else []
    )
    has_rankings = bool(industries or concepts)

    if not rankings_supported:
        status = "not_supported"
        quality_status = "not_supported"
    elif has_rankings:
        status = "partial"
        quality_status = "partial"
    else:
        status = "unavailable"
        quality_status = "unavailable"

    available_fields = []
    if has_rankings:
        available_fields.extend(
            [
                "name",
                "category",
                "rank",
                "rank_side",
                "session_change_pct",
                "session_trend",
                "risk_level",
                "risk_flags",
            ]
        )
    if benchmark_change_pct is not None and has_rankings:
        available_fields.extend(
            [
                "benchmark_change_pct",
                "relative_strength_pct",
                "relative_strength",
            ]
        )

    missing_fields = [
        "index_namespace",
        "canonical_index_id",
        "index_code",
        "index_level",
        "etf_mapping",
        "historical_series",
        "capital_flow",
    ]
    if not has_rankings:
        missing_fields.append("sector_rankings")
    if benchmark_change_pct is None:
        missing_fields.append("benchmark_change_pct")

    return {
        "version": 1,
        "status": status,
        "scope": "session_rankings",
        "as_of": as_of,
        "benchmark": {
            "status": "available" if benchmark_change_pct is not None else "unavailable",
            "method": "major_index_average",
            "change_pct": benchmark_change_pct,
            "sample_size": len(benchmark_values),
        },
        "industries": industries,
        "concepts": concepts,
        "capital_flow": {
            "status": "not_available",
            "reason": "provider_contract_unavailable",
        },
        "data_quality": {
            "status": quality_status,
            "available_fields": available_fields,
            "missing_fields": missing_fields,
            "limitations": [
                "single_session_rankings_only",
                "no_namespace_aware_index_resolution",
                "no_canonical_index_id",
                "no_etf_mapping",
                "no_historical_trend",
                "no_sector_capital_flow",
            ],
        },
    }


def render_sector_analysis_markdown(
    analysis: Dict[str, Any],
    *,
    language: str,
    rank_limit: int = 2,
) -> str:
    """Render a bounded sector-analysis table for a market-review report."""
    report_rows = _select_report_rows(analysis, rank_limit=rank_limit)
    analysis_status = str(analysis.get("status") or "")
    if not report_rows and analysis_status != "unavailable":
        return ""

    use_english = language == "en"
    label_language = "en" if use_english else "zh"
    benchmark = analysis.get("benchmark", {})
    benchmark_change_pct = benchmark.get("change_pct")
    benchmark_text = _format_signed_pct(benchmark_change_pct)
    benchmark_count = int(benchmark.get("sample_size") or 0)

    if use_english:
        lines = [
            "#### Sector Index Analysis",
            (
                "> Scope: current-session industry/concept rankings versus "
                "the average move of available major indices. This is not a "
                "multi-session trend or fund-flow measure."
            ),
        ]
        if not report_rows:
            lines.append(
                "- **Status**: unavailable (no valid sector/theme rankings "
                "were returned for this run)"
            )
        lines.append(
            (
                f"- **Benchmark**: major-index average {benchmark_text} "
                f"({benchmark_count} indices)"
                if benchmark_count
                else "- **Benchmark**: unavailable"
            )
        )
        if report_rows:
            lines.extend(
                [
                    "",
                    "| Group / Rank | Sector / Theme | Session Trend | Relative Strength | Risk |",
                    "|--------------|----------------|---------------|-------------------|------|",
                ]
            )
    else:
        lines = [
            "#### 板块指数分析",
            (
                "> 口径：仅比较当日行业/概念涨跌榜与可用主要指数平均涨跌幅，"
                "不代表多日趋势或真实资金流。"
            ),
        ]
        if not report_rows:
            lines.append("- **状态**：不可用（本次未返回有效行业/概念排行）")
        lines.append(
            (
                f"- **比较基准**：主要指数平均 {benchmark_text}"
                f"（{benchmark_count} 个指数）"
                if benchmark_count
                else "- **比较基准**：暂无可用主要指数"
            )
        )
        if report_rows:
            lines.extend(
                [
                    "",
                    "| 类型/排名 | 板块/题材 | 当日趋势 | 相对强弱 | 风险 |",
                    "|-----------|-----------|----------|----------|------|",
                ]
            )

    for item in report_rows:
        category = item.get("category")
        rank_side = item.get("rank_side")
        if use_english:
            category_label = "Industry" if category == "industry" else "Concept"
            side_label = "Leader" if rank_side == "leader" else "Laggard"
        else:
            category_label = "行业" if category == "industry" else "概念"
            side_label = "领涨" if rank_side == "leader" else "领跌"

        lines.append(
            f"| {category_label} {side_label} #{item.get('rank', '-')} | "
            f"{item.get('name', '-')} | "
            f"{_format_signed_pct(item.get('session_change_pct'))} / "
            f"{_TREND_LABELS[label_language].get(str(item.get('session_trend')), '-')} | "
            f"{_format_signed_pct(item.get('relative_strength_pct'))} / "
            f"{_STRENGTH_LABELS[label_language].get(str(item.get('relative_strength')), '-')} | "
            f"{_RISK_LABELS[label_language].get(str(item.get('risk_level')), '-')} |"
        )

    if use_english:
        lines.extend(
            [
                "",
                (
                    "- **Data limits**: namespace-aware sector index codes/levels, "
                    "collision-free canonical IDs, ETF mappings, historical series, "
                    "and sector capital flow are unavailable from the current public "
                    "provider contract."
                ),
            ]
        )
    else:
        lines.extend(
            [
                "",
                (
                    "- **数据限制**：当前公共 provider 合同不提供板块指数命名空间/"
                    "代码/点位、无冲突规范 ID、ETF 映射、历史序列和板块资金流，"
                    "不据此推断。"
                ),
            ]
        )
    return "\n".join(lines)


def render_sector_analysis_prompt_context(
    analysis: Dict[str, Any],
    *,
    language: str,
    rank_limit: int = 2,
) -> str:
    """Render compact evidence for the LLM without duplicating report headings."""
    report_rows = _select_report_rows(analysis, rank_limit=rank_limit)
    analysis_status = str(analysis.get("status") or "")
    if not report_rows and analysis_status != "unavailable":
        return ""

    use_english = language == "en"
    benchmark = analysis.get("benchmark", {})
    benchmark_text = _format_signed_pct(benchmark.get("change_pct"))
    benchmark_count = int(benchmark.get("sample_size") or 0)
    if use_english:
        lines = ["Deterministic sector-analysis inputs:"]
        if not report_rows:
            lines.append(
                "- Status: unavailable; no valid sector/theme rankings were "
                "returned for this run."
            )
        lines.append(
            (
                f"- Session benchmark: {benchmark_text} "
                f"(average of {benchmark_count} major indices)"
                if benchmark_count
                else "- Session benchmark: unavailable"
            )
        )
    else:
        lines = ["确定性板块分析输入："]
        if not report_rows:
            lines.append("- 状态：不可用；本次未返回有效行业/概念排行。")
        lines.append(
            (
                f"- 当日比较基准：{benchmark_text}（{benchmark_count} 个主要指数平均）"
                if benchmark_count
                else "- 当日比较基准：不可用"
            )
        )

    for item in report_rows:
        if use_english:
            category = "Industry" if item.get("category") == "industry" else "Concept"
            side = "leader" if item.get("rank_side") == "leader" else "laggard"
        else:
            category = "行业" if item.get("category") == "industry" else "概念"
            side = "领涨" if item.get("rank_side") == "leader" else "领跌"
        lines.append(
            f"- {category} {side} #{item.get('rank', '-')}: {item.get('name', '-')}; "
            f"session {_format_signed_pct(item.get('session_change_pct'))}; "
            f"relative {_format_signed_pct(item.get('relative_strength_pct'))}; "
            f"trend={item.get('session_trend', 'unknown')}; "
            f"strength={item.get('relative_strength', 'unknown')}; "
            f"risk={item.get('risk_level', 'unknown')}"
        )

    lines.append(
        (
            "- Data boundary: session rankings only; namespace-aware sector index "
            "codes/levels, collision-free canonical IDs, ETF mappings, historical "
            "series, and sector fund flow are unavailable."
        )
        if use_english
        else (
            "- 数据边界：仅有当日排行；板块指数命名空间/代码/点位、无冲突规范 ID、"
            "ETF 映射、历史序列和板块资金流不可用。"
        )
    )
    return "\n".join(lines)


def _select_report_rows(
    analysis: Dict[str, Any],
    *,
    rank_limit: int,
) -> List[Dict[str, Any]]:
    """Select bounded valid rows shared by prompt and Markdown renderers."""
    selected = []
    for key in ("industries", "concepts"):
        for item in analysis.get(key, []):
            if not isinstance(item, dict):
                continue
            rank = _coerce_number(item.get("rank"))
            if rank is None or rank <= 0 or rank > rank_limit:
                continue
            selected.append(item)
    return selected


def _build_analysis_items(
    top_rows: Any,
    bottom_rows: Any,
    *,
    category: str,
    benchmark_change_pct: Optional[float],
) -> List[Dict[str, Any]]:
    """Normalize leader and laggard rankings into deterministic analysis rows."""
    rows: List[Dict[str, Any]] = []
    seen_names = set()
    for rank_side, raw_rows in (("leader", top_rows), ("laggard", bottom_rows)):
        if not isinstance(raw_rows, list):
            continue
        for rank, raw_item in enumerate(raw_rows, 1):
            if not isinstance(raw_item, dict):
                continue
            name = str(raw_item.get("name") or "").strip()
            change_pct = _coerce_number(raw_item.get("change_pct"))
            normalized_name = name.casefold()
            if not name or change_pct is None or normalized_name in seen_names:
                continue
            seen_names.add(normalized_name)

            relative_strength_pct = (
                round(change_pct - benchmark_change_pct, 4)
                if benchmark_change_pct is not None
                else None
            )
            risk_level, risk_flags = _classify_risk(
                change_pct=change_pct,
                relative_strength_pct=relative_strength_pct,
                rank_side=rank_side,
            )
            rows.append(
                {
                    "name": name,
                    "category": category,
                    "rank": rank,
                    "rank_side": rank_side,
                    "session_change_pct": round(change_pct, 4),
                    "benchmark_change_pct": benchmark_change_pct,
                    "relative_strength_pct": relative_strength_pct,
                    "session_trend": _classify_session_trend(change_pct),
                    "relative_strength": _classify_relative_strength(
                        relative_strength_pct
                    ),
                    "risk_level": risk_level,
                    "risk_flags": risk_flags,
                }
            )
    return rows


def _coerce_number(value: Any) -> Optional[float]:
    """Return a finite float for provider ranking values."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _classify_session_trend(change_pct: float) -> str:
    """Classify the current-session move without implying historical trend."""
    if change_pct >= 2.0:
        return "strong_up"
    if change_pct > 0:
        return "up"
    if change_pct <= -2.0:
        return "strong_down"
    if change_pct < 0:
        return "down"
    return "flat"


def _classify_relative_strength(relative_strength_pct: Optional[float]) -> str:
    """Classify relative strength against the available broad-index benchmark."""
    if relative_strength_pct is None:
        return "unknown"
    if relative_strength_pct >= 0.5:
        return "outperforming"
    if relative_strength_pct <= -0.5:
        return "underperforming"
    return "in_line"


def _classify_risk(
    *,
    change_pct: float,
    relative_strength_pct: Optional[float],
    rank_side: str,
) -> tuple[str, List[str]]:
    """Build conservative risk labels from session-only evidence."""
    risk_flags: List[str] = []
    if rank_side == "laggard":
        risk_flags.append("lagging_rank")
    if change_pct <= -2.0:
        risk_flags.append("downside_momentum")
    if change_pct >= 3.0:
        risk_flags.append("extension_risk")
    if relative_strength_pct is None:
        risk_flags.append("benchmark_unavailable")
    elif relative_strength_pct <= -1.0:
        risk_flags.append("market_underperformance")

    if change_pct <= -3.0 or (
        relative_strength_pct is not None and relative_strength_pct <= -2.0
    ):
        risk_level = "high"
    elif rank_side == "laggard" or change_pct < 0 or abs(change_pct) >= 3.0:
        risk_level = "moderate"
    else:
        risk_level = "low"
    return risk_level, risk_flags


def _format_signed_pct(value: Any) -> str:
    """Format optional percentages for stable Markdown tables."""
    number = _coerce_number(value)
    return "N/A" if number is None else f"{number:+.2f}%"


_TREND_LABELS = {
    "en": {
        "strong_up": "Strong up",
        "up": "Up",
        "flat": "Flat",
        "down": "Down",
        "strong_down": "Strong down",
    },
    "zh": {
        "strong_up": "强势上行",
        "up": "上行",
        "flat": "持平",
        "down": "下行",
        "strong_down": "明显下行",
    },
}

_STRENGTH_LABELS = {
    "en": {
        "outperforming": "Outperforming",
        "in_line": "In line",
        "underperforming": "Underperforming",
        "unknown": "Unknown",
    },
    "zh": {
        "outperforming": "跑赢",
        "in_line": "同步",
        "underperforming": "跑输",
        "unknown": "未知",
    },
}

_RISK_LABELS = {
    "en": {"low": "Low", "moderate": "Moderate", "high": "High"},
    "zh": {"low": "低", "moderate": "中", "high": "高"},
}
