# -*- coding: utf-8 -*-
"""Report export service: convert rendered Markdown reports to archive formats.

This module is a **presentation-layer converter**. It never rebuilds analysis
results or mutates report content. Callers supply already-rendered Markdown
(for example from ``HistoryService.get_markdown_report`` or
``report_renderer.render``).

Formats
-------
- ``md``: always available (UTF-8 bytes of the input Markdown).
- ``pdf``: optional; requires the ``fpdf2`` package (see
  ``requirements-report-export.txt``). Pure-Python PDF stack chosen so default
  installs stay free of system libraries (unlike WeasyPrint) and free of a
  headless browser.

Chinese fonts
-------------
PDF export embeds a TrueType/OpenType font. Resolution order:

1. ``REPORT_EXPORT_PDF_FONT_PATH`` (absolute path to a ``.ttf`` / ``.otf`` file)
2. Common OS CJK / Unicode font locations

When no usable font is found, export fails with an explicit message (no silent
tofu/boxes fallback for CJK-heavy reports).

Charts / images
---------------
Markdown image syntax is replaced with a short textual omission note. Remote
chart bytes are not fetched at export time (avoids network and secret leakage
into the archive).
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

SUPPORTED_FORMATS = ("md", "pdf")
PDF_OPTIONAL_PACKAGE = "fpdf2"
PDF_INSTALL_HINT = (
    "PDF export requires the optional dependency set. Install after the default "
    "StockPulse requirements:\n"
    "  python -m pip install --build-constraint build-constraints.txt "
    "-r requirements-report-export.txt\n"
    "Default analysis, API, Web, and notifications do not need this package."
)

# Image markdown: ![alt](url) — replaced, never fetched.
_IMAGE_MD_RE = re.compile(r"!\[([^\]]*)\]\([^)]+\)")
# Fenced code blocks
_FENCE_RE = re.compile(r"```([^\n`]*)\n(.*?)```", re.DOTALL)
# ATX headings
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
# Unordered / ordered list items
_UL_RE = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_OL_RE = re.compile(r"^(\s*)(\d+)[.)]\s+(.*)$")
# Table separator row
_TABLE_SEP_RE = re.compile(r"^\s*\|?(?:\s*:?-+:?\s*\|)+\s*:?-+:?\s*\|?\s*$")
# Strip simple inline markers for PDF plain runs (content preserved, markers removed)
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
_CODE_INLINE_RE = re.compile(r"`([^`]+)`")
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")

_IMAGE_OMISSION_NOTE_ZH = "（图表/图片已在 PDF 导出中省略，请参阅原报告 Markdown 附件）"
_IMAGE_OMISSION_NOTE_EN = "(Chart/image omitted in PDF export; see the Markdown attachment.)"

# Common CJK-capable TrueType/OpenType paths (TTF/OTF only; TTC needs fonttools).
_DEFAULT_FONT_CANDIDATES: Tuple[str, ...] = (
    # Linux
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    # macOS
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    # Windows
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyh.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\arialuni.ttf",
    r"C:\Windows\Fonts\NotoSansSC-Regular.otf",
)


class ReportExportError(Exception):
    """Base error for report export failures."""

    def __init__(self, message: str, *, error_code: str = "export_failed") -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code


class ReportExportDependencyError(ReportExportError):
    """Raised when an optional export backend package is not installed."""

    def __init__(self, message: str, *, install_hint: str = PDF_INSTALL_HINT) -> None:
        super().__init__(message, error_code="export_dependency_missing")
        self.install_hint = install_hint


class ReportExportFontError(ReportExportError):
    """Raised when PDF export cannot locate a usable font file."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="export_font_missing")


class ReportExportFormatError(ReportExportError):
    """Raised for unsupported or empty export requests."""

    def __init__(self, message: str, *, error_code: str = "export_format_invalid") -> None:
        super().__init__(message, error_code=error_code)


@dataclass(frozen=True)
class ExportArtifact:
    """Bytes plus HTTP-facing metadata for one export."""

    content: bytes
    media_type: str
    filename: str
    format: str


def is_pdf_dependency_available() -> bool:
    """Return True when the optional PDF package can be imported."""
    try:
        import fpdf  # noqa: F401
    except ImportError:
        return False
    return True


def _configured_font_path() -> Optional[str]:
    raw = os.environ.get("REPORT_EXPORT_PDF_FONT_PATH", "").strip()
    return raw or None


def _is_supported_font_file(path: Path) -> bool:
    """fpdf2 add_font supports TTF/OTF; TTC often needs fonttools and is skipped."""
    if not path.is_file():
        return False
    suffix = path.suffix.lower()
    return suffix in {".ttf", ".otf"}


