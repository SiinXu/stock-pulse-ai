# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Watchlist group service compatibility and membership contracts."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect

from src.migrations.versions.v202608090001_watchlist_groups_schema import (
    MIGRATION as WATCHLIST_GROUPS_MIGRATION,
    downgrade as downgrade_watchlist_groups,
    upgrade as upgrade_watchlist_groups,
)
from src.services.watchlist_group_service import (
    WatchlistGroupService,
    WatchlistGroupServiceError,
)
from src.storage import DatabaseManager


@pytest.fixture(autouse=True)
def _reset_db_singleton():
    DatabaseManager.reset_instance()
    yield
    DatabaseManager.reset_instance()


def _db(tmp_path: Path, name: str) -> DatabaseManager:
    return DatabaseManager(db_url=f"sqlite:///{tmp_path / name}")


def test_upgrade_seeds_existing_stock_list_into_default_group(tmp_path: Path) -> None:
    service = WatchlistGroupService(db_manager=_db(tmp_path, "watchlist-groups.db"))

    groups = service.list_groups(stock_list_codes=["600519", "AAPL", "hk00700"])

    assert len(groups) == 1
    assert groups[0].id == "default"
    assert groups[0].is_default is True
    codes = [member.stock_code for member in groups[0].members]
    assert codes == ["600519", "AAPL", "hk00700"]

    again = service.list_groups(stock_list_codes=["600519", "AAPL", "hk00700"])
    assert [member.stock_code for member in again[0].members] == codes


def test_multi_group_membership_and_move(tmp_path: Path) -> None:
    service = WatchlistGroupService(db_manager=_db(tmp_path, "watchlist-groups-move.db"))
    service.list_groups(stock_list_codes=["600519", "AAPL"])

    growth = service.create_group(name="Growth")
    service.add_member(group_id=growth.id, stock_code="AAPL")
    groups = service.list_groups(stock_list_codes=["600519", "AAPL"])
    by_id = {group.id: group for group in groups}
    assert any(member.stock_code == "AAPL" for member in by_id["default"].members)
    assert any(member.stock_code == "AAPL" for member in by_id[growth.id].members)

    service.move_member(
        stock_code="600519",
        source_group_id="default",
        target_group_id=growth.id,
        target_index=0,
        copy=False,
    )
    groups = service.list_groups(stock_list_codes=["600519", "AAPL"])
    by_id = {group.id: group for group in groups}
    default_codes = [member.stock_code for member in by_id["default"].members]
    growth_codes = [member.stock_code for member in by_id[growth.id].members]
    assert "600519" not in default_codes
    assert growth_codes[0] == "600519"


def test_member_attrs_mount_point(tmp_path: Path) -> None:
    service = WatchlistGroupService(db_manager=_db(tmp_path, "watchlist-groups-attrs.db"))
    service.list_groups(stock_list_codes=["600519"])
    growth = service.create_group(name="Focus")
    service.add_member(
        group_id=growth.id,
        stock_code="600519",
        attrs={"score": 82, "focus": True},
    )
    groups = service.list_groups(stock_list_codes=["600519"])
    focus = next(group for group in groups if group.id == growth.id)
    member = next(item for item in focus.members if item.stock_code == "600519")
    assert member.attrs == {"score": 82, "focus": True}


def test_cannot_delete_default_group(tmp_path: Path) -> None:
    service = WatchlistGroupService(db_manager=_db(tmp_path, "watchlist-groups-default.db"))
    service.list_groups(stock_list_codes=["600519"])
    with pytest.raises(WatchlistGroupServiceError) as exc:
        service.delete_group(group_id="default")
    assert exc.value.error_code == "watchlist_group_default_delete_forbidden"


def test_migration_upgrade_and_downgrade_roundtrip(tmp_path: Path) -> None:
    """Schema migration is idempotent and manually reversible without touching STOCK_LIST."""
    db_path = tmp_path / "watchlist-groups-migration.db"
    # Bootstrap a fully migrated DB, then exercise downgrade/upgrade helpers.
    manager = DatabaseManager(db_url=f"sqlite:///{db_path}")
    engine = manager._engine
    tables = set(inspect(engine).get_table_names())
    assert "watchlist_groups" in tables
    assert "watchlist_group_members" in tables

    with engine.begin() as connection:
        class _Exec:
            def exec_driver_sql(self, statement, parameters=None):
                return connection.exec_driver_sql(statement, parameters)

        downgrade_watchlist_groups(_Exec())
    tables_after = set(inspect(engine).get_table_names())
    assert "watchlist_groups" not in tables_after
    assert "watchlist_group_members" not in tables_after

    with engine.begin() as connection:
        class _Exec:
            def exec_driver_sql(self, statement, parameters=None):
                return connection.exec_driver_sql(statement, parameters)

        upgrade_watchlist_groups(_Exec())
        upgrade_watchlist_groups(_Exec())
    tables_restored = set(inspect(engine).get_table_names())
    assert "watchlist_groups" in tables_restored
    assert "watchlist_group_members" in tables_restored
    assert WATCHLIST_GROUPS_MIGRATION.id.endswith("watchlist_groups_schema")


def test_remove_from_watchlist_hook_clears_memberships(tmp_path: Path) -> None:
    service = WatchlistGroupService(db_manager=_db(tmp_path, "watchlist-groups-remove.db"))
    service.list_groups(stock_list_codes=["600519", "AAPL"])
    service.on_watchlist_code_removed("600519")
    groups = service.list_groups(stock_list_codes=["AAPL"])
    codes = [member.stock_code for group in groups for member in group.members]
    assert "600519" not in codes
    assert "AAPL" in codes
