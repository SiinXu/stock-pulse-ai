# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Optional stdlib cProfile helpers for local offline profiling."""

from __future__ import annotations

import cProfile
import pstats
from io import StringIO
from pathlib import Path
from typing import Callable, Optional, TypeVar

T = TypeVar("T")


def profile_callable(
    fn: Callable[[], T],
    *,
    stats_out: Optional[Path] = None,
    sort_by: str = "cumulative",
    limit: int = 40,
) -> tuple[T, str]:
    """Run ``fn`` under cProfile and return ``(result, text_stats)``."""
    profiler = cProfile.Profile()
    profiler.enable()
    try:
        result = fn()
    finally:
        profiler.disable()

    if stats_out is not None:
        stats_out.parent.mkdir(parents=True, exist_ok=True)
        profiler.dump_stats(str(stats_out))

    stream = StringIO()
    stats = pstats.Stats(profiler, stream=stream)
    stats.strip_dirs().sort_stats(sort_by).print_stats(limit)
    return result, stream.getvalue()


def run_with_optional_profile(
    fn: Callable[[], T],
    *,
    enabled: bool,
    stats_out: Optional[Path] = None,
) -> tuple[T, Optional[str]]:
    """Run ``fn`` with cProfile only when ``enabled`` is true."""
    if not enabled:
        return fn(), None
    return profile_callable(fn, stats_out=stats_out)
