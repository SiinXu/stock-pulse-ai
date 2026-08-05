# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Add optional resolution_notes column on backtest_results."""

from sqlalchemy.engine import Connection

from src.migrations.types import Migration


MIGRATION_ID = "202608050001_backtest_resolution_notes"
DESCRIPTION = "Add nullable resolution_notes on backtest_results"


def _backtest_result_columns(connection: Connection) -> set:
    """Return current column names of backtest_results, if the table exists."""
    rows = connection.exec_driver_sql("PRAGMA table_info(backtest_results)").fetchall()
    return {str(row[1]) for row in rows}


def upgrade(connection: Connection) -> None:
    """Add resolution_notes when missing; no-op on fresh create_all schemas.

    Restart-idempotent: re-running after the column exists is a no-op, which
    keeps docker-build CI (migrations executed twice) safe.
    """
    existing = _backtest_result_columns(connection)
    if not existing:
        return
    if "resolution_notes" in existing:
        return
    connection.exec_driver_sql(
        "ALTER TABLE backtest_results ADD COLUMN resolution_notes VARCHAR(64)"
    )


MIGRATION = Migration.from_source_file(
    id=MIGRATION_ID,
    description=DESCRIPTION,
    upgrade=upgrade,
    source_file=__file__,
)
