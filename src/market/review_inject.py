# -*- coding: utf-8 -*-
"""Market-review markdown injectors rebound through the analyzer facade.

Issue #1085 extracts ``_inject_data_into_review`` from
``src.market.analyzer``. Prompt assembly, LLM generation, snapshots, and
degradation policy remain on the analyzer. This module must not import
the analyzer class; the helper receives ``owner`` and reaches
``_get_review_language``, ``_build_stats_block``, ``_build_indices_block``,
``_build_sector_block``, and ``_insert_after_section`` through it so
class-level and instance-level overrides stay effective. ``overview`` is
typed ``Any`` for the same reason. ``news`` is accepted and unused.
"""

from __future__ import annotations

from typing import Any, List, Optional

__all__ = (
    "inject_data_into_review",
)


_ENGLISH_SECTION_PATTERNS = {
    "market_summary": r"###\s*(?:1\.\s*)?Market Summary",
    "index_commentary": r"###\s*(?:2\.\s*)?(?:Index Commentary|Major Indices)",
    "sector_highlights": r"###\s*(?:4\.\s*)?(?:Sector Highlights|Sector/Theme Highlights)",
}

_CHINESE_SECTION_PATTERNS = {
    "market_summary": r"###\s*一、(?:盘面总览|市场总结)",
    "index_commentary": r"###\s*二、(?:指数结构|指数点评|主要指数)",
    "sector_highlights": r"###\s*三、(?:板块主线|热点解读|板块表现)",
    "funds_sentiment": r"###\s*四、(?:资金与情绪|资金动向)",
    "news_catalysts": r"###\s*五、(?:消息催化|后市展望)",
}


def inject_data_into_review(
    owner: Any,
    review: str,
    overview: Any,
    news: Optional[List] = None,
) -> str:
    """Inject structured data tables into the corresponding LLM prose sections."""
    stats_block = owner._build_stats_block(overview)
    indices_block = owner._build_indices_block(overview)
    sector_block = owner._build_sector_block(overview)
    patterns = (
        _ENGLISH_SECTION_PATTERNS
        if owner._get_review_language() == "en"
        else _CHINESE_SECTION_PATTERNS
    )

    if stats_block:
        review = owner._insert_after_section(
            review,
            patterns["market_summary"],
            stats_block,
        )

    if indices_block:
        review = owner._insert_after_section(
            review,
            patterns["index_commentary"],
            indices_block,
        )

    if sector_block:
        original_review = review
        review = owner._insert_after_section(
            review,
            patterns["sector_highlights"],
            sector_block,
        )
        if review == original_review and sector_block not in review:
            fallback_heading = (
                "### 4. Sector Highlights"
                if owner._get_review_language() == "en"
                else "### 三、板块主线"
            )
            review = f"{review.rstrip()}\n\n{fallback_heading}\n{sector_block}\n"

    return review
