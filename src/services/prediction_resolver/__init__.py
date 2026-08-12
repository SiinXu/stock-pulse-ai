# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Automatic prediction horizon resolution (Issues #1102 / #1116, Epic #1107)."""

from __future__ import annotations

from src.services.prediction_resolver.memory_store import InMemoryPredictionStore
from src.services.prediction_resolver.ports import (
    ActualsFetcherPort,
    ClaimScorerPort,
    EvolutionEventSink,
    PredictionStorePort,
)
from src.services.prediction_resolver.resolver import (
    PREDICTION_RESOLVER_BACKGROUND_TASK_NAME,
    PREDICTION_RESOLVER_DEFAULT_INTERVAL_SECONDS,
    PredictionResolver,
    TickItemResult,
    TickSummary,
    build_prediction_resolver,
    build_prediction_resolver_background_tasks,
    derive_aggregate_label,
)

__all__ = [
    "ActualsFetcherPort",
    "ClaimScorerPort",
    "EvolutionEventSink",
    "InMemoryPredictionStore",
    "PREDICTION_RESOLVER_BACKGROUND_TASK_NAME",
    "PREDICTION_RESOLVER_DEFAULT_INTERVAL_SECONDS",
    "PredictionResolver",
    "PredictionStorePort",
    "TickItemResult",
    "TickSummary",
    "build_prediction_resolver",
    "build_prediction_resolver_background_tasks",
    "derive_aggregate_label",
]
