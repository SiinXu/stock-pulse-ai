# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Add a bounded, low-sensitive full-text index for analysis history search."""

from src.migrations.types import Migration, MigrationExecution


MIGRATION_ID = "202608100002_analysis_history_search_fts"
DESCRIPTION = "Add full-text search index for analysis history summaries"

_SEARCH_COLUMNS = (
    "code",
    "name",
    "report_type",
    "trend_prediction",
    "analysis_summary",
    "operation_advice",
    "created_at",
)


def upgrade(execution: MigrationExecution) -> None:
    """Create the FTS index, synchronize existing rows, and install maintenance triggers."""
    columns = ", ".join(_SEARCH_COLUMNS)
    execution.exec_driver_sql(
        "CREATE VIRTUAL TABLE analysis_history_search USING fts5("
        f"{columns}, "
        "content='analysis_history', content_rowid='id', tokenize='trigram'"
        ")"
    )
    execution.exec_driver_sql(
        "CREATE TRIGGER trg_analysis_history_search_insert "
        "AFTER INSERT ON analysis_history BEGIN "
        f"INSERT INTO analysis_history_search(rowid, {columns}) "
        f"VALUES (new.id, {', '.join(f'new.{column}' for column in _SEARCH_COLUMNS)}); "
        "END"
    )
    execution.exec_driver_sql(
        "CREATE TRIGGER trg_analysis_history_search_delete "
        "AFTER DELETE ON analysis_history BEGIN "
        f"INSERT INTO analysis_history_search(analysis_history_search, rowid, {columns}) "
        f"VALUES ('delete', old.id, {', '.join(f'old.{column}' for column in _SEARCH_COLUMNS)}); "
        "END"
    )
    execution.exec_driver_sql(
        "CREATE TRIGGER trg_analysis_history_search_update "
        "AFTER UPDATE OF code, name, report_type, trend_prediction, analysis_summary, operation_advice, created_at "
        "ON analysis_history BEGIN "
        f"INSERT INTO analysis_history_search(analysis_history_search, rowid, {columns}) "
        f"VALUES ('delete', old.id, {', '.join(f'old.{column}' for column in _SEARCH_COLUMNS)}); "
        f"INSERT INTO analysis_history_search(rowid, {columns}) "
        f"VALUES (new.id, {', '.join(f'new.{column}' for column in _SEARCH_COLUMNS)}); "
        "END"
    )
    execution.exec_driver_sql(
        "INSERT INTO analysis_history_search(analysis_history_search) VALUES ('rebuild')"
    )
    execution.exec_driver_sql(
        "INSERT INTO analysis_history_search(analysis_history_search, rank) "
        "VALUES ('integrity-check', 1)"
    )


MIGRATION = Migration.from_source_file(
    id=MIGRATION_ID,
    description=DESCRIPTION,
    upgrade=upgrade,
    source_file=__file__,
)
