# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Capability inventory (read) and write-side control plane foundation."""

from src.capability_registry.models import (
    CAPABILITY_SCHEMA_VERSION,
    CapabilityDomain,
    CapabilityRecord,
    CapabilitySnapshot,
    CapabilityType,
    SourceState,
    SourceStatus,
)
from src.capability_registry.resolution import (
    CapabilityResolutionError,
    detect_dependency_cycle,
    resolve_capability_dependencies,
    resolve_many,
)
from src.capability_registry.service import collect_capability_records
from src.capability_registry.task_routing import (
    decision_for_diagnostics,
    resolve_task_model_route,
)
from src.capability_registry.write_models import (
    WRITE_SCHEMA_VERSION,
    DependencyIssue,
    ResolutionResult,
    RouteCandidate,
    TaskRouteDecision,
    WriteCapabilityEntry,
    WriteRegistrySnapshot,
)
from src.capability_registry.write_service import (
    CapabilityWriteError,
    CapabilityWriteService,
    get_capability_write_service,
)

__all__ = (
    "CapabilityDomain",
    "CapabilityRecord",
    "CapabilityResolutionError",
    "CapabilitySnapshot",
    "CapabilityType",
    "CapabilityWriteError",
    "CapabilityWriteService",
    "CAPABILITY_SCHEMA_VERSION",
    "DependencyIssue",
    "ResolutionResult",
    "RouteCandidate",
    "SourceState",
    "SourceStatus",
    "TaskRouteDecision",
    "WRITE_SCHEMA_VERSION",
    "WriteCapabilityEntry",
    "WriteRegistrySnapshot",
    "collect_capability_records",
    "decision_for_diagnostics",
    "detect_dependency_cycle",
    "get_capability_write_service",
    "resolve_capability_dependencies",
    "resolve_many",
    "resolve_task_model_route",
)
