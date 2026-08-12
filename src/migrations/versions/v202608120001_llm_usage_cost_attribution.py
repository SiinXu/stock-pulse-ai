# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Backfill cost attribution and routing telemetry columns on llm_usage."""

from sqlalchemy.engine import Connection
from src.migrations.types import Migration

MIGRATION_ID = "202608120001_llm_usage_cost_attribution"
DESCRIPTION = "Backfill cost attribution and routing columns on llm_usage"
_ATTRIBUTION_COLUMNS = (
    ("run_id", "VARCHAR(64)"), ("stage", "VARCHAR(64)"), ("agent_mode", "VARCHAR(32)"),
    ("estimated_cost_usd", "FLOAT"), ("cost_status", "VARCHAR(32)"),
    ("route_outcome", "VARCHAR(32)"), ("route_attempt", "INTEGER"),
    ("primary_model", "VARCHAR(128)"), ("latency_ms", "INTEGER"), ("call_success", "INTEGER"),
)

def _llm_usage_columns(connection: Connection) -> set:
    rows = connection.exec_driver_sql("PRAGMA table_info(llm_usage)").fetchall()
    return {str(row[1]) for row in rows}

def upgrade(connection: Connection) -> None:
    existing = _llm_usage_columns(connection)
    if not existing:
        return
    for column, column_type in _ATTRIBUTION_COLUMNS:
        if column in existing:
            continue
        connection.exec_driver_sql(f"ALTER TABLE llm_usage ADD COLUMN {column} {column_type}")

MIGRATION = Migration.from_source_file(id=MIGRATION_ID, description=DESCRIPTION, upgrade=upgrade, source_file=__file__)
