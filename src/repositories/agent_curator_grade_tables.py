# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Focused SQLAlchemy table projection for episode curator-grade sidecars."""

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    String,
    Table,
)


metadata = MetaData()

agent_episode_curator_grades_table = Table(
    "agent_episode_curator_grades",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("episode_id", String(128), nullable=False),
    Column("run_id", String(128), nullable=False),
    Column("manual_grade", String(16), nullable=False),
    Column("provenance_source", String(32)),
    Column("actor_id", String(128)),
    Column("created_at", DateTime, nullable=False),
    Column("updated_at", DateTime, nullable=False),
    Index(
        "uix_agent_episode_curator_grades_episode",
        "episode_id",
        unique=True,
    ),
    Index("ix_agent_episode_curator_grades_run_id", "run_id"),
)
