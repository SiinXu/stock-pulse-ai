# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Plugin lifecycle controls: list, enable/disable, and basic hot-reload."""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, HTTPException, Security
from fastapi.security import APIKeyCookie

from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.plugins import (
    PluginHealthEntryResponse,
    PluginHealthResponse,
    PluginInfo,
    PluginLifecycleRequest,
    PluginLifecycleResponse,
    PluginListResponse,
)
from src.auth import COOKIE_NAME, is_auth_enabled
from src.plugins import (
    PluginLifecycleAuditCompletionUnavailable,
    PluginManager,
    PluginSnapshot,
)
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
    401: {
        "model": ErrorResponse,
        "description": "Login required when ADMIN_AUTH_ENABLED=true",
    },
}


def _plugin_manager() -> PluginManager:
    from src.application_services import get_application_services

    return get_application_services().plugin_manager


def _plugin_lifecycle_actor_id() -> str:
    """Return the attributable operator class for the single-admin model."""

    if os.getenv("DSA_DESKTOP_MODE") == "true":
        return "desktop_operator"
    if is_auth_enabled():
        return "authenticated_admin"
    return "local_operator"


def _to_info(snapshot: PluginSnapshot) -> PluginInfo:
    return PluginInfo(
        id=snapshot.manifest.id,
        name=snapshot.manifest.name,
        version=snapshot.manifest.version,
        source=snapshot.source,
        state=snapshot.state,
        desired_enabled=snapshot.desired_enabled,
        reloadable=snapshot.reloadable,
        package_root=snapshot.package_root,
        extension_points=list(snapshot.extension_points),
        description=snapshot.manifest.description,
        author=snapshot.manifest.author,
        last_error_code=snapshot.last_error_code,
    )


@router.get(
    "",
    response_model=PluginListResponse,
    responses={**AUTH_RESPONSE},
    summary="List registered plugins and lifecycle state",
    description=(
        "Return every plugin registered on the process composition root, including "
        "runtime state, last failure codes, and persisted desired_enabled intent. "
        "PLUG-02 UI and loaded-extensions consumers use this list."
    ),
    operation_id="listPlugins",
)
def list_plugins() -> PluginListResponse:
    manager = _plugin_manager()
    items = [_to_info(snapshot) for snapshot in manager.list_snapshots()]
    return PluginListResponse(items=items, total=len(items))


@router.get(
    "/health",
    response_model=PluginHealthResponse,
    responses={**AUTH_RESPONSE},
    summary="Read-only plugin health snapshot",
    description=(
        "Return each registered plugin's load state, extension points, and last "
        "stable failure code. Backs operator diagnostics and the loaded-extensions "
        "panel without introducing a new API version surface."
    ),
    operation_id="getPluginHealth",
)
def get_plugin_health() -> PluginHealthResponse:
    report = _plugin_manager().health_check()
    return PluginHealthResponse(
        generated_at=report.generated_at,
        total=report.total,
        plugins=[
            PluginHealthEntryResponse(
                plugin_id=entry.plugin_id,
                name=entry.name,
                version=entry.version,
                source=entry.source,
                state=entry.state,
                desired_enabled=entry.desired_enabled,
                extension_points=list(entry.extension_points),
                last_error_code=entry.last_error_code,
                package_root=entry.package_root,
                reloadable=entry.reloadable,
            )
            for entry in report.plugins
        ],
    )


@router.post(
    "/{plugin_id}/lifecycle",
    response_model=PluginLifecycleResponse,
    responses={
        **AUTH_RESPONSE,
        404: {"model": ErrorResponse, "description": "Plugin not found"},
        400: {"model": ErrorResponse, "description": "Invalid lifecycle request"},
        500: {"model": ErrorResponse, "description": "Lifecycle operation failed unexpectedly"},
        503: {"model": ErrorResponse, "description": "Security audit storage unavailable"},
    },
    summary="Enable, disable, or hot-reload one plugin",
    description=(
        "Toggle persisted enable/disable intent and apply it immediately, or attempt "
        "in-process hot-reload for an external plugin. Built-in plugins return "
        "restart_required=true for reload. Disabled plugins are never loaded or invoked."
    ),
    operation_id="updatePluginLifecycle",
)
def update_plugin_lifecycle(
    plugin_id: str,
    request: PluginLifecycleRequest,
) -> PluginLifecycleResponse:
    manager = _plugin_manager()
    if manager.snapshot(plugin_id) is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "plugin_not_found",
                "message": f"Plugin {plugin_id!r} is not registered",
            },
        )
    try:
        audit_fields = {
            "require_audit": True,
            "actor_type": "administrator",
            "actor_id": _plugin_lifecycle_actor_id(),
        }
        if request.action == "enable":
            result = manager.set_enabled(plugin_id, True, **audit_fields)
            snapshot = manager.snapshot(plugin_id)
            return PluginLifecycleResponse(
                plugin_id=plugin_id,
                action=request.action,
                success=result.success,
                state=result.state,
                reloaded=False,
                restart_required=False,
                error_code=result.error_code,
                message=(
                    "Plugin enabled"
                    if result.success
                    else (result.error_code or "enable failed")
                ),
                plugin=None if snapshot is None else _to_info(snapshot),
            )
        if request.action == "disable":
            result = manager.set_enabled(plugin_id, False, **audit_fields)
            snapshot = manager.snapshot(plugin_id)
            return PluginLifecycleResponse(
                plugin_id=plugin_id,
                action=request.action,
                success=result.success,
                state=result.state,
                reloaded=False,
                restart_required=False,
                error_code=result.error_code,
                message=(
                    "Plugin disabled; will not be loaded or invoked"
                    if result.success
                    else (result.error_code or "disable failed")
                ),
                plugin=None if snapshot is None else _to_info(snapshot),
            )
        # reload
        reload_result = manager.reload(plugin_id, **audit_fields)
        snapshot = manager.snapshot(plugin_id)
        return PluginLifecycleResponse(
            plugin_id=plugin_id,
            action=request.action,
            success=reload_result.success,
            state=reload_result.state,
            reloaded=reload_result.reloaded,
            restart_required=reload_result.restart_required,
            error_code=reload_result.error_code,
            message=reload_result.message,
            plugin=None if snapshot is None else _to_info(snapshot),
        )
    except PluginLifecycleAuditCompletionUnavailable as exc:
        result = exc.result
        detail = {
            "error": "security_audit_unavailable",
            "message": (
                "Plugin lifecycle operation completed, but its audit completion "
                "could not be persisted"
            ),
            "operation_completed": True,
            "operation_success": result.success,
            "state": result.state,
        }
        if hasattr(result, "reloaded"):
            detail["reloaded"] = result.reloaded
        raise HTTPException(status_code=503, detail=detail) from None
    except SecurityAuditUnavailable:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "security_audit_unavailable",
                "message": "Security audit storage is unavailable",
                "operation_completed": False,
            },
        ) from None
    except HTTPException:
        raise
    except Exception as exc:  # broad-exception: fallback_recorded - map unexpected lifecycle failures to a sanitized API error
        log_safe_exception(
            logger,
            "Plugin lifecycle operation failed",
            exc,
            error_code="plugin_lifecycle_failed",
            context={"plugin_id": plugin_id, "action": request.action},
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "plugin_lifecycle_failed",
                "message": "Plugin lifecycle operation failed",
            },
        ) from exc
