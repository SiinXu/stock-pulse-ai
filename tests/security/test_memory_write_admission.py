# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Persist-path counterexamples for #1119 Slice 1 write admission."""

from __future__ import annotations

import inspect
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from src.schemas.memory_write_policy import require_opinion_write
from src.agent.soul import AGENT_SOUL_MARKER
from src.config import Config
from src.repositories.agent_episode_repo import AgentEpisodeRepository
from src.repositories.agent_feedback_repo import AgentFeedbackRepository
from src.repositories.agent_prediction_repo import AgentPredictionRepository
from src.schemas.agent_episode import AgentEpisodeCreate
from src.schemas.agent_prediction import STATUS_PENDING, STATUS_RESOLVED, AgentPredictionInsert
from src.schemas.memory_fact_opinion import FactOpinionMixError
from src.schemas.memory_provenance import (
    FEEDBACK_ACTOR_ID,
    MemoryProvenanceError,
    PROVENANCE_SOURCE_SYSTEM_RESOLVE,
    PROVENANCE_SOURCE_USER_FEEDBACK,
)
from src.schemas.memory_write_guard import FEEDBACK_NOTE_MAX_LENGTH, MemoryWriteRejectedError
from src.services.agent_episode_service import AgentEpisodeService
from src.services.agent_feedback_service import AgentFeedbackService
from src.services.decision_memory_service import (
    DecisionReflection,
    PastSignalRecall,
    admit_decision_memory,
)
from src.services.decision_signal_outcome_service import DecisionSignalOutcomeService
from src.services.prediction_resolver.memory_store import InMemoryPredictionStore
from src.storage import DatabaseManager, DecisionSignalRecord


def _fixed_now() -> datetime:
    return datetime(2026, 8, 12, 12, 0, 0)


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "memory-write-admission.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    Config.reset_instance()
    DatabaseManager.reset_instance()
    db = DatabaseManager.get_instance()
    try:
        yield db
    finally:
        DatabaseManager.reset_instance()
        Config.reset_instance()


