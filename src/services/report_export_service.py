# -*- coding: utf-8 -*-
"""Bounded Markdown, office-friendly HTML, and optional PDF report export.

Markdown is the lossless archive format and is always available. HTML is the
office-friendly presentation format (Word / LibreOffice open it directly) and
reuses the same ``markdown-it-py`` AST as PDF so link destinations and image
URLs never leak. PDF is an optional fpdf2 presentation transform: it validates
the exact report glyph set before rendering, wraps table cells without deleting
content, and enforces explicit resource bounds. DOCX/XLSX remain deferred in
favor of this pure-Python HTML path (no ``python-docx`` dependency).
"""

from __future__ import annotations

import hashlib
import html
import importlib
import importlib.metadata
import logging
import multiprocessing
import re
import threading
import time
import unicodedata
from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

SUPPORTED_FORMATS = ("md", "html", "pdf")
PDF_OPTIONAL_PACKAGE = "fpdf2"
HTML_OPTIONAL_PACKAGE = "markdown-it-py"
PDF_OPTIONAL_SUPPORT_PACKAGES: Tuple[Tuple[str, str], ...] = (
    ("fonttools", "fontTools"),
    ("markdown-it-py", "markdown_it"),
)
PDF_MIN_VERSION = (2, 7, 0)
PDF_MAX_MAJOR = 3
PDF_INSTALL_HINT = (
    "Install the optional report-export dependency set with "
    "'python -m pip install --build-constraint build-constraints.txt "
    "-r requirements-report-export.txt'."
)
HTML_INSTALL_HINT = PDF_INSTALL_HINT

MAX_PDF_INPUT_BYTES = 1_000_000
MAX_HTML_INPUT_BYTES = MAX_PDF_INPUT_BYTES
MAX_PDF_PAGES = 100
MAX_TABLE_ROWS = 500
MAX_TABLE_COLUMNS = 12
MAX_TOTAL_TABLE_CELLS = 3_000
PDF_RENDER_DEADLINE_SECONDS = 20.0
PDF_MAX_CONCURRENCY = 2
PDF_CACHE_ENTRIES = 12
PDF_CACHE_MAX_BYTES = 24 * 1024 * 1024
PDF_MAX_OUTPUT_BYTES = PDF_CACHE_MAX_BYTES
HTML_MAX_OUTPUT_BYTES = PDF_CACHE_MAX_BYTES
PDF_WORKER_SHUTDOWN_SECONDS = 1.0

_IMAGE_OMISSION_NOTE_ZH = "（图表/图片已在 PDF 导出中省略，请参阅原报告 Markdown 附件）"
_IMAGE_OMISSION_NOTE_EN = (
    "(Chart/image omitted in PDF export; see the Markdown attachment.)"
)

# Only formats that fpdf2 can load as a single face are probed. Collection
# fonts are deliberately excluded because selecting a face by platform index
# is not a stable operator contract.
_DEFAULT_FONT_CANDIDATES: Tuple[str, ...] = (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.otf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    r"C:\Windows\Fonts\msyh.ttf",
    r"C:\Windows\Fonts\arialuni.ttf",
    r"C:\Windows\Fonts\NotoSansSC-Regular.otf",
)

_CAPABILITY_GLYPHS: Dict[str, str] = {
    "en": "StockPulse report Buy Hold Sell Risk 0123456789 • ✅ ⚠ 🚨 📊",
    "zh": "股票分析报告 买入 持有 卖出 风险 0123456789 • ✅ ⚠ 🚨 📊",
    "zh-TW": "股票分析報告 買入 持有 賣出 風險 0123456789 • ✅ ⚠ 🚨 📊",
    "ja": "株式分析レポート 買い 保有 売り リスク 0123456789 • ✅ ⚠ 🚨 📊",
    "ko": "주식 분석 보고서 매수 보유 매도 위험 0123456789 • ✅ ⚠ 🚨 📊",
}


class ReportExportError(Exception):
    """Base error for report export failures."""

    def __init__(self, message: str, *, error_code: str = "export_failed") -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code


class ReportExportDependencyError(ReportExportError):
    """Raised when the fpdf namespace is absent, legacy, or incompatible."""

    def __init__(self, message: str, *, install_hint: str = PDF_INSTALL_HINT) -> None:
        super().__init__(message, error_code="export_dependency_missing")
        self.install_hint = install_hint


class ReportExportFontError(ReportExportError):
    """Raised when a configured font is invalid or lacks report glyphs."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "export_font_missing",
    ) -> None:
        super().__init__(message, error_code=error_code)


class ReportExportFormatError(ReportExportError):
    """Raised for unsupported or empty export requests."""

    def __init__(self, message: str, *, error_code: str = "export_format_invalid") -> None:
        super().__init__(message, error_code=error_code)


class ReportExportLimitError(ReportExportError):
    """Raised when a deterministic export resource bound is exceeded."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "export_limit_exceeded",
        status_code: int = 413,
    ) -> None:
        super().__init__(message, error_code=error_code)
        self.status_code = status_code


class ReportExportBusyError(ReportExportError):
    """Raised when all bounded synchronous PDF render slots are occupied."""

    def __init__(self) -> None:
        super().__init__(
            "PDF export capacity is busy; retry later.",
            error_code="export_busy",
        )
        self.status_code = 429


class ReportExportWorkerError(ReportExportError):
    """Raised when the isolated PDF renderer cannot start or return safely."""

    def __init__(self) -> None:
        super().__init__(
            "The isolated PDF render worker is unavailable.",
            error_code="export_worker_unavailable",
        )
        self.status_code = 503


@dataclass(frozen=True)
class ExportArtifact:
    """Bytes plus HTTP-facing metadata for one export."""

    content: bytes
    media_type: str
    filename: str
    format: str


@dataclass(frozen=True)
class PdfBackendStatus:
    """Validated fpdf2 distribution/import status."""

    available: bool
    status: str
    version: Optional[str] = None
    installed: Optional[bool] = None

    @property
    def dependency_installed(self) -> bool:
        """Distinguish an installed incompatible fpdf2 from legacy PyFPDF."""
        return self.installed if self.installed is not None else self.version is not None


