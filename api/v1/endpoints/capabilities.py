# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Owner-driven, read-only capability inventory endpoint."""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Security
from fastapi.security import APIKeyCookie

from api.v1.schemas.capabilities import (
    CapabilityItem,
    CapabilityListResponse,
    DataCapabilityItem,
    ExtensionCapabilityItem,
    ToolCapabilityItem,
)
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
    item_model = {
        "data": DataCapabilityItem,
        "tool": ToolCapabilityItem,
        "extension": ExtensionCapabilityItem,
    }[record.domain]
    return item_model(
        id=record.capability_id,
        domain=record.domain,
        type=record.capability_type,
        owner=record.owner,
        provider=record.provider,
        version=record.version,
        source_generation=record.source_generation,
        as_of=record.as_of,
        registered=record.registered,
        configured=record.configured,
        dependency_ready=record.dependency_ready,
        grantable=record.grantable,
        executable=record.executable,
        healthy=record.healthy,
        degraded=record.degraded,
        dependencies=list(record.dependencies),
        scopes=list(record.scopes),
        markets=list(record.markets),
        reason_code=record.reason_code,
        display_name=record.display_name,
    )


@router.get(
    "",
    response_model=CapabilityListResponse,
    responses={**AUTH_RESPONSE},
    summary="List the runtime capability inventory (read-only)",
    description=(
        "Capture a versioned read-only inventory from the live data-provider, "
        "tool, and plugin owners. Unknown readiness remains null. Source read "
        "failures are returned explicitly with partial=true; this endpoint does "
        "not register, resolve, grant, execute, or health-check capabilities."
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
        snapshot = collect_capability_records(domains=domain)
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

    items = [_to_item(record) for record in snapshot.items]
    executable_count = sum(item.executable is True for item in items)
    non_executable_count = sum(item.executable is False for item in items)
    return CapabilityListResponse(
        schema_version=snapshot.schema_version,
        partial=snapshot.partial,
        sources=[source.to_dict() for source in snapshot.sources],
        items=items,
        total=len(items),
        executable_count=executable_count,
        non_executable_count=non_executable_count,
        unknown_executable_count=len(items) - executable_count - non_executable_count,
    )
