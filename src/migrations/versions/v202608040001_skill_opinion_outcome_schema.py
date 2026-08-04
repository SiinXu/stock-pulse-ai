# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Create immutable skill-opinion samples and forward outcomes."""

from src.migrations.types import Migration, MigrationExecution


MIGRATION_ID = "202608040001_skill_opinion_outcome_schema"
DESCRIPTION = "Create skill opinion sample and outcome tables"

_TABLE_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS skill_opinion_samples (
        id INTEGER NOT NULL PRIMARY KEY,
        analysis_history_id INTEGER NOT NULL,
        stock_code VARCHAR(16) NOT NULL,
        skill_id VARCHAR(128) NOT NULL,
        skill_version VARCHAR(64),
        signal VARCHAR(16) NOT NULL,
        confidence FLOAT NOT NULL,
        horizon VARCHAR(16),
        data_quality_level VARCHAR(24),
        opinion_created_at DATETIME,
        sample_schema_version VARCHAR(32) NOT NULL,
        created_at DATETIME NOT NULL,
        CONSTRAINT uix_skill_opinion_sample_key
            UNIQUE (analysis_history_id, skill_id, sample_schema_version),
        CONSTRAINT ck_skill_opinion_sample_signal
            CHECK (signal IN ('strong_buy', 'buy', 'hold', 'sell', 'strong_sell')),
        CONSTRAINT ck_skill_opinion_sample_confidence
            CHECK (confidence >= 0.0 AND confidence <= 1.0),
        FOREIGN KEY(analysis_history_id)
            REFERENCES analysis_history (id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS skill_opinion_outcomes (
        id INTEGER NOT NULL PRIMARY KEY,
        skill_opinion_sample_id INTEGER NOT NULL,
        horizon VARCHAR(16) NOT NULL,
        engine_version VARCHAR(32) NOT NULL,
        eval_status VARCHAR(24) NOT NULL,
        outcome VARCHAR(16),
        direction_correct BOOLEAN,
        unable_reason VARCHAR(64),
        analysis_date DATE,
        start_trade_date DATE,
        end_trade_date DATE,
        start_price FLOAT,
        end_close FLOAT,
        stock_return_pct FLOAT,
        directional_return_pct FLOAT,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        CONSTRAINT uix_skill_opinion_outcome_key
            UNIQUE (skill_opinion_sample_id, horizon, engine_version),
        CONSTRAINT ck_skill_opinion_outcome_horizon
            CHECK (horizon IN ('1d', '3d', '5d', '10d')),
        CONSTRAINT ck_skill_opinion_outcome_eval_status
            CHECK (eval_status IN ('pending', 'evaluated', 'observational', 'unable')),
        CONSTRAINT ck_skill_opinion_outcome_value
            CHECK (outcome IS NULL OR outcome IN ('hit', 'miss', 'observational')),
        CONSTRAINT ck_skill_opinion_outcome_state_fields CHECK (
            (eval_status IN ('pending', 'unable')
                AND outcome IS NULL
                AND direction_correct IS NULL
                AND directional_return_pct IS NULL)
            OR (eval_status = 'observational'
                AND outcome = 'observational'
                AND direction_correct IS NULL
                AND directional_return_pct IS NULL)
            OR (eval_status = 'evaluated'
                AND outcome IN ('hit', 'miss')
                AND direction_correct IS NOT NULL
                AND directional_return_pct IS NOT NULL)
        ),
        FOREIGN KEY(skill_opinion_sample_id)
            REFERENCES skill_opinion_samples (id) ON DELETE CASCADE
    )
    """,
)

_INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS ix_skill_opinion_samples_history_id "
    "ON skill_opinion_samples (analysis_history_id)",
    "CREATE INDEX IF NOT EXISTS ix_skill_opinion_samples_stock_code "
    "ON skill_opinion_samples (stock_code)",
    "CREATE INDEX IF NOT EXISTS ix_skill_opinion_samples_skill_id "
    "ON skill_opinion_samples (skill_id)",
    "CREATE INDEX IF NOT EXISTS ix_skill_opinion_sample_skill_horizon_created "
    "ON skill_opinion_samples (skill_id, horizon, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_skill_opinion_sample_stock_created "
    "ON skill_opinion_samples (stock_code, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_skill_opinion_outcomes_sample_id "
    "ON skill_opinion_outcomes (skill_opinion_sample_id)",
    "CREATE INDEX IF NOT EXISTS ix_skill_opinion_outcomes_horizon "
    "ON skill_opinion_outcomes (horizon)",
    "CREATE INDEX IF NOT EXISTS ix_skill_opinion_outcomes_engine_version "
    "ON skill_opinion_outcomes (engine_version)",
    "CREATE INDEX IF NOT EXISTS ix_skill_opinion_outcomes_eval_status "
    "ON skill_opinion_outcomes (eval_status)",
    "CREATE INDEX IF NOT EXISTS ix_skill_opinion_outcomes_unable_reason "
    "ON skill_opinion_outcomes (unable_reason)",
    "CREATE INDEX IF NOT EXISTS ix_skill_opinion_outcome_candidate "
    "ON skill_opinion_outcomes (engine_version, eval_status, updated_at)",
    "CREATE INDEX IF NOT EXISTS ix_skill_opinion_outcome_horizon_status "
    "ON skill_opinion_outcomes (engine_version, horizon, eval_status)",
)

_TRIGGER_STATEMENTS = (
    """
    CREATE TRIGGER IF NOT EXISTS trg_skill_opinion_history_delete
    AFTER DELETE ON analysis_history
    BEGIN
        DELETE FROM skill_opinion_outcomes
        WHERE skill_opinion_sample_id IN (
            SELECT id FROM skill_opinion_samples
            WHERE analysis_history_id = OLD.id
        );
        DELETE FROM skill_opinion_samples
        WHERE analysis_history_id = OLD.id;
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_skill_opinion_sample_delete
    AFTER DELETE ON skill_opinion_samples
    BEGIN
        DELETE FROM skill_opinion_outcomes
        WHERE skill_opinion_sample_id = OLD.id;
    END
    """,
)


def upgrade(execution: MigrationExecution) -> None:
    """Create the additive schema and idempotent cleanup triggers."""
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
