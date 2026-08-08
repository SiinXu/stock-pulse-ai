# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Read-only capability registry aggregation endpoint (Issue #221 / T15)."""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Security
from fastapi.security import APIKeyCookie

from api.v1.schemas.capabilities import CapabilityItem, CapabilityListResponse
from api.v1.schemas.common import ErrorResponse
from src.auth import COOKIE_NAME
from src.capability_registry import CapabilityRecord, collect_capability_records
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

admin_session_cookie = APIKeyCookie(
    name=COOKIE_NAME,
    scheme_name="AdminSessionCookie",
    auto_error=False,
)
router = APIRouter(dependencies=[Security(admin_session_cookie)])

AUTH_RESPONSE = {
    401: {"model": ErrorResponse, "description": "Login required when ADMIN_AUTH_ENABLED=true"},
    400: {"model": ErrorResponse, "description": "Invalid domain filter"},
}


def _to_item(record: CapabilityRecord) -> CapabilityItem:
    return CapabilityItem(
        id=record.capability_id,
        domain=record.domain,
        provider=record.provider,
        available=record.available,
        reason_code=record.reason_code,
        reason_message=record.reason_message,
        display_name=record.display_name,
        details=dict(record.details),
    )


@router.get(
    "",
    response_model=CapabilityListResponse,
    responses={**AUTH_RESPONSE},
    summary="List aggregated agent capabilities (read-only)",
    description=(
        "Return a read-only aggregation of capabilities from the existing "
        "data-provider catalog, agent tool registry, and plugin extension "
        "surface. Does not change registration behavior. "
        "available=false includes a stable reason_code such as "
        "feature_disabled, missing_config, or missing_dependency."
    ),
    operation_id="listCapabilities",
)
def list_capabilities(
    domain: Optional[List[str]] = Query(
        default=None,
        description="Optional domain filter. Allowed values: data, tool, extension.",
    ),
) -> CapabilityListResponse:
    try:
        records = collect_capability_records(domains=domain)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_capability_domain", "message": str(exc)},
        ) from exc
    except Exception as exc:  # broad-exception: fallback_recorded - defensive aggregation boundary
        log_safe_exception(
            logger,
            "Capability registry aggregation failed",
            exc,
            error_code="capability_registry_failed",
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "capability_registry_failed",
                "message": "Capability registry aggregation failed",
            },
        ) from exc

    items = [_to_item(record) for record in records]
    available_count = sum(1 for item in items if item.available)
    return CapabilityListResponse(
        items=items,
        total=len(items),
        available_count=available_count,
        unavailable_count=len(items) - available_count,
    )
