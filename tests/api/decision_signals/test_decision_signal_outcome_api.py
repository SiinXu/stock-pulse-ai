# -*- coding: utf-8 -*-
"""API tests for DecisionSignal P5 outcomes and feedback."""

from __future__ import annotations

import os
import sys
from datetime import date
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
from src.schemas.memory_write_guard import FEEDBACK_NOTE_MAX_LENGTH
from src.storage import DatabaseManager, StockDaily


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
    db_path = tmp_path / "decision_signal_outcome_api.db"
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


def _payload(**overrides):
    payload = {
        "stock_code": "600519",
        "stock_name": "贵州茅台",
        "market": "cn",
        "source_type": "analysis",
        "source_agent": "api-test",
        "source_report_id": 4301,
        "trace_id": "trace-outcome-api",
        "decision_profile": "balanced",
        "market_phase": "postmarket",
        "trigger_source": "api",
        "action": "buy",
        "confidence": 0.75,
        "score": 80,
        "horizon": "3d",
        "entry_low": 100,
        "stop_loss": 95,
        "reason": "突破平台",
        "data_quality_summary": {"level": "good"},
        "metadata": {
            "market_phase_summary": {"session_date": "2024-01-02"},
            "holding_state": "holding",
            "profile_source": "auto_default",
        },
    }
    payload.update(overrides)
    return payload


def _seed_bars(db: DatabaseManager, *, code: str = "600519") -> None:
    with db.session_scope() as session:
        session.add(StockDaily(code=code, date=date(2024, 1, 2), open=100, high=101, low=99, close=100))
        session.add(StockDaily(code=code, date=date(2024, 1, 3), open=103, high=104, low=102, close=103))
        session.add(StockDaily(code=code, date=date(2024, 1, 4), open=104, high=105, low=103, close=104))
        session.add(StockDaily(code=code, date=date(2024, 1, 5), open=105, high=106, low=104, close=105))


def test_outcome_run_list_stats_signal_outcomes_and_feedback(client_and_db) -> None:
    client, db = client_and_db
    created_resp = client.post("/api/v1/decision-signals", json=_payload())
    assert created_resp.status_code == 200, created_resp.text
    signal_id = created_resp.json()["item"]["id"]
    _seed_bars(db)

    run_resp = client.post(
        "/api/v1/decision-signals/outcomes/run",
        json={"signal_id": signal_id},
    )
    assert run_resp.status_code == 200, run_resp.text
    run_data = run_resp.json()
    assert run_data["evaluated"] == 1
    assert run_data["created"] == 1
    assert run_data["items"][0]["outcome"] == "hit"
    assert run_data["items"][0]["stock_return_pct"] == 5.0
    assert run_data["items"][0]["holding_state"] == "holding"

    second_run_resp = client.post(
        "/api/v1/decision-signals/outcomes/run",
        json={"signal_id": signal_id},
    )
    assert second_run_resp.status_code == 200, second_run_resp.text
    assert second_run_resp.json()["evaluated"] == 0
    assert second_run_resp.json()["skipped"] == 1

    list_resp = client.get(
        "/api/v1/decision-signals/outcomes",
        params={"signal_id": signal_id, "horizon": "3d"},
    )
    assert list_resp.status_code == 200, list_resp.text
    assert list_resp.json()["total"] == 1

    stats_resp = client.get("/api/v1/decision-signals/outcomes/stats")
    assert stats_resp.status_code == 200, stats_resp.text
    stats = stats_resp.json()
    assert stats["total"] == 1
    assert stats["hit"] == 1
    assert stats["minimum_completed_sample_size"] == 30
    assert stats["sample_sufficient"] is False
    assert stats["hit_rate_pct"] is None
    assert stats["breakdowns"]["action"][0]["value"] == "buy"
    assert stats["breakdowns"]["action"][0]["sample_sufficient"] is False
    assert "period" in stats["breakdowns"]
    assert stats.get("profile_calibration") in (None, {})

    signal_outcomes_resp = client.get(f"/api/v1/decision-signals/{signal_id}/outcomes")
    assert signal_outcomes_resp.status_code == 200, signal_outcomes_resp.text
    assert signal_outcomes_resp.json()["items"][0]["signal_id"] == signal_id

    empty_feedback_resp = client.get(f"/api/v1/decision-signals/{signal_id}/feedback")
    assert empty_feedback_resp.status_code == 200, empty_feedback_resp.text
    assert empty_feedback_resp.json()["feedback_value"] is None
    assert empty_feedback_resp.json()["provenance_source"] is None
    assert empty_feedback_resp.json()["actor_id"] is None

    put_feedback_resp = client.put(
        f"/api/v1/decision-signals/{signal_id}/feedback",
        json={
            "feedback_value": "useful",
            "reason_code": "matched_plan",
            "note": "后验表现符合预期",
            "source": "web",
        },
    )
    assert put_feedback_resp.status_code == 200, put_feedback_resp.text
    assert put_feedback_resp.json()["feedback_value"] == "useful"
    assert put_feedback_resp.json()["source"] == "web"
    assert put_feedback_resp.json()["provenance_source"] == "user_feedback"
    assert put_feedback_resp.json()["actor_id"] == "local_admin"

    get_feedback_resp = client.get(f"/api/v1/decision-signals/{signal_id}/feedback")
    assert get_feedback_resp.status_code == 200, get_feedback_resp.text
    assert get_feedback_resp.json()["reason_code"] == "matched_plan"
    assert get_feedback_resp.json()["provenance_source"] == "user_feedback"
    assert get_feedback_resp.json()["actor_id"] == "local_admin"


