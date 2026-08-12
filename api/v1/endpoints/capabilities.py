# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Capability inventory (read-only) and write-side registry endpoints.

GET "" remains a pure live-owner inventory. Write-side register/update/retire,
dependency resolution, and task-aware routing live under /registry and /route
so inventory contracts stay additive-compatible.
"""

from __future__ import annotations

import logging
import os
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request, Security
from fastapi.security import APIKeyCookie

from api.v1.schemas.capabilities import (
    CapabilityItem,
    CapabilityListResponse,
    CapabilityResolveRequest,
    CapabilityResolveResponse,
    DataCapabilityItem,
    DependencyIssueResponse,
    ExtensionCapabilityItem,
    PipelineCapabilityItem,
    ResolutionResultResponse,
    RouteCandidateResponse,
    SkillCapabilityItem,
    TaskRouteRequest,
    TaskRouteResponse,
    ToolCapabilityItem,
    WriteCapabilityEntryResponse,
    WriteCapabilityListResponse,
    WriteCapabilityRegisterRequest,
    WriteCapabilityUpdateRequest,
)
from api.v1.schemas.common import ErrorResponse
from src.auth import COOKIE_NAME, is_auth_enabled, verify_session
from src.capability_registry import (
    CapabilityRecord,
    CapabilityWriteError,
    collect_capability_records,
    decision_for_diagnostics,
    get_capability_write_service,
    resolve_many,
    resolve_task_model_route,
)
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
    400: {"model": ErrorResponse, "description": "Invalid domain filter"},
}

WRITE_AUTH_RESPONSE = {
    **AUTH_RESPONSE,
    403: {"model": ErrorResponse, "description": "Write denied"},
    404: {"model": ErrorResponse, "description": "Capability not found"},
    409: {"model": ErrorResponse, "description": "Capability already exists"},
    503: {"model": ErrorResponse, "description": "Security audit unavailable"},
}


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
        domain=entry.domain,
        capability_type=entry.capability_type,
        version=entry.version,
        status=entry.status,
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


def _capability_write_actor_id() -> str:
    if os.getenv("DSA_DESKTOP_MODE") == "true":
        return "desktop_operator"
    if is_auth_enabled():
        return "authenticated_admin"
    return "local_operator"


def _require_write_access(
    request: Request,
    *,
    operation: str,
    capability_id: str,
) -> None:
    """Reject unauthorized writes with a durable denied audit trail."""

    if not is_auth_enabled():
        return
    session_cookie = request.cookies.get(COOKIE_NAME)
    if session_cookie and verify_session(session_cookie):
        return

    service = get_capability_write_service()
    try:
        service.auditor.record_denied(
            capability_id=capability_id or "unknown",
            operation=operation,
            reason_code="capability_write_unauthorized",
            metadata={"path": str(request.url.path)[:128]},
            actor_type="anonymous",
            actor_id="unauthenticated",
        )
    except SecurityAuditUnavailable:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "security_audit_unavailable",
                "message": "Security audit storage is unavailable",
                "operation_completed": False,
            },
        ) from None
    except Exception as exc:  # broad-exception: fallback_recorded - still deny
        log_safe_exception(
            logger,
            "Capability write denied-audit failed",
            exc,
            error_code="capability_write_denied_audit_failed",
        )
    raise HTTPException(
        status_code=401,
        detail={
            "error": "unauthorized",
            "message": "Administrator authentication required for capability writes",
        },
    )


def _http_from_write_error(exc: CapabilityWriteError) -> HTTPException:
    status = {
        "capability_already_exists": 409,
        "capability_not_found": 404,
        "capability_retired": 400,
        "capability_identity_immutable": 400,
        "capability_validation_failed": 400,
        "write_registry_corrupt": 500,
        "write_registry_unreadable": 500,
        "write_registry_too_large": 500,
        "write_registry_persist_failed": 500,
        "write_registry_schema_unsupported": 500,
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
        "Capture a versioned read-only inventory from the live data-provider, "
        "tool, plugin, skill, and pipeline owners. Availability comes only from "
        "runtime registration and owner health state, never from a static "
        "catalog. Unknown readiness remains null. Source or config read "
        "failures are returned explicitly with partial=true; this endpoint does "
        "not register, resolve, grant, execute, or perform side-effecting "
        "health checks."
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


@router.get(
    "/registry",
    response_model=WriteCapabilityListResponse,
    responses={**AUTH_RESPONSE},
    summary="List write-side capability declarations",
    description=(
        "Return operator-declared capability entries from the durable write "
        "registry. This is independent of the live-owner inventory."
    ),
    operation_id="listCapabilityWriteRegistry",
)
def list_write_registry(
    domain: Optional[str] = Query(default=None),
    include_retired: bool = Query(default=True),
) -> WriteCapabilityListResponse:
    service = get_capability_write_service()
    try:
        snapshot = service.list_entries(
            domain=domain,
            include_retired=include_retired,
        )
    except WriteRegistryStoreError as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": exc.error_code, "message": str(exc)},
        ) from exc
    entries = [_write_entry_response(item) for item in snapshot.entries]
    return WriteCapabilityListResponse(
        schema_version=snapshot.schema_version,  # type: ignore[arg-type]
        generation=snapshot.generation,
        as_of=snapshot.as_of or "unknown",
        entries=entries,
        total=len(entries),
    )


@router.post(
    "/registry",
    response_model=WriteCapabilityEntryResponse,
    responses={**WRITE_AUTH_RESPONSE},
    summary="Register a write-side capability",
    description=(
        "Create a new operator-declared capability. Failures are explicit and "
        "never pollute the read-only inventory snapshot. Privileged writes "
        "require the security-audit chain."
    ),
    operation_id="registerCapability",
)
def register_capability(
    request: Request,
    body: WriteCapabilityRegisterRequest,
) -> WriteCapabilityEntryResponse:
    _require_write_access(
        request, operation="register", capability_id=body.capability_id
    )
    service = get_capability_write_service()
    payload = body.model_dump()
    if not payload.get("provider"):
        payload["provider"] = body.capability_id
    try:
        entry = service.register(
            payload,
            actor_type="administrator",
            actor_id=_capability_write_actor_id(),
        )
    except CapabilityWriteError as exc:
        raise _http_from_write_error(exc) from None
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
    responses={**WRITE_AUTH_RESPONSE},
    summary="Update a write-side capability",
    operation_id="updateCapability",
)
def update_capability(
    request: Request,
    capability_id: str,
    body: WriteCapabilityUpdateRequest,
) -> WriteCapabilityEntryResponse:
    _require_write_access(
        request, operation="update", capability_id=capability_id
    )
    service = get_capability_write_service()
    payload = {
        key: value
        for key, value in body.model_dump(exclude_unset=True).items()
        if value is not None
    }
    try:
        entry = service.update(
            capability_id,
            payload,
            actor_type="administrator",
            actor_id=_capability_write_actor_id(),
        )
    except CapabilityWriteError as exc:
        raise _http_from_write_error(exc) from None
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
    responses={**WRITE_AUTH_RESPONSE},
    summary="Retire a write-side capability",
    description=(
        "Mark a capability retired so task-aware routing and resolution no "
        "longer treat it as active. Idempotent for already-retired ids."
    ),
    operation_id="retireCapability",
)
def retire_capability(
    request: Request,
    capability_id: str,
) -> WriteCapabilityEntryResponse:
    _require_write_access(
        request, operation="retire", capability_id=capability_id
    )
    service = get_capability_write_service()
    try:
        entry = service.retire(
            capability_id,
            actor_type="administrator",
            actor_id=_capability_write_actor_id(),
        )
    except CapabilityWriteError as exc:
        raise _http_from_write_error(exc) from None
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
    "/registry/resolve",
    response_model=CapabilityResolveResponse,
    responses={**AUTH_RESPONSE, 400: {"model": ErrorResponse}},
    summary="Resolve capability dependencies and version compatibility",
    operation_id="resolveCapabilityDependencies",
)
def resolve_capabilities(
    body: CapabilityResolveRequest,
) -> CapabilityResolveResponse:
    service = get_capability_write_service()
    try:
        write_snapshot = service.list_entries(include_retired=True)
    except WriteRegistryStoreError as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": exc.error_code, "message": str(exc)},
        ) from exc

    inventory_items: Any = None
    if body.include_inventory:
        try:
            inventory_items = collect_capability_records().items
        except Exception as exc:  # broad-exception: fallback_recorded - resolve without inventory
            log_safe_exception(
                logger,
                "Inventory unavailable during capability resolve",
                exc,
                error_code="capability_resolve_inventory_unavailable",
            )
            inventory_items = ()

    try:
        results = resolve_many(
            body.capability_ids,
            write_snapshot=write_snapshot,
            inventory_items=inventory_items,
            active_only=body.active_only,
        )
    except Exception as exc:
        if getattr(exc, "error_code", None) == "empty_capability_set":
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "empty_capability_set",
                    "message": str(exc),
                },
            ) from None
        raise

    payload = [
        ResolutionResultResponse(
            capability_id=item.capability_id,
            ready=item.ready,
            reason_code=item.reason_code,
            satisfied=list(item.satisfied),
            issues=[
                DependencyIssueResponse(
                    dependency=issue.dependency,
                    capability_id=issue.capability_id,
                    reason_code=issue.reason_code,
                    detail=issue.detail,
                )
                for issue in item.issues
            ],
            checked_against_generation=item.checked_against_generation,
        )
        for item in results
    ]
    return CapabilityResolveResponse(
        results=payload,
        total=len(payload),
        write_generation=write_snapshot.generation,
    )


@router.post(
    "/route",
    response_model=TaskRouteResponse,
    responses={**AUTH_RESPONSE, 400: {"model": ErrorResponse}},
    summary="Compute an explainable task-aware model route decision",
    description=(
        "Select a model for a task class using write-registry LLM capabilities "
        "and the configured routing policy. Explicit pins win; decisions are "
        "structured for diagnostics reconstruction."
    ),
    operation_id="routeTaskModel",
)
def route_task_model(body: TaskRouteRequest) -> TaskRouteResponse:
    from src.config import Config

    service = get_capability_write_service()
    try:
        write_snapshot = service.list_entries(include_retired=True)
    except WriteRegistryStoreError as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": exc.error_code, "message": str(exc)},
        ) from exc

    try:
        config = Config.get_instance()
    except Exception:  # broad-exception: fallback_recorded - route with no config
        config = None

    try:
        decision = resolve_task_model_route(
            body.task_class,
            config=config,
            write_snapshot=write_snapshot,
            policy=body.policy,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_task_route_request", "message": str(exc)},
        ) from None

    # Attach to current run diagnostics when a context is active.
    try:
        from src.services.run_diagnostics import get_current_diagnostic_context

        ctx = get_current_diagnostic_context()
        if ctx is not None:
            ctx.record_agent_event(
                {
                    "event_type": "task_route_decision",
                    "decision": decision_for_diagnostics(decision),
                }
            )
    except Exception as exc:  # broad-exception: fallback_recorded - route still returns
        log_safe_exception(
            logger,
            "Failed to attach task route decision to diagnostics",
            exc,
            error_code="task_route_diagnostics_attach_failed",
        )

    payload = decision.to_dict()
    return TaskRouteResponse(
        schema_version="task-route-decision/v1",
        task_class=payload["task_class"],  # type: ignore[arg-type]
        policy=payload["policy"],  # type: ignore[arg-type]
        selected_model=payload["selected_model"],
        selected_capability_id=payload["selected_capability_id"],
        reason_code=payload["reason_code"],
        explain=list(payload["explain"]),
        candidates=[
            RouteCandidateResponse(**item) for item in payload["candidates"]
        ],
        pin_source=payload["pin_source"],
        fallback_used=payload["fallback_used"],
        routing_enabled=payload["routing_enabled"],
        as_of=payload["as_of"],
    )
