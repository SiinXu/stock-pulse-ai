# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Application contract for revisioned watchlist-group organization."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import timezone
import json
from typing import Any, Dict, List, Optional, Sequence
from uuid import uuid4

from src.repositories.base import RepositoryError
from src.repositories.watchlist_group_repo import (
    DEFAULT_GROUP_KEY,
    DEFAULT_GROUP_NAME_KEY,
    StoredWatchlistGroup,
    StoredWatchlistGroupMember,
    StoredWatchlistState,
    WatchlistGroupRepository,
)
from src.services.watchlist_identity import watchlist_match_key
from src.storage import DatabaseManager

MAX_GROUP_NAME_LENGTH = 80


class WatchlistGroupServiceError(ValueError):
    error_code = "watchlist_group_error"

    def __init__(self, message: str, *, error_code: Optional[str] = None) -> None:
        super().__init__(message)
        if error_code:
            self.error_code = error_code


class WatchlistGroupNotFoundError(WatchlistGroupServiceError):
    error_code = "watchlist_group_not_found"


class WatchlistGroupConflictError(WatchlistGroupServiceError):
    error_code = "watchlist_group_revision_conflict"

    def __init__(self, message: str, *, current_revision: int) -> None:
        super().__init__(message, error_code=self.error_code)
        self.current_revision = current_revision


@dataclass(frozen=True)
class WatchlistMemberView:
    stock_code: str
    sort_order: int
    attrs: Dict[str, Any]


@dataclass(frozen=True)
class WatchlistGroupView:
    id: str
    name: str
    name_key: Optional[str]
    sort_order: int
    is_default: bool
    created_at: str
    updated_at: str
    members: List[WatchlistMemberView]


@dataclass(frozen=True)
class WatchlistGroupStateView:
    revision: int
    groups: List[WatchlistGroupView]


def _iso(value: Any) -> str:
    if value is None or not hasattr(value, "isoformat"):
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _member_view(member: StoredWatchlistGroupMember) -> WatchlistMemberView:
    return WatchlistMemberView(
        stock_code=member.stock_code,
        sort_order=member.sort_order,
        attrs=dict(member.attrs),
    )


def _group_view(group: StoredWatchlistGroup) -> WatchlistGroupView:
    return WatchlistGroupView(
        id=group.group_key,
        name=group.name,
        name_key=DEFAULT_GROUP_NAME_KEY if group.is_default else None,
        sort_order=group.sort_order,
        is_default=bool(group.is_default),
        created_at=_iso(group.created_at),
        updated_at=_iso(group.updated_at),
        members=[_member_view(item) for item in group.members],
    )


def _state_view(state: StoredWatchlistState) -> WatchlistGroupStateView:
    return WatchlistGroupStateView(
        revision=state.revision,
        groups=[_group_view(group) for group in state.groups],
    )


def group_state_to_payload(state: WatchlistGroupStateView) -> Dict[str, Any]:
    payload = asdict(state)
    json.dumps(payload, ensure_ascii=False, allow_nan=False)
    return payload


def group_views_to_payload(groups: Sequence[WatchlistGroupView]) -> List[Dict[str, Any]]:
    payload = [asdict(group) for group in groups]
    json.dumps(payload, ensure_ascii=False, allow_nan=False)
    return payload


def _translate_repo_error(exc: RepositoryError) -> WatchlistGroupServiceError:
    code = exc.error_code
    if code == "watchlist_group_revision_conflict":
        return WatchlistGroupConflictError(
            "Watchlist groups changed; refresh and retry",
            current_revision=int(exc.context.get("current_revision", 1)),
        )
    if code in {"watchlist_group_not_found", "watchlist_group_member_not_found"}:
        return WatchlistGroupNotFoundError("Watchlist group or member was not found", error_code=code)
    if code in {
        "watchlist_group_reorder_invalid",
        "watchlist_group_member_reorder_invalid",
        "watchlist_group_default_delete_forbidden",
        "watchlist_group_limit_reached",
        "watchlist_group_member_limit_reached",
    }:
        return WatchlistGroupServiceError(str(exc), error_code=code)
    return WatchlistGroupServiceError("Watchlist group operation failed", error_code=code)


