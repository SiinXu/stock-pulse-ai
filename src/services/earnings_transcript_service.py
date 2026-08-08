# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Earnings-call transcript parsing with source-traceable extraction (issue #253).

Deterministic, local-first structured parsing of user-supplied transcript text
or files. Designed for long earnings-call transcripts (prepared remarks + Q&A).

Honesty contract
----------------
* Every extracted metric value is an exact substring of the source text and
  carries ``start_char`` / ``end_char`` offsets into that source.
* Missing numbers stay empty; the parser never invents or rounds figures.
* Management tone is optional and always marked as a subjective judgment.

Reuse note
----------
Path sandboxing reuses ``resolve_safe_file_path`` from
``pdf_parsing_service``. When the input is a PDF, text is obtained via
``parse_pdf_path`` / ``parse_pdf_bytes`` and then fed into the same
transcript structuring pipeline. Chunking is transcript-specific (long oral
text, not PDF pages).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

TRANSCRIPT_SCHEMA_VERSION = "earnings-transcript-v1"
TRANSCRIPT_DISCLAIMER = (
    "Parsed earnings-call transcript content is for research support only. "
    "Extracted metrics are exact source substrings with character offsets; "
    "missing values stay empty and are never invented. Management tone labels "
    "are subjective judgments when present. Not investment advice."
)

MAX_TRANSCRIPT_CHARS = 200_000
MAX_TRANSCRIPT_BYTES = 2 * 1024 * 1024
MAX_CHUNK_CHARS = 6_000
CHUNK_OVERLAP_CHARS = 200
MAX_QA_ITEMS = 80
MAX_METRICS = 200
MAX_FORWARD_LOOKING = 40
MAX_SEGMENTS = 20
MAX_FILENAME_CHARS = 255
MIN_USEFUL_CHARS = 40

_TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".text", ".transcript", ".log"}
_PDF_SUFFIXES = {".pdf"}

_QA_SECTION_RE = re.compile(
    r"(?im)^(?:\s*)(?:"
    r"question[\s\-–—]*and[\s\-–—]*answer(?:\s+session)?|"
    r"questions?\s+and\s+answers?|"
    r"q\s*&\s*a(?:\s+session)?|"
    r"q\s+and\s+a(?:\s+session)?|"
    r"问答(?:环节|部分|时间)?|"
    r"提问与回答"
    r")\s*:?\s*$"
)
_PREPARED_SECTION_RE = re.compile(
    r"(?im)^(?:\s*)(?:"
    r"prepared\s+remarks?|"
    r"management\s+(?:presentation|remarks?|discussion)|"
    r"opening\s+remarks?|"
    r"管理层(?:陈述|发言|致辞|讨论)|"
    r"经营层发言"
    r")\s*:?\s*$"
)

# Explicit "Q -" / "Question -" headers (not bare "Question-and-Answer" titles).
_QUESTIONER_RE = re.compile(
    r"(?im)^(?:\s*)(?:"
    r"(?:operator|主持人)\s*[:：]\s*(?P<op>.+?)|"
    r"(?:q|question)\s+[-–—]\s*(?P<qname>[^,\n:：]+)(?:,\s*(?P<qfirm>[^\n:：]+))?\s*[:：]?\s*|"
    r"(?:q|question)\s*[:：]\s*(?P<qname2>[^,\n:：]+)(?:,\s*(?P<qfirm2>[^\n:：]+))?\s*"
    r")(?P<qbody>.*)$"
)
_ANSWER_RE = re.compile(
    r"(?im)^(?:\s*)(?:"
    r"(?:a|answer)\s+[-–—]\s*(?P<aname>[^,\n:：]+)\s*[:：]?\s*|"
    r"(?:a|answer)\s*[:：]\s*(?P<aname2>[^,\n:：]+)\s*|"
    r"(?P<exec>[A-Z][A-Za-z.\- ]{1,40})\s*[:：]\s*"
    r")(?P<body>.*)$"
)
_SECTION_HEADING_LINE_RE = re.compile(
    r"(?im)^(?:\s*)(?:"
    r"question[\s\-–—]*and[\s\-–—]*answer|"
    r"q\s*&\s*a|"
    r"prepared\s+remarks?|"
    r"management\s+(?:presentation|remarks?|discussion)|"
    r"问答|管理层"
    r")"
)
_OPERATOR_NEXT_RE = re.compile(
    r"(?im)^(?:\s*)(?:operator|主持人)\s*[:：]"
)

