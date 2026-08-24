# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Finalize-path persistence of verifiable prediction drafts (Issue #1101)."""

from __future__ import annotations

import inspect
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import func, select
from tests.litellm_stub import ensure_litellm_stub

ensure_litellm_stub()

from src.agent.orchestrator_parts.dashboard import _DashboardMethods
from src.agent.protocols import AgentContext, AgentOpinion
from src.config import Config
from src.core.stages.analysis_agent import _AgentAnalysisStageMixin
from src.core.stages.persistence import _PersistenceStageMixin
from src.repositories.agent_prediction_repo import AgentPredictionRepository
from src.repositories.agent_prediction_tables import agent_predictions_table
from src.repositories.base import RepositoryError
from src.schemas.agent_prediction import STATUS_PENDING, STATUS_RESOLVED
from src.services.prediction_persist import canonical_run_id, prediction_id_for_run
from src.storage import DatabaseManager


UTC = timezone.utc
RESOLVE = datetime(2024, 3, 22, 7, 0, 0, tzinfo=UTC)


class _FakeResolve:
    def __init__(self) -> None:
        self.resolve_after = RESOLVE

    def to_dict(self) -> dict:
        return {
            "resolve_after": self.resolve_after.isoformat(),
            "calendar_approx": False,
            "market": "cn",
            "horizon": "5d",
        }


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "prediction-persist.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    Config.reset_instance()
    DatabaseManager.reset_instance()
    db = DatabaseManager.get_instance()
    try:
        yield db
    finally:
        DatabaseManager.reset_instance()
        Config.reset_instance()


@pytest.fixture()
def mock_resolve_after():
    with patch(
        "src.services.prediction_extractor._compute_resolve_after",
        return_value=(RESOLVE, _FakeResolve().to_dict(), None),
    ) as mocked:
        yield mocked


def _pending_rows(db) -> list:
    with db.get_session() as session:
        return list(
            session.execute(
                select(agent_predictions_table).where(
                    agent_predictions_table.c.status == STATUS_PENDING
                )
            ).all()
        )


def _pending_count(db) -> int:
    with db.get_session() as session:
        return int(
            session.execute(
                select(func.count())
                .select_from(agent_predictions_table)
                .where(agent_predictions_table.c.status == STATUS_PENDING)
            ).scalar_one()
        )


def _all_prediction_rows(db) -> list:
    with db.get_session() as session:
        return list(session.execute(select(agent_predictions_table)).all())


def _verifiable_pipeline(repo: AgentPredictionRepository) -> _PersistenceStageMixin:
    pipeline = _PersistenceStageMixin()
    pipeline.config = SimpleNamespace(prediction_extract_enabled=True)
    pipeline.agent_prediction_repo = repo
    return pipeline


def _verifiable_agent(
    repo: Optional[AgentPredictionRepository] = None,
) -> _DashboardMethods:
    orchestrator = _DashboardMethods()
    orchestrator.config = SimpleNamespace(prediction_extract_enabled=True)
    if repo is not None:
        orchestrator.agent_prediction_repo = repo
    return orchestrator


def _agent_context_for_query(query_id: str) -> AgentContext:
    ctx = AgentContext(
        query="analyze 600519",
        stock_code="600519",
        stock_name="Test",
        meta={"run_id": query_id, "query_id": query_id},
    )
    ctx.add_opinion(AgentOpinion(agent_name="decision", signal="buy", confidence=0.8))
    return ctx


def _agent_dashboard() -> dict:
    return {"action": "buy", "stock_code": "600519", "stock_name": "Test"}


def _agent_history_result() -> SimpleNamespace:
    return SimpleNamespace(
        code="600519",
        name="Test",
        model_used="test-model",
        prediction_source={
            "code": "600519",
            "action": "buy",
            "confidence": 0.8,
        },
        dashboard={},
    )


def _verifiable_result() -> SimpleNamespace:
    return SimpleNamespace(
        code="600519",
        name="Test",
        model_used="test-model",
        prediction_source={
            "code": "600519",
            "decision_type": "buy",
            "confidence_level": "高",
        },
        dashboard={},
    )


def test_prediction_id_for_run_is_stable_bounded_and_unambiguous() -> None:
    first = prediction_id_for_run("run-a", "600519")
    second = prediction_id_for_run("run-a", "600519")
    other = prediction_id_for_run("run-b", "600519")
    assert first == second == "pred-5:run-a:600519"
    assert other != first
    assert prediction_id_for_run("a-b", "c") != prediction_id_for_run("a", "b-c")
    overflow = prediction_id_for_run("r" * 128, "600519")
    assert overflow.startswith("pred-")
    assert len(overflow) <= 128
    assert overflow != prediction_id_for_run("r" * 128, "AAPL")
    assert canonical_run_id("", None, " query-1 ", "session") == "query-1"


def test_agent_analysis_threads_query_id_as_canonical_run_id() -> None:
    source = inspect.getsource(_AgentAnalysisStageMixin._analyze_with_agent)
    assert '"query_id": query_id' in source
    assert '"run_id": query_id' in source