class WatchlistGroupService:
    """Coordinates the authoritative STOCK_LIST projection and group aggregate."""

    def __init__(
        self,
        db_manager: Optional[DatabaseManager] = None,
        repo: Optional[WatchlistGroupRepository] = None,
    ) -> None:
        self.repo = repo or WatchlistGroupRepository(db_manager)

    def list_state(self, *, stock_list_codes: Sequence[str]) -> WatchlistGroupStateView:
        try:
            return _state_view(self.repo.reconcile(stock_list_codes=stock_list_codes))
        except RepositoryError as exc:
            raise _translate_repo_error(exc) from exc

    def list_groups(self, *, stock_list_codes: Sequence[str]) -> List[WatchlistGroupView]:
        return self.list_state(stock_list_codes=stock_list_codes).groups

    @staticmethod
    def _name(name: str) -> str:
        cleaned = str(name or "").strip()
        if not cleaned:
            raise WatchlistGroupServiceError(
                "Group name is required", error_code="watchlist_group_name_required"
            )
        if len(cleaned) > MAX_GROUP_NAME_LENGTH:
            raise WatchlistGroupServiceError(
                "Group name is too long", error_code="watchlist_group_name_too_long"
            )
        return cleaned

    @staticmethod
    def _revision(expected_revision: int) -> int:
        if type(expected_revision) is not int or expected_revision < 1:
            raise WatchlistGroupServiceError(
                "expected_revision must be a positive integer",
                error_code="watchlist_group_revision_invalid",
            )
        return expected_revision

    def create_group(self, *, name: str, expected_revision: int) -> WatchlistGroupStateView:
        try:
            return _state_view(
                self.repo.create_group(
                    group_key=f"g_{uuid4().hex[:12]}",
                    name=self._name(name),
                    expected_revision=self._revision(expected_revision),
                )
            )
        except RepositoryError as exc:
            raise _translate_repo_error(exc) from exc

    def rename_group(self, *, group_id: str, name: str, expected_revision: int) -> WatchlistGroupStateView:
        try:
            return _state_view(
                self.repo.rename_group(
                    group_key=group_id,
                    name=self._name(name),
                    expected_revision=self._revision(expected_revision),
                )
            )
        except RepositoryError as exc:
            raise _translate_repo_error(exc) from exc

    def delete_group(self, *, group_id: str, expected_revision: int) -> WatchlistGroupStateView:
        try:
            return _state_view(
                self.repo.delete_group(
                    group_key=group_id,
                    expected_revision=self._revision(expected_revision),
                )
            )
        except RepositoryError as exc:
            raise _translate_repo_error(exc) from exc

    def reorder_groups(
        self, *, ordered_ids: Sequence[str], expected_revision: int
    ) -> WatchlistGroupStateView:
        try:
            return _state_view(
                self.repo.reorder_groups(
                    ordered_keys=ordered_ids,
                    expected_revision=self._revision(expected_revision),
                )
            )
        except RepositoryError as exc:
            raise _translate_repo_error(exc) from exc

    def add_member(
        self, *, group_id: str, stock_code: str, expected_revision: int
    ) -> WatchlistGroupStateView:
        identity = watchlist_match_key(stock_code)
        if not identity:
            raise WatchlistGroupServiceError(
                "Stock code is required", error_code="watchlist_group_member_code_required"
            )
        try:
            return _state_view(
                self.repo.add_member(
                    group_key=group_id,
                    stock_code=identity,
                    expected_revision=self._revision(expected_revision),
                )
            )
        except RepositoryError as exc:
            raise _translate_repo_error(exc) from exc

    def remove_member(
        self, *, group_id: str, stock_code: str, expected_revision: int
    ) -> WatchlistGroupStateView:
        try:
            return _state_view(
                self.repo.remove_member(
                    group_key=group_id,
                    stock_code=watchlist_match_key(stock_code),
                    expected_revision=self._revision(expected_revision),
                )
            )
        except RepositoryError as exc:
            raise _translate_repo_error(exc) from exc

    def reorder_members(
        self,
        *,
        group_id: str,
        ordered_codes: Sequence[str],
        expected_revision: int,
    ) -> WatchlistGroupStateView:
        try:
            return _state_view(
                self.repo.reorder_members(
                    group_key=group_id,
                    ordered_codes=ordered_codes,
                    expected_revision=self._revision(expected_revision),
                )
            )
        except RepositoryError as exc:
            raise _translate_repo_error(exc) from exc

    def move_member(
        self,
        *,
        stock_code: str,
        source_group_id: str,
        target_group_id: str,
        expected_revision: int,
        target_index: Optional[int] = None,
        copy: bool = False,
    ) -> WatchlistGroupStateView:
        try:
            return _state_view(
                self.repo.move_member(
                    stock_code=watchlist_match_key(stock_code),
                    source_group_key=source_group_id,
                    target_group_key=target_group_id,
                    target_index=target_index,
                    copy=copy,
                    expected_revision=self._revision(expected_revision),
                )
            )
        except RepositoryError as exc:
            raise _translate_repo_error(exc) from exc


__all__ = [
    "WatchlistGroupConflictError",
    "WatchlistGroupNotFoundError",
    "WatchlistGroupService",
    "WatchlistGroupServiceError",
    "WatchlistGroupStateView",
    "group_state_to_payload",
    "group_views_to_payload",
]
