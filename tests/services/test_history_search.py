from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from api.v1.endpoints.history import search_history
from src.config import Config
from src.migrations.versions.v202608100002_analysis_history_search_fts import upgrade
from src.storage import AnalysisHistory, DatabaseManager


@pytest.fixture()
def database() -> DatabaseManager:
    Config.reset_instance()
    DatabaseManager.reset_instance()
    manager = DatabaseManager(db_url="sqlite:///:memory:")
    try:
        yield manager
    finally:
        DatabaseManager.reset_instance()
        Config.reset_instance()


def _history_row(
    index: int,
    *,
    code: str = "600519.SH",
    name: str = "Kweichow Moutai",
    summary: str = "Long-term quality remains constructive",
) -> AnalysisHistory:
    return AnalysisHistory(
        query_id=None,
        code=code,
        name=name,
        report_type="detailed",
        trend_prediction="bullish structure",
        analysis_summary=summary,
        operation_advice="hold patiently",
        raw_result='{"private_token":"must-not-be-searchable"}',
        news_content="provider secret marker",
        context_snapshot='{"api_key":"must-not-be-searchable"}',
        created_at=datetime(2026, 8, 10, 9, 0) - timedelta(minutes=index),
    )


def test_search_migration_backfills_existing_history_rows() -> None:
    engine = create_engine("sqlite:///:memory:")
    AnalysisHistory.__table__.create(engine)
    with engine.begin() as connection:
        connection.execute(
            AnalysisHistory.__table__.insert().values(
                code="AAPL",
                name="Apple",
                analysis_summary="Legacy durable quality",
            )
        )
        upgrade(connection)
        count = connection.exec_driver_sql(
            "SELECT count(*) FROM analysis_history_search "
            "WHERE analysis_history_search MATCH '\"durable quality\"'"
        ).scalar_one()

    engine.dispose()
    assert count == 1


def test_search_migration_preserves_unknown_reserved_name_collision() -> None:
    engine = create_engine("sqlite:///:memory:")
    AnalysisHistory.__table__.create(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE analysis_history_search (sentinel TEXT NOT NULL)"
        )

    with pytest.raises(OperationalError):
        with engine.begin() as connection:
            upgrade(connection)

    with engine.connect() as connection:
        columns = connection.exec_driver_sql(
            "PRAGMA table_info(analysis_history_search)"
        ).fetchall()
    engine.dispose()
    assert [column[1] for column in columns] == ["sentinel"]


def test_search_uses_bounded_low_sensitive_projection(database: DatabaseManager) -> None:
    with database.session_scope() as session:
        session.add_all([_history_row(index) for index in range(12)])

    records = database.search_analysis_history("Long-term quality", limit=99)

    assert len(records) == 10
    assert set(records[0]) == {
        "id",
        "stock_code",
        "stock_name",
        "report_type",
        "analysis_summary",
        "operation_advice",
        "trend_prediction",
        "created_at",
    }
    assert database.search_analysis_history("must-not-be-searchable", limit=5) == []
    assert database.search_analysis_history("provider secret", limit=5) == []


def test_search_triggers_synchronize_insert_update_and_delete(database: DatabaseManager) -> None:
    with database.session_scope() as session:
        row = _history_row(1, summary="Initial durable thesis")
        session.add(row)
        session.flush()
        record_id = int(row.id)

    assert [item["id"] for item in database.search_analysis_history("durable thesis")] == [record_id]

    with database.session_scope() as session:
        row = session.get(AnalysisHistory, record_id)
        assert row is not None
        row.analysis_summary = "Updated cash-flow quality"

    assert database.search_analysis_history("durable thesis") == []
    assert [item["id"] for item in database.search_analysis_history("cash-flow quality")] == [record_id]

    with database.session_scope() as session:
        row = session.get(AnalysisHistory, record_id)
        assert row is not None
        session.delete(row)

    assert database.search_analysis_history("cash-flow quality") == []


@pytest.mark.parametrize(
    ("query", "field", "value"),
    [
        ("600519.SH", "code", "600519.SH"),
        ("Kweichow Moutai", "name", "Kweichow Moutai"),
        ("detailed", "report_type", "detailed"),
        ("bullish structure", "trend_prediction", "bullish structure"),
        ("Long-term quality", "analysis_summary", "Long-term quality remains constructive"),
        ("hold patiently", "operation_advice", "hold patiently"),
    ],
)
def test_search_indexes_each_allowed_column(
    database: DatabaseManager,
    query: str,
    field: str,
    value: str,
) -> None:
    row = _history_row(1)
    setattr(row, field, value)
    with database.session_scope() as session:
        session.add(row)

    assert len(database.search_analysis_history(query)) == 1


@pytest.mark.parametrize(
    "query",
    ['abc"def', "foo OR bar", "NOT", "code:", "(value)", "long-term"],
)
def test_search_treats_fts_operators_as_literal_text(
    database: DatabaseManager,
    query: str,
) -> None:
    with database.session_scope() as session:
        session.add(_history_row(1, summary=f"Literal marker {query} remains searchable"))

    assert len(database.search_analysis_history(query)) == 1


def test_search_query_plan_uses_fts_virtual_index(database: DatabaseManager) -> None:
    with database.get_session() as session:
        plan = session.execute(
            text(
                "EXPLAIN QUERY PLAN SELECT history.id "
                "FROM analysis_history_search "
                "JOIN analysis_history AS history ON history.id = analysis_history_search.rowid "
                "WHERE analysis_history_search MATCH :query LIMIT 5"
            ),
            {"query": '"quality"'},
        ).fetchall()

    detail = " ".join(str(row[-1]) for row in plan).lower()
    assert "virtual table index" in detail
    assert "scan history" not in detail


def test_history_search_endpoint_returns_truncated_dto_and_hides_full_payload(
    database: DatabaseManager,
) -> None:
    long_summary = "Long-term quality " + ("evidence " * 80)
    with database.session_scope() as session:
        session.add(_history_row(1, summary=long_summary))

    response = search_history(q="Long-term quality", limit=5, db_manager=database)
    payload = response.model_dump()

    assert len(payload["items"]) == 1
    assert len(payload["items"][0]["summary"]) <= 240
    assert set(payload["items"][0]) == {
        "id",
        "stock_code",
        "stock_name",
        "report_type",
        "summary",
        "created_at",
    }
    assert "query_id" not in payload["items"][0]
    assert "raw_result" not in payload["items"][0]
    assert "context_snapshot" not in payload["items"][0]


def test_history_search_endpoint_rejects_whitespace_after_normalization(
    database: DatabaseManager,
) -> None:
    with pytest.raises(HTTPException) as raised:
        search_history(q="   ", limit=5, db_manager=database)

    assert raised.value.status_code == 422