@dataclass(frozen=True)
class FontInspection:
    """Sanitized font validation result plus internal Unicode coverage."""

    valid: bool
    status: str
    codepoints: frozenset[int] = frozenset()


_PDF_SEMAPHORE = threading.BoundedSemaphore(PDF_MAX_CONCURRENCY)
_PDF_CACHE_LOCK = threading.Lock()
_PDF_CACHE: "OrderedDict[str, ExportArtifact]" = OrderedDict()
_PDF_CACHE_BYTES = 0


def _version_tuple(value: str) -> Tuple[int, int, int]:
    parts = [int(item) for item in re.findall(r"\d+", value)[:3]]
    return tuple((parts + [0, 0, 0])[:3])  # type: ignore[return-value]


def inspect_pdf_backend() -> PdfBackendStatus:
    """Verify the fpdf2 distribution and reject the legacy PyFPDF conflict."""
    try:
        version = importlib.metadata.version(PDF_OPTIONAL_PACKAGE)
    except importlib.metadata.PackageNotFoundError:
        distributions = {
            item.lower()
            for item in importlib.metadata.packages_distributions().get("fpdf", [])
        }
        if "fpdf" in distributions:
            return PdfBackendStatus(
                False,
                "legacy_namespace_conflict",
                None,
                False,
            )
        return PdfBackendStatus(False, "dependency_missing", installed=False)

    try:
        import fpdf
        from fpdf import FPDF  # noqa: F401
    except (ImportError, AttributeError):
        return PdfBackendStatus(False, "dependency_import_invalid", version, True)

    distributions = {
        item.lower()
        for item in importlib.metadata.packages_distributions().get("fpdf", [])
    }
    if "fpdf" in distributions:
        return PdfBackendStatus(False, "legacy_namespace_conflict", version, True)

    for distribution, module_name in PDF_OPTIONAL_SUPPORT_PACKAGES:
        try:
            importlib.metadata.version(distribution)
            importlib.import_module(module_name)
        except importlib.metadata.PackageNotFoundError:
            return PdfBackendStatus(False, "dependency_missing", version, True)
        except (ImportError, AttributeError):
            return PdfBackendStatus(False, "dependency_import_invalid", version, True)

    parsed = _version_tuple(version)
    module_version = str(getattr(fpdf, "__version__", ""))
    if (
        parsed < PDF_MIN_VERSION
        or parsed[0] >= PDF_MAX_MAJOR
        or _version_tuple(module_version) != parsed
    ):
        return PdfBackendStatus(False, "dependency_version_invalid", version, True)
    return PdfBackendStatus(True, "ready", version, True)


def is_pdf_dependency_available() -> bool:
    """Return whether the exact supported fpdf2 backend is ready."""
    return inspect_pdf_backend().available


@dataclass(frozen=True)
class HtmlBackendStatus:
    """Validated markdown-it-py availability for structured HTML export."""

    available: bool
    status: str
    version: Optional[str] = None
    installed: Optional[bool] = None

    @property
    def dependency_installed(self) -> bool:
        return self.installed if self.installed is not None else self.version is not None


def inspect_html_backend() -> HtmlBackendStatus:
    """Verify markdown-it-py so HTML can reuse the secret-safe Markdown AST."""
    try:
        version = importlib.metadata.version(HTML_OPTIONAL_PACKAGE)
    except importlib.metadata.PackageNotFoundError:
        return HtmlBackendStatus(False, "dependency_missing", installed=False)
    try:
        importlib.import_module("markdown_it")
    except (ImportError, AttributeError):
        return HtmlBackendStatus(False, "dependency_import_invalid", version, True)
    return HtmlBackendStatus(True, "ready", version, True)


def is_html_dependency_available() -> bool:
    """Return whether structured HTML export can parse the Markdown AST."""
    return inspect_html_backend().available


def _configured_font_path() -> Optional[str]:
    """Read the font path from the shared runtime Config owner."""
    try:
        from src.application_services import get_application_services

        raw = getattr(
            get_application_services().config,
            "report_export_pdf_font_path",
            None,
        )
    except Exception as exc:  # broad-exception: fallback_recorded - config diagnostics own details
        log_safe_exception(
            logger,
            "Report export config lookup failed",
            exc,
            error_code="export_config_lookup_failed",
            level=logging.WARNING,
        )
        raw = None
    return str(raw).strip() if raw else None


def _font_signature(path: Path) -> Tuple[str, int, int]:
    stat = path.stat()
    return (str(path.resolve()), stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=24)
def _inspect_font_signature(signature: Tuple[str, int, int]) -> FontInspection:
    path = signature[0]
    try:
        from fontTools.ttLib import TTFont

        font = TTFont(path, lazy=False)
        try:
            cmap = font.getBestCmap() or {}
            codepoints = frozenset(int(value) for value in cmap)
        finally:
            font.close()
    except Exception as exc:  # broad-exception: fallback_recorded - never expose parser/path
        log_safe_exception(
            logger,
            "Report export font validation failed",
            exc,
            error_code="export_font_invalid",
            level=logging.WARNING,
            context={"font_path": path},
        )
        return FontInspection(False, "font_invalid")
    if not codepoints:
        return FontInspection(False, "font_empty_cmap")
    return FontInspection(True, "font_parsed", codepoints)


def inspect_font_file(path_value: str) -> FontInspection:
    """Parse a single TTF/OTF file and return sanitized readiness."""
    try:
        path = Path(path_value).expanduser()
        if not path.is_file() or path.suffix.lower() not in {".ttf", ".otf"}:
            return FontInspection(False, "font_invalid")
        return _inspect_font_signature(_font_signature(path))
    except OSError as exc:
        log_safe_exception(
            logger,
            "Report export font stat failed",
            exc,
            error_code="export_font_invalid",
            level=logging.WARNING,
        )
        return FontInspection(False, "font_invalid")


