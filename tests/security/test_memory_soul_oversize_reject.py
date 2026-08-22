# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Real-SQLite tests: Soul markers and oversize notes are not persisted (#1124 DAG-2)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from src.agent.soul import AGENT_SOUL_END_MARKER, AGENT_SOUL_MARKER
from src.config import Config
from src.repositories.agent_episode_repo import AgentEpisodeRepository
from src.repositories.agent_prediction_repo import AgentPredictionRepository
from src.schemas.agent_episode import AgentEpisodeCreate, reject_episode_free_text
from src.schemas.agent_prediction import STATUS_PENDING, STATUS_RESOLVED, AgentPredictionInsert
from src.schemas.memory_write_guard import (
    FEEDBACK_NOTE_MAX_LENGTH,
    MemoryWriteRejectedError,
)
from src.services.agent_episode_service import AgentEpisodeService
from src.services.decision_signal_outcome_service import DecisionSignalOutcomeService
from src.storage import DatabaseManager, DecisionSignalRecord


def _fixed_now() -> datetime:
    return datetime(2026, 8, 12, 12, 0, 0)


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "soul-oversize-reject.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    Config.reset_instance()
    DatabaseManager.reset_instance()
    db = DatabaseManager.get_instance()
    try:
        yield db
    finally:
        DatabaseManager.reset_instance()
        Config.reset_instance()


def _add_signal(db: DatabaseManager) -> int:
    with db.session_scope() as session:
        row = DecisionSignalRecord(
            stock_code="600519",
            stock_name="贵州茅台",
            market="cn",
            source_type="analysis",
            source_report_id=1124,
            trace_id="trace-soul-oversize-reject",
            market_phase="postmarket",
            trigger_source="api",
            action="buy",
            action_label="buy",
            horizon="3d",
            reason="soul reject test",
            data_quality_summary_json=json.dumps({"level": "good"}),
            metadata_json=json.dumps({"holding_state": "holding"}),
            plan_quality="complete",
            status="active",
        )
        session.add(row)
        session.flush()
        return int(row.id)


def _insert_prediction(repo: AgentPredictionRepository, *, prediction_id: str = "pred-soul") -> None:
    created, record = repo.insert_pending(
        AgentPredictionInsert(
            prediction_id=prediction_id,
            run_id="run-soul",
            symbol="600519",
            market="cn",
            as_of=_fixed_now().date(),
            horizon="5d",
            resolve_after=_fixed_now() - timedelta(hours=1),
            claims=[
                {
                    "claim_id": "direction-0",
                    "type": "direction",
                    "confidence": 0.7,
                    "payload": {"direction": "up"},
                }
            ],
            model_meta={"mode": "analysis"},
            created_at=_fixed_now() - timedelta(days=1),
        )
    )
    assert created is True
    assert record is not None
    assert record.status == STATUS_PENDING


def test_repo_upsert_feedback_rejects_oversize_and_markers_without_persist(
    isolated_db,
) -> None:
    signal_id = _add_signal(isolated_db)
    service = DecisionSignalOutcomeService(db_manager=isolated_db)
    legal_fields = {
        "signal_id": signal_id,
        "feedback_value": "useful",
        "reason_code": "matched_plan",
        "note": "agrees with the call",
        "source": "web",
    }

    with pytest.raises(MemoryWriteRejectedError, match="at most 1000"):
        service.repo.upsert_feedback(
            {**legal_fields, "note": "x" * (FEEDBACK_NOTE_MAX_LENGTH + 1)}
        )
    assert service.repo.get_feedback(signal_id=signal_id) is None

    with pytest.raises(MemoryWriteRejectedError, match="Soul boundary"):
        service.repo.upsert_feedback(
            {**legal_fields, "note": f"looks fine {AGENT_SOUL_MARKER}"}
        )
    assert service.repo.get_feedback(signal_id=signal_id) is None

    stored = service.repo.upsert_feedback(legal_fields)
    assert stored.note == "agrees with the call"
    assert stored.feedback_value == "useful"

    with pytest.raises(MemoryWriteRejectedError, match="Soul boundary"):
        service.repo.upsert_feedback(
            {**legal_fields, "note": AGENT_SOUL_END_MARKER, "feedback_value": "not_useful"}
        )
    again = service.repo.get_feedback(signal_id=signal_id)
    assert again is not None
    assert again.note == "agrees with the call"
    assert again.feedback_value == "useful"


