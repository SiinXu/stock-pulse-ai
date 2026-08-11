# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""FastAPI contract tests for agent-guided onboarding endpoints."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import src.auth as auth
from api.app import create_app
from src.config import Config
from src.storage import DatabaseManager


def _reset_auth_globals() -> None:
    auth._auth_enabled = None
    auth._session_secret = None
    auth._password_hash_salt = None
    auth._password_hash_stored = None
    auth._rate_limit = {}


@pytest.fixture
def client(tmp_path: Path):
    _reset_auth_globals()
    env_path = tmp_path / ".env"
    database_path = tmp_path / "onboarding.sqlite"
    env_path.write_text(
        "\n".join(
            (
                "STOCK_LIST=",
                "ADMIN_AUTH_ENABLED=false",
                f"DATABASE_PATH={database_path}",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    os.environ["ENV_FILE"] = str(env_path)
    os.environ["DATABASE_PATH"] = str(database_path)
    Config.reset_instance()
    DatabaseManager.reset_instance()
    with TestClient(create_app(static_dir=tmp_path / "empty-static")) as test_client:
        yield test_client, env_path
    DatabaseManager.reset_instance()
    Config.reset_instance()
    os.environ.pop("ENV_FILE", None)
    os.environ.pop("DATABASE_PATH", None)
    _reset_auth_globals()


def test_generate_plan_and_apply_round_trip(client) -> None:
    test_client, env_path = client
    plan_resp = test_client.post(
        "/api/v1/onboarding/plan",
        json={
            "profile": {
                "schema_version": 1,
                "experience_stage": "beginner",
                "markets": ["cn", "us"],
                "goals": ["pre_post_market"],
                "holdings": "none",
                "interaction": "web",
                "risk_tone": "conservative",
                "infrastructure": "cloud_key",
                "report_language": "en",
            },
            "model_available": False,
            "prefer_llm": True,
        },
    )
    assert plan_resp.status_code == 200, plan_resp.text
    plan = plan_resp.json()
    assert plan["engine"] == "rules"
    assert plan["feature_stage"] == "L0"
    assert plan["recommended_preset_id"] == "cloud-balanced"
    assert plan["config_items"]
    assert all("KEY" not in item["key"] or item["key"].endswith("_MODELS") for item in plan["config_items"] if "TOKEN" not in item["key"])

    config_resp = test_client.get("/api/v1/system/config")
    assert config_resp.status_code == 200, config_resp.text
    config_version = config_resp.json()["config_version"]

    apply_resp = test_client.post(
        "/api/v1/onboarding/apply",
        json={
            "profile": plan["profile"],
            "config_version": config_version,
            "confirm": True,
            "model_available": False,
            "prefer_llm": False,
        },
    )
    assert apply_resp.status_code == 200, apply_resp.text
    applied = apply_resp.json()
    assert applied["success"] is True
    assert applied["plan"]["engine"] == "rules"

    state_resp = test_client.get("/api/v1/onboarding/state")
    assert state_resp.status_code == 200
    state = state_resp.json()
    assert state["exists"] is True
    assert state["profile"]["report_language"] == "en"

    # Non-secret keys written into the active env file
    env_text = env_path.read_text(encoding="utf-8")
    assert "REPORT_LANGUAGE=en" in env_text or "REPORT_LANGUAGE" in env_text

    reset_resp = test_client.delete("/api/v1/onboarding/state")
    assert reset_resp.status_code == 200
    assert reset_resp.json()["success"] is True
    state_after = test_client.get("/api/v1/onboarding/state").json()
    assert state_after["exists"] is False


def test_invalid_profile_returns_400(client) -> None:
    test_client, _env_path = client
    resp = test_client.post(
        "/api/v1/onboarding/plan",
        json={"profile": {"markets": ["not-a-market"]}},
    )
    assert resp.status_code == 400
    body = resp.json()
    detail = body.get("detail") or body
    assert "onboarding_profile_invalid" in str(detail) or detail.get("error") == "onboarding_profile_invalid"


def test_first_run_and_demo_analysis_endpoints(client) -> None:
    test_client, _env_path = client
    readiness = test_client.get("/api/v1/onboarding/first-run")
    assert readiness.status_code == 200, readiness.text
    body = readiness.json()
    assert body["schema_version"] == 1
    assert body["demo_available"] is True
    assert body["config_mutated"] is False
    assert body["existing_config_untouched"] is True
    assert body["primary_path"] in {"configured", "local_ollama", "demo"}
    assert body["primary_cta"] in {"continue", "open_local_setup", "view_demo"}
    assert len(body["snapshot_id"]) == 24
    assert "headline" not in body
    assert "local_runtime" in body
    assert set(body["local_runtime"]) >= {"reachable", "models_available", "runnable", "reason_code"}

    demo = test_client.get("/api/v1/onboarding/demo-analysis", params={"report_language": "en"})
    assert demo.status_code == 200, demo.text
    demo_body = demo.json()
    assert demo_body["is_sample"] is True
    assert demo_body["stock_code"] == "600519"
    assert demo_body["sample_banner"]

    korean = test_client.get("/api/v1/onboarding/demo-analysis", params={"report_language": "ko"})
    assert korean.status_code == 200, korean.text
    assert korean.json()["report"]["meta"]["report_language"] == "ko"

    unsupported = test_client.get("/api/v1/onboarding/demo-analysis", params={"report_language": "ja"})
    assert unsupported.status_code == 422
