# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Create sidecar table for research-only episode forward-return buckets."""

from src.migrations.types import Migration, MigrationExecution


MIGRATION_ID = "202608250001_agent_forward_return_schema"
DESCRIPTION = "Create agent episode forward-return bucket sidecar table"

_TABLE_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS agent_episode_forward_returns (
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        episode_id VARCHAR(128) NOT NULL,
        run_id VARCHAR(128) NOT NULL,
        horizon VARCHAR(8) NOT NULL,
        forward_return_bucket VARCHAR(16) NOT NULL,
        provenance_source VARCHAR(32),
        actor_id VARCHAR(128),
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        CONSTRAINT uix_agent_episode_forward_returns_episode_horizon
            UNIQUE (episode_id, horizon),
        CONSTRAINT ck_agent_episode_forward_returns_horizon
            CHECK (horizon IN ('1d', '5d')),
        CONSTRAINT ck_agent_episode_forward_returns_bucket
            CHECK (forward_return_bucket IN (
                '1d_up', '1d_down', '1d_flat',
                '5d_up', '5d_down', '5d_flat'
            )),
        CONSTRAINT ck_agent_episode_forward_returns_bucket_matches_horizon
            CHECK (forward_return_bucket LIKE horizon || '_%')
    )
    """,
)

_INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS ix_agent_episode_forward_returns_run_id "
    "ON agent_episode_forward_returns (run_id)",
    "CREATE INDEX IF NOT EXISTS ix_agent_episode_forward_returns_episode_id "
    "ON agent_episode_forward_returns (episode_id)",
)

_DROP_STATEMENTS = (
    "DROP INDEX IF EXISTS ix_agent_episode_forward_returns_episode_id",
    "DROP INDEX IF EXISTS ix_agent_episode_forward_returns_run_id",
    "DROP TABLE IF EXISTS agent_episode_forward_returns",
)


def upgrade(execution: MigrationExecution) -> None:
    """Create additive forward-return sidecar table and indexes (restart-idempotent)."""
    for statement in _TABLE_STATEMENTS:
        execution.exec_driver_sql(statement)
    for statement in _INDEX_STATEMENTS:
        execution.exec_driver_sql(statement)


def downgrade(execution: MigrationExecution) -> None:
    """Drop the forward-return sidecar. Append-only episodes are untouched."""
    for statement in _DROP_STATEMENTS:
        execution.exec_driver_sql(statement)


MIGRATION = Migration.from_source_file(
    id=MIGRATION_ID,
    description=DESCRIPTION,
    upgrade=upgrade,
    source_file=__file__,
)
