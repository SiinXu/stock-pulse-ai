# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Focused SQLAlchemy table projection for agent evolution episodes."""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
)


metadata = MetaData()

agent_episodes_table = Table(
    "agent_episodes",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("schema_version", String(32), nullable=False),
    Column("episode_id", String(128), nullable=False, unique=True),
    Column("run_id", String(128), nullable=False),
    Column("mode", String(32), nullable=False),
    Column("symbol", String(32)),
    Column("market", String(16)),
    Column("started_at", DateTime),
    Column("completed_at", DateTime),
    Column("success", Boolean),
    Column("soul_version", String(64)),
    Column("soul_hash", String(128)),
    Column("trajectory_summary_json", Text, nullable=False, default="[]"),
    Column("lessons_json", Text, nullable=False, default="[]"),
    Column("outcome_labels_json", Text),
    Column("created_at", DateTime, nullable=False),
    Index("ix_agent_episodes_run_id", "run_id"),
    Index("ix_agent_episodes_symbol_created", "symbol", "created_at"),
    Index("ix_agent_episodes_created_at", "created_at"),
    Index("ix_agent_episodes_mode_created", "mode", "created_at"),
)
