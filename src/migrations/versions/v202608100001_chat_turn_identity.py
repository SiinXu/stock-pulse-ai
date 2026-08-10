# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Add durable identity and report context to Agent Chat user turns."""

from src.migrations.types import Migration, MigrationExecution


MIGRATION_ID = "202608100001_chat_turn_identity"
DESCRIPTION = "Add durable Agent Chat turn identity and context"


def upgrade(execution: MigrationExecution) -> None:
    """Add nullable compatibility columns and an idempotency index."""
    columns = {
        row[1]
        for row in execution.exec_driver_sql(
            "PRAGMA table_info(conversation_messages)"
        ).fetchall()
    }
    if "turn_id" not in columns:
        execution.exec_driver_sql(
            "ALTER TABLE conversation_messages ADD COLUMN turn_id VARCHAR(64)"
        )
    if "context_json" not in columns:
        execution.exec_driver_sql(
            "ALTER TABLE conversation_messages ADD COLUMN context_json TEXT"
        )
    execution.exec_driver_sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS "
        "uix_conversation_messages_session_turn "
        "ON conversation_messages (session_id, turn_id)"
    )


def downgrade(execution: MigrationExecution) -> None:
    """Drop the index; SQLite compatibility columns remain additive."""
    execution.exec_driver_sql(
        "DROP INDEX IF EXISTS uix_conversation_messages_session_turn"
    )


MIGRATION = Migration.from_source_file(
    id=MIGRATION_ID,
    description=DESCRIPTION,
    upgrade=upgrade,
    source_file=__file__,
)
