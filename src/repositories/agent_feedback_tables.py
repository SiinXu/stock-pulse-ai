# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Focused SQLAlchemy table projections for optional agent feedback sidecars."""

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
)


metadata = MetaData()

agent_run_feedback_table = Table(
    "agent_run_feedback",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", String(128), nullable=False, unique=True),
    Column("feedback_value", String(16), nullable=False),
    Column("note", Text),
    Column("source", String(16), nullable=False, default="api"),
    Column("provenance_source", String(32)),
    Column("actor_id", String(128)),
    Column("created_at", DateTime, nullable=False),
    Column("updated_at", DateTime, nullable=False),
)

agent_prediction_feedback_table = Table(
    "agent_prediction_feedback",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("prediction_id", String(128), nullable=False, unique=True),
    Column("run_id", String(128), nullable=False),
    Column("feedback_value", String(16), nullable=False),
    Column("note", Text),
    Column("source", String(16), nullable=False, default="api"),
    Column("provenance_source", String(32)),
    Column("actor_id", String(128)),
    Column("created_at", DateTime, nullable=False),
    Column("updated_at", DateTime, nullable=False),
)
