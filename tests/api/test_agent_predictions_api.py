# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""HTTP contract tests for authenticated prediction get-by-id and list APIs."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, List, Optional, Set
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

try:
    import litellm  # noqa: F401
except ModuleNotFoundError:
    sys.modules["litellm"] = MagicMock()

import src.auth as auth
from src.api.app import create_app
from src.api.middlewares.auth import EXEMPT_PATHS
from src.config import Config
from src.repositories.agent_prediction_repo import AgentPredictionRepository
from src.schemas.agent_prediction import (
    STATUS_DATA_UNAVAILABLE,
    STATUS_PENDING,
    STATUS_RESOLVED,
    AgentPredictionInsert,
)
from src.services.prediction_resolver.resolver import PredictionResolver
from src.storage import DatabaseManager


GET_PATH = "/api/v1/agent/predictions/{prediction_id}"
LIST_PATH = "/api/v1/agent/predictions"
FEEDBACK_PATH = "/api/v1/agent/predictions/{prediction_id}/feedback"
DIAGNOSTICS_PATH = "/api/v1/agent/prediction-resolver/diagnostics"
COLLISION_PATH = "/api/v1/agent/predictions/resolver-diagnostics"

ITEM_ALLOWLIST = {
    "prediction_id",
    "run_id",
    "symbol",
    "market",
    "as_of",
    "horizon",
    "resolve_after",
    "status",
    "outcome_label",
    "created_at",
    "updated_at",
    "resolved_at",
}
LIST_ALLOWLIST = {"items", "truncated"}
FORBIDDEN_KEYS = frozenset(
    {
        "outcome",
        "outcome_json",
        "claims",
        "claims_json",
        "notes",
        "lease_token",
        "lease_owner",
        "lease_expires_at",
        "model_meta",
        "start_price",
        "end_price",
        "high_price",
        "low_price",
        "actor_id",
        "provenance_source",
        "attempts",
        "today_resolve_counts",
        "last_tick",
        "last_tick_at",
        "stuck",
        "never_ticked",
        "resolver_state",
        "postmortem_queue_depth",
        "adapter_updates_total",
        "actuals_fetch_errors",
        "soul",
        "api_key",
        "api_keys",
        "openai_api_key",
        "gemini_api_key",
        "secret",
        "secrets",
        "provider_body",
        "raw_body",
        "score",
        "retry_exhausted",
    }
)


def _reset_auth_globals() -> None:
    auth._auth_enabled = None
    auth._session_secret = None
    auth._password_hash_salt = None
    auth._password_hash_stored = None
    auth._rate_limit = {}


def _fixed_now() -> datetime:
    return datetime(2026, 8, 24, 12, 0, 0)


def _direction_claim() -> dict:
    return {
        "claim_id": "direction-0",
        "type": "direction",
        "confidence": 0.7,
        "payload": {"direction": "up"},
    }


def _collect_keys(value: Any, into: Optional[Set[str]] = None) -> Set[str]:
    keys: Set[str] = set() if into is None else into
    if isinstance(value, dict):
        for key, nested in value.items():
            keys.add(str(key))
            _collect_keys(nested, keys)
    elif isinstance(value, list):
        for item in value:
            _collect_keys(item, keys)
    return keys


def _assert_no_forbidden_keys(payload: Any, *, allow_items: bool = False) -> None:
    found = _collect_keys(payload)
    forbidden = set(FORBIDDEN_KEYS)
    if not allow_items:
        forbidden.add("items")
    leaked = sorted(found & forbidden)
    assert leaked == [], f"forbidden keys present: {leaked}"


