# -*- coding: utf-8 -*-
"""No-LLM market-review template renderer.

Issue #1085 step 3 extracts only the template fallback renderer. LLM
generation, backend config, logging, prompt builders, payloads, snapshots,
and fetch/news orchestration remain in ``src.market.analyzer``. This module
must not import ``MarketAnalyzer``; it calls facade helpers via ``owner``.
"""

from __future__ import annotations

from typing import Any, List


def generate_template_review(
    owner: Any,
    overview: Any,
    news: List,
    *,
    datetime_cls: Any,
) -> str:
    """Render the no-LLM market-review template through facade helpers.

    ``news`` is accepted for facade compatibility and is unused by this
    renderer. ``datetime_cls`` must be the analyzer-module ``datetime``
    binding so monkeypatches of ``src.market.analyzer.datetime`` remain
    effective.
    """
    template_language = owner._get_template_review_language()
    mood_code = owner.profile.mood_index_code
    # Lookup the corresponding index based on mood_index_code
    # cn: mood_code="000001", idx.code May be "sh000001"(With mood_code End)
    # us: mood_code="SPX", idx.code Directly for "SPX"
    mood_index = next(
        (
            idx
            for idx in overview.indices
            if idx.code == mood_code or idx.code.endswith(mood_code)
        ),
        None,
    )
    if mood_index:
        if mood_index.change_pct > 1:
            market_mood = owner._get_market_mood_text("strong_up", template_language)
        elif mood_index.change_pct > 0:
            market_mood = owner._get_market_mood_text("mild_up", template_language)
        elif mood_index.change_pct > -1:
            market_mood = owner._get_market_mood_text("mild_down", template_language)
        else:
            market_mood = owner._get_market_mood_text("strong_down", template_language)
    else:
        market_mood = owner._get_market_mood_text("range", template_language)

    # Index market data (concise format)
    indices_text = ""
    for idx in overview.indices[:4]:
        direction = "↑" if idx.change_pct > 0 else "↓" if idx.change_pct < 0 else "-"
        indices_text += f"- **{idx.name}**: {idx.current:.2f} ({direction}{abs(idx.change_pct):.2f}%)\n"

    # Sector information
    separator = ", " if template_language == "en" else "、"
    top_text = separator.join([s['name'] for s in overview.top_sectors[:3]])
    bottom_text = separator.join([s['name'] for s in overview.bottom_sectors[:3]])
    top_concept_text = separator.join([s['name'] for s in overview.top_concepts[:3]])
    bottom_concept_text = separator.join([s['name'] for s in overview.bottom_concepts[:3]])
    sector_analysis_block = owner._build_sector_analysis_block(overview)

    if template_language == "en":
        stats_section = ""
        if owner.profile.has_market_stats:
            stats_section = f"""
### 3. Breadth & Liquidity
| Metric | Value |
|--------|-------|
| Advancers | {overview.up_count} |
| Decliners | {overview.down_count} |
| Limit-up | {overview.limit_up_count} |
| Limit-down | {overview.limit_down_count} |
| Turnover ({owner._get_turnover_unit_label()}) | {overview.total_amount:.0f} |
"""
        sector_section = ""
        if owner.profile.has_sector_rankings and (
            top_text
            or bottom_text
            or top_concept_text
            or bottom_concept_text
            or sector_analysis_block
        ):
            sector_section = f"""
### 4. Sector / Theme Highlights
- **Industry Leaders**: {top_text or "N/A"}
- **Industry Laggards**: {bottom_text or "N/A"}
- **Concept Leaders**: {top_concept_text or "N/A"}
- **Concept Laggards**: {bottom_concept_text or "N/A"}

{sector_analysis_block}
"""
        market_names = {
            "us": "US Market Recap",
            "hk": "HK Market Recap",
            "jp": "Japan Market Recap",
            "kr": "Korea Market Recap",
        }
        market_name = market_names.get(owner.region, "A-share Market Recap")
        report = f"""## {overview.date} {market_name}

### 1. Market Summary
Today's {owner._get_market_scope_name(template_language)} showed **{market_mood}**.

### 2. Major Indices
{indices_text or "- No index data available"}
{stats_section}
{sector_section}
### 5. Risk Alerts
Market conditions can change quickly. The data above is for reference only and does not constitute investment advice.

{owner._get_strategy_markdown_block(template_language)}

---
*Review Time: {datetime_cls.now().strftime('%H:%M')}*
"""
        return report

    market_labels = {"cn": "A股", "us": "美股", "hk": "港股", "jp": "日股", "kr": "韩股"}
    market_label = market_labels.get(owner.region, "A股")
    dashboard_block = owner._build_stats_block(overview) if owner.profile.has_market_stats else ""
    indices_block = owner._build_indices_block(overview)
    sector_block = owner._build_sector_block(overview) if owner.profile.has_sector_rankings else ""
    summary_focus = (
        "指数承接、成交额变化和板块持续性"
        if owner.profile.has_market_stats and owner.profile.has_sector_rankings
        else "指数承接、消息催化和整体风险状态"
    )
    market_summary_block = (
        dashboard_block
        if dashboard_block
        else (
            "暂无市场宽度数据。"
            if owner.profile.has_market_stats
            else "- 当前以主要指数与可用新闻线索评估整体风险状态。"
        )
    )
    sector_section = (
        f"""
### 三、板块主线
{sector_block or "- 暂无板块涨跌榜数据。"}
"""
        if owner.profile.has_sector_rankings
        else ""
    )
    funds_section = (
        """
### 四、资金与情绪
- 结合成交额和涨跌家数看，当前更适合等待确认，避免仅凭单一热点追高。
"""
        if owner.profile.has_market_stats
        else ""
    )
    return f"""## {overview.date} 大盘复盘

> 今日{market_label}市场整体呈现**{market_mood}**态势，优先观察{summary_focus}。

### 一、盘面总览
{market_summary_block}

### 二、指数结构
{indices_block or indices_text or "暂无指数数据。"}
{sector_section}
{funds_section}

### 五、消息催化
- 暂无可用新闻时，应降低对题材持续性的确定性判断。

{owner._get_strategy_markdown_block(template_language)}

### 七、风险提示
- 市场有风险，投资需谨慎。以上数据仅供参考，不构成投资建议。

---
*复盘时间: {datetime_cls.now().strftime('%H:%M')}*
"""
