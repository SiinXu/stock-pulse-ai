# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Watchlist group organization endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_system_config_service
from api.v1.endpoints.stocks import _read_watchlist_codes, _validate_and_normalize_stock_code
from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.watchlist_groups import (
    WatchlistGroupCreateRequest,
    WatchlistGroupMemberAddRequest,
    WatchlistGroupMemberMoveRequest,
    WatchlistGroupMemberReorderRequest,
    WatchlistGroupRenameRequest,
    WatchlistGroupReorderRequest,
    WatchlistGroupsResponse,
)
from src.services.system_config_service import SystemConfigService
from src.services.watchlist_group_service import (
    WatchlistGroupNotFoundError,
    WatchlistGroupService,
    WatchlistGroupServiceError,
    group_views_to_payload,
)
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

router = APIRouter()


def get_watchlist_group_service() -> WatchlistGroupService:
    return WatchlistGroupService()


def _response(groups, message: str) -> WatchlistGroupsResponse:
    return WatchlistGroupsResponse(
        groups=group_views_to_payload(groups),
        message=message,
    )


def _http_from_service_error(exc: WatchlistGroupServiceError) -> HTTPException:
    status = 404 if isinstance(exc, WatchlistGroupNotFoundError) else 400
    return HTTPException(
        status_code=status,
        detail={"error": exc.error_code, "message": str(exc)},
    )


@router.get(
    "/watchlist/groups",
    response_model=WatchlistGroupsResponse,
    responses={
        200: {"description": "Watchlist groups"},
        500: {"description": "Server error", "model": ErrorResponse},
    },
    summary="List watchlist groups",
    description=(
        "Return organized watchlist groups. On first access, existing STOCK_LIST "
        "symbols are seeded into the default group without loss."
    ),
)
def list_watchlist_groups(
    service: SystemConfigService = Depends(get_system_config_service),
    group_service: WatchlistGroupService = Depends(get_watchlist_group_service),
) -> WatchlistGroupsResponse:
    try:
        codes = _read_watchlist_codes(service)
        groups = group_service.list_groups(stock_list_codes=codes)
        return _response(groups, f"{len(groups)} groups")
    except Exception as exc:
        log_safe_exception(
            logger,
            "Watchlist groups list failed",
            exc,
            error_code="internal_error",
        )
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"Failed to list groups: {exc}"},
        ) from exc


@router.post(
    "/watchlist/groups",
    response_model=WatchlistGroupsResponse,
    responses={
        200: {"description": "Group created"},
        400: {"description": "Validation error", "model": ErrorResponse},
        500: {"description": "Server error", "model": ErrorResponse},
    },
    summary="Create a watchlist group",
)
def create_watchlist_group(
    request: WatchlistGroupCreateRequest,
    service: SystemConfigService = Depends(get_system_config_service),
    group_service: WatchlistGroupService = Depends(get_watchlist_group_service),
) -> WatchlistGroupsResponse:
    try:
        group_service.create_group(name=request.name)
        codes = _read_watchlist_codes(service)
        groups = group_service.list_groups(stock_list_codes=codes)
        return _response(groups, f"Created group {request.name.strip()}")
    except WatchlistGroupServiceError as exc:
        raise _http_from_service_error(exc) from exc
    except Exception as exc:
        log_safe_exception(
            logger,
            "Watchlist group create failed",
            exc,
            error_code="internal_error",
        )
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"Failed to create group: {exc}"},
        ) from exc


@router.patch(
    "/watchlist/groups/{group_id}",
    response_model=WatchlistGroupsResponse,
    responses={
        200: {"description": "Group renamed"},
        400: {"description": "Validation error", "model": ErrorResponse},
        404: {"description": "Not found", "model": ErrorResponse},
        500: {"description": "Server error", "model": ErrorResponse},
    },
    summary="Rename a watchlist group",
)
def rename_watchlist_group(
    group_id: str,
    request: WatchlistGroupRenameRequest,
    service: SystemConfigService = Depends(get_system_config_service),
    group_service: WatchlistGroupService = Depends(get_watchlist_group_service),
) -> WatchlistGroupsResponse:
    try:
        group_service.rename_group(group_id=group_id, name=request.name)
        codes = _read_watchlist_codes(service)
        groups = group_service.list_groups(stock_list_codes=codes)
        return _response(groups, f"Renamed group {group_id}")
    except WatchlistGroupServiceError as exc:
        raise _http_from_service_error(exc) from exc
    except Exception as exc:
        log_safe_exception(
            logger,
            "Watchlist group rename failed",
            exc,
            error_code="internal_error",
            context={"group_id": group_id},
        )
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"Failed to rename group: {exc}"},
        ) from exc


