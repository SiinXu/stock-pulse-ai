# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Focused SQLAlchemy table projections for agent prediction persistence."""

from sqlalchemy import (
    Column,
    Date,
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
    # Widths align with A1 PredictionRecord (prediction_id/run_id max_length=128).
    Column("prediction_id", String(128), primary_key=True),
    Column("run_id", String(128), nullable=False),
    Column("symbol", String(32), nullable=False),
    Column("market", String(16), nullable=False),
    Column("as_of", Date, nullable=False),
    Column("horizon", String(32), nullable=False),
    Column("resolve_after", DateTime, nullable=False),
    Column("status", String(32), nullable=False),
    Column("lease_owner", String(128)),
    Column("lease_token", String(64)),
    Column("lease_expires_at", DateTime),
    Column("claims_json", Text, nullable=False),
    Column("outcome_json", Text),
    Column("model_meta_json", Text),
    Column("source_decision_id", String(128)),
    Column("no_verifiable_reason", String(64)),
    Column("notes", String(500)),
    Column("provenance_source", String(32)),
    Column("actor_id", String(128)),
    Column("attempts", Integer, nullable=False, default=0),
    Column("created_at", DateTime, nullable=False),
    Column("updated_at", DateTime, nullable=False),
    Column("resolved_at", DateTime),
)
