# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Persistence boundary for watchlist groups and memberships."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
import logging
from typing import Any, Dict, List, Mapping, Optional, Sequence

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError

from src.repositories.base import BaseRepository, RepositoryError
from src.repositories.watchlist_group_tables import (
    watchlist_group_members_table,
    watchlist_groups_table,
)
from src.storage import DatabaseManager, utc_naive_now
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

DEFAULT_GROUP_KEY = "default"
DEFAULT_GROUP_NAME = "Default"


@dataclass(frozen=True)
class StoredWatchlistGroupMember:
    member_id: int
    group_id: int
    stock_code: str
    sort_order: int
    attrs: Dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class StoredWatchlistGroup:
    group_id: int
    group_key: str
    name: str
    sort_order: int
    is_default: bool
    created_at: datetime
    updated_at: datetime
    members: tuple[StoredWatchlistGroupMember, ...] = field(default_factory=tuple)


class WatchlistGroupRepository(BaseRepository):
    """SQLite-backed watchlist group storage."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None) -> None:
        super().__init__(db_manager)

    @staticmethod
    def _parse_attrs(raw: Any) -> Dict[str, Any]:
        if raw is None or raw == "":
            return {}
        if isinstance(raw, dict):
            return dict(raw)
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}

    @classmethod
    def _row_to_member(cls, row: Mapping[str, Any]) -> StoredWatchlistGroupMember:
        return StoredWatchlistGroupMember(
            member_id=int(row["id"]),
            group_id=int(row["group_id"]),
            stock_code=str(row["stock_code"]),
            sort_order=int(row["sort_order"]),
            attrs=cls._parse_attrs(row.get("attrs_json")),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @classmethod
    def _row_to_group(
        cls,
        row: Mapping[str, Any],
        members: Sequence[StoredWatchlistGroupMember] = (),
    ) -> StoredWatchlistGroup:
        return StoredWatchlistGroup(
            group_id=int(row["id"]),
            group_key=str(row["group_key"]),
            name=str(row["name"]),
            sort_order=int(row["sort_order"]),
            is_default=bool(row["is_default"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            members=tuple(members),
        )

    def list_groups_with_members(self) -> List[StoredWatchlistGroup]:
        try:
            with self.db.get_session() as session:
                group_rows = session.execute(
                    select(watchlist_groups_table).order_by(
                        watchlist_groups_table.c.sort_order,
                        watchlist_groups_table.c.id,
                    )
                ).mappings().all()
                if not group_rows:
                    return []
                group_ids = [int(row["id"]) for row in group_rows]
                member_rows = session.execute(
                    select(watchlist_group_members_table)
                    .where(watchlist_group_members_table.c.group_id.in_(group_ids))
                    .order_by(
                        watchlist_group_members_table.c.group_id,
                        watchlist_group_members_table.c.sort_order,
                        watchlist_group_members_table.c.id,
                    )
                ).mappings().all()
                members_by_group: Dict[int, List[StoredWatchlistGroupMember]] = {
                    group_id: [] for group_id in group_ids
                }
                for row in member_rows:
                    member = self._row_to_member(row)
                    members_by_group.setdefault(member.group_id, []).append(member)
                return [
                    self._row_to_group(row, members_by_group.get(int(row["id"]), []))
                    for row in group_rows
                ]
        except Exception as exc:  # broad-exception: fallback_recorded - surface as repository error
            context = {}
            log_safe_exception(
                logger,
                "Watchlist group list failed",
                exc,
                error_code="watchlist_group_list_failed",
                context=context,
            )
            raise RepositoryError(
                "Watchlist group list failed",
                error_code="watchlist_group_list_failed",
                context=context,
            ) from exc

    def get_group_by_key(self, group_key: str) -> Optional[StoredWatchlistGroup]:
        key = str(group_key or "").strip()
        if not key:
            return None
        try:
            with self.db.get_session() as session:
                row = session.execute(
                    select(watchlist_groups_table).where(
                        watchlist_groups_table.c.group_key == key
                    )
                ).mappings().one_or_none()
                if row is None:
                    return None
                member_rows = session.execute(
                    select(watchlist_group_members_table)
                    .where(watchlist_group_members_table.c.group_id == int(row["id"]))
                    .order_by(
                        watchlist_group_members_table.c.sort_order,
                        watchlist_group_members_table.c.id,
                    )
                ).mappings().all()
                members = [self._row_to_member(item) for item in member_rows]
                return self._row_to_group(row, members)
        except Exception as exc:  # broad-exception: fallback_recorded - surface as repository error
            context = {"group_key": key}
            log_safe_exception(
                logger,
                "Watchlist group lookup failed",
                exc,
                error_code="watchlist_group_get_failed",
                context=context,
            )
            raise RepositoryError(
                "Watchlist group lookup failed",
                error_code="watchlist_group_get_failed",
                context=context,
            ) from exc

    def ensure_default_group(self, *, name: str = DEFAULT_GROUP_NAME) -> StoredWatchlistGroup:
        existing = self.get_group_by_key(DEFAULT_GROUP_KEY)
        if existing is not None:
            return existing
        now = utc_naive_now()
        try:
            with self.db.get_session() as session:
                session.execute(
                    watchlist_groups_table.insert().values(
                        group_key=DEFAULT_GROUP_KEY,
                        name=name,
                        sort_order=0,
                        is_default=True,
                        created_at=now,
                        updated_at=now,
                    )
                )
                session.commit()
        except IntegrityError:
            pass
        except Exception as exc:  # broad-exception: fallback_recorded - surface as repository error
            context = {}
            log_safe_exception(
                logger,
                "Watchlist default group create failed",
                exc,
                error_code="watchlist_group_default_create_failed",
                context=context,
            )
            raise RepositoryError(
                "Watchlist default group create failed",
                error_code="watchlist_group_default_create_failed",
                context=context,
            ) from exc
        group = self.get_group_by_key(DEFAULT_GROUP_KEY)
        if group is None:
            raise RepositoryError(
                "Default watchlist group missing after create",
                error_code="watchlist_group_default_missing",
            )
        return group

    def create_group(self, *, group_key: str, name: str, sort_order: int) -> StoredWatchlistGroup:
        now = utc_naive_now()
        try:
            with self.db.get_session() as session:
                session.execute(
                    watchlist_groups_table.insert().values(
                        group_key=group_key,
                        name=name,
                        sort_order=int(sort_order),
                        is_default=False,
                        created_at=now,
                        updated_at=now,
                    )
                )
                session.commit()
        except IntegrityError as exc:
            raise RepositoryError(
                "Watchlist group key already exists",
                error_code="watchlist_group_key_conflict",
                context={"group_key": group_key},
            ) from exc
        except Exception as exc:  # broad-exception: fallback_recorded - surface as repository error
            context = {"group_key": group_key}
            log_safe_exception(
                logger,
                "Watchlist group create failed",
                exc,
                error_code="watchlist_group_create_failed",
                context=context,
            )
            raise RepositoryError(
                "Watchlist group create failed",
                error_code="watchlist_group_create_failed",
                context=context,
            ) from exc
        group = self.get_group_by_key(group_key)
        if group is None:
            raise RepositoryError(
                "Watchlist group missing after create",
                error_code="watchlist_group_missing_after_create",
                context={"group_key": group_key},
            )
        return group

    def rename_group(self, *, group_key: str, name: str) -> Optional[StoredWatchlistGroup]:
        now = utc_naive_now()
        try:
            with self.db.get_session() as session:
                result = session.execute(
                    update(watchlist_groups_table)
                    .where(watchlist_groups_table.c.group_key == group_key)
                    .values(name=name, updated_at=now)
                )
                session.commit()
                if int(result.rowcount or 0) == 0:
                    return None
        except Exception as exc:  # broad-exception: fallback_recorded - surface as repository error
            context = {"group_key": group_key}
            log_safe_exception(
                logger,
                "Watchlist group rename failed",
                exc,
                error_code="watchlist_group_rename_failed",
                context=context,
            )
            raise RepositoryError(
                "Watchlist group rename failed",
                error_code="watchlist_group_rename_failed",
                context=context,
            ) from exc
        return self.get_group_by_key(group_key)

    def delete_group(self, *, group_key: str) -> bool:
        if group_key == DEFAULT_GROUP_KEY:
            raise RepositoryError(
                "Default watchlist group cannot be deleted",
                error_code="watchlist_group_default_delete_forbidden",
            )
        try:
            with self.db.get_session() as session:
                result = session.execute(
                    delete(watchlist_groups_table).where(
                        watchlist_groups_table.c.group_key == group_key
                    )
                )
                session.commit()
                return int(result.rowcount or 0) > 0
        except Exception as exc:  # broad-exception: fallback_recorded - surface as repository error
            context = {"group_key": group_key}
            log_safe_exception(
                logger,
                "Watchlist group delete failed",
                exc,
                error_code="watchlist_group_delete_failed",
                context=context,
            )
            raise RepositoryError(
                "Watchlist group delete failed",
                error_code="watchlist_group_delete_failed",
                context=context,
            ) from exc

    def set_group_sort_orders(self, ordered_keys: Sequence[str]) -> None:
        now = utc_naive_now()
        try:
            with self.db.get_session() as session:
                for index, group_key in enumerate(ordered_keys):
                    session.execute(
                        update(watchlist_groups_table)
                        .where(watchlist_groups_table.c.group_key == group_key)
                        .values(sort_order=index, updated_at=now)
                    )
                session.commit()
        except Exception as exc:  # broad-exception: fallback_recorded - surface as repository error
            context = {}
            log_safe_exception(
                logger,
                "Watchlist group reorder failed",
                exc,
                error_code="watchlist_group_reorder_failed",
                context=context,
            )
            raise RepositoryError(
                "Watchlist group reorder failed",
                error_code="watchlist_group_reorder_failed",
                context=context,
            ) from exc

    def list_membership_codes(self) -> List[str]:
        try:
            with self.db.get_session() as session:
                rows = session.execute(
                    select(watchlist_group_members_table.c.stock_code).distinct()
                ).all()
                return [str(row[0]) for row in rows if row and row[0]]
        except Exception as exc:  # broad-exception: fallback_recorded - surface as repository error
            context = {}
            log_safe_exception(
                logger,
                "Watchlist membership codes list failed",
                exc,
                error_code="watchlist_group_membership_list_failed",
                context=context,
            )
            raise RepositoryError(
                "Watchlist membership codes list failed",
                error_code="watchlist_group_membership_list_failed",
                context=context,
            ) from exc

    def add_member(
        self,
        *,
        group_id: int,
        stock_code: str,
        sort_order: Optional[int] = None,
        attrs: Optional[Mapping[str, Any]] = None,
    ) -> StoredWatchlistGroupMember:
        now = utc_naive_now()
        attrs_json = json.dumps(dict(attrs or {}), ensure_ascii=False, sort_keys=True)
        try:
            with self.db.get_session() as session:
                existing = session.execute(
                    select(watchlist_group_members_table).where(
                        watchlist_group_members_table.c.group_id == group_id,
                        watchlist_group_members_table.c.stock_code == stock_code,
                    )
                ).mappings().one_or_none()
                if existing is not None:
                    return self._row_to_member(existing)

                if sort_order is None:
                    max_order = session.execute(
                        select(watchlist_group_members_table.c.sort_order)
                        .where(watchlist_group_members_table.c.group_id == group_id)
                        .order_by(watchlist_group_members_table.c.sort_order.desc())
                        .limit(1)
                    ).scalar()
                    sort_order = int(max_order) + 1 if max_order is not None else 0

                session.execute(
                    watchlist_group_members_table.insert().values(
                        group_id=group_id,
                        stock_code=stock_code,
                        sort_order=int(sort_order),
                        attrs_json=attrs_json,
                        created_at=now,
                        updated_at=now,
                    )
                )
                session.commit()
                row = session.execute(
                    select(watchlist_group_members_table).where(
                        watchlist_group_members_table.c.group_id == group_id,
                        watchlist_group_members_table.c.stock_code == stock_code,
                    )
                ).mappings().one()
                return self._row_to_member(row)
        except Exception as exc:  # broad-exception: fallback_recorded - surface as repository error
            context = {"group_id": group_id, "stock_code": stock_code}
            log_safe_exception(
                logger,
                "Watchlist group member add failed",
                exc,
                error_code="watchlist_group_member_add_failed",
                context=context,
            )
            raise RepositoryError(
                "Watchlist group member add failed",
                error_code="watchlist_group_member_add_failed",
                context=context,
            ) from exc

    def remove_member(self, *, group_id: int, stock_code: str) -> bool:
        try:
            with self.db.get_session() as session:
                result = session.execute(
                    delete(watchlist_group_members_table).where(
                        watchlist_group_members_table.c.group_id == group_id,
                        watchlist_group_members_table.c.stock_code == stock_code,
                    )
                )
                session.commit()
                return int(result.rowcount or 0) > 0
        except Exception as exc:  # broad-exception: fallback_recorded - surface as repository error
            context = {"group_id": group_id, "stock_code": stock_code}
            log_safe_exception(
                logger,
                "Watchlist group member remove failed",
                exc,
                error_code="watchlist_group_member_remove_failed",
                context=context,
            )
            raise RepositoryError(
                "Watchlist group member remove failed",
                error_code="watchlist_group_member_remove_failed",
                context=context,
            ) from exc

    def remove_member_from_all_groups(self, *, stock_code: str) -> int:
        try:
            with self.db.get_session() as session:
                result = session.execute(
                    delete(watchlist_group_members_table).where(
                        watchlist_group_members_table.c.stock_code == stock_code
                    )
                )
                session.commit()
                return int(result.rowcount or 0)
        except Exception as exc:  # broad-exception: fallback_recorded - surface as repository error
            context = {"stock_code": stock_code}
            log_safe_exception(
                logger,
                "Watchlist group member global remove failed",
                exc,
                error_code="watchlist_group_member_global_remove_failed",
                context=context,
            )
            raise RepositoryError(
                "Watchlist group member global remove failed",
                error_code="watchlist_group_member_global_remove_failed",
                context=context,
            ) from exc

    def set_member_sort_orders(
        self,
        *,
        group_id: int,
        ordered_codes: Sequence[str],
    ) -> None:
        now = utc_naive_now()
        try:
            with self.db.get_session() as session:
                for index, stock_code in enumerate(ordered_codes):
                    session.execute(
                        update(watchlist_group_members_table)
                        .where(
                            watchlist_group_members_table.c.group_id == group_id,
                            watchlist_group_members_table.c.stock_code == stock_code,
                        )
                        .values(sort_order=index, updated_at=now)
                    )
                session.commit()
        except Exception as exc:  # broad-exception: fallback_recorded - surface as repository error
            context = {"group_id": group_id}
            log_safe_exception(
                logger,
                "Watchlist group member reorder failed",
                exc,
                error_code="watchlist_group_member_reorder_failed",
                context=context,
            )
            raise RepositoryError(
                "Watchlist group member reorder failed",
                error_code="watchlist_group_member_reorder_failed",
                context=context,
            ) from exc

    def move_member(
        self,
        *,
        stock_code: str,
        source_group_id: int,
        target_group_id: int,
        target_index: Optional[int] = None,
        copy: bool = False,
    ) -> None:
        """Move or copy a member between groups, preserving attrs on move."""
        try:
            with self.db.get_session() as session:
                source = session.execute(
                    select(watchlist_group_members_table).where(
                        watchlist_group_members_table.c.group_id == source_group_id,
                        watchlist_group_members_table.c.stock_code == stock_code,
                    )
                ).mappings().one_or_none()
                if source is None:
                    raise RepositoryError(
                        "Source membership not found",
                        error_code="watchlist_group_member_not_found",
                        context={
                            "stock_code": stock_code,
                            "source_group_id": source_group_id,
                        },
                    )

                now = utc_naive_now()
                target = session.execute(
                    select(watchlist_group_members_table).where(
                        watchlist_group_members_table.c.group_id == target_group_id,
                        watchlist_group_members_table.c.stock_code == stock_code,
                    )
                ).mappings().one_or_none()

                if target is None:
                    max_order = session.execute(
                        select(watchlist_group_members_table.c.sort_order)
                        .where(watchlist_group_members_table.c.group_id == target_group_id)
                        .order_by(watchlist_group_members_table.c.sort_order.desc())
                        .limit(1)
                    ).scalar()
                    next_order = int(max_order) + 1 if max_order is not None else 0
                    insert_order = (
                        max(0, min(int(target_index), next_order))
                        if target_index is not None
                        else next_order
                    )
                    existing_codes = session.execute(
                        select(
                            watchlist_group_members_table.c.id,
                            watchlist_group_members_table.c.sort_order,
                        )
                        .where(watchlist_group_members_table.c.group_id == target_group_id)
                        .order_by(watchlist_group_members_table.c.sort_order)
                    ).all()
                    for row_id, sort_order in existing_codes:
                        if int(sort_order) >= insert_order:
                            session.execute(
                                update(watchlist_group_members_table)
                                .where(watchlist_group_members_table.c.id == int(row_id))
                                .values(sort_order=int(sort_order) + 1, updated_at=now)
                            )
                    session.execute(
                        watchlist_group_members_table.insert().values(
                            group_id=target_group_id,
                            stock_code=stock_code,
                            sort_order=insert_order,
                            attrs_json=source["attrs_json"] or "{}",
                            created_at=now,
                            updated_at=now,
                        )
                    )
                elif target_index is not None:
                    codes = [
                        str(row[0])
                        for row in session.execute(
                            select(watchlist_group_members_table.c.stock_code)
                            .where(
                                watchlist_group_members_table.c.group_id == target_group_id
                            )
                            .order_by(watchlist_group_members_table.c.sort_order)
                        ).all()
                    ]
                    if stock_code in codes:
                        codes.remove(stock_code)
                    insert_at = max(0, min(int(target_index), len(codes)))
                    codes.insert(insert_at, stock_code)
                    for index, code in enumerate(codes):
                        session.execute(
                            update(watchlist_group_members_table)
                            .where(
                                watchlist_group_members_table.c.group_id == target_group_id,
                                watchlist_group_members_table.c.stock_code == code,
                            )
                            .values(sort_order=index, updated_at=now)
                        )

                if not copy and source_group_id != target_group_id:
                    session.execute(
                        delete(watchlist_group_members_table).where(
                            watchlist_group_members_table.c.group_id == source_group_id,
                            watchlist_group_members_table.c.stock_code == stock_code,
                        )
                    )
                session.commit()
        except RepositoryError:
            raise
        except Exception as exc:  # broad-exception: fallback_recorded - surface as repository error
            context = {
                    "stock_code": stock_code,
                    "source_group_id": source_group_id,
                    "target_group_id": target_group_id,
                }
            log_safe_exception(
                logger,
                "Watchlist group member move failed",
                exc,
                error_code="watchlist_group_member_move_failed",
                context=context,
            )
            raise RepositoryError(
                "Watchlist group member move failed",
                error_code="watchlist_group_member_move_failed",
                context=context,
            ) from exc
