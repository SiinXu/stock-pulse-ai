# -*- coding: utf-8 -*-
"""History report export endpoints (Markdown / HTML / optional PDF).

Mounted under ``/history`` so paths match the existing report history surface
without editing ``history.py`` (parallel-batch ownership boundary).
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import unicodedata
from typing import Annotated, Any, Mapping, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from src.api.deps import get_database_manager, require_security_audit_service
from src.api.v1.errors import api_error
from src.api.v1.schemas.common import ErrorResponse
from src.api.v1.schemas.report_export import (
    ReportExportCapabilitiesResponse,
    ReportExportCapabilityLanguage,
)
from src.auth import is_auth_enabled
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
    ReportExportWorkerError,
    capabilities_public_view,
    export_report,
    get_export_capabilities,
)
from src.services.security_audit_service import (
    SecurityAuditRecorder,
    SecurityAuditService,
    SecurityAuditUnavailable,
    require_security_audit_recorder,
)
from src.storage import DatabaseManager
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

router = APIRouter()

REPORT_EXPORT_EVENT_TYPE = "report.export"
REPORT_EXPORT_TARGET_TYPE = "analysis_history"
_IDENTITY_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,119}")


class ReportExportAuditCompletionUnavailable(RuntimeError):
    """Raised when export already produced bytes but audit completion could not be stored."""

    def __init__(self, *, record_id: str, format: str) -> None:
        super().__init__("security_audit_unavailable")
        self.record_id = record_id
        self.format = format


def _audit_target_id(record_id: str) -> str:
    """Return a bounded audit identity without persisting arbitrary route text."""
    if _IDENTITY_PATTERN.fullmatch(record_id):
        return record_id
    return f"sha256:{hashlib.sha256(record_id.encode('utf-8')).hexdigest()[:24]}"


def _report_export_audit_actor() -> str:
    """Return the attributable operator class for the single-admin model."""
    if os.getenv("DSA_DESKTOP_MODE") == "true":
        return "desktop_operator"
    if is_auth_enabled():
        return "authenticated_admin"
    return "local_operator"


def _resolved_record_id(detail: Optional[Mapping[str, Any]]) -> Optional[str]:
    if not isinstance(detail, Mapping):
        return None
    raw_id = detail.get("id")
    if raw_id not in (None, ""):
        return str(raw_id)
    query_id = detail.get("query_id")
    if query_id not in (None, ""):
        return str(query_id)
    return None


def _export_lookup_mode(
    record_id: str,
    detail: Optional[Mapping[str, Any]],
) -> Optional[str]:
    resolved = _resolved_record_id(detail)
    if resolved is None:
        return None
    try:
        if int(record_id) == int(resolved):
            return "primary_key"
    except (TypeError, ValueError):
        pass
    return "query_id"


def _report_export_audit_unavailable(
    *,
    operation_completed: bool = False,
    record_id: str | None = None,
    format: str | None = None,
) -> HTTPException:
    detail = {
        "error": "security_audit_unavailable",
        "message": (
            "Report export was generated, but audit completion could not be persisted"
            if operation_completed
            else "Security audit storage is unavailable"
        ),
        "operation_completed": operation_completed,
    }
    if record_id is not None:
        detail["record_id"] = record_id
    if format is not None:
        detail["format"] = format
    return HTTPException(status_code=503, detail=detail)


def _report_export_audit_metadata(
    *,
    format: str,
    lookup_key: str,
    resolved_record_id: str | None = None,
    lookup_mode: str | None = None,
    byte_length: int | None = None,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "format": format,
        "lookup_key": _audit_target_id(lookup_key),
    }
    if resolved_record_id is not None:
        metadata["resolved_record_id"] = _audit_target_id(resolved_record_id)
    if lookup_mode is not None:
        metadata["lookup_mode"] = lookup_mode
    if byte_length is not None:
        metadata["byte_length"] = int(byte_length)
    return metadata


def _record_report_export_audit(
    security_audit: SecurityAuditRecorder,
    *,
    phase: str,
    correlation_id: str,
    record_id: str,
    format: str,
    outcome: str = "success",
    reason_code: str = "export_completed",
    resolved_record_id: str | None = None,
    lookup_mode: str | None = None,
    byte_length: int | None = None,
) -> None:
    service = require_security_audit_recorder(security_audit)
    audited_id = resolved_record_id or record_id
    common = {
        "event_type": REPORT_EXPORT_EVENT_TYPE,
        "actor_type": "administrator",
        "actor_id": _report_export_audit_actor(),
        "execution_id": correlation_id,
        "action": REPORT_EXPORT_EVENT_TYPE,
        "target_type": REPORT_EXPORT_TARGET_TYPE,
        "target_id": _audit_target_id(audited_id),
        "correlation_id": correlation_id,
        "metadata": _report_export_audit_metadata(
            format=format,
            lookup_key=record_id,
            resolved_record_id=resolved_record_id,
            lookup_mode=lookup_mode,
            byte_length=byte_length,
        ),
    }
    if phase == "attempt":
        service.record_attempt(**common)
        return
    service.record_completion(
        **common,
        outcome=outcome,
        reason_code=reason_code,
    )


def _record_report_export_completion_best_effort(
    security_audit: SecurityAuditRecorder,
    *,
    correlation_id: str,
    record_id: str,
    format: str,
    outcome: str,
    reason_code: str,
    resolved_record_id: str | None = None,
    lookup_mode: str | None = None,
) -> None:
    try:
        _record_report_export_audit(
            security_audit,
            phase="completion",
            correlation_id=correlation_id,
            record_id=record_id,
            format=format,
            outcome=outcome,
            reason_code=reason_code,
            resolved_record_id=resolved_record_id,
            lookup_mode=lookup_mode,
        )
    except SecurityAuditUnavailable:
        return


def _filename_stem_for_record(record_id: str, detail: Optional[Mapping[str, Any]]) -> str:
    record_key = None
    if isinstance(detail, Mapping):
        record_key = detail.get("id") or detail.get("query_id")
    key = record_key if record_key not in (None, "") else record_id
    return f"stockpulse-report-{key}"


def _truncate_utf8(value: str, max_bytes: int) -> str:
    encoded = value.encode("utf-8")[:max_bytes]
    return encoded.decode("utf-8", errors="ignore")


def _export_filename_suffix(filename: str) -> str:
    lowered = str(filename).lower()
    for suffix in (".pdf", ".html", ".htm", ".md"):
        if lowered.endswith(suffix):
            return ".html" if suffix == ".htm" else suffix
    return ".md"


def build_content_disposition(filename: str) -> str:
    """Build a bounded ASCII fallback plus RFC 5987 UTF-8 filename."""
    # Discard everything after the first line break instead of attempting to
    # preserve attacker-controlled pseudo-header text in either filename form.
    first_line = re.split(r"[\r\n]", str(filename), maxsplit=1)[0]
    bounded = _truncate_utf8(first_line, 180)
    normalized = unicodedata.normalize("NFKD", bounded)
    ascii_name = normalized.encode("ascii", errors="ignore").decode("ascii")
    ascii_name = re.sub(r"[^A-Za-z0-9._-]+", "_", ascii_name).strip("._")
    suffix = _export_filename_suffix(bounded)
    bare_suffixes = {item.lstrip(".") for item in (".pdf", ".html", ".md")}
    if not ascii_name or ascii_name in bare_suffixes:
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
        "Markdown is always available. HTML is the office-friendly format and "
        "requires markdown-it-py from the optional report-export set. PDF "
        "requires the optional fpdf2 package and a resolvable CJK/Unicode font. "
        "DOCX/XLSX are not implemented; office_formats_status is html_only."
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
                "text/html": {"schema": {"type": "string", "format": "binary"}},
                "application/pdf": {"schema": {"type": "string", "format": "binary"}},
            },
        },
        400: {"description": "Invalid export format", "model": ErrorResponse},
        413: {"description": "Export resource limit exceeded", "model": ErrorResponse},
        429: {"description": "PDF export capacity is busy", "model": ErrorResponse},
        404: {"description": "Report not found", "model": ErrorResponse},
        500: {"description": "Export or report generation failed", "model": ErrorResponse},
        503: {
            "description": (
                "PDF/HTML dependency, font, deadline, or render worker unavailable; "
                "or security audit unavailable (operation_completed)"
            ),
            "model": ErrorResponse,
        },
    },
    summary="Export a history report",
    description=(
        "Export an analysis history record as Markdown (always), HTML "
        "(office-friendly; optional markdown-it-py), or PDF (optional fpdf2 + "
        "font). Content is converted from the same Markdown intermediate "
        "representation used by GET /history/{id}/markdown. Markdown is "
        "lossless. HTML and PDF preserve visible wording but drop link "
        "destinations and complete image destinations, replace images with an "
        "omission note, and enforce explicit byte/table bounds. PDF also "
        "enforces page/time/concurrency limits and exact glyph coverage. "
        "Invalid format is rejected before audit. Attempt is persisted before "
        "markdown load; attempt-store failure returns 503 "
        "operation_completed=false without generating bytes. After generation, "
        "completion-store failure returns 503 operation_completed=true with "
        "record_id and format and does not return the file. Domain 404/413/"
        "429/500/503 export codes are unchanged. GET /history/export/capabilities "
        "and GET /history/{id}/markdown are not this event."
    ),
)
def export_history_report(
    record_id: str,
    format: Annotated[
        str,
        Query(
            alias="format",
            description="Export format: md (default), html, or pdf",
            json_schema_extra={"enum": ["md", "html", "pdf"]},
        ),
    ] = "md",
    db_manager: DatabaseManager = Depends(get_database_manager),
    security_audit: SecurityAuditRecorder = Depends(require_security_audit_service),
) -> Response:
    if format not in ("md", "html", "pdf"):
        raise api_error(
            400,
            "export_format_invalid",
            "Unsupported export format. Supported formats: md, html, pdf.",
        )

    correlation_id = SecurityAuditService.new_correlation_id()
    try:
        _record_report_export_audit(
            security_audit,
            phase="attempt",
            correlation_id=correlation_id,
            record_id=record_id,
            format=format,
        )
    except SecurityAuditUnavailable:
        raise _report_export_audit_unavailable(operation_completed=False) from None

    service = HistoryService(db_manager)
    detail = service.resolve_and_get_detail(record_id)
    lookup_mode = _export_lookup_mode(record_id, detail)
    resolved_record_id = _resolved_record_id(detail)
    completion_fields = {
        "correlation_id": correlation_id,
        "record_id": record_id,
        "format": format,
        "resolved_record_id": resolved_record_id,
        "lookup_mode": lookup_mode,
    }

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
        _record_report_export_completion_best_effort(
            security_audit,
            outcome="failure",
            reason_code="generation_failed",
            **completion_fields,
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
        _record_report_export_completion_best_effort(
            security_audit,
            outcome="failure",
            reason_code="internal_error",
            **completion_fields,
        )
        raise api_error(
            500,
            "internal_error",
            "Failed to load report content for export",
        ) from exc

    if markdown_content is None:
        _record_report_export_completion_best_effort(
            security_audit,
            outcome="rejected",
            reason_code="not_found",
            **completion_fields,
        )
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
        _record_report_export_completion_best_effort(
            security_audit,
            outcome="rejected",
            reason_code=exc.error_code,
            **completion_fields,
        )
        raise api_error(400, exc.error_code, exc.message) from exc
    except ReportExportDependencyError as exc:
        _record_report_export_completion_best_effort(
            security_audit,
            outcome="failure",
            reason_code=exc.error_code,
            **completion_fields,
        )
        dependency = "markdown-it-py" if format == "html" else "fpdf2"
        raise api_error(
            503,
            exc.error_code,
            "The optional export backend is unavailable for the requested format.",
            params={
                "dependency": dependency,
                "install_hint": exc.install_hint,
            },
        ) from exc
    except ReportExportFontError as exc:
        _record_report_export_completion_best_effort(
            security_audit,
            outcome="failure",
            reason_code=exc.error_code,
            **completion_fields,
        )
        raise api_error(
            503,
            exc.error_code,
            "A validated font covering every report glyph is required for PDF export.",
            params={"env": "REPORT_EXPORT_PDF_FONT_PATH"},
        ) from exc
    except ReportExportLimitError as exc:
        _record_report_export_completion_best_effort(
            security_audit,
            outcome="failure",
            reason_code=exc.error_code,
            **completion_fields,
        )
        raise api_error(exc.status_code, exc.error_code, exc.message) from exc
    except ReportExportBusyError as exc:
        _record_report_export_completion_best_effort(
            security_audit,
            outcome="failure",
            reason_code=exc.error_code,
            **completion_fields,
        )
        raise api_error(exc.status_code, exc.error_code, exc.message) from exc
    except ReportExportWorkerError as exc:
        _record_report_export_completion_best_effort(
            security_audit,
            outcome="failure",
            reason_code=exc.error_code,
            **completion_fields,
        )
        raise api_error(exc.status_code, exc.error_code, exc.message) from exc
    except ReportExportError as exc:
        log_safe_exception(
            logger,
            "Report export failed",
            exc,
            error_code=exc.error_code,
            context={"record_id": record_id, "format": format},
        )
        _record_report_export_completion_best_effort(
            security_audit,
            outcome="failure",
            reason_code=exc.error_code or "internal_error",
            **completion_fields,
        )
        raise api_error(500, exc.error_code, "Report export failed.") from exc

    try:
        _record_report_export_audit(
            security_audit,
            phase="completion",
            correlation_id=correlation_id,
            record_id=record_id,
            format=format,
            outcome="success",
            reason_code="export_completed",
            resolved_record_id=resolved_record_id,
            lookup_mode=lookup_mode,
            byte_length=len(artifact.content),
        )
    except SecurityAuditUnavailable:
        completion_error = ReportExportAuditCompletionUnavailable(
            record_id=_audit_target_id(resolved_record_id or record_id),
            format=format,
        )
        raise _report_export_audit_unavailable(
            operation_completed=True,
            record_id=completion_error.record_id,
            format=completion_error.format,
        ) from completion_error

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
