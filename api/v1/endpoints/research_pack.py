# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Research asset package export endpoints (Issues #988 / #1140)."""
from __future__ import annotations
import hashlib, json, logging, re
from typing import Literal
from fastapi import APIRouter, Depends, Query, Request, Response
from api.deps import get_database_manager, require_security_audit_service
from api.v1.errors import api_error
from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.research_pack import ResearchPackJsonEnvelope
from src.application_services import get_application_services
from src.auth import COOKIE_NAME, is_auth_enabled, verify_session
from src.services.history_service import HistoryService
from src.services.research_pack_export_service import (
    ResearchPackExportDisabled, ResearchPackExportService, ResearchPackLimitError,
    ResearchPackNotFound, is_research_pack_export_enabled,
)
from src.services.security_audit_service import (
    SecurityAuditRecorder, SecurityAuditService, SecurityAuditUnavailable,
)
from src.storage import DatabaseManager
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)
router = APIRouter()

def _audit_target_id(record_id: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,119}", record_id):
        return record_id
    return f"sha256:{hashlib.sha256(record_id.encode('utf-8')).hexdigest()[:24]}"

def _require_export_access(request: Request) -> None:
    if not is_auth_enabled():
        raise api_error(403, "research_pack_auth_required",
                        "Research pack export requires enabled administrator authentication")
    session_cookie = request.cookies.get(COOKIE_NAME)
    if not session_cookie or not verify_session(session_cookie):
        raise api_error(401, "unauthorized", "Administrator authentication required")

def _record_export_audit(security_audit, *, phase, correlation_id, record_id, format,
                         outcome="success", reason_code="export_completed",
                         resolved_record_id=None, lookup_mode=None):
    audited_id = resolved_record_id or record_id
    metadata = {"format": format, "lookup_key": _audit_target_id(record_id)}
    if resolved_record_id is not None:
        metadata["resolved_record_id"] = _audit_target_id(resolved_record_id)
    if lookup_mode is not None:
        metadata["lookup_mode"] = lookup_mode
    common = {
        "event_type": "research_pack.export", "actor_type": "administrator",
        "actor_id": "admin_session", "execution_id": correlation_id,
        "action": "research_pack.export", "target_type": "analysis_history",
        "target_id": _audit_target_id(audited_id), "correlation_id": correlation_id,
        "metadata": metadata,
    }
    try:
        if phase == "attempt":
            security_audit.record_attempt(**common)
        else:
            security_audit.record_completion(**common, outcome=outcome, reason_code=reason_code)
    except SecurityAuditUnavailable:
        raise api_error(503, "security_audit_unavailable", "Security audit storage is unavailable") from None

def _progress_header(progress):
    parts = []
    for item in progress or []:
        if isinstance(item, dict) and item.get("name") and item.get("status"):
            parts.append(f"{str(item['name'])[:40]}={str(item['status'])[:16]}")
    return ";".join(parts)[:900]

@router.get(
    "/{record_id}/research-pack",
    responses={
        200: {"description": "Research pack ZIP or JSON envelope",
              "content": {"application/zip": {"schema": {"type": "string", "format": "binary"}},
                          "application/json": {"schema": {"$ref": "#/components/schemas/ResearchPackJsonEnvelope"}}}},
        401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse},
        413: {"model": ErrorResponse}, 500: {"model": ErrorResponse}, 503: {"model": ErrorResponse},
    },
    summary="Export research asset package for an analysis history record",
    description="One-click ZIP with redacted report, decision card, evidence refs, signals, and reasoning trace. Default off.",
    operation_id="exportResearchPack", response_model=None,
)
def export_research_pack(
    request: Request, record_id: str,
    format: Literal["zip", "json"] = Query("zip"),
    language: str = Query("en"),
    db_manager: DatabaseManager = Depends(get_database_manager),
    security_audit: SecurityAuditRecorder = Depends(require_security_audit_service),
) -> Response:
    config = get_application_services().config
    if not is_research_pack_export_enabled(config):
        raise api_error(404, "research_pack_export_disabled", "Research pack export is not enabled")
    _require_export_access(request)
    correlation_id = SecurityAuditService.new_correlation_id()
    _record_export_audit(security_audit, phase="attempt", correlation_id=correlation_id,
                         record_id=record_id, format=format)
    history = HistoryService(db_manager)
    service = ResearchPackExportService(history_service=history, config=config)
    lang = "zh" if str(language).lower().startswith("zh") else "en"
    try:
        result = service.export_for_record(record_id, language=lang)
    except ResearchPackExportDisabled:
        _record_export_audit(security_audit, phase="completion", correlation_id=correlation_id,
                             record_id=record_id, format=format, outcome="denied", reason_code="export_disabled")
        raise api_error(404, "research_pack_export_disabled", "Research pack export is not enabled")
    except ResearchPackNotFound:
        _record_export_audit(security_audit, phase="completion", correlation_id=correlation_id,
                             record_id=record_id, format=format, outcome="denied", reason_code="record_not_found")
        raise api_error(404, "not_found", "Analysis history record not found")
    except ResearchPackLimitError as exc:
        _record_export_audit(security_audit, phase="completion", correlation_id=correlation_id,
                             record_id=record_id, format=format, outcome="failure", reason_code=exc.code)
        raise api_error(413, exc.code, exc.message)
    except Exception as exc:  # broad-exception: fallback_recorded
        log_safe_exception(logger, "Research pack export failed", exc,
                           error_code="research_pack_export_failed", context={"record_id": record_id})
        _record_export_audit(security_audit, phase="completion", correlation_id=correlation_id,
                             record_id=record_id, format=format, outcome="failure", reason_code="export_failed")
        raise api_error(500, "internal_error", "Research pack export failed")
    _record_export_audit(security_audit, phase="completion", correlation_id=correlation_id,
                         record_id=record_id, format=format, outcome="success", reason_code="export_completed",
                         resolved_record_id=result.resolved_record_id, lookup_mode=result.lookup_mode)
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", record_id)[:80] or "record"
    headers = {
        "Cache-Control": "private, no-store", "Pragma": "no-cache", "X-Content-Type-Options": "nosniff",
        "X-Research-Pack-Schema": result.schema_version,
        "X-Research-Pack-Truncated": "1" if result.truncated else "0",
        "X-Research-Pack-Bytes": str(len(result.zip_bytes)),
        "X-Research-Pack-Progress": _progress_header(result.progress),
    }
    if format == "json":
        envelope = result.to_json_envelope()
        try:
            ResearchPackJsonEnvelope.model_validate(envelope)
        except ValueError:
            raise api_error(500, "internal_error", "Research pack export failed")
        return Response(
            content=json.dumps(envelope, ensure_ascii=False, separators=(",", ":")),
            media_type="application/json",
            headers={**headers, "Content-Disposition": f'attachment; filename="research-pack-{safe_id}.json"'},
        )
    return Response(
        content=result.zip_bytes, media_type="application/zip",
        headers={**headers, "Content-Disposition": f'attachment; filename="research-pack-{safe_id}.zip"'},
    )
