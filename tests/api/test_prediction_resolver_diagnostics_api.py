# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""HTTP contract tests for prediction resolver diagnostics."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
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
from src.config import Config
from src.repositories.agent_prediction_repo import AgentPredictionRepository
from src.schemas.agent_prediction import (
    STATUS_DATA_UNAVAILABLE,
    STATUS_PENDING,
    STATUS_RESOLVING,
    AgentPredictionInsert,
)
from src.services.prediction_resolver.resolver import PredictionResolver
from src.storage import DatabaseManager


DIAGNOSTICS_PATH = "/api/v1/agent/prediction-resolver/diagnostics"
COLLISION_PATH = "/api/v1/agent/predictions/resolver-diagnostics"
FORBIDDEN_KEYS = frozenset(
    {
        "outcome",
        "outcome_json",
        "claims",
        "claims_json",
        "notes",
        "lease_token",
        "lease_owner",
        "model_meta",
        "start_price",
        "end_price",
        "high_price",
        "low_price",
        "items",
        "today_resolve_counts",
        "last_tick",
        "last_tick_at",
        "stuck",
        "never_ticked",
        "resolver_state",
    }
)
OLDEST_DUE_ALLOWLIST = {
    "prediction_id",
    "symbol",
    "market",
    "status",
    "resolve_after",
    "lag_seconds",
}


def _reset_auth_globals() -> None:
    auth._auth_enabled = None
    auth._session_secret = None
    auth._password_hash_salt = None
    auth._password_hash_stored = None
    auth._rate_limit = {}


def _naive_now() -> datetime:
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


def _insert_prediction(
    db: DatabaseManager,
    *,
    prediction_id: str,
    run_id: str = "run-1",
    resolve_after: Optional[datetime] = None,
    clock: Any = _naive_now,
) -> None:
    repo = AgentPredictionRepository(db, clock=clock)
    created, record = repo.insert_pending(
        AgentPredictionInsert(
            prediction_id=prediction_id,
            run_id=run_id,
            symbol="600519",
            market="cn",
            as_of=_naive_now().date(),
            horizon="5d",
            resolve_after=resolve_after or (_naive_now() - timedelta(hours=1)),
            claims=[_direction_claim()],
            created_at=_naive_now() - timedelta(days=1),
        )
    )
    assert created is True
    assert record.status == STATUS_PENDING


def _assert_no_forbidden_keys(payload: Any) -> None:
    found = _collect_keys(payload)
    leaked = sorted(found & FORBIDDEN_KEYS)
    assert leaked == [], f"forbidden keys present: {leaked}"


