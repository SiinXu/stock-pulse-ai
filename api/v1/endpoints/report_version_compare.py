# -*- coding: utf-8 -*-
"""Report version selection and comparison endpoints (issue #188 / T18)."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Security
from fastapi.security import APIKeyCookie

from api.deps import get_database_manager
from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.report_version_compare import (
    AnalysisDeltaPayload,
    ConfigComponentDiff,
    ConfigFingerprintDiff,
    ReportFieldDiff,
    ReportVersionCompareResponse,
    ReportVersionRunItem,
    ReportVersionRunListResponse,
)
from src.auth import COOKIE_NAME
from src.services.report_version_compare_service import (
    ReportVersionCompareError,
    ReportVersionCompareService,
)
from src.storage import DatabaseManager
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

admin_session_cookie = APIKeyCookie(
    name=COOKIE_NAME,
    scheme_name="AdminSessionCookie",
    auto_error=False,
)
router = APIRouter(dependencies=[Security(admin_session_cookie)])

AUTH_RESPONSE = {
    401: {
        "model": ErrorResponse,
        "description": "Not authenticated when ADMIN_AUTH_ENABLED=true",
    },
}


def _http_from_service_error(exc: ReportVersionCompareError) -> HTTPException:
    status = 400
    if exc.code in {"base_run_not_found", "target_run_not_found"}:
        status = 404
    elif exc.code == "incomparable":
        status = 409
    return HTTPException(
        status_code=status,
        detail={
            "error": exc.code,
            "message": str(exc),
            "params": exc.params,
        },
    )


def _run_item(data: dict) -> ReportVersionRunItem:
    return ReportVersionRunItem(**data)


@router.get(
    "/runs",
    response_model=ReportVersionRunListResponse,
    responses={
        **AUTH_RESPONSE,
        400: {"model": ErrorResponse, "description": "Invalid query parameters"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
    summary="List analysis runs for version comparison",
    description=(
        "List historical analysis runs for a symbol with run id, time, model, "
        "and configuration fingerprint for the report version picker."
    ),
    operation_id="listReportVersionRuns",
)
def list_report_version_runs(
    stock_code: str = Query(..., min_length=1, description="Stock code filter"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    limit: int = Query(20, ge=1, le=100, description="Page size"),
    report_type: Optional[str] = Query(
        None,
        description="Optional report type filter; market_review rows are skipped when omitted",
    ),
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> ReportVersionRunListResponse:
    service = ReportVersionCompareService(db_manager)
    try:
        result = service.list_runs(
            stock_code=stock_code,
            page=page,
            limit=limit,
            report_type=report_type,
        )
    except ReportVersionCompareError as exc:
        raise _http_from_service_error(exc) from exc
    except Exception as exc:  # broad-exception: fallback_recorded - map list failures to sanitized 500
        log_safe_exception(
            logger,
            "List report version runs failed",
            exc,
            error_code="internal_error",
            context={"stock_code": stock_code},
        )
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": "Internal server error"},
        ) from exc

    return ReportVersionRunListResponse(
        stock_code=result["stock_code"],
        total=result["total"],
        page=result["page"],
        limit=result["limit"],
        items=[_run_item(item) for item in result.get("items", [])],
    )


@router.get(
    "/compare",
    response_model=ReportVersionCompareResponse,
    responses={
        **AUTH_RESPONSE,
        400: {"model": ErrorResponse, "description": "Invalid parameters"},
        404: {"model": ErrorResponse, "description": "Run not found"},
        409: {"model": ErrorResponse, "description": "Runs are incomparable"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
    summary="Compare two analysis report versions",
    description=(
        "Compare two selected analysis runs: side-by-side field snapshots, "
        "configuration provenance differences, and the typed T17 AnalysisDelta. "
        "engine_pending and no_baseline are "
        "never presented as 'no change'."
    ),
    operation_id="compareReportVersions",
)
def compare_report_versions(
    stock_code: str = Query(..., min_length=1, description="Stock code for the selected runs"),
    base_run_id: str = Query(..., min_length=1, description="Baseline analysis history id"),
    target_run_id: str = Query(..., min_length=1, description="Target analysis history id"),
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> ReportVersionCompareResponse:
    service = ReportVersionCompareService(db_manager)
    try:
        result = service.compare_runs(
            stock_code=stock_code,
            base_run_id=base_run_id,
            target_run_id=target_run_id,
        )
    except ReportVersionCompareError as exc:
        raise _http_from_service_error(exc) from exc
    except Exception as exc:  # broad-exception: fallback_recorded - map compare failures to sanitized 500
        log_safe_exception(
            logger,
            "Compare report versions failed",
            exc,
            error_code="internal_error",
            context={
                "stock_code": stock_code,
                "base_run_id": base_run_id,
                "target_run_id": target_run_id,
            },
        )
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": "Internal server error"},
        ) from exc

    delta_raw = result.get("delta")
    delta = AnalysisDeltaPayload(**delta_raw) if isinstance(delta_raw, dict) else None
    config_raw = result.get("config_diff") or {}
    config_diff = ConfigFingerprintDiff(
        base_fingerprint=config_raw.get("base_fingerprint"),
        target_fingerprint=config_raw.get("target_fingerprint"),
        identical=bool(config_raw.get("identical")),
        has_differences=bool(config_raw.get("has_differences")),
        comparison_status=config_raw.get("comparison_status") or "unknown",
        base_complete=bool(config_raw.get("base_complete")),
        target_complete=bool(config_raw.get("target_complete")),
        base_missing_keys=list(config_raw.get("base_missing_keys") or []),
        target_missing_keys=list(config_raw.get("target_missing_keys") or []),
        components=[
            ConfigComponentDiff(**component)
            for component in config_raw.get("components") or []
        ],
    )
    field_diffs = [
        ReportFieldDiff(**item) for item in result.get("field_diffs") or []
    ]

    return ReportVersionCompareResponse(
        status=result["status"],
        stock_code=result["stock_code"],
        base_run=_run_item(result["base_run"]),
        target_run=_run_item(result["target_run"]),
        config_diff=config_diff,
        field_diffs=field_diffs,
        delta=delta,
        engine_status=result["engine_status"],
    )
