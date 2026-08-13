# -*- coding: utf-8 -*-
"""Smoke tests for offline key-path workloads (no wall-clock gate)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.perf.baseline import SCHEMA_VERSION, load_baseline
from src.perf.workloads import KEY_PATH_WORKLOADS, run_all_workloads, run_workload

pytestmark = [pytest.mark.unit]

BASELINE_PATH = Path(__file__).resolve().parent / "baselines" / "offline_key_paths.json"


def test_all_key_path_workloads_registered() -> None:
    assert set(KEY_PATH_WORKLOADS) == {
        "data_fetch_indicators",
        "analysis_trend",
        "report_generate",
    }


@pytest.mark.parametrize("name", sorted(KEY_PATH_WORKLOADS))
def test_workload_runs_offline(name: str) -> None:
    result = run_workload(name)
    assert result["name"] == name
    assert result["duration_ms"] >= 0.0
    assert result["iterations"] >= 1
    assert result["category"]
    assert result["notes"]


def test_run_all_workloads_produces_report_with_collector() -> None:
    report = run_all_workloads(collect=True)
    assert report["schema_version"] == SCHEMA_VERSION
    names = {item["name"] for item in report["workloads"]}
    assert names == set(KEY_PATH_WORKLOADS)
    assert report["collector"]["span_count"] >= len(KEY_PATH_WORKLOADS)


def test_committed_baseline_exists_and_covers_key_paths() -> None:
    assert BASELINE_PATH.is_file(), f"missing committed baseline: {BASELINE_PATH}"
    baseline = load_baseline(BASELINE_PATH)
    assert baseline.get("schema_version") == SCHEMA_VERSION
    names = {item["name"] for item in baseline.get("workloads") or []}
    assert names == set(KEY_PATH_WORKLOADS)
