# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Performance baseline collection and offline profiling (Issue #227).

Default-off span collection for key paths (data fetch, analysis, report
generation) plus offline workloads and baseline compare helpers.

When collection is disabled (the default), :func:`perf_span` is a no-op
early return so production paths pay essentially zero overhead.
"""

from __future__ import annotations

from src.perf.baseline import (
    SCHEMA_VERSION,
    compare_to_baseline,
    load_baseline,
    render_markdown_report,
    write_baseline,
)
from src.perf.collector import (
    PerfCollector,
    PerfSpan,
    activate_collector,
    clear_enabled_cache,
    get_current_collector,
    is_perf_collection_enabled,
    is_perf_profile_enabled,
    perf_span,
    record_span,
    reset_collector,
    set_collection_enabled_override,
)
from src.perf.profiler import profile_callable, run_with_optional_profile
from src.perf.workloads import (
    KEY_PATH_WORKLOADS,
    run_all_workloads,
    run_workload,
)

__all__ = [
    "SCHEMA_VERSION",
    "KEY_PATH_WORKLOADS",
    "PerfCollector",
    "PerfSpan",
    "activate_collector",
    "clear_enabled_cache",
    "compare_to_baseline",
    "get_current_collector",
    "is_perf_collection_enabled",
    "is_perf_profile_enabled",
    "load_baseline",
    "perf_span",
    "profile_callable",
    "record_span",
    "render_markdown_report",
    "reset_collector",
    "run_all_workloads",
    "run_with_optional_profile",
    "run_workload",
    "set_collection_enabled_override",
    "write_baseline",
]