def _insert_prediction(
    db: DatabaseManager,
    *,
    prediction_id: str = "pred-1",
    run_id: str = "run-1",
    symbol: str = "600519",
    market: str = "cn",
    created_at: Optional[datetime] = None,
) -> None:
    repo = AgentPredictionRepository(db, clock=_fixed_now)
    created, record = repo.insert_pending(
        AgentPredictionInsert(
            prediction_id=prediction_id,
            run_id=run_id,
            symbol=symbol,
            market=market,
            as_of=_fixed_now().date(),
            horizon="5d",
            resolve_after=_fixed_now() - timedelta(hours=1),
            claims=[_direction_claim()],
            created_at=created_at or (_fixed_now() - timedelta(days=1)),
        )
    )
    assert created is True
    assert record.status == STATUS_PENDING


def _resolve_prediction(
    db: DatabaseManager,
    prediction_id: str,
    outcome: Optional[dict] = None,
) -> dict:
    pred_repo = AgentPredictionRepository(db, clock=_fixed_now)
    applied, resolved = pred_repo.resolve(
        prediction_id=prediction_id,
        outcome=outcome or {"label": "hit", "score": 1.0},
        as_of=_fixed_now(),
    )
    assert applied is True
    assert resolved is not None
    assert resolved.status == STATUS_RESOLVED
    return dict(resolved.outcome or {})


