# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Watchlist group application service.

Groups organize STOCK_LIST symbols for the Web workspace. STOCK_LIST remains
the authoritative membership set for analysis/alerts. Per-member ``attrs`` is
the mount point for T25 scores and T26 focus flags.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence
from uuid import uuid4

from src.repositories.base import RepositoryError
from src.repositories.watchlist_group_repo import (
    DEFAULT_GROUP_KEY,
    DEFAULT_GROUP_NAME,
    StoredWatchlistGroup,
    StoredWatchlistGroupMember,
    WatchlistGroupRepository,
)
from src.storage import DatabaseManager


class WatchlistGroupServiceError(ValueError):
    """Domain error for watchlist group operations."""

    error_code = "watchlist_group_error"

    def __init__(self, message: str, *, error_code: Optional[str] = None) -> None:
        super().__init__(message)
        if error_code:
            self.error_code = error_code


class WatchlistGroupNotFoundError(WatchlistGroupServiceError):
    error_code = "watchlist_group_not_found"


class WatchlistGroupConflictError(WatchlistGroupServiceError):
    error_code = "watchlist_group_conflict"


@dataclass(frozen=True)
class WatchlistMemberView:
    stock_code: str
    sort_order: int
    attrs: Dict[str, Any]


@dataclass(frozen=True)
class WatchlistGroupView:
    id: str
    name: str
    sort_order: int
    is_default: bool
    created_at: str
    updated_at: str
    members: List[WatchlistMemberView]


