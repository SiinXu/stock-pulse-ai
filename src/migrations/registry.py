# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Explicit production migration registry."""

from __future__ import annotations

from typing import Tuple

from src.migrations.types import Migration, MigrationRegistryError, validate_registry
from src.migrations.versions.v20260605_create_all_baseline import (
    MIGRATION as LEGACY_BASELINE_MIGRATION,
)
from src.migrations.versions.v202607160001_migration_runner_registry import (
    MIGRATION as REGISTRY_METADATA_MIGRATION,
)
from src.migrations.versions.v202607190001_llm_usage_telemetry_columns import (
    MIGRATION as LLM_USAGE_TELEMETRY_MIGRATION,
)
from src.migrations.versions.v202607190002_decision_signal_profile_schema import (
    MIGRATION as DECISION_SIGNAL_PROFILE_MIGRATION,
)
from src.migrations.versions.v202607190003_portfolio_idempotency_scope_schema import (
    MIGRATION as PORTFOLIO_IDEMPOTENCY_SCOPE_MIGRATION,
)


MIGRATIONS: Tuple[Migration, ...] = validate_registry(
    (
        LEGACY_BASELINE_MIGRATION,
        REGISTRY_METADATA_MIGRATION,
        LLM_USAGE_TELEMETRY_MIGRATION,
        DECISION_SIGNAL_PROFILE_MIGRATION,
        PORTFOLIO_IDEMPOTENCY_SCOPE_MIGRATION,
    )
)

if not MIGRATIONS[0].is_legacy_baseline:
    raise MigrationRegistryError("legacy_baseline_not_first", MIGRATIONS[0].id)
if sum(migration.is_legacy_baseline for migration in MIGRATIONS) != 1:
    raise MigrationRegistryError("legacy_baseline_count_invalid")
if sum(migration.bootstraps_registry for migration in MIGRATIONS) != 1:
    raise MigrationRegistryError("registry_bootstrap_count_invalid")
if not all(migration.source_bound for migration in MIGRATIONS):
    raise MigrationRegistryError("production_checksum_source_unbound")

TARGET_VERSION = MIGRATIONS[-1].id


def get_migrations() -> Tuple[Migration, ...]:
    """Return the immutable registry in authored order."""
    return MIGRATIONS
