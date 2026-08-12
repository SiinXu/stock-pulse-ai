# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Capability inventory (read) plus write-side registry and task routing."""

from __future__ import annotations

import logging
import os
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Security
from fastapi.security import APIKeyCookie

from api.v1.schemas.capabilities import (
    CapabilityItem,
    CapabilityListResponse,
    DataCapabilityItem,
    DependencyIssueResponse,
    ExtensionCapabilityItem,
    PipelineCapabilityItem,
    ResolutionResultResponse,
    ResolveCapabilitiesRequest,
    ResolveCapabilitiesResponse,
    RouteCandidateResponse,
    SkillCapabilityItem,
    TaskRouteDecisionResponse,
    TaskRouteRequest,
    ToolCapabilityItem,
    WriteCapabilityEntryRequest,
    WriteCapabilityEntryResponse,
    WriteCapabilityListResponse,
    WriteCapabilityUpdateRequest,
)
from api.v1.schemas.common import ErrorResponse
from src.auth import COOKIE_NAME, is_auth_enabled
from src.capability_registry import (
    CapabilityRecord,
    CapabilityWriteError,
    collect_capability_records,
    get_capability_write_service,
    resolve_many,
    resolve_task_model_route,
)
from src.capability_registry.resolution import CapabilityResolutionError
from src.capability_registry.write_models import WriteCapabilityEntry
from src.capability_registry.write_store import WriteRegistryStoreError
from src.services.security_audit_service import SecurityAuditUnavailable
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
    400: {"model": ErrorResponse, "description": "Invalid request"},
    404: {"model": ErrorResponse, "description": "Capability not found"},
    409: {"model": ErrorResponse, "description": "Capability already exists"},
    503: {"model": ErrorResponse, "description": "Security audit or registry storage unavailable"},
}


def _actor_id() -> str:
    if os.getenv("DSA_DESKTOP_MODE") == "true":
        return "desktop_operator"
    if is_auth_enabled():
        return "authenticated_admin"
    return "local_operator"


def _to_item(record: CapabilityRecord) -> CapabilityItem:
    item_model = {
        "data": DataCapabilityItem,
        "tool": ToolCapabilityItem,
        "extension": ExtensionCapabilityItem,
        "skill": SkillCapabilityItem,
        "pipeline": PipelineCapabilityItem,
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
        providers=list(record.providers),
        provider_count=record.provider_count,
        reason_code=record.reason_code,
        display_name=record.display_name,
    )


def _write_entry_response(entry: WriteCapabilityEntry) -> WriteCapabilityEntryResponse:
    return WriteCapabilityEntryResponse(
        capability_id=entry.capability_id,
        domain=entry.domain,  # type: ignore[arg-type]
        capability_type=entry.capability_type,  # type: ignore[arg-type]
        version=entry.version,
        status=entry.status,  # type: ignore[arg-type]
        provider=entry.provider,
        display_name=entry.display_name,
        dependencies=list(entry.dependencies),
        tags=list(entry.tags),
        scopes=list(entry.scopes),
        markets=list(entry.markets),
        model_route=entry.model_route,
        cost_tier=entry.cost_tier,
        latency_class=entry.latency_class,
        registered_at=entry.registered_at,
        updated_at=entry.updated_at,
        retired_at=entry.retired_at,
        generation=entry.generation,
    )


def _map_write_error(exc: CapabilityWriteError) -> HTTPException:
    status = {
        "capability_not_found": 404,
        "capability_already_exists": 409,
        "capability_retired": 409,
        "capability_identity_immutable": 400,
        "capability_validation_failed": 400,
        "write_registry_corrupt": 503,
        "write_registry_unreadable": 503,
        "write_registry_too_large": 503,
        "write_registry_schema_unsupported": 503,
        "write_registry_persist_failed": 503,
    }.get(exc.error_code, 400)
    return HTTPException(
        status_code=status,
        detail={"error": exc.error_code, "message": exc.message},
    )


@router.get(
    "",
    response_model=CapabilityListResponse,
    responses={**AUTH_RESPONSE},
    summary="List the runtime capability inventory (read-only)",
    description=(
        "Capture a versioned read-only inventory from live owners. Availability "
        "comes only from runtime registration and owner health state."
    ),
    operation_id="listCapabilities",
)
def list_capabilities(
    domain: Optional[List[str]] = Query(
        default=None,
        description="Optional domain filter. Allowed values: data, tool, extension, skill, pipeline.",
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
            logger, "Capability registry aggregation failed", exc,
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


@router.get(
    "/registry",
    response_model=WriteCapabilityListResponse,
    responses={**AUTH_RESPONSE},
    summary="List write-side capability declarations",
    operation_id="listCapabilityRegistry",
)
def list_capability_registry(
    domain: Optional[str] = Query(default=None),
    include_retired: bool = Query(default=True),
) -> WriteCapabilityListResponse:
    service = get_capability_write_service()
    try:
        snapshot = service.list_entries(domain=domain, include_retired=include_retired)
    except WriteRegistryStoreError as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": exc.error_code, "message": str(exc)},
        ) from exc
    items = [_write_entry_response(entry) for entry in snapshot.entries]
    return WriteCapabilityListResponse(
        schema_version=snapshot.schema_version,  # type: ignore[arg-type]
        generation=snapshot.generation,
        as_of=snapshot.as_of,
        items=items,
        total=len(items),
    )


@router.post(
    "/registry",
    response_model=WriteCapabilityEntryResponse,
    responses={**AUTH_RESPONSE},
    summary="Register a write-side capability declaration",
    operation_id="registerCapability",
)
def register_capability(request: WriteCapabilityEntryRequest) -> WriteCapabilityEntryResponse:
    service = get_capability_write_service()
    payload = request.model_dump()
    if not payload.get("provider"):
        payload["provider"] = payload["capability_id"]
    try:
        entry = service.register(
            payload, actor_type="administrator", actor_id=_actor_id(),
        )
    except CapabilityWriteError as exc:
        raise _map_write_error(exc) from None
    except SecurityAuditUnavailable:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "security_audit_unavailable",
                "message": "Security audit storage is unavailable",
                "operation_completed": False,
            },
        ) from None
    return _write_entry_response(entry)


