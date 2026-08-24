# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""HTTP contract tests for prediction resolver diagnostics."""

from __future__ import annotations

import math
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, List, Optional, Set
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

try:
    import litellm  # noqa: F401
except ModuleNotFoundError:
    sys.modules["litellm"] = MagicMock()

import src.auth as auth
from src.api.app import create_app
from src.api.v1.endpoints import prediction_resolver_diagnostics as diagnostics_endpoint
from src.api.v1.schemas.prediction_resolver_diagnostics import (
    PredictionResolverClaimableDueLag,
    PredictionResolverDiagnosticsResponse,
)
from src.application_services import (
    get_application_services,
    get_installed_application_services,
)
from src.config import Config
from src.repositories.agent_prediction_repo import AgentPredictionRepository
from src.schemas.agent_prediction import (
    STATUS_DATA_UNAVAILABLE,
    STATUS_PENDING,
    STATUS_RESOLVED,
    STATUS_RESOLVING,
    AgentPredictionInsert,
)
from src.services.prediction_resolver.resolver import PredictionResolver
from src.services.prediction_resolver_diagnostics import (
    collect_prediction_resolver_diagnostics,
)
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
        "postmortem_queue_depth",
        "adapter_updates_total",
        "actuals_fetch_errors",
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
LAG_SECONDS_ALLOWLIST = {"p50", "p95", "max"}


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
    assert payload["resolved_utc_day_counts"] == {
        "hit": 0,
        "miss": 0,
        "partial": 0,
        "unavailable": 0,
        "unlabeled": 0,
    }
    assert payload["resolved_utc_day_start"].endswith("+00:00")
    assert payload["resolved_utc_day_end"].endswith("+00:00")
    assert payload["claimable_due_lag_seconds"] == {
        "p50": None,
        "p95": None,
        "max": None,
    }
    assert set(payload["claimable_due_lag_seconds"]) == LAG_SECONDS_ALLOWLIST
    _assert_no_forbidden_keys(payload)


