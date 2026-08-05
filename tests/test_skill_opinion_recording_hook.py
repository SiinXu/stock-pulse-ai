# -*- coding: utf-8 -*-
"""Config-gated skill-opinion recording hook parity tests."""

from __future__ import annotations

from datetime import datetime
from types import MethodType, SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.agent.orchestrator_parts.pipeline import _PipelineMethods
from src.agent.protocols import AgentContext, AgentOpinion
from src.agent.skills.engine import StrategyResult, StrategyResultStatus
from src.config import Config
from src.repositories.skill_opinion_sample_repo import SkillOpinionSampleRepository
from src.services.skill_opinion_sample_service import (
    SkillOpinionSampleService,
    is_skill_opinion_recording_enabled,
)
from src.storage import AnalysisHistory, DatabaseManager


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "skill-recording.db"))
    Config.reset_instance()
    DatabaseManager.reset_instance()
    db = DatabaseManager.get_instance()
    try:
        yield db
    finally:
        DatabaseManager.reset_instance()
        Config.reset_instance()


def _add_history(db: DatabaseManager, *, code: str = "600519") -> int:
    with db.session_scope() as session:
        row = AnalysisHistory(
            query_id="recording-hook",
            code=code,
            report_type="simple",
            raw_result="{}",
            context_snapshot="{}",
            created_at=datetime(2026, 8, 4, 12, 0, 0),
        )
        session.add(row)
        session.flush()
        return int(row.id)


def _valid_opinions() -> list[AgentOpinion]:
    return [
        AgentOpinion(
            agent_name="skill_bull_trend",
            signal="buy",
            confidence=0.81,
            raw_data={"skill_id": "bull_trend"},
        ),
        AgentOpinion(
            agent_name="skill_hot_theme",
            signal="hold",
            confidence=0.55,
            raw_data={"skill_id": "hot_theme"},
        ),
    ]


def test_recording_flag_default_off(isolated_db) -> None:
    config = Config.get_instance()
    assert config.skill_opinion_recording_enabled is False
    assert is_skill_opinion_recording_enabled(config) is False


def test_pipeline_hook_off_writes_zero_rows(isolated_db) -> None:
    history_id = _add_history(isolated_db)
    ctx = AgentContext(stock_code="600519")
    ctx.meta["analysis_history_id"] = history_id
    opinions = _valid_opinions()

    host = SimpleNamespace(
        config=SimpleNamespace(skill_opinion_recording_enabled=False),
    )
    _PipelineMethods._maybe_record_skill_opinion_samples(
        host,  # type: ignore[arg-type]
        ctx,
        opinions,
    )

    repo = SkillOpinionSampleRepository(isolated_db)
    assert repo.list_for_history(history_id) == []
    assert "skill_opinion_recording" not in ctx.meta


def test_pipeline_hook_on_persists_samples(isolated_db) -> None:
    history_id = _add_history(isolated_db)
    ctx = AgentContext(stock_code="600519")
    ctx.meta["analysis_history_id"] = history_id
    ctx.set_data(
        "analysis_context_pack_overview",
        {"data_quality": {"level": "usable"}},
    )
    opinions = _valid_opinions()

    host = SimpleNamespace(
        config=SimpleNamespace(skill_opinion_recording_enabled=True),
    )
    _PipelineMethods._maybe_record_skill_opinion_samples(
        host,  # type: ignore[arg-type]
        ctx,
        opinions,
    )

    rows = SkillOpinionSampleRepository(isolated_db).list_for_history(history_id)
    assert [(r.skill_id, r.signal, r.confidence) for r in rows] == [
        ("bull_trend", "buy", 0.81),
        ("hot_theme", "hold", 0.55),
    ]
    assert all(r.data_quality_level == "usable" for r in rows)
    assert ctx.meta["skill_opinion_recording"]["status"] == "recorded"
    assert ctx.meta["skill_opinion_recording"]["samples_created"] == 2


