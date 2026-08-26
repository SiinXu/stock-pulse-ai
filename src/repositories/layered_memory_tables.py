# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Focused SQLAlchemy table projections for layered memory persistence."""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
)


metadata = MetaData()

layered_memory_observations_table = Table(
    "layered_memory_observations",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("schema_version", String(32), nullable=False),
    Column("principal_id", String(128), nullable=False),
    Column("analysis_history_id", Integer, nullable=False),
    Column("stock_code", String(32), nullable=False),
    Column("observed_at", DateTime, nullable=False),
    Column("expires_at", DateTime),
    Column("signal", String(8), nullable=False),
    Column("sentiment_score", Float, nullable=False),
    Column("price_at_analysis", Float, nullable=False),
    Column("outcome_id", Integer),
    Column("outcome_horizon_days", Integer),
    Column("evaluated_at", DateTime),
    Column("was_correct", Boolean),
    Column("provenance_source", String(32), nullable=False),
    Column("actor_id", String(128)),
    Column("created_at", DateTime, nullable=False),
    Column("updated_at", DateTime, nullable=False),
    UniqueConstraint(
        "principal_id",
        "analysis_history_id",
        name="uix_layered_memory_observations_principal_history",
    ),
    Index(
        "ix_layered_memory_observations_principal_observed",
        "principal_id",
        "observed_at",
        "analysis_history_id",
    ),
    Index(
        "ix_layered_memory_observations_principal_expires",
        "principal_id",
        "expires_at",
    ),
    Index(
        "ix_layered_memory_observations_principal_stock",
        "principal_id",
        "stock_code",
        "observed_at",
    ),
)

layered_memory_consent_table = Table(
    "layered_memory_consent",
    metadata,
    Column("principal_id", String(128), primary_key=True),
    Column("granted_at", DateTime, nullable=False),
    Column("created_at", DateTime, nullable=False),
    Column("updated_at", DateTime, nullable=False),
)

layered_memory_access_audit_table = Table(
    "layered_memory_access_audit",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("event_id", String(64), nullable=False, unique=True),
    Column("principal_id", String(128), nullable=False),
    Column("action", String(32), nullable=False),
    Column("at", DateTime, nullable=False),
    Column("detail", String(200), nullable=False, default=""),
    Column("resource_count", Integer, nullable=False, default=0),
    Column("created_at", DateTime, nullable=False),
    Index(
        "ix_layered_memory_access_audit_principal_at",
        "principal_id",
        "at",
        "id",
    ),
)
