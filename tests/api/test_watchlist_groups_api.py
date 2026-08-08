# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""API-level watchlist group contracts with isolated SQLite storage."""

from __future__ import annotations

from pathlib import Path

import pytest

from api.v1.endpoints import watchlist_groups as endpoints
from api.v1.schemas.watchlist_groups import (
    WatchlistGroupCreateRequest,
    WatchlistGroupMemberAddRequest,
    WatchlistGroupMemberMoveRequest,
    WatchlistGroupMemberReorderRequest,
    WatchlistGroupRenameRequest,
    WatchlistGroupReorderRequest,
)
from src.services.watchlist_group_service import WatchlistGroupService
from src.storage import DatabaseManager


@pytest.fixture(autouse=True)
def _reset_db_singleton():
    DatabaseManager.reset_instance()
    yield
    DatabaseManager.reset_instance()


class FakeSystemConfigService:
    def __init__(self, stock_list: str) -> None:
        self.stock_list = stock_list
        self.config_version = "cfg-v1"
        self.update_calls: list[str] = []

    def get_config(self, include_schema: bool = False) -> dict:
        return {
            "config_version": self.config_version,
            "items": [{"key": "STOCK_LIST", "value": self.stock_list}],
        }

    def update(self, **kwargs) -> None:
        items = kwargs["items"]
        self.stock_list = items[0]["value"]
        self.update_calls.append(self.stock_list)


def _service(tmp_path: Path, name: str) -> WatchlistGroupService:
    return WatchlistGroupService(
        db_manager=DatabaseManager(db_url=f"sqlite:///{tmp_path / name}")
    )


def test_list_groups_seeds_stock_list(tmp_path: Path) -> None:
    config = FakeSystemConfigService("600519,AAPL")
    group_service = _service(tmp_path, "api-list.db")

    response = endpoints.list_watchlist_groups(
        service=config,
        group_service=group_service,
    )

    assert len(response.groups) == 1
    assert response.groups[0].id == "default"
    assert [member.stock_code for member in response.groups[0].members] == [
        "600519",
        "AAPL",
    ]


def test_create_rename_reorder_and_move(tmp_path: Path) -> None:
    config = FakeSystemConfigService("600519,AAPL,300750")
    group_service = _service(tmp_path, "api-flow.db")

    endpoints.list_watchlist_groups(service=config, group_service=group_service)
    created = endpoints.create_watchlist_group(
        WatchlistGroupCreateRequest(name="Core"),
        service=config,
        group_service=group_service,
    )
    core_id = next(group.id for group in created.groups if group.name == "Core")

    renamed = endpoints.rename_watchlist_group(
        core_id,
        WatchlistGroupRenameRequest(name="Core Holdings"),
        service=config,
        group_service=group_service,
    )
    assert any(group.name == "Core Holdings" for group in renamed.groups)

    reordered = endpoints.reorder_watchlist_groups(
        WatchlistGroupReorderRequest(ordered_ids=[core_id, "default"]),
        service=config,
        group_service=group_service,
    )
    assert reordered.groups[0].id == core_id

    endpoints.add_watchlist_group_member(
        core_id,
        WatchlistGroupMemberAddRequest(stock_code="600519"),
        service=config,
        group_service=group_service,
    )
    moved = endpoints.move_watchlist_group_member(
        WatchlistGroupMemberMoveRequest(
            stock_code="AAPL",
            source_group_id="default",
            target_group_id=core_id,
            target_index=0,
            copy_membership=False,
        ),
        service=config,
        group_service=group_service,
    )
    core = next(group for group in moved.groups if group.id == core_id)
    assert core.members[0].stock_code == "AAPL"

    reordered_members = endpoints.reorder_watchlist_group_members(
        core_id,
        WatchlistGroupMemberReorderRequest(
            ordered_codes=[member.stock_code for member in reversed(core.members)]
        ),
        service=config,
        group_service=group_service,
    )
    core_after = next(group for group in reordered_members.groups if group.id == core_id)
    assert [member.stock_code for member in core_after.members] == [
        member.stock_code for member in reversed(core.members)
    ]
