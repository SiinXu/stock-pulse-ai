# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Create sidecar table for eval-fixture curator grades."""

from src.migrations.types import Migration, MigrationExecution


MIGRATION_ID = "202608250002_agent_curator_grade_schema"
DESCRIPTION = "Create agent episode curator-grade sidecar table"


_TABLE_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS agent_episode_curator_grades (
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        episode_id VARCHAR(128) NOT NULL,
        run_id VARCHAR(128) NOT NULL,
        manual_grade VARCHAR(16) NOT NULL,
        provenance_source VARCHAR(32),
        actor_id VARCHAR(128),
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        CONSTRAINT uix_agent_episode_curator_grades_episode
            UNIQUE (episode_id),
        CONSTRAINT ck_agent_episode_curator_grades_grade
            CHECK (manual_grade IN ('fail', 'harmful', 'partial', 'pass'))
    )
    """,
)

_INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS ix_agent_episode_curator_grades_run_id "
    "ON agent_episode_curator_grades (run_id)",
)

_DROP_STATEMENTS = (
    "DROP INDEX IF EXISTS ix_agent_episode_curator_grades_run_id",
    "DROP TABLE IF EXISTS agent_episode_curator_grades",
)


def upgrade(execution: MigrationExecution) -> None:
    """Create additive curator-grade sidecar table and indexes (restart-idempotent)."""
    for statement in _TABLE_STATEMENTS:
        execution.exec_driver_sql(statement)
    for statement in _INDEX_STATEMENTS:
        execution.exec_driver_sql(statement)


def downgrade(execution: MigrationExecution) -> None:
    """Drop the curator-grade sidecar. Append-only episodes are untouched."""
    for statement in _DROP_STATEMENTS:
        execution.exec_driver_sql(statement)


MIGRATION = Migration.from_source_file(
    id=MIGRATION_ID,
    description=DESCRIPTION,
    upgrade=upgrade,
    source_file=__file__,
)