@pytest.fixture()
def client_and_db(tmp_path, monkeypatch):
    old_env = dict(os.environ)
    env_path = tmp_path / ".env"
    db_path = tmp_path / "agent_predictions_api.db"
    static_dir = tmp_path / "empty-static"
    static_dir.mkdir()
    env_path.write_text(
        "\n".join(
            [
                "STOCK_LIST=600519",
                "GEMINI_API_KEY=test",
                "ADMIN_AUTH_ENABLED=false",
                "PREDICTION_RESOLVE_ENABLED=false",
                f"DATABASE_PATH={db_path}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ENV_FILE", str(env_path))
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    monkeypatch.setenv("ADMIN_AUTH_ENABLED", "false")
    _reset_auth_globals()
    Config.reset_instance()
    DatabaseManager.reset_instance()
    app = create_app(static_dir=Path(static_dir))
    client = TestClient(app)
    db = DatabaseManager.get_instance()
    try:
        yield client, db
    finally:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        _reset_auth_globals()
        os.environ.clear()
        os.environ.update(old_env)


def test_get_pending_prediction_returns_allowlisted_null_label(client_and_db) -> None:
    client, db = client_and_db
    _insert_prediction(db, prediction_id="pred-1")
    response = client.get(GET_PATH.format(prediction_id="pred-1"))
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["prediction_id"] == "pred-1"
    assert payload["run_id"] == "run-1"
    assert payload["symbol"] == "600519"
    assert payload["market"] == "cn"
    assert payload["horizon"] == "5d"
    assert payload["status"] == STATUS_PENDING
    assert payload["outcome_label"] is None
    assert payload["resolved_at"] is None
    assert payload["as_of"] == "2026-08-24"
    assert payload["resolve_after"].endswith("+00:00")
    assert payload["created_at"].endswith("+00:00")
    assert payload["updated_at"].endswith("+00:00")
    assert set(payload) == ITEM_ALLOWLIST
    _assert_no_forbidden_keys(payload)


def test_get_resolved_hit_returns_label_without_outcome_payload(client_and_db) -> None:
    client, db = client_and_db
    _insert_prediction(db, prediction_id="pred-1")
    _resolve_prediction(db, "pred-1", {"label": "hit", "score": 1.0, "start_price": 1.2})
    response = client.get(GET_PATH.format(prediction_id="pred-1"))
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == STATUS_RESOLVED
    assert payload["outcome_label"] == "hit"
    assert payload["resolved_at"] is not None
    assert payload["resolved_at"].endswith("+00:00")
    assert "score" not in payload
    assert set(payload) == ITEM_ALLOWLIST
    _assert_no_forbidden_keys(payload)


def test_get_unexpected_outcome_label_fails_closed(client_and_db) -> None:
    client, db = client_and_db
    _insert_prediction(db, prediction_id="pred-unexpected-label")
    _resolve_prediction(
        db, "pred-unexpected-label", {"label": "mystery", "score": 0.4}
    )
    response = client.get(GET_PATH.format(prediction_id="pred-unexpected-label"))
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == STATUS_RESOLVED
    assert payload["outcome_label"] is None
    assert "mystery" not in response.text
    _assert_no_forbidden_keys(payload)


def test_get_data_unavailable_status_projects_label(client_and_db) -> None:
    client, db = client_and_db
    now = _fixed_now()
    _insert_prediction(db, prediction_id="pred-unavail")
    repo = AgentPredictionRepository(db, clock=lambda: now)
    claimed = repo.claim_for_resolve(
        prediction_id="pred-unavail",
        lease_owner="worker-1",
        lease_token="lease-unavail",
        lease_ttl_seconds=3600,
        as_of=now,
    )
    assert claimed is not None
    applied, marked = repo.mark_data_unavailable(
        prediction_id="pred-unavail",
        reason="provider_down",
        expected_lease_token="lease-unavail",
        as_of=now,
    )
    assert applied is True
    assert marked is not None
    assert marked.status == STATUS_DATA_UNAVAILABLE
    response = client.get(GET_PATH.format(prediction_id="pred-unavail"))
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == STATUS_DATA_UNAVAILABLE
    assert payload["outcome_label"] == "data_unavailable"
    _assert_no_forbidden_keys(payload)


def test_list_by_run_id_returns_matching_rows(client_and_db) -> None:
    client, db = client_and_db
    _insert_prediction(db, prediction_id="pred-1", run_id="run-1")
    _insert_prediction(db, prediction_id="pred-2", run_id="run-1")
    _insert_prediction(db, prediction_id="pred-other", run_id="run-other")
    response = client.get(LIST_PATH, params={"run_id": "run-1"})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert set(payload) == LIST_ALLOWLIST
    assert payload["truncated"] is False
    ids = {item["prediction_id"] for item in payload["items"]}
    assert ids == {"pred-1", "pred-2"}
    assert len(payload["items"]) == 2
    for item in payload["items"]:
        assert set(item) == ITEM_ALLOWLIST
        assert item["run_id"] == "run-1"
    _assert_no_forbidden_keys(payload, allow_items=True)


def test_list_by_symbol_market_normalizes_market_case(client_and_db) -> None:
    client, db = client_and_db
    _insert_prediction(db, prediction_id="pred-cn", symbol="600519", market="CN")
    _insert_prediction(
        db, prediction_id="pred-us", run_id="run-us", symbol="AAPL", market="us"
    )
    response = client.get(LIST_PATH, params={"symbol": "600519", "market": "CN"})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["truncated"] is False
    assert len(payload["items"]) == 1
    assert payload["items"][0]["prediction_id"] == "pred-cn"
    assert payload["items"][0]["market"] == "cn"
    _assert_no_forbidden_keys(payload, allow_items=True)


def test_list_unknown_run_returns_empty_200(client_and_db) -> None:
    client, db = client_and_db
    _insert_prediction(db, prediction_id="pred-1")
    response = client.get(LIST_PATH, params={"run_id": "missing-run"})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload == {"items": [], "truncated": False}
    _assert_no_forbidden_keys(payload, allow_items=True)


def test_get_unknown_id_returns_404_not_found(client_and_db) -> None:
    client, _db = client_and_db
    response = client.get(GET_PATH.format(prediction_id="missing"))
    assert response.status_code == 404, response.text
    payload = response.json()
    assert payload["error"] == "not_found"
    assert "outcome_label" not in payload
    assert "prediction_id" not in payload
    _assert_no_forbidden_keys(payload)


def test_list_rejects_mutually_invalid_filters(client_and_db) -> None:
    client, db = client_and_db
    _insert_prediction(db, prediction_id="pred-1")
    both = client.get(
        LIST_PATH, params={"run_id": "run-1", "symbol": "600519", "market": "cn"}
    )
    run_and_symbol = client.get(LIST_PATH, params={"run_id": "run-1", "symbol": "600519"})
    only_symbol = client.get(LIST_PATH, params={"symbol": "600519"})
    only_market = client.get(LIST_PATH, params={"market": "cn"})
    none = client.get(LIST_PATH)
    for response in (both, run_and_symbol, only_symbol, only_market, none):
        assert response.status_code == 422, response.text
        assert "items" not in response.json()


def test_list_rejects_limit_outside_public_cap(client_and_db) -> None:
    client, db = client_and_db
    _insert_prediction(db, prediction_id="pred-1")
    too_high = client.get(LIST_PATH, params={"run_id": "run-1", "limit": 51})
    zero = client.get(LIST_PATH, params={"run_id": "run-1", "limit": 0})
    negative = client.get(LIST_PATH, params={"run_id": "run-1", "limit": -1})
    for response in (too_high, zero, negative):
        assert response.status_code == 422, response.text


def test_list_limit_50_truncates_when_more_rows_exist(client_and_db) -> None:
    client, db = client_and_db
    for index in range(51):
        _insert_prediction(
            db,
            prediction_id=f"pred-{index:02d}",
            run_id="run-many",
            created_at=_fixed_now() - timedelta(days=1, seconds=index),
        )
    response = client.get(LIST_PATH, params={"run_id": "run-many", "limit": 50})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload["items"]) == 50
    assert payload["truncated"] is True
    _assert_no_forbidden_keys(payload, allow_items=True)


def test_list_rejects_extra_query_key(client_and_db) -> None:
    client, db = client_and_db
    _insert_prediction(db, prediction_id="pred-1")
    response = client.get(
        LIST_PATH, params={"run_id": "run-1", "status": "pending"}
    )
    assert response.status_code == 422, response.text
    assert "items" not in response.json()


def test_get_and_list_do_not_write_or_tick(client_and_db, monkeypatch) -> None:
    client, db = client_and_db
    _insert_prediction(db, prediction_id="pred-1")
    before = AgentPredictionRepository(db).get("pred-1")
    assert before is not None
    write_calls: List[str] = []

    def _track(name: str, original):
        def _wrapped(self, *args, **kwargs):
            write_calls.append(name)
            return original(self, *args, **kwargs)

        return _wrapped

    monkeypatch.setattr(
        AgentPredictionRepository,
        "claim_for_resolve",
        _track("claim", AgentPredictionRepository.claim_for_resolve),
    )
    monkeypatch.setattr(
        AgentPredictionRepository,
        "resolve",
        _track("resolve", AgentPredictionRepository.resolve),
    )
    monkeypatch.setattr(
        AgentPredictionRepository,
        "requeue_pending",
        _track("requeue", AgentPredictionRepository.requeue_pending),
    )
    monkeypatch.setattr(
        AgentPredictionRepository,
        "list_due",
        _track("list_due", AgentPredictionRepository.list_due),
    )
    monkeypatch.setattr(
        PredictionResolver,
        "tick",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("prediction query must not tick")
        ),
    )

    got = client.get(GET_PATH.format(prediction_id="pred-1"))
    listed = client.get(LIST_PATH, params={"run_id": "run-1"})
    assert got.status_code == 200, got.text
    assert listed.status_code == 200, listed.text
    after = AgentPredictionRepository(db).get("pred-1")
    assert after is not None
    assert after.status == before.status == STATUS_PENDING
    assert after.lease_token == before.lease_token
    assert after.updated_at == before.updated_at
    assert write_calls == []


