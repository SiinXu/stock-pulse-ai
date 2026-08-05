# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Facade and dependency-inversion guards for daily source health extraction."""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import MagicMock

from data_provider.base import DataFetcherManager


ROOT = Path(__file__).resolve().parents[2]
BASE_PATH = ROOT / "data_provider" / "base.py"


def test_base_module_has_no_module_level_run_diagnostics_import() -> None:
    tree = ast.parse(BASE_PATH.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "src.services.run_diagnostics":
            raise AssertionError(
                "data_provider.base must not import run_diagnostics at module level"
            )


def test_health_methods_remain_on_data_fetcher_manager_facade() -> None:
    required = (
        "_ensure_concurrency_guards",
        "_get_fetcher_call_lock",
        "_call_fetcher_method",
        "_daily_health_key",
        "_order_daily_fetchers",
        "_is_daily_source_available",
        "get_daily_source_health_snapshot",
        "get_daily_provider_health_report",
        "log_daily_provider_health_report",
        "reset_daily_source_health",
    )
    for name in required:
        assert callable(getattr(DataFetcherManager, name)), name


def test_construction_injects_provider_run_recorders() -> None:
    run_calls: list[dict] = []
    started_calls: list[dict] = []

    def run_recorder(**kwargs):
        run_calls.append(kwargs)

    def started_recorder(**kwargs):
        started_calls.append(kwargs)

    manager = DataFetcherManager(
        fetchers=[],
        provider_run_recorder=run_recorder,
        provider_run_started_recorder=started_recorder,
    )
    assert manager._provider_run_recorder is run_recorder
    assert manager._provider_run_started_recorder is started_recorder


def test_default_construction_wires_production_recorders() -> None:
    manager = DataFetcherManager(fetchers=[])
    assert callable(manager._provider_run_recorder)
    assert callable(manager._provider_run_started_recorder)
    assert manager._provider_run_recorder.__module__ == "src.services.run_diagnostics"
    assert (
        manager._provider_run_started_recorder.__module__
        == "src.services.run_diagnostics"
    )


def test_health_snapshot_and_reset_remain_process_local() -> None:
    DataFetcherManager.reset_daily_source_health()
    snapshot = DataFetcherManager.get_daily_source_health_snapshot()
    assert isinstance(snapshot, dict)
    unused = MagicMock()
    unused.name = "UnusedFetcher"
    unused.priority = 1
    manager = DataFetcherManager(fetchers=[unused])
    report = manager.get_daily_provider_health_report()
    assert report["schema_version"] == "provider_daily_health_v1"
    assert report["provider_count"] == 0
