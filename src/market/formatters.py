# -*- coding: utf-8 -*-
"""Pure market-review text and number formatters.

Issue #1085 step 4 extracts pure report formatters only; markdown block
builders, prompt assembly, LLM generation, snapshots, and fetch
orchestration remain in ``src.market.analyzer``. This module must not import
``MarketAnalyzer``; the two composite formatters call sibling helpers via
``owner`` so class-level and instance-level overrides stay effective.
"""

from __future__ import annotations

from typing import Any, Dict, List

__all__ = (
    "get_news_field",
    "format_news_catalyst_line",
    "compact_news_text",
    "format_optional_number",
    "format_optional_pct",
    "format_signed_pct",
    "format_ranking_summary",
    "escape_markdown_link_label",
    "describe_turnover",
)


def get_news_field(item: Any, field: str) -> str:
    if hasattr(item, field):
        value = getattr(item, field, "") or ""
    elif isinstance(item, dict):
        value = item.get(field, "") or ""
    else:
        value = ""
    return str(value).strip()


def format_news_catalyst_line(
    owner: Any, idx: int, item: Any, *, language: str = "zh"
) -> str:
    fallback_title = "Untitled catalyst" if language == "en" else "未命名线索"
    title = owner._compact_news_text(owner._get_news_field(item, "title"), limit=90) or fallback_title
    source = owner._compact_news_text(owner._get_news_field(item, "source"), limit=40)
    date_text = owner._compact_news_text(owner._get_news_field(item, "published_date"), limit=24)
    url = owner._compact_news_text(owner._get_news_field(item, "url"), limit=0)
    title_text = owner._escape_markdown_link_label(title)
    if url:
        title_text = f"[{title_text}]({url})"
    meta_parts = [part for part in (source, date_text) if part]
    if language == "en":
        meta = f" ({' / '.join(meta_parts)})" if meta_parts else ""
    else:
        meta = f"（{' / '.join(meta_parts)}）" if meta_parts else ""
    return f"- {idx}. {title_text}{meta}"


def compact_news_text(value: str, *, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if limit <= 0 or len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def format_optional_number(value: float) -> str:
    return "N/A" if value in (None, 0, 0.0) else f"{value:.2f}"


def format_optional_pct(value: float) -> str:
    return "N/A" if value in (None, 0, 0.0) else f"{value:.2f}%"


def format_signed_pct(value: Any) -> str:
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return "N/A"
    return f"{numeric_value:+.2f}%"


def format_ranking_summary(owner: Any, rows: List[Dict], limit: int = 3) -> str:
    parts = []
    for item in (rows or [])[:limit]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        parts.append(f"{name}({owner._format_signed_pct(item.get('change_pct'))})")
    return ", ".join(parts)


def escape_markdown_link_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def describe_turnover(total_amount: float) -> str:
    if total_amount >= 15000:
        return "高活跃度"
    if total_amount >= 9000:
        return "中等活跃"
    if total_amount > 0:
        return "缩量观望"
    return "暂无数据"