def test_feedback_put_rejects_fact_fields_and_leaves_outcomes_unchanged(client_and_db) -> None:
    client, db = client_and_db
    created_resp = client.post("/api/v1/decision-signals", json=_payload(trace_id="trace-fact-opinion-api"))
    assert created_resp.status_code == 200, created_resp.text
    signal_id = created_resp.json()["item"]["id"]
    _seed_bars(db)

    run_resp = client.post(
        "/api/v1/decision-signals/outcomes/run",
        json={"signal_id": signal_id},
    )
    assert run_resp.status_code == 200, run_resp.text
    before = run_resp.json()["items"][0]
    assert before["outcome"] == "hit"
    assert before["stock_return_pct"] == 5.0

    mixed_resp = client.put(
        f"/api/v1/decision-signals/{signal_id}/feedback",
        json={
            "feedback_value": "not_useful",
            "source": "web",
            "outcome": "miss",
            "start_price": 1,
            "label": "miss",
            "stock_return_pct": -99,
        },
    )
    assert mixed_resp.status_code == 422, mixed_resp.text

    empty_feedback = client.get(f"/api/v1/decision-signals/{signal_id}/feedback")
    assert empty_feedback.status_code == 200, empty_feedback.text
    assert empty_feedback.json()["feedback_value"] is None

    ok_resp = client.put(
        f"/api/v1/decision-signals/{signal_id}/feedback",
        json={"feedback_value": "not_useful", "source": "web", "note": "opinion only"},
    )
    assert ok_resp.status_code == 200, ok_resp.text
    assert ok_resp.json()["feedback_value"] == "not_useful"

    outcomes_resp = client.get(f"/api/v1/decision-signals/{signal_id}/outcomes")
    assert outcomes_resp.status_code == 200, outcomes_resp.text
    item = outcomes_resp.json()["items"][0]
    assert item["outcome"] == "hit"
    assert item["stock_return_pct"] == 5.0
    assert item["eval_status"] == before["eval_status"]
    assert item["start_price"] == before["start_price"]


