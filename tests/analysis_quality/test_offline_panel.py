# -*- coding: utf-8 -*-
"""Offline fixed-panel analysis quality benchmark tests (#617 Phase A).

All cases are synthetic fixtures. No network and no live LLM calls.
"""

from __future__ import annotations

import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from tests.analysis_quality.assertions import (  # noqa: E402
    assert_no_traceback_leakage,
    assert_numeric_consistency,
    evaluate_case,
    invent_price_contradiction,
)
from tests.analysis_quality.panel_loader import (  # noqa: E402
    FIXTURE_ROOT,
    MANIFEST_PATH,
    iter_panel_cases,
    list_panel_case_ids,
    load_manifest,
)


pytestmark = [
    pytest.mark.unit,
    pytest.mark.quality_benchmark,
]


def test_manifest_declares_small_fixed_panel() -> None:
    manifest = load_manifest()
    assert manifest.get("schema_version") == "analysis-quality-panel-v1"
    case_ids = list_panel_case_ids()
    assert 3 <= len(case_ids) <= 5
    assert case_ids == [entry["id"] for entry in manifest["cases"]]
    for entry in manifest["cases"]:
        path = FIXTURE_ROOT / entry["file"]
        assert path.is_file(), f"missing fixture file: {path}"
    assert MANIFEST_PATH.is_file()


@pytest.mark.parametrize("case_id", list_panel_case_ids())
def test_panel_case_passes_offline_quality_assertions(case_id: str) -> None:
    case = next(case for case in iter_panel_cases() if case["id"] == case_id)
    evaluate_case(case)


def test_numeric_contradiction_is_detected() -> None:
    case = next(iter_panel_cases())
    corrupted = invent_price_contradiction(
        case,
        path="dashboard.data_perspective.price_position.current_price",
        bogus_value=999999.0,
    )
    with pytest.raises(AssertionError, match="numeric contradiction"):
        evaluate_case(corrupted)


def test_missing_gap_marker_is_detected() -> None:
    case = next(case for case in iter_panel_cases() if case["id"] == "us-missing-fundamentals")
    mutated = copy.deepcopy(case)
    mutated["report"]["risk_warning"] = "Not investment advice."
    mutated["report"]["data_sources"] = (
        "market_data@2026-07-01T16:00:00-04:00; news@2026-07-01T12:00:00-04:00"
    )
    mutated["report"]["fundamental_analysis"] = "Strong balance sheet (invented)"
    mutated["report"]["dashboard"]["intelligence"]["risk_alerts"] = ["generic caution"]
    mutated["report"]["dashboard"]["intelligence"]["earnings_outlook"] = "stable"
    mutated["report"]["analysis_summary"] = "Technicals only; no gap language."
    with pytest.raises(AssertionError, match="required gap marker"):
        evaluate_case(mutated)


def test_traceback_leakage_is_detected() -> None:
    with pytest.raises(AssertionError, match="traceback/exception leakage"):
        assert_no_traceback_leakage(
            {"analysis_summary": 'Traceback (most recent call last):\n  File "x.py", line 1'},
            case_id="synthetic",
        )


def test_assert_numeric_consistency_direct() -> None:
    report = {
        "dashboard": {
            "data_perspective": {
                "price_position": {"current_price": 10.0},
            }
        }
    }
    assert_numeric_consistency(
        report,
        {"dashboard.data_perspective.price_position.current_price": 10.0},
        case_id="direct",
    )
    with pytest.raises(AssertionError, match="numeric contradiction"):
        assert_numeric_consistency(
            report,
            {"dashboard.data_perspective.price_position.current_price": 11.0},
            case_id="direct",
        )
