# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Default provider-run diagnostic recorders for ``DataFetcherManager``.

Keeps ``data_provider.base`` free of a module-level import edge into
``src.services.run_diagnostics``. Construction of ``DataFetcherManager``
resolves these defaults so behavior stays identical while dependency
direction is inverted.
"""

from __future__ import annotations

from typing import Callable, Optional, Tuple

ProviderRunRecorder = Callable[..., None]
ProviderRunStartedRecorder = Callable[..., None]


def load_default_provider_run_recorders() -> Tuple[
    ProviderRunRecorder, ProviderRunStartedRecorder
]:
    """Import and return the production diagnostic recorder pair."""

    from src.services.run_diagnostics import (
        record_provider_run,
        record_provider_run_started,
    )

    return record_provider_run, record_provider_run_started


def resolve_provider_run_recorders(
    record_provider_run: Optional[ProviderRunRecorder] = None,
    record_provider_run_started: Optional[ProviderRunStartedRecorder] = None,
) -> Tuple[ProviderRunRecorder, ProviderRunStartedRecorder]:
    """Resolve construction-time recorders, defaulting to production wiring."""

    if record_provider_run is not None and record_provider_run_started is not None:
        return record_provider_run, record_provider_run_started

    default_run, default_started = load_default_provider_run_recorders()
    return (
        record_provider_run if record_provider_run is not None else default_run,
        (
            record_provider_run_started
            if record_provider_run_started is not None
            else default_started
        ),
    )
