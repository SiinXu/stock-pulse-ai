# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Focused SQLAlchemy table projection for episode forward-return sidecars."""

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

agent_episode_forward_returns_table = Table(
    "agent_episode_forward_returns",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("episode_id", String(128), nullable=False),
    Column("run_id", String(128), nullable=False),
    Column("horizon", String(8), nullable=False),
    Column("forward_return_bucket", String(16), nullable=False),
    Column("provenance_source", String(32)),
    Column("actor_id", String(128)),
    Column("created_at", DateTime, nullable=False),
    Column("updated_at", DateTime, nullable=False),
    Index(
        "uix_agent_episode_forward_returns_episode_horizon",
        "episode_id",
        "horizon",
        unique=True,
    ),
    Index("ix_agent_episode_forward_returns_run_id", "run_id"),
    Index("ix_agent_episode_forward_returns_episode_id", "episode_id"),
)