def test_feedback_put_rejects_soul_markers_and_oversize_notes(client_and_db) -> None:
    client, db = client_and_db
    created_resp = client.post(
        "/api/v1/decision-signals",
        json=_payload(trace_id="trace-soul-oversize-api"),
    )
    assert created_resp.status_code == 200, created_resp.text
    signal_id = created_resp.json()["item"]["id"]
    _seed_bars(db)

    run_resp = client.post(
        "/api/v1/decision-signals/outcomes/run",
        json={"signal_id": signal_id},
    )
    assert run_resp.status_code == 200, run_resp.text
    before = run_resp.json()["items"][0]
    assert before["outcome"] == "hit"

    marker_resp = client.put(
        f"/api/v1/decision-signals/{signal_id}/feedback",
        json={
            "feedback_value": "useful",
            "source": "web",
            "note": f"looks fine {AGENT_SOUL_MARKER}",
        },
    )
    assert marker_resp.status_code == 422, marker_resp.text

    end_marker_resp = client.put(
        f"/api/v1/decision-signals/{signal_id}/feedback",
        json={
            "feedback_value": "useful",
            "source": "web",
            "note": AGENT_SOUL_END_MARKER,
        },
    )
    assert end_marker_resp.status_code == 422, end_marker_resp.text

    mixed_case_resp = client.put(
        f"/api/v1/decision-signals/{signal_id}/feedback",
        json={
            "feedback_value": "useful",
            "source": "web",
            "note": "<!-- StockPulse-Agent-Soul -->",
        },
    )
    assert mixed_case_resp.status_code == 422, mixed_case_resp.text

    control_resp = client.put(
        f"/api/v1/decision-signals/{signal_id}/feedback",
        json={
            "feedback_value": "useful",
            "source": "web",
            "note": "ok\x00spoof",
        },
    )
    assert control_resp.status_code == 422, control_resp.text

    oversize_resp = client.put(
        f"/api/v1/decision-signals/{signal_id}/feedback",
        json={
            "feedback_value": "useful",
            "source": "web",
            "note": "n" * (FEEDBACK_NOTE_MAX_LENGTH + 1),
        },
    )
    assert oversize_resp.status_code == 422, oversize_resp.text

    empty_feedback = client.get(f"/api/v1/decision-signals/{signal_id}/feedback")
    assert empty_feedback.status_code == 200, empty_feedback.text
    assert empty_feedback.json()["feedback_value"] is None

    legal_note = "n" * FEEDBACK_NOTE_MAX_LENGTH
    ok_resp = client.put(
        f"/api/v1/decision-signals/{signal_id}/feedback",
        json={
            "feedback_value": "useful",
            "reason_code": "matched_plan",
            "note": legal_note,
            "source": "web",
        },
    )
    assert ok_resp.status_code == 200, ok_resp.text
    assert ok_resp.json()["note"] == legal_note
    assert ok_resp.json()["source"] == "web"

    overwrite_resp = client.put(
        f"/api/v1/decision-signals/{signal_id}/feedback",
        json={
            "feedback_value": "not_useful",
            "source": "web",
            "note": "stockpulse-agent-soul",
        },
    )
    assert overwrite_resp.status_code == 422, overwrite_resp.text
    kept = client.get(f"/api/v1/decision-signals/{signal_id}/feedback")
    assert kept.status_code == 200, kept.text
    assert kept.json()["feedback_value"] == "useful"
    assert kept.json()["note"] == legal_note

    outcomes_resp = client.get(f"/api/v1/decision-signals/{signal_id}/outcomes")
    assert outcomes_resp.status_code == 200, outcomes_resp.text
    item = outcomes_resp.json()["items"][0]
    assert item["outcome"] == "hit"
    assert item["stock_return_pct"] == before["stock_return_pct"]


