# -*- coding: utf-8 -*-
"""Wall-clock baseline regression (excluded from default offline CI gate)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.perf.baseline import compare_to_baseline, load_baseline
from src.perf.workloads import run_all_workloads

pytestmark = [pytest.mark.benchmark]

BASELINE_PATH = Path(__file__).resolve().parent / "baselines" / "offline_key_paths.json"


def test_offline_key_paths_within_baseline_ratio() -> None:
    baseline = load_baseline(BASELINE_PATH)
    report = run_all_workloads(collect=False)
    comparison = compare_to_baseline(report, baseline, regression_ratio=2.5)
    assert comparison["ok"], (
        "key-path duration exceeded baseline * 2.5: "
        f"{comparison.get('regressed')}; details={comparison.get('comparisons')}"
    )