def test_disabled_pending_due_is_listed_without_mutation(client_and_db, monkeypatch) -> None:
    client, db = client_and_db
    _insert_prediction(db, prediction_id="pred-due-1")
    claim_calls: List[str] = []
    requeue_calls: List[str] = []
    original_claim = AgentPredictionRepository.claim_for_resolve
    original_requeue = AgentPredictionRepository.requeue_pending
    original_resolve = AgentPredictionRepository.resolve
    resolve_calls: List[str] = []

    def _claim(self, *args, **kwargs):
        claim_calls.append("claim")
        return original_claim(self, *args, **kwargs)

    def _requeue(self, *args, **kwargs):
        requeue_calls.append("requeue")
        return original_requeue(self, *args, **kwargs)

    def _resolve(self, *args, **kwargs):
        resolve_calls.append("resolve")
        return original_resolve(self, *args, **kwargs)

    monkeypatch.setattr(AgentPredictionRepository, "claim_for_resolve", _claim)
    monkeypatch.setattr(AgentPredictionRepository, "requeue_pending", _requeue)
    monkeypatch.setattr(AgentPredictionRepository, "resolve", _resolve)
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
    monkeypatch.setattr(
        "src.services.prediction_resolver.postmortem_drain.drain_postmortem_queue",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("diagnostics must not drain")
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
    assert resolve_calls == []
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
    observed = datetime.fromisoformat(
        payload["observed_at"].replace("Z", "+00:00")
    )
    if observed.tzinfo is not None:
        observed = observed.astimezone(timezone.utc).replace(tzinfo=None)
    lags = sorted(
        max(0.0, (observed - (base - timedelta(hours=12 - index))).total_seconds())
        for index in range(12)
    )
    probe_p50_rank = min(12, max(1, math.ceil(50 / 100.0 * 12)))
    probe_p95_rank = min(12, max(1, math.ceil(95 / 100.0 * 12)))
    oldest_only = sorted(item["lag_seconds"] for item in payload["oldest_due"])
    oldest_p50_rank = min(10, max(1, math.ceil(50 / 100.0 * 10)))
    lag = payload["claimable_due_lag_seconds"]
    assert set(lag) == LAG_SECONDS_ALLOWLIST
    assert lag["p50"] == lags[probe_p50_rank - 1]
    assert lag["p95"] == lags[probe_p95_rank - 1]
    assert lag["max"] == lags[-1]
    assert lag["max"] == payload["oldest_due"][0]["lag_seconds"]
    assert lag["p50"] != oldest_only[oldest_p50_rank - 1]
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
    assert "resolved_utc_day_counts" not in payload
    assert "resolved_utc_day_start" not in payload
    assert "claimable_due_lag_seconds" not in payload
    _assert_no_forbidden_keys(payload)


def test_count_query_failure_returns_503_without_partial_snapshot(
    client_and_db, monkeypatch
) -> None:
    client, db = client_and_db
    _insert_prediction(db, prediction_id="pred-due-count-fail")

    def _raise(self, *args, **kwargs):
        raise RuntimeError("count unavailable")

    monkeypatch.setattr(AgentPredictionRepository, "count_resolved_utc_day", _raise)
    response = client.get(DIAGNOSTICS_PATH)
    assert response.status_code == 503, response.text
    payload = response.json()
    assert payload["error"] == "internal_error"
    assert "claimable_due_count" not in payload
    assert "oldest_due" not in payload
    assert "resolved_utc_day_counts" not in payload
    assert "claimable_due_lag_seconds" not in payload
    assert "pred-due-count-fail" not in response.text
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
            assert "resolved_utc_day_counts" not in missing.json()
            assert "resolved_utc_day_start" not in missing.json()
            assert "claimable_due_lag_seconds" not in missing.json()
            assert invalid.status_code == 401
            assert invalid.json()["error"] == "unauthorized"
            assert "resolved_utc_day_counts" not in invalid.json()
            assert "claimable_due_lag_seconds" not in invalid.json()
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
    parent = schema["components"]["schemas"]["PredictionResolverDiagnosticsResponse"]
    counts = schema["components"]["schemas"]["PredictionResolverResolvedUtcDayCounts"]
    lag = schema["components"]["schemas"]["PredictionResolverClaimableDueLag"]
    assert parent["additionalProperties"] is False
    assert counts["additionalProperties"] is False
    assert lag["additionalProperties"] is False
    assert "resolved_utc_day_start" in parent["properties"]
    assert "resolved_utc_day_end" in parent["properties"]
    assert "resolved_utc_day_counts" in parent["properties"]
    assert "claimable_due_lag_seconds" in parent["properties"]
    assert "claimable_due_lag_seconds" in parent["required"]
    assert "today_resolve_counts" not in parent["properties"]
    assert "last_tick" not in parent["properties"]
    assert "postmortem_queue_depth" not in parent["properties"]
    assert "adapter_updates_total" not in parent["properties"]
    assert set(counts["required"]) == {
        "hit",
        "miss",
        "partial",
        "unavailable",
        "unlabeled",
    }
    assert set(lag["required"]) == {"p50", "p95", "max"}
    for key in ("p50", "p95", "max"):
        field = lag["properties"][key]
        any_of = field.get("anyOf") or field.get("oneOf") or []
        types = {item.get("type") for item in any_of}
        nullable_number = "null" in types and "number" in types
        legacy_nullable = field.get("type") == "number" and field.get("nullable") is True
        assert nullable_number or legacy_nullable, field
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


def test_endpoint_reads_installed_application_services_config(
    client_and_db, monkeypatch
) -> None:
    client, _db = client_and_db
    assert "get_config" not in vars(diagnostics_endpoint)
    assert diagnostics_endpoint.get_application_services is get_application_services

    installed = get_application_services()
    assert get_installed_application_services() is installed
    process_config = Config.get_instance()
    assert bool(getattr(process_config, "prediction_resolve_enabled", False)) is False
    sentinel = SimpleNamespace(
        prediction_resolve_enabled=True,
        prediction_resolve_interval_seconds=77,
        prediction_resolve_max_per_tick=50,
    )
    monkeypatch.setattr(installed, "_config", sentinel)

    captured: List[Any] = []
    original = collect_prediction_resolver_diagnostics

    def _capture(*, config: Any, store: Any, scheduler: Any = None, now: Any = None):
        captured.append(config)
        return original(config=config, store=store, scheduler=scheduler, now=now)

    monkeypatch.setattr(
        diagnostics_endpoint,
        "collect_prediction_resolver_diagnostics",
        _capture,
    )

    response = client.get(DIAGNOSTICS_PATH)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["enabled"] is True
    assert payload["interval_seconds"] == 77
    assert captured == [sentinel]
    assert captured[0] is not process_config
    assert get_installed_application_services() is installed
    assert installed.config is sentinel
    _assert_no_forbidden_keys(payload)


def _claim_and_write(
    db: DatabaseManager,
    *,
    prediction_id: str,
    as_of: datetime,
    outcome: dict,
    unavailable: bool = False,
) -> None:
    _insert_prediction(
        db,
        prediction_id=prediction_id,
        resolve_after=as_of - timedelta(hours=1),
        clock=lambda: as_of,
    )
    repo = AgentPredictionRepository(db, clock=lambda: as_of)
    claimed = repo.claim_for_resolve(
        prediction_id=prediction_id,
        lease_owner="worker-mix",
        lease_token=f"token-{prediction_id}",
        lease_ttl_seconds=120,
        as_of=as_of,
    )
    assert claimed is not None
    if unavailable:
        applied, record = repo.mark_data_unavailable(
            prediction_id=prediction_id,
            reason=str(outcome.get("reason") or "data_unavailable"),
            expected_lease_token=f"token-{prediction_id}",
            as_of=as_of,
            outcome=outcome,
        )
    else:
        applied, record = repo.resolve(
            prediction_id=prediction_id,
            outcome=outcome,
            expected_lease_token=f"token-{prediction_id}",
            as_of=as_of,
        )
    assert applied is True
    assert record is not None


def test_utc_day_counts_mix_and_exclusions(client_and_db, monkeypatch) -> None:
    client, db = client_and_db
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    start = datetime(now.year, now.month, now.day)
    _claim_and_write(
        db,
        prediction_id="pred-hit",
        as_of=now,
        outcome={"label": "hit", "score": 1.0},
    )
    _claim_and_write(
        db,
        prediction_id="pred-miss",
        as_of=now,
        outcome={"label": "miss", "score": 0.0},
    )
    _claim_and_write(
        db,
        prediction_id="pred-partial",
        as_of=now,
        outcome={"label": "partial", "score": 0.5},
    )
    _claim_and_write(
        db,
        prediction_id="pred-yesterday-hit",
        as_of=start - timedelta(seconds=1),
        outcome={"label": "hit", "score": 1.0},
    )
    _claim_and_write(
        db,
        prediction_id="pred-unlabeled",
        as_of=now,
        outcome={"score": 1.0},
    )
    _claim_and_write(
        db,
        prediction_id="pred-retryable",
        as_of=now,
        outcome={"retryable": True, "retry_exhausted": False},
        unavailable=True,
    )
    _claim_and_write(
        db,
        prediction_id="pred-exhausted",
        as_of=now,
        outcome={"retryable": False, "retry_exhausted": True},
        unavailable=True,
    )
    original_claim = AgentPredictionRepository.claim_for_resolve
    claim_calls: List[str] = []

    def _claim(self, *args, **kwargs):
        claim_calls.append("claim")
        return original_claim(self, *args, **kwargs)

    monkeypatch.setattr(AgentPredictionRepository, "claim_for_resolve", _claim)
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
    assert payload["resolved_utc_day_counts"] == {
        "hit": 1,
        "miss": 1,
        "partial": 1,
        "unavailable": 1,
        "unlabeled": 1,
    }
    assert payload["resolved_utc_day_start"].endswith("T00:00:00+00:00")
    assert payload["resolved_utc_day_end"].endswith("T00:00:00+00:00")
    assert claim_calls == []
    repo = AgentPredictionRepository(db)
    hit_row = repo.get("pred-hit")
    retry_row = repo.get("pred-retryable")
    assert hit_row is not None and hit_row.status == STATUS_RESOLVED
    assert retry_row is not None and retry_row.status == STATUS_DATA_UNAVAILABLE
    _assert_no_forbidden_keys(payload)
    found = _collect_keys(payload)
    assert "today_resolve_counts" not in found
    assert "outcome_json" not in found
    assert "pred-hit" not in str(payload.get("resolved_utc_day_counts"))
    assert "postmortem_queue_depth" not in found
    assert "adapter_updates_total" not in found


def test_mixed_lags_http_quantiles_use_real_due_probe(client_and_db, monkeypatch) -> None:
    client, db = client_and_db
    frozen = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)
    naive = frozen.replace(tzinfo=None)
    monkeypatch.setattr(
        "src.services.prediction_resolver_diagnostics._utc_now",
        lambda: frozen,
    )
    for lag_seconds in (10, 20, 30, 40, 50):
        _insert_prediction(
            db,
            prediction_id=f"pred-lag-{lag_seconds}",
            resolve_after=naive - timedelta(seconds=lag_seconds),
            clock=lambda: naive,
        )
    original_claim = AgentPredictionRepository.claim_for_resolve
    claim_calls: List[str] = []

    def _claim(self, *args, **kwargs):
        claim_calls.append("claim")
        return original_claim(self, *args, **kwargs)

    monkeypatch.setattr(AgentPredictionRepository, "claim_for_resolve", _claim)
    response = client.get(DIAGNOSTICS_PATH)
    assert response.status_code == 200, response.text
    payload = response.json()
    lag = payload["claimable_due_lag_seconds"]
    assert payload["claimable_due_count"] == 5
    assert lag == {"p50": 30.0, "p95": 50.0, "max": 50.0}
    assert lag["max"] == payload["oldest_due"][0]["lag_seconds"]
    assert claim_calls == []
    _assert_no_forbidden_keys(payload)


def test_collector_payload_validates_forbid_schema() -> None:
    from src.services.prediction_resolver.memory_store import InMemoryPredictionStore

    store = InMemoryPredictionStore()
    store._clock = lambda: datetime(2026, 8, 12, 12, 0, 0)
    payload = collect_prediction_resolver_diagnostics(
        config=SimpleNamespace(
            prediction_resolve_enabled=False,
            prediction_resolve_interval_seconds=60,
            prediction_resolve_max_per_tick=50,
        ),
        store=store,
        now=datetime(2026, 8, 12, 12, 0, 0),
    )
    model = PredictionResolverDiagnosticsResponse(**payload)
    assert model.claimable_due_lag_seconds.p50 is None
    with pytest.raises(ValidationError):
        PredictionResolverDiagnosticsResponse(
            **{**payload, "today_resolve_counts": {"hit": 0}}
        )
    with pytest.raises(ValidationError):
        PredictionResolverClaimableDueLag(p50=1.0, p95=1.0, max=1.0, stuck=True)
