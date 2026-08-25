# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Focused SQLAlchemy table projection for append-only EvolutionEvents."""

from sqlalchemy import (
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

agent_evolution_events_table = Table(
    "agent_evolution_events",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("schema_version", String(32), nullable=False),
    Column("event_id", String(128), nullable=False, unique=True),
    Column("occurred_at", DateTime, nullable=False),
    Column("event_type", String(64), nullable=False),
    Column("actor", String(16), nullable=False),
    Column("reason_refs_json", Text, nullable=False),
    Column("before_json", Text, nullable=False),
    Column("after_json", Text, nullable=False),
    Column("created_at", DateTime, nullable=False),
    Index("ix_agent_evolution_events_occurred_at", "occurred_at", "id"),
    Index(
        "ix_agent_evolution_events_type_occurred",
        "event_type",
        "occurred_at",
        "id",
    ),
)