def resolve_pdf_font_path(
    *,
    configured: Optional[str] = None,
    candidates: Optional[Sequence[str]] = None,
) -> Optional[str]:
    """Return the first usable font path, or None when none are available."""
    ordered: List[str] = []
    cfg = configured if configured is not None else _configured_font_path()
    if cfg:
        ordered.append(cfg)
    ordered.extend(candidates if candidates is not None else _DEFAULT_FONT_CANDIDATES)
    seen = set()
    for item in ordered:
        if not item or item in seen:
            continue
        seen.add(item)
        path = Path(item).expanduser()
        if _is_supported_font_file(path):
            return str(path.resolve())
    return None


def get_export_capabilities() -> Dict[str, Any]:
    """Describe which export formats are available in the current process."""
    pdf_available = is_pdf_dependency_available()
    font_path = resolve_pdf_font_path() if pdf_available else None
    return {
        "formats": {
            "md": {
                "available": True,
                "media_type": "text/markdown; charset=utf-8",
                "dependency": None,
            },
            "pdf": {
                "available": bool(pdf_available and font_path),
                "media_type": "application/pdf",
                "dependency": PDF_OPTIONAL_PACKAGE,
                "dependency_installed": pdf_available,
                "font_resolved": bool(font_path),
                "font_path": font_path,
                "install_hint": PDF_INSTALL_HINT,
                "remaining_formats": ["docx", "xlsx"],
            },
        },
        "supported_query_formats": list(SUPPORTED_FORMATS),
        "office_formats_status": "not_implemented",
        "chart_handling": "markdown_images_omitted",
    }