def test_store_failure_returns_sanitized_500(client_and_db, monkeypatch) -> None:
    client, db = client_and_db
    _insert_prediction(db, prediction_id="pred-1")

    def _boom(self, prediction_id: str):
        raise RuntimeError("secret-fail lease_token=abc outcome={'label':'hit'}")

    monkeypatch.setattr(AgentPredictionRepository, "get", _boom)
    response = client.get(GET_PATH.format(prediction_id="pred-1"))
    assert response.status_code == 500, response.text
    payload = response.json()
    assert payload["error"] == "internal_error"
    assert "secret-fail" not in response.text
    assert "lease_token" not in response.text
    assert "outcome_label" not in payload
    _assert_no_forbidden_keys(payload)


def test_list_projection_failure_returns_500_not_422(
    client_and_db, monkeypatch
) -> None:
    client, db = client_and_db
    _insert_prediction(db, prediction_id="pred-1")

    def _boom(record: Any):
        raise ValueError("prediction horizon is not allowlisted")

    monkeypatch.setattr(
        "src.services.agent_prediction_query.project_prediction_item",
        _boom,
    )
    response = client.get(LIST_PATH, params={"run_id": "run-1"})
    assert response.status_code == 500, response.text
    payload = response.json()
    assert payload["error"] == "internal_error"
    assert "not allowlisted" not in response.text
    assert "items" not in payload


