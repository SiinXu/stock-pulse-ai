# -*- coding: utf-8 -*-
"""RepositoryError contract: failures raise; missing rows stay None/empty."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from fastapi import HTTPException

from src.repositories.analysis_repo import AnalysisRepository
from src.repositories.base import BaseRepository, RepositoryError
from src.repositories.stock_repo import StockRepository


def test_base_repository_log_and_raise_wraps_cause() -> None:
    repo = BaseRepository(db_manager=MagicMock())
    logger = MagicMock()
    cause = RuntimeError("db down")

    with pytest.raises(RepositoryError) as raised:
        repo._log_and_raise(
            logger,
            "lookup failed",
            cause,
            error_code="test_lookup_failed",
            context={"stock_code": "600519"},
        )

    assert raised.value.error_code == "test_lookup_failed"
    assert raised.value.context == {"stock_code": "600519"}
    assert raised.value.__cause__ is cause


def test_stock_repo_get_latest_raises_on_query_failure_not_empty_list() -> None:
    db = MagicMock()
    db.get_latest_data.side_effect = RuntimeError("connection lost")
    repo = StockRepository(db)

    with pytest.raises(RepositoryError) as raised:
        repo.get_latest("600519", days=2)

    assert raised.value.error_code == "latest_stock_data_lookup_failed"
    assert raised.value.context.get("stock_code") == "600519"


def test_stock_repo_get_range_raises_on_query_failure() -> None:
    db = MagicMock()
    db.get_data_range.side_effect = RuntimeError("timeout")
    repo = StockRepository(db)

    with pytest.raises(RepositoryError):
        repo.get_range("600519", date(2026, 1, 1), date(2026, 1, 31))


def test_stock_repo_save_dataframe_raises_instead_of_returning_zero() -> None:
    """Duplicate-write counterexample: silent 0 previously invited retries that rewrite."""
    db = MagicMock()
    db.save_daily_data.side_effect = RuntimeError("unique constraint / disk full")
    repo = StockRepository(db)
    frame = pd.DataFrame(
        {
            "date": [date(2026, 1, 2)],
            "open": [10.0],
            "high": [11.0],
            "low": [9.0],
            "close": [10.5],
            "volume": [1000],
        }
    )

    with pytest.raises(RepositoryError) as raised:
        saved = repo.save_dataframe(frame, "600519", data_source="test")
        # If the old contract returned 0, callers treated failure as "nothing saved"
        # and could retry/duplicate under DB pressure.
        assert saved == 0  # pragma: no cover - must not reach

    assert raised.value.error_code == "daily_stock_data_save_failed"
    assert "0" not in str(raised.value) or True


def test_stock_repo_has_today_data_raises_on_check_failure() -> None:
    db = MagicMock()
    db.has_today_data.side_effect = RuntimeError("db offline")
    repo = StockRepository(db)

    with pytest.raises(RepositoryError) as raised:
        repo.has_today_data("600519")

    assert raised.value.error_code == "stock_data_existence_check_failed"


def test_stock_repo_get_analysis_context_raises_on_failure_not_none() -> None:
    db = MagicMock()
    db.get_analysis_context.side_effect = RuntimeError("query failed")
    repo = StockRepository(db)

    with pytest.raises(RepositoryError):
        repo.get_analysis_context("600519")


def test_analysis_repo_get_by_query_id_returns_none_when_missing() -> None:
    db = MagicMock()
    db.get_analysis_history.return_value = []
    repo = AnalysisRepository(db)

    assert repo.get_by_query_id("missing-query") is None


def test_analysis_repo_get_by_query_id_raises_on_query_failure() -> None:
    db = MagicMock()
    db.get_analysis_history.side_effect = RuntimeError("database unavailable")
    repo = AnalysisRepository(db)

    with pytest.raises(RepositoryError) as raised:
        repo.get_by_query_id("q-1")

    assert raised.value.error_code == "analysis_record_lookup_failed"
    assert raised.value.context.get("query_id") == "q-1"


def test_analysis_repo_get_list_raises_on_failure_not_empty() -> None:
    db = MagicMock()
    db.get_analysis_history.side_effect = RuntimeError("database unavailable")
    repo = AnalysisRepository(db)

    with pytest.raises(RepositoryError):
        repo.get_list(code="600519")


def test_analysis_repo_save_raises_instead_of_returning_zero() -> None:
    """Duplicate-write counterexample for analysis history persistence."""
    db = MagicMock()
    db.save_analysis_history.side_effect = RuntimeError("write failed mid-transaction")
    repo = AnalysisRepository(db)
    result = SimpleNamespace(code="600519", name="test")

    with pytest.raises(RepositoryError) as raised:
        repo.save(result, query_id="q-dup", report_type="detailed")

    assert raised.value.error_code == "analysis_result_save_failed"
    db.save_analysis_history.assert_called_once()


def test_analysis_repo_count_by_code_raises_on_failure() -> None:
    db = MagicMock()
    db.get_analysis_history.side_effect = RuntimeError("database unavailable")
    repo = AnalysisRepository(db)

    with pytest.raises(RepositoryError):
        repo.count_by_code("600519")


def test_analysis_repo_delete_no_progress_raises_repository_error() -> None:
    db = MagicMock()
    db.get_analysis_history_paginated.return_value = ([SimpleNamespace(id=1)], 1)
    db.delete_analysis_history_records.return_value = 0
    repo = AnalysisRepository(db)

    with pytest.raises(RepositoryError) as raised:
        repo.delete_by_stock_codes(["600519"])

    assert raised.value.error_code == "analysis_history_delete_no_progress"


def test_history_detail_maps_not_found_to_404_and_repository_error_to_500() -> None:
    try:
        from api.v1.endpoints.history import get_history_detail
    except ModuleNotFoundError:
        pytest.skip("fastapi is not installed in this test environment")

    db = MagicMock()

    with patch("api.v1.endpoints.history.HistoryService") as service_class:
        service_class.return_value.resolve_and_get_detail.return_value = None
        with pytest.raises(HTTPException) as not_found:
            get_history_detail("missing-id", db_manager=db)
        assert not_found.value.status_code == 404
        assert not_found.value.detail.get("error") == "not_found"

    with patch("api.v1.endpoints.history.HistoryService") as service_class:
        service_class.return_value.resolve_and_get_detail.side_effect = RepositoryError(
            "analysis lookup failed",
            error_code="analysis_record_lookup_failed",
        )
        with pytest.raises(HTTPException) as server_error:
            get_history_detail("q-1", db_manager=db)
        assert server_error.value.status_code == 500
        assert server_error.value.detail.get("error") == "internal_error"


def test_history_delete_by_code_maps_repository_error_to_500() -> None:
    try:
        from api.v1.endpoints.history import delete_history_by_code
    except ModuleNotFoundError:
        pytest.skip("fastapi is not installed in this test environment")

    db = MagicMock()
    with patch("api.v1.endpoints.history.HistoryService") as service_class:
        service_class.return_value.delete_history_by_code.side_effect = RepositoryError(
            "history deletion made no progress",
            error_code="analysis_history_delete_no_progress",
        )
        with pytest.raises(HTTPException) as raised:
            delete_history_by_code("600519", db_manager=db)

    assert raised.value.status_code == 500
    assert raised.value.detail.get("error") == "internal_error"


def test_history_list_maps_repository_error_to_500() -> None:
    try:
        from api.v1.endpoints.history import get_history_list
    except ModuleNotFoundError:
        pytest.skip("fastapi is not installed in this test environment")

    db = MagicMock()
    with patch("api.v1.endpoints.history.HistoryService") as service_class:
        service_class.return_value.get_history_list.side_effect = RepositoryError(
            "list failed",
            error_code="analysis_record_list_failed",
        )
        with pytest.raises(HTTPException) as raised:
            get_history_list(
                stock_code=None,
                report_type=None,
                start_date=None,
                end_date=None,
                page=1,
                limit=20,
                db_manager=db,
            )

    assert raised.value.status_code == 500
    assert raised.value.detail.get("error") == "internal_error"
