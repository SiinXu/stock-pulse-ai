# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""HTTP contract tests for optional run and prediction feedback APIs."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

try:
    import litellm  # noqa: F401
except ModuleNotFoundError:
    sys.modules["litellm"] = MagicMock()

import src.auth as auth
from src.agent.soul import AGENT_SOUL_END_MARKER, AGENT_SOUL_MARKER
from src.api.app import create_app
from src.config import Config
from src.repositories.agent_episode_repo import AgentEpisodeRepository
from src.repositories.agent_prediction_repo import AgentPredictionRepository
from src.schemas.agent_episode import AgentEpisodeCreate
from src.schemas.agent_prediction import STATUS_PENDING, STATUS_RESOLVED, AgentPredictionInsert
from src.schemas.memory_write_guard import FEEDBACK_NOTE_MAX_LENGTH
from src.services.prediction_persist import prediction_id_for_run
from src.storage import AnalysisHistory, DatabaseManager


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


def _insert_prediction(
    db: DatabaseManager,
    *,
    prediction_id: str = "pred-1",
    run_id: str = "run-1",
) -> None:
    repo = AgentPredictionRepository(db, clock=_fixed_now)
    created, record = repo.insert_pending(
        AgentPredictionInsert(
            prediction_id=prediction_id,
            run_id=run_id,
            symbol="600519",
            market="cn",
            as_of=_fixed_now().date(),
            horizon="5d",
            resolve_after=_fixed_now() - timedelta(hours=1),
            claims=[_direction_claim()],
            created_at=_fixed_now() - timedelta(days=1),
        )
    )
    assert created is True
    assert record.status == STATUS_PENDING


def _resolve_prediction(db: DatabaseManager, prediction_id: str) -> dict:
    pred_repo = AgentPredictionRepository(db, clock=_fixed_now)
    applied, resolved = pred_repo.resolve(
        prediction_id=prediction_id,
        outcome={"label": "hit", "score": 1.0},
        as_of=_fixed_now(),
    )
    assert applied is True
    assert resolved is not None
    assert resolved.status == STATUS_RESOLVED
    return dict(resolved.outcome or {})


@pytest.fixture()
def client_and_db(tmp_path):
    old_env_file = os.environ.get("ENV_FILE")
    old_database_path = os.environ.get("DATABASE_PATH")
    env_path = tmp_path / ".env"
    db_path = tmp_path / "agent_feedback_api.db"
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
    os.environ["ENV_FILE"] = str(env_path)
    os.environ["DATABASE_PATH"] = str(db_path)
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
        if old_env_file is None:
            os.environ.pop("ENV_FILE", None)
        else:
            os.environ["ENV_FILE"] = old_env_file
        if old_database_path is None:
            os.environ.pop("DATABASE_PATH", None)
        else:
            os.environ["DATABASE_PATH"] = old_database_path


def test_run_and_prediction_feedback_upsert_get_and_empty(client_and_db) -> None:
    client, db = client_and_db
    run_id = "run-a"
    prediction_id = prediction_id_for_run(run_id, "600519")
    assert prediction_id == "pred-5:run-a:600519"
    _insert_prediction(db, prediction_id=prediction_id, run_id=run_id)

    empty_run = client.get(f"/api/v1/agent/runs/{run_id}/feedback")
    assert empty_run.status_code == 200, empty_run.text
    assert empty_run.json()["run_id"] == run_id
    assert empty_run.json()["feedback_value"] is None
    assert empty_run.json()["provenance_source"] is None

    empty_pred = client.get(f"/api/v1/agent/predictions/{prediction_id}/feedback")
    assert empty_pred.status_code == 200, empty_pred.text
    assert empty_pred.json()["prediction_id"] == prediction_id
    assert empty_pred.json()["feedback_value"] is None

    put_run = client.put(
        f"/api/v1/agent/runs/{run_id}/feedback",
        json={"feedback_value": "useful", "note": "helped", "source": "web"},
    )
    assert put_run.status_code == 200, put_run.text
    assert put_run.json()["feedback_value"] == "useful"
    assert put_run.json()["source"] == "web"
    assert put_run.json()["provenance_source"] == "user_feedback"
    assert put_run.json()["actor_id"] == "local_admin"

    pending_put = client.put(
        f"/api/v1/agent/predictions/{prediction_id}/feedback",
        json={"feedback_value": "agree_hit", "source": "api"},
    )
    assert pending_put.status_code == 409, pending_put.text
    assert pending_put.json()["error"] == "conflict"
    still_empty = client.get(f"/api/v1/agent/predictions/{prediction_id}/feedback")
    assert still_empty.status_code == 200
    assert still_empty.json()["feedback_value"] is None

    _resolve_prediction(db, prediction_id)
    put_pred = client.put(
        f"/api/v1/agent/predictions/{prediction_id}/feedback",
        json={"feedback_value": "agree_hit", "source": "api"},
    )
    assert put_pred.status_code == 200, put_pred.text
    assert put_pred.json()["feedback_value"] == "agree_hit"
    created_at = put_pred.json()["created_at"]

    again = client.put(
        f"/api/v1/agent/predictions/{prediction_id}/feedback",
        json={"feedback_value": "disagree_score", "note": "too optimistic"},
    )
    assert again.status_code == 200, again.text
    assert again.json()["feedback_value"] == "disagree_score"
    assert again.json()["created_at"] == created_at
    got = client.get(f"/api/v1/agent/predictions/{prediction_id}/feedback")
    assert got.json()["note"] == "too optimistic"
    assert got.json()["provenance_source"] == "user_feedback"


