# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Real-SQLite tests: server stamps provenance; client spoofs are rejected (#1124 DAG-3)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from src.agent.soul import AGENT_SOUL_MARKER
from src.config import Config
from src.repositories.agent_episode_repo import AgentEpisodeRepository
from src.repositories.agent_prediction_repo import AgentPredictionRepository
from src.schemas.agent_episode import AgentEpisodeCreate
from src.schemas.agent_prediction import STATUS_PENDING, STATUS_RESOLVED, AgentPredictionInsert
from src.schemas.memory_fact_opinion import FactOpinionMixError
from src.schemas.memory_provenance import (
    FEEDBACK_ACTOR_ID,
    MemoryProvenanceError,
    PROVENANCE_SOURCE_OPERATOR,
    PROVENANCE_SOURCE_SYSTEM_RESOLVE,
    PROVENANCE_SOURCE_USER_FEEDBACK,
)
from src.schemas.memory_write_guard import FEEDBACK_NOTE_MAX_LENGTH, MemoryWriteRejectedError
from src.services.agent_episode_service import AgentEpisodeService
from src.services.decision_signal_outcome_service import DecisionSignalOutcomeService
from src.storage import (
    DatabaseManager,
    DecisionSignalFeedbackRecord,
    DecisionSignalOutcomeRecord,
    DecisionSignalRecord,
)


def _fixed_now() -> datetime:
    return datetime(2026, 8, 12, 12, 0, 0)


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "memory-provenance-stamp.db"
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
            trace_id="trace-memory-provenance",
            market_phase="postmarket",
            trigger_source="api",
            action="buy",
            action_label="buy",
            horizon="3d",
            reason="provenance stamp test",
            data_quality_summary_json=json.dumps({"level": "good"}),
            metadata_json=json.dumps({"holding_state": "holding"}),
            plan_quality="complete",
            status="active",
        )
        session.add(row)
        session.flush()
        return int(row.id)


