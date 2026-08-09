# -*- coding: utf-8 -*-
"""History report export endpoints (Markdown / optional PDF).

Mounted under ``/history`` so paths match the existing report history surface
without editing ``history.py`` (parallel-batch ownership boundary).
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Annotated, Any, Mapping, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from api.deps import get_database_manager
from api.v1.errors import api_error
from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.report_export import (
    ReportExportCapabilitiesResponse,
    ReportExportCapabilityLanguage,
    ReportExportFormat,
)
from src.services.history_service import (
    HistoryService,
    MarkdownReportGenerationError,
)
from src.services.report_export_service import (
    ReportExportBusyError,
    ReportExportDependencyError,
    ReportExportError,
    ReportExportFontError,
    ReportExportFormatError,
    ReportExportLimitError,
    capabilities_public_view,
    export_report,
    get_export_capabilities,
)
from src.storage import DatabaseManager
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

router = APIRouter()


def _filename_stem_for_record(record_id: str, detail: Optional[Mapping[str, Any]]) -> str:
    record_key = None
    if isinstance(detail, Mapping):
        record_key = detail.get("id") or detail.get("query_id")
    key = record_key if record_key not in (None, "") else record_id
    return f"stockpulse-report-{key}"


def _truncate_utf8(value: str, max_bytes: int) -> str:
    encoded = value.encode("utf-8")[:max_bytes]
    return encoded.decode("utf-8", errors="ignore")


def build_content_disposition(filename: str) -> str:
    """Build a bounded ASCII fallback plus RFC 5987 UTF-8 filename."""
    # Discard everything after the first line break instead of attempting to
    # preserve attacker-controlled pseudo-header text in either filename form.
    first_line = re.split(r"[\r\n]", str(filename), maxsplit=1)[0]
    bounded = _truncate_utf8(first_line, 180)
    normalized = unicodedata.normalize("NFKD", bounded)
    ascii_name = normalized.encode("ascii", errors="ignore").decode("ascii")
    ascii_name = re.sub(r"[^A-Za-z0-9._-]+", "_", ascii_name).strip("._")
    suffix = ".pdf" if bounded.lower().endswith(".pdf") else ".md"
    if not ascii_name or ascii_name in {"pdf", "md"}:
        ascii_name = f"stockpulse-report{suffix}"
    elif not ascii_name.lower().endswith(suffix):
        ascii_name = f"{ascii_name[:56]}{suffix}"
    else:
        stem = ascii_name[: -len(suffix)][:56].rstrip("._-") or "stockpulse-report"
        ascii_name = f"{stem}{suffix}"
    encoded = quote(bounded, safe="")
    return f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded}'


@router.get(
    "/export/capabilities",
    response_model=ReportExportCapabilitiesResponse,
    responses={
        200: {"description": "Available report export formats and dependency status"},
    },
    summary="Report export capabilities",
    description=(
        "Return which report export formats are available in this process. "
        "Markdown is always available. PDF requires the optional fpdf2 package "
        "and a resolvable CJK/Unicode font. Office formats (docx/xlsx) are not "
        "implemented in this release."
    ),
)
def get_report_export_capabilities(
    language: Annotated[
        ReportExportCapabilityLanguage,
        Query(description="Report language whose representative glyph set must be supported."),
    ] = "zh",
) -> ReportExportCapabilitiesResponse:
    payload = capabilities_public_view(get_export_capabilities(language))
    return ReportExportCapabilitiesResponse.model_validate(payload)


@router.get(
    "/{record_id}/export",
    response_class=Response,
    responses={
        200: {
            "description": "Exported report file",
            "content": {
                "text/markdown": {"schema": {"type": "string", "format": "binary"}},
                "application/pdf": {"schema": {"type": "string", "format": "binary"}},
            },
        },
        400: {"description": "Invalid export format", "model": ErrorResponse},
        413: {"description": "Export resource limit exceeded", "model": ErrorResponse},
        429: {"description": "PDF export capacity is busy", "model": ErrorResponse},
        404: {"description": "Report not found", "model": ErrorResponse},
        500: {"description": "Export or report generation failed", "model": ErrorResponse},
        503: {
            "description": "Optional export dependency or font missing",
            "model": ErrorResponse,
        },
    },
    summary="Export a history report",
    description=(
        "Export an analysis history record as Markdown (always) or PDF "
        "(optional fpdf2 + font). Content is converted from the same Markdown "
        "intermediate representation used by GET /history/{id}/markdown. Markdown "
        "is lossless. PDF preserves visible wording but drops link destinations "
        "and complete image destinations, replaces images with an omission note, "
        "and renders tables wider than six columns as stacked header/value rows. "
        "Explicit byte/page/table/time/concurrency limits apply."
    ),
)
def export_history_report(
    record_id: str,
    format: Annotated[
        ReportExportFormat,
        Query(alias="format", description="Export format: md (default) or pdf"),
    ] = "md",
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> Response:
    service = HistoryService(db_manager)
    detail = service.resolve_and_get_detail(record_id)

    try:
        markdown_content = service.get_markdown_report(record_id)
    except MarkdownReportGenerationError as exc:
        log_safe_exception(
            logger,
            "Report export markdown generation failed",
            exc,
            error_code="generation_failed",
            context={"record_id": record_id},
        )
        raise api_error(
            500,
            "generation_failed",
            "Failed to generate report content for export.",
        ) from exc
    except Exception as exc:
        log_safe_exception(
            logger,
            "Report export markdown lookup failed",
            exc,
            error_code="internal_error",
            context={"record_id": record_id},
        )
        raise api_error(
            500,
            "internal_error",
            "Failed to load report content for export",
        ) from exc

    if markdown_content is None:
        raise api_error(
            404,
            "not_found",
            "No analysis record found for the requested history id.",
        )

    stem = _filename_stem_for_record(record_id, detail)
    try:
        artifact = export_report(
            markdown_content,
            format,
            filename_stem=stem,
            title=stem,
        )
    except ReportExportFormatError as exc:
        raise api_error(400, exc.error_code, exc.message) from exc
    except ReportExportDependencyError as exc:
        raise api_error(
            503,
            exc.error_code,
            "The optional PDF export backend is unavailable.",
            params={
                "dependency": "fpdf2",
                "install_hint": exc.install_hint,
            },
        ) from exc
    except ReportExportFontError as exc:
        raise api_error(
            503,
            exc.error_code,
            "A validated font covering every report glyph is required for PDF export.",
            params={"env": "REPORT_EXPORT_PDF_FONT_PATH"},
        ) from exc
    except ReportExportLimitError as exc:
        raise api_error(exc.status_code, exc.error_code, exc.message) from exc
    except ReportExportBusyError as exc:
        raise api_error(exc.status_code, exc.error_code, exc.message) from exc
    except ReportExportError as exc:
        log_safe_exception(
            logger,
            "Report export failed",
            exc,
            error_code=exc.error_code,
            context={"record_id": record_id, "format": format},
        )
        raise api_error(500, exc.error_code, "Report export failed.") from exc

    return Response(
        content=artifact.content,
        media_type=artifact.media_type,
        headers={
            "Content-Disposition": build_content_disposition(artifact.filename),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-StockPulse-Export-Format": artifact.format,
        },
    )