def test_build_context_copies_pipeline_query_id_as_run_id() -> None:
    from src.agent.orchestrator import AgentOrchestrator

    orchestrator = AgentOrchestrator(
        tool_registry=MagicMock(),
        llm_adapter=MagicMock(),
    )
    ctx = orchestrator._build_context(
        "analyze 600519",
        {
            "stock_code": "600519",
            "stock_name": "Test",
            "query_id": "query-canonical-run",
            "run_id": "query-canonical-run",
        },
    )
    assert ctx.meta["run_id"] == "query-canonical-run"
    assert ctx.meta["query_id"] == "query-canonical-run"
    assert ctx.session_id == ""


def test_finalize_writes_one_pending_row_per_verifiable_prediction(
    isolated_db, mock_resolve_after
) -> None:
    repo = AgentPredictionRepository(isolated_db)
    pipeline = _verifiable_pipeline(repo)
    result = _verifiable_result()

    pipeline._extract_prediction_after_history_save(
        result=result,
        query_id="query-persist-one",
        source_report_id=41,
        mode="analysis",
    )

    assert result.prediction_extraction["verifiable"] is True
    rows = _pending_rows(isolated_db)
    assert len(rows) == 1
    stored = rows[0]
    assert stored.status == STATUS_PENDING
    assert stored.run_id == "query-persist-one"
    assert stored.symbol == "600519"
    assert stored.prediction_id == prediction_id_for_run(
        "query-persist-one", "600519"
    )
    assert result.prediction_extraction["record"]["prediction_id"] == stored.prediction_id
    assert result.prediction_extraction["record"]["run_id"] == stored.run_id
    claims = stored.claims_json
    assert "direction" in claims
    assert stored.source_decision_id == "41"


def test_re_finalize_same_run_does_not_duplicate_rows(
    isolated_db, mock_resolve_after
) -> None:
    repo = AgentPredictionRepository(isolated_db)
    pipeline = _verifiable_pipeline(repo)
    first = _verifiable_result()
    second = _verifiable_result()

    pipeline._extract_prediction_after_history_save(
        result=first,
        query_id="query-persist-dup",
        source_report_id=41,
        mode="analysis",
    )
    pipeline._extract_prediction_after_history_save(
        result=second,
        query_id="query-persist-dup",
        source_report_id=41,
        mode="analysis",
    )

    assert first.prediction_extraction["verifiable"] is True
    assert second.prediction_extraction["verifiable"] is True
    assert _pending_count(isolated_db) == 1
    row = _pending_rows(isolated_db)[0]
    assert row.prediction_id == prediction_id_for_run(
        "query-persist-dup", "600519"
    )
    assert first.prediction_extraction["record"]["prediction_id"] == row.prediction_id
    assert second.prediction_extraction["record"]["prediction_id"] == row.prediction_id
    existing = repo.get(row.prediction_id)
    assert existing is not None
    assert existing.status == STATUS_PENDING


def test_store_failure_leaves_analysis_result_intact_and_records_failure(
    isolated_db, mock_resolve_after
) -> None:
    repo = AgentPredictionRepository(isolated_db)

    def _boom(fields):
        raise RepositoryError(
            "Agent prediction insert failed",
            error_code="agent_prediction_insert_failed",
            context={"prediction_id": fields.prediction_id},
        )

    repo.insert_pending = _boom  # type: ignore[method-assign]
    pipeline = _verifiable_pipeline(repo)
    result = _verifiable_result()

    with patch(
        "src.services.prediction_persist.log_safe_exception"
    ) as logged:
        pipeline._extract_prediction_after_history_save(
            result=result,
            query_id="query-persist-fail",
            source_report_id=41,
            mode="analysis",
        )

    assert result.prediction_extraction["verifiable"] is True
    assert result.prediction_extraction["record"]["status"] == "pending"
    assert result.prediction_extraction["record"]["claims"]
    assert _pending_count(isolated_db) == 0
    logged.assert_called()
    kwargs = logged.call_args.kwargs
    assert kwargs["error_code"] == "pipeline_prediction_persist_failed"
    assert kwargs["level"] == logging.WARNING


def test_non_verifiable_extraction_does_not_insert_pending_row(
    isolated_db, mock_resolve_after
) -> None:
    repo = AgentPredictionRepository(isolated_db)
    pipeline = _verifiable_pipeline(repo)
    result = SimpleNamespace(
        code="600519",
        name="Test",
        model_used="test-model",
        prediction_source={
            "code": "600519",
            "analysis_summary": "散文不应单独成为声明",
        },
        dashboard={},
    )

    pipeline._extract_prediction_after_history_save(
        result=result,
        query_id="query-persist-prose",
        source_report_id=41,
        mode="analysis",
    )

    assert result.prediction_extraction["verifiable"] is False
    assert _pending_count(isolated_db) == 0


