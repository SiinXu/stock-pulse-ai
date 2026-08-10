# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Watchlist group authority, identity, concurrency, and migration contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import inspect, update

from src.migrations.versions.v202608090001_watchlist_groups_schema import (
    MIGRATION as WATCHLIST_GROUPS_MIGRATION,
    downgrade as downgrade_watchlist_groups,
    upgrade as upgrade_watchlist_groups,
)
from src.repositories.watchlist_group_repo import MAX_MEMBERS_PER_GROUP
from src.repositories.watchlist_group_tables import watchlist_group_members_table
from src.services.watchlist_group_service import (
    WatchlistGroupConflictError,
    WatchlistGroupService,
    WatchlistGroupServiceError,
    group_state_to_payload,
)
from src.storage import DatabaseManager


@pytest.fixture(autouse=True)
def _reset_db_singleton():
    DatabaseManager.reset_instance()
    yield
    DatabaseManager.reset_instance()


def _db(tmp_path: Path, name: str) -> DatabaseManager:
    return DatabaseManager(db_url=f"sqlite:///{tmp_path / name}")


def test_upgrade_canonicalizes_and_seeds_existing_stock_list(tmp_path: Path) -> None:
    service = WatchlistGroupService(db_manager=_db(tmp_path, "watchlist-groups.db"))

    state = service.list_state(
        stock_list_codes=["600519", "AAPL", "00700.HK", "hk00700", "00700"]
    )

    assert state.revision >= 1
    assert len(state.groups) == 1
    assert state.groups[0].id == "default"
    assert state.groups[0].name_key == "watchlist.defaultGroupName"
    assert [member.stock_code for member in state.groups[0].members] == [
        "600519",
        "AAPL",
        "HK00700",
    ]
    assert state.groups[0].created_at.endswith("+00:00")


def test_authoritative_reconciliation_prunes_ghosts_and_repairs_aliases(tmp_path: Path) -> None:
    service = WatchlistGroupService(db_manager=_db(tmp_path, "watchlist-reconcile.db"))
    initial = service.list_state(stock_list_codes=["00700.HK", "AAPL"])
    created = service.create_group(name="Growth", expected_revision=initial.revision)
    growth = next(group for group in created.groups if group.name == "Growth")
    service.add_member(
        group_id=growth.id,
        stock_code="HK00700",
        expected_revision=created.revision,
    )

    reconciled = service.list_state(stock_list_codes=["AAPL"])

    codes = [member.stock_code for group in reconciled.groups for member in group.members]
    assert "HK00700" not in codes
    assert codes.count("AAPL") == 1


def test_multi_group_move_is_revisioned_and_contiguous(tmp_path: Path) -> None:
    service = WatchlistGroupService(db_manager=_db(tmp_path, "watchlist-move.db"))
    initial = service.list_state(stock_list_codes=["600519", "AAPL"])
    created = service.create_group(name="Growth", expected_revision=initial.revision)
    growth = next(group for group in created.groups if group.name == "Growth")
    copied = service.add_member(
        group_id=growth.id,
        stock_code="AAPL",
        expected_revision=created.revision,
    )
    moved = service.move_member(
        stock_code="600519",
        source_group_id="default",
        target_group_id=growth.id,
        target_index=0,
        copy=False,
        expected_revision=copied.revision,
    )

    by_id = {group.id: group for group in moved.groups}
    assert [member.stock_code for member in by_id[growth.id].members] == ["600519", "AAPL"]
    for group in moved.groups:
        assert [member.sort_order for member in group.members] == list(range(len(group.members)))


def test_reorder_requires_exact_unique_current_set_and_fresh_revision(tmp_path: Path) -> None:
    service = WatchlistGroupService(db_manager=_db(tmp_path, "watchlist-reorder.db"))
    initial = service.list_state(stock_list_codes=["600519", "AAPL"])
    created = service.create_group(name="Core", expected_revision=initial.revision)
    core = next(group for group in created.groups if group.name == "Core")

    with pytest.raises(WatchlistGroupServiceError) as invalid:
        service.reorder_groups(
            ordered_ids=[core.id, core.id, "missing"],
            expected_revision=created.revision,
        )
    assert invalid.value.error_code == "watchlist_group_reorder_invalid"

    reordered = service.reorder_groups(
        ordered_ids=[core.id, "default"],
        expected_revision=created.revision,
    )
    assert [group.sort_order for group in reordered.groups] == [0, 1]
    with pytest.raises(WatchlistGroupConflictError) as stale:
        service.reorder_groups(
            ordered_ids=["default", core.id],
            expected_revision=created.revision,
        )
    assert stale.value.current_revision == reordered.revision