def _iso(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _member_view(member: StoredWatchlistGroupMember) -> WatchlistMemberView:
    return WatchlistMemberView(
        stock_code=member.stock_code,
        sort_order=member.sort_order,
        attrs=dict(member.attrs or {}),
    )


def _group_view(group: StoredWatchlistGroup) -> WatchlistGroupView:
    return WatchlistGroupView(
        id=group.group_key,
        name=group.name,
        sort_order=group.sort_order,
        is_default=bool(group.is_default),
        created_at=_iso(group.created_at),
        updated_at=_iso(group.updated_at),
        members=[_member_view(item) for item in group.members],
    )


def group_views_to_payload(groups: Sequence[WatchlistGroupView]) -> List[Dict[str, Any]]:
    return [asdict(group) for group in groups]


class WatchlistGroupService:
    """Coordinates group CRUD, reorder, and STOCK_LIST compatibility seeding."""

    def __init__(
        self,
        db_manager: Optional[DatabaseManager] = None,
        repo: Optional[WatchlistGroupRepository] = None,
    ) -> None:
        self.repo = repo or WatchlistGroupRepository(db_manager)

    def list_groups(
        self,
        *,
        stock_list_codes: Sequence[str],
        default_group_name: str = DEFAULT_GROUP_NAME,
    ) -> List[WatchlistGroupView]:
        """Return groups after ensuring default group and STOCK_LIST seed."""
        self.ensure_compatible_with_stock_list(
            stock_list_codes=stock_list_codes,
            default_group_name=default_group_name,
        )
        return [_group_view(group) for group in self.repo.list_groups_with_members()]

    def ensure_compatible_with_stock_list(
        self,
        *,
        stock_list_codes: Sequence[str],
        default_group_name: str = DEFAULT_GROUP_NAME,
    ) -> None:
        """Idempotently place every STOCK_LIST code into the default group when missing."""
        default_group = self.repo.ensure_default_group(name=default_group_name)
        codes = [str(code).strip() for code in stock_list_codes if str(code).strip()]
        if not codes:
            return
        grouped = set(self.repo.list_membership_codes())
        for code in codes:
            if code not in grouped:
                self.repo.add_member(group_id=default_group.group_id, stock_code=code)

    def create_group(self, *, name: str) -> WatchlistGroupView:
        cleaned = str(name or "").strip()
        if not cleaned:
            raise WatchlistGroupServiceError(
                "Group name is required",
                error_code="watchlist_group_name_required",
            )
        if len(cleaned) > 128:
            raise WatchlistGroupServiceError(
                "Group name is too long",
                error_code="watchlist_group_name_too_long",
            )
        existing = self.repo.list_groups_with_members()
        sort_order = max((group.sort_order for group in existing), default=-1) + 1
        group_key = f"g_{uuid4().hex[:12]}"
        try:
            group = self.repo.create_group(
                group_key=group_key,
                name=cleaned,
                sort_order=sort_order,
            )
        except RepositoryError as exc:
            if exc.error_code == "watchlist_group_key_conflict":
                raise WatchlistGroupConflictError(str(exc)) from exc
            raise
        return _group_view(group)

    def rename_group(self, *, group_id: str, name: str) -> WatchlistGroupView:
        cleaned = str(name or "").strip()
        if not cleaned:
            raise WatchlistGroupServiceError(
                "Group name is required",
                error_code="watchlist_group_name_required",
            )
        group = self.repo.rename_group(group_key=group_id, name=cleaned)
        if group is None:
            raise WatchlistGroupNotFoundError(f"Group not found: {group_id}")
        return _group_view(group)

    def delete_group(self, *, group_id: str) -> None:
        if group_id == DEFAULT_GROUP_KEY:
            raise WatchlistGroupServiceError(
                "Default group cannot be deleted",
                error_code="watchlist_group_default_delete_forbidden",
            )
        group = self.repo.get_group_by_key(group_id)
        if group is None:
            raise WatchlistGroupNotFoundError(f"Group not found: {group_id}")
        # Re-home exclusive members into the default group so codes are not lost.
        default_group = self.repo.ensure_default_group()
        membership_counts: Dict[str, int] = {}
        for item in self.repo.list_groups_with_members():
            for member in item.members:
                membership_counts[member.stock_code] = membership_counts.get(member.stock_code, 0) + 1
        for member in group.members:
            if membership_counts.get(member.stock_code, 0) <= 1:
                self.repo.add_member(
                    group_id=default_group.group_id,
                    stock_code=member.stock_code,
                    attrs=member.attrs,
                )
        deleted = self.repo.delete_group(group_key=group_id)
        if not deleted:
            raise WatchlistGroupNotFoundError(f"Group not found: {group_id}")

    def reorder_groups(self, *, ordered_ids: Sequence[str]) -> List[WatchlistGroupView]:
        existing = {group.group_key: group for group in self.repo.list_groups_with_members()}
        if not existing:
            return []
        ordered = [key for key in ordered_ids if key in existing]
        missing = [key for key in existing if key not in ordered]
        # Preserve unspecified groups at the end in previous relative order.
        final_order = ordered + sorted(missing, key=lambda key: existing[key].sort_order)
        self.repo.set_group_sort_orders(final_order)
        return [_group_view(group) for group in self.repo.list_groups_with_members()]

    def add_member(
        self,
        *,
        group_id: str,
        stock_code: str,
        attrs: Optional[Mapping[str, Any]] = None,
    ) -> WatchlistGroupView:
        code = str(stock_code or "").strip()
        if not code:
            raise WatchlistGroupServiceError(
                "Stock code is required",
                error_code="watchlist_group_member_code_required",
            )
        group = self.repo.get_group_by_key(group_id)
        if group is None:
            raise WatchlistGroupNotFoundError(f"Group not found: {group_id}")
        self.repo.add_member(group_id=group.group_id, stock_code=code, attrs=attrs)
        refreshed = self.repo.get_group_by_key(group_id)
        assert refreshed is not None
        return _group_view(refreshed)

    def remove_member(self, *, group_id: str, stock_code: str) -> WatchlistGroupView:
        group = self.repo.get_group_by_key(group_id)
        if group is None:
            raise WatchlistGroupNotFoundError(f"Group not found: {group_id}")
        code = str(stock_code or "").strip()
        removed = self.repo.remove_member(group_id=group.group_id, stock_code=code)
        if not removed:
            raise WatchlistGroupNotFoundError(
                f"Member {code} not found in group {group_id}"
            )
        # If the code is no longer in any group, put it back into default so
        # upgrade compatibility keeps every watchlist symbol grouped.
        still_grouped = code in set(self.repo.list_membership_codes())
        if not still_grouped:
            default_group = self.repo.ensure_default_group()
            if default_group.group_key != group_id:
                self.repo.add_member(group_id=default_group.group_id, stock_code=code)
        refreshed = self.repo.get_group_by_key(group_id)
        assert refreshed is not None
        return _group_view(refreshed)

    def reorder_members(
        self,
        *,
        group_id: str,
        ordered_codes: Sequence[str],
    ) -> WatchlistGroupView:
        group = self.repo.get_group_by_key(group_id)
        if group is None:
            raise WatchlistGroupNotFoundError(f"Group not found: {group_id}")
        existing_codes = {member.stock_code for member in group.members}
        ordered = [code for code in ordered_codes if code in existing_codes]
        missing = [
            member.stock_code
            for member in sorted(group.members, key=lambda item: item.sort_order)
            if member.stock_code not in ordered
        ]
        self.repo.set_member_sort_orders(
            group_id=group.group_id,
            ordered_codes=ordered + missing,
        )
        refreshed = self.repo.get_group_by_key(group_id)
        assert refreshed is not None
        return _group_view(refreshed)

    def move_member(
        self,
        *,
        stock_code: str,
        source_group_id: str,
        target_group_id: str,
        target_index: Optional[int] = None,
        copy: bool = False,
    ) -> List[WatchlistGroupView]:
        code = str(stock_code or "").strip()
        source = self.repo.get_group_by_key(source_group_id)
        target = self.repo.get_group_by_key(target_group_id)
        if source is None:
            raise WatchlistGroupNotFoundError(f"Group not found: {source_group_id}")
        if target is None:
            raise WatchlistGroupNotFoundError(f"Group not found: {target_group_id}")
        try:
            self.repo.move_member(
                stock_code=code,
                source_group_id=source.group_id,
                target_group_id=target.group_id,
                target_index=target_index,
                copy=copy,
            )
        except RepositoryError as exc:
            if exc.error_code == "watchlist_group_member_not_found":
                raise WatchlistGroupNotFoundError(str(exc)) from exc
            raise
        return [_group_view(group) for group in self.repo.list_groups_with_members()]

    def on_watchlist_code_added(self, stock_code: str) -> None:
        """Hook for STOCK_LIST add: place code in default group if not grouped."""
        code = str(stock_code or "").strip()
        if not code:
            return
        default_group = self.repo.ensure_default_group()
        if code not in set(self.repo.list_membership_codes()):
            self.repo.add_member(group_id=default_group.group_id, stock_code=code)

    def on_watchlist_code_removed(self, stock_code: str) -> None:
        """Hook for STOCK_LIST remove: drop memberships everywhere."""
        code = str(stock_code or "").strip()
        if not code:
            return
        self.repo.remove_member_from_all_groups(stock_code=code)
