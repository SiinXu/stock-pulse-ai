# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Create append-only EvolutionEvent persistence table."""

from src.migrations.types import Migration, MigrationExecution


MIGRATION_ID = "202608250003_agent_evolution_event_schema"
DESCRIPTION = "Create append-only agent evolution event store"


_TABLE_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS agent_evolution_events (
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        schema_version VARCHAR(32) NOT NULL,
        event_id VARCHAR(128) NOT NULL,
        occurred_at DATETIME NOT NULL,
        event_type VARCHAR(64) NOT NULL,
        actor VARCHAR(16) NOT NULL,
        reason_refs_json TEXT NOT NULL,
        before_json TEXT NOT NULL,
        after_json TEXT NOT NULL,
        created_at DATETIME NOT NULL,
        CONSTRAINT uix_agent_evolution_events_event_id UNIQUE (event_id),
        CONSTRAINT ck_agent_evolution_events_actor
            CHECK (actor IN ('system', 'user', 'operator')),
        CONSTRAINT ck_agent_evolution_events_type
            CHECK (length(trim(event_type)) > 0)
    )
    """,
)

_INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS ix_agent_evolution_events_occurred_at "
    "ON agent_evolution_events (occurred_at, id)",
    "CREATE INDEX IF NOT EXISTS ix_agent_evolution_events_type_occurred "
    "ON agent_evolution_events (event_type, occurred_at, id)",
)

_TRIGGER_STATEMENTS = (
    """
    CREATE TRIGGER IF NOT EXISTS trg_agent_evolution_events_no_update
    BEFORE UPDATE ON agent_evolution_events
    BEGIN
        SELECT RAISE(ABORT, 'agent_evolution_events are append-only');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_agent_evolution_events_no_delete
    BEFORE DELETE ON agent_evolution_events
    BEGIN
        SELECT RAISE(ABORT, 'agent_evolution_events are append-only');
    END
    """,
)

_DROP_STATEMENTS = (
    "DROP TRIGGER IF EXISTS trg_agent_evolution_events_no_delete",
    "DROP TRIGGER IF EXISTS trg_agent_evolution_events_no_update",
    "DROP INDEX IF EXISTS ix_agent_evolution_events_type_occurred",
    "DROP INDEX IF EXISTS ix_agent_evolution_events_occurred_at",
    "DROP TABLE IF EXISTS agent_evolution_events",
)


def upgrade(execution: MigrationExecution) -> None:
    """Create additive EvolutionEvent table, indexes, and append-only guards."""
    for statement in _TABLE_STATEMENTS:
        execution.exec_driver_sql(statement)
    for statement in _INDEX_STATEMENTS:
        execution.exec_driver_sql(statement)
    for statement in _TRIGGER_STATEMENTS:
        execution.exec_driver_sql(statement)


def downgrade(execution: MigrationExecution) -> None:
    """Drop only the EvolutionEvent table. Other agent tables are untouched."""
    for statement in _DROP_STATEMENTS:
        execution.exec_driver_sql(statement)


MIGRATION = Migration.from_source_file(
    id=MIGRATION_ID,
    description=DESCRIPTION,
    upgrade=upgrade,
    source_file=__file__,
)