_METRIC_RE = re.compile(
    r"(?P<label_left>(?:revenue|sales|eps|guidance|gross\s+margin|operating\s+margin|"
    r"net\s+(?:income|profit)|ebitda|arr|mrr|growth|yoy|qoq|"
    r"营收|收入|净利润|毛利率|指引|同比增长|同比下降)[^.\n]{0,40}?)?"
    r"(?P<value>"
    r"(?:(?:USD|US\$|\$|CNY|RMB|¥|€|£)\s*)?"
    r"[+-]?"
    r"(?:\d{1,3}(?:,\d{3})+|\d+)"
    r"(?:\.\d+)?"
    r"(?:\s*(?:%|percent|bps|basis\s+points|million|billion|bn|mn|万|亿|元))?"
    r")"
    r"(?P<label_right>[^.\n]{0,40})?",
    re.IGNORECASE,
)

_GUIDANCE_HINT_RE = re.compile(
    r"(?i)\b(?:guidance|outlook|expect(?:s|ed|ing)?|forecast|project(?:s|ed|ing)?|"
    r"will\s+be|target(?:s|ing)?|指引|展望|预计|预期)\b"
)
_DISCLAIMER_HINT_RE = re.compile(
    r"(?i)\b(?:forward[\s\-]?looking|safe\s+harbor|non[\s\-]?gaap|"
    r"not\s+(?:a\s+)?guarantee|risk\s+factors?|"
    r"前瞻性|免责声明|不构成投资建议)\b"
)
_CONFIDENT_HINT_RE = re.compile(
    r"(?i)\b(?:confident|strong|solid|pleased|optimistic|well[\s\-]?positioned|"
    r"充满信心|稳健|乐观)\b"
)
_CAUTIOUS_HINT_RE = re.compile(
    r"(?i)\b(?:cautious|uncertain|challenging|headwind|soft(?:ness)?|pressure|"
    r"谨慎|不确定|承压|挑战)\b"
)

_WHITESPACE_COLLAPSE_RE = re.compile(r"[ \t\f\v]+")


def _result(
    *,
    status: str,
    reason_code: Optional[str] = None,
    source: Optional[Mapping[str, Any]] = None,
    segments: Optional[Sequence[Mapping[str, Any]]] = None,
    qa_items: Optional[Sequence[Mapping[str, Any]]] = None,
    metrics: Optional[Sequence[Mapping[str, Any]]] = None,
    forward_looking: Optional[Sequence[Mapping[str, Any]]] = None,
    management_tone: Optional[Mapping[str, Any]] = None,
    chunks: Optional[Sequence[Mapping[str, Any]]] = None,
    method: str = "local_deterministic",
    text_char_count: int = 0,
) -> dict[str, Any]:
    return {
        "schema_version": TRANSCRIPT_SCHEMA_VERSION,
        "status": status,
        "reason_code": reason_code,
        "source": dict(source or {}),
        "segments": list(segments or []),
        "qa_items": list(qa_items or []),
        "metrics": list(metrics or []),
        "forward_looking": list(forward_looking or []),
        "management_tone": management_tone,
        "chunks": list(chunks or []),
        "method": method,
        "text_char_count": text_char_count,
        "disclaimer": TRANSCRIPT_DISCLAIMER,
    }


