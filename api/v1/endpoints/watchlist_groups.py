# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Revisioned watchlist-group organization endpoints."""

from __future__ import annotations

import logging
from typing import Callable, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_system_config_service
from api.v1.endpoints.stocks import (
    _read_watchlist_codes,
    _read_watchlist_snapshot,
    _validate_and_normalize_stock_code,
    _watchlist_match_key,
    _write_watchlist_codes,
)
from api.v1.errors import api_error
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
    WatchlistGroupAuthorityChangedError,
    WatchlistGroupConflictError,
    WatchlistGroupNotFoundError,
    WatchlistGroupService,
    WatchlistGroupServiceError,
    WatchlistGroupStateView,
    group_state_to_payload,
)
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)
router = APIRouter()
T = TypeVar("T")

_ERROR_RESPONSES = {
    400: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    500: {"model": ErrorResponse},
}
_AUTHORITY_RECONCILE_ATTEMPTS = 3


def get_watchlist_group_service() -> WatchlistGroupService:
    return WatchlistGroupService()


def _response(state: WatchlistGroupStateView, message: str) -> WatchlistGroupsResponse:
    payload = group_state_to_payload(state)
    return WatchlistGroupsResponse(revision=payload["revision"], groups=payload["groups"], message=message)


def _execute(operation: Callable[[], T], *, log_message: str) -> T:
    try:
        return operation()
    except WatchlistGroupConflictError as exc:
        raise api_error(
            409,
            exc.error_code,
            str(exc),
            params={"current_revision": exc.current_revision},
        ) from exc
    except WatchlistGroupAuthorityChangedError as exc:
        raise api_error(409, exc.error_code, str(exc)) from exc
    except WatchlistGroupNotFoundError as exc:
        raise api_error(404, exc.error_code, str(exc)) from exc
    except WatchlistGroupServiceError as exc:
        raise api_error(400, exc.error_code, str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:  # broad-exception: fallback_recorded - stable public envelope; diagnostics stay in logs.
        log_safe_exception(logger, log_message, exc, error_code="watchlist_group_internal_error")
        raise api_error(500, "internal_error", "Watchlist group operation failed") from exc


@router.get(
    "/watchlist/groups",
    response_model=WatchlistGroupsResponse,
    responses={409: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="List watchlist groups",
    description="Reconcile groups from authoritative STOCK_LIST before returning revisioned state.",
)
def list_watchlist_groups(
    service: SystemConfigService = Depends(get_system_config_service),
    group_service: WatchlistGroupService = Depends(get_watchlist_group_service),
) -> WatchlistGroupsResponse:
    def operation() -> WatchlistGroupsResponse:
        last_error: WatchlistGroupAuthorityChangedError | None = None
        for _attempt in range(_AUTHORITY_RECONCILE_ATTEMPTS):
            codes, authority_version = _read_watchlist_snapshot(service)
            try:
                state = group_service.list_state(
                    stock_list_codes=codes,
                    authority_version=authority_version,
                    authority_version_reader=lambda: _read_watchlist_snapshot(service)[1],
                )
                return _response(state, "Watchlist groups loaded")
            except WatchlistGroupAuthorityChangedError as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        raise WatchlistGroupAuthorityChangedError(
            "Authoritative watchlist changed; retry with a fresh snapshot"
        )

    return _execute(
        operation,
        log_message="Watchlist groups list failed",
    )


@router.post(
    "/watchlist/groups",
    response_model=WatchlistGroupsResponse,
    responses=_ERROR_RESPONSES,
    summary="Create a watchlist group",
)
def create_watchlist_group(
    request: WatchlistGroupCreateRequest,
    group_service: WatchlistGroupService = Depends(get_watchlist_group_service),
) -> WatchlistGroupsResponse:
    return _execute(
        lambda: _response(
            group_service.create_group(
                name=request.name, expected_revision=request.expected_revision
            ),
            "Watchlist group created",
        ),
        log_message="Watchlist group create failed",
    )


@router.patch(
    "/watchlist/groups/{group_id}",
    response_model=WatchlistGroupsResponse,
    responses=_ERROR_RESPONSES,
    summary="Rename a watchlist group",
)
def rename_watchlist_group(
    group_id: str,
    request: WatchlistGroupRenameRequest,
    group_service: WatchlistGroupService = Depends(get_watchlist_group_service),
) -> WatchlistGroupsResponse:
    return _execute(
        lambda: _response(
            group_service.rename_group(
                group_id=group_id,
                name=request.name,
                expected_revision=request.expected_revision,
            ),
            "Watchlist group renamed",
        ),
        log_message="Watchlist group rename failed",
    )


@router.delete(
    "/watchlist/groups/{group_id}",
    response_model=WatchlistGroupsResponse,
    responses=_ERROR_RESPONSES,
    summary="Delete a watchlist group",
)
def delete_watchlist_group(
    group_id: str,
    expected_revision: int = Query(..., ge=1),
    group_service: WatchlistGroupService = Depends(get_watchlist_group_service),
) -> WatchlistGroupsResponse:
    return _execute(
        lambda: _response(
            group_service.delete_group(
                group_id=group_id, expected_revision=expected_revision
            ),
            "Watchlist group deleted",
        ),
        log_message="Watchlist group delete failed",
    )


@router.put(
    "/watchlist/groups/reorder",
    response_model=WatchlistGroupsResponse,
    responses=_ERROR_RESPONSES,
    summary="Atomically reorder every watchlist group",
)
def reorder_watchlist_groups(
    request: WatchlistGroupReorderRequest,
    group_service: WatchlistGroupService = Depends(get_watchlist_group_service),
) -> WatchlistGroupsResponse:
    return _execute(
        lambda: _response(
            group_service.reorder_groups(
                ordered_ids=request.ordered_ids,
                expected_revision=request.expected_revision,
            ),
            "Watchlist groups reordered",
        ),
        log_message="Watchlist group reorder failed",
    )


@router.post(
    "/watchlist/groups/{group_id}/members",
    response_model=WatchlistGroupsResponse,
    responses=_ERROR_RESPONSES,
    summary="Add an authoritative symbol to a group",
)
def add_watchlist_group_member(
    group_id: str,
    request: WatchlistGroupMemberAddRequest,
    service: SystemConfigService = Depends(get_system_config_service),
    group_service: WatchlistGroupService = Depends(get_watchlist_group_service),
) -> WatchlistGroupsResponse:
    def operation() -> WatchlistGroupsResponse:
        validated = _validate_and_normalize_stock_code(request.stock_code)
        identity = _watchlist_match_key(validated)
        codes = _read_watchlist_codes(service)
        if identity not in {_watchlist_match_key(code) for code in codes}:
            # Authority commits first. A later group failure is repaired deterministically
            # into Default by the next reconciliation and remains visible as an error.
            codes.append(identity)
            _write_watchlist_codes(service, codes)
        return _response(
            group_service.add_member(
                group_id=group_id,
                stock_code=identity,
                expected_revision=request.expected_revision,
            ),
            "Watchlist member added",
        )

    return _execute(operation, log_message="Watchlist group member add failed")


@router.delete(
    "/watchlist/groups/{group_id}/members/{stock_code}",
    response_model=WatchlistGroupsResponse,
    responses=_ERROR_RESPONSES,
    summary="Remove a symbol from one group",
)
def remove_watchlist_group_member(
    group_id: str,
    stock_code: str,
    expected_revision: int = Query(..., ge=1),
    group_service: WatchlistGroupService = Depends(get_watchlist_group_service),
) -> WatchlistGroupsResponse:
    return _execute(
        lambda: _response(
            group_service.remove_member(
                group_id=group_id,
                stock_code=stock_code,
                expected_revision=expected_revision,
            ),
            "Watchlist member removed from group",
        ),
        log_message="Watchlist group member remove failed",
    )


@router.put(
    "/watchlist/groups/{group_id}/members/reorder",
    response_model=WatchlistGroupsResponse,
    responses=_ERROR_RESPONSES,
    summary="Atomically reorder every member in one group",
)
def reorder_watchlist_group_members(
    group_id: str,
    request: WatchlistGroupMemberReorderRequest,
    group_service: WatchlistGroupService = Depends(get_watchlist_group_service),
) -> WatchlistGroupsResponse:
    return _execute(
        lambda: _response(
            group_service.reorder_members(
                group_id=group_id,
                ordered_codes=request.ordered_codes,
                expected_revision=request.expected_revision,
            ),
            "Watchlist group members reordered",
        ),
        log_message="Watchlist group member reorder failed",
    )


@router.post(
    "/watchlist/groups/move-member",
    response_model=WatchlistGroupsResponse,
    responses=_ERROR_RESPONSES,
    summary="Move or copy a symbol between groups",
)
def move_watchlist_group_member(
    request: WatchlistGroupMemberMoveRequest,
    group_service: WatchlistGroupService = Depends(get_watchlist_group_service),
) -> WatchlistGroupsResponse:
    return _execute(
        lambda: _response(
            group_service.move_member(
                stock_code=request.stock_code,
                source_group_id=request.source_group_id,
                target_group_id=request.target_group_id,
                target_index=request.target_index,
                copy=request.copy_membership,
                expected_revision=request.expected_revision,
            ),
            "Watchlist member moved",
        ),
        log_message="Watchlist group member move failed",
    )
