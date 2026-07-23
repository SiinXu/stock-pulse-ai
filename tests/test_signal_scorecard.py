# -*- coding: utf-8 -*-
"""Tests for the public signal scorecard aggregation and endpoint (Issue #379)."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import src.auth as auth
from api.app import create_app
from src.config import Config
from src.services.decision_signal_outcome_service import (
    DECISION_SIGNAL_OUTCOME_ENGINE_VERSION,
)
from src.services.signal_scorecard_service import SignalScorecardService
from src.storage import (
    DatabaseManager,
    DecisionSignalOutcomeRecord,
    DecisionSignalRecord,
)


@pytest.fixture()
def isolated_db(tmp_path):
    old_database_path = os.environ.get("DATABASE_PATH")
    db_path = tmp_path / "scorecard.db"
    os.environ["DATABASE_PATH"] = str(db_path)
    Config.reset_instance()
    DatabaseManager.reset_instance()
    db = DatabaseManager.get_instance()
    try:
        yield db
    finally:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        if old_database_path is None:
            os.environ.pop("DATABASE_PATH", None)
        else:
            os.environ["DATABASE_PATH"] = old_database_path


def _reset_auth_globals() -> None:
    auth._auth_enabled = None
    auth._session_secret = None
    auth._password_hash_salt = None
    auth._password_hash_stored = None


_SCORECARD_ENV_KEYS = ("SIGNAL_SCORECARD_PUBLIC_ENABLED", "SIGNAL_SCORECARD_MIN_SAMPLES")


@contextmanager
def _client(tmp_path, *, scorecard_enabled: bool):
    old_env_file = os.environ.get("ENV_FILE")
    old_database_path = os.environ.get("DATABASE_PATH")
    # Manage the scorecard flags directly in the process environment: dotenv does
    # not override an already-set os.environ value, so relying on the .env file
    # alone would leak the first test's value into the next.
    saved_scorecard = {key: os.environ.get(key) for key in _SCORECARD_ENV_KEYS}
    env_path = tmp_path / ".env"
    db_path = tmp_path / "scorecard_api.db"
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
    os.environ["SIGNAL_SCORECARD_PUBLIC_ENABLED"] = "true" if scorecard_enabled else "false"
    os.environ["SIGNAL_SCORECARD_MIN_SAMPLES"] = "1"
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
        for key, value in saved_scorecard.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        if old_env_file is None:
            os.environ.pop("ENV_FILE", None)
        else:
            os.environ["ENV_FILE"] = old_env_file
        if old_database_path is None:
            os.environ.pop("DATABASE_PATH", None)
        else:
            os.environ["DATABASE_PATH"] = old_database_path


def _add_signal_with_outcome(
    db,
    *,
    action: str = "buy",
    horizon: str = "3d",
    outcome: str = "hit",
    stock_return_pct: float = 5.0,
    anchor: date = date(2024, 5, 1),
    idx: int = 0,
) -> None:
    with db.session_scope() as session:
        signal = DecisionSignalRecord(
            stock_code="600519",
            stock_name="Test Co",
            market="cn",
            source_type="analysis",
            trace_id=f"trace-{action}-{horizon}-{outcome}-{idx}-{anchor.isoformat()}",
            market_phase="postmarket",
            trigger_source="api",
            action=action,
            action_label=action,
            horizon=horizon,
            reason="unit test",
            data_quality_summary_json=json.dumps({"level": "good"}),
            metadata_json=json.dumps({"holding_state": "unknown"}),
            plan_quality="complete",
            status="active",
        )
        session.add(signal)
        session.flush()
        session.add(
            DecisionSignalOutcomeRecord(
                signal_id=int(signal.id),
                horizon=horizon,
                engine_version=DECISION_SIGNAL_OUTCOME_ENGINE_VERSION,
                eval_status="completed",
                outcome=outcome,
                direction_expected="up",
                anchor_date=anchor,
                eval_window_days=3,
                stock_return_pct=stock_return_pct,
                action=action,
                market="cn",
                holding_state="unknown",
            )
        )


# --------------------------------------------------------------------------
# Aggregation service.
# --------------------------------------------------------------------------


def test_bucket_below_min_samples_is_insufficient_data(isolated_db) -> None:
    _add_signal_with_outcome(isolated_db, outcome="hit", idx=1)
    _add_signal_with_outcome(isolated_db, outcome="miss", stock_return_pct=-5.0, idx=2)

    card = SignalScorecardService().build_scorecard(min_samples=5)

    buckets = {(b["signal_type"], b["horizon"]): b for b in card["by_signal_type_horizon"]}
    bucket = buckets[("buy", "3d")]
    assert bucket["status"] == "insufficient_data"
    assert bucket["hit_rate_pct"] is None
    assert bucket["sample_size"] == 2
    assert card["overall"]["status"] == "insufficient_data"


def test_bucket_at_threshold_reports_hit_rate(isolated_db) -> None:
    for i in range(3):
        _add_signal_with_outcome(isolated_db, outcome="hit", idx=10 + i)
    for i in range(2):
        _add_signal_with_outcome(isolated_db, outcome="miss", stock_return_pct=-5.0, idx=20 + i)

    card = SignalScorecardService().build_scorecard(min_samples=5)

    bucket = next(
        b for b in card["by_signal_type_horizon"] if b["signal_type"] == "buy" and b["horizon"] == "3d"
    )
    assert bucket["status"] == "ok"
    assert bucket["hit_rate_pct"] == 60.0
    assert card["overall"]["hit_rate_pct"] == 60.0


def test_return_distribution_bands(isolated_db) -> None:
    _add_signal_with_outcome(isolated_db, outcome="hit", stock_return_pct=12.0, idx=31)
    _add_signal_with_outcome(isolated_db, outcome="hit", stock_return_pct=3.0, idx=32)
    _add_signal_with_outcome(isolated_db, outcome="miss", stock_return_pct=-6.0, idx=33)

    card = SignalScorecardService().build_scorecard(min_samples=1)

    bands = {b["band"]: b["count"] for b in card["return_distribution"]}
    assert bands[">= +10%"] == 1
    assert bands["+2% ~ +5%"] == 1
    assert bands["-10% ~ -5%"] == 1


def test_recent_misses_are_non_sensitive_and_recent_first(isolated_db) -> None:
    _add_signal_with_outcome(isolated_db, outcome="miss", stock_return_pct=-4.0, anchor=date(2024, 4, 1), idx=41)
    _add_signal_with_outcome(isolated_db, outcome="miss", stock_return_pct=-8.0, anchor=date(2024, 5, 20), idx=42)
    _add_signal_with_outcome(isolated_db, outcome="hit", idx=43)

    card = SignalScorecardService().build_scorecard(min_samples=1)

    misses = card["recent_misses"]
    assert len(misses) == 2
    assert misses[0]["anchor_date"] == "2024-05-20"  # most recent first
    # Non-sensitive: no stock identity is exposed.
    for miss in misses:
        assert "stock_code" not in miss and "stock_name" not in miss
        assert set(miss.keys()) == {"signal_type", "horizon", "return_pct", "anchor_date"}


# --------------------------------------------------------------------------
# Public endpoint.
# --------------------------------------------------------------------------


def test_scorecard_returns_404_when_disabled(tmp_path) -> None:
    with _client(tmp_path, scorecard_enabled=False) as (client, _db):
        resp = client.get("/api/v1/scorecard")
        assert resp.status_code == 404


def test_scorecard_public_no_auth_when_enabled(tmp_path) -> None:
    with _client(tmp_path, scorecard_enabled=True) as (client, db):
        _add_signal_with_outcome(db, outcome="hit", idx=51)
        _add_signal_with_outcome(db, outcome="miss", stock_return_pct=-5.0, idx=52)

        # No session cookie is provided; the public route must still be reachable
        # even though ADMIN_AUTH_ENABLED=true.
        resp = client.get("/api/v1/scorecard")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["min_samples"] == 1
        assert body["overall"]["sample_size"] == 2
        assert any(b["signal_type"] == "buy" for b in body["by_signal_type_horizon"])
        # Aggregated, non-sensitive payload only.
        assert "recent_misses" in body
        assert all("stock_code" not in miss for miss in body["recent_misses"])
