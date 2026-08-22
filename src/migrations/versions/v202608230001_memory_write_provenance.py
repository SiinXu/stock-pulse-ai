# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Add nullable server-stamped provenance columns on governed memory tables."""

from src.migrations.types import Migration, MigrationExecution


MIGRATION_ID = "202608230001_memory_write_provenance"
DESCRIPTION = "Add nullable memory-write provenance columns"


def _column_names(execution: MigrationExecution, pragma_sql: str) -> set:
    rows = execution.exec_driver_sql(pragma_sql).fetchall()
    return {str(row[1]) for row in rows}


def _add_if_missing(
    execution: MigrationExecution,
    existing: set,
    column: str,
    alter_sql: str,
) -> None:
    if column not in existing:
        execution.exec_driver_sql(alter_sql)


def upgrade(execution: MigrationExecution) -> None:
    """Add nullable provenance columns and indexes; backfill feedback only."""
    feedback = _column_names(
        execution, "PRAGMA table_info(decision_signal_feedback)"
    )
    if feedback:
        _add_if_missing(
            execution,
            feedback,
            "provenance_source",
            "ALTER TABLE decision_signal_feedback "
            "ADD COLUMN provenance_source VARCHAR(32)",
        )
        _add_if_missing(
            execution,
            feedback,
            "actor_id",
            "ALTER TABLE decision_signal_feedback ADD COLUMN actor_id VARCHAR(128)",
        )
    outcomes = _column_names(
        execution, "PRAGMA table_info(decision_signal_outcomes)"
    )
    if outcomes:
        _add_if_missing(
            execution,
            outcomes,
            "provenance_source",
            "ALTER TABLE decision_signal_outcomes "
            "ADD COLUMN provenance_source VARCHAR(32)",
        )
        _add_if_missing(
            execution,
            outcomes,
            "actor_id",
            "ALTER TABLE decision_signal_outcomes ADD COLUMN actor_id VARCHAR(128)",
        )
    predictions = _column_names(execution, "PRAGMA table_info(agent_predictions)")
    if predictions:
        _add_if_missing(
            execution,
            predictions,
            "provenance_source",
            "ALTER TABLE agent_predictions ADD COLUMN provenance_source VARCHAR(32)",
        )
        _add_if_missing(
            execution,
            predictions,
            "actor_id",
            "ALTER TABLE agent_predictions ADD COLUMN actor_id VARCHAR(128)",
        )
    episodes = _column_names(execution, "PRAGMA table_info(agent_episodes)")
    if episodes:
        _add_if_missing(
            execution,
            episodes,
            "provenance_source",
            "ALTER TABLE agent_episodes ADD COLUMN provenance_source VARCHAR(32)",
        )
        _add_if_missing(
            execution,
            episodes,
            "actor_id",
            "ALTER TABLE agent_episodes ADD COLUMN actor_id VARCHAR(128)",
        )
    execution.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_decision_signal_feedback_provenance_source "
        "ON decision_signal_feedback (provenance_source)"
    )
    execution.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_decision_signal_outcomes_provenance_source "
        "ON decision_signal_outcomes (provenance_source)"
    )
    execution.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_agent_predictions_provenance_source "
        "ON agent_predictions (provenance_source)"
    )
    execution.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_agent_episodes_provenance_source "
        "ON agent_episodes (provenance_source)"
    )
    if "provenance_source" in _column_names(
        execution, "PRAGMA table_info(decision_signal_feedback)"
    ):
        execution.exec_driver_sql(
            "UPDATE decision_signal_feedback "
            "SET provenance_source = 'user_feedback' "
            "WHERE provenance_source IS NULL"
        )


def downgrade(execution: MigrationExecution) -> None:
    """Drop indexes; SQLite additive columns remain."""
    execution.exec_driver_sql(
        "DROP INDEX IF EXISTS ix_agent_episodes_provenance_source"
    )
    execution.exec_driver_sql(
        "DROP INDEX IF EXISTS ix_agent_predictions_provenance_source"
    )
    execution.exec_driver_sql(
        "DROP INDEX IF EXISTS ix_decision_signal_outcomes_provenance_source"
    )
    execution.exec_driver_sql(
        "DROP INDEX IF EXISTS ix_decision_signal_feedback_provenance_source"
    )


MIGRATION = Migration.from_source_file(
    id=MIGRATION_ID,
    description=DESCRIPTION,
    upgrade=upgrade,
    source_file=__file__,
)