def test_list_store_failure_returns_sanitized_500(client_and_db, monkeypatch) -> None:
    client, db = client_and_db
    _insert_prediction(db, prediction_id="pred-1")

    def _boom(self, run_id: str, *, limit: int = 50):
        raise RuntimeError("secret-list-fail")

    monkeypatch.setattr(AgentPredictionRepository, "list_by_run_id", _boom)
    response = client.get(LIST_PATH, params={"run_id": "run-1"})
    assert response.status_code == 500, response.text
    payload = response.json()
    assert payload["error"] == "internal_error"
    assert "secret-list-fail" not in response.text
    assert "items" not in payload


def test_feedback_path_coexists_with_prediction_get(client_and_db) -> None:
    client, db = client_and_db
    _insert_prediction(db, prediction_id="pred-1")
    feedback = client.get(FEEDBACK_PATH.format(prediction_id="pred-1"))
    prediction = client.get(GET_PATH.format(prediction_id="pred-1"))
    assert feedback.status_code == 200, feedback.text
    assert feedback.json()["prediction_id"] == "pred-1"
    assert feedback.json()["feedback_value"] is None
    assert prediction.status_code == 200, prediction.text
    assert prediction.json()["status"] == STATUS_PENDING
    assert "feedback_value" not in prediction.json()


def test_collision_token_is_unknown_prediction_not_diagnostics(client_and_db) -> None:
    client, _db = client_and_db
    collision = client.get(COLLISION_PATH)
    diagnostics = client.get(DIAGNOSTICS_PATH)
    assert collision.status_code == 404, collision.text
    assert collision.json()["error"] == "not_found"
    assert "claimable_due_count" not in collision.json()
    assert "oldest_due" not in collision.json()
    assert diagnostics.status_code == 200, diagnostics.text
    assert "claimable_due_count" in diagnostics.json()
    assert "claimable_due_lag_seconds" in diagnostics.json()


def test_prediction_paths_are_not_auth_exempt() -> None:
    assert LIST_PATH not in EXEMPT_PATHS
    assert GET_PATH.format(prediction_id="pred-1") not in EXEMPT_PATHS
    assert "/api/v1/agent/predictions" not in EXEMPT_PATHS


