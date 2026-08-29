"""Sanitize market-review history summaries without changing stored Markdown."""

from __future__ import annotations

import re
from typing import Any, Optional

from src.formatters import markdown_to_plain_text


def extract_market_review_content(record, raw_result: Any) -> Optional[str]:
    """Return persisted market review content from raw_result or news_content."""
    if isinstance(raw_result, dict):
        for field in ("raw_response", "market_review_report"):
            content = raw_result.get(field)
            if isinstance(content, str) and content.strip():
                return content

    news_content = getattr(record, "news_content", None)
    if isinstance(news_content, str) and news_content.strip():
        return news_content
    return None


def market_review_summary(
    persisted_summary: Any,
    markdown: Any,
    *,
    limit: int = 120,
) -> Optional[str]:
    """Return a stable short summary without leaking report Markdown or metadata."""
    persisted = str(persisted_summary or "").strip()
    if persisted:
        return persisted

    source = str(markdown or "").strip()
    if not source:
        return None

    # Full reports can contain internal reference metadata, tables, links and
    # fenced diagnostic payloads. Keep readable prose only for summary fields.
    source = re.sub(r"```[^\n]*\n.*?```", " ", source, flags=re.DOTALL)
    source = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", source)
    source = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", source)
    source = re.sub(r"^\[[^\]]+\]:\s+.*$", " ", source, flags=re.MULTILINE)
    source = re.sub(r"<[^>]+>", " ", source)
    text = markdown_to_plain_text(source)
    text = re.sub(r"[`~|]", " ", text)
    text = re.sub(r"^\s*:?-{3,}:?(?:\s+:?-{3,}:?)+\s*$", " ", text, flags=re.MULTILINE)
    text = re.sub(r"^[+\d]+[.)]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s+", " ", text).strip(" •-—")
    if not text:
        return None
    if len(text) > limit:
        return text[:limit].rstrip() + "…"
    return text