def resolve_pdf_font_path(
    *,
    configured: Optional[str] = None,
    candidates: Optional[Sequence[str]] = None,
) -> Optional[str]:
    """Resolve a parsed font; an explicit invalid configured path fails closed."""
    cfg = configured if configured is not None else _configured_font_path()
    if cfg:
        inspection = inspect_font_file(cfg)
        return str(Path(cfg).expanduser().resolve()) if inspection.valid else None

    for item in candidates if candidates is not None else _DEFAULT_FONT_CANDIDATES:
        if not item:
            continue
        inspection = inspect_font_file(item)
        if inspection.valid:
            return str(Path(item).expanduser().resolve())
    return None


def _required_codepoints(text: str) -> frozenset[int]:
    ignored_categories = {"Cc", "Cf", "Zl", "Zp"}
    return frozenset(
        ord(ch)
        for ch in text
        if not ch.isspace()
        and unicodedata.category(ch) not in ignored_categories
        and ord(ch) not in {0xFE0E, 0xFE0F}
    )


def missing_font_codepoints(font_path: str, text: str) -> frozenset[int]:
    """Return report codepoints absent from an already parsed font."""
    inspection = inspect_font_file(font_path)
    if not inspection.valid:
        return _required_codepoints(text)
    return _required_codepoints(text) - inspection.codepoints


def _resolve_font_for_text(
    text: str,
    *,
    configured: Optional[str],
) -> Tuple[Optional[str], str, int]:
    """Resolve a font covering ``text`` while preserving explicit fail-closed config."""
    if configured:
        resolved = resolve_pdf_font_path(configured=configured)
        if resolved is None:
            return None, "configured_font_invalid", 0
        missing = missing_font_codepoints(resolved, text)
        if missing:
            return None, "font_coverage_missing", len(missing)
        return resolved, "font_parsed", 0

    parsed_candidate_seen = False
    smallest_missing: Optional[int] = None
    for candidate in _DEFAULT_FONT_CANDIDATES:
        if not inspect_font_file(candidate).valid:
            continue
        parsed_candidate_seen = True
        missing = missing_font_codepoints(candidate, text)
        if not missing:
            return str(Path(candidate).expanduser().resolve()), "font_parsed", 0
        smallest_missing = (
            len(missing)
            if smallest_missing is None
            else min(smallest_missing, len(missing))
        )
    if parsed_candidate_seen:
        return None, "font_coverage_missing", int(smallest_missing or 0)
    return None, "font_not_found", 0


@lru_cache(maxsize=24)
def _font_smoke(signature: Tuple[str, int, int], sample: str) -> bool:
    """Run a deterministic fpdf2 add-font/render smoke for capability truth."""
    try:
        from fpdf import FPDF

        pdf = FPDF()
        pdf.add_font("ReportFont", "", signature[0])
        pdf.add_page()
        pdf.set_font("ReportFont", size=10)
        pdf.multi_cell(0, 6, sample)
        raw = pdf.output()
        return bytes(raw).startswith(b"%PDF")
    except Exception as exc:  # broad-exception: fallback_recorded - sanitized status
        log_safe_exception(
            logger,
            "Report export font/backend smoke failed",
            exc,
            error_code="export_font_smoke_failed",
            level=logging.WARNING,
            context={"font_path": signature[0]},
        )
        return False


def _normalize_capability_language(language: str) -> str:
    value = (language or "zh").strip()
    return value if value in _CAPABILITY_GLYPHS else "zh"


def get_export_capabilities(language: str = "zh") -> Dict[str, Any]:
    """Return language-aware, sanitized export capability details."""
    normalized_language = _normalize_capability_language(language)
    backend = inspect_pdf_backend()
    html_backend = inspect_html_backend()
    configured = _configured_font_path()
    font_path: Optional[str] = None
    font_status = "not_checked"
    missing_count = 0

    if backend.available:
        sample = _CAPABILITY_GLYPHS[normalized_language]
        font_path, font_status, missing_count = _resolve_font_for_text(
            sample,
            configured=configured,
        )
        if font_path is not None:
            try:
                signature = _font_signature(Path(font_path))
                font_status = (
                    "ready" if _font_smoke(signature, sample) else "font_smoke_failed"
                )
            except OSError:
                font_status = "font_invalid"

    pdf_available = backend.available and font_status == "ready"
    return {
        "formats": {
            "md": {
                "available": True,
                "status": "ready",
                "media_type": "text/markdown; charset=utf-8",
                "dependency": None,
                "dependency_installed": True,
                "font_validated": None,
                "missing_glyph_count": 0,
            },
            "html": {
                "available": html_backend.available,
                "status": html_backend.status,
                "media_type": "text/html; charset=utf-8",
                "dependency": HTML_OPTIONAL_PACKAGE,
                "dependency_installed": html_backend.dependency_installed,
                "dependency_version": html_backend.version,
                "font_validated": None,
                "missing_glyph_count": 0,
            },
            "pdf": {
                "available": pdf_available,
                "status": backend.status if not backend.available else font_status,
                "media_type": "application/pdf",
                "dependency": PDF_OPTIONAL_PACKAGE,
                "dependency_installed": backend.dependency_installed,
                "dependency_version": backend.version,
                "font_validated": font_status == "ready",
                "missing_glyph_count": missing_count,
            },
        },
        "requested_language": normalized_language,
        "supported_query_formats": list(SUPPORTED_FORMATS),
        # HTML is the office-friendly format delivered for Issue #163.
        # DOCX/XLSX remain out of scope to avoid python-docx/openpyxl surface.
        "office_formats_status": "html_only",
        "chart_handling": "markdown_images_omitted_without_destinations",
        "pdf_limits": {
            "max_input_bytes": MAX_PDF_INPUT_BYTES,
            "max_pages": MAX_PDF_PAGES,
            "max_table_rows": MAX_TABLE_ROWS,
            "max_table_columns": MAX_TABLE_COLUMNS,
            "max_output_bytes": PDF_MAX_OUTPUT_BYTES,
            "max_render_seconds": PDF_RENDER_DEADLINE_SECONDS,
            "max_concurrency": PDF_MAX_CONCURRENCY,
        },
    }


def _detect_primarily_chinese(text: str) -> bool:
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    return cjk >= 8 or (cjk > 0 and cjk * 30 >= max(len(text), 1))


