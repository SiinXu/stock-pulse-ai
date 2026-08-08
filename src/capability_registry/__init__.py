# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Read-only Agent capability aggregation view (Issue #221 / T15)."""

from src.capability_registry.models import (
    KNOWN_UNAVAILABLE_REASON_CODES,
    REASON_FEATURE_DISABLED,
    REASON_MISSING_CONFIG,
    REASON_MISSING_DEPENDENCY,
    REASON_NOT_REGISTERED,
    REASON_PLUGIN_DISABLED,
    REASON_PLUGIN_FAILED,
    CapabilityDomain,
    CapabilityRecord,
)
from src.capability_registry.service import collect_capability_records

__all__ = (
    "CapabilityDomain",
    "CapabilityRecord",
    "KNOWN_UNAVAILABLE_REASON_CODES",
    "REASON_FEATURE_DISABLED",
    "REASON_MISSING_CONFIG",
    "REASON_MISSING_DEPENDENCY",
    "REASON_NOT_REGISTERED",
    "REASON_PLUGIN_DISABLED",
    "REASON_PLUGIN_FAILED",
    "collect_capability_records",
)