@pytest.fixture()
def client_and_db(tmp_path, monkeypatch):
    old_env = dict(os.environ)
    env_path = tmp_path / ".env"
    db_path = tmp_path / "prediction_resolver_diagnostics.db"
    static_dir = tmp_path / "empty-static"
    static_dir.mkdir()
    env_path.write_text(
        "\n".join(
            [
                "STOCK_LIST=600519",
                "GEMINI_API_KEY=test",
                "ADMIN_AUTH_ENABLED=false",
                "PREDICTION_RESOLVE_ENABLED=false",
                "DSA_CLI_SCHEDULER_OWNS_SCHEDULE=true",
                f"DATABASE_PATH={db_path}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ENV_FILE", str(env_path))
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    monkeypatch.setenv("DSA_CLI_SCHEDULER_OWNS_SCHEDULE", "true")
    monkeypatch.setenv("ADMIN_AUTH_ENABLED", "false")
    monkeypatch.setenv("PREDICTION_RESOLVE_ENABLED", "false")
    _reset_auth_globals()
    Config.reset_instance()
    DatabaseManager.reset_instance()
    app = create_app(static_dir=Path(static_dir))
    with TestClient(app) as client:
        db = DatabaseManager.get_instance()
        try:
            yield client, db
        finally:
            DatabaseManager.reset_instance()
            Config.reset_instance()
            _reset_auth_globals()
            os.environ.clear()
            os.environ.update(old_env)


def test_disabled_empty_store_returns_honest_200(client_and_db) -> None:
    client, _db = client_and_db
    response = client.get(DIAGNOSTICS_PATH)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["enabled"] is False
    assert payload["this_process_worker_registered"] is False
    assert payload["claimable_due_count"] == 0
    assert payload["oldest_due"] == []
    assert payload["claimable_due_truncated"] is False
    assert payload["claimable_due_probe_limit"] >= 1
    assert "interval_seconds" in payload
    _assert_no_forbidden_keys(payload)


def test_disabled_pending_due_is_listed_without_mutation(client_and_db, monkeypatch) -> None:
    client, db = client_and_db
    _insert_prediction(db, prediction_id="pred-due-1")
    claim_calls: List[str] = []
    requeue_calls: List[str] = []
    original_claim = AgentPredictionRepository.claim_for_resolve
    original_requeue = AgentPredictionRepository.requeue_pending

    def _claim(self, *args, **kwargs):
        claim_calls.append("claim")
        return original_claim(self, *args, **kwargs)

    def _requeue(self, *args, **kwargs):
        requeue_calls.append("requeue")
        return original_requeue(self, *args, **kwargs)

    monkeypatch.setattr(AgentPredictionRepository, "claim_for_resolve", _claim)
    monkeypatch.setattr(AgentPredictionRepository, "requeue_pending", _requeue)
    monkeypatch.setattr(
        "src.services.prediction_resolver.resolver.build_prediction_resolver",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("diagnostics must not construct a worker")
        ),
    )
    monkeypatch.setattr(
        PredictionResolver,
        "tick",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("diagnostics must not tick")
        ),
    )

    response = client.get(DIAGNOSTICS_PATH)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["enabled"] is False
    assert payload["claimable_due_count"] >= 1
    assert payload["oldest_due"][0]["prediction_id"] == "pred-due-1"
    assert payload["oldest_due"][0]["status"] == STATUS_PENDING
    assert set(payload["oldest_due"][0]) == OLDEST_DUE_ALLOWLIST
    assert payload["oldest_due"][0]["lag_seconds"] >= 0
    repo = AgentPredictionRepository(db)
    after = repo.get("pred-due-1")
    assert after is not None
    assert after.status == STATUS_PENDING
    assert claim_calls == []
    assert requeue_calls == []
    _assert_no_forbidden_keys(payload)