def test_feedback_put_rejects_client_provenance_and_keeps_transport_source(
    client_and_db,
) -> None:
    client, _db = client_and_db
    created_resp = client.post(
        "/api/v1/decision-signals",
        json=_payload(trace_id="trace-memory-provenance-api"),
    )
    assert created_resp.status_code == 200, created_resp.text
    signal_id = created_resp.json()["item"]["id"]

    empty = client.get(f"/api/v1/decision-signals/{signal_id}/feedback")
    assert empty.status_code == 200, empty.text
    assert empty.json()["feedback_value"] is None
    assert empty.json()["provenance_source"] is None
    assert empty.json()["actor_id"] is None

    spoof_source = client.put(
        f"/api/v1/decision-signals/{signal_id}/feedback",
        json={
            "feedback_value": "useful",
            "source": "web",
            "provenance_source": "system_resolve",
        },
    )
    assert spoof_source.status_code == 422, spoof_source.text

    spoof_actor = client.put(
        f"/api/v1/decision-signals/{signal_id}/feedback",
        json={
            "feedback_value": "useful",
            "source": "web",
            "actor_id": "root",
        },
    )
    assert spoof_actor.status_code == 422, spoof_actor.text

    spoof_operator = client.put(
        f"/api/v1/decision-signals/{signal_id}/feedback",
        json={
            "feedback_value": "useful",
            "source": "web",
            "provenance_source": "operator",
        },
    )
    assert spoof_operator.status_code == 422, spoof_operator.text

    spoof_transport = client.put(
        f"/api/v1/decision-signals/{signal_id}/feedback",
        json={
            "feedback_value": "useful",
            "source": "system_resolve",
        },
    )
    assert spoof_transport.status_code == 422, spoof_transport.text

    still_empty = client.get(f"/api/v1/decision-signals/{signal_id}/feedback")
    assert still_empty.status_code == 200, still_empty.text
    assert still_empty.json()["feedback_value"] is None
    assert still_empty.json()["provenance_source"] is None

    ok_resp = client.put(
        f"/api/v1/decision-signals/{signal_id}/feedback",
        json={
            "feedback_value": "useful",
            "reason_code": "matched_plan",
            "note": "opinion only",
            "source": "web",
        },
    )
    assert ok_resp.status_code == 200, ok_resp.text
    body = ok_resp.json()
    assert body["source"] == "web"
    assert body["provenance_source"] == "user_feedback"
    assert body["actor_id"] == "local_admin"


def test_outcome_api_rejects_invalid_params_and_returns_404(client_and_db) -> None:
    client, _db = client_and_db

    missing_run_resp = client.post(
        "/api/v1/decision-signals/outcomes/run",
        json={"signal_id": 999999},
    )
    assert missing_run_resp.status_code == 404

    invalid_run_resp = client.post(
        "/api/v1/decision-signals/outcomes/run",
        json={"horizons": ["bad"]},
    )
    assert invalid_run_resp.status_code == 422

    invalid_list_resp = client.get(
        "/api/v1/decision-signals/outcomes",
        params={"outcome": "bad"},
    )
    assert invalid_list_resp.status_code == 400

    missing_outcomes_resp = client.get("/api/v1/decision-signals/999999/outcomes")
    assert missing_outcomes_resp.status_code == 404

    missing_feedback_resp = client.get("/api/v1/decision-signals/999999/feedback")
    assert missing_feedback_resp.status_code == 404


