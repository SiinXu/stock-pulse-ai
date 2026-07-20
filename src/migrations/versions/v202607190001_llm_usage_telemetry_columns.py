# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Backfill nullable LLM usage telemetry columns on legacy llm_usage tables."""

from sqlalchemy.engine import Connection

from src.migrations.types import Migration


MIGRATION_ID = "202607190001_llm_usage_telemetry_columns"
DESCRIPTION = "Backfill nullable telemetry columns on legacy llm_usage tables"

# Ordered (column, affinity) pairs reproduce the nullable telemetry columns the
# LLMUsage model declares. Databases created before P0a telemetry keep the old
# llm_usage shape and need these columns added; fresh databases already receive
# them through metadata create_all, so this migration is a no-op there. The list
# is embedded rather than imported from storage so the migration stays
# self-contained and its checksum only changes when this file changes.
_TELEMETRY_COLUMNS = (
    ("provider_usage_json", "TEXT"),
    ("provider", "VARCHAR(64)"),
    ("provider_usage_schema_name", "VARCHAR(64)"),
    ("provider_usage_schema_version", "VARCHAR(32)"),
    ("provider_usage_observed_at", "VARCHAR(32)"),
    ("normalized_prompt_tokens", "INTEGER"),
    ("normalized_completion_tokens", "INTEGER"),
    ("normalized_total_tokens", "INTEGER"),
    ("normalized_cache_read_tokens", "INTEGER"),
    ("normalized_cache_write_tokens", "INTEGER"),
    ("normalized_cache_miss_tokens", "INTEGER"),
    ("normalized_uncached_input_tokens", "INTEGER"),
    ("normalized_cache_eligible_input_tokens", "INTEGER"),
    ("normalized_cache_hit_ratio", "FLOAT"),
    ("normalized_cache_write_ratio", "FLOAT"),
    ("cache_capability", "VARCHAR(32)"),
    ("cache_eligibility", "VARCHAR(32)"),
    ("cache_observation", "VARCHAR(32)"),
    ("estimated_prefix_tokens", "INTEGER"),
    ("provider_reported_prompt_tokens", "INTEGER"),
    ("provider_reported_cached_tokens", "INTEGER"),
    ("provider_min_cache_tokens", "INTEGER"),
    ("eligibility_confidence", "VARCHAR(32)"),
    ("tokenizer_name", "VARCHAR(128)"),
    ("tokenizer_version", "VARCHAR(64)"),
    ("messages_hmac", "VARCHAR(64)"),
    ("system_message_hmac", "VARCHAR(64)"),
    ("user_message_hmac", "VARCHAR(64)"),
    ("hmac_key_version", "VARCHAR(64)"),
    ("hmac_domain", "VARCHAR(32)"),
    ("hash_scope", "VARCHAR(32)"),
    ("language", "VARCHAR(16)"),
    ("market_group", "VARCHAR(16)"),
    ("analysis_mode", "VARCHAR(64)"),
    ("legacy_prompt_mode", "VARCHAR(32)"),
    ("skill_config_hmac", "VARCHAR(64)"),
    ("transport", "VARCHAR(64)"),
    ("message_count", "INTEGER"),
    ("estimated_total_prompt_tokens", "INTEGER"),
    ("approx_common_prefix_chars", "INTEGER"),
    ("approx_common_prefix_tokens", "INTEGER"),
    ("known_dynamic_marker_positions", "TEXT"),
)


def _llm_usage_columns(connection: Connection) -> set:
    """Return the current column names of the llm_usage table, if it exists."""
    rows = connection.exec_driver_sql("PRAGMA table_info(llm_usage)").fetchall()
    return {str(row[1]) for row in rows}


def upgrade(connection: Connection) -> None:
    """Add every missing nullable telemetry column to a legacy llm_usage table.

    The column and affinity literals are authored constants, never external
    input, so composing the ALTER statement with them is safe. Adding a column
    only when it is absent keeps the migration idempotent under the runner's
    serialized re-execution.
    """
    existing = _llm_usage_columns(connection)
    if not existing:
        # No llm_usage table to upgrade. Fresh databases create it with every
        # column through metadata create_all before the runner executes.
        return
    for column, column_type in _TELEMETRY_COLUMNS:
        if column in existing:
            continue
        connection.exec_driver_sql(
            f"ALTER TABLE llm_usage ADD COLUMN {column} {column_type}"
        )


MIGRATION = Migration.from_source_file(
    id=MIGRATION_ID,
    description=DESCRIPTION,
    upgrade=upgrade,
    source_file=__file__,
)
