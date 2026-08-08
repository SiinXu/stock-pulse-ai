# -*- coding: utf-8 -*-
"""History report export endpoints (Markdown / optional PDF).

Mounted under ``/history`` so paths match the existing report history surface
without editing ``history.py`` (parallel-batch ownership boundary).
"""

from __future__ import annotations

import logging
from typing import Any, Mapping, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, Response

from api.deps import get_database_manager
from api.v1.errors import api_error
from api.v1.schemas.common import ErrorResponse
from src.services.history_service import (
    HistoryService,
    MarkdownReportGenerationError,
)
from src.services.report_export_service import (
    ReportExportDependencyError,
    ReportExportError,
    ReportExportFontError,
    ReportExportFormatError,
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


@router.get(
    "/export/capabilities",
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
def get_report_export_capabilities() -> JSONResponse:
    payload = capabilities_public_view(get_export_capabilities())
    return JSONResponse(content=payload)


@router.get(
    "/{record_id}/export",
    response_class=Response,
    responses={
        200: {"description": "Exported report file (Markdown or PDF)"},
        400: {"description": "Invalid export format", "model": ErrorResponse},
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
        "intermediate representation used by GET /history/{id}/markdown; report "
        "structure and wording are not altered. Chart/image markdown is omitted "
        "in PDF with an explicit note. Secrets must not be present in the "
        "rendered Markdown (export does not inject credentials)."
    ),
)
def export_history_report(
    record_id: str,
    format: str = Query(
        "md",
        alias="format",
        description="Export format: md (default) or pdf",
    ),
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
            f"Failed to generate report content for export: {exc.message}",
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
            f"No analysis record found for id/query_id={record_id}",
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
            exc.message,
            params={
                "dependency": "fpdf2",
                "install_hint": exc.install_hint,
            },
        ) from exc
    except ReportExportFontError as exc:
        raise api_error(
            503,
            exc.error_code,
            exc.message,
            params={"env": "REPORT_EXPORT_PDF_FONT_PATH"},
        ) from exc
    except ReportExportError as exc:
        log_safe_exception(
            logger,
            "Report export failed",
            exc,
            error_code=exc.error_code,
            context={"record_id": record_id, "format": format},
        )
        raise api_error(500, exc.error_code, exc.message) from exc

    return Response(
        content=artifact.content,
        media_type=artifact.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{artifact.filename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-StockPulse-Export-Format": artifact.format,
        },
    )
