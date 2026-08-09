# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Transactional persistence boundary for watchlist groups."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import math
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from sqlalchemy import delete, func, select, update
from src.repositories.base import BaseRepository, RepositoryError
from src.repositories.watchlist_group_tables import (
    watchlist_group_members_table,
    watchlist_group_state_table,
    watchlist_groups_table,
)
from src.services.watchlist_identity import canonicalize_watchlist_codes, watchlist_match_key
from src.storage import DatabaseManager

DEFAULT_GROUP_KEY = "default"
DEFAULT_GROUP_NAME = "__default__"
DEFAULT_GROUP_NAME_KEY = "watchlist.defaultGroupName"
MAX_GROUPS = 50
MAX_MEMBERS_PER_GROUP = 500
MAX_TOTAL_MEMBERSHIPS = 2_000
COMPUTED_ATTRS_SCHEMA_VERSION = 1


def _now() -> datetime:
    """Return UTC for storage; SQLite may deserialize it without tzinfo."""
    return datetime.now(timezone.utc)


def _typed_attrs(raw: Any) -> Dict[str, Any]:
    """Project legacy JSON into the bounded, versioned computed schema."""
    if raw in (None, ""):
        parsed: Mapping[str, Any] = {}
    elif isinstance(raw, Mapping):
        parsed = raw
    else:
        try:
            value = json.loads(str(raw))
        except (TypeError, ValueError):
            value = {}
        parsed = value if isinstance(value, Mapping) else {}
    result: Dict[str, Any] = {"schema_version": COMPUTED_ATTRS_SCHEMA_VERSION}
    score = parsed.get("ai_score", parsed.get("score"))
    if (
        isinstance(score, (int, float))
        and not isinstance(score, bool)
        and math.isfinite(float(score))
        and 0 <= float(score) <= 100
    ):
        result["ai_score"] = float(score)
    focus = parsed.get("focus")
    if isinstance(focus, bool):
        result["focus"] = focus
    return result


def _attrs_json(raw: Any) -> str:
    return json.dumps(_typed_attrs(raw), ensure_ascii=False, sort_keys=True, allow_nan=False)


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


@dataclass(frozen=True)
class StoredWatchlistState:
    revision: int
    groups: tuple[StoredWatchlistGroup, ...]