def _sanitize_filename(name: Optional[str]) -> str:
    if not name:
        return "transcript.txt"
    base = Path(str(name)).name.strip()
    if not base or base in {".", ".."}:
        return "transcript.txt"
    base = re.sub(r"[^\w.\- ()\[\]]+", "_", base, flags=re.UNICODE)
    return base[:MAX_FILENAME_CHARS] or "transcript.txt"


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def chunk_transcript_text(
    text: str,
    *,
    max_chunk_chars: int = MAX_CHUNK_CHARS,
    overlap_chars: int = CHUNK_OVERLAP_CHARS,
) -> list[dict[str, Any]]:
    """Split long transcript text into bounded overlapping character chunks."""
    if not text:
        return []
    limit = max(500, int(max_chunk_chars or MAX_CHUNK_CHARS))
    overlap = max(0, min(int(overlap_chars or 0), limit // 4))
    n = len(text)
    if n <= limit:
        return [
            {
                "index": 0,
                "start_char": 0,
                "end_char": n,
                "char_count": n,
                "text": text,
            }
        ]

    chunks: list[dict[str, Any]] = []
    start = 0
    index = 0
    while start < n:
        end = min(start + limit, n)
        if end < n:
            window = text[start:end]
            search_from = max(0, len(window) - limit // 3)
            break_at = window.rfind("\n\n", search_from)
            if break_at < 0:
                break_at = window.rfind("\n", search_from)
            if break_at > 0:
                end = start + break_at + 1
        piece = text[start:end]
        chunks.append(
            {
                "index": index,
                "start_char": start,
                "end_char": end,
                "char_count": len(piece),
                "text": piece,
            }
        )
        index += 1
        if end >= n:
            break
        next_start = end - overlap
        if next_start <= start:
            next_start = end
        start = next_start
        if len(chunks) >= 500:
            break
    return chunks


def _find_section_spans(text: str) -> list[dict[str, Any]]:
    markers: list[tuple[int, str]] = []
    for match in _PREPARED_SECTION_RE.finditer(text):
        markers.append((match.start(), "prepared_remarks"))
    for match in _QA_SECTION_RE.finditer(text):
        markers.append((match.start(), "qa"))
    markers.sort(key=lambda item: item[0])

    if not markers:
        operator_hits = len(_OPERATOR_NEXT_RE.findall(text))
        if operator_hits >= 2:
            return [
                {
                    "type": "qa",
                    "start_char": 0,
                    "end_char": len(text),
                    "label": "inferred_qa",
                }
            ]
        return [
            {
                "type": "unknown",
                "start_char": 0,
                "end_char": len(text),
                "label": "full_transcript",
            }
        ]

    segments: list[dict[str, Any]] = []
    if markers[0][0] > 0:
        segments.append(
            {
                "type": "prepared_remarks" if markers[0][1] == "qa" else "unknown",
                "start_char": 0,
                "end_char": markers[0][0],
                "label": "preamble",
            }
        )
    for i, (pos, kind) in enumerate(markers):
        end = markers[i + 1][0] if i + 1 < len(markers) else len(text)
        segments.append(
            {
                "type": kind,
                "start_char": pos,
                "end_char": end,
                "label": kind,
            }
        )
    return segments[:MAX_SEGMENTS]


def _line_spans(text: str) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    start = 0
    for line in text.split("\n"):
        end = start + len(line)
        spans.append((start, end, line))
        start = end + 1
    return spans


def _extract_qa_items(text: str, *, qa_span: Optional[tuple[int, int]] = None) -> list[dict[str, Any]]:
    if qa_span is not None:
        region_start, region_end = qa_span
        region = text[region_start:region_end]
        base = region_start
    else:
        region = text
        base = 0

    lines = _line_spans(region)
    items: list[dict[str, Any]] = []
    i = 0
    while i < len(lines) and len(items) < MAX_QA_ITEMS:
        start_i, end_i, line = lines[i]
        if _SECTION_HEADING_LINE_RE.match(line):
            i += 1
            continue

        op_intro = re.match(
            r"(?im)^(?:\s*)(?:operator|主持人)\s*[:：]\s*(?P<body>.+)$",
            line,
        )
        q_match = _QUESTIONER_RE.match(line)
        is_explicit_q = bool(
            re.match(r"(?i)^\s*(?:q|question)\s*(?:[-–—]|[:：])", line)
        )
        if not is_explicit_q and not op_intro:
            i += 1
            continue
        if op_intro and not is_explicit_q:
            i += 1
            continue
        if not q_match:
            i += 1
            continue

        groups = q_match.groupdict()
        questioner = None
        firm = None
        if groups.get("op"):
            questioner = (groups.get("op") or "").strip() or "Operator"
        else:
            questioner = (
                (groups.get("qname") or groups.get("qname2") or "").strip() or None
            )
            firm = (groups.get("qfirm") or groups.get("qfirm2") or "").strip() or None

        q_body_parts: list[str] = []
        first_body = (groups.get("qbody") or "").strip()
        if first_body:
            q_body_parts.append(first_body)
        q_start = base + start_i
        j = i + 1
        while j < len(lines):
            _, _, nxt = lines[j]
            if _SECTION_HEADING_LINE_RE.match(nxt):
                break
            if re.match(r"(?i)^\s*(?:a|answer)\s*(?:[-–—]|[:：])", nxt):
                break
            if re.match(r"(?i)^\s*[A-Z][A-Za-z.\- ]{1,40}\s*[:：]", nxt) and j > i:
                break
            if _OPERATOR_NEXT_RE.match(nxt) and j > i:
                break
            if re.match(r"(?i)^\s*(?:q|question)\s*(?:[-–—]|[:：])", nxt):
                break
            q_body_parts.append(nxt.strip())
            j += 1

        answer_parts: list[str] = []
        answerer = None
        if j < len(lines):
            _, _, ans_line = lines[j]
            a_match = _ANSWER_RE.match(ans_line)
            is_explicit_a = bool(
                re.match(r"(?i)^\s*(?:a|answer)\s*(?:[-–—]|[:：])", ans_line)
            )
            is_name_a = bool(
                re.match(r"(?i)^\s*[A-Z][A-Za-z.\- ]{1,40}\s*[:：]", ans_line)
            )
            if a_match and (is_explicit_a or is_name_a):
                answerer = (
                    (
                        a_match.groupdict().get("aname")
                        or a_match.groupdict().get("aname2")
                        or a_match.groupdict().get("exec")
                        or ""
                    ).strip()
                    or None
                )
                first_ans = (a_match.groupdict().get("body") or "").strip()
                if first_ans:
                    answer_parts.append(first_ans)
                j += 1
                while j < len(lines):
                    _, _, nxt = lines[j]
                    if _OPERATOR_NEXT_RE.match(nxt):
                        break
                    if re.match(r"(?i)^\s*(?:q|question)\s*(?:[-–—]|[:：])", nxt):
                        break
                    if re.match(r"(?i)^\s*(?:operator|主持人)\s*[:：]", nxt):
                        break
                    if _SECTION_HEADING_LINE_RE.match(nxt):
                        break
                    answer_parts.append(nxt.strip())
                    j += 1

        q_end_line = lines[min(j, len(lines)) - 1] if j > i else lines[i]
        q_end = base + q_end_line[1]
        question_text = _WHITESPACE_COLLAPSE_RE.sub(" ", " ".join(q_body_parts)).strip()
        answer_text = _WHITESPACE_COLLAPSE_RE.sub(" ", " ".join(answer_parts)).strip()
        topic = question_text[:120] if question_text else (questioner or "question")
        if firm and questioner and firm not in questioner:
            questioner_label = f"{questioner}, {firm}"
        else:
            questioner_label = questioner

        if not question_text and not answer_text:
            i = max(j, i + 1)
            continue

        source_excerpt = text[q_start:q_end][:500]
        items.append(
            {
                "questioner": questioner_label,
                "answerer": answerer,
                "question_topic": topic[:200],
                "question_text": question_text[:2000],
                "answer_summary": (answer_text[:400] if answer_text else ""),
                "answer_text": answer_text[:4000],
                "start_char": q_start,
                "end_char": q_end,
                "source_excerpt": source_excerpt,
            }
        )
        i = max(j, i + 1)

    return items


def _classify_metric_category(context: str) -> str:
    if _GUIDANCE_HINT_RE.search(context):
        return "guidance"
    return "metric"


def extract_metrics_with_offsets(
    text: str,
    *,
    max_items: int = MAX_METRICS,
) -> list[dict[str, Any]]:
    """Extract numeric tokens that exist verbatim in ``text`` with offsets."""
    if not text:
        return []
    metrics: list[dict[str, Any]] = []
    seen_spans: set[tuple[int, int]] = set()
    for match in _METRIC_RE.finditer(text):
        value = match.group("value")
        if value is None:
            continue
        full = match.group(0)
        value_rel = full.find(value)
        if value_rel < 0:
            continue
        start = match.start() + value_rel
        end = start + len(value)
        if (start, end) in seen_spans:
            continue
        raw_digits = re.sub(r"[^\d.]", "", value)
        if re.fullmatch(r"\d{4}", raw_digits or "") and "%" not in value and not re.search(
            r"(?i)(?:million|billion|revenue|eps|margin|guidance|营收|亿|万)",
            match.group(0),
        ):
            window = text[max(0, start - 40) : min(len(text), end + 40)]
            if not re.search(
                r"(?i)(?:revenue|eps|guidance|margin|sales|growth|营收|指引|利润)",
                window,
            ):
                continue
        if text[start:end] != value:
            continue
        left = (match.group("label_left") or "").strip()
        right = (match.group("label_right") or "").strip()
        label = (left or right or "").strip(" :-–—,\t") or None
        context = text[max(0, start - 80) : min(len(text), end + 80)]
        category = _classify_metric_category(context if not label else f"{label} {context}")
        metrics.append(
            {
                "label": label[:120] if label else None,
                "value_text": value,
                "start_char": start,
                "end_char": end,
                "category": category,
                "source_verified": True,
            }
        )
        seen_spans.add((start, end))
        if len(metrics) >= max_items:
            break
    return metrics


def _extract_forward_looking(text: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for match in re.finditer(r"[^.!?\n]+[.!?]?|\n+", text):
        sentence = match.group(0)
        if not sentence or sentence.isspace() or sentence == "\n":
            continue
        kind = None
        if _DISCLAIMER_HINT_RE.search(sentence):
            kind = "disclaimer"
        elif _GUIDANCE_HINT_RE.search(sentence):
            kind = "guidance"
        if kind is None:
            continue
        cleaned = _WHITESPACE_COLLAPSE_RE.sub(" ", sentence).strip()
        if len(cleaned) < 12:
            continue
        items.append(
            {
                "kind": kind,
                "text": cleaned[:500],
                "start_char": match.start(),
                "end_char": match.end(),
            }
        )
        if len(items) >= MAX_FORWARD_LOOKING:
            break
    return items


def _infer_management_tone(text: str) -> Optional[dict[str, Any]]:
    conf = len(_CONFIDENT_HINT_RE.findall(text))
    caut = len(_CAUTIOUS_HINT_RE.findall(text))
    if conf == 0 and caut == 0:
        return None
    if conf > caut + 1:
        label = "confident"
    elif caut > conf + 1:
        label = "cautious"
    else:
        label = "mixed"
    return {
        "label": label,
        "confident_signal_count": conf,
        "cautious_signal_count": caut,
        "judgment": "subjective",
        "note": (
            "Subjective heuristic based on keyword counts; not a model of "
            "true management intent."
        ),
    }


def parse_transcript_text(
    text: str,
    *,
    filename: Optional[str] = None,
    max_chars: int = MAX_TRANSCRIPT_CHARS,
    max_chunk_chars: int = MAX_CHUNK_CHARS,
) -> dict[str, Any]:
    """Parse transcript text into structured, source-traceable fields."""
    safe_name = _sanitize_filename(filename)
    source: dict[str, Any] = {
        "filename": safe_name,
        "byte_size": len(text.encode("utf-8")) if text else 0,
        "media_type": "text/plain",
        "input_mode": "text",
    }
    if text is None or not str(text).strip():
        return _result(
            status="unavailable",
            reason_code="empty_input",
            source=source,
            method="none",
        )

    normalized = _normalize_newlines(str(text))
    truncated = False
    if len(normalized) > max_chars:
        normalized = normalized[:max_chars]
        truncated = True

    source["char_count"] = len(normalized)
    source["truncated"] = truncated

    segments = _find_section_spans(normalized)
    qa_span: Optional[tuple[int, int]] = None
    for seg in segments:
        if seg.get("type") == "qa":
            qa_span = (int(seg["start_char"]), int(seg["end_char"]))
            break
    qa_items = _extract_qa_items(normalized, qa_span=qa_span)
    metrics = extract_metrics_with_offsets(normalized)
    forward_looking = _extract_forward_looking(normalized)
    tone = _infer_management_tone(normalized)
    chunks = chunk_transcript_text(normalized, max_chunk_chars=max_chunk_chars)

    verified_metrics: list[dict[str, Any]] = []
    for metric in metrics:
        start = int(metric["start_char"])
        end = int(metric["end_char"])
        value = metric["value_text"]
        if 0 <= start < end <= len(normalized) and normalized[start:end] == value:
            verified_metrics.append(metric)
        else:
            logger.warning(
                "Dropped metric that failed source verification value=%r span=%s:%s",
                value,
                start,
                end,
            )

    if len(normalized.strip()) < MIN_USEFUL_CHARS:
        return _result(
            status="degraded",
            reason_code="sparse_text",
            source=source,
            segments=segments,
            qa_items=qa_items,
            metrics=verified_metrics,
            forward_looking=forward_looking,
            management_tone=tone,
            chunks=chunks,
            text_char_count=len(normalized),
        )

    status = "available"
    reason_code = "truncated" if truncated else None
    if truncated:
        status = "degraded"

    return _result(
        status=status,
        reason_code=reason_code,
        source=source,
        segments=segments,
        qa_items=qa_items,
        metrics=verified_metrics,
        forward_looking=forward_looking,
        management_tone=tone,
        chunks=chunks,
        text_char_count=len(normalized),
    )


def parse_transcript_path(
    file_path: str,
    *,
    file_root: Optional[str] = None,
    max_chars: int = MAX_TRANSCRIPT_CHARS,
    max_chunk_chars: int = MAX_CHUNK_CHARS,
) -> dict[str, Any]:
    """Read a local transcript file (text or PDF) and parse it."""
    from src.services.pdf_parsing_service import (
        parse_pdf_bytes,
        resolve_safe_file_path,
    )

    try:
        resolved = resolve_safe_file_path(file_path, file_root=file_root)
    except ValueError as exc:
        return _result(
            status="unavailable",
            reason_code=str(exc),
            source={
                "filename": _sanitize_filename(file_path),
                "byte_size": 0,
                "media_type": "unknown",
                "input_mode": "path",
            },
            method="none",
        )

    size = resolved.stat().st_size
    source_base = {
        "filename": _sanitize_filename(resolved.name),
        "byte_size": size,
        "media_type": "application/pdf" if resolved.suffix.lower() in _PDF_SUFFIXES else "text/plain",
        "input_mode": "path",
        "path": resolved.name,
    }
    if size > MAX_TRANSCRIPT_BYTES:
        return _result(
            status="unavailable",
            reason_code="file_too_large",
            source=source_base,
            method="none",
        )

    suffix = resolved.suffix.lower()
    if suffix in _PDF_SUFFIXES:
        with resolved.open("rb") as handle:
            data = handle.read(MAX_TRANSCRIPT_BYTES + 1)
        if len(data) > MAX_TRANSCRIPT_BYTES:
            return _result(
                status="unavailable",
                reason_code="file_too_large",
                source=source_base,
                method="none",
            )
        pdf_result = parse_pdf_bytes(data, filename=resolved.name)
        if pdf_result.get("status") == "unavailable":
            return _result(
                status="unavailable",
                reason_code=pdf_result.get("reason_code") or "pdf_extract_failed",
                source={**source_base, "pdf_status": pdf_result.get("status")},
                method="pdf_then_transcript",
            )
        text = str(pdf_result.get("text") or "")
        parsed = parse_transcript_text(
            text,
            filename=resolved.name,
            max_chars=max_chars,
            max_chunk_chars=max_chunk_chars,
        )
        parsed["method"] = "pdf_then_transcript"
        parsed["source"] = {
            **parsed.get("source", {}),
            **source_base,
            "pdf_page_count": (pdf_result.get("source") or {}).get("page_count"),
            "pdf_method": pdf_result.get("method"),
        }
        return parsed

    if suffix and suffix not in _TEXT_SUFFIXES:
        logger.debug(
            "Transcript path has non-text suffix=%s; attempting utf-8 text read",
            suffix,
        )

    try:
        raw = resolved.read_bytes()
    except OSError as exc:
        log_safe_exception(
            logger,
            "Failed to read transcript file",
            exc,
            error_code="transcript_file_read_failed",
            level=logging.WARNING,
        )
        return _result(
            status="unavailable",
            reason_code="file_read_failed",
            source=source_base,
            method="none",
        )
    if len(raw) > MAX_TRANSCRIPT_BYTES:
        return _result(
            status="unavailable",
            reason_code="file_too_large",
            source=source_base,
            method="none",
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")

    parsed = parse_transcript_text(
        text,
        filename=resolved.name,
        max_chars=max_chars,
        max_chunk_chars=max_chunk_chars,
    )
    parsed["source"] = {**parsed.get("source", {}), **source_base}
    return parsed


def assert_metrics_source_traceable(
    text: str,
    metrics: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    """Return metrics that fail the source-equality contract (empty if honest)."""
    failures: list[Mapping[str, Any]] = []
    for metric in metrics:
        try:
            start = int(metric["start_char"])
            end = int(metric["end_char"])
            value = str(metric["value_text"])
        except (KeyError, TypeError, ValueError):
            failures.append(dict(metric))
            continue
        if not (0 <= start < end <= len(text)) or text[start:end] != value:
            failures.append(dict(metric))
    return failures


class EarningsTranscriptService:
    """Thin service wrapper used by Agent tools and tests."""

    def __init__(self, *, file_root: Optional[str] = None) -> None:
        self._file_root = file_root

    def parse_text(
        self,
        text: str,
        *,
        filename: Optional[str] = None,
        max_chunk_chars: int = MAX_CHUNK_CHARS,
    ) -> dict[str, Any]:
        return parse_transcript_text(
            text,
            filename=filename,
            max_chunk_chars=max_chunk_chars,
        )

    def parse_path(
        self,
        file_path: str,
        *,
        max_chunk_chars: int = MAX_CHUNK_CHARS,
    ) -> dict[str, Any]:
        return parse_transcript_path(
            file_path,
            file_root=self._file_root,
            max_chunk_chars=max_chunk_chars,
        )
