# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Evidence-chain and auditable report-package export endpoints (Issues #986 / #127)."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response

from api.deps import get_database_manager, require_security_audit_service
from api.v1.errors import api_error
from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.evidence_pack import AuditPackageJsonEnvelope, EvidenceChainExportResponse
from src.application_services import get_application_services
from src.auth import COOKIE_NAME, is_auth_enabled, verify_session
from src.services.audit_package_export_service import (
    AuditPackageExportDisabled,
    AuditPackageExportService,
    AuditPackageNotFound,
    is_audit_export_enabled,
)
from src.services.evidence_chain_service import (
    EvidenceChainDisabled,
    EvidenceChainNotFound,
    EvidenceChainService,
    is_evidence_chain_enabled,
)
from src.services.history_service import HistoryService
from src.services.security_audit_service import (
    SecurityAuditRecorder,
    SecurityAuditService,
    SecurityAuditUnavailable,
)
from src.storage import DatabaseManager
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)
router = APIRouter()
analysis_alias_router = APIRouter()

AUDIT_PACKAGE_RESPONSES = {
    200: {
        "description": "ZIP audit package or JSON envelope",
        "model": AuditPackageJsonEnvelope,
        "content": {
            "application/zip": {"schema": {"type": "string", "format": "binary"}},
        },
    },
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
    500: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
}


def _audit_target_id(record_id: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,119}", record_id):
        return record_id
    return f"sha256:{hashlib.sha256(record_id.encode('utf-8')).hexdigest()[:24]}"


def _require_export_access(request: Request, *, auth_required_code: str, auth_required_message: str) -> None:
    if not is_auth_enabled():
        raise api_error(403, auth_required_code, auth_required_message)
    session_cookie = request.cookies.get(COOKIE_NAME)
    if not session_cookie or not verify_session(session_cookie):
        raise api_error(401, "unauthorized", "Administrator authentication required")


def _record_export_audit(
    security_audit: SecurityAuditRecorder, *, phase, correlation_id, record_id, action, format,
    outcome="success", reason_code="export_completed", resolved_record_id=None, lookup_mode=None,
) -> None:
    audited_id = resolved_record_id or record_id
    metadata = {"format": format, "lookup_key": _audit_target_id(record_id)}
    if resolved_record_id is not None:
        metadata["resolved_record_id"] = _audit_target_id(resolved_record_id)
    if lookup_mode is not None:
        metadata["lookup_mode"] = lookup_mode
    common = {
        "event_type": action, "actor_type": "administrator", "actor_id": "admin_session",
        "execution_id": correlation_id, "action": action, "target_type": "analysis_history",
        "target_id": _audit_target_id(audited_id), "correlation_id": correlation_id, "metadata": metadata,
    }
    try:
        if phase == "attempt":
            security_audit.record_attempt(**common)
        else:
            security_audit.record_completion(**common, outcome=outcome, reason_code=reason_code)
    except SecurityAuditUnavailable:
        raise api_error(503, "security_audit_unavailable", "Security audit storage is unavailable") from None


def _download_headers(*, record_id: str, extension: str, schema: str, truncated: bool) -> dict:
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", record_id)[:80] or "record"
    return {
        "Cache-Control": "private, no-store", "Pragma": "no-cache",
        "Content-Disposition": f'attachment; filename="audit-package-{safe_id}.{extension}"',
        "X-Content-Type-Options": "nosniff",
        "X-Audit-Package-Schema": schema,
        "X-Audit-Package-Truncated": "1" if truncated else "0",
    }


