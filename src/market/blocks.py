# -*- coding: utf-8 -*-
"""Pure market-review markdown block builders.

Issue #1085 step 5 extracts the markdown block builders that
``src.market.formatters`` (step 4) deliberately left behind. Prompt
assembly (``src.market.prompts``), LLM generation, snapshots, and fetch
orchestration remain in ``src.market.analyzer``. This module must not
import ``MarketAnalyzer``; every builder receives ``owner`` and calls
sibling helpers through it so class-level and instance-level overrides
stay effective. ``overview`` is typed ``Any`` for the same reason, matching
``src.market.degradation``.
"""

from __future__ import annotations

from typing import Any, Dict, List

__all__ = (
    "build_stats_block",
    "build_indices_block",
    "build_sector_block",
    "build_sector_analysis_block",
    "build_news_block",
)


def build_stats_block(owner: Any, overview: Any) -> str:
    """Build market statistics block."""
    has_stats = overview.up_count or overview.down_count or overview.total_amount
    if not has_stats:
        return ""
    if owner._get_review_language() == "en":
        light = owner.build_market_light_snapshot(overview)
        return "\n".join(
            [
                f"- **Market Signal**: {light['score']}/100 "
                f"({light['temperature_label']}, {light['label']})",
                f"- **Drivers**: {'; '.join(light['reasons'])}",
                f"- **Guidance**: {light['guidance']}",
                "",
                f"- **Breadth**: Advancers {overview.up_count} / Decliners {overview.down_count} / "
                f"Flat {overview.flat_count}; "
                f"Limit-up {overview.limit_up_count} / Limit-down {overview.limit_down_count}; "
                f"Turnover {overview.total_amount:.0f} ({owner._get_turnover_unit_label()})",
            ]
        )
    light = owner.build_market_light_snapshot(overview)
    score, label = light["score"], light["temperature_label"]
    participation = overview.up_count + overview.down_count
    up_ratio = overview.up_count / participation if participation else 0.0
    limit_spread = overview.limit_up_count - overview.limit_down_count
    lines = [
        f"- **盘面信号**：{score}/100（{label}，{light['label']}）",
        f"- **信号依据**：{'；'.join(light['reasons'])}",
        f"- **操作建议**：{light['guidance']}",
        "",
        "| 指标 | 数值 | 观察 |",
        "|------|------|------|",
        f"| 上涨/下跌/平盘 | {overview.up_count} / {overview.down_count} / {overview.flat_count} | 上涨占比(不含平盘) {up_ratio:.1%} |",
        f"| 涨停/跌停 | {overview.limit_up_count} / {overview.limit_down_count} | 涨跌停差 {limit_spread:+d} |",
        f"| 两市成交额 | {overview.total_amount:.0f} 亿 | {owner._describe_turnover(overview.total_amount)} |",
    ]
    return "\n".join(lines)


def build_indices_block(owner: Any, overview: Any) -> str:
    """构建指数行情表格"""
    if not overview.indices:
        return ""
    if owner._get_review_language() == "en":
        lines = [
            f"| Index | Last | Change % | Open | High | Low | Amplitude | Turnover ({owner._get_turnover_unit_label()}) |",
            "|-------|------|----------|------|------|-----|-----------|-----------------|",
        ]
    else:
        lines = [
            "| 指数 | 最新 | 涨跌幅 | 开盘 | 最高 | 最低 | 振幅 | 成交额(亿) |",
            "|------|------|--------|------|------|------|------|-----------|",
        ]
    for idx in overview.indices:
        arrow = owner._get_index_change_arrow(idx.change_pct)
        amount_raw = idx.amount or 0.0
        amount_str = owner._format_turnover_value(amount_raw)
        lines.append(
            f"| {idx.name} | {idx.current:.2f} | {arrow} {idx.change_pct:+.2f}% | "
            f"{owner._format_optional_number(idx.open)} | {owner._format_optional_number(idx.high)} | "
            f"{owner._format_optional_number(idx.low)} | {owner._format_optional_pct(idx.amplitude)} | {amount_str} |"
        )
    return "\n".join(lines)


def build_sector_block(owner: Any, overview: Any) -> str:
    """Build industry and concept ranking blocks."""
    lines = []
    language = owner._get_review_language()

    def append_ranking(title: str, name_label: str, rows: List[Dict]) -> None:
        if not rows:
            return
        if lines:
            lines.append("")
        lines.extend([
            title,
            f"| {'Rank' if language == 'en' else '排名'} | {name_label} | {'Change' if language == 'en' else '涨跌幅'} |",
            "|------|------|--------|",
        ])
        for rank, item in enumerate(rows[:5], 1):
            lines.append(
                f"| {rank} | {item.get('name', '-')} | {owner._format_signed_pct(item.get('change_pct'))} |"
            )

    if language == "en":
        append_ranking("#### Leading Industry Sectors", "Sector", overview.top_sectors)
        append_ranking("#### Lagging Industry Sectors", "Sector", overview.bottom_sectors)
        append_ranking("#### Leading Concept Themes", "Concept", overview.top_concepts)
        append_ranking("#### Lagging Concept Themes", "Concept", overview.bottom_concepts)
    else:
        append_ranking("#### 行业板块领涨 Top 5", "行业板块", overview.top_sectors)
        append_ranking("#### 行业板块领跌 Top 5", "行业板块", overview.bottom_sectors)
        append_ranking("#### 概念板块领涨 Top 5", "概念板块", overview.top_concepts)
        append_ranking("#### 概念板块领跌 Top 5", "概念板块", overview.bottom_concepts)
    analysis_block = owner._build_sector_analysis_block(overview)
    if analysis_block:
        if lines:
            lines.append("")
        lines.append(analysis_block)
    return "\n".join(lines)


def build_sector_analysis_block(
    owner: Any, overview: Any, *, renderer: Any
) -> str:
    """Render the bounded sector-analysis contract for market-review reports.

    ``renderer`` is injected by the ``MarketAnalyzer`` facade so this module
    does not import the grandfathered ``src.market_sector_analysis`` seam.
    """
    return renderer(
        owner.build_sector_analysis(overview),
        language=owner._get_review_language(),
    )


def build_news_block(owner: Any, news: List) -> str:
    """Build a compact source-aware news catalyst list for the rendered report."""
    if not news:
        return ""
    language = owner._get_review_language()
    if language == "en":
        lines = [
            "#### News Catalysts",
        ]
    else:
        lines = [
            "#### 近三日市场线索",
        ]

    for idx, item in enumerate(news[:5], 1):
        lines.append(owner._format_news_catalyst_line(idx, item, language=language))
    return "\n".join(lines)
