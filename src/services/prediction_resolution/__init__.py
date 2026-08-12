# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Batch and parallel prediction resolution (queues, leases, backpressure).

This package implements Issue #1104 (A8 of Epic #1107): claim due predictions
with leases, coalesce actuals fetches by (symbol, market, as_of), apply
concurrency caps, and keep scoring idempotent under multi-worker races.

Upstream contract / store / fetcher / scorer implementations (A1–A5) plug in
through the Protocols defined in ``contracts``. Until those land, tests and
single-process dry-runs use ``InMemoryPredictionWorkStore``.
"""

from __future__ import annotations

from src.services.prediction_resolution.batch_resolver import (
    PredictionBatchResolver,
    TickResult,
)
from src.services.prediction_resolution.coalesce import (
    CoalesceGroup,
    coalesce_key,
    group_by_actuals_key,
)
from src.services.prediction_resolution.config import (
    PredictionResolveConfig,
    load_prediction_resolve_config,
)
from src.services.prediction_resolution.contracts import (
    ActualsSnapshot,
    ClaimScoreResult,
    DataUnavailable,
    OutcomeLabel,
    PredictionWorkItem,
    PredictionWorkStore,
    ActualsFetcherPort,
    ClaimScorerPort,
    PostmortemQueuePort,
    ResolveOutcome,
)
from src.services.prediction_resolution.lease_store import InMemoryPredictionWorkStore
from src.services.prediction_resolution.metrics import (
    PredictionResolveMetrics,
    PredictionResolveMetricsSnapshot,
)
from src.services.prediction_resolution.postmortem_queue import InMemoryPostmortemQueue

__all__ = [
    "ActualsFetcherPort",
    "ActualsSnapshot",
    "ClaimScoreResult",
    "ClaimScorerPort",
    "CoalesceGroup",
    "DataUnavailable",
    "InMemoryPostmortemQueue",
    "InMemoryPredictionWorkStore",
    "OutcomeLabel",
    "PostmortemQueuePort",
    "PredictionBatchResolver",
    "PredictionResolveConfig",
    "PredictionResolveMetrics",
    "PredictionResolveMetricsSnapshot",
    "PredictionWorkItem",
    "PredictionWorkStore",
    "ResolveOutcome",
    "TickResult",
    "coalesce_key",
    "group_by_actuals_key",
    "load_prediction_resolve_config",
]