def _insert_prediction(repo: AgentPredictionRepository, *, prediction_id: str = "pred-prov") -> None:
    created, record = repo.insert_pending(
        AgentPredictionInsert(
            prediction_id=prediction_id,
            run_id="run-prov",
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
    assert record.provenance_source is None
    assert record.actor_id is None


def _legal_feedback(signal_id: int) -> dict:
    return {
        "signal_id": signal_id,
        "feedback_value": "useful",
        "reason_code": "matched_plan",
        "note": "agrees with the call",
        "source": "web",
    }


def test_repo_upsert_feedback_stamps_user_feedback_and_rejects_client_keys(
    isolated_db,
) -> None:
    signal_id = _add_signal(isolated_db)
    service = DecisionSignalOutcomeService(db_manager=isolated_db)

    with pytest.raises(MemoryProvenanceError, match="client-supplied"):
        service.repo.upsert_feedback(
            {
                **_legal_feedback(signal_id),
                "provenance_source": PROVENANCE_SOURCE_SYSTEM_RESOLVE,
            }
        )
    assert service.repo.get_feedback(signal_id=signal_id) is None

    with pytest.raises(MemoryProvenanceError, match="client-supplied"):
        service.repo.upsert_feedback(
            {**_legal_feedback(signal_id), "actor_id": "root"}
        )
    assert service.repo.get_feedback(signal_id=signal_id) is None

    with pytest.raises(MemoryProvenanceError, match="client-supplied"):
        service.repo.upsert_feedback(
            {
                **_legal_feedback(signal_id),
                "provenance_source": PROVENANCE_SOURCE_OPERATOR,
            }
        )
    assert service.repo.get_feedback(signal_id=signal_id) is None

    stored = service.repo.upsert_feedback(_legal_feedback(signal_id))
    assert stored.source == "web"
    assert stored.provenance_source == PROVENANCE_SOURCE_USER_FEEDBACK
    assert stored.actor_id == FEEDBACK_ACTOR_ID
    assert stored.note == "agrees with the call"


def test_service_put_feedback_stamps_without_trusting_transport_source(
    isolated_db,
) -> None:
    signal_id = _add_signal(isolated_db)
    service = DecisionSignalOutcomeService(db_manager=isolated_db)
    empty = service.get_feedback(signal_id)
    assert empty["feedback_value"] is None
    assert empty["provenance_source"] is None
    assert empty["actor_id"] is None

    stored = service.put_feedback(
        signal_id,
        feedback_value="useful",
        reason_code="matched_plan",
        note="agrees with the call",
        source="web",
    )
    assert stored["source"] == "web"
    assert stored["provenance_source"] == PROVENANCE_SOURCE_USER_FEEDBACK
    assert stored["actor_id"] == FEEDBACK_ACTOR_ID


def test_historical_feedback_row_stays_unstamped_until_governed_write(
    isolated_db,
) -> None:
    signal_id = _add_signal(isolated_db)
    with isolated_db.session_scope() as session:
        session.add(
            DecisionSignalFeedbackRecord(
                signal_id=signal_id,
                feedback_value="useful",
                source="api",
            )
        )
    service = DecisionSignalOutcomeService(db_manager=isolated_db)
    legacy = service.get_feedback(signal_id)
    assert legacy["feedback_value"] == "useful"
    assert legacy["source"] == "api"
    assert legacy["provenance_source"] is None
    assert legacy["actor_id"] is None

    stamped = service.put_feedback(
        signal_id,
        feedback_value="not_useful",
        source="web",
    )
    assert stamped["source"] == "web"
    assert stamped["provenance_source"] == PROVENANCE_SOURCE_USER_FEEDBACK
    assert stamped["actor_id"] == FEEDBACK_ACTOR_ID


def test_prediction_resolve_stamps_system_resolve_and_feedback_cannot_rewrite(
    isolated_db,
) -> None:
    repo = AgentPredictionRepository(isolated_db, clock=_fixed_now)
    _insert_prediction(repo)
    actuals = {"label": "hit", "score": 1.0, "engine_version": "claim-scorer-v1"}

    with pytest.raises(MemoryProvenanceError, match="client-supplied"):
        repo.resolve(
            prediction_id="pred-prov",
            outcome={**actuals, "provenance_source": PROVENANCE_SOURCE_USER_FEEDBACK},
            as_of=_fixed_now(),
        )
    pending = repo.get("pred-prov")
    assert pending is not None
    assert pending.status == STATUS_PENDING
    assert pending.outcome is None
    assert pending.provenance_source is None

    applied, resolved = repo.resolve(
        prediction_id="pred-prov",
        outcome=actuals,
        as_of=_fixed_now(),
    )
    assert applied is True
    assert resolved is not None
    assert resolved.status == STATUS_RESOLVED
    assert resolved.outcome == actuals
    assert resolved.provenance_source == PROVENANCE_SOURCE_SYSTEM_RESOLVE
    assert resolved.actor_id is None
    assert "provenance_source" not in resolved.outcome

    signal_id = _add_signal(isolated_db)
    service = DecisionSignalOutcomeService(db_manager=isolated_db)
    service.put_feedback(
        signal_id,
        feedback_value="not_useful",
        note="user disagrees",
        source="web",
    )
    again = repo.get("pred-prov")
    assert again is not None
    assert again.outcome == actuals
    assert again.provenance_source == PROVENANCE_SOURCE_SYSTEM_RESOLVE


def test_upsert_outcome_cannot_select_user_feedback_provenance(isolated_db) -> None:
    signal_id = _add_signal(isolated_db)
    service = DecisionSignalOutcomeService(db_manager=isolated_db)
    with pytest.raises(MemoryProvenanceError, match="client-supplied"):
        service.repo.upsert_outcome(
            {
                "signal_id": signal_id,
                "horizon": "3d",
                "engine_version": "decision-signal-v1",
                "eval_status": "completed",
                "outcome": "hit",
                "holding_state": "holding",
                "provenance_source": PROVENANCE_SOURCE_USER_FEEDBACK,
            }
        )
    listed, total = service.repo.list_outcomes(signal_id=signal_id, page=1, page_size=20)
    assert total == 0
    assert listed == []

    row, created = service.repo.upsert_outcome(
        {
            "signal_id": signal_id,
            "horizon": "3d",
            "engine_version": "decision-signal-v1",
            "eval_status": "completed",
            "outcome": "hit",
            "holding_state": "holding",
        }
    )
    assert created is True
    assert isinstance(row, DecisionSignalOutcomeRecord)
    assert row.outcome == "hit"
    assert row.provenance_source == PROVENANCE_SOURCE_SYSTEM_RESOLVE
    assert row.actor_id is None


def test_episode_append_stamps_system_resolve(isolated_db) -> None:
    config = type("Cfg", (), {"agent_episode_log_enabled": True})()
    service = AgentEpisodeService(
        repository=AgentEpisodeRepository(isolated_db),
        config=config,
    )
    with pytest.raises(ValidationError):
        AgentEpisodeCreate.model_validate(
            {
                "episode_id": "ep-prov-spoof",
                "run_id": "run-prov",
                "mode": "single",
                "started_at": datetime(2026, 8, 12, 10, 0, 0, tzinfo=timezone.utc),
                "completed_at": datetime(2026, 8, 12, 10, 1, 0, tzinfo=timezone.utc),
                "provenance_source": PROVENANCE_SOURCE_OPERATOR,
            }
        )
    stored = service.record_episode(
        AgentEpisodeCreate.model_validate(
            {
                "episode_id": "ep-prov-1",
                "run_id": "run-prov",
                "mode": "single",
                "symbol": "600519",
                "market": "cn",
                "started_at": datetime(2026, 8, 12, 10, 0, 0, tzinfo=timezone.utc),
                "completed_at": datetime(2026, 8, 12, 10, 1, 0, tzinfo=timezone.utc),
            }
        ),
        config=config,
    )
    assert stored is not None
    assert stored.provenance_source == PROVENANCE_SOURCE_SYSTEM_RESOLVE
    assert stored.actor_id is None


def test_dag1_and_dag2_rejects_still_leave_rows_unstored(isolated_db) -> None:
    signal_id = _add_signal(isolated_db)
    service = DecisionSignalOutcomeService(db_manager=isolated_db)
    with pytest.raises(FactOpinionMixError, match="outcome"):
        service.repo.upsert_feedback(
            {
                **_legal_feedback(signal_id),
                "outcome": "miss",
            }
        )
    with pytest.raises(MemoryWriteRejectedError, match="Soul boundary"):
        service.repo.upsert_feedback(
            {**_legal_feedback(signal_id), "note": AGENT_SOUL_MARKER}
        )
    with pytest.raises(MemoryWriteRejectedError, match="at most 1000"):
        service.repo.upsert_feedback(
            {
                **_legal_feedback(signal_id),
                "note": "x" * (FEEDBACK_NOTE_MAX_LENGTH + 1),
            }
        )
    assert service.repo.get_feedback(signal_id=signal_id) is None
