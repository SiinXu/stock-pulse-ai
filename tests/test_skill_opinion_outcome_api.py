# -*- coding: utf-8 -*-
"""API tests for skill-opinion outcome endpoints."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

try:
    import litellm  # noqa: F401
except ModuleNotFoundError:
    sys.modules["litellm"] = MagicMock()

import src.auth as auth
from api.app import create_app
from src.config import Config
from src.schemas.skill_opinion_outcome import SkillOpinionInput
from src.services.skill_opinion_outcome_service import (
    SKILL_OPINION_OUTCOME_ENGINE_VERSION,
)
from src.services.skill_opinion_sample_service import SkillOpinionSampleService
from src.storage import AnalysisHistory, DatabaseManager


def _reset_auth_globals() -> None:
    auth._auth_enabled = None
    auth._session_secret = None
    auth._password_hash_salt = None
    auth._password_hash_stored = None
    auth._rate_limit = {}


@pytest.fixture()
def client_and_db(tmp_path):
    old_env_file = os.environ.get("ENV_FILE")
    old_database_path = os.environ.get("DATABASE_PATH")
    env_path = tmp_path / ".env"
    db_path = tmp_path / "skill_outcome_api.db"
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


def _seed_sample(db: DatabaseManager) -> int:
    with db.session_scope() as session:
        row = AnalysisHistory(
            query_id="skill-outcome-api",
            code="600519",
            report_type="simple",
            raw_result=json.dumps(
                {
                    "dashboard": {
                        "strategy_synthesis": {
                            "supporting_skills": [
                                {
                                    "skill_id": "bull_trend",
                                    "signal": "buy",
                                    "confidence": 0.8,
                                }
                            ],
                            "opposing_skills": [],
                        }
                    }
                }
            ),
            context_snapshot=json.dumps(
                {
                    "analysis_context_pack_overview": {
                        "data_quality": {"level": "usable"}
                    }
                }
            ),
            created_at=datetime(2026, 8, 4, 12, 0, 0),
        )
        session.add(row)
        session.flush()
        history_id = int(row.id)

    service = SkillOpinionSampleService(db)
    created = service.persist(
        analysis_history_id=history_id,
        stock_code="600519",
        opinions=[
            SkillOpinionInput(
                skill_id="bull_trend",
                signal="buy",
                confidence=0.8,
            )
        ],
        data_quality_level="usable",
    )
    assert created == 1
    return history_id


def test_skill_outcome_api_requires_session_when_admin_auth_enabled(
    tmp_path,
) -> None:
    old_env_file = os.environ.get("ENV_FILE")
    old_database_path = os.environ.get("DATABASE_PATH")
    env_path = tmp_path / ".env"
    db_path = tmp_path / "skill_outcome_auth.db"
    static_dir = tmp_path / "empty-static"
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
    os.environ["ENV_FILE"] = str(env_path)
    os.environ["DATABASE_PATH"] = str(db_path)
    _reset_auth_globals()
    Config.reset_instance()
    DatabaseManager.reset_instance()

    try:
        client = TestClient(create_app(static_dir=Path(static_dir)))
        for path in (
            "/api/v1/skill-outcomes/stats",
            "/api/v1/skill-outcomes/samples",
            "/api/v1/skill-outcomes",
        ):
            resp = client.get(path)
            assert resp.status_code == 401, path
            assert resp.json()["error"] == "unauthorized"
        run_resp = client.post("/api/v1/skill-outcomes/run", json={})
        assert run_resp.status_code == 401
        assert run_resp.json()["error"] == "unauthorized"
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


def test_samples_stats_run_and_list_shapes(client_and_db) -> None:
    client, db = client_and_db
    history_id = _seed_sample(db)

    samples_resp = client.get("/api/v1/skill-outcomes/samples")
    assert samples_resp.status_code == 200, samples_resp.text
    samples = samples_resp.json()
    assert samples["total"] == 1
    assert samples["limit"] == 50
    assert samples["offset"] == 0
    item = samples["items"][0]
    assert item["skill_id"] == "bull_trend"
    assert item["signal"] == "buy"
    assert item["confidence"] == 0.8
    assert item["analysis_history_id"] == history_id
    assert "reasoning" not in item

    stats_resp = client.get("/api/v1/skill-outcomes/stats")
    assert stats_resp.status_code == 200, stats_resp.text
    stats = stats_resp.json()
    assert stats["engine_version"] == SKILL_OPINION_OUTCOME_ENGINE_VERSION
    assert stats["minimum_evaluated_sample_size"] == 30
    assert isinstance(stats["buckets"], list)

    run_resp = client.post(
        "/api/v1/skill-outcomes/run",
        json={"analysis_history_id": history_id, "limit": 10},
    )
    assert run_resp.status_code == 200, run_resp.text
    run_body = run_resp.json()
    assert run_body["engine_version"] == SKILL_OPINION_OUTCOME_ENGINE_VERSION
    assert run_body["limit_unit"] == "outcome_key"
    assert "processed_keys" in run_body
    assert "samples_created" in run_body
    assert isinstance(run_body["items"], list)
    assert isinstance(run_body["errors"], list)

    list_resp = client.get("/api/v1/skill-outcomes", params={"limit": 20})
    assert list_resp.status_code == 200, list_resp.text
    listed = list_resp.json()
    assert listed["engine_version"] == SKILL_OPINION_OUTCOME_ENGINE_VERSION
    assert listed["total"] >= 0
    assert isinstance(listed["items"], list)


def test_stats_rejects_conflicting_skill_filters(client_and_db) -> None:
    client, _db = client_and_db
    resp = client.get(
        "/api/v1/skill-outcomes/stats",
        params=[("skill_id", "bull_trend"), ("skill_ids", "hot_theme")],
    )
    assert resp.status_code == 400
    body = resp.json()
    detail = body.get("detail") or body
    message = detail.get("message") if isinstance(detail, dict) else str(detail)
    assert "mutually exclusive" in message
