# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""API-level watchlist group contracts with isolated SQLite storage."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

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
        self.fail_updates = False

    def get_config(self, include_schema: bool = False) -> dict:
        return {
            "config_version": self.config_version,
            "items": [{"key": "STOCK_LIST", "value": self.stock_list}],
        }

    def update(self, **kwargs) -> None:
        if self.fail_updates:
            raise RuntimeError("configuration write failed")
        self.stock_list = kwargs["items"][0]["value"]
        self.update_calls.append(self.stock_list)


def _service(tmp_path: Path, name: str) -> WatchlistGroupService:
    return WatchlistGroupService(db_manager=DatabaseManager(db_url=f"sqlite:///{tmp_path / name}"))


def _client(config: FakeSystemConfigService, service: WatchlistGroupService) -> TestClient:
    app = FastAPI()
    app.include_router(endpoints.router, prefix="/api/v1/stocks")
    app.dependency_overrides[endpoints.get_system_config_service] = lambda: config
    app.dependency_overrides[endpoints.get_watchlist_group_service] = lambda: service
    return TestClient(app, raise_server_exceptions=False)


def test_real_client_validates_revisioned_response_contract(tmp_path: Path) -> None:
    config = FakeSystemConfigService("600519,AAPL")
    service = _service(tmp_path, "api-real-client.db")
    client = _client(config, service)

    listed = client.get("/api/v1/stocks/watchlist/groups")
    assert listed.status_code == 200
    payload = listed.json()
    assert payload["revision"] >= 1
    assert datetime.fromisoformat(payload["groups"][0]["created_at"]).tzinfo is not None

    created = client.post(
        "/api/v1/stocks/watchlist/groups",
        json={"name": "Core", "expected_revision": payload["revision"]},
    )
    assert created.status_code == 200
    assert created.json()["revision"] > payload["revision"]

    stale = client.post(
        "/api/v1/stocks/watchlist/groups",
        json={"name": "Stale", "expected_revision": payload["revision"]},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["error"] == "watchlist_group_revision_conflict"
    assert stale.json()["detail"]["params"]["current_revision"] == created.json()["revision"]


def test_revisioned_api_flow_and_strict_json(tmp_path: Path) -> None:
    config = FakeSystemConfigService("600519,AAPL,300750")
    service = _service(tmp_path, "api-flow.db")
    listed = endpoints.list_watchlist_groups(service=config, group_service=service)
    created = endpoints.create_watchlist_group(
        WatchlistGroupCreateRequest(name="Core", expected_revision=listed.revision),
        group_service=service,
    )
    core_id = next(group.id for group in created.groups if group.name == "Core")
    renamed = endpoints.rename_watchlist_group(
        core_id,
        WatchlistGroupRenameRequest(name="Core Holdings", expected_revision=created.revision),
        group_service=service,
    )
    reordered = endpoints.reorder_watchlist_groups(
        WatchlistGroupReorderRequest(
            ordered_ids=[core_id, "default"], expected_revision=renamed.revision
        ),
        group_service=service,
    )
    added = endpoints.add_watchlist_group_member(
        core_id,
        WatchlistGroupMemberAddRequest(
            stock_code="600519", expected_revision=reordered.revision
        ),
        service=config,
        group_service=service,
    )
    moved = endpoints.move_watchlist_group_member(
        WatchlistGroupMemberMoveRequest(
            stock_code="AAPL",
            source_group_id="default",
            target_group_id=core_id,
            target_index=0,
            copy_membership=False,
            expected_revision=added.revision,
        ),
        group_service=service,
    )
    core = next(group for group in moved.groups if group.id == core_id)
    final = endpoints.reorder_watchlist_group_members(
        core_id,
        WatchlistGroupMemberReorderRequest(
            ordered_codes=[member.stock_code for member in reversed(core.members)],
            expected_revision=moved.revision,
        ),
        group_service=service,
    )
    json.dumps(final.model_dump(mode="json"), allow_nan=False)
    assert final.revision > listed.revision


def test_alias_add_updates_authority_before_group_projection(tmp_path: Path) -> None:
    config = FakeSystemConfigService("AAPL")
    service = _service(tmp_path, "api-authority.db")
    listed = endpoints.list_watchlist_groups(service=config, group_service=service)
    response = endpoints.add_watchlist_group_member(
        "default",
        WatchlistGroupMemberAddRequest(stock_code="00700.HK", expected_revision=listed.revision),
        service=config,
        group_service=service,
    )
    assert config.stock_list == "AAPL,HK00700"
    assert [member.stock_code for member in response.groups[0].members] == ["AAPL", "HK00700"]


def test_authority_failure_does_not_create_group_membership(tmp_path: Path) -> None:
    config = FakeSystemConfigService("AAPL")
    service = _service(tmp_path, "api-authority-failure.db")
    listed = endpoints.list_watchlist_groups(service=config, group_service=service)
    config.fail_updates = True

    with pytest.raises(HTTPException) as exc:
        endpoints.add_watchlist_group_member(
            "default",
            WatchlistGroupMemberAddRequest(
                stock_code="00700.HK", expected_revision=listed.revision
            ),
            service=config,
            group_service=service,
        )

    assert exc.value.status_code == 500
    config.fail_updates = False
    recovered = endpoints.list_watchlist_groups(service=config, group_service=service)
    assert [member.stock_code for member in recovered.groups[0].members] == ["AAPL"]


def test_group_failure_after_authority_commit_repairs_into_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = FakeSystemConfigService("AAPL")
    service = _service(tmp_path, "api-group-failure.db")
    listed = endpoints.list_watchlist_groups(service=config, group_service=service)

    with monkeypatch.context() as scoped:
        scoped.setattr(
            service,
            "add_member",
            lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("group write failed")),
        )
        with pytest.raises(HTTPException) as exc:
            endpoints.add_watchlist_group_member(
                "default",
                WatchlistGroupMemberAddRequest(
                    stock_code="00700.HK", expected_revision=listed.revision
                ),
                service=config,
                group_service=service,
            )

    assert exc.value.status_code == 500
    assert config.stock_list == "AAPL,HK00700"
    recovered = endpoints.list_watchlist_groups(service=config, group_service=service)
    assert [member.stock_code for member in recovered.groups[0].members] == [
        "AAPL",
        "HK00700",
    ]


def test_member_add_schema_rejects_arbitrary_non_finite_attrs() -> None:
    with pytest.raises(ValidationError):
        WatchlistGroupMemberAddRequest(
            stock_code="AAPL",
            expected_revision=1,
            attrs={"ai_score": float("nan")},
        )


def test_public_500_never_leaks_internal_exception_text(tmp_path: Path, monkeypatch) -> None:
    config = FakeSystemConfigService("AAPL")
    service = _service(tmp_path, "api-error.db")

    def fail(*, stock_list_codes):
        raise RuntimeError("database at /secret/customer/path failed")

    monkeypatch.setattr(service, "list_state", fail)
    with pytest.raises(HTTPException) as exc:
        endpoints.list_watchlist_groups(service=config, group_service=service)
    assert exc.value.status_code == 500
    assert exc.value.detail["error"] == "internal_error"
    assert exc.value.detail["message"] == "Watchlist group operation failed"
    assert "/secret/customer/path" not in str(exc.value.detail)