@router.put(
    "/registry/{capability_id}",
    response_model=WriteCapabilityEntryResponse,
    responses={**AUTH_RESPONSE},
    summary="Update a write-side capability declaration",
    operation_id="updateCapability",
)
def update_capability(
    capability_id: str,
    request: WriteCapabilityUpdateRequest,
) -> WriteCapabilityEntryResponse:
    service = get_capability_write_service()
    payload = {k: v for k, v in request.model_dump().items() if v is not None}
    try:
        entry = service.update(
            capability_id, payload, actor_type="administrator", actor_id=_actor_id(),
        )
    except CapabilityWriteError as exc:
        raise _map_write_error(exc) from None
    except SecurityAuditUnavailable:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "security_audit_unavailable",
                "message": "Security audit storage is unavailable",
                "operation_completed": False,
            },
        ) from None
    return _write_entry_response(entry)


@router.post(
    "/registry/{capability_id}/retire",
    response_model=WriteCapabilityEntryResponse,
    responses={**AUTH_RESPONSE},
    summary="Retire a write-side capability declaration",
    operation_id="retireCapability",
)
def retire_capability(capability_id: str) -> WriteCapabilityEntryResponse:
    service = get_capability_write_service()
    try:
        entry = service.retire(
            capability_id, actor_type="administrator", actor_id=_actor_id(),
        )
    except CapabilityWriteError as exc:
        raise _map_write_error(exc) from None
    except SecurityAuditUnavailable:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "security_audit_unavailable",
                "message": "Security audit storage is unavailable",
                "operation_completed": False,
            },
        ) from None
    return _write_entry_response(entry)


@router.post(
    "/resolve",
    response_model=ResolveCapabilitiesResponse,
    responses={**AUTH_RESPONSE},
    summary="Resolve capability dependencies and version compatibility",
    operation_id="resolveCapabilities",
)
def resolve_capabilities(request: ResolveCapabilitiesRequest) -> ResolveCapabilitiesResponse:
    service = get_capability_write_service()
    try:
        snapshot = service.list_entries(include_retired=True)
    except WriteRegistryStoreError as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": exc.error_code, "message": str(exc)},
        ) from exc

    inventory_items = None
    if request.include_inventory:
        try:
            inventory_items = collect_capability_records().items
        except Exception as exc:  # broad-exception: fallback_recorded
            log_safe_exception(
                logger, "Capability inventory unavailable during resolve", exc,
                error_code="capability_inventory_unavailable_for_resolve",
            )
            inventory_items = ()

    try:
        results = resolve_many(
            request.capability_ids,
            write_snapshot=snapshot,
            inventory_items=inventory_items,
        )
    except CapabilityResolutionError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": exc.error_code, "message": exc.message},
        ) from None

    payload = [
        ResolutionResultResponse(
            capability_id=item.capability_id,
            ready=item.ready,
            reason_code=item.reason_code,
            satisfied=list(item.satisfied),
            issues=[DependencyIssueResponse(**issue.to_dict()) for issue in item.issues],
            checked_against_generation=item.checked_against_generation,
        )
        for item in results
    ]
    ready_count = sum(1 for item in payload if item.ready)
    return ResolveCapabilitiesResponse(
        write_generation=snapshot.generation,
        results=payload,
        ready_count=ready_count,
        blocked_count=len(payload) - ready_count,
    )


@router.post(
    "/route",
    response_model=TaskRouteDecisionResponse,
    responses={**AUTH_RESPONSE},
    summary="Compute a task-aware model routing decision",
    operation_id="routeTaskModel",
)
def route_task_model(request: TaskRouteRequest) -> TaskRouteDecisionResponse:
    from src.config import Config

    service = get_capability_write_service()
    try:
        snapshot = service.list_entries(include_retired=False)
    except WriteRegistryStoreError as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": exc.error_code, "message": str(exc)},
        ) from exc

    try:
        config = Config()
    except Exception as exc:  # broad-exception: fallback_recorded
        log_safe_exception(
            logger, "Config unavailable for task routing", exc,
            error_code="task_routing_config_unavailable",
        )
        config = None

    try:
        decision = resolve_task_model_route(
            request.task_class,
            config=config,
            write_snapshot=snapshot,
            policy=request.policy,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_task_route_request", "message": str(exc)},
        ) from None

    return TaskRouteDecisionResponse(
        schema_version=decision.schema_version,  # type: ignore[arg-type]
        task_class=decision.task_class,  # type: ignore[arg-type]
        policy=decision.policy,  # type: ignore[arg-type]
        selected_model=decision.selected_model,
        selected_capability_id=decision.selected_capability_id,
        reason_code=decision.reason_code,
        explain=list(decision.explain),
        candidates=[RouteCandidateResponse(**item.to_dict()) for item in decision.candidates],
        pin_source=decision.pin_source,
        fallback_used=decision.fallback_used,
        routing_enabled=decision.routing_enabled,
        as_of=decision.as_of,
    )
