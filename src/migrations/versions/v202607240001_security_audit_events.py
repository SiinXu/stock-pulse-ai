# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Create the append-only privileged-operation security audit table."""

from sqlalchemy.engine import Connection

from src.migrations.types import Migration


MIGRATION_ID = "202607240001_security_audit_events"
DESCRIPTION = "Create append-only privileged-operation security audit events"

_TABLE_DDL = (
    "CREATE TABLE IF NOT EXISTS security_audit_events ("
    "id INTEGER NOT NULL, "
    "schema_version VARCHAR(32) NOT NULL, "
    "occurred_at DATETIME NOT NULL, "
    "event_type VARCHAR(64) NOT NULL, "
    "phase VARCHAR(16) NOT NULL, "
    "actor_type VARCHAR(64) NOT NULL, "
    "actor_id VARCHAR(128) NOT NULL, "
    "execution_id VARCHAR(128) NOT NULL, "
    "action VARCHAR(64) NOT NULL, "
    "target_type VARCHAR(64) NOT NULL, "
    "target_id VARCHAR(128) NOT NULL, "
    "outcome VARCHAR(16) NOT NULL, "
    "reason_code VARCHAR(64) NOT NULL, "
    "correlation_id VARCHAR(64) NOT NULL, "
    "metadata_json TEXT NOT NULL, "
    "PRIMARY KEY (id)"
    ")"
)

_INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS ix_security_audit_events_occurred_at "
    "ON security_audit_events (occurred_at)",
    "CREATE INDEX IF NOT EXISTS ix_security_audit_events_event_type "
    "ON security_audit_events (event_type)",
    "CREATE INDEX IF NOT EXISTS ix_security_audit_events_phase "
    "ON security_audit_events (phase)",
    "CREATE INDEX IF NOT EXISTS ix_security_audit_events_execution_id "
    "ON security_audit_events (execution_id)",
    "CREATE INDEX IF NOT EXISTS ix_security_audit_events_action "
    "ON security_audit_events (action)",
    "CREATE INDEX IF NOT EXISTS ix_security_audit_events_outcome "
    "ON security_audit_events (outcome)",
    "CREATE INDEX IF NOT EXISTS ix_security_audit_events_correlation_id "
    "ON security_audit_events (correlation_id)",
    "CREATE INDEX IF NOT EXISTS ix_security_audit_event_time_id "
    "ON security_audit_events (occurred_at, id)",
    "CREATE INDEX IF NOT EXISTS ix_security_audit_correlation_phase "
    "ON security_audit_events (correlation_id, phase)",
)


def upgrade(connection: Connection) -> None:
    """Create the table and indexes without mutating existing audit rows."""
    connection.exec_driver_sql(_TABLE_DDL)
    for statement in _INDEX_STATEMENTS:
        connection.exec_driver_sql(statement)


MIGRATION = Migration.from_source_file(
    id=MIGRATION_ID,
    description=DESCRIPTION,
    upgrade=upgrade,
    source_file=__file__,
)