def test_missing_identity_returns_404(client_and_db) -> None:
    client, db = client_and_db
    missing_run = client.get("/api/v1/agent/runs/unknown-run/feedback")
    assert missing_run.status_code == 404
    missing_pred = client.put(
        "/api/v1/agent/predictions/pred-missing/feedback",
        json={"feedback_value": "agree_hit"},
    )
    assert missing_pred.status_code == 404

    with db.get_session() as session:
        session.add(
            AnalysisHistory(
                query_id="hist-only",
                code="600519",
                report_type="simple",
            )
        )
        session.commit()
    hist = client.put(
        "/api/v1/agent/runs/hist-only/feedback",
        json={"feedback_value": "partial"},
    )
    assert hist.status_code == 200, hist.text
    assert hist.json()["feedback_value"] == "partial"

    started = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)
    AgentEpisodeRepository(db).append(
        AgentEpisodeCreate(
            episode_id="ep-only",
            run_id="episode-only",
            mode="analysis",
            started_at=started,
            completed_at=started,
            success=True,
        )
    )
    episode_only = client.put(
        "/api/v1/agent/runs/episode-only/feedback",
        json={"feedback_value": "wrong"},
    )
    assert episode_only.status_code == 404


def test_invalid_enum_and_payload_rejected_without_persist(client_and_db) -> None:
    client, db = client_and_db
    prediction_id = prediction_id_for_run("run-1", "600519")
    _insert_prediction(db, prediction_id=prediction_id, run_id="run-1")
    _resolve_prediction(db, prediction_id)

    invalid_enum = client.put(
        "/api/v1/agent/runs/run-1/feedback",
        json={"feedback_value": "not_useful"},
    )
    assert invalid_enum.status_code == 422, invalid_enum.text

    mixed = client.put(
        f"/api/v1/agent/predictions/{prediction_id}/feedback",
        json={
            "feedback_value": "agree_hit",
            "outcome": "miss",
            "score": 0,
            "label": "miss",
        },
    )
    assert mixed.status_code == 422, mixed.text

    body_id = client.put(
        f"/api/v1/agent/predictions/{prediction_id}/feedback",
        json={
            "prediction_id": prediction_id,
            "feedback_value": "agree_hit",
        },
    )
    assert body_id.status_code == 422, body_id.text

    extra = client.put(
        "/api/v1/agent/runs/run-1/feedback",
        json={"feedback_value": "useful", "unexpected": "nope"},
    )
    assert extra.status_code == 422, extra.text

    empty = client.get(f"/api/v1/agent/predictions/{prediction_id}/feedback")
    assert empty.status_code == 200
    assert empty.json()["feedback_value"] is None