def test_enabled_api_without_worker_still_lists_due(tmp_path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    db_path = tmp_path / "diagnostics_enabled.db"
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    env_path.write_text(
        "\n".join(
            [
                "STOCK_LIST=600519",
                "GEMINI_API_KEY=test",
                "ADMIN_AUTH_ENABLED=false",
                "PREDICTION_RESOLVE_ENABLED=true",
                "PREDICTION_RESOLVE_INTERVAL_SECONDS=90",
                "DSA_CLI_SCHEDULER_OWNS_SCHEDULE=true",
                f"DATABASE_PATH={db_path}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ENV_FILE", str(env_path))
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    monkeypatch.setenv("DSA_CLI_SCHEDULER_OWNS_SCHEDULE", "true")
    monkeypatch.setenv("PREDICTION_RESOLVE_ENABLED", "true")
    original_environ = dict(os.environ)
    os.environ["ENV_FILE"] = str(env_path)
    os.environ["DATABASE_PATH"] = str(db_path)
    Config.reset_instance()
    DatabaseManager.reset_instance()
    _reset_auth_globals()
    try:
        with TestClient(create_app(static_dir=static_dir)) as client:
            db = DatabaseManager.get_instance()
            _insert_prediction(db, prediction_id="pred-enabled-due")
            response = client.get(DIAGNOSTICS_PATH)
            assert response.status_code == 200, response.text
            payload = response.json()
            assert payload["enabled"] is True
            assert payload["interval_seconds"] == 90
            assert payload["this_process_worker_registered"] is False
            assert payload["claimable_due_count"] >= 1
            assert payload["oldest_due"][0]["prediction_id"] == "pred-enabled-due"
            _assert_no_forbidden_keys(payload)
    finally:
        os.environ.clear()
        os.environ.update(original_environ)
        DatabaseManager.reset_instance()
        Config.reset_instance()
        _reset_auth_globals()


def test_expired_resolving_lease_is_listed_and_active_lease_is_not(
    client_and_db,
) -> None:
    client, db = client_and_db
    past = datetime(2026, 8, 1, 12, 0, 0)
    _insert_prediction(
        db,
        prediction_id="pred-expired-lease",
        resolve_after=past - timedelta(hours=1),
        clock=lambda: past,
    )
    live_now = datetime.now(timezone.utc).replace(tzinfo=None)
    _insert_prediction(
        db,
        prediction_id="pred-active-lease",
        resolve_after=live_now - timedelta(hours=1),
        clock=lambda: live_now,
    )
    repo = AgentPredictionRepository(db, clock=lambda: past)
    expired = repo.claim_for_resolve(
        prediction_id="pred-expired-lease",
        lease_owner="dead-worker",
        lease_token="expired-token",
        lease_ttl_seconds=1,
        as_of=past,
    )
    assert expired is not None
    assert expired.status == STATUS_RESOLVING
    live_repo = AgentPredictionRepository(db, clock=lambda: live_now)
    active = live_repo.claim_for_resolve(
        prediction_id="pred-active-lease",
        lease_owner="live-worker",
        lease_token="live-token",
        lease_ttl_seconds=3600,
        as_of=live_now,
    )
    assert active is not None
    assert active.status == STATUS_RESOLVING

    response = client.get(DIAGNOSTICS_PATH)
    assert response.status_code == 200, response.text
    payload = response.json()
    ids = [item["prediction_id"] for item in payload["oldest_due"]]
    assert "pred-expired-lease" in ids
    assert "pred-active-lease" not in ids
    expired_item = next(
        item for item in payload["oldest_due"] if item["prediction_id"] == "pred-expired-lease"
    )
    assert expired_item["status"] == STATUS_RESOLVING
    after_expired = AgentPredictionRepository(db).get("pred-expired-lease")
    after_active = AgentPredictionRepository(db).get("pred-active-lease")
    assert after_expired is not None and after_expired.status == STATUS_RESOLVING
    assert after_active is not None and after_active.status == STATUS_RESOLVING
    _assert_no_forbidden_keys(payload)


def test_ready_data_unavailable_retry_is_not_requeued(client_and_db) -> None:
    client, db = client_and_db
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    _insert_prediction(
        db,
        prediction_id="pred-retry",
        resolve_after=now - timedelta(hours=1),
        clock=lambda: now,
    )
    repo = AgentPredictionRepository(db, clock=lambda: now)
    claimed = repo.claim_for_resolve(
        prediction_id="pred-retry",
        lease_owner="worker-1",
        lease_token="retry-token",
        lease_ttl_seconds=3600,
        as_of=now,
    )
    assert claimed is not None
    applied, marked = repo.mark_data_unavailable(
        prediction_id="pred-retry",
        reason="provider_down",
        expected_lease_token="retry-token",
        as_of=now,
        outcome={
            "retryable": True,
            "next_attempt_at": (now - timedelta(seconds=1)).isoformat(),
        },
    )
    assert applied is True
    assert marked is not None
    assert marked.status == STATUS_DATA_UNAVAILABLE

    response = client.get(DIAGNOSTICS_PATH)
    assert response.status_code == 200, response.text
    payload = response.json()
    ids = [item["prediction_id"] for item in payload["oldest_due"]]
    assert "pred-retry" not in ids
    after = AgentPredictionRepository(db).get("pred-retry")
    assert after is not None
    assert after.status == STATUS_DATA_UNAVAILABLE
    _assert_no_forbidden_keys(payload)


def test_oldest_due_cap_ordering_and_allowlist(client_and_db) -> None:
    client, db = client_and_db
    base = _naive_now()
    for index in range(12):
        _insert_prediction(
            db,
            prediction_id=f"pred-{index:02d}",
            resolve_after=base - timedelta(hours=12 - index),
        )
    response = client.get(DIAGNOSTICS_PATH)
    assert response.status_code == 200, response.text
    payload = response.json()
    ids = [item["prediction_id"] for item in payload["oldest_due"]]
    assert payload["claimable_due_count"] == 12
    assert ids == [f"pred-{index:02d}" for index in range(10)]
    for item in payload["oldest_due"]:
        assert set(item) == OLDEST_DUE_ALLOWLIST
    _assert_no_forbidden_keys(payload)


def test_store_read_failure_returns_503_not_empty_backlog(
    client_and_db, monkeypatch
) -> None:
    client, _db = client_and_db

    def _raise(self, *args, **kwargs):
        raise RuntimeError("store unavailable")

    monkeypatch.setattr(AgentPredictionRepository, "list_due", _raise)
    response = client.get(DIAGNOSTICS_PATH)
    assert response.status_code == 503, response.text
    payload = response.json()
    assert payload["error"] == "internal_error"
    assert "claimable_due_count" not in payload
    assert "oldest_due" not in payload
    _assert_no_forbidden_keys(payload)


def test_admin_auth_enabled_rejects_missing_and_invalid_session(
    tmp_path, monkeypatch
) -> None:
    env_path = tmp_path / ".env"
    db_path = tmp_path / "diagnostics_auth.db"
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    env_path.write_text(
        "\n".join(
            [
                "STOCK_LIST=600519",
                "GEMINI_API_KEY=test",
                "ADMIN_AUTH_ENABLED=true",
                "DSA_CLI_SCHEDULER_OWNS_SCHEDULE=true",
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
    os.environ["DSA_CLI_SCHEDULER_OWNS_SCHEDULE"] = "true"
    Config.reset_instance()
    DatabaseManager.reset_instance()
    _reset_auth_globals()
    try:
        with TestClient(create_app(static_dir=static_dir)) as client:
            db = DatabaseManager.get_instance()
            _insert_prediction(db, prediction_id="pred-secret")
            missing = client.get(DIAGNOSTICS_PATH)
            invalid = client.get(
                DIAGNOSTICS_PATH,
                cookies={auth.COOKIE_NAME: "not-a-signed-session"},
            )
            session = auth.create_session()
            allowed = client.get(
                DIAGNOSTICS_PATH,
                cookies={auth.COOKIE_NAME: session},
            )
            assert missing.status_code == 401
            assert missing.json()["error"] == "unauthorized"
            assert "pred-secret" not in missing.text
            assert "oldest_due" not in missing.json()
            assert invalid.status_code == 401
            assert invalid.json()["error"] == "unauthorized"
            assert allowed.status_code == 200, allowed.text
            assert allowed.json()["oldest_due"][0]["prediction_id"] == "pred-secret"
            assert allowed.status_code != 403
            assert missing.status_code != 403
    finally:
        os.environ.clear()
        os.environ.update(original_environ)
        DatabaseManager.reset_instance()
        Config.reset_instance()
        _reset_auth_globals()


def test_diagnostics_path_is_not_auth_exempt() -> None:
    from src.api.middlewares.auth import EXEMPT_PATHS

    assert DIAGNOSTICS_PATH not in EXEMPT_PATHS
    assert "/api/v1/agent/prediction-resolver/diagnostics" not in EXEMPT_PATHS


def test_openapi_contract_uses_resolver_scoped_path(client_and_db) -> None:
    client, _db = client_and_db
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    assert DIAGNOSTICS_PATH in paths
    assert COLLISION_PATH not in paths
    operation = paths[DIAGNOSTICS_PATH]["get"]
    assert operation["operationId"] == "getPredictionResolverDiagnostics"
    assert "401" in operation["responses"]
    assert "503" in operation["responses"]
    collision = client.get(COLLISION_PATH)
    assert collision.status_code != 200
    feedback_path = "/api/v1/agent/predictions/{prediction_id}/feedback"
    assert feedback_path in paths


def test_build_helpers_are_not_used_for_diagnostics(client_and_db, monkeypatch) -> None:
    client, db = client_and_db
    _insert_prediction(db, prediction_id="pred-no-build")
    monkeypatch.setattr(
        "src.services.prediction_resolver.resolver.build_prediction_resolver",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("must not call build_prediction_resolver")
        ),
    )
    monkeypatch.setattr(
        "src.services.prediction_resolver.resolver.build_prediction_resolver_background_tasks",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("must not call build_prediction_resolver_background_tasks")
        ),
    )
    response = client.get(DIAGNOSTICS_PATH)
    assert response.status_code == 200, response.text
    assert response.json()["oldest_due"][0]["prediction_id"] == "pred-no-build"
