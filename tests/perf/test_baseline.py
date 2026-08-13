# -*- coding: utf-8 -*-
"""Unit tests for baseline compare / write helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.perf.baseline import (
    SCHEMA_VERSION,
    compare_to_baseline,
    load_baseline,
    render_markdown_report,
    write_baseline,
)

pytestmark = [pytest.mark.unit]


def _report(*items):
    return {"schema_version": SCHEMA_VERSION, "workloads": list(items)}


def test_compare_detects_regression() -> None:
    baseline = _report(
        {"name": "analysis_trend", "duration_ms": 100.0},
        {"name": "report_generate", "duration_ms": 50.0},
    )
    current = _report(
        {"name": "analysis_trend", "duration_ms": 400.0},
        {"name": "report_generate", "duration_ms": 55.0},
    )
    result = compare_to_baseline(current, baseline, regression_ratio=2.5)
    assert result["ok"] is False
    assert result["regressed"] == ["analysis_trend"]


def test_compare_ok_within_threshold() -> None:
    baseline = _report({"name": "data_fetch_indicators", "duration_ms": 100.0})
    current = _report({"name": "data_fetch_indicators", "duration_ms": 200.0})
    result = compare_to_baseline(current, baseline, regression_ratio=2.5)
    assert result["ok"] is True


def test_compare_reports_new_and_missing() -> None:
    baseline = _report({"name": "old_only", "duration_ms": 10.0})
    current = _report({"name": "new_only", "duration_ms": 12.0})
    result = compare_to_baseline(current, baseline)
    by_name = {row["name"]: row for row in result["comparisons"]}
    assert by_name["old_only"]["status"] == "missing"
    assert by_name["new_only"]["status"] == "new"


def test_write_and_load_baseline_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    report = _report(
        {
            "name": "analysis_trend",
            "category": "analysis_run",
            "iterations": 8,
            "duration_ms": 12.3456,
            "ops_per_sec": 100.5,
            "notes": "unit",
        }
    )
    write_baseline(path, report)
    loaded = load_baseline(path)
    assert loaded["schema_version"] == SCHEMA_VERSION
    assert loaded["workloads"][0]["duration_ms"] == 12.346


def test_render_markdown_includes_comparison() -> None:
    report = _report({"name": "analysis_trend", "duration_ms": 10.0, "category": "a"})
    comparison = compare_to_baseline(report, report)
    md = render_markdown_report(report, comparison=comparison)
    assert "analysis_trend" in md
    assert "Baseline comparison" in md
