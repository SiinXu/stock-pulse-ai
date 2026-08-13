# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Create append-oriented agent evolution episode log table."""

from src.migrations.types import Migration, MigrationExecution


MIGRATION_ID = "202608120002_agent_episode_schema"
DESCRIPTION = "Create agent_episodes table for trajectory and lesson storage"

_TABLE_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS agent_episodes (
        id INTEGER NOT NULL PRIMARY KEY,
        schema_version VARCHAR(32) NOT NULL,
        episode_id VARCHAR(128) NOT NULL,
        run_id VARCHAR(128) NOT NULL,
        mode VARCHAR(32) NOT NULL,
        symbol VARCHAR(32),
        market VARCHAR(16),
        started_at DATETIME,
        completed_at DATETIME,
        success BOOLEAN,
        soul_version VARCHAR(64),
        soul_hash VARCHAR(128),
        trajectory_summary_json TEXT NOT NULL,
        lessons_json TEXT NOT NULL,
        outcome_labels_json TEXT,
        created_at DATETIME NOT NULL,
        CONSTRAINT uix_agent_episodes_episode_id UNIQUE (episode_id)
    )
    """,
)

_INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS ix_agent_episodes_run_id "
    "ON agent_episodes (run_id)",
    "CREATE INDEX IF NOT EXISTS ix_agent_episodes_symbol_created "
    "ON agent_episodes (symbol, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_agent_episodes_created_at "
    "ON agent_episodes (created_at)",
    "CREATE INDEX IF NOT EXISTS ix_agent_episodes_mode_created "
    "ON agent_episodes (mode, created_at)",
)

_TRIGGER_STATEMENTS = (
    """
    CREATE TRIGGER IF NOT EXISTS trg_agent_episodes_immutable
    BEFORE UPDATE ON agent_episodes
    BEGIN
        SELECT RAISE(ABORT, 'agent_episodes are append-only');
    END
    """,
)


def upgrade(execution: MigrationExecution) -> None:
    """Create the episode table, indexes, and append-only update guard."""
    for statement in _TABLE_STATEMENTS:
        execution.exec_driver_sql(statement)
    for statement in _INDEX_STATEMENTS:
        execution.exec_driver_sql(statement)
    for statement in _TRIGGER_STATEMENTS:
        execution.exec_driver_sql(statement)


MIGRATION = Migration.from_source_file(
    id=MIGRATION_ID,
    description=DESCRIPTION,
    upgrade=upgrade,
    source_file=__file__,
)