@router.delete(
    "/watchlist/groups/{group_id}",
    response_model=WatchlistGroupsResponse,
    responses={
        200: {"description": "Group deleted"},
        400: {"description": "Validation error", "model": ErrorResponse},
        404: {"description": "Not found", "model": ErrorResponse},
        500: {"description": "Server error", "model": ErrorResponse},
    },
    summary="Delete a watchlist group",
    description="Default group cannot be deleted. Exclusive members are moved to Default.",
)
def delete_watchlist_group(
    group_id: str,
    service: SystemConfigService = Depends(get_system_config_service),
    group_service: WatchlistGroupService = Depends(get_watchlist_group_service),
) -> WatchlistGroupsResponse:
    try:
        group_service.delete_group(group_id=group_id)
        codes = _read_watchlist_codes(service)
        groups = group_service.list_groups(stock_list_codes=codes)
        return _response(groups, f"Deleted group {group_id}")
    except WatchlistGroupServiceError as exc:
        raise _http_from_service_error(exc) from exc
    except Exception as exc:
        log_safe_exception(
            logger,
            "Watchlist group delete failed",
            exc,
            error_code="internal_error",
            context={"group_id": group_id},
        )
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"Failed to delete group: {exc}"},
        ) from exc


@router.put(
    "/watchlist/groups/reorder",
    response_model=WatchlistGroupsResponse,
    responses={
        200: {"description": "Groups reordered"},
        400: {"description": "Validation error", "model": ErrorResponse},
        500: {"description": "Server error", "model": ErrorResponse},
    },
    summary="Reorder watchlist groups",
)
def reorder_watchlist_groups(
    request: WatchlistGroupReorderRequest,
    service: SystemConfigService = Depends(get_system_config_service),
    group_service: WatchlistGroupService = Depends(get_watchlist_group_service),
) -> WatchlistGroupsResponse:
    try:
        group_service.reorder_groups(ordered_ids=request.ordered_ids)
        codes = _read_watchlist_codes(service)
        groups = group_service.list_groups(stock_list_codes=codes)
        return _response(groups, "Groups reordered")
    except WatchlistGroupServiceError as exc:
        raise _http_from_service_error(exc) from exc
    except Exception as exc:
        log_safe_exception(
            logger,
            "Watchlist group reorder failed",
            exc,
            error_code="internal_error",
        )
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"Failed to reorder groups: {exc}"},
        ) from exc


@router.post(
    "/watchlist/groups/{group_id}/members",
    response_model=WatchlistGroupsResponse,
    responses={
        200: {"description": "Member added"},
        400: {"description": "Validation error", "model": ErrorResponse},
        404: {"description": "Not found", "model": ErrorResponse},
        500: {"description": "Server error", "model": ErrorResponse},
    },
    summary="Add a symbol to a group",
    description="Supports multi-group membership. Does not remove the symbol from other groups.",
)
def add_watchlist_group_member(
    group_id: str,
    request: WatchlistGroupMemberAddRequest,
    service: SystemConfigService = Depends(get_system_config_service),
    group_service: WatchlistGroupService = Depends(get_watchlist_group_service),
) -> WatchlistGroupsResponse:
    try:
        validated = _validate_and_normalize_stock_code(request.stock_code)
        # Keep the user-facing code when possible; validated form is for safety checks.
        display_code = request.stock_code.strip() or validated
        group_service.add_member(
            group_id=group_id,
            stock_code=display_code,
            attrs=request.attrs,
        )
        # Ensure STOCK_LIST stays the global membership authority.
        codes = _read_watchlist_codes(service)
        from api.v1.endpoints.stocks import _watchlist_match_key, _write_watchlist_codes

        existing_keys = [_watchlist_match_key(code) for code in codes]
        if _watchlist_match_key(validated) not in existing_keys:
            codes.append(display_code)
            _write_watchlist_codes(service, codes)
        groups = group_service.list_groups(stock_list_codes=codes)
        return _response(groups, f"Added {display_code} to group {group_id}")
    except HTTPException:
        raise
    except WatchlistGroupServiceError as exc:
        raise _http_from_service_error(exc) from exc
    except Exception as exc:
        log_safe_exception(
            logger,
            "Watchlist group member add failed",
            exc,
            error_code="internal_error",
            context={"group_id": group_id},
        )
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"Failed to add member: {exc}"},
        ) from exc


