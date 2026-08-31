# -*- coding: utf-8 -*-
"""Pure market-review report section helpers.

Issue #1085 step 9. These three are genuinely pure: they take only their
arguments and touch no analyzer state, so unlike ``blocks``, ``market_data``,
``news``, and ``diagnostics`` they need no ``owner`` parameter.

``MarketAnalyzer`` keeps them as thin delegators preserving their original
descriptor kinds — ``_extract_report_title`` and ``_insert_after_section`` stay
``staticmethod``, ``_split_report_sections`` stays ``classmethod`` — because the
descriptor kind is part of the public surface.
"""

from __future__ import annotations

import re
from typing import Dict, List

__all__ = (
    "extract_report_title",
    "split_report_sections",
    "insert_after_section",
)


def extract_report_title(report: str) -> str:
    for line in (report or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return ""


def split_report_sections(report: str) -> List[Dict[str, str]]:
    text = (report or "").strip()
    if not text:
        return []
    matches = list(re.finditer(r"^(#{2,3})\s+(.+?)\s*$", text, flags=re.MULTILINE))
    if not matches:
        return [{"key": "full_review", "title": "Review", "markdown": text}]

    sections: List[Dict[str, str]] = []
    first_match = matches[0]
    starts_with_report_title = first_match.start() == 0 and first_match.group(1) == "##"
    content_start_index = 1 if starts_with_report_title else 0
    intro_start = first_match.end() if starts_with_report_title else 0
    intro_end = (
        matches[1].start()
        if starts_with_report_title and len(matches) > 1
        else (len(text) if starts_with_report_title else matches[0].start())
    )
    intro = text[intro_start:intro_end].strip()
    if intro:
        sections.append({"key": "overview", "title": "Overview", "markdown": intro})

    for index, match in enumerate(matches[content_start_index:], start=content_start_index):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        title = match.group(2).strip()
        markdown = text[start:end].strip()
        if not markdown:
            continue
        key = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "_", title).strip("_").lower()
        sections.append({
            "key": key or f"section_{index + 1}",
            "title": title,
            "markdown": markdown,
        })
    return sections


def insert_after_section(text: str, heading_pattern: str, block: str) -> str:
    """Insert a data block at the end of a markdown section (before the next ### heading)."""
    import re
    # Find the heading
    match = re.search(heading_pattern, text)
    if not match:
        return text
    start = match.end()
    # Find the next ### heading after this one
    next_heading = re.search(r'\n###\s', text[start:])
    if next_heading:
        insert_pos = start + next_heading.start()
    else:
        # No next heading — append at end
        insert_pos = len(text)
    # Insert the block before the next heading, with spacing
    return text[:insert_pos].rstrip() + '\n\n' + block + '\n\n' + text[insert_pos:].lstrip('\n')
