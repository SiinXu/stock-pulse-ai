# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Owner-driven, read-only capability inventory foundation."""

from src.capability_registry.models import (
    CAPABILITY_SCHEMA_VERSION,
    CapabilityDomain,
    CapabilityRecord,
    CapabilitySnapshot,
    CapabilityType,
    SourceState,
    SourceStatus,
)
from src.capability_registry.service import collect_capability_records

__all__ = (
    "CapabilityDomain",
    "CapabilityRecord",
    "CapabilitySnapshot",
    "CapabilityType",
    "CAPABILITY_SCHEMA_VERSION",
    "SourceState",
    "SourceStatus",
    "collect_capability_records",
)