@router.delete(
    "/watchlist/groups/{group_id}/members/{stock_code}",
    response_model=WatchlistGroupsResponse,
    responses={
        200: {"description": "Member removed from group"},
        404: {"description": "Not found", "model": ErrorResponse},
        500: {"description": "Server error", "model": ErrorResponse},
    },
    summary="Remove a symbol from a group",
    description=(
        "Removes membership from one group only. If the symbol would become ungrouped, "
        "it is re-homed into the default group. Use the global watchlist remove endpoint "
        "to drop a symbol from STOCK_LIST entirely."
    ),
)
def remove_watchlist_group_member(
    group_id: str,
    stock_code: str,
    service: SystemConfigService = Depends(get_system_config_service),
    group_service: WatchlistGroupService = Depends(get_watchlist_group_service),
) -> WatchlistGroupsResponse:
    try:
        group_service.remove_member(group_id=group_id, stock_code=stock_code.strip())
        codes = _read_watchlist_codes(service)
        groups = group_service.list_groups(stock_list_codes=codes)
        return _response(groups, f"Removed {stock_code} from group {group_id}")
    except WatchlistGroupServiceError as exc:
        raise _http_from_service_error(exc) from exc
    except Exception as exc:
        log_safe_exception(
            logger,
            "Watchlist group member remove failed",
            exc,
            error_code="internal_error",
            context={"group_id": group_id, "stock_code": stock_code},
        )
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"Failed to remove member: {exc}"},
        ) from exc


@router.put(
    "/watchlist/groups/{group_id}/members/reorder",
    response_model=WatchlistGroupsResponse,
    responses={
        200: {"description": "Members reordered"},
        404: {"description": "Not found", "model": ErrorResponse},
        500: {"description": "Server error", "model": ErrorResponse},
    },
    summary="Reorder symbols inside a group",
)
def reorder_watchlist_group_members(
    group_id: str,
    request: WatchlistGroupMemberReorderRequest,
    service: SystemConfigService = Depends(get_system_config_service),
    group_service: WatchlistGroupService = Depends(get_watchlist_group_service),
) -> WatchlistGroupsResponse:
    try:
        group_service.reorder_members(
            group_id=group_id,
            ordered_codes=request.ordered_codes,
        )
        codes = _read_watchlist_codes(service)
        groups = group_service.list_groups(stock_list_codes=codes)
        return _response(groups, f"Reordered members in group {group_id}")
    except WatchlistGroupServiceError as exc:
        raise _http_from_service_error(exc) from exc
    except Exception as exc:
        log_safe_exception(
            logger,
            "Watchlist group member reorder failed",
            exc,
            error_code="internal_error",
            context={"group_id": group_id},
        )
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"Failed to reorder members: {exc}"},
        ) from exc


@router.post(
    "/watchlist/groups/move-member",
    response_model=WatchlistGroupsResponse,
    responses={
        200: {"description": "Member moved or copied"},
        400: {"description": "Validation error", "model": ErrorResponse},
        404: {"description": "Not found", "model": ErrorResponse},
        500: {"description": "Server error", "model": ErrorResponse},
    },
    summary="Move or copy a symbol between groups",
    description="Desktop drag-and-drop and mobile Move-to actions share this endpoint.",
)
def move_watchlist_group_member(
    request: WatchlistGroupMemberMoveRequest,
    service: SystemConfigService = Depends(get_system_config_service),
    group_service: WatchlistGroupService = Depends(get_watchlist_group_service),
) -> WatchlistGroupsResponse:
    try:
        group_service.move_member(
            stock_code=request.stock_code.strip(),
            source_group_id=request.source_group_id,
            target_group_id=request.target_group_id,
            target_index=request.target_index,
            copy=bool(request.copy_membership),
        )
        codes = _read_watchlist_codes(service)
        groups = group_service.list_groups(stock_list_codes=codes)
        action = "Copied" if request.copy_membership else "Moved"
        return _response(
            groups,
            f"{action} {request.stock_code} to group {request.target_group_id}",
        )
    except WatchlistGroupServiceError as exc:
        raise _http_from_service_error(exc) from exc
    except Exception as exc:
        log_safe_exception(
            logger,
            "Watchlist group member move failed",
            exc,
            error_code="internal_error",
        )
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_error", "message": f"Failed to move member: {exc}"},
        ) from exc
