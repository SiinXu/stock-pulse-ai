# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""HTTP contract tests for authenticated EvolutionEvent list API."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
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
from src.repositories.agent_evolution_event_repo import AgentEvolutionEventRepository
from src.schemas.evolution_event import EvolutionEventCreate
from src.storage import DatabaseManager


LIST_PATH = "/api/v1/agent/evolution-events"
CHECKED_IN_OPENAPI = (
    Path(__file__).resolve().parents[2] / "apps" / "dsa-web" / "openapi.json"
)


def _reset_auth_globals() -> None:
    auth._auth_enabled = None
    auth._session_secret = None
    auth._password_hash_salt = None
    auth._password_hash_stored = None
    auth._rate_limit = {}


def _ts(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 8, 25, hour, minute, tzinfo=timezone.utc)


def _iso(hour: int, minute: int = 0) -> str:
    return _ts(hour, minute).isoformat().replace("+00:00", "Z")


def _create(**overrides: Any) -> EvolutionEventCreate:
    payload = {
        "event_type": "adapter.calibrate",
        "actor": "system",
        "occurred_at": _ts(12),
        "reason_refs": {"prediction_ids": ["pred-1"], "run_ids": ["run-1"]},
        "before": {"applied": False, "factor": 1.0},
        "after": {"applied": True, "factor": 1.1},
    }
    payload.update(overrides)
    return EvolutionEventCreate.model_validate(payload)


def _seed(db: DatabaseManager, **overrides: Any) -> None:
    AgentEvolutionEventRepository(db).append(_create(**overrides))


