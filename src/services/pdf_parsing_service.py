# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Local-first financial PDF parsing for analysis context (issue #253 phase 1).

Extracts structured text and best-effort table-like rows from user-supplied
PDF bytes. Never executes PDF content. Vision-model assist for scanned pages
is reserved for a later phase; phase 1 degrades honestly when local extraction
is empty or sparse.
"""

from __future__ import annotations

import logging
import re
import zlib
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

PDF_SCHEMA_VERSION = "pdf-parse-v1"
PDF_DISCLAIMER = (
    "Parsed document text is for research support only. Extraction quality "
    "depends on the PDF structure; scanned pages without text layers may yield "
    "empty or partial results. Not investment advice."
)

MAX_PDF_BYTES = 10 * 1024 * 1024  # 10 MiB
MAX_PDF_PAGES = 50
MAX_PAGE_TEXT_CHARS = 20_000
MAX_TOTAL_TEXT_CHARS = 100_000
MAX_TABLE_ROWS = 100
MAX_FILENAME_CHARS = 255

_PDF_HEADER_RE = re.compile(rb"%PDF-(\d+(?:\.\d+)?)")
_STREAM_RE = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.DOTALL)
_TJ_RE = re.compile(r"\((?:\\.|[^\\)])*\)\s*Tj")
_TJ_ARRAY_RE = re.compile(r"\[(.*?)\]\s*TJ", re.DOTALL)
_STRING_RE = re.compile(r"\((?:\\.|[^\\)])*\)")
_HEX_STRING_RE = re.compile(r"<([0-9A-Fa-f\s]+)>")
_WHITESPACE_RE = re.compile(r"[ \t\f\v]+")
_NUMERIC_TOKEN_RE = re.compile(r"^-?\d+(?:\.\d+)?%?$")


def _result(
    *,
    status: str,
    reason_code: Optional[str] = None,
    source: Optional[Mapping[str, Any]] = None,
    text: str = "",
    pages: Optional[Sequence[Mapping[str, Any]]] = None,
    tables: Optional[Sequence[Mapping[str, Any]]] = None,
    method: str = "local",
    vision_assist: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    return {
        "schema_version": PDF_SCHEMA_VERSION,
        "status": status,
        "reason_code": reason_code,
        "source": dict(source or {}),
        "text": text,
        "pages": list(pages or []),
        "tables": list(tables or []),
        "method": method,
        "vision_assist": dict(
            vision_assist
            or {
                "status": "not_applicable",
                "reason": "phase1_local_text_only",
            }
        ),
        "disclaimer": PDF_DISCLAIMER,
    }


def _unescape_pdf_string(raw: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(raw):
        ch = raw[i]
        if ch != "\\" or i + 1 >= len(raw):
            out.append(ch)
            i += 1
            continue
        nxt = raw[i + 1]
        if nxt in "nrtbf()\\":
            mapping = {
                "n": "\n",
                "r": "\r",
                "t": "\t",
                "b": "\b",
                "f": "\f",
                "(": "(",
                ")": ")",
                "\\": "\\",
            }
            out.append(mapping[nxt])
            i += 2
            continue
        if nxt in "01234567":
            j = i + 1
            digits = ""
            while j < len(raw) and len(digits) < 3 and raw[j] in "01234567":
                digits += raw[j]
                j += 1
            out.append(chr(int(digits, 8)))
            i = j
            continue
        out.append(nxt)
        i += 2
    return "".join(out)


def _decode_pdf_strings_from_content(content: str) -> str:
    parts: list[str] = []
    for match in _TJ_RE.finditer(content):
        inner = match.group(0)
        # strip trailing " Tj" and outer parentheses
        string_body = inner[1 : inner.rfind(")")]
        parts.append(_unescape_pdf_string(string_body))
    for match in _TJ_ARRAY_RE.finditer(content):
        array_body = match.group(1)
        for sm in _STRING_RE.finditer(array_body):
            parts.append(_unescape_pdf_string(sm.group(0)[1:-1]))
        for hm in _HEX_STRING_RE.finditer(array_body):
            hex_digits = re.sub(r"\s+", "", hm.group(1))
            if len(hex_digits) % 2:
                hex_digits += "0"
            try:
                parts.append(bytes.fromhex(hex_digits).decode("latin-1", errors="replace"))
            except ValueError:
                continue
    if parts:
        return " ".join(parts)
    # Fallback: any literal strings in the content stream
    for sm in _STRING_RE.finditer(content):
        parts.append(_unescape_pdf_string(sm.group(0)[1:-1]))
    return " ".join(parts)


def _maybe_decompress_stream(stream_bytes: bytes, dict_header: bytes) -> bytes:
    if b"/FlateDecode" in dict_header or b"/Fl" in dict_header:
        try:
            return zlib.decompress(stream_bytes)
        except zlib.error:
            try:
                return zlib.decompress(stream_bytes, -15)
            except zlib.error:
                return stream_bytes
    return stream_bytes


def _extract_streams(data: bytes) -> list[str]:
    texts: list[str] = []
    for match in _STREAM_RE.finditer(data):
        stream_start = match.start()
        # Look back a limited window for the stream dictionary.
        header_window = data[max(0, stream_start - 400) : stream_start]
        raw = match.group(1)
        decoded = _maybe_decompress_stream(raw, header_window)
        # latin-1 with replace never fails; keep decode explicit for binary streams.
        content = decoded.decode("latin-1", errors="replace")
        # Only keep streams that look like content operators.
        if "Tj" not in content and "TJ" not in content and "BT" not in content:
            continue
        extracted = _decode_pdf_strings_from_content(content)
        cleaned = _WHITESPACE_RE.sub(" ", extracted).strip()
        if cleaned:
            texts.append(cleaned[:MAX_PAGE_TEXT_CHARS])
    return texts


def _try_pypdf(data: bytes) -> list[str]:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        try:
            from PyPDF2 import PdfReader  # type: ignore
        except ImportError:
            return []

    import io

    try:
        reader = PdfReader(io.BytesIO(data))
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        log_safe_exception(
            logger,
            "Optional pypdf reader failed; using built-in stream extractor",
            exc,
            error_code="pdf_pypdf_reader_failed",
            level=logging.DEBUG,
        )
        return []

    pages: list[str] = []
    for index, page in enumerate(reader.pages[:MAX_PDF_PAGES]):
        try:
            text = page.extract_text() or ""
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            log_safe_exception(
                logger,
                "Optional pypdf page extract failed; skipping page",
                exc,
                error_code="pdf_pypdf_page_failed",
                level=logging.DEBUG,
                context={"page_index": index},
            )
            text = ""
        cleaned = _WHITESPACE_RE.sub(" ", str(text)).strip()
        if cleaned:
            pages.append(cleaned[:MAX_PAGE_TEXT_CHARS])
        else:
            pages.append("")
        if index + 1 >= MAX_PDF_PAGES:
            break
    return pages


def _infer_tables(page_texts: Sequence[str]) -> list[dict[str, Any]]:
    """Best-effort detection of whitespace-separated numeric rows."""
    rows: list[dict[str, Any]] = []
    for page_index, page_text in enumerate(page_texts, start=1):
        for line in re.split(r"[\n\r]+", page_text):
            tokens = [t for t in re.split(r"\s{2,}|\t+|,", line.strip()) if t]
            if len(tokens) < 2:
                # Also accept single-space rows with multiple numeric tokens.
                tokens = line.strip().split()
            if len(tokens) < 2:
                continue
            numeric_count = sum(1 for t in tokens if _NUMERIC_TOKEN_RE.match(t.replace(",", "")))
            if numeric_count < 1 or numeric_count < max(1, len(tokens) // 3):
                continue
            rows.append(
                {
                    "page": page_index,
                    "cells": tokens[:32],
                    "numeric_cell_count": numeric_count,
                }
            )
            if len(rows) >= MAX_TABLE_ROWS:
                return rows
    return rows


def _sanitize_filename(name: Optional[str]) -> str:
    if not name:
        return "document.pdf"
    base = Path(str(name)).name.strip()
    if not base or base in {".", ".."}:
        return "document.pdf"
    base = re.sub(r"[^\w.\- ()\[\]]+", "_", base, flags=re.UNICODE)
    return base[:MAX_FILENAME_CHARS] or "document.pdf"


def parse_pdf_bytes(
    data: bytes,
    *,
    filename: Optional[str] = None,
    max_pages: int = MAX_PDF_PAGES,
) -> dict[str, Any]:
    """Parse PDF bytes into structured text/tables for analysis context."""
    safe_name = _sanitize_filename(filename)
    source = {
        "filename": safe_name,
        "byte_size": len(data) if data else 0,
        "page_count": 0,
        "media_type": "application/pdf",
    }

    if not data:
        return _result(
            status="unavailable",
            reason_code="empty_input",
            source=source,
            method="none",
        )
    if len(data) > MAX_PDF_BYTES:
        return _result(
            status="unavailable",
            reason_code="file_too_large",
            source=source,
            method="none",
        )
    if not data.lstrip().startswith(b"%PDF"):
        # Allow leading whitespace but still require a real header soon.
        header = _PDF_HEADER_RE.search(data[:1024])
        if header is None:
            return _result(
                status="unavailable",
                reason_code="invalid_pdf_header",
                source=source,
                method="none",
            )

    page_limit = max(1, min(int(max_pages or MAX_PDF_PAGES), MAX_PDF_PAGES))

    # Prefer pypdf when installed for broader real-world PDF coverage; always
    # fall back to the stdlib stream extractor used by deterministic fixtures.
    page_texts = _try_pypdf(data)
    method = "local_pypdf" if page_texts else "local"
    if not page_texts:
        page_texts = _extract_streams(data)

    page_texts = list(page_texts[:page_limit])
    # If stream extractor returned a flat list of content streams, treat each as a page.
    pages_payload = []
    for index, text in enumerate(page_texts, start=1):
        pages_payload.append(
            {
                "page": index,
                "text": text[:MAX_PAGE_TEXT_CHARS],
                "char_count": len(text),
            }
        )

    combined = "\n\n".join(p["text"] for p in pages_payload if p["text"]).strip()
    if len(combined) > MAX_TOTAL_TEXT_CHARS:
        combined = combined[:MAX_TOTAL_TEXT_CHARS]
    source = {
        **source,
        "page_count": len(pages_payload),
        "extractor": method,
    }
    tables = _infer_tables([p["text"] for p in pages_payload])

    if not combined:
        return _result(
            status="unavailable",
            reason_code="no_extractable_text",
            source=source,
            pages=pages_payload,
            tables=tables,
            method=method,
            vision_assist={
                "status": "skipped",
                "reason": "phase1_no_page_rasterization",
            },
        )

    status = "available"
    reason_code = None
    if len(combined) < 40:
        status = "degraded"
        reason_code = "sparse_text"

    return _result(
        status=status,
        reason_code=reason_code,
        source=source,
        text=combined,
        pages=pages_payload,
        tables=tables,
        method=method,
    )


def resolve_safe_file_path(
    file_path: str,
    *,
    file_root: Optional[str] = None,
) -> Path:
    """Resolve a user path under an optional root with traversal protection.

    Raises ValueError with a stable reason token on failure.
    """
    if file_path is None or not str(file_path).strip():
        raise ValueError("empty_path")
    raw = str(file_path).strip()
    if "\x00" in raw:
        raise ValueError("invalid_path")
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", raw):
        raise ValueError("url_not_allowed")
    if raw.startswith("~"):
        raise ValueError("home_expansion_not_allowed")

    candidate = Path(raw)
    if file_root:
        root = Path(file_root).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            raise ValueError("file_root_unavailable")
        # Relative paths are resolved under root; absolute paths must stay inside root.
        if candidate.is_absolute():
            resolved = candidate.resolve()
        else:
            resolved = (root / candidate).resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError("path_outside_root") from exc
    else:
        if not candidate.is_absolute():
            raise ValueError("absolute_path_required")
        resolved = candidate.resolve()

    if not resolved.exists() or not resolved.is_file():
        raise ValueError("file_not_found")
    return resolved


def parse_pdf_path(
    file_path: str,
    *,
    file_root: Optional[str] = None,
    max_pages: int = MAX_PDF_PAGES,
) -> dict[str, Any]:
    """Read and parse a local PDF path after sanitization."""
    try:
        resolved = resolve_safe_file_path(file_path, file_root=file_root)
    except ValueError as exc:
        return _result(
            status="unavailable",
            reason_code=str(exc),
            source={"filename": _sanitize_filename(file_path), "byte_size": 0, "page_count": 0},
            method="none",
        )

    size = resolved.stat().st_size
    if size > MAX_PDF_BYTES:
        return _result(
            status="unavailable",
            reason_code="file_too_large",
            source={
                "filename": _sanitize_filename(resolved.name),
                "byte_size": size,
                "page_count": 0,
            },
            method="none",
        )

    # Read with a hard byte cap; reject if more data remains.
    with resolved.open("rb") as handle:
        data = handle.read(MAX_PDF_BYTES + 1)
    if len(data) > MAX_PDF_BYTES:
        return _result(
            status="unavailable",
            reason_code="file_too_large",
            source={
                "filename": _sanitize_filename(resolved.name),
                "byte_size": size,
                "page_count": 0,
            },
            method="none",
        )
    return parse_pdf_bytes(data, filename=resolved.name, max_pages=max_pages)


class PdfParsingService:
    """Thin service wrapper used by Agent tools and tests."""

    def __init__(self, *, file_root: Optional[str] = None) -> None:
        self._file_root = file_root

    def parse_bytes(self, data: bytes, *, filename: Optional[str] = None) -> dict[str, Any]:
        return parse_pdf_bytes(data, filename=filename)

    def parse_path(self, file_path: str, *, max_pages: int = MAX_PDF_PAGES) -> dict[str, Any]:
        return parse_pdf_path(
            file_path,
            file_root=self._file_root,
            max_pages=max_pages,
        )