def test_soul_oversize_and_client_provenance_rejected(client_and_db) -> None:
    client, db = client_and_db
    prediction_id = prediction_id_for_run("run-1", "600519")
    _insert_prediction(db, prediction_id=prediction_id, run_id="run-1")
    _resolve_prediction(db, prediction_id)

    marker = client.put(
        "/api/v1/agent/runs/run-1/feedback",
        json={"feedback_value": "wrong", "note": AGENT_SOUL_MARKER},
    )
    assert marker.status_code == 422, marker.text
    end_marker = client.put(
        f"/api/v1/agent/predictions/{prediction_id}/feedback",
        json={"feedback_value": "context_note", "note": AGENT_SOUL_END_MARKER},
    )
    assert end_marker.status_code == 422, end_marker.text
    oversize = client.put(
        "/api/v1/agent/runs/run-1/feedback",
        json={"feedback_value": "useful", "note": "n" * (FEEDBACK_NOTE_MAX_LENGTH + 1)},
    )
    assert oversize.status_code == 422, oversize.text
    spoof = client.put(
        f"/api/v1/agent/predictions/{prediction_id}/feedback",
        json={
            "feedback_value": "agree_miss",
            "provenance_source": "system_resolve",
            "actor_id": "attacker",
        },
    )
    assert spoof.status_code == 422, spoof.text

    still_empty = client.get("/api/v1/agent/runs/run-1/feedback")
    assert still_empty.json()["feedback_value"] is None
    still_pred = client.get(f"/api/v1/agent/predictions/{prediction_id}/feedback")
    assert still_pred.json()["feedback_value"] is None


def test_feedback_does_not_block_resolve_or_rewrite_actuals(client_and_db) -> None:
    client, db = client_and_db
    prediction_id = prediction_id_for_run("run-1", "600519")
    _insert_prediction(db, prediction_id=prediction_id, run_id="run-1")
    pred_repo = AgentPredictionRepository(db, clock=_fixed_now)

    empty = client.get(f"/api/v1/agent/predictions/{prediction_id}/feedback")
    assert empty.json()["feedback_value"] is None
    due = pred_repo.list_due(as_of=_fixed_now(), limit=10)
    assert any(row.prediction_id == prediction_id for row in due)
    before = _resolve_prediction(db, prediction_id)
    after_resolve = pred_repo.get(prediction_id)
    assert after_resolve is not None
    assert after_resolve.status == STATUS_RESOLVED

    put_resp = client.put(
        f"/api/v1/agent/predictions/{prediction_id}/feedback",
        json={"feedback_value": "disagree_score", "note": "still a miss to me"},
    )
    assert put_resp.status_code == 200, put_resp.text
    after = pred_repo.get(prediction_id)
    assert after is not None
    assert after.status == STATUS_RESOLVED
    assert after.outcome == before
    assert after.resolved_at == after_resolve.resolved_at


def test_admin_auth_enabled_rejects_missing_and_invalid_session(tmp_path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    db_path = tmp_path / "agent_feedback_auth.db"
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
            prediction_id = prediction_id_for_run("run-1", "600519")
            _insert_prediction(db, prediction_id=prediction_id, run_id="run-1")
            _resolve_prediction(db, prediction_id)
            missing_get = client.get("/api/v1/agent/runs/run-1/feedback")
            missing_put = client.put(
                f"/api/v1/agent/predictions/{prediction_id}/feedback",
                json={"feedback_value": "agree_hit"},
            )
            invalid = client.put(
                "/api/v1/agent/runs/run-1/feedback",
                json={"feedback_value": "useful"},
                cookies={auth.COOKIE_NAME: "not-a-signed-session"},
            )
            session = auth.create_session()
            allowed = client.put(
                "/api/v1/agent/runs/run-1/feedback",
                json={"feedback_value": "useful"},
                cookies={auth.COOKIE_NAME: session},
            )
            allowed_pred = client.put(
                f"/api/v1/agent/predictions/{prediction_id}/feedback",
                json={"feedback_value": "context_note", "note": "context"},
                cookies={auth.COOKIE_NAME: session},
            )
            assert missing_get.status_code == 401
            assert missing_get.json()["error"] == "unauthorized"
            assert missing_put.status_code == 401
            assert missing_put.json()["error"] == "unauthorized"
            assert invalid.status_code == 401
            assert allowed.status_code == 200, allowed.text
            assert allowed.json()["feedback_value"] == "useful"
            assert allowed_pred.status_code == 200, allowed_pred.text
            assert allowed_pred.json()["feedback_value"] == "context_note"
    finally:
        os.environ.clear()
        os.environ.update(original_environ)
        DatabaseManager.reset_instance()
        Config.reset_instance()
        _reset_auth_globals()
