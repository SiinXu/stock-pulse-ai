# -*- coding: utf-8 -*-
"""Tests for memorable/ignored signal curation and its reflection wiring (#118)."""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import src.auth as auth
from api.app import create_app
from src.config import Config
from src.services.decision_memory_service import DecisionMemoryService
from src.services.decision_signal_service import DecisionSignalNotFoundError
from src.services.decision_signal_outcome_service import (
    DECISION_SIGNAL_OUTCOME_ENGINE_VERSION,
)
from src.services.decision_signal_service import DecisionSignalService
from src.storage import (
    DatabaseManager,
    DecisionSignalOutcomeRecord,
    DecisionSignalRecord,
)


_FIXED_NOW = datetime(2024, 6, 1, 12, 0, 0)


@pytest.fixture()
def isolated_db(tmp_path):
    old_database_path = os.environ.get("DATABASE_PATH")
    db_path = tmp_path / "memory_flags.db"
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


@pytest.fixture()
def client_and_db(tmp_path):
    old_env_file = os.environ.get("ENV_FILE")
    old_database_path = os.environ.get("DATABASE_PATH")
    env_path = tmp_path / ".env"
    db_path = tmp_path / "memory_flags_api.db"
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


def _canon(code: str = "600519", market: str = "cn") -> str:
    return DecisionSignalService.normalize_stock_code_for_signal(code, market=market)


def _insert_signal(db, *, action: str = "buy", created_at: datetime) -> int:
    with db.session_scope() as session:
        row = DecisionSignalRecord(
            stock_code=_canon(),
            stock_name="Test Co",
            market="cn",
            source_type="analysis",
            trace_id=f"trace-{action}-{created_at.isoformat()}",
            market_phase="postmarket",
            trigger_source="api",
            action=action,
            action_label=action,
            horizon="3d",
            reason="unit test",
            data_quality_summary_json=json.dumps({"level": "good"}),
            metadata_json=json.dumps({"holding_state": "unknown"}),
            plan_quality="complete",
            status="active",
            created_at=created_at,
        )
        session.add(row)
        session.flush()
        return int(row.id)


def _insert_outcome(db, *, signal_id: int, outcome: str = "hit") -> None:
    with db.session_scope() as session:
        session.add(
            DecisionSignalOutcomeRecord(
                signal_id=signal_id,
                horizon="3d",
                engine_version=DECISION_SIGNAL_OUTCOME_ENGINE_VERSION,
                eval_status="completed",
                outcome=outcome,
                direction_expected="up",
                anchor_date=date(2024, 5, 1),
                eval_window_days=3,
                stock_return_pct=5.0 if outcome == "hit" else -5.0,
                action="buy",
                market="cn",
                holding_state="unknown",
            )
        )


def _seed(db, *, outcome: str = "hit", age_days: int = 30) -> int:
    sid = _insert_signal(db, created_at=_FIXED_NOW - timedelta(days=age_days))
    _insert_outcome(db, signal_id=sid, outcome=outcome)
    return sid


def _build(db):
    return DecisionMemoryService().build_reflection(
        stock_code="600519", market="cn", lookback=10, min_age_days=3, min_samples=1, now=_FIXED_NOW
    )


# --------------------------------------------------------------------------
# Flag service.
# --------------------------------------------------------------------------


def test_get_flag_defaults_false_when_unset(isolated_db) -> None:
    sid = _seed(isolated_db)
    flag = DecisionMemoryService().get_flag(sid)
    assert flag["signal_id"] == sid
    assert flag["memorable"] is False
    assert flag["ignored"] is False


def test_set_flag_memorable_then_partial_update_preserves_ignored(isolated_db) -> None:
    sid = _seed(isolated_db)
    service = DecisionMemoryService()

    first = service.set_flag(sid, memorable=True, ignored=True)
    assert first["memorable"] is True and first["ignored"] is True

    # Update only memorable; ignored must be preserved.
    second = service.set_flag(sid, memorable=False)
    assert second["memorable"] is False
    assert second["ignored"] is True

    assert service.get_flag(sid)["ignored"] is True


def test_set_flag_missing_signal_raises_not_found(isolated_db) -> None:
    with pytest.raises(DecisionSignalNotFoundError):
        DecisionMemoryService().set_flag(999999, memorable=True)
    with pytest.raises(DecisionSignalNotFoundError):
        DecisionMemoryService().get_flag(999999)


# --------------------------------------------------------------------------
# Reflection wiring.
# --------------------------------------------------------------------------


def test_ignored_signal_excluded_from_reflection(isolated_db) -> None:
    keep = _seed(isolated_db, outcome="hit")
    drop = _seed(isolated_db, outcome="miss")
    DecisionMemoryService().set_flag(drop, ignored=True)

    reflection = _build(isolated_db)

    assert reflection is not None
    # Only the kept signal's outcome contributes.
    assert reflection.same_stock_total == 1
    assert {c.signal_id for c in reflection.recent_calls} == {keep}


def test_all_signals_ignored_returns_none(isolated_db) -> None:
    sid = _seed(isolated_db)
    DecisionMemoryService().set_flag(sid, ignored=True)
    assert _build(isolated_db) is None


def test_memorable_signal_is_marked_and_ordered_first(isolated_db) -> None:
    older = _insert_signal(isolated_db, created_at=_FIXED_NOW - timedelta(days=40))
    _insert_outcome(isolated_db, signal_id=older, outcome="hit")
    newer = _insert_signal(isolated_db, created_at=_FIXED_NOW - timedelta(days=10))
    _insert_outcome(isolated_db, signal_id=newer, outcome="hit")
    DecisionMemoryService().set_flag(older, memorable=True)

    reflection = _build(isolated_db)

    assert reflection is not None
    # The older-but-memorable call is ordered ahead of the newer one.
    assert reflection.recent_calls[0].signal_id == older
    assert reflection.recent_calls[0].memorable is True
    assert reflection.recent_calls[1].signal_id == newer
    assert reflection.recent_calls[1].memorable is False


# --------------------------------------------------------------------------
# API round-trip.
# --------------------------------------------------------------------------


def test_memory_flag_endpoints_round_trip(client_and_db) -> None:
    client, _db = client_and_db
    created = client.post(
        "/api/v1/decision-signals",
        json={
            "stock_code": "SH600519",
            "market": "cn",
            "source_type": "analysis",
            "trigger_source": "api",
            "action": "buy",
            "horizon": "3d",
            "reason": "unit test",
        },
    )
    assert created.status_code == 200, created.text
    signal_id = created.json()["item"]["id"]

    # Defaults before any write.
    initial = client.get(f"/api/v1/decision-signals/{signal_id}/memory-flag")
    assert initial.status_code == 200
    assert initial.json() == {
        "signal_id": signal_id,
        "memorable": False,
        "ignored": False,
        "created_at": None,
        "updated_at": None,
    }

    patched = client.patch(
        f"/api/v1/decision-signals/{signal_id}/memory-flag",
        json={"memorable": True},
    )
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["memorable"] is True and body["ignored"] is False

    fetched = client.get(f"/api/v1/decision-signals/{signal_id}/memory-flag")
    assert fetched.json()["memorable"] is True

    missing = client.get("/api/v1/decision-signals/999999/memory-flag")
    assert missing.status_code == 404
