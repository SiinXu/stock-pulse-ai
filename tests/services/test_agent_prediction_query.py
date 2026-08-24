# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Unit tests for allowlisted prediction query projection."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, List, Optional

import pytest
from pydantic import ValidationError

from src.api.v1.schemas.agent_predictions import AgentPredictionListQuery
from src.schemas.agent_prediction import (
    STATUS_DATA_UNAVAILABLE,
    STATUS_PENDING,
    STATUS_RESOLVED,
    AgentPredictionRecord,
)
from src.services.agent_prediction_query import (
    AgentPredictionFilterError,
    AgentPredictionNotFoundError,
    AgentPredictionQueryService,
    project_outcome_label,
    project_prediction_item,
)


def _record(**overrides: Any) -> AgentPredictionRecord:
    values = dict(
        prediction_id="pred-1",
        run_id="run-1",
        symbol="600519",
        market="cn",
        as_of=date(2026, 8, 23),
        horizon="5d",
        resolve_after=datetime(2026, 8, 24, 11, 0, 0),
        status=STATUS_PENDING,
        claims=[{"claim_id": "c1"}],
        created_at=datetime(2026, 8, 23, 12, 0, 0),
        updated_at=datetime(2026, 8, 23, 12, 0, 0),
        outcome=None,
        model_meta={"soul": "secret"},
        notes="private",
        lease_token="lease-1",
        lease_owner="worker-1",
        actor_id="system",
    )
    values.update(overrides)
    return AgentPredictionRecord(**values)


class _FakeStore:
    def __init__(self, rows: List[AgentPredictionRecord]) -> None:
        self.rows = rows
        self.calls: List[Any] = []

    def get(self, prediction_id: str) -> Optional[AgentPredictionRecord]:
        self.calls.append(("get", prediction_id))
        for row in self.rows:
            if row.prediction_id == prediction_id:
                return row
        return None

    def list_by_run_id(self, run_id: str, *, limit: int = 50) -> List[AgentPredictionRecord]:
        self.calls.append(("list_by_run_id", run_id, limit))
        return [row for row in self.rows if row.run_id == run_id][:limit]

    def list_by_symbol_market(
        self, *, symbol: str, market: str, limit: int = 50
    ) -> List[AgentPredictionRecord]:
        self.calls.append(("list_by_symbol_market", symbol, market, limit))
        return [
            row
            for row in self.rows
            if row.symbol == symbol and row.market == market.lower()
        ][:limit]

    def list_due(self, *args: Any, **kwargs: Any) -> List[AgentPredictionRecord]:
        raise AssertionError("query service must not call list_due")

    def claim_for_resolve(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("query service must not claim")

    def resolve(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("query service must not resolve")

    def requeue_pending(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("query service must not requeue")


def test_project_outcome_label_fail_closed_and_data_unavailable() -> None:
    pending = _record()
    hit = _record(status=STATUS_RESOLVED, outcome={"label": "hit", "score": 1.0})
    mystery = _record(status=STATUS_RESOLVED, outcome={"label": "mystery"})
    missing = _record(status=STATUS_RESOLVED, outcome={"score": 1.0})
    unavailable = _record(status=STATUS_DATA_UNAVAILABLE, outcome={"reason": "timeout"})
    assert project_outcome_label(pending) is None
    assert project_outcome_label(hit) == "hit"
    assert project_outcome_label(mystery) is None
    assert project_outcome_label(missing) is None
    assert project_outcome_label(unavailable) == "data_unavailable"


def test_project_prediction_item_omits_store_secrets() -> None:
    item = project_prediction_item(
        _record(status=STATUS_RESOLVED, outcome={"label": "miss", "score": 0.0})
    )
    assert item["outcome_label"] == "miss"
    assert item["status"] == STATUS_RESOLVED
    assert item["market"] == "cn"
    assert item["as_of"] == "2026-08-23"
    assert item["resolve_after"].endswith("+00:00")
    assert "outcome" not in item
    assert "claims" not in item
    assert "lease_token" not in item
    assert "model_meta" not in item
    assert "notes" not in item
    assert "soul" not in item
    assert "score" not in item
    assert "actor_id" not in item


def test_query_service_get_and_list_use_indexed_readers_only() -> None:
    rows = [
        _record(prediction_id="pred-1", run_id="run-1"),
        _record(prediction_id="pred-2", run_id="run-1", symbol="600519"),
        _record(prediction_id="pred-us", run_id="run-us", symbol="AAPL", market="us"),
    ]
    store = _FakeStore(rows)
    service = AgentPredictionQueryService(store=store)

    missing = None
    try:
        service.get_prediction("missing")
    except AgentPredictionNotFoundError as exc:
        missing = exc
    assert missing is not None

    got = service.get_prediction("pred-1")
    assert got["prediction_id"] == "pred-1"
    listed = service.list_predictions(run_id="run-1", limit=50)
    assert [item["prediction_id"] for item in listed["items"]] == ["pred-1", "pred-2"]
    assert listed["truncated"] is False
    by_symbol = service.list_predictions(symbol="AAPL", market="US", limit=10)
    assert [item["prediction_id"] for item in by_symbol["items"]] == ["pred-us"]
    names = [call[0] for call in store.calls]
    assert names == ["get", "get", "list_by_run_id", "list_by_symbol_market"]


def test_query_service_clamps_public_limit_and_flags_truncation() -> None:
    rows = [_record(prediction_id=f"pred-{index:02d}") for index in range(51)]
    store = _FakeStore(rows)
    service = AgentPredictionQueryService(store=store)
    payload = service.list_predictions(run_id="run-1", limit=51)
    assert len(payload["items"]) == 50
    assert payload["truncated"] is True
    assert store.calls[-1] == ("list_by_run_id", "run-1", 50)


def test_query_service_rejects_invalid_filter_modes() -> None:
    service = AgentPredictionQueryService(store=_FakeStore([]))
    with pytest.raises(AgentPredictionFilterError, match="exactly one identity filter"):
        service.list_predictions()
    with pytest.raises(AgentPredictionFilterError, match="exactly one identity filter"):
        service.list_predictions(run_id="run-1", symbol="600519")
    with pytest.raises(AgentPredictionFilterError, match="exactly one identity filter"):
        service.list_predictions(symbol="600519")


def test_list_query_schema_enforces_xor_and_extra_forbid() -> None:
    run_mode = AgentPredictionListQuery.model_validate({"run_id": "run-1"})
    assert run_mode.limit == 50
    symbol_mode = AgentPredictionListQuery.model_validate(
        {"symbol": "600519", "market": "CN"}
    )
    assert symbol_mode.market == "cn"
    with pytest.raises(ValidationError):
        AgentPredictionListQuery.model_validate({})
    with pytest.raises(ValidationError):
        AgentPredictionListQuery.model_validate({"symbol": "600519"})
    with pytest.raises(ValidationError):
        AgentPredictionListQuery.model_validate(
            {"run_id": "run-1", "symbol": "600519", "market": "cn"}
        )
    with pytest.raises(ValidationError):
        AgentPredictionListQuery.model_validate({"run_id": "run-1", "limit": 51})
    with pytest.raises(ValidationError):
        AgentPredictionListQuery.model_validate({"run_id": "run-1", "status": "pending"})
