# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Focused SQLAlchemy table projections for watchlist group repositories."""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
)

metadata = MetaData()

watchlist_groups_table = Table(
    "watchlist_groups",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("group_key", String(64), nullable=False),
    Column("name", String(128), nullable=False),
    Column("sort_order", Integer, nullable=False),
    Column("is_default", Boolean, nullable=False, default=False),
    Column("created_at", DateTime, nullable=False),
    Column("updated_at", DateTime, nullable=False),
)

watchlist_group_members_table = Table(
    "watchlist_group_members",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("group_id", Integer, nullable=False),
    Column("stock_code", String(32), nullable=False),
    Column("sort_order", Integer, nullable=False),
    Column("attrs_json", Text, nullable=False, default="{}"),
    Column("created_at", DateTime, nullable=False),
    Column("updated_at", DateTime, nullable=False),
)