def test_outcome_stats_profile_calibration_when_gate_enabled(
    client_and_db,
    monkeypatch,
) -> None:
    client, db = client_and_db
    monkeypatch.setenv("DECISION_PROFILE_CALIBRATION_ENABLED", "true")
    from src.config import Config

    Config.reset_instance()
    created_resp = client.post("/api/v1/decision-signals", json=_payload())
    assert created_resp.status_code == 200, created_resp.text
    signal_id = created_resp.json()["item"]["id"]
    _seed_bars(db)
    run_resp = client.post(
        "/api/v1/decision-signals/outcomes/run",
        json={"signal_id": signal_id},
    )
    assert run_resp.status_code == 200, run_resp.text

    stats_resp = client.get("/api/v1/decision-signals/outcomes/stats")
    assert stats_resp.status_code == 200, stats_resp.text
    calibration = stats_resp.json()["profile_calibration"]
    assert calibration["minimum_completed_sample_size"] == 30
    assert set(calibration["breakdowns"]) == {
        "decision_profile",
        "decision_profile_action",
        "decision_profile_horizon",
        "decision_profile_market_phase",
        "decision_profile_data_quality_level",
        "profile_source",
    }
    assert calibration["breakdowns"]["decision_profile"][0]["dimensions"] == {
        "decision_profile": "balanced",
    }
    assert calibration["breakdowns"]["profile_source"][0]["dimensions"] == {
        "profile_source": "auto_default",
    }

    monkeypatch.delenv("DECISION_PROFILE_CALIBRATION_ENABLED", raising=False)
    Config.reset_instance()


def test_outcome_run_retries_transient_unable_by_default(client_and_db) -> None:
    client, db = client_and_db
    created_resp = client.post("/api/v1/decision-signals", json=_payload())
    assert created_resp.status_code == 200, created_resp.text
    signal_id = created_resp.json()["item"]["id"]
    with db.session_scope() as session:
        session.add(StockDaily(code="600519", date=date(2024, 1, 2), open=100, high=101, low=99, close=100))
        session.add(StockDaily(code="600519", date=date(2024, 1, 3), open=103, high=104, low=102, close=103))

    first_run = client.post(
        "/api/v1/decision-signals/outcomes/run",
        json={"signal_id": signal_id},
    )
    assert first_run.status_code == 200, first_run.text
    assert first_run.json()["items"][0]["unable_reason"] == "insufficient_forward_bars"

    with db.session_scope() as session:
        session.add(StockDaily(code="600519", date=date(2024, 1, 4), open=104, high=105, low=103, close=104))
        session.add(StockDaily(code="600519", date=date(2024, 1, 5), open=105, high=106, low=104, close=105))
    second_run = client.post(
        "/api/v1/decision-signals/outcomes/run",
        json={"signal_id": signal_id},
    )

    assert second_run.status_code == 200, second_run.text
    second_data = second_run.json()
    assert second_data["evaluated"] == 1
    assert second_data["updated"] == 1
    assert second_data["skipped"] == 0
    assert second_data["items"][0]["eval_status"] == "completed"
    assert second_data["items"][0]["stock_return_pct"] == 5.0


def test_outcome_run_uses_hk_alias_stock_code_filter(client_and_db) -> None:
    client, db = client_and_db
    created_resp = client.post(
        "/api/v1/decision-signals",
        json=_payload(
            stock_code="00700",
            stock_name="Tencent",
            market="hk",
            horizon="1d",
            trace_id="trace-outcome-api-hk",
        ),
    )
    assert created_resp.status_code == 200, created_resp.text
    signal_id = created_resp.json()["item"]["id"]
    assert created_resp.json()["item"]["stock_code"] == "HK00700"
    _seed_bars(db, code="HK00700")

    run_resp = client.post(
        "/api/v1/decision-signals/outcomes/run",
        json={"stock_code": "00700", "horizons": ["1d"]},
    )
    assert run_resp.status_code == 200, run_resp.text
    run_data = run_resp.json()
    assert run_data["evaluated"] == 1
    assert run_data["created"] == 1
    assert run_data["items"][0]["signal_id"] == signal_id

    force_resp = client.post(
        "/api/v1/decision-signals/outcomes/run",
        json={"stock_code": "00700", "horizons": ["1d"], "force": True},
    )
    assert force_resp.status_code == 200, force_resp.text
    force_data = force_resp.json()
    assert force_data["evaluated"] == 1
    assert force_data["updated"] == 1
    assert force_data["items"][0]["signal_id"] == signal_id