def test_service_put_feedback_rejects_marker_before_sanitize(isolated_db) -> None:
    signal_id = _add_signal(isolated_db)
    service = DecisionSignalOutcomeService(db_manager=isolated_db)
    with pytest.raises(MemoryWriteRejectedError, match="Soul boundary"):
        service.put_feedback(
            signal_id,
            feedback_value="useful",
            reason_code="matched_plan",
            note="<!-- StockPulse-Agent-Soul -->",
            source="web",
        )
    assert service.get_feedback(signal_id)["feedback_value"] is None

    stored = service.put_feedback(
        signal_id,
        feedback_value="useful",
        reason_code="matched_plan",
        note="a" * FEEDBACK_NOTE_MAX_LENGTH,
        source="web",
    )
    assert stored["feedback_value"] == "useful"
    assert stored["note"] == "a" * FEEDBACK_NOTE_MAX_LENGTH
    assert stored["source"] == "web"


def test_episode_soul_marker_does_not_write_or_change_prediction_actuals(
    isolated_db,
) -> None:
    pred_repo = AgentPredictionRepository(isolated_db, clock=_fixed_now)
    _insert_prediction(pred_repo, prediction_id="pred-soul-ep")
    actuals = {"label": "hit", "score": 1.0}
    applied, resolved = pred_repo.resolve(
        prediction_id="pred-soul-ep",
        outcome=actuals,
        as_of=_fixed_now(),
    )
    assert applied is True
    assert resolved is not None
    assert resolved.status == STATUS_RESOLVED

    config = type("Cfg", (), {"agent_episode_log_enabled": True})()
    episode_repo = AgentEpisodeRepository(isolated_db)
    service = AgentEpisodeService(repository=episode_repo, config=config)
    legal_payload = {
        "episode_id": "ep-soul-1",
        "run_id": "run-soul",
        "mode": "single",
        "symbol": "600519",
        "market": "cn",
        "started_at": datetime(2026, 8, 12, 10, 0, 0, tzinfo=timezone.utc),
        "completed_at": datetime(2026, 8, 12, 10, 1, 0, tzinfo=timezone.utc),
        "outcome_labels": {
            "user_feedback": "disagree_score",
            "prediction_outcome": "hit",
            "prediction_id": "pred-soul-ep",
            "extra": {"comment": "review later"},
        },
        "lessons": [{"kind": "evidence_gap", "severity": "low", "remedy": "add source"}],
    }

    with pytest.raises(ValidationError, match="Soul boundary"):
        AgentEpisodeCreate.model_validate(
            {
                **legal_payload,
                "outcome_labels": {
                    "user_feedback": AGENT_SOUL_MARKER,
                    "prediction_id": "pred-soul-ep",
                    "extra": {"comment": "review later"},
                },
            }
        )
    with pytest.raises(ValidationError, match="Soul boundary"):
        AgentEpisodeCreate.model_validate(
            {
                **legal_payload,
                "episode_id": "ep-soul-extra",
                "outcome_labels": {
                    "user_feedback": "disagree_score",
                    "extra": {"comment": AGENT_SOUL_MARKER},
                },
            }
        )

    skipped = service.record_episode(
        {
            **legal_payload,
            "episode_id": "ep-soul-service",
            "outcome_labels": {
                "user_feedback": AGENT_SOUL_END_MARKER,
                "prediction_id": "pred-soul-ep",
            },
        },
        config=config,
    )
    assert skipped is None
    assert episode_repo.get_by_episode_id("ep-soul-service") is None

    stored = service.record_episode(
        AgentEpisodeCreate.model_validate(legal_payload),
        config=config,
    )
    assert stored is not None
    assert stored.outcome_labels is not None
    assert stored.outcome_labels.user_feedback == "disagree_score"

    mutated = AgentEpisodeCreate.model_validate(
        {**legal_payload, "episode_id": "ep-soul-mutated"}
    )
    assert mutated.outcome_labels is not None
    mutated.outcome_labels.user_feedback = f"looks fine {AGENT_SOUL_MARKER}"
    with pytest.raises(MemoryWriteRejectedError, match="Soul boundary"):
        reject_episode_free_text(mutated)
    with pytest.raises(MemoryWriteRejectedError, match="Soul boundary"):
        episode_repo.append(mutated)
    assert episode_repo.get_by_episode_id("ep-soul-mutated") is None

    persisted = pred_repo.get("pred-soul-ep")
    assert persisted is not None
    assert persisted.status == STATUS_RESOLVED
    assert persisted.outcome == actuals