def test_admin_auth_enabled_rejects_missing_and_invalid_session(
    tmp_path, monkeypatch
) -> None:
    env_path = tmp_path / ".env"
    db_path = tmp_path / "agent_predictions_auth.db"
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    env_path.write_text(
        "\n".join(
            [
                "STOCK_LIST=600519",
                "GEMINI_API_KEY=test",
                "ADMIN_AUTH_ENABLED=true",
                f"DATABASE_PATH={db_path}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ENV_FILE", str(env_path))
    original_environ = dict(os.environ)
    os.environ["ENV_FILE"] = str(env_path)
    os.environ["DATABASE_PATH"] = str(db_path)
    Config.reset_instance()
    DatabaseManager.reset_instance()
    _reset_auth_globals()
    try:
        with TestClient(create_app(static_dir=static_dir)) as client:
            db = DatabaseManager.get_instance()
            _insert_prediction(db, prediction_id="pred-secret")
            missing_get = client.get(GET_PATH.format(prediction_id="pred-secret"))
            missing_list = client.get(LIST_PATH, params={"run_id": "run-1"})
            invalid = client.get(
                GET_PATH.format(prediction_id="pred-secret"),
                cookies={auth.COOKIE_NAME: "not-a-signed-session"},
            )
            session = auth.create_session()
            allowed_get = client.get(
                GET_PATH.format(prediction_id="pred-secret"),
                cookies={auth.COOKIE_NAME: session},
            )
            allowed_list = client.get(
                LIST_PATH,
                params={"run_id": "run-1"},
                cookies={auth.COOKIE_NAME: session},
            )
            assert missing_get.status_code == 401
            assert missing_get.status_code != 403
            assert missing_get.json()["error"] == "unauthorized"
            assert "pred-secret" not in missing_get.text
            assert "outcome_label" not in missing_get.json()
            assert "status" not in missing_get.json()
            assert missing_list.status_code == 401
            assert missing_list.status_code != 403
            assert missing_list.json()["error"] == "unauthorized"
            assert "items" not in missing_list.json()
            assert invalid.status_code == 401
            assert invalid.status_code != 403
            assert allowed_get.status_code == 200, allowed_get.text
            assert allowed_get.json()["prediction_id"] == "pred-secret"
            assert allowed_list.status_code == 200, allowed_list.text
            assert allowed_list.json()["items"][0]["prediction_id"] == "pred-secret"
            _assert_no_forbidden_keys(allowed_get.json())
            _assert_no_forbidden_keys(allowed_list.json(), allow_items=True)
    finally:
        os.environ.clear()
        os.environ.update(original_environ)
        DatabaseManager.reset_instance()
        Config.reset_instance()
        _reset_auth_globals()


def test_openapi_contract_adds_query_paths_without_changing_lag(client_and_db) -> None:
    client, _db = client_and_db
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    get_path = "/api/v1/agent/predictions/{prediction_id}"
    assert get_path in paths
    assert LIST_PATH in paths
    assert FEEDBACK_PATH.format(prediction_id="{prediction_id}") in paths
    assert DIAGNOSTICS_PATH in paths
    assert COLLISION_PATH not in paths
    get_op = paths[get_path]["get"]
    list_op = paths[LIST_PATH]["get"]
    assert get_op["operationId"] == "getAgentPrediction"
    assert list_op["operationId"] == "listAgentPredictions"
    assert "401" in get_op["responses"]
    assert "401" in list_op["responses"]
    assert "404" in get_op["responses"]
    assert set(paths[get_path].keys()) == {"get"}
    assert set(paths[LIST_PATH].keys()) == {"get"}
    item = schema["components"]["schemas"]["AgentPredictionItem"]
    listing = schema["components"]["schemas"]["AgentPredictionListResponse"]
    assert item["additionalProperties"] is False
    assert listing["additionalProperties"] is False
    assert set(item["required"]) == ITEM_ALLOWLIST
    assert "outcome" not in item["properties"]
    assert "claims" not in item["properties"]
    assert "lease_token" not in item["properties"]
    assert "model_meta" not in item["properties"]
    lag = schema["components"]["schemas"]["PredictionResolverClaimableDueLag"]
    parent = schema["components"]["schemas"]["PredictionResolverDiagnosticsResponse"]
    assert lag["additionalProperties"] is False
    assert set(lag["required"]) == {"p50", "p95", "max"}
    assert "claimable_due_lag_seconds" in parent["properties"]
    assert "claimable_due_lag_seconds" in parent["required"]