@pytest.fixture()
def client_and_db(tmp_path, monkeypatch):
    old_env = dict(os.environ)
    env_path = tmp_path / ".env"
    db_path = tmp_path / "evolution_events_api.db"
    static_dir = tmp_path / "empty-static"
    static_dir.mkdir()
    env_path.write_text(
        "\n".join(
            [
                "STOCK_LIST=600519",
                "GEMINI_API_KEY=test",
                "ADMIN_AUTH_ENABLED=false",
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


def test_list_returns_seeded_rows_in_occurred_at_order(client_and_db) -> None:
    client, db = client_and_db
    _seed(
        db,
        event_type="episode.forget",
        occurred_at=_ts(13),
        before={"count": 2},
        after={"count": 0},
    )
    _seed(
        db,
        event_type="adapter.calibrate",
        occurred_at=_ts(11),
        before={"applied": False, "factor": 1.0},
        after={"applied": True, "factor": 0.9},
    )
    response = client.get(
        LIST_PATH,
        params={"occurred_from": _iso(10), "occurred_to": _iso(14)},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["returned"] == 2
    assert body["limit"] == 100
    types = [item["event_type"] for item in body["items"]]
    assert types == ["adapter.calibrate", "episode.forget"]


def test_event_type_exact_match_filters_and_unknown_type_is_empty(
    client_and_db,
) -> None:
    client, db = client_and_db
    _seed(db, event_type="adapter.calibrate", occurred_at=_ts(12))
    _seed(
        db,
        event_type="episode.forget",
        occurred_at=_ts(12, 1),
        before={"count": 2},
        after={"count": 0},
    )
    matched = client.get(
        LIST_PATH,
        params={
            "occurred_from": _iso(12),
            "occurred_to": _iso(13),
            "event_type": "adapter.calibrate",
        },
    )
    assert matched.status_code == 200, matched.text
    assert matched.json()["returned"] == 1
    assert matched.json()["items"][0]["event_type"] == "adapter.calibrate"

    missing = client.get(
        LIST_PATH,
        params={
            "occurred_from": _iso(12),
            "occurred_to": _iso(13),
            "event_type": "adapter.missing",
        },
    )
    assert missing.status_code == 200, missing.text
    assert missing.json() == {"items": [], "limit": 100, "returned": 0}


def test_inclusive_window_from_equals_to_returns_that_timestamp(
    client_and_db,
) -> None:
    client, db = client_and_db
    _seed(db, occurred_at=_ts(12))
    _seed(
        db,
        event_type="episode.forget",
        occurred_at=_ts(13),
        before={"count": 1},
        after={"count": 0},
    )
    response = client.get(
        LIST_PATH,
        params={"occurred_from": _iso(12), "occurred_to": _iso(12)},
    )
    assert response.status_code == 200, response.text
    assert response.json()["returned"] == 1
    assert response.json()["items"][0]["event_type"] == "adapter.calibrate"


def test_inverted_and_naive_windows_return_400(client_and_db) -> None:
    client, _db = client_and_db
    inverted = client.get(
        LIST_PATH,
        params={"occurred_from": _iso(14), "occurred_to": _iso(10)},
    )
    assert inverted.status_code == 400, inverted.text
    assert inverted.json()["error"] == "validation_error"

    naive = client.get(
        LIST_PATH,
        params={
            "occurred_from": "2026-08-25T12:00:00",
            "occurred_to": "2026-08-25T13:00:00",
        },
    )
    assert naive.status_code == 400, naive.text
    assert naive.json()["error"] == "validation_error"


def test_missing_required_window_params_fail_closed(client_and_db) -> None:
    client, _db = client_and_db
    missing_from = client.get(LIST_PATH, params={"occurred_to": _iso(13)})
    missing_to = client.get(LIST_PATH, params={"occurred_from": _iso(10)})
    assert missing_from.status_code in {400, 422}
    assert missing_to.status_code in {400, 422}


def test_blank_event_type_is_rejected_not_unfiltered(client_and_db) -> None:
    client, db = client_and_db
    _seed(db, occurred_at=_ts(12))
    response = client.get(
        LIST_PATH,
        params={
            "occurred_from": _iso(10),
            "occurred_to": _iso(14),
            "event_type": "",
        },
    )
    assert response.status_code == 400, response.text
    assert response.json()["error"] == "validation_error"
    assert response.json().get("items") is None


def test_limit_bounds_and_default_cap(client_and_db) -> None:
    client, db = client_and_db
    for hour in range(10, 15):
        _seed(
            db,
            occurred_at=_ts(hour),
            before={"n": hour},
            after={"n": hour + 1},
        )
    zero = client.get(
        LIST_PATH,
        params={"occurred_from": _iso(10), "occurred_to": _iso(14), "limit": 0},
    )
    oversized = client.get(
        LIST_PATH,
        params={"occurred_from": _iso(10), "occurred_to": _iso(14), "limit": 201},
    )
    truncated = client.get(
        LIST_PATH,
        params={"occurred_from": _iso(10), "occurred_to": _iso(14), "limit": 1},
    )
    defaulted = client.get(
        LIST_PATH,
        params={"occurred_from": _iso(10), "occurred_to": _iso(14)},
    )
    assert zero.status_code == 400, zero.text
    assert oversized.status_code == 400, oversized.text
    assert truncated.status_code == 200, truncated.text
    assert truncated.json()["returned"] == 1
    assert truncated.json()["limit"] == 1
    assert defaulted.status_code == 200, defaulted.text
    assert defaulted.json()["returned"] == 5
    assert defaulted.json()["limit"] == 100


def test_list_rejects_extra_query_key(client_and_db) -> None:
    client, db = client_and_db
    _seed(db, occurred_at=_ts(12))
    response = client.get(
        LIST_PATH,
        params={
            "occurred_from": _iso(10),
            "occurred_to": _iso(14),
            "actor": "system",
        },
    )
    assert response.status_code == 422, response.text
    assert "items" not in response.json()


def test_get_does_not_insert_rows(client_and_db) -> None:
    client, db = client_and_db
    _seed(db, occurred_at=_ts(12))
    before = AgentEvolutionEventRepository(db).list_events(
        occurred_from=_ts(10),
        occurred_to=_ts(14),
    )
    response = client.get(
        LIST_PATH,
        params={"occurred_from": _iso(10), "occurred_to": _iso(14)},
    )
    after = AgentEvolutionEventRepository(db).list_events(
        occurred_from=_ts(10),
        occurred_to=_ts(14),
    )
    assert response.status_code == 200, response.text
    assert len(before) == 1
    assert len(after) == 1
    assert after[0].event_id == before[0].event_id


def test_evolution_event_path_is_not_auth_exempt() -> None:
    assert LIST_PATH not in EXEMPT_PATHS
    assert "/api/v1/agent/evolution-events" not in EXEMPT_PATHS


def test_admin_auth_enabled_rejects_missing_and_invalid_session(
    tmp_path, monkeypatch
) -> None:
    env_path = tmp_path / ".env"
    db_path = tmp_path / "evolution_events_auth.db"
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
    os.environ["ADMIN_AUTH_ENABLED"] = "true"
    Config.reset_instance()
    DatabaseManager.reset_instance()
    _reset_auth_globals()
    try:
        with TestClient(create_app(static_dir=static_dir)) as client:
            db = DatabaseManager.get_instance()
            _seed(db, occurred_at=_ts(12))
            params = {"occurred_from": _iso(10), "occurred_to": _iso(14)}
            missing = client.get(LIST_PATH, params=params)
            invalid = client.get(
                LIST_PATH,
                params=params,
                cookies={auth.COOKIE_NAME: "not-a-signed-session"},
            )
            session = auth.create_session()
            allowed = client.get(
                LIST_PATH,
                params=params,
                cookies={auth.COOKIE_NAME: session},
            )
            assert missing.status_code == 401
            assert missing.status_code != 403
            assert missing.json()["error"] == "unauthorized"
            assert "items" not in missing.json()
            assert invalid.status_code == 401
            assert invalid.status_code != 403
            assert allowed.status_code == 200, allowed.text
            assert allowed.json()["returned"] == 1
            assert allowed.json()["items"][0]["event_type"] == "adapter.calibrate"
    finally:
        os.environ.clear()
        os.environ.update(original_environ)
        DatabaseManager.reset_instance()
        Config.reset_instance()
        _reset_auth_globals()


def test_live_openapi_exposes_get_only_list_contract(client_and_db) -> None:
    client, _db = client_and_db
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    assert LIST_PATH in paths
    assert set(paths[LIST_PATH].keys()) == {"get"}
    operation = paths[LIST_PATH]["get"]
    assert operation["operationId"] == "listAgentEvolutionEvents"
    assert "401" in operation["responses"]
    assert "400" in operation["responses"]
    assert operation.get("security") == [{"AdminSessionCookie": []}]
    listing = schema["components"]["schemas"]["EvolutionEventListResponse"]
    assert listing["additionalProperties"] is False
    assert set(listing["required"]) == {"items", "limit", "returned"}
    assert "post" not in paths[LIST_PATH]
    assert "patch" not in paths[LIST_PATH]
    assert "delete" not in paths[LIST_PATH]


def test_checked_in_openapi_snapshot_includes_list_path() -> None:
    spec = json.loads(CHECKED_IN_OPENAPI.read_text(encoding="utf-8"))
    assert LIST_PATH in spec["paths"]
    assert "get" in spec["paths"][LIST_PATH]
    assert set(spec["paths"][LIST_PATH].keys()) == {"get"}
    assert spec["paths"][LIST_PATH]["get"]["operationId"] == "listAgentEvolutionEvents"