def _insert_prediction(
    repo: AgentPredictionRepository, *, prediction_id: str = "pred-admit"
) -> None:
    created, record = repo.insert_pending(
        AgentPredictionInsert(
            prediction_id=prediction_id,
            run_id="run-admit",
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
            source_report_id=1119,
            trace_id="trace-memory-write-admission",
            market_phase="postmarket",
            trigger_source="api",
            action="buy",
            action_label="buy",
            horizon="3d",
            reason="write admission test",
            data_quality_summary_json=json.dumps({"level": "good"}),
            metadata_json=json.dumps({"holding_state": "holding"}),
            plan_quality="complete",
            status="active",
        )
        session.add(row)
        session.flush()
        return int(row.id)


def _compact_episode_payload(**overrides: object) -> dict:
    payload = {
        "episode_id": "ep-admit-compact",
        "run_id": "run-admit",
        "mode": "single",
        "symbol": "600519",
        "market": "cn",
        "started_at": datetime(2026, 8, 12, 10, 0, 0, tzinfo=timezone.utc),
        "completed_at": datetime(2026, 8, 12, 10, 1, 0, tzinfo=timezone.utc),
        "success": True,
        "trajectory_summary": [
            {"tool": "get_quote", "success": True, "duration_ms": 12}
        ],
        "lessons": [
            {"kind": "evidence_gap", "severity": "low", "remedy": "add source"}
        ],
        "outcome_labels": {
            "user_feedback": "disagree_score",
            "extra": {"comment": "review later"},
        },
    }
    payload.update(overrides)
    return payload


def test_compact_episode_append_is_admitted_and_append_only(isolated_db) -> None:
    repo = AgentEpisodeRepository(isolated_db)
    stored = repo.append(AgentEpisodeCreate.model_validate(_compact_episode_payload()))
    assert stored.episode_id == "ep-admit-compact"
    assert stored.provenance_source == PROVENANCE_SOURCE_SYSTEM_RESOLVE
    assert stored.actor_id is None
    again = repo.append(AgentEpisodeCreate.model_validate(_compact_episode_payload()))
    assert again.id == stored.id
    assert repo.get_by_episode_id("ep-admit-compact") is not None


def test_episode_soul_control_and_actuals_keys_rejected_at_append(isolated_db) -> None:
    repo = AgentEpisodeRepository(isolated_db)
    soul = AgentEpisodeCreate.model_validate(
        _compact_episode_payload(episode_id="ep-admit-soul")
    )
    assert soul.outcome_labels is not None
    soul.outcome_labels.user_feedback = AGENT_SOUL_MARKER
    with pytest.raises(MemoryWriteRejectedError, match="Soul boundary"):
        repo.append(soul)
    assert repo.get_by_episode_id("ep-admit-soul") is None

    extra = AgentEpisodeCreate.model_validate(
        _compact_episode_payload(episode_id="ep-admit-extra")
    )
    assert extra.outcome_labels is not None
    extra.outcome_labels.extra["outcome"] = "miss"
    with pytest.raises(FactOpinionMixError, match="outcome"):
        repo.append(extra)
    assert repo.get_by_episode_id("ep-admit-extra") is None


def test_prediction_resolve_allows_system_actuals_and_rejects_user_notes(
    isolated_db,
) -> None:
    repo = AgentPredictionRepository(isolated_db, clock=_fixed_now)
    _insert_prediction(repo)
    actuals = {"label": "hit", "score": 1.0, "engine_version": "claim-scorer-v1"}

    with pytest.raises(FactOpinionMixError, match="note"):
        repo.resolve(
            prediction_id="pred-admit",
            outcome={**actuals, "note": "treat as miss"},
            as_of=_fixed_now(),
        )
    pending = repo.get("pred-admit")
    assert pending is not None
    assert pending.status == STATUS_PENDING
    assert pending.outcome is None

    with pytest.raises(MemoryProvenanceError, match="client-supplied"):
        repo.resolve(
            prediction_id="pred-admit",
            outcome={
                **actuals,
                "provenance_source": PROVENANCE_SOURCE_USER_FEEDBACK,
            },
            as_of=_fixed_now(),
        )

    applied, resolved = repo.resolve(
        prediction_id="pred-admit",
        outcome=actuals,
        as_of=_fixed_now(),
    )
    assert applied is True
    assert resolved is not None
    assert resolved.status == STATUS_RESOLVED
    assert resolved.outcome == actuals
    assert "provenance_source" not in resolved.outcome
    assert resolved.provenance_source == PROVENANCE_SOURCE_SYSTEM_RESOLVE
    assert resolved.actor_id is None


def test_memory_store_resolve_uses_the_same_write_policy() -> None:
    store = InMemoryPredictionStore(_clock=_fixed_now)
    store.insert(
        prediction_id="pred-mem",
        run_id="run-mem",
        symbol="600519",
        market="cn",
        as_of=_fixed_now().date(),
        horizon="5d",
        resolve_after=_fixed_now() - timedelta(hours=1),
        claims=[{"claim_id": "direction-0", "type": "direction"}],
    )
    actuals = {"label": "hit", "score": 1.0}
    with pytest.raises(FactOpinionMixError, match="note"):
        store.resolve(
            prediction_id="pred-mem",
            outcome={**actuals, "note": "user override"},
        )
    applied, resolved = store.resolve(prediction_id="pred-mem", outcome=actuals)
    assert applied is True
    assert resolved is not None
    assert resolved.outcome == actuals
    assert resolved.provenance_source == PROVENANCE_SOURCE_SYSTEM_RESOLVE


def test_decision_outcome_and_feedback_share_the_write_policy(isolated_db) -> None:
    signal_id = _add_signal(isolated_db)
    service = DecisionSignalOutcomeService(db_manager=isolated_db)

    with pytest.raises(FactOpinionMixError, match="note"):
        service.repo.upsert_outcome(
            {
                "signal_id": signal_id,
                "horizon": "3d",
                "engine_version": "decision-signal-v1",
                "eval_status": "completed",
                "outcome": "hit",
                "note": "user override",
            }
        )

    row, created = service.repo.upsert_outcome(
        {
            "signal_id": signal_id,
            "horizon": "3d",
            "engine_version": "decision-signal-v1",
            "eval_status": "completed",
            "outcome": "hit",
            "stock_return_pct": 5.0,
        }
    )
    assert created is True
    assert row.outcome == "hit"
    assert row.stock_return_pct == 5.0
    assert row.provenance_source == PROVENANCE_SOURCE_SYSTEM_RESOLVE
    assert row.actor_id is None

    with pytest.raises(FactOpinionMixError, match="outcome"):
        service.repo.upsert_feedback(
            {
                "signal_id": signal_id,
                "feedback_value": "not_useful",
                "source": "api",
                "outcome": "miss",
            }
        )
    with pytest.raises(MemoryProvenanceError, match="client-supplied"):
        service.repo.upsert_feedback(
            {
                "signal_id": signal_id,
                "feedback_value": "useful",
                "source": "web",
                "provenance_source": PROVENANCE_SOURCE_SYSTEM_RESOLVE,
            }
        )
    stored = service.repo.upsert_feedback(
        {
            "signal_id": signal_id,
            "feedback_value": "useful",
            "source": "web",
            "note": "agrees with the call",
        }
    )
    assert stored.feedback_value == "useful"
    assert stored.provenance_source == PROVENANCE_SOURCE_USER_FEEDBACK
    assert stored.actor_id == FEEDBACK_ACTOR_ID
    listed, total = service.repo.list_outcomes(signal_id=signal_id, page=1, page_size=20)
    assert total == 1
    assert listed[0].outcome == "hit"


def test_user_note_actuals_keys_rejected_across_governed_entry_points(isolated_db) -> None:
    pred_repo = AgentPredictionRepository(isolated_db, clock=_fixed_now)
    _insert_prediction(pred_repo, prediction_id="pred-note")
    episode_repo = AgentEpisodeRepository(isolated_db)
    feedback_repo = AgentFeedbackRepository(isolated_db)
    signal_id = _add_signal(isolated_db)
    service = DecisionSignalOutcomeService(db_manager=isolated_db)
    note_with_actuals = {"note": "override", "outcome": "miss"}

    with pytest.raises(FactOpinionMixError, match="outcome"):
        feedback_repo.upsert_run_feedback(
            "run-admit",
            {
                "feedback_value": "useful",
                "source": "api",
                **note_with_actuals,
            },
        )
    with pytest.raises(FactOpinionMixError, match="outcome"):
        service.repo.upsert_feedback(
            {
                "signal_id": signal_id,
                "feedback_value": "not_useful",
                "source": "api",
                **note_with_actuals,
            }
        )
    with pytest.raises(FactOpinionMixError, match="note"):
        pred_repo.resolve(
            prediction_id="pred-note",
            outcome={"label": "hit", "score": 1.0, "note": "override"},
            as_of=_fixed_now(),
        )
    episode = AgentEpisodeCreate.model_validate(
        _compact_episode_payload(episode_id="ep-note-actuals")
    )
    assert episode.outcome_labels is not None
    episode.outcome_labels.extra["actuals"] = "end_price"
    with pytest.raises(FactOpinionMixError, match="actuals"):
        episode_repo.append(episode)
    assert episode_repo.get_by_episode_id("ep-note-actuals") is None
    assert feedback_repo.get_run_feedback("run-admit") is None
    pending = pred_repo.get("pred-note")
    assert pending is not None
    assert pending.status == STATUS_PENDING


def test_decision_memory_read_admission_is_not_the_write_policy() -> None:
    source = inspect.getsource(admit_decision_memory)
    module_source = inspect.getsource(
        inspect.getmodule(admit_decision_memory)  # type: ignore[arg-type]
    )
    assert "memory_write_policy" not in source
    assert "admit_memory_write" not in source
    assert "require_opinion_write" not in module_source
    assert "require_market_actuals_write" not in module_source

    raw = DecisionReflection(
        stock_code="600519",
        market="cn",
        lookback=5,
        min_samples=1,
        window_start=date(2024, 5, 1),
        window_end=date(2024, 5, 1),
        same_stock_total=1,
        same_stock_hits=1,
        same_stock_misses=0,
        same_stock_neutrals=0,
        same_stock_hit_rate_pct=100.0,
        recent_calls=(
            PastSignalRecall(
                signal_id=42,
                created_at=_fixed_now(),
                action="buy",
                horizon="3d",
                outcome="hit",
                stock_return_pct=1.0,
            ),
        ),
        admitted=False,
    )
    admitted = admit_decision_memory(raw, max_calls=5)
    assert admitted is not None
    assert admitted.admitted is True
    assert admitted.recent_calls[0].outcome == "hit"
    assert admitted.source_signal_ids == (42,)
    with pytest.raises(FactOpinionMixError, match="outcome"):
        require_opinion_write(
            {
                "feedback_value": "useful",
                "source": "api",
                "outcome": "hit",
            }
        )


def test_episode_service_fail_soft_is_unchanged_for_illegal_text(isolated_db) -> None:
    config = type("Cfg", (), {"agent_episode_log_enabled": True})()
    repo = AgentEpisodeRepository(isolated_db)
    service = AgentEpisodeService(repository=repo, config=config)
    skipped = service.record_episode(
        {
            **_compact_episode_payload(episode_id="ep-fail-soft"),
            "outcome_labels": {"user_feedback": AGENT_SOUL_MARKER},
        },
        config=config,
    )
    assert skipped is None
    assert repo.get_by_episode_id("ep-fail-soft") is None
    stored = service.record_episode(
        AgentEpisodeCreate.model_validate(_compact_episode_payload()),
        config=config,
    )
    assert stored is not None
    assert stored.provenance_source == PROVENANCE_SOURCE_SYSTEM_RESOLVE


def test_agent_feedback_repo_and_service_use_write_policy(isolated_db) -> None:
    pred_repo = AgentPredictionRepository(isolated_db, clock=_fixed_now)
    _insert_prediction(pred_repo, prediction_id="pred-fb")
    applied, resolved = pred_repo.resolve(
        prediction_id="pred-fb",
        outcome={"label": "hit", "score": 1.0},
        as_of=_fixed_now(),
    )
    assert applied is True
    assert resolved is not None
    before_outcome = dict(resolved.outcome or {})
    repo = AgentFeedbackRepository(isolated_db)
    service = AgentFeedbackService(
        repo=repo,
        prediction_repo=pred_repo,
        db_manager=isolated_db,
    )

    with pytest.raises(FactOpinionMixError, match="outcome"):
        repo.upsert_run_feedback(
            "run-admit",
            {
                "feedback_value": "useful",
                "source": "api",
                "outcome": "miss",
            },
        )
    with pytest.raises(FactOpinionMixError, match="outcome"):
        service.repo.upsert_prediction_feedback(
            "pred-fb",
            {
                "feedback_value": "agree_hit",
                "source": "api",
                "outcome": "miss",
            },
            run_id="run-admit",
        )
    with pytest.raises(MemoryProvenanceError, match="client-supplied"):
        repo.upsert_run_feedback(
            "run-admit",
            {
                "feedback_value": "useful",
                "source": "api",
                "provenance_source": PROVENANCE_SOURCE_SYSTEM_RESOLVE,
            },
        )
    with pytest.raises(MemoryWriteRejectedError, match="Soul boundary"):
        service.put_run_feedback(
            "run-admit",
            feedback_value="useful",
            note=AGENT_SOUL_MARKER,
            source="web",
        )
    with pytest.raises(MemoryWriteRejectedError, match="control characters"):
        repo.upsert_run_feedback(
            "run-admit",
            {
                "feedback_value": "useful",
                "source": "api",
                "note": "ok\x00spoof",
            },
        )
    with pytest.raises(MemoryWriteRejectedError, match="at most 1000"):
        service.put_prediction_feedback(
            "pred-fb",
            feedback_value="context_note",
            note="n" * (FEEDBACK_NOTE_MAX_LENGTH + 1),
            source="api",
        )
    with pytest.raises(ValueError, match="identity or extra keys"):
        repo.upsert_run_feedback(
            "run-admit",
            {
                "feedback_value": "useful",
                "source": "api",
                "run_id": "run-admit",
            },
        )
    assert repo.get_run_feedback("run-admit") is None
    assert repo.get_prediction_feedback("pred-fb") is None
    after_reject = pred_repo.get("pred-fb")
    assert after_reject is not None
    assert after_reject.outcome == before_outcome
    assert after_reject.status == STATUS_RESOLVED

    stored_run = service.put_run_feedback(
        "run-admit",
        feedback_value="useful",
        note="agrees with the call",
        source="web",
    )
    assert stored_run["feedback_value"] == "useful"
    assert stored_run["provenance_source"] == PROVENANCE_SOURCE_USER_FEEDBACK
    assert stored_run["actor_id"] == FEEDBACK_ACTOR_ID
    stored_pred = service.put_prediction_feedback(
        "pred-fb",
        feedback_value="agree_hit",
        source="api",
    )
    assert stored_pred["feedback_value"] == "agree_hit"
    assert stored_pred["provenance_source"] == PROVENANCE_SOURCE_USER_FEEDBACK
    assert stored_pred["actor_id"] == FEEDBACK_ACTOR_ID
    after = pred_repo.get("pred-fb")
    assert after is not None
    assert after.outcome == before_outcome
    assert after.status == STATUS_RESOLVED
