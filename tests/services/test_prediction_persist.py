# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Finalize-path persistence of verifiable prediction drafts (Issue #1101)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import func, select

from src.config import Config
from src.core.stages.persistence import _PersistenceStageMixin
from src.repositories.agent_prediction_repo import AgentPredictionRepository
from src.repositories.agent_prediction_tables import agent_predictions_table
from src.repositories.base import RepositoryError
from src.schemas.agent_prediction import STATUS_PENDING
from src.services.prediction_persist import prediction_id_for_run
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


def _verifiable_pipeline(repo: AgentPredictionRepository) -> _PersistenceStageMixin:
    pipeline = _PersistenceStageMixin()
    pipeline.config = SimpleNamespace(prediction_extract_enabled=True)
    pipeline.agent_prediction_repo = repo
    return pipeline


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


def test_prediction_id_for_run_is_stable_and_bounded() -> None:
    first = prediction_id_for_run("run-a", "600519")
    second = prediction_id_for_run("run-a", "600519")
    other = prediction_id_for_run("run-b", "600519")
    assert first == second == "pred-run-a-600519"
    assert other != first
    overflow = prediction_id_for_run("r" * 128, "600519")
    assert overflow.startswith("pred-")
    assert len(overflow) <= 128
    assert overflow != prediction_id_for_run("r" * 128, "AAPL")


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
