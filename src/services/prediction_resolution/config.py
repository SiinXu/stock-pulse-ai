# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Concurrency and backpressure caps for prediction batch resolution.

Environment variables (documented in ``.env.example`` and
``docs/agent-prediction-resolution.md``). Feature-flag registry ownership stays
with Issue #1115; this module only parses operational caps so the batch layer
can run offline tests without the full Settings surface.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional


def _env_int(
    name: str,
    default: int,
    *,
    minimum: int = 0,
    maximum: Optional[int] = None,
    source: Optional[Mapping[str, str]] = None,
) -> int:
    raw = (source or os.environ).get(name)
    if raw is None or str(raw).strip() == "":
        value = default
    else:
        try:
            value = int(str(raw).strip())
        except ValueError:
            value = default
    if value < minimum:
        value = minimum
    if maximum is not None and value > maximum:
        value = maximum
    return value


def _env_float(
    name: str,
    default: float,
    *,
    minimum: float = 0.0,
    maximum: Optional[float] = None,
    source: Optional[Mapping[str, str]] = None,
) -> float:
    raw = (source or os.environ).get(name)
    if raw is None or str(raw).strip() == "":
        value = default
    else:
        try:
            value = float(str(raw).strip())
        except ValueError:
            value = default
    if value < minimum:
        value = minimum
    if maximum is not None and value > maximum:
        value = maximum
    return value


def _env_bool(
    name: str,
    default: bool,
    *,
    source: Optional[Mapping[str, str]] = None,
) -> bool:
    raw = (source or os.environ).get(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class PredictionResolveConfig:
    """Operational caps for one resolve tick and its worker pools."""

    # Master switch for scheduler wiring (A7). Batch API itself is always callable.
    enabled: bool = False
    # Backpressure: hard cap on rows claimed per tick.
    max_per_tick: int = 50
    # Data-fetch pool concurrency (global). Per-provider caps can layer later.
    fetch_concurrency: int = 4
    # Separate, smaller pool for expensive LLM post-mortems.
    postmortem_concurrency: int = 1
    # Max post-mortem enqueues accepted per tick (unbounded LLM stampede guard).
    postmortem_max_per_tick: int = 10
    # Lease length so multi-worker / crash recovery can reclaim stale resolving rows.
    lease_seconds: int = 120
    # Bounded retry for data_unavailable / provider_down.
    max_attempts: int = 5
    retry_base_seconds: float = 30.0
    retry_max_seconds: float = 3600.0
    retry_jitter_ratio: float = 0.1
    # Circuit breaker: after this many provider errors in a tick window, shrink claim size.
    provider_error_circuit_threshold: int = 5
    provider_error_circuit_cooldown_seconds: float = 60.0
    # When circuit is open, claim at most this many rows per tick.
    circuit_open_max_per_tick: int = 5

    def effective_claim_limit(self, *, circuit_open: bool) -> int:
        if circuit_open:
            return max(0, min(self.max_per_tick, self.circuit_open_max_per_tick))
        return max(0, self.max_per_tick)


def load_prediction_resolve_config(
    source: Optional[Mapping[str, str]] = None,
) -> PredictionResolveConfig:
    """Load caps from environment (or an injected mapping for tests)."""
    return PredictionResolveConfig(
        enabled=_env_bool("PREDICTION_RESOLVE_ENABLED", False, source=source),
        max_per_tick=_env_int(
            "PREDICTION_RESOLVE_MAX_PER_TICK",
            50,
            minimum=0,
            maximum=10_000,
            source=source,
        ),
        fetch_concurrency=_env_int(
            "PREDICTION_RESOLVE_FETCH_CONCURRENCY",
            4,
            minimum=1,
            maximum=64,
            source=source,
        ),
        postmortem_concurrency=_env_int(
            "PREDICTION_RESOLVE_POSTMORTEM_CONCURRENCY",
            1,
            minimum=1,
            maximum=16,
            source=source,
        ),
        postmortem_max_per_tick=_env_int(
            "PREDICTION_RESOLVE_POSTMORTEM_MAX_PER_TICK",
            10,
            minimum=0,
            maximum=10_000,
            source=source,
        ),
        lease_seconds=_env_int(
            "PREDICTION_RESOLVE_LEASE_SECONDS",
            120,
            minimum=5,
            maximum=86_400,
            source=source,
        ),
        max_attempts=_env_int(
            "PREDICTION_RESOLVE_MAX_ATTEMPTS",
            5,
            minimum=1,
            maximum=100,
            source=source,
        ),
        retry_base_seconds=_env_float(
            "PREDICTION_RESOLVE_RETRY_BASE_SECONDS",
            30.0,
            minimum=1.0,
            maximum=86_400.0,
            source=source,
        ),
        retry_max_seconds=_env_float(
            "PREDICTION_RESOLVE_RETRY_MAX_SECONDS",
            3600.0,
            minimum=1.0,
            maximum=604_800.0,
            source=source,
        ),
        retry_jitter_ratio=_env_float(
            "PREDICTION_RESOLVE_RETRY_JITTER_RATIO",
            0.1,
            minimum=0.0,
            maximum=1.0,
            source=source,
        ),
        provider_error_circuit_threshold=_env_int(
            "PREDICTION_RESOLVE_PROVIDER_ERROR_CIRCUIT_THRESHOLD",
            5,
            minimum=1,
            maximum=10_000,
            source=source,
        ),
        provider_error_circuit_cooldown_seconds=_env_float(
            "PREDICTION_RESOLVE_PROVIDER_ERROR_CIRCUIT_COOLDOWN_SECONDS",
            60.0,
            minimum=1.0,
            maximum=86_400.0,
            source=source,
        ),
        circuit_open_max_per_tick=_env_int(
            "PREDICTION_RESOLVE_CIRCUIT_OPEN_MAX_PER_TICK",
            5,
            minimum=0,
            maximum=10_000,
            source=source,
        ),
    )