class _HTMLTextExtractor(HTMLParser):
    """Keep HTML text nodes while dropping tags and every attribute URL."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _html_text(value: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(value)
    parser.close()
    return html.unescape("".join(parser.parts)).strip()


def _inline_text(children: Optional[Sequence[Any]], fallback: str, note: str) -> str:
    if not children:
        return fallback
    parts: List[str] = []
    for child in children:
        child_type = getattr(child, "type", "")
        if child_type in {"text", "code_inline"}:
            parts.append(str(getattr(child, "content", "")))
        elif child_type in {"softbreak", "hardbreak"}:
            parts.append("\n")
        elif child_type == "image":
            alt = str(getattr(child, "content", "") or "").strip()
            parts.append(f"[{alt}] {note}" if alt else note)
        elif child_type == "html_inline":
            parts.append(_html_text(str(getattr(child, "content", ""))))
        # link_open/link_close and emphasis markers intentionally contribute no
        # destination/markup; their visible child text remains in order.
    return "".join(parts).strip()


def _parse_table_tokens(tokens: Sequence[Any], start: int, note: str) -> Tuple[Dict[str, Any], int]:
    rows: List[List[str]] = []
    current_row: Optional[List[str]] = None
    in_cell = False
    i = start + 1
    while i < len(tokens):
        token = tokens[i]
        kind = token.type
        if kind == "table_close":
            break
        if kind == "tr_open":
            current_row = []
        elif kind in {"th_open", "td_open"}:
            in_cell = True
        elif kind == "inline" and in_cell and current_row is not None:
            current_row.append(_inline_text(token.children, token.content, note))
        elif kind in {"th_close", "td_close"}:
            in_cell = False
        elif kind == "tr_close" and current_row is not None:
            rows.append(current_row)
            current_row = None
        i += 1
    return {
        "header": rows[0] if rows else [],
        "rows": rows[1:] if len(rows) > 1 else [],
    }, i


def _parse_markdown_blocks(markdown: str) -> List[Tuple[str, Any]]:
    """Parse report Markdown through an AST without retaining URL targets."""
    from markdown_it import MarkdownIt

    note = _IMAGE_OMISSION_NOTE_ZH if _detect_primarily_chinese(markdown) else _IMAGE_OMISSION_NOTE_EN
    parser = MarkdownIt("commonmark", {"html": True}).enable("table")
    tokens = parser.parse(markdown)
    blocks: List[Tuple[str, Any]] = []
    list_stack: List[Dict[str, Any]] = []
    item_depth = 0
    quote_depth = 0
    heading_level: Optional[int] = None
    i = 0

    while i < len(tokens):
        token = tokens[i]
        kind = token.type
        if kind == "table_open":
            table, i = _parse_table_tokens(tokens, i, note)
            blocks.append(("table", table))
        elif kind == "heading_open":
            heading_level = int(str(token.tag).lstrip("h") or "1")
        elif kind == "heading_close":
            heading_level = None
        elif kind == "blockquote_open":
            quote_depth += 1
        elif kind == "blockquote_close":
            quote_depth = max(quote_depth - 1, 0)
        elif kind == "bullet_list_open":
            list_stack.append({"ordered": False, "next": 1})
        elif kind == "ordered_list_open":
            start = token.attrGet("start")
            list_stack.append({"ordered": True, "next": int(start or 1)})
        elif kind in {"bullet_list_close", "ordered_list_close"}:
            if list_stack:
                list_stack.pop()
        elif kind == "list_item_open":
            item_depth += 1
        elif kind == "list_item_close":
            item_depth = max(item_depth - 1, 0)
        elif kind == "inline":
            text = _inline_text(token.children, token.content, note)
            if heading_level is not None:
                blocks.append(("heading", {"level": heading_level, "text": text}))
            elif item_depth and list_stack:
                owner = list_stack[-1]
                marker = f"{owner['next']}." if owner["ordered"] else "•"
                if owner["ordered"]:
                    owner["next"] += 1
                blocks.append(
                    (
                        "list_item",
                        {"depth": len(list_stack), "marker": marker, "text": text},
                    )
                )
            elif quote_depth:
                blocks.append(("quote", text))
            elif text:
                blocks.append(("paragraph", text))
        elif kind in {"fence", "code_block"}:
            blocks.append(
                (
                    "code",
                    {"lang": str(getattr(token, "info", "") or "").strip(), "body": token.content.rstrip("\n")},
                )
            )
        elif kind == "hr":
            blocks.append(("hr", None))
        elif kind == "html_block":
            text = _html_text(token.content)
            if text:
                blocks.append(("paragraph", text))
        i += 1
    return blocks


def _table_shape_guard(blocks: Sequence[Tuple[str, Any]]) -> None:
    total_cells = 0
    for kind, payload in blocks:
        if kind != "table":
            continue
        header = list(payload.get("header") or [])
        rows = list(payload.get("rows") or [])
        columns = max(len(header), max((len(row) for row in rows), default=0), 1)
        if len(rows) > MAX_TABLE_ROWS:
            raise ReportExportLimitError(
                f"PDF table exceeds the {MAX_TABLE_ROWS}-row limit.",
                error_code="export_table_rows_exceeded",
            )
        if columns > MAX_TABLE_COLUMNS:
            raise ReportExportLimitError(
                f"PDF table exceeds the {MAX_TABLE_COLUMNS}-column limit.",
                error_code="export_table_columns_exceeded",
            )
        total_cells += (len(rows) + (1 if header else 0)) * columns
        if total_cells > MAX_TOTAL_TABLE_CELLS:
            raise ReportExportLimitError(
                "PDF tables exceed the total cell budget.",
                error_code="export_table_cells_exceeded",
            )


def _rendered_text(blocks: Sequence[Tuple[str, Any]]) -> str:
    parts: List[str] = []
    for kind, payload in blocks:
        if kind == "heading":
            parts.append(str(payload.get("text") or ""))
        elif kind in {"paragraph", "quote"}:
            parts.append(str(payload))
        elif kind == "list_item":
            parts.extend([str(payload.get("marker") or ""), str(payload.get("text") or "")])
        elif kind == "code":
            parts.append(str(payload.get("body") or ""))
        elif kind == "table":
            parts.extend(str(value) for value in payload.get("header") or [])
            for row in payload.get("rows") or []:
                parts.extend(str(value) for value in row)
    return "\n".join(parts)


def _deadline_guard(deadline: float) -> None:
    if time.monotonic() > deadline:
        raise ReportExportLimitError(
            "PDF export exceeded the render deadline.",
            error_code="export_deadline_exceeded",
            status_code=503,
        )


def _wrap_cell(pdf: Any, text: str, max_width: float) -> List[str]:
    """Character-safe measured wrapping with zero content truncation."""
    available = max(max_width, 1.0)
    output: List[str] = []
    for source_line in str(text).split("\n") or [""]:
        if not source_line:
            output.append("")
            continue
        current: List[str] = []
        width = 0.0
        for char in source_line:
            char_width = float(pdf.get_string_width(char))
            if current and width + char_width > available:
                output.append("".join(current))
                current = [char]
                width = char_width
            else:
                current.append(char)
                width += char_width
        output.append("".join(current))
    return output or [""]


def _render_pdf_bytes(
    blocks: Sequence[Tuple[str, Any]],
    *,
    font_path: str,
    title: Optional[str],
    deadline: float,
) -> bytes:
    from fpdf import FPDF

    class _ReportPDF(FPDF):
        def add_page(self, *args: Any, **kwargs: Any) -> None:
            if self.page_no() >= MAX_PDF_PAGES:
                raise ReportExportLimitError(
                    f"PDF export exceeds the {MAX_PDF_PAGES}-page limit.",
                    error_code="export_page_limit_exceeded",
                )
            super().add_page(*args, **kwargs)

        def footer(self) -> None:
            self.set_y(-12)
            self.set_font("ReportFont", size=8)
            self.cell(0, 8, str(self.page_no()), align="C")

    pdf = _ReportPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_margins(16, 16, 16)
    try:
        pdf.add_font("ReportFont", "", font_path)
    except Exception as exc:  # broad-exception: fallback_recorded - sanitized public error
        log_safe_exception(
            logger,
            "PDF font load failed for report export",
            exc,
            error_code="export_font_load_failed",
            level=logging.WARNING,
            context={"font_path": font_path},
        )
        raise ReportExportFontError(
            "The configured PDF font could not be loaded.",
            error_code="export_font_invalid",
        ) from exc

    if title:
        pdf.set_title(str(title)[:180])
    pdf.add_page()
    pdf.set_font("ReportFont", size=11)

    def write_flow(text: str, *, height: float = 6, indent: float = 0) -> None:
        _deadline_guard(deadline)
        pdf.set_x(pdf.l_margin + indent)
        width = max(pdf.epw - indent, 10)
        pdf.multi_cell(width, height, text or " ")
        pdf.set_x(pdf.l_margin)

    def draw_segment(lines_by_cell: Sequence[Sequence[str]], widths: Sequence[float], line_height: float) -> None:
        row_lines = max((len(lines) for lines in lines_by_cell), default=1)
        row_height = row_lines * line_height + 2
        x = pdf.l_margin
        y = pdf.get_y()
        for lines, width in zip(lines_by_cell, widths):
            pdf.rect(x, y, width, row_height)
            for line_index, line in enumerate(lines):
                pdf.set_xy(x + 1, y + 1 + line_index * line_height)
                pdf.cell(max(width - 2, 1), line_height, line)
            x += width
        pdf.set_xy(pdf.l_margin, y + row_height)

    def render_stacked_table(header: List[str], rows: List[List[str]]) -> None:
        for row_index, row in enumerate(rows, start=1):
            _deadline_guard(deadline)
            if pdf.get_y() > pdf.page_break_trigger - 18:
                pdf.add_page()
            for column_index, value in enumerate(row):
                label = header[column_index] if column_index < len(header) else f"Column {column_index + 1}"
                write_flow(f"{label}: {value}", height=5)
            if row_index != len(rows):
                y = pdf.get_y() + 1
                pdf.line(pdf.l_margin, y, pdf.l_margin + pdf.epw, y)
                pdf.ln(3)

    def render_grid_table(header: List[str], rows: List[List[str]]) -> None:
        column_count = max(len(header), max((len(row) for row in rows), default=0), 1)
        widths = [pdf.epw / column_count] * column_count
        line_height = 4.5
        pdf.set_font("ReportFont", size=8.5)
        padded_header = (header + [""] * column_count)[:column_count]
        header_lines = [_wrap_cell(pdf, value, widths[index] - 2) for index, value in enumerate(padded_header)]
        header_height = max(len(lines) for lines in header_lines) * line_height + 2
        if header_height >= pdf.page_break_trigger - pdf.t_margin:
            raise ReportExportLimitError(
                "PDF table header is too tall for one page.",
                error_code="export_table_header_too_large",
            )

        def draw_header() -> None:
            if header and pdf.get_y() + header_height > pdf.page_break_trigger:
                pdf.add_page()
            if header:
                draw_segment(header_lines, widths, line_height)

        draw_header()
        for row in rows:
            _deadline_guard(deadline)
            padded = (list(row) + [""] * column_count)[:column_count]
            remaining = [
                _wrap_cell(pdf, value, widths[index] - 2)
                for index, value in enumerate(padded)
            ]
            row_line_count = max(len(lines) for lines in remaining)
            page_body_lines = int(
                max(
                    pdf.page_break_trigger
                    - pdf.t_margin
                    - (header_height if header else 0)
                    - 2,
                    0,
                )
                // line_height
            )
            row_height = row_line_count * line_height + 2
            if (
                row_line_count <= page_body_lines
                and pdf.get_y() + row_height > pdf.page_break_trigger
            ):
                pdf.add_page()
                draw_header()
            while any(lines for lines in remaining):
                available_lines = int(
                    max(pdf.page_break_trigger - pdf.get_y() - 2, 0) // line_height
                )
                if available_lines < 1:
                    pdf.add_page()
                    draw_header()
                    available_lines = int(
                        max(pdf.page_break_trigger - pdf.get_y() - 2, 0) // line_height
                    )
                chunk_size = max(1, min(max(len(lines) for lines in remaining), available_lines))
                segment = [lines[:chunk_size] for lines in remaining]
                remaining = [lines[chunk_size:] for lines in remaining]
                draw_segment(segment, widths, line_height)
                if any(lines for lines in remaining):
                    pdf.add_page()
                    draw_header()
        pdf.set_font("ReportFont", size=11)
        pdf.ln(2)

    for kind, payload in blocks:
        _deadline_guard(deadline)
        if kind == "heading":
            level = int(payload.get("level") or 1)
            size = {1: 18, 2: 15, 3: 13}.get(level, 12)
            pdf.ln(4 if level <= 2 else 2)
            pdf.set_font("ReportFont", size=size)
            write_flow(str(payload.get("text") or ""), height=max(size * 0.55, 6))
            pdf.set_font("ReportFont", size=11)
            pdf.ln(1)
        elif kind == "paragraph":
            write_flow(str(payload), height=6)
            pdf.ln(1)
        elif kind == "quote":
            write_flow(str(payload), height=6, indent=6)
            pdf.ln(1)
        elif kind == "list_item":
            indent = min(max(int(payload.get("depth") or 1) - 1, 0) * 5, 30)
            write_flow(
                f"{payload.get('marker') or '•'} {payload.get('text') or ''}",
                height=6,
                indent=indent,
            )
        elif kind == "code":
            pdf.set_font("ReportFont", size=9)
            for line in str(payload.get("body") or "").split("\n") or [""]:
                write_flow(line or " ", height=5, indent=3)
            pdf.set_font("ReportFont", size=11)
            pdf.ln(1)
        elif kind == "table":
            header = [str(value) for value in payload.get("header") or []]
            rows = [[str(value) for value in row] for row in payload.get("rows") or []]
            column_count = max(len(header), max((len(row) for row in rows), default=0), 1)
            if column_count > 6:
                render_stacked_table(header, rows)
            else:
                render_grid_table(header, rows)
        elif kind == "hr":
            y = pdf.get_y() + 2
            pdf.line(pdf.l_margin, y, pdf.l_margin + pdf.epw, y)
            pdf.ln(4)

    _deadline_guard(deadline)
    raw = pdf.output()
    return bytes(raw) if isinstance(raw, (bytes, bytearray)) else str(raw).encode("latin-1")


def _render_pdf_worker(
    send_connection: Any,
    blocks: Sequence[Tuple[str, Any]],
    font_path: str,
    title: Optional[str],
    deadline: float,
) -> None:
    """Render in an isolated process so the parent can enforce a hard deadline."""
    try:
        payload: Tuple[Any, ...] = (
            "ok",
            _render_pdf_bytes(
                blocks,
                font_path=font_path,
                title=title,
                deadline=deadline,
            ),
        )
    except ReportExportError as exc:
        payload = (
            "export_error",
            type(exc).__name__,
            exc.error_code,
            exc.message,
            getattr(exc, "status_code", None),
        )
    except Exception as exc:  # broad-exception: fallback_recorded - child details stay private
        log_safe_exception(
            logger,
            "Isolated PDF render worker failed",
            exc,
            error_code="export_worker_failed",
            level=logging.WARNING,
        )
        payload = ("worker_error",)
    try:
        send_connection.send(payload)
    except (BrokenPipeError, EOFError, OSError):
        pass
    finally:
        send_connection.close()


def _stop_render_worker(process: Any) -> None:
    """Bound shutdown of a timed-out or malformed render worker."""
    if not process.is_alive():
        process.join(timeout=0)
        return
    process.terminate()
    process.join(timeout=PDF_WORKER_SHUTDOWN_SECONDS)
    if process.is_alive() and hasattr(process, "kill"):
        process.kill()
        process.join(timeout=PDF_WORKER_SHUTDOWN_SECONDS)


def _raise_worker_export_error(payload: Tuple[Any, ...]) -> None:
    _tag, class_name, error_code, message, status_code = payload
    if class_name == "ReportExportFontError":
        raise ReportExportFontError(message, error_code=error_code)
    if class_name == "ReportExportDependencyError":
        raise ReportExportDependencyError(message)
    if class_name == "ReportExportLimitError":
        raise ReportExportLimitError(
            message,
            error_code=error_code,
            status_code=int(status_code or 413),
        )
    raise ReportExportError(message, error_code=error_code)


def _render_pdf_bytes_isolated(
    blocks: Sequence[Tuple[str, Any]],
    *,
    font_path: str,
    title: Optional[str],
    deadline: float,
) -> bytes:
    """Run fpdf2 in a spawn worker and terminate it when the deadline expires."""
    context = multiprocessing.get_context("spawn")
    receive_connection, send_connection = context.Pipe(duplex=False)
    process = context.Process(
        target=_render_pdf_worker,
        args=(send_connection, blocks, font_path, title, deadline),
        name="stockpulse-report-export",
        daemon=True,
    )
    try:
        process.start()
    except Exception as exc:  # broad-exception: fallback_recorded - platform start failure
        receive_connection.close()
        send_connection.close()
        log_safe_exception(
            logger,
            "PDF render worker could not start",
            exc,
            error_code="export_worker_unavailable",
            level=logging.WARNING,
        )
        raise ReportExportWorkerError() from exc
    send_connection.close()

    try:
        remaining = max(deadline - time.monotonic(), 0.0)
        if remaining <= 0 or not receive_connection.poll(remaining):
            _stop_render_worker(process)
            raise ReportExportLimitError(
                "PDF export exceeded the render deadline.",
                error_code="export_deadline_exceeded",
                status_code=503,
            )
        try:
            payload = receive_connection.recv()
        except (EOFError, OSError) as exc:
            _stop_render_worker(process)
            raise ReportExportWorkerError() from exc
    finally:
        receive_connection.close()

    process.join(timeout=PDF_WORKER_SHUTDOWN_SECONDS)
    if process.is_alive():
        _stop_render_worker(process)
    if not isinstance(payload, tuple) or not payload:
        raise ReportExportWorkerError()
    if payload[0] == "export_error":
        _raise_worker_export_error(payload)
    if payload[0] != "ok" or len(payload) != 2 or not isinstance(payload[1], bytes):
        raise ReportExportWorkerError()
    return payload[1]


def _safe_filename_stem(stem: str) -> str:
    cleaned = re.sub(r"[^\w.\-]+", "_", str(stem).strip(), flags=re.UNICODE)
    cleaned = cleaned.strip("._") or "report"
    return cleaned[:80]


def export_markdown_bytes(markdown: str, *, filename_stem: str = "report") -> ExportArtifact:
    """Export exact UTF-8 Markdown without optional dependencies."""
    if markdown is None or not str(markdown).strip():
        raise ReportExportFormatError("Report content is empty.", error_code="export_empty")
    content = str(markdown)
    stem = _safe_filename_stem(filename_stem)
    return ExportArtifact(
        content=content.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        filename=f"{stem}.md",
        format="md",
    )


def _escape_html(value: str) -> str:
    return html.escape(str(value), quote=True)


def _render_html_document(
    blocks: Sequence[Tuple[str, Any]],
    *,
    title: Optional[str],
) -> str:
    """Render AST blocks to a self-contained HTML document (no external URLs)."""
    body_parts: List[str] = []
    for kind, payload in blocks:
        if kind == "heading":
            level = min(max(int(payload.get("level") or 1), 1), 6)
            text_value = _escape_html(str(payload.get("text") or ""))
            body_parts.append(f"<h{level}>{text_value}</h{level}>")
        elif kind == "paragraph":
            body_parts.append(f"<p>{_escape_html(str(payload))}</p>")
        elif kind == "quote":
            body_parts.append(
                f"<blockquote><p>{_escape_html(str(payload))}</p></blockquote>"
            )
        elif kind == "list_item":
            depth = min(max(int(payload.get("depth") or 1), 1), 8)
            indent_em = (depth - 1) * 1.25
            marker = _escape_html(str(payload.get("marker") or "•"))
            item_text = _escape_html(str(payload.get("text") or ""))
            body_parts.append(
                f'<p class="list-item" style="margin-left:{indent_em:.2f}em">'
                f"{marker} {item_text}</p>"
            )
        elif kind == "code":
            lang = _escape_html(str(payload.get("lang") or ""))
            body = _escape_html(str(payload.get("body") or ""))
            lang_attr = f' data-lang="{lang}"' if lang else ""
            body_parts.append(f"<pre{lang_attr}><code>{body}</code></pre>")
        elif kind == "table":
            header = [str(value) for value in payload.get("header") or []]
            rows = [[str(value) for value in row] for row in payload.get("rows") or []]
            thead = ""
            if header:
                cells = "".join(f"<th>{_escape_html(cell)}</th>" for cell in header)
                thead = f"<thead><tr>{cells}</tr></thead>"
            body_rows: List[str] = []
            for row in rows:
                cells = "".join(f"<td>{_escape_html(cell)}</td>" for cell in row)
                body_rows.append(f"<tr>{cells}</tr>")
            tbody = f"<tbody>{''.join(body_rows)}</tbody>" if body_rows else ""
            body_parts.append(f"<table>{thead}{tbody}</table>")
        elif kind == "hr":
            body_parts.append("<hr />")

    doc_title = _escape_html(title or "StockPulse report")
    body = "\n".join(body_parts)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="zh">\n'
        "<head>\n"
        '<meta charset="utf-8" />\n'
        f"<title>{doc_title}</title>\n"
        "<style>\n"
        "body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,"
        "Noto Sans,PingFang SC,Microsoft YaHei,sans-serif;line-height:1.55;"
        "margin:2rem auto;max-width:48rem;padding:0 1rem;color:#111;}\n"
        "h1,h2,h3,h4,h5,h6{line-height:1.25;}\n"
        "table{border-collapse:collapse;width:100%;margin:1rem 0;}\n"
        "th,td{border:1px solid #ccc;padding:0.4rem 0.55rem;vertical-align:top;}\n"
        "th{background:#f5f5f5;text-align:left;}\n"
        "pre{background:#f6f8fa;padding:0.75rem;overflow:auto;}\n"
        "blockquote{border-left:3px solid #ccc;margin-left:0;padding-left:0.75rem;"
        "color:#444;}\n"
        ".list-item{margin:0.2rem 0;}\n"
        "</style>\n"
        "</head>\n"
        f"<body>\n{body}\n</body>\n"
        "</html>\n"
    )


def export_html_bytes(
    markdown: str,
    *,
    filename_stem: str = "report",
    title: Optional[str] = None,
) -> ExportArtifact:
    """Export structured, secret-safe HTML for office-friendly archive use."""
    if markdown is None or not str(markdown).strip():
        raise ReportExportFormatError("Report content is empty.", error_code="export_empty")
    content = str(markdown)
    input_bytes = len(content.encode("utf-8"))
    if input_bytes > MAX_HTML_INPUT_BYTES:
        raise ReportExportLimitError(
            f"HTML input exceeds the {MAX_HTML_INPUT_BYTES}-byte limit.",
            error_code="export_input_too_large",
        )

    backend = inspect_html_backend()
    if not backend.available:
        raise ReportExportDependencyError(
            "Structured HTML export requires markdown-it-py from the optional "
            "report-export dependency set.",
            install_hint=HTML_INSTALL_HINT,
        )

    blocks = _parse_markdown_blocks(content)
    _table_shape_guard(blocks)
    document = _render_html_document(blocks, title=title or filename_stem)
    encoded = document.encode("utf-8")
    if len(encoded) > HTML_MAX_OUTPUT_BYTES:
        raise ReportExportLimitError(
            "HTML output exceeds the in-memory artifact limit.",
            error_code="export_output_too_large",
        )
    stem = _safe_filename_stem(filename_stem)
    return ExportArtifact(
        content=encoded,
        media_type="text/html; charset=utf-8",
        filename=f"{stem}.html",
        format="html",
    )


def _cache_key(markdown: str, font_path: str, title: Optional[str]) -> str:
    signature = _font_signature(Path(font_path))
    digest = hashlib.sha256()
    digest.update(markdown.encode("utf-8"))
    digest.update(repr(signature).encode("utf-8"))
    digest.update(str(title or "").encode("utf-8"))
    return digest.hexdigest()


def _cache_get(key: str) -> Optional[ExportArtifact]:
    with _PDF_CACHE_LOCK:
        artifact = _PDF_CACHE.get(key)
        if artifact is not None:
            _PDF_CACHE.move_to_end(key)
        return artifact


def _cache_put(key: str, artifact: ExportArtifact) -> None:
    global _PDF_CACHE_BYTES
    if len(artifact.content) > PDF_CACHE_MAX_BYTES:
        return
    with _PDF_CACHE_LOCK:
        old = _PDF_CACHE.pop(key, None)
        if old is not None:
            _PDF_CACHE_BYTES -= len(old.content)
        _PDF_CACHE[key] = artifact
        _PDF_CACHE_BYTES += len(artifact.content)
        while len(_PDF_CACHE) > PDF_CACHE_ENTRIES or _PDF_CACHE_BYTES > PDF_CACHE_MAX_BYTES:
            _, removed = _PDF_CACHE.popitem(last=False)
            _PDF_CACHE_BYTES -= len(removed.content)


def export_pdf_bytes(
    markdown: str,
    *,
    filename_stem: str = "report",
    title: Optional[str] = None,
    font_path: Optional[str] = None,
) -> ExportArtifact:
    """Render a bounded PDF after backend, font, glyph, and AST validation."""
    if markdown is None or not str(markdown).strip():
        raise ReportExportFormatError("Report content is empty.", error_code="export_empty")
    content = str(markdown)
    input_bytes = len(content.encode("utf-8"))
    if input_bytes > MAX_PDF_INPUT_BYTES:
        raise ReportExportLimitError(
            f"PDF input exceeds the {MAX_PDF_INPUT_BYTES}-byte limit.",
            error_code="export_input_too_large",
        )
    deadline = time.monotonic() + PDF_RENDER_DEADLINE_SECONDS

    backend = inspect_pdf_backend()
    if not backend.available:
        raise ReportExportDependencyError(
            "The supported fpdf2 backend is unavailable or conflicts with legacy PyFPDF."
        )
    _deadline_guard(deadline)

    blocks = _parse_markdown_blocks(content)
    _table_shape_guard(blocks)
    _deadline_guard(deadline)
    configured = font_path or _configured_font_path()
    rendered_text = _rendered_text(blocks)
    resolved_font, font_status, _missing_count = _resolve_font_for_text(
        rendered_text,
        configured=configured,
    )
    if resolved_font is None:
        if font_status == "font_coverage_missing":
            raise ReportExportFontError(
                "The validated PDF font does not cover all glyphs in this report. Use the lossless Markdown export or configure a font with complete coverage.",
                error_code="export_font_coverage_missing",
            )
        code = "export_font_invalid" if configured else "export_font_missing"
        raise ReportExportFontError(
            "The configured PDF font is invalid or no validated PDF font is available.",
            error_code=code,
        )
    _deadline_guard(deadline)

    stem = _safe_filename_stem(filename_stem)
    try:
        key = _cache_key(content, resolved_font, title or stem)
    except OSError as exc:
        log_safe_exception(
            logger,
            "Report export font changed before rendering",
            exc,
            error_code="export_font_invalid",
            level=logging.WARNING,
        )
        raise ReportExportFontError(
            "The validated PDF font is no longer available.",
            error_code="export_font_invalid",
        ) from exc
    cached = _cache_get(key)
    if cached is not None:
        return ExportArtifact(cached.content, cached.media_type, f"{stem}.pdf", "pdf")
    if not _PDF_SEMAPHORE.acquire(blocking=False):
        raise ReportExportBusyError()
    try:
        pdf_bytes = _render_pdf_bytes_isolated(
            blocks,
            font_path=resolved_font,
            title=title or stem,
            deadline=deadline,
        )
        _deadline_guard(deadline)
    finally:
        _PDF_SEMAPHORE.release()

    if not pdf_bytes.startswith(b"%PDF"):
        raise ReportExportError(
            "PDF backend returned invalid output.",
            error_code="export_pdf_invalid",
        )
    if len(pdf_bytes) > PDF_MAX_OUTPUT_BYTES:
        raise ReportExportLimitError(
            "PDF output exceeds the in-memory artifact limit.",
            error_code="export_output_too_large",
        )
    artifact = ExportArtifact(pdf_bytes, "application/pdf", f"{stem}.pdf", "pdf")
    _cache_put(key, artifact)
    return artifact


def export_report(
    markdown: str,
    fmt: str,
    *,
    filename_stem: str = "stockpulse-report",
    title: Optional[str] = None,
    font_path: Optional[str] = None,
) -> ExportArtifact:
    """Export Markdown to the requested ``md``, ``html``, or ``pdf`` format."""
    normalized = (fmt or "").strip().lower()
    if normalized not in SUPPORTED_FORMATS:
        raise ReportExportFormatError(
            f"Unsupported export format '{fmt}'. Supported: {', '.join(SUPPORTED_FORMATS)}."
        )
    if normalized == "md":
        return export_markdown_bytes(markdown, filename_stem=filename_stem)
    if normalized == "html":
        return export_html_bytes(
            markdown,
            filename_stem=filename_stem,
            title=title,
        )
    return export_pdf_bytes(
        markdown,
        filename_stem=filename_stem,
        title=title,
        font_path=font_path,
    )


def capabilities_public_view(payload: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Return a detached public capability mapping with no filesystem paths."""
    data = dict(payload or get_export_capabilities())
    formats = data.get("formats")
    if isinstance(formats, Mapping):
        data["formats"] = {
            key: {inner_key: inner_value for inner_key, inner_value in dict(value).items() if inner_key != "font_path"}
            if isinstance(value, Mapping)
            else value
            for key, value in formats.items()
        }
    return data