def _detect_primarily_chinese(text: str) -> bool:
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    return cjk >= 8 or (cjk > 0 and cjk * 3 >= max(len(text), 1) // 10)


def _strip_images_for_pdf(markdown: str) -> Tuple[str, int]:
    note = (
        _IMAGE_OMISSION_NOTE_ZH
        if _detect_primarily_chinese(markdown)
        else _IMAGE_OMISSION_NOTE_EN
    )
    count = 0

    def _repl(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        alt = (match.group(1) or "").strip()
        if alt:
            return f"[{alt}] {note}"
        return note

    cleaned = _IMAGE_MD_RE.sub(_repl, markdown)
    return cleaned, count


def _plain_inline(text: str) -> str:
    text = _BOLD_RE.sub(r"\1", text)
    text = _ITALIC_RE.sub(r"\1", text)
    text = _CODE_INLINE_RE.sub(r"\1", text)
    text = _LINK_RE.sub(r"\1", text)
    return text.strip()


def _split_table_row(line: str) -> List[str]:
    raw = line.strip()
    if raw.startswith("|"):
        raw = raw[1:]
    if raw.endswith("|"):
        raw = raw[:-1]
    return [cell.strip() for cell in raw.split("|")]


def _parse_markdown_blocks(markdown: str) -> List[Tuple[str, Any]]:
    """Parse Markdown into a small set of PDF-friendly blocks.

    This is intentionally lossy for exotic Markdown; structure (headings,
    lists, tables, code, paragraphs) is preserved for stock reports.
    """
    text, _ = _strip_images_for_pdf(markdown)
    fences: List[Tuple[str, str]] = []

    def _fence_repl(match: re.Match[str]) -> str:
        fences.append(((match.group(1) or "").strip(), match.group(2)))
        return f"\n@@FENCE{len(fences) - 1}@@\n"

    text = _FENCE_RE.sub(_fence_repl, text)
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks: List[Tuple[str, Any]] = []
    i = 0
    para_buf: List[str] = []

    def flush_para() -> None:
        nonlocal para_buf
        if para_buf:
            blocks.append(("paragraph", " ".join(para_buf).strip()))
            para_buf = []

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        fence_m = re.fullmatch(r"@@FENCE(\d+)@@", stripped)
        if fence_m:
            flush_para()
            lang, body = fences[int(fence_m.group(1))]
            blocks.append(("code", {"lang": lang, "body": body.rstrip("\n")}))
            i += 1
            continue

        if not stripped:
            flush_para()
            i += 1
            continue

        heading_m = _HEADING_RE.match(stripped)
        if heading_m:
            flush_para()
            level = len(heading_m.group(1))
            blocks.append(("heading", {"level": level, "text": _plain_inline(heading_m.group(2))}))
            i += 1
            continue

        if stripped.startswith(">"):
            flush_para()
            quote_lines = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote_lines.append(lines[i].strip().lstrip(">").strip())
                i += 1
            blocks.append(("quote", _plain_inline(" ".join(quote_lines))))
            continue

        if "|" in stripped and i + 1 < len(lines) and _TABLE_SEP_RE.match(lines[i + 1]):
            flush_para()
            header = _split_table_row(stripped)
            i += 2
            rows: List[List[str]] = []
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append([_plain_inline(c) for c in _split_table_row(lines[i])])
                i += 1
            blocks.append(
                (
                    "table",
                    {
                        "header": [_plain_inline(c) for c in header],
                        "rows": rows,
                    },
                )
            )
            continue

        ul_m = _UL_RE.match(line)
        if ul_m:
            flush_para()
            items: List[str] = []
            while i < len(lines):
                m = _UL_RE.match(lines[i])
                if not m:
                    break
                items.append(_plain_inline(m.group(2)))
                i += 1
            blocks.append(("ul", items))
            continue

        ol_m = _OL_RE.match(line)
        if ol_m:
            flush_para()
            items = []
            while i < len(lines):
                m = _OL_RE.match(lines[i])
                if not m:
                    break
                items.append(_plain_inline(m.group(3)))
                i += 1
            blocks.append(("ol", items))
            continue

        if stripped in {"---", "***", "___"}:
            flush_para()
            blocks.append(("hr", None))
            i += 1
            continue

        para_buf.append(_plain_inline(stripped))
        i += 1

    flush_para()
    return blocks


def _render_pdf_bytes(
    markdown: str,
    *,
    font_path: str,
    title: Optional[str] = None,
) -> bytes:
    try:
        from fpdf import FPDF
    except ImportError as exc:
        raise ReportExportDependencyError(
            f"Optional package '{PDF_OPTIONAL_PACKAGE}' is not installed."
        ) from exc

    class _ReportPDF(FPDF):
        def footer(self) -> None:  # noqa: D102 - fpdf hook
            self.set_y(-12)
            self.set_font("ReportFont", size=8)
            self.cell(0, 8, f"{self.page_no()}", align="C")

    pdf = _ReportPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_margins(16, 16, 16)
    try:
        pdf.add_font("ReportFont", "", font_path)
    except Exception as exc:  # broad-exception: fallback_recorded - surface as font error for API
        log_safe_exception(
            logger,
            "PDF font load failed for report export",
            exc,
            error_code="export_font_load_failed",
            level=logging.WARNING,
            context={"font_path": font_path},
        )
        raise ReportExportFontError(
            f"Failed to load PDF font at '{font_path}': {exc}. "
            "Set REPORT_EXPORT_PDF_FONT_PATH to a .ttf/.otf font that covers Chinese glyphs."
        ) from exc

    if title:
        pdf.set_title(title[:180])
    pdf.add_page()
    pdf.set_font("ReportFont", size=11)

    def _write_flow(text: str, *, h: float = 6, indent: float = 0) -> None:
        """Write a flowing multi_cell always starting at left margin (+indent)."""
        pdf.set_x(pdf.l_margin + indent)
        width = pdf.epw - indent
        if width < 10:
            width = pdf.epw
            pdf.set_x(pdf.l_margin)
        pdf.multi_cell(width, h, text)
        pdf.set_x(pdf.l_margin)

    blocks = _parse_markdown_blocks(markdown)
    for kind, payload in blocks:
        if kind == "heading":
            level = int(payload["level"])
            size = {1: 18, 2: 15, 3: 13}.get(level, 12)
            pdf.ln(4 if level <= 2 else 2)
            pdf.set_font("ReportFont", size=size)
            _write_flow(str(payload["text"]), h=max(size * 0.55, 6))
            pdf.set_font("ReportFont", size=11)
            pdf.ln(1)
        elif kind == "paragraph":
            _write_flow(str(payload), h=6)
            pdf.ln(1)
        elif kind == "quote":
            _write_flow(str(payload), h=6, indent=6)
            pdf.ln(1)
        elif kind == "ul":
            for item in payload:
                _write_flow(f"• {item}", h=6)
            pdf.ln(1)
        elif kind == "ol":
            for idx, item in enumerate(payload, start=1):
                _write_flow(f"{idx}. {item}", h=6)
            pdf.ln(1)
        elif kind == "code":
            body = str(payload.get("body") or "")
            pdf.set_font("ReportFont", size=9)
            for code_line in body.split("\n") or [""]:
                _write_flow(code_line if code_line else " ", h=5)
            pdf.set_font("ReportFont", size=11)
            pdf.ln(1)
        elif kind == "table":
            # Keep table layout simple: single-line cells + explicit left margin
            # reset. multi_cell per-cell layouts leave the cursor mid-row and
            # break subsequent blocks with "Not enough horizontal space".
            header: List[str] = list(payload.get("header") or [])
            rows: List[List[str]] = list(payload.get("rows") or [])
            col_count = max(len(header), max((len(r) for r in rows), default=0), 1)
            col_w = pdf.epw / col_count
            pdf.set_font("ReportFont", size=9)
            pdf.set_x(pdf.l_margin)
            if header:
                for cell in header + [""] * (col_count - len(header)):
                    pdf.cell(col_w, 7, str(cell)[:40], border=1)
                pdf.ln()
                pdf.set_x(pdf.l_margin)
            for row in rows:
                padded = row + [""] * (col_count - len(row))
                pdf.set_x(pdf.l_margin)
                for cell in padded:
                    pdf.cell(col_w, 7, str(cell)[:40], border=1)
                pdf.ln()
            pdf.set_x(pdf.l_margin)
            pdf.set_font("ReportFont", size=11)
            pdf.ln(2)
        elif kind == "hr":
            y = pdf.get_y() + 2
            pdf.line(pdf.l_margin, y, pdf.l_margin + pdf.epw, y)
            pdf.ln(4)

    # fpdf2 >=2.2 returns bytes/bytearray from output() without dest=
    raw = pdf.output()
    if isinstance(raw, (bytes, bytearray)):
        return bytes(raw)
    return str(raw).encode("latin-1")


def _safe_filename_stem(stem: str) -> str:
    cleaned = re.sub(r"[^\w.\-]+", "_", stem.strip(), flags=re.UNICODE)
    cleaned = cleaned.strip("._") or "report"
    return cleaned[:80]


def export_markdown_bytes(markdown: str, *, filename_stem: str = "report") -> ExportArtifact:
    """Export Markdown as UTF-8 bytes (always available, no optional deps)."""
    if markdown is None:
        raise ReportExportFormatError("Report content is empty", error_code="export_empty")
    content = str(markdown)
    if not content.strip():
        raise ReportExportFormatError("Report content is empty", error_code="export_empty")
    stem = _safe_filename_stem(filename_stem)
    return ExportArtifact(
        content=content.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        filename=f"{stem}.md",
        format="md",
    )


def export_pdf_bytes(
    markdown: str,
    *,
    filename_stem: str = "report",
    title: Optional[str] = None,
    font_path: Optional[str] = None,
) -> ExportArtifact:
    """Export Markdown to PDF when the optional dependency and a font are present."""
    if markdown is None or not str(markdown).strip():
        raise ReportExportFormatError("Report content is empty", error_code="export_empty")
    if not is_pdf_dependency_available():
        raise ReportExportDependencyError(
            f"Optional package '{PDF_OPTIONAL_PACKAGE}' is not installed. {PDF_INSTALL_HINT}"
        )
    resolved_font = font_path or resolve_pdf_font_path()
    if not resolved_font:
        raise ReportExportFontError(
            "No usable PDF font found for report export. "
            "Set REPORT_EXPORT_PDF_FONT_PATH to a .ttf or .otf file that covers "
            "the report language (Chinese reports need a CJK-capable font). "
            "Collection TrueType fonts (.ttc) are not used without extra tooling."
        )
    pdf_bytes = _render_pdf_bytes(
        str(markdown),
        font_path=resolved_font,
        title=title or filename_stem,
    )
    if not pdf_bytes.startswith(b"%PDF"):
        raise ReportExportError("PDF backend returned non-PDF bytes", error_code="export_pdf_invalid")
    stem = _safe_filename_stem(filename_stem)
    return ExportArtifact(
        content=pdf_bytes,
        media_type="application/pdf",
        filename=f"{stem}.pdf",
        format="pdf",
    )


def export_report(
    markdown: str,
    fmt: str,
    *,
    filename_stem: str = "stockpulse-report",
    title: Optional[str] = None,
    font_path: Optional[str] = None,
) -> ExportArtifact:
    """Export Markdown to the requested format.

    Parameters
    ----------
    markdown:
        Already-rendered report text. Must not contain secrets; the service does
        not redact beyond what callers provide.
    fmt:
        ``md`` or ``pdf`` (case-insensitive).
    """
    normalized = (fmt or "").strip().lower()
    if normalized not in SUPPORTED_FORMATS:
        raise ReportExportFormatError(
            f"Unsupported export format '{fmt}'. Supported: {', '.join(SUPPORTED_FORMATS)}. "
            "Office formats (docx, xlsx) are not implemented in this release."
        )
    if normalized == "md":
        return export_markdown_bytes(markdown, filename_stem=filename_stem)
    return export_pdf_bytes(
        markdown,
        filename_stem=filename_stem,
        title=title,
        font_path=font_path,
    )


def capabilities_public_view(payload: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Return capabilities without absolute font paths (safe for API clients)."""
    data = dict(payload or get_export_capabilities())
    formats = data.get("formats")
    if isinstance(formats, dict):
        pdf = formats.get("pdf")
        if isinstance(pdf, dict):
            pdf = dict(pdf)
            pdf.pop("font_path", None)
            formats = dict(formats)
            formats["pdf"] = pdf
            data["formats"] = formats
    return data