def test_pipeline_hook_on_without_history_id_defers(isolated_db) -> None:
    ctx = AgentContext(stock_code="600519")
    host = SimpleNamespace(
        config=SimpleNamespace(skill_opinion_recording_enabled=True),
    )
    _PipelineMethods._maybe_record_skill_opinion_samples(
        host,  # type: ignore[arg-type]
        ctx,
        _valid_opinions(),
    )
    assert ctx.meta["skill_opinion_recording"]["status"] == "deferred"
    assert ctx.meta["skill_opinion_recording"]["reason"] == "missing_analysis_history_id"
    samples, total = SkillOpinionSampleRepository(isolated_db).list_recent(limit=10)
    assert total == 0
    assert samples == []


def test_pipeline_hook_failure_never_raises(isolated_db, monkeypatch) -> None:
    history_id = _add_history(isolated_db)
    ctx = AgentContext(stock_code="600519")
    ctx.meta["analysis_history_id"] = history_id

    def _boom(**_kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(
        SkillOpinionSampleService,
        "record_from_agent_opinions",
        _boom,
    )
    host = SimpleNamespace(
        config=SimpleNamespace(skill_opinion_recording_enabled=True),
    )
    _PipelineMethods._maybe_record_skill_opinion_samples(
        host,  # type: ignore[arg-type]
        ctx,
        _valid_opinions(),
    )
    assert ctx.meta["skill_opinion_recording"]["status"] == "failed"


def test_run_strategy_engine_off_parity_no_db_side_effect(isolated_db) -> None:
    history_id = _add_history(isolated_db)
    ctx = AgentContext(stock_code="600519")
    ctx.meta["analysis_history_id"] = history_id
    ctx.opinions = _valid_opinions()

    host = SimpleNamespace(
        config=SimpleNamespace(skill_opinion_recording_enabled=False),
        strategy_engine=MagicMock(),
    )
    host._maybe_record_skill_opinion_samples = MethodType(
        _PipelineMethods._maybe_record_skill_opinion_samples,
        host,
    )
    consensus = AgentOpinion(
        agent_name="skill_consensus",
        signal="buy",
        confidence=0.7,
    )
    host.strategy_engine.process.return_value = StrategyResult(
        status=StrategyResultStatus.CONSENSUS,
        synthesis_dict={"final_signal": "buy"},
        consensus_opinion=consensus,
        skill_consensus_data={
            "signal": "buy",
            "confidence": 0.7,
            "strategy_synthesis": {"final_signal": "buy"},
        },
        valid_skill_opinions=list(ctx.opinions),
        non_skill_opinions=[],
        invalid_records=[],
        invalid_count=0,
    )

    _PipelineMethods._run_strategy_engine(host, ctx)  # type: ignore[arg-type]

    assert ctx.get_data("skill_consensus")["signal"] == "buy"
    assert any(op.agent_name == "skill_consensus" for op in ctx.opinions)
    assert SkillOpinionSampleRepository(isolated_db).list_for_history(history_id) == []


def test_maybe_materialize_after_history_save_respects_flag(isolated_db) -> None:
    import json

    raw = json.dumps(
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
    )
    with isolated_db.session_scope() as session:
        row = AnalysisHistory(
            query_id="materialize-flag",
            code="600519",
            report_type="simple",
            raw_result=raw,
            context_snapshot="{}",
            created_at=datetime(2026, 8, 4, 12, 0, 0),
        )
        session.add(row)
        session.flush()
        history_id = int(row.id)

    service = SkillOpinionSampleService(isolated_db)
    assert (
        service.maybe_materialize_after_history_save(
            history_id,
            config=SimpleNamespace(skill_opinion_recording_enabled=False),
        )
        == 0
    )
    assert SkillOpinionSampleRepository(isolated_db).list_for_history(history_id) == []

    created = service.maybe_materialize_after_history_save(
        history_id,
        config=SimpleNamespace(skill_opinion_recording_enabled=True),
    )
    assert created == 1
    rows = SkillOpinionSampleRepository(isolated_db).list_for_history(history_id)
    assert len(rows) == 1
    assert rows[0].skill_id == "bull_trend"
