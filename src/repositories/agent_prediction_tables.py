# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Focused SQLAlchemy table projections for agent prediction persistence."""

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

agent_predictions_table = Table(
    "agent_predictions",
    metadata,
    Column("prediction_id", String(64), primary_key=True),
    Column("run_id", String(64), nullable=False),
    Column("symbol", String(32), nullable=False),
    Column("market", String(16), nullable=False),
    Column("horizon", String(32), nullable=False),
    Column("resolve_after", DateTime, nullable=False),
    Column("status", String(32), nullable=False),
    Column("lease_owner", String(128)),
    Column("lease_token", String(64)),
    Column("lease_expires_at", DateTime),
    Column("claims_json", Text, nullable=False),
    Column("outcome_json", Text),
    Column("model_meta_json", Text),
    Column("attempts", Integer, nullable=False, default=0),
    Column("created_at", DateTime, nullable=False),
    Column("updated_at", DateTime, nullable=False),
    Column("resolved_at", DateTime),
)
