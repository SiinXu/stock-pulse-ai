# -*- coding: utf-8 -*-
"""Markdown section/table extraction for share-image posters."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable, Mapping, Optional

from .formatting import (
    _MARKET_RE,
    _MARKET_SCOPE_RE,
    _DASHBOARD_RE,
    _HEADING_RE,
    _DATE_RE,
    _MARKET_REGION_REF_RE,
    _CODE_RE,
    _NUMERIC_CODE_RE,
    _MARKET_LABEL_PATTERNS,
    _plain,
    _clean_value,
)

@dataclass
class Table:
    headers: list[str]
    rows: list[list[str]]
    raw_rows: list[list[str]] = field(default_factory=list)

@dataclass
class MarketSegment:
    title: str
    markdown: str

def _extract_sections(markdown_text: str) -> list[tuple[str, str, int]]:
    matches = list(_HEADING_RE.finditer(markdown_text or ""))
    sections: list[tuple[str, str, int]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown_text)
        sections.append((_plain(match.group(2)), markdown_text[start:end].strip(), len(match.group(1))))
    return sections

def _section(markdown_text: str, *terms: str) -> str:
    matches = list(_HEADING_RE.finditer(markdown_text or ""))
    for index, match in enumerate(matches):
        title = _plain(match.group(2)).lower()
        if not any(term.lower() in title for term in terms):
            continue
        level = len(match.group(1))
        end = len(markdown_text)
        for following in matches[index + 1 :]:
            if len(following.group(1)) <= level:
                end = following.start()
                break
        return markdown_text[match.end() : end].strip()
    return ""

def _parse_tables(markdown_text: str) -> list[Table]:
    lines = (markdown_text or "").splitlines()
    tables: list[Table] = []
    index = 0
    while index < len(lines):
        if not lines[index].strip().startswith("|"):
            index += 1
            continue
        block: list[str] = []
        while index < len(lines) and lines[index].strip().startswith("|"):
            block.append(lines[index].strip())
            index += 1
        if len(block) < 2:
            continue
        raw_cells = [[cell.strip() for cell in row.strip("|").split("|")] for row in block]
        if not all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in raw_cells[1]):
            continue
        cells = [
            [_clean_value(cell, limit=140) for cell in row.strip("|").split("|")]
            for row in block
        ]
        width = len(cells[0])
        rows = [row[:width] + [""] * max(0, width - len(row)) for row in cells[2:]]
        tables.append(Table(headers=cells[0], rows=rows, raw_rows=raw_cells[2:]))
    return tables

def _table_map(table: Table) -> dict[str, str]:
    return {
        _plain(row[0]).lower(): _clean_value(row[1], limit=120)
        for row in table.rows
        if len(row) >= 2 and _plain(row[0])
    }

def _find_table(markdown_text: str, *header_terms: str) -> Optional[Table]:
    for table in _parse_tables(markdown_text):
        header = " ".join(table.headers).lower()
        body = " ".join(" ".join(row) for row in table.rows).lower()
        if all(term.lower() in f"{header} {body}" for term in header_terms):
            return table
    return None

def _mapped_value(mapping: dict[str, str], *labels: str) -> str:
    for key, value in mapping.items():
        if any(label.lower() in key for label in labels) and _clean_value(value):
            return _clean_value(value)
    return ""

def _has_meaningful_section(markdown_text: str, *terms: str) -> bool:
    section = _section(markdown_text, *terms)
    if not section:
        return False
    cleaned = _clean_value(section, limit=400)
    if not cleaned:
        return False
    for boilerplate in (
        "建议仅供参考，不构成投资建议",
        "仅供研究交流，不构成投资建议",
        "does not constitute investment advice",
    ):
        cleaned = cleaned.replace(boilerplate, "").strip()
    return bool(cleaned)

def _meaningful_market_subsection_count(markdown_text: str) -> int:
    count = 0
    for _title, body, level in _extract_sections(markdown_text):
        if level == 3 and _clean_value(body, limit=400):
            count += 1
    return count

def _labeled_value(text: str, *labels: str, limit: int = 100) -> str:
    joined = "|".join(re.escape(label) for label in labels)
    match = re.search(
        rf"(?:\*{{0,2}}(?:{joined})\*{{0,2}})\s*[:：]\s*(.+?)(?=\s*\||\n|$)",
        text or "",
        flags=re.IGNORECASE,
    )
    return _clean_value(match.group(1), limit=limit) if match else ""

def _labeled_line(text: str, *labels: str, limit: int = 100) -> str:
    joined = "|".join(re.escape(label) for label in labels)
    match = re.search(
        rf"(?:\*{{0,2}}(?:{joined})\*{{0,2}})\s*[:：]\s*(.+?)(?=\n|$)",
        text or "",
        flags=re.IGNORECASE,
    )
    return _clean_value(match.group(1), limit=limit) if match else ""

def _list_after_label(text: str, *labels: str, limit: int = 3) -> list[str]:
    joined = "|".join(re.escape(label) for label in labels)
    match = re.search(
        rf"(?:\*{{0,2}}[^\n]*(?:{joined})[^\n]*\*{{0,2}})\s*[:：]?\s*\n(?P<body>.*?)(?=\n\s*\*{{1,2}}[^\n]+\*{{1,2}}\s*[:：]|\n#|\Z)",
        text or "",
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return []
    items = []
    for line in match.group("body").splitlines():
        cleaned = _clean_value(re.sub(r"^\s*(?:[-*+]\s+|\d+[.)、]\s*)", "", line), limit=72)
        if cleaned:
            items.append(cleaned)
        if len(items) >= limit:
            break
    return items

def _section_items(text: str, *, limit: int = 3) -> list[str]:
    items: list[str] = []
    for line in (text or "").splitlines():
        if not re.match(r"^\s*(?:[-*+]\s+|\d+[.)、]\s*)", line):
            continue
        cleaned = _clean_value(re.sub(r"^\s*(?:[-*+]\s+|\d+[.)、]\s*)", "", line), limit=88)
        if cleaned and "不构成投资建议" not in cleaned:
            items.append(cleaned)
        if len(items) >= limit:
            break
    return items

def _sentences(text: str, *, limit: int = 2) -> list[str]:
    clean = _plain(re.sub(r"^\s*(?:[-*+]\s+|\d+[.)、]\s*)", "", text or "", flags=re.MULTILINE))
    clean = re.sub(r"#{1,4}\s*", "", clean)
    pieces = re.split(r"(?<=[。！？!?])\s*", clean)
    result = [_clean_value(piece, limit=88) for piece in pieces if _clean_value(piece, limit=88)]
    return result[:limit]

def _extract_date(markdown_text: str, fallback: date) -> str:
    match = _DATE_RE.search(markdown_text or "")
    return match.group(1) if match else fallback.isoformat()

def _market_label(text: str) -> str:
    scope = _plain(text)
    for label, pattern in _MARKET_LABEL_PATTERNS:
        if pattern.search(scope):
            return label
    return ""

def _market_region_hint(markdown_text: str) -> str:
    match = _MARKET_REGION_REF_RE.search(markdown_text or "")
    return match.group(1).strip().lower() if match else ""

def _market_label_for_region(region: str) -> str:
    return {
        "cn": "A股",
        "hk": "港股",
        "us": "美股",
        "jp": "日股",
        "kr": "韩股",
    }.get((region or "").strip().lower(), "")

def _stock_heading_entry(raw_title: str) -> Optional[tuple[str, str]]:
    def _heading_name(fragment: str) -> str:
        name = _plain(fragment).strip(" -—()（）")
        return re.sub(r"\b(?:分析报告|analysis report)$", "", name, flags=re.IGNORECASE).strip()

    def _is_parenthesized(match: re.Match[str]) -> bool:
        start, end = match.span(1)
        return start > 0 and raw_title[start - 1] in "(（" and end < len(raw_title) and raw_title[end] in ")）"

    trailing_candidate: Optional[tuple[str, str]] = None
    leading_candidate: Optional[tuple[str, str]] = None
    for match in _CODE_RE.finditer(raw_title):
        code = match.group(1).upper()
        name = _heading_name(raw_title[: match.start()])
        if name:
            if _is_parenthesized(match):
                return name, code
            if leading_candidate is None:
                leading_candidate = (name, code)
            continue
        if _NUMERIC_CODE_RE.fullmatch(code):
            trailing_name = _heading_name(raw_title[match.end() :])
            if trailing_name and trailing_candidate is None:
                trailing_candidate = (trailing_name, code)
    return trailing_candidate or leading_candidate

def _stock_headings(markdown_text: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for raw_title, _body, level in _extract_sections(markdown_text):
        if level > 2 or _MARKET_RE.search(raw_title) or _DASHBOARD_RE.search(raw_title):
            continue
        entry = _stock_heading_entry(raw_title)
        if entry:
            found.append(entry)
    return found

def _is_market_review_title(title: str) -> bool:
    return bool(_MARKET_RE.search(_plain(title)))

def _has_market_scope(title: str) -> bool:
    return bool(_MARKET_SCOPE_RE.search(_plain(title)))

def _market_segments(markdown_text: str) -> list[MarketSegment]:
    top_level_matches = [
        match
        for match in _HEADING_RE.finditer(markdown_text or "")
        if len(match.group(1)) == 1
    ]
    matches = [match for match in top_level_matches if _is_market_review_title(match.group(2))]
    if len(matches) < 2:
        return []
    if top_level_matches and matches[0].start() == top_level_matches[0].start():
        first_title = matches[0].group(2)
        if not _has_market_scope(first_title):
            scoped_matches = [match for match in top_level_matches if _has_market_scope(match.group(2))]
            if len(scoped_matches) >= 2:
                matches = scoped_matches

    segments: list[MarketSegment] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown_text)
        segments.append(
            MarketSegment(
                title=_plain(match.group(2)),
                markdown=markdown_text[match.start() : end].strip(),
            )
        )
    return segments