class WatchlistGroupRepository(BaseRepository):
    """SQLite-backed aggregate with revision-checked atomic mutations."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None) -> None:
        super().__init__(db_manager)

    @staticmethod
    def _row_to_member(row: Mapping[str, Any]) -> StoredWatchlistGroupMember:
        return StoredWatchlistGroupMember(
            member_id=int(row["id"]),
            group_id=int(row["group_id"]),
            stock_code=str(row["stock_code"]),
            sort_order=int(row["sort_order"]),
            attrs=_typed_attrs(row.get("attrs_json")),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @classmethod
    def _groups(cls, session) -> tuple[StoredWatchlistGroup, ...]:
        group_rows = session.execute(
            select(watchlist_groups_table).order_by(
                watchlist_groups_table.c.sort_order, watchlist_groups_table.c.id
            )
        ).mappings().all()
        if not group_rows:
            return ()
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
        members: dict[int, list[StoredWatchlistGroupMember]] = {group_id: [] for group_id in group_ids}
        for row in member_rows:
            member = cls._row_to_member(row)
            members.setdefault(member.group_id, []).append(member)
        return tuple(
            StoredWatchlistGroup(
                group_id=int(row["id"]),
                group_key=str(row["group_key"]),
                name=str(row["name"]),
                sort_order=int(row["sort_order"]),
                is_default=bool(row["is_default"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                members=tuple(members.get(int(row["id"]), [])),
            )
            for row in group_rows
        )

    @staticmethod
    def _revision(session) -> int:
        revision = session.execute(
            select(watchlist_group_state_table.c.revision).where(watchlist_group_state_table.c.id == 1)
        ).scalar_one_or_none()
        if revision is None:
            session.execute(
                watchlist_group_state_table.insert().values(id=1, revision=1, updated_at=_now())
            )
            return 1
        return int(revision)

    @classmethod
    def _acquire_revision_lease(cls, session, expected_revision: int) -> int:
        """Acquire the aggregate write lease before any business mutation."""
        next_revision = expected_revision + 1
        result = session.execute(
            update(watchlist_group_state_table)
            .where(
                watchlist_group_state_table.c.id == 1,
                watchlist_group_state_table.c.revision == expected_revision,
            )
            .values(revision=next_revision, updated_at=_now())
        )
        if int(result.rowcount or 0) != 1:
            latest = cls._revision(session)
            if latest == expected_revision:
                result = session.execute(
                    update(watchlist_group_state_table)
                    .where(
                        watchlist_group_state_table.c.id == 1,
                        watchlist_group_state_table.c.revision == expected_revision,
                    )
                    .values(revision=next_revision, updated_at=_now())
                )
                if int(result.rowcount or 0) == 1:
                    return next_revision
            raise RepositoryError(
                "Watchlist group revision changed concurrently",
                error_code="watchlist_group_revision_conflict",
                context={"current_revision": latest},
            )
        return next_revision

    @classmethod
    def _acquire_reconcile_lease(cls, session) -> int:
        """Serialize reconciliation with mutations without changing revision."""
        result = session.execute(
            update(watchlist_group_state_table)
            .where(watchlist_group_state_table.c.id == 1)
            .values(revision=watchlist_group_state_table.c.revision)
        )
        if int(result.rowcount or 0) == 0:
            cls._revision(session)
            result = session.execute(
                update(watchlist_group_state_table)
                .where(watchlist_group_state_table.c.id == 1)
                .values(revision=watchlist_group_state_table.c.revision)
            )
            if int(result.rowcount or 0) != 1:
                raise RepositoryError(
                    "Watchlist group write lease is unavailable",
                    error_code="watchlist_group_revision_conflict",
                    context={"current_revision": cls._revision(session)},
                )
        return cls._revision(session)

    @staticmethod
    def _commit_reconciled_revision(session, current: int) -> int:
        next_revision = current + 1
        result = session.execute(
            update(watchlist_group_state_table)
            .where(
                watchlist_group_state_table.c.id == 1,
                watchlist_group_state_table.c.revision == current,
            )
            .values(revision=next_revision, updated_at=_now())
        )
        if int(result.rowcount or 0) != 1:
            latest = WatchlistGroupRepository._revision(session)
            raise RepositoryError(
                "Watchlist group revision changed concurrently",
                error_code="watchlist_group_revision_conflict",
                context={"current_revision": latest},
            )
        return next_revision

    @staticmethod
    def _rewrite_orders(session, table, rows: Sequence[tuple[int, int]], *, group_id: int | None = None) -> bool:
        """Rewrite one exact contiguous sequence without transient unique collisions."""
        changed = any(old_order != index for index, (_, old_order) in enumerate(rows))
        if not changed:
            return False
        now = _now()
        offset = max((old for _, old in rows), default=0) + len(rows) + 1_000
        for index, (row_id, _) in enumerate(rows):
            where = table.c.id == row_id
            if group_id is not None:
                where = where & (table.c.group_id == group_id)
            session.execute(update(table).where(where).values(sort_order=offset + index, updated_at=now))
        session.flush()
        for index, (row_id, _) in enumerate(rows):
            where = table.c.id == row_id
            if group_id is not None:
                where = where & (table.c.group_id == group_id)
            session.execute(update(table).where(where).values(sort_order=index, updated_at=now))
        return True

    @classmethod
    def _normalize_all_orders(cls, session) -> bool:
        changed = False
        group_rows = session.execute(
            select(watchlist_groups_table.c.id, watchlist_groups_table.c.sort_order).order_by(
                watchlist_groups_table.c.sort_order, watchlist_groups_table.c.id
            )
        ).all()
        changed |= cls._rewrite_orders(session, watchlist_groups_table, group_rows)
        for group_id, _ in group_rows:
            member_rows = session.execute(
                select(watchlist_group_members_table.c.id, watchlist_group_members_table.c.sort_order)
                .where(watchlist_group_members_table.c.group_id == int(group_id))
                .order_by(watchlist_group_members_table.c.sort_order, watchlist_group_members_table.c.id)
            ).all()
            changed |= cls._rewrite_orders(
                session, watchlist_group_members_table, member_rows, group_id=int(group_id)
            )
        return changed

    @staticmethod
    def _default_group_id(session) -> int:
        row = session.execute(
            select(watchlist_groups_table.c.id).where(
                watchlist_groups_table.c.group_key == DEFAULT_GROUP_KEY
            )
        ).scalar_one_or_none()
        if row is not None:
            return int(row)
        max_order = session.execute(select(func.max(watchlist_groups_table.c.sort_order))).scalar()
        session.execute(
            watchlist_groups_table.insert().values(
                group_key=DEFAULT_GROUP_KEY,
                name=DEFAULT_GROUP_NAME,
                sort_order=int(max_order) + 1 if max_order is not None else 0,
                is_default=True,
                created_at=_now(),
                updated_at=_now(),
            )
        )
        return int(
            session.execute(
                select(watchlist_groups_table.c.id).where(
                    watchlist_groups_table.c.group_key == DEFAULT_GROUP_KEY
                )
            ).scalar_one()
        )

    def get_state(self) -> StoredWatchlistState:
        with self.db.get_session() as session:
            return StoredWatchlistState(self._revision(session), self._groups(session))

    def list_groups_with_members(self) -> List[StoredWatchlistGroup]:
        return list(self.get_state().groups)

    def get_group_by_key(self, group_key: str) -> Optional[StoredWatchlistGroup]:
        return next((group for group in self.get_state().groups if group.group_key == group_key), None)

    def reconcile(
        self,
        *,
        stock_list_codes: Sequence[str],
        authority_version: Optional[str] = None,
        authority_version_reader: Optional[Callable[[], str]] = None,
    ) -> StoredWatchlistState:
        """Atomically project authoritative STOCK_LIST membership into group rows."""
        authoritative = canonicalize_watchlist_codes([str(code) for code in stock_list_codes])
        authoritative_set = set(authoritative)
        with self.db.get_session() as session:
            current = self._acquire_reconcile_lease(session)
            if (
                authority_version is not None
                and authority_version_reader is not None
                and authority_version_reader() != authority_version
            ):
                raise RepositoryError(
                    "Authoritative STOCK_LIST changed during reconciliation",
                    error_code="watchlist_group_authority_changed",
                )
            default_id = self._default_group_id(session)
            changed = False
            rows = session.execute(
                select(watchlist_group_members_table).order_by(
                    watchlist_group_members_table.c.group_id,
                    watchlist_group_members_table.c.sort_order,
                    watchlist_group_members_table.c.id,
                )
            ).mappings().all()
            survivors: dict[tuple[int, str], Mapping[str, Any]] = {}
            delete_ids: list[int] = []
            for row in rows:
                identity = watchlist_match_key(str(row["stock_code"]))
                key = (int(row["group_id"]), identity)
                if identity not in authoritative_set or key in survivors:
                    delete_ids.append(int(row["id"]))
                    continue
                survivors[key] = row
            globally_grouped = {identity for _, identity in survivors}
            missing = [identity for identity in authoritative if identity not in globally_grouped]
            projected_default_count = sum(
                1 for group_id, _identity in survivors if group_id == default_id
            ) + len(missing)
            if projected_default_count > MAX_MEMBERS_PER_GROUP:
                raise RepositoryError(
                    "Authoritative watchlist exceeds the default group limit",
                    error_code="watchlist_group_member_limit_reached",
                )
            if len(survivors) + len(missing) > MAX_TOTAL_MEMBERSHIPS:
                raise RepositoryError(
                    "Membership limit reached",
                    error_code="watchlist_group_member_limit_reached",
                )
            if delete_ids:
                session.execute(
                    delete(watchlist_group_members_table).where(
                        watchlist_group_members_table.c.id.in_(delete_ids)
                    )
                )
                session.flush()
                changed = True
            for (_, identity), row in survivors.items():
                typed_json = _attrs_json(row.get("attrs_json"))
                if str(row["stock_code"]) != identity or str(row.get("attrs_json") or "") != typed_json:
                    session.execute(
                        update(watchlist_group_members_table)
                        .where(watchlist_group_members_table.c.id == int(row["id"]))
                        .values(stock_code=identity, attrs_json=typed_json, updated_at=_now())
                    )
                    changed = True
            next_order = session.execute(
                select(func.max(watchlist_group_members_table.c.sort_order)).where(
                    watchlist_group_members_table.c.group_id == default_id
                )
            ).scalar()
            insert_order = int(next_order) + 1 if next_order is not None else 0
            for identity in missing:
                session.execute(
                    watchlist_group_members_table.insert().values(
                        group_id=default_id,
                        stock_code=identity,
                        sort_order=insert_order,
                        attrs_json=_attrs_json({}),
                        created_at=_now(),
                        updated_at=_now(),
                    )
                )
                insert_order += 1
                changed = True
            changed |= self._normalize_all_orders(session)
            if changed:
                current = self._commit_reconciled_revision(session, current)
            session.commit()
            return StoredWatchlistState(current, self._groups(session))

    def create_group(self, *, group_key: str, name: str, expected_revision: int) -> StoredWatchlistState:
        with self.db.get_session() as session:
            current = self._acquire_revision_lease(session, expected_revision)
            count = int(session.execute(select(func.count()).select_from(watchlist_groups_table)).scalar_one())
            if count >= MAX_GROUPS:
                raise RepositoryError("Group limit reached", error_code="watchlist_group_limit_reached")
            session.execute(
                watchlist_groups_table.insert().values(
                    group_key=group_key,
                    name=name,
                    sort_order=count,
                    is_default=False,
                    created_at=_now(),
                    updated_at=_now(),
                )
            )
            session.commit()
            return StoredWatchlistState(current, self._groups(session))

    def rename_group(self, *, group_key: str, name: str, expected_revision: int) -> StoredWatchlistState:
        with self.db.get_session() as session:
            current = self._acquire_revision_lease(session, expected_revision)
            result = session.execute(
                update(watchlist_groups_table)
                .where(watchlist_groups_table.c.group_key == group_key)
                .values(name=name, updated_at=_now())
            )
            if int(result.rowcount or 0) != 1:
                raise RepositoryError("Group not found", error_code="watchlist_group_not_found")
            session.commit()
            return StoredWatchlistState(current, self._groups(session))

    def delete_group(self, *, group_key: str, expected_revision: int) -> StoredWatchlistState:
        if group_key == DEFAULT_GROUP_KEY:
            raise RepositoryError(
                "Default group cannot be deleted",
                error_code="watchlist_group_default_delete_forbidden",
            )
        with self.db.get_session() as session:
            current = self._acquire_revision_lease(session, expected_revision)
            group_id = session.execute(
                select(watchlist_groups_table.c.id).where(watchlist_groups_table.c.group_key == group_key)
            ).scalar_one_or_none()
            if group_id is None:
                raise RepositoryError("Group not found", error_code="watchlist_group_not_found")
            default_id = self._default_group_id(session)
            members = session.execute(
                select(watchlist_group_members_table).where(
                    watchlist_group_members_table.c.group_id == int(group_id)
                )
            ).mappings().all()
            default_count = int(
                session.execute(
                    select(func.count()).select_from(watchlist_group_members_table).where(
                        watchlist_group_members_table.c.group_id == default_id
                    )
                ).scalar_one()
            )
            for member in members:
                other = int(
                    session.execute(
                        select(func.count()).select_from(watchlist_group_members_table).where(
                            watchlist_group_members_table.c.stock_code == member["stock_code"],
                            watchlist_group_members_table.c.group_id != int(group_id),
                        )
                    ).scalar_one()
                )
                if other == 0:
                    if default_count >= MAX_MEMBERS_PER_GROUP:
                        raise RepositoryError(
                            "Membership limit reached",
                            error_code="watchlist_group_member_limit_reached",
                        )
                    session.execute(
                        watchlist_group_members_table.insert().values(
                            group_id=default_id,
                            stock_code=member["stock_code"],
                            sort_order=default_count,
                            attrs_json=_attrs_json(member.get("attrs_json")),
                            created_at=_now(),
                            updated_at=_now(),
                        )
                    )
                    default_count += 1
            session.execute(delete(watchlist_groups_table).where(watchlist_groups_table.c.id == int(group_id)))
            self._normalize_all_orders(session)
            session.commit()
            return StoredWatchlistState(current, self._groups(session))

    def reorder_groups(self, *, ordered_keys: Sequence[str], expected_revision: int) -> StoredWatchlistState:
        with self.db.get_session() as session:
            current = self._acquire_revision_lease(session, expected_revision)
            rows = session.execute(
                select(
                    watchlist_groups_table.c.id,
                    watchlist_groups_table.c.group_key,
                    watchlist_groups_table.c.sort_order,
                )
                .order_by(watchlist_groups_table.c.sort_order)
            ).all()
            current_keys = [str(row[1]) for row in rows]
            requested = [str(key) for key in ordered_keys]
            if len(requested) != len(set(requested)) or set(requested) != set(current_keys):
                raise RepositoryError(
                    "Reorder must contain every current group exactly once",
                    error_code="watchlist_group_reorder_invalid",
                )
            by_key = {str(row[1]): (int(row[0]), int(row[2])) for row in rows}
            self._rewrite_orders(session, watchlist_groups_table, [by_key[key] for key in requested])
            session.commit()
            return StoredWatchlistState(current, self._groups(session))

    def add_member(self, *, group_key: str, stock_code: str, expected_revision: int) -> StoredWatchlistState:
        with self.db.get_session() as session:
            current = self._acquire_revision_lease(session, expected_revision)
            group_id = session.execute(
                select(watchlist_groups_table.c.id).where(watchlist_groups_table.c.group_key == group_key)
            ).scalar_one_or_none()
            if group_id is None:
                raise RepositoryError("Group not found", error_code="watchlist_group_not_found")
            identity = watchlist_match_key(stock_code)
            exists = session.execute(
                select(watchlist_group_members_table.c.id).where(
                    watchlist_group_members_table.c.group_id == int(group_id),
                    watchlist_group_members_table.c.stock_code == identity,
                )
            ).scalar_one_or_none()
            if exists is not None:
                session.rollback()
                return self.get_state()
            group_count = int(
                session.execute(
                    select(func.count()).select_from(watchlist_group_members_table).where(
                        watchlist_group_members_table.c.group_id == int(group_id)
                    )
                ).scalar_one()
            )
            total_count = int(
                session.execute(
                    select(func.count()).select_from(watchlist_group_members_table)
                ).scalar_one()
            )
            if group_count >= MAX_MEMBERS_PER_GROUP or total_count >= MAX_TOTAL_MEMBERSHIPS:
                raise RepositoryError("Membership limit reached", error_code="watchlist_group_member_limit_reached")
            session.execute(
                watchlist_group_members_table.insert().values(
                    group_id=int(group_id),
                    stock_code=identity,
                    sort_order=group_count,
                    attrs_json=_attrs_json({}),
                    created_at=_now(),
                    updated_at=_now(),
                )
            )
            session.commit()
            return StoredWatchlistState(current, self._groups(session))

    def remove_member(self, *, group_key: str, stock_code: str, expected_revision: int) -> StoredWatchlistState:
        with self.db.get_session() as session:
            current = self._acquire_revision_lease(session, expected_revision)
            group_id = session.execute(
                select(watchlist_groups_table.c.id).where(watchlist_groups_table.c.group_key == group_key)
            ).scalar_one_or_none()
            if group_id is None:
                raise RepositoryError("Group not found", error_code="watchlist_group_not_found")
            identity = watchlist_match_key(stock_code)
            result = session.execute(
                delete(watchlist_group_members_table).where(
                    watchlist_group_members_table.c.group_id == int(group_id),
                    watchlist_group_members_table.c.stock_code == identity,
                )
            )
            if int(result.rowcount or 0) != 1:
                raise RepositoryError("Member not found", error_code="watchlist_group_member_not_found")
            remaining = int(
                session.execute(
                    select(func.count()).select_from(watchlist_group_members_table).where(
                        watchlist_group_members_table.c.stock_code == identity
                    )
                ).scalar_one()
            )
            if remaining == 0:
                default_id = self._default_group_id(session)
                default_count = int(
                    session.execute(
                        select(func.count()).select_from(watchlist_group_members_table).where(
                            watchlist_group_members_table.c.group_id == default_id
                        )
                    ).scalar_one()
                )
                session.execute(
                    watchlist_group_members_table.insert().values(
                        group_id=default_id,
                        stock_code=identity,
                        sort_order=default_count,
                        attrs_json=_attrs_json({}),
                        created_at=_now(),
                        updated_at=_now(),
                    )
                )
            self._normalize_all_orders(session)
            session.commit()
            return StoredWatchlistState(current, self._groups(session))

    def reorder_members(
        self, *, group_key: str, ordered_codes: Sequence[str], expected_revision: int
    ) -> StoredWatchlistState:
        with self.db.get_session() as session:
            current = self._acquire_revision_lease(session, expected_revision)
            group_id = session.execute(
                select(watchlist_groups_table.c.id).where(watchlist_groups_table.c.group_key == group_key)
            ).scalar_one_or_none()
            if group_id is None:
                raise RepositoryError("Group not found", error_code="watchlist_group_not_found")
            rows = session.execute(
                select(
                    watchlist_group_members_table.c.id,
                    watchlist_group_members_table.c.stock_code,
                    watchlist_group_members_table.c.sort_order,
                )
                .where(watchlist_group_members_table.c.group_id == int(group_id))
                .order_by(watchlist_group_members_table.c.sort_order)
            ).all()
            requested = [watchlist_match_key(code) for code in ordered_codes]
            current_codes = [str(row[1]) for row in rows]
            if len(requested) != len(set(requested)) or set(requested) != set(current_codes):
                raise RepositoryError(
                    "Reorder must contain every current member exactly once",
                    error_code="watchlist_group_member_reorder_invalid",
                )
            by_code = {str(row[1]): (int(row[0]), int(row[2])) for row in rows}
            self._rewrite_orders(
                session,
                watchlist_group_members_table,
                [by_code[code] for code in requested],
                group_id=int(group_id),
            )
            session.commit()
            return StoredWatchlistState(current, self._groups(session))

    def move_member(
        self,
        *,
        stock_code: str,
        source_group_key: str,
        target_group_key: str,
        target_index: Optional[int],
        copy: bool,
        expected_revision: int,
    ) -> StoredWatchlistState:
        with self.db.get_session() as session:
            current = self._acquire_revision_lease(session, expected_revision)
            groups = dict(
                session.execute(select(watchlist_groups_table.c.group_key, watchlist_groups_table.c.id)).all()
            )
            if source_group_key not in groups or target_group_key not in groups:
                raise RepositoryError("Group not found", error_code="watchlist_group_not_found")
            source_id = int(groups[source_group_key])
            target_id = int(groups[target_group_key])
            identity = watchlist_match_key(stock_code)
            source = session.execute(
                select(watchlist_group_members_table).where(
                    watchlist_group_members_table.c.group_id == source_id,
                    watchlist_group_members_table.c.stock_code == identity,
                )
            ).mappings().one_or_none()
            if source is None:
                raise RepositoryError("Member not found", error_code="watchlist_group_member_not_found")
            target = session.execute(
                select(watchlist_group_members_table).where(
                    watchlist_group_members_table.c.group_id == target_id,
                    watchlist_group_members_table.c.stock_code == identity,
                )
            ).mappings().one_or_none()
            if target is None:
                target_count = int(
                    session.execute(
                        select(func.count()).select_from(watchlist_group_members_table).where(
                            watchlist_group_members_table.c.group_id == target_id
                        )
                    ).scalar_one()
                )
                if target_count >= MAX_MEMBERS_PER_GROUP:
                    raise RepositoryError("Membership limit reached", error_code="watchlist_group_member_limit_reached")
                if copy:
                    total_count = int(
                        session.execute(
                            select(func.count()).select_from(watchlist_group_members_table)
                        ).scalar_one()
                    )
                    if total_count >= MAX_TOTAL_MEMBERSHIPS:
                        raise RepositoryError(
                            "Membership limit reached",
                            error_code="watchlist_group_member_limit_reached",
                        )
                session.execute(
                    watchlist_group_members_table.insert().values(
                        group_id=target_id,
                        stock_code=identity,
                        sort_order=target_count,
                        attrs_json=_attrs_json(source.get("attrs_json")),
                        created_at=_now(),
                        updated_at=_now(),
                    )
                )
            if not copy and source_id != target_id:
                session.execute(
                    delete(watchlist_group_members_table).where(
                        watchlist_group_members_table.c.id == int(source["id"])
                    )
                )
            session.flush()
            for affected_id in {source_id, target_id}:
                ordered_rows = session.execute(
                    select(
                        watchlist_group_members_table.c.id,
                        watchlist_group_members_table.c.stock_code,
                        watchlist_group_members_table.c.sort_order,
                    )
                    .where(watchlist_group_members_table.c.group_id == affected_id)
                    .order_by(watchlist_group_members_table.c.sort_order, watchlist_group_members_table.c.id)
                ).all()
                if affected_id == target_id and target_index is not None:
                    ordered_rows = list(ordered_rows)
                    moving = next((row for row in ordered_rows if row[1] == identity), None)
                    if moving is not None:
                        ordered_rows.remove(moving)
                        ordered_rows.insert(min(int(target_index), len(ordered_rows)), moving)
                self._rewrite_orders(
                    session,
                    watchlist_group_members_table,
                    [(int(row[0]), int(row[2])) for row in ordered_rows],
                    group_id=affected_id,
                )
            session.commit()
            return StoredWatchlistState(current, self._groups(session))


__all__ = [
    "COMPUTED_ATTRS_SCHEMA_VERSION",
    "DEFAULT_GROUP_KEY",
    "DEFAULT_GROUP_NAME",
    "DEFAULT_GROUP_NAME_KEY",
    "MAX_GROUPS",
    "MAX_MEMBERS_PER_GROUP",
    "MAX_TOTAL_MEMBERSHIPS",
    "StoredWatchlistGroup",
    "StoredWatchlistGroupMember",
    "StoredWatchlistState",
    "WatchlistGroupRepository",
]
