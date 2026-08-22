# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Real-SQLite tests: feedback cannot mutate PredictionOutcome actuals (#1124 DAG-1)."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import pytest

from src.config import Config
from src.repositories.agent_episode_repo import AgentEpisodeRepository
from src.repositories.agent_prediction_repo import AgentPredictionRepository
from src.schemas.agent_episode import AgentEpisodeCreate
from src.schemas.agent_prediction import STATUS_PENDING, STATUS_RESOLVED, AgentPredictionInsert
from src.schemas.memory_fact_opinion import FactOpinionMixError
from src.services.agent_episode_service import AgentEpisodeService
from src.services.decision_signal_outcome_service import DecisionSignalOutcomeService
from src.storage import (
    DatabaseManager,
    DecisionSignalOutcomeRecord,
    DecisionSignalRecord,
    StockDaily,
)


def _fixed_now() -> datetime:
    return datetime(2026, 8, 12, 12, 0, 0)


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "fact-opinion-lock.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    Config.reset_instance()
    DatabaseManager.reset_instance()
    db = DatabaseManager.get_instance()
    try:
        yield db
    finally:
        DatabaseManager.reset_instance()
        Config.reset_instance()


def _insert_prediction(repo: AgentPredictionRepository, *, prediction_id: str = "pred-lock") -> None:
    created, record = repo.insert_pending(
        AgentPredictionInsert(
            prediction_id=prediction_id,
            run_id="run-lock",
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


def _add_signal(db: DatabaseManager) -> int:
    with db.session_scope() as session:
        row = DecisionSignalRecord(
            stock_code="600519",
            stock_name="贵州茅台",
            market="cn",
            source_type="analysis",
            source_report_id=1124,
            trace_id="trace-fact-opinion-lock",
            market_phase="postmarket",
            trigger_source="api",
            action="buy",
            action_label="buy",
            horizon="3d",
            reason="lock test",
            data_quality_summary_json=json.dumps({"level": "good"}),
            metadata_json=json.dumps(
                {
                    "market_phase_summary": {"session_date": "2024-01-02"},
                    "holding_state": "holding",
                }
            ),
            plan_quality="complete",
            status="active",
        )
        session.add(row)
        session.flush()
        return int(row.id)


def _seed_bars(db: DatabaseManager) -> None:
    with db.session_scope() as session:
        session.add(StockDaily(code="600519", date=date(2024, 1, 2), open=100, high=101, low=99, close=100))
        session.add(StockDaily(code="600519", date=date(2024, 1, 3), open=103, high=104, low=102, close=103))
        session.add(StockDaily(code="600519", date=date(2024, 1, 4), open=104, high=105, low=103, close=104))
        session.add(StockDaily(code="600519", date=date(2024, 1, 5), open=105, high=106, low=104, close=105))


def test_feedback_cannot_resolve_or_rewrite_prediction_outcome_actuals(isolated_db) -> None:
    repo = AgentPredictionRepository(isolated_db, clock=_fixed_now)
    _insert_prediction(repo)
    actuals = {"label": "hit", "score": 1.0, "engine_version": "claim-scorer-v1"}

    with pytest.raises(FactOpinionMixError, match="feedback_value"):
        repo.resolve(
            prediction_id="pred-lock",
            outcome={
                **actuals,
                "feedback_value": "useful",
                "note": "treat this opinion as a miss",
            },
            as_of=_fixed_now(),
        )
    pending = repo.get("pred-lock")
    assert pending is not None
    assert pending.status == STATUS_PENDING
    assert pending.outcome is None

    applied, resolved = repo.resolve(
        prediction_id="pred-lock",
        outcome=actuals,
        as_of=_fixed_now(),
    )
    assert applied is True
    assert resolved is not None
    assert resolved.status == STATUS_RESOLVED
    assert resolved.outcome == actuals

    with pytest.raises(FactOpinionMixError, match="user_feedback"):
        repo.resolve(
            prediction_id="pred-lock",
            outcome={"label": "miss", "score": 0.0, "user_feedback": "disagree_score"},
            as_of=_fixed_now(),
        )
    again = repo.get("pred-lock")
    assert again is not None
    assert again.status == STATUS_RESOLVED
    assert again.outcome == actuals


def test_decision_signal_feedback_cannot_mutate_outcome_actuals(isolated_db) -> None:
    signal_id = _add_signal(isolated_db)
    _seed_bars(isolated_db)
    service = DecisionSignalOutcomeService(db_manager=isolated_db)
    run = service.run_outcomes(signal_id=signal_id, horizons=["3d"])
    assert run["created"] == 1
    before = run["items"][0]
    assert before["outcome"] == "hit"
    assert before["stock_return_pct"] == 5.0

    with pytest.raises(FactOpinionMixError, match="outcome"):
        service.repo.upsert_feedback(
            {
                "signal_id": signal_id,
                "feedback_value": "not_useful",
                "source": "api",
                "outcome": "miss",
                "start_price": 1.0,
                "stock_return_pct": -99.0,
            }
        )

    with pytest.raises(FactOpinionMixError, match="note"):
        service.repo.upsert_outcome(
            {
                "signal_id": signal_id,
                "horizon": "3d",
                "engine_version": "decision-signal-v1",
                "eval_status": "completed",
                "outcome": "miss",
                "note": "user override",
                "feedback_value": "not_useful",
            }
        )

    feedback = service.put_feedback(
        signal_id,
        feedback_value="not_useful",
        reason_code="disputed",
        note="user disagrees with the hit",
        source="web",
    )
    assert feedback["feedback_value"] == "not_useful"
    assert feedback["note"] == "user disagrees with the hit"

    listed, total = service.repo.list_outcomes(signal_id=signal_id, page=1, page_size=20)
    assert total == 1
    row = listed[0]
    assert isinstance(row, DecisionSignalOutcomeRecord)
    assert row.outcome == "hit"
    assert row.stock_return_pct == 5.0
    assert row.eval_status == "completed"
    assert row.anchor_date == date(2024, 1, 2)


def test_episode_opinion_labels_do_not_write_prediction_actuals(isolated_db) -> None:
    pred_repo = AgentPredictionRepository(isolated_db, clock=_fixed_now)
    _insert_prediction(pred_repo, prediction_id="pred-episode")
    applied, resolved = pred_repo.resolve(
        prediction_id="pred-episode",
        outcome={"label": "hit", "score": 1.0},
        as_of=_fixed_now(),
    )
    assert applied is True
    assert resolved is not None

    config = type("Cfg", (), {"agent_episode_log_enabled": True})()
    service = AgentEpisodeService(
        repository=AgentEpisodeRepository(isolated_db),
        config=config,
    )
    stored = service.record_episode(
        AgentEpisodeCreate.model_validate(
            {
                "episode_id": "ep-fact-opinion-1",
                "run_id": "run-lock",
                "mode": "single",
                "symbol": "600519",
                "market": "cn",
                "started_at": datetime(2026, 8, 12, 10, 0, 0, tzinfo=timezone.utc),
                "completed_at": datetime(2026, 8, 12, 10, 1, 0, tzinfo=timezone.utc),
                "outcome_labels": {
                    "user_feedback": "disagree_score",
                    "manual_grade": "wrong",
                    "prediction_outcome": "hit",
                    "prediction_id": "pred-episode",
                },
            }
        ),
        config=config,
    )
    assert stored is not None
    assert stored.outcome_labels is not None
    assert stored.outcome_labels.user_feedback == "disagree_score"
    assert stored.outcome_labels.prediction_outcome == "hit"

    persisted = pred_repo.get("pred-episode")
    assert persisted is not None
    assert persisted.status == STATUS_RESOLVED
    assert persisted.outcome == {"label": "hit", "score": 1.0}