def test_member_reorder_and_mutations_reject_stale_or_inexact_state(tmp_path: Path) -> None:
    service = WatchlistGroupService(db_manager=_db(tmp_path, "watchlist-concurrency.db"))
    initial = service.list_state(stock_list_codes=["600519", "AAPL"])
    created = service.create_group(name="Core", expected_revision=initial.revision)
    core = next(group for group in created.groups if group.name == "Core")

    with pytest.raises(WatchlistGroupConflictError):
        service.create_group(name="Stale", expected_revision=initial.revision)
    with pytest.raises(WatchlistGroupServiceError) as invalid_members:
        service.reorder_members(
            group_id="default",
            ordered_codes=["600519", "600519"],
            expected_revision=created.revision,
        )
    assert invalid_members.value.error_code == "watchlist_group_member_reorder_invalid"

    newest = service.create_group(name="Growth", expected_revision=created.revision)
    with pytest.raises(WatchlistGroupConflictError):
        service.move_member(
            stock_code="600519",
            source_group_id="default",
            target_group_id=core.id,
            expected_revision=created.revision,
        )
    with pytest.raises(WatchlistGroupConflictError):
        service.delete_group(group_id=core.id, expected_revision=created.revision)
    assert newest.revision > created.revision


def test_computed_attrs_are_typed_finite_and_strict_json(tmp_path: Path) -> None:
    service = WatchlistGroupService(db_manager=_db(tmp_path, "watchlist-attrs.db"))
    state = service.list_state(stock_list_codes=["600519"])
    member = state.groups[0].members[0]
    assert member.attrs == {"schema_version": 1}
    json.dumps(group_state_to_payload(state), allow_nan=False)

    with service.repo.db.get_session() as session:
        session.execute(
            update(watchlist_group_members_table).values(
                attrs_json='{"ai_score": NaN, "focus": true, "unknown": "discarded"}'
            )
        )
        session.commit()
    sanitized = service.list_state(stock_list_codes=["600519"])
    assert sanitized.groups[0].members[0].attrs == {
        "schema_version": 1,
        "focus": True,
    }
    json.dumps(group_state_to_payload(sanitized), allow_nan=False)


def test_reconciliation_rejects_an_unbounded_authoritative_watchlist(tmp_path: Path) -> None:
    service = WatchlistGroupService(db_manager=_db(tmp_path, "watchlist-limit.db"))
    with pytest.raises(WatchlistGroupServiceError) as exc:
        service.list_state(
            stock_list_codes=[f"SYMBOL{index}" for index in range(MAX_MEMBERS_PER_GROUP + 1)]
        )
    assert exc.value.error_code == "watchlist_group_member_limit_reached"


def test_cannot_delete_default_group(tmp_path: Path) -> None:
    service = WatchlistGroupService(db_manager=_db(tmp_path, "watchlist-default.db"))
    state = service.list_state(stock_list_codes=["600519"])
    with pytest.raises(WatchlistGroupServiceError) as exc:
        service.delete_group(group_id="default", expected_revision=state.revision)
    assert exc.value.error_code == "watchlist_group_default_delete_forbidden"


def test_migration_upgrade_and_downgrade_roundtrip(tmp_path: Path) -> None:
    db_path = tmp_path / "watchlist-migration.db"
    manager = DatabaseManager(db_url=f"sqlite:///{db_path}")
    engine = manager._engine
    tables = set(inspect(engine).get_table_names())
    assert {"watchlist_groups", "watchlist_group_members", "watchlist_group_state"} <= tables

    with engine.begin() as connection:
        class _Exec:
            def exec_driver_sql(self, statement, parameters=None):
                return connection.exec_driver_sql(statement, parameters)

        downgrade_watchlist_groups(_Exec())
    assert not {"watchlist_groups", "watchlist_group_members", "watchlist_group_state"} & set(
        inspect(engine).get_table_names()
    )

    with engine.begin() as connection:
        class _Exec:
            def exec_driver_sql(self, statement, parameters=None):
                return connection.exec_driver_sql(statement, parameters)

        upgrade_watchlist_groups(_Exec())
        upgrade_watchlist_groups(_Exec())
        connection.exec_driver_sql(
            "INSERT INTO watchlist_groups "
            "(id, group_key, name, sort_order, is_default, created_at, updated_at) "
            "VALUES (99, 'cascade', 'Cascade', 0, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        connection.exec_driver_sql(
            "INSERT INTO watchlist_group_members "
            "(group_id, stock_code, sort_order, attrs_json, created_at, updated_at) "
            "VALUES (99, 'AAPL', 0, '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        connection.exec_driver_sql("DELETE FROM watchlist_groups WHERE id = 99")
        assert connection.exec_driver_sql(
            "SELECT COUNT(*) FROM watchlist_group_members WHERE group_id = 99"
        ).scalar_one() == 0
    assert {"watchlist_groups", "watchlist_group_members", "watchlist_group_state"} <= set(
        inspect(engine).get_table_names()
    )
    assert WATCHLIST_GROUPS_MIGRATION.id.endswith("watchlist_groups_schema")