def test_agent_dashboard_finalize_persists_one_pending_row(
    isolated_db, mock_resolve_after
) -> None:
    repo = AgentPredictionRepository(isolated_db)
    orchestrator = _verifiable_agent(repo)
    ctx = _agent_context_for_query("query-agent-dash")

    orchestrator._maybe_extract_prediction_on_finalize(_agent_dashboard(), ctx)

    extraction = ctx.meta["prediction_extraction"]
    rows = _pending_rows(isolated_db)
    assert extraction["verifiable"] is True
    assert len(rows) == 1
    stored = rows[0]
    assert stored.run_id == "query-agent-dash"
    assert stored.symbol == "600519"
    assert stored.prediction_id == prediction_id_for_run("query-agent-dash", "600519")
    assert extraction["record"]["prediction_id"] == stored.prediction_id
    assert extraction["record"]["run_id"] == stored.run_id


def test_agent_dashboard_default_repo_persists_pending_row(
    isolated_db, mock_resolve_after
) -> None:
    orchestrator = _verifiable_agent()
    ctx = _agent_context_for_query("query-agent-default-repo")

    orchestrator._maybe_extract_prediction_on_finalize(_agent_dashboard(), ctx)

    extraction = ctx.meta["prediction_extraction"]
    rows = _pending_rows(isolated_db)
    assert extraction["verifiable"] is True
    assert len(rows) == 1
    stored = rows[0]
    assert extraction["record"]["prediction_id"] == stored.prediction_id
    assert stored.run_id == "query-agent-default-repo"


def test_dual_hook_same_analysis_writes_one_row_and_attached_id_equals_stored(
    isolated_db, mock_resolve_after
) -> None:
    from src.agent.orchestrator import AgentOrchestrator

    query_id = "query-dual-hook"
    repo = AgentPredictionRepository(isolated_db)
    orchestrator = AgentOrchestrator(
        tool_registry=MagicMock(),
        llm_adapter=MagicMock(),
    )
    orchestrator.config = SimpleNamespace(prediction_extract_enabled=True)
    orchestrator.agent_prediction_repo = repo
    ctx = orchestrator._build_context(
        "analyze 600519",
        {
            "stock_code": "600519",
            "stock_name": "Test",
            "query_id": query_id,
            "run_id": query_id,
        },
    )
    ctx.add_opinion(AgentOpinion(agent_name="decision", signal="buy", confidence=0.8))
    pipeline = _verifiable_pipeline(repo)
    result = _agent_history_result()

    orchestrator._maybe_extract_prediction_on_finalize(_agent_dashboard(), ctx)
    pipeline._extract_prediction_after_history_save(
        result=result,
        query_id=query_id,
        source_report_id=41,
        mode="agent",
    )

    rows = _all_prediction_rows(isolated_db)
    assert len(rows) == 1
    stored = rows[0]
    expected_id = prediction_id_for_run(query_id, "600519")
    assert stored.status == STATUS_PENDING
    assert stored.run_id == query_id
    assert stored.prediction_id == expected_id
    agent_extraction = ctx.meta["prediction_extraction"]
    history_extraction = result.prediction_extraction
    assert agent_extraction["record"]["prediction_id"] == stored.prediction_id
    assert history_extraction["record"]["prediction_id"] == stored.prediction_id
    assert agent_extraction["record"]["run_id"] == stored.run_id
    assert history_extraction["record"]["run_id"] == stored.run_id


def test_re_finalize_after_resolve_does_not_overwrite(
    isolated_db, mock_resolve_after
) -> None:
    query_id = "query-after-resolve"
    repo = AgentPredictionRepository(isolated_db)
    orchestrator = _verifiable_agent(repo)
    pipeline = _verifiable_pipeline(repo)
    ctx = _agent_context_for_query(query_id)
    result = _agent_history_result()

    orchestrator._maybe_extract_prediction_on_finalize(_agent_dashboard(), ctx)
    pipeline._extract_prediction_after_history_save(
        result=result,
        query_id=query_id,
        source_report_id=41,
        mode="agent",
    )
    stored_id = prediction_id_for_run(query_id, "600519")
    original = repo.get(stored_id)
    assert original is not None
    original_claims = original.claims
    applied, resolved = repo.resolve(
        prediction_id=stored_id,
        outcome={"label": "hit", "score": 1.0},
        as_of=RESOLVE + timedelta(seconds=1),
    )
    assert applied is True
    assert resolved is not None
    assert resolved.status == STATUS_RESOLVED

    later_ctx = _agent_context_for_query(query_id)
    later_result = _agent_history_result()
    orchestrator._maybe_extract_prediction_on_finalize(_agent_dashboard(), later_ctx)
    pipeline._extract_prediction_after_history_save(
        result=later_result,
        query_id=query_id,
        source_report_id=99,
        mode="agent",
    )

    rows = _all_prediction_rows(isolated_db)
    assert len(rows) == 1
    again = repo.get(stored_id)
    assert again is not None
    assert again.status == STATUS_RESOLVED
    assert again.outcome == {"label": "hit", "score": 1.0}
    assert again.claims == original_claims
    assert again.source_decision_id == original.source_decision_id
    assert later_ctx.meta["prediction_extraction"]["record"]["prediction_id"] == stored_id
    assert later_result.prediction_extraction["record"]["prediction_id"] == stored_id
    assert _pending_count(isolated_db) == 0