@router.get(
    "/{record_id}/evidence-chain",
    response_model=EvidenceChainExportResponse,
    responses={200: {"description": "Redacted evidence-chain-v1 package"},
               401: {"model": ErrorResponse}, 403: {"model": ErrorResponse},
               404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    summary="Export evidence chain for an analysis history record",
    operation_id="exportEvidenceChain",
)
def export_evidence_chain(
    request: Request, record_id: str,
    db_manager: DatabaseManager = Depends(get_database_manager),
    security_audit: SecurityAuditRecorder = Depends(require_security_audit_service),
) -> Response:
    config = get_application_services().config
    if not is_evidence_chain_enabled(config):
        raise api_error(404, "evidence_chain_disabled", "Evidence chain is not enabled")
    _require_export_access(
        request,
        auth_required_code="evidence_chain_auth_required",
        auth_required_message="Evidence chain export requires enabled administrator authentication",
    )
    correlation_id = SecurityAuditService.new_correlation_id()
    action = "evidence_chain.export"
    _record_export_audit(security_audit, phase="attempt", correlation_id=correlation_id,
                         record_id=record_id, action=action, format="json")
    history = HistoryService(db_manager)
    service = EvidenceChainService(history_service=history, config=config)
    try:
        result = service.build_for_record(record_id)
    except EvidenceChainDisabled:
        _record_export_audit(security_audit, phase="completion", correlation_id=correlation_id,
                             record_id=record_id, action=action, format="json",
                             outcome="denied", reason_code="export_disabled")
        raise api_error(404, "evidence_chain_disabled", "Evidence chain is not enabled")
    except EvidenceChainNotFound:
        _record_export_audit(security_audit, phase="completion", correlation_id=correlation_id,
                             record_id=record_id, action=action, format="json",
                             outcome="denied", reason_code="record_not_found")
        raise api_error(404, "not_found", "Analysis history record not found")
    except Exception as exc:  # broad-exception: fallback_recorded - Export failure is logged, audited, and mapped to a safe API error.
        log_safe_exception(logger, "Evidence chain export failed", exc,
                           error_code="evidence_chain_export_failed",
                           context={"record_id": _audit_target_id(record_id)})
        _record_export_audit(security_audit, phase="completion", correlation_id=correlation_id,
                             record_id=record_id, action=action, format="json",
                             outcome="failure", reason_code="export_failed")
        raise api_error(500, "internal_error", "Evidence chain export failed")

    run = result.package.get("run") if isinstance(result.package, dict) else {}
    run = run if isinstance(run, dict) else {}
    resolved_s = str(run["record_id"]) if isinstance(run.get("record_id"), str) and run.get("record_id") else None
    mode_s = str(run["lookup_mode"]) if isinstance(run.get("lookup_mode"), str) else None
    try:
        EvidenceChainExportResponse.model_validate(result.package)
    except ValueError:
        _record_export_audit(security_audit, phase="completion", correlation_id=correlation_id,
                             record_id=record_id, action=action, format="json",
                             outcome="failure", reason_code="response_contract_invalid",
                             resolved_record_id=resolved_s, lookup_mode=mode_s)
        raise api_error(500, "internal_error", "Evidence chain export failed")
    _record_export_audit(security_audit, phase="completion", correlation_id=correlation_id,
                         record_id=record_id, action=action, format="json",
                         outcome="success", reason_code="export_completed",
                         resolved_record_id=resolved_s, lookup_mode=mode_s)
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", record_id)[:80] or "record"
    return Response(
        content=result.to_json_text(), media_type="application/json",
        headers={
            "Cache-Control": "private, no-store", "Pragma": "no-cache",
            "Content-Disposition": f'attachment; filename="evidence-chain-{safe_id}.json"',
            "X-Content-Type-Options": "nosniff",
            "X-Evidence-Chain-Schema": result.schema_version,
            "X-Evidence-Chain-Truncated": "1" if result.package.get("truncated") else "0",
        },
    )


@router.get(
    "/{record_id}/evidence-pack",
    responses=AUDIT_PACKAGE_RESPONSES,
    summary="Export auditable report package for an analysis history record",
    operation_id="exportAuditPackage",
    response_model=None,
)
def export_audit_package(
    request: Request, record_id: str,
    format: Literal["zip", "json"] = Query("zip"),
    db_manager: DatabaseManager = Depends(get_database_manager),
    security_audit: SecurityAuditRecorder = Depends(require_security_audit_service),
) -> Response:
    config = get_application_services().config
    if not is_audit_export_enabled(config):
        raise api_error(404, "audit_export_disabled", "Audit package export is not enabled")
    _require_export_access(
        request,
        auth_required_code="audit_export_auth_required",
        auth_required_message="Audit package export requires enabled administrator authentication",
    )
    correlation_id = SecurityAuditService.new_correlation_id()
    action = "audit_package.export"
    _record_export_audit(security_audit, phase="attempt", correlation_id=correlation_id,
                         record_id=record_id, action=action, format=format)
    history = HistoryService(db_manager)
    service = AuditPackageExportService(history_service=history, config=config)
    try:
        result = service.export_for_record(record_id)
    except AuditPackageExportDisabled:
        _record_export_audit(security_audit, phase="completion", correlation_id=correlation_id,
                             record_id=record_id, action=action, format=format,
                             outcome="denied", reason_code="export_disabled")
        raise api_error(404, "audit_export_disabled", "Audit package export is not enabled")
    except EvidenceChainDisabled:
        _record_export_audit(security_audit, phase="completion", correlation_id=correlation_id,
                             record_id=record_id, action=action, format=format,
                             outcome="denied", reason_code="evidence_chain_disabled")
        raise api_error(404, "evidence_chain_disabled", "Evidence chain is not enabled")
    except (AuditPackageNotFound, EvidenceChainNotFound):
        _record_export_audit(security_audit, phase="completion", correlation_id=correlation_id,
                             record_id=record_id, action=action, format=format,
                             outcome="denied", reason_code="record_not_found")
        raise api_error(404, "not_found", "Analysis history record not found")
    except Exception as exc:  # broad-exception: fallback_recorded - Export failure is logged, audited, and mapped to a safe API error.
        log_safe_exception(logger, "Audit package export failed", exc,
                           error_code="audit_package_export_failed",
                           context={"record_id": _audit_target_id(record_id)})
        _record_export_audit(security_audit, phase="completion", correlation_id=correlation_id,
                             record_id=record_id, action=action, format=format,
                             outcome="failure", reason_code="export_failed")
        raise api_error(500, "internal_error", "Audit package export failed")

    if format == "json":
        envelope = result.to_json_envelope()
        try:
            validated_envelope = AuditPackageJsonEnvelope.model_validate(envelope)
            response_content = json.dumps(
                validated_envelope.model_dump(mode="json"),
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            )
        except (TypeError, ValueError):
            _record_export_audit(
                security_audit,
                phase="completion",
                correlation_id=correlation_id,
                record_id=record_id,
                action=action,
                format=format,
                outcome="failure",
                reason_code="response_contract_invalid",
                resolved_record_id=result.resolved_record_id,
                lookup_mode=result.lookup_mode,
            )
            raise api_error(500, "internal_error", "Audit package export failed")
        _record_export_audit(security_audit, phase="completion", correlation_id=correlation_id,
                             record_id=record_id, action=action, format=format,
                             outcome="success", reason_code="export_completed",
                             resolved_record_id=result.resolved_record_id,
                             lookup_mode=result.lookup_mode)
        return Response(
            content=response_content,
            media_type="application/json",
            headers=_download_headers(record_id=record_id, extension="json",
                                      schema=result.schema_version, truncated=result.truncated),
        )
    _record_export_audit(security_audit, phase="completion", correlation_id=correlation_id,
                         record_id=record_id, action=action, format=format,
                         outcome="success", reason_code="export_completed",
                         resolved_record_id=result.resolved_record_id,
                         lookup_mode=result.lookup_mode)
    return Response(
        content=result.zip_bytes, media_type="application/zip",
        headers=_download_headers(record_id=record_id, extension="zip",
                                  schema=result.schema_version, truncated=result.truncated),
    )


# Keep the issue-compatible /analysis aliases in the same implementation while
# assigning distinct operation ids so OpenAPI clients can generate both paths.
analysis_alias_router.add_api_route(
    "/{record_id}/evidence-chain",
    export_evidence_chain,
    methods=["GET"],
    response_model=EvidenceChainExportResponse,
    responses={
        200: {"description": "Redacted evidence-chain-v1 package"},
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
    summary="Export evidence chain for an analysis history record",
    operation_id="exportAnalysisEvidenceChain",
)
analysis_alias_router.add_api_route(
    "/{record_id}/evidence-pack",
    export_audit_package,
    methods=["GET"],
    response_model=None,
    responses=AUDIT_PACKAGE_RESPONSES,
    summary="Export auditable report package for an analysis history record",
    operation_id="exportAnalysisAuditPackage",
)
