# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Focused SQLAlchemy table projections for skill-opinion repositories."""

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
)


metadata = MetaData()

analysis_history_table = Table(
    "analysis_history",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("code", String(10), nullable=False),
    Column("raw_result", Text),
    Column("context_snapshot", Text),
    Column("created_at", DateTime),
)

stock_daily_table = Table(
    "stock_daily",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("code", String(10), nullable=False),
    Column("date", Date, nullable=False),
    Column("close", Float),
)

skill_opinion_sample_table = Table(
    "skill_opinion_samples",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("analysis_history_id", Integer, nullable=False),
    Column("stock_code", String(16), nullable=False),
    Column("skill_id", String(128), nullable=False),
    Column("skill_version", String(64)),
    Column("signal", String(16), nullable=False),
    Column("confidence", Float, nullable=False),
    Column("horizon", String(16)),
    Column("data_quality_level", String(24)),
    Column("opinion_created_at", DateTime),
    Column("sample_schema_version", String(32), nullable=False),
    Column("created_at", DateTime, nullable=False),
)

skill_opinion_outcome_table = Table(
    "skill_opinion_outcomes",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("skill_opinion_sample_id", Integer, nullable=False),
    Column("horizon", String(16), nullable=False),
    Column("engine_version", String(32), nullable=False),
    Column("eval_status", String(24), nullable=False),
    Column("outcome", String(16)),
    Column("direction_correct", Boolean),
    Column("unable_reason", String(64)),
    Column("analysis_date", Date),
    Column("start_trade_date", Date),
    Column("end_trade_date", Date),
    Column("start_price", Float),
    Column("end_close", Float),
    Column("stock_return_pct", Float),
    Column("directional_return_pct", Float),
    Column("created_at", DateTime, nullable=False),
    Column("updated_at", DateTime, nullable=False),
)
