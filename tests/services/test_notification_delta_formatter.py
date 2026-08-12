from __future__ import annotations

from types import SimpleNamespace

from src.services.history_comparison_service import (
    AnalysisDelta,
    BASELINE_INCOMPARABLE,
    BASELINE_MISSING_HISTORY,
    BASELINE_OK,
    ListChange,
    ValueChange,
)
from src.services.notification_delta_formatter import format_delta_first_notification


def _result(code: str = "AAPL", language: str = "en") -> SimpleNamespace:
    return SimpleNamespace(code=code, report_language=language)


def _delta(**overrides) -> AnalysisDelta:
    values = {
        "has_baseline": True,
        "baseline_status": BASELINE_OK,
        "has_material_changes": False,
    }
    values.update(overrides)
    return AnalysisDelta(**values)


def test_first_analysis_and_no_change_are_distinct() -> None:
    deltas = iter(
        [
            _delta(
                has_baseline=False,
                baseline_status=BASELINE_MISSING_HISTORY,
            ),
            _delta(),
        ]
    )

    rendered = format_delta_first_notification(
        "# Full report",
        [_result("AAPL"), _result("MSFT")],
        "simple",
        delta_loader=lambda _code, _report_type: next(deltas),
    )

    assert "### AAPL" in rendered
    assert "First analysis: no previous baseline is available." in rendered
    assert "### MSFT" in rendered
    assert "No material changes since the previous analysis." in rendered
    assert rendered.endswith("# Full report")


def test_material_delta_renders_bounded_safe_changes() -> None:
    delta = _delta(
        has_material_changes=True,
        conclusion_changes=[
            ValueChange(
                field="action",
                base_value="hold",
                target_value="buy",
                direction="changed",
            )
        ],
        score_changes=[
            ValueChange(
                field="sentiment_score",
                base_value=60,
                target_value=72,
                direction="up",
                delta=12,
            ),
            ValueChange(
                field="dimension.unsafe",
                base_value=1,
                target_value=float("inf"),
                direction="unavailable",
                delta=float("inf"),
            ),
        ],
        evidence_changes=[
            ListChange(
                field="positive_catalysts",
                added=("Raised guidance",),
                added_total=1,
            )
        ],
    )

    rendered = format_delta_first_notification(
        "report",
        [_result()],
        "simple",
        delta_loader=lambda _code, _report_type: delta,
    )

    assert "Action: hold -> buy" in rendered
    assert "Sentiment score: 60 -> 72 (+12)" in rendered
    assert "New catalysts: Raised guidance" in rendered
    assert "inf" not in rendered.lower()


def test_incomparable_and_loader_failure_remain_visible_without_dropping_report() -> None:
    incomparable = format_delta_first_notification(
        "original",
        [_result(language="zh")],
        "simple",
        delta_loader=lambda _code, _report_type: _delta(
            has_baseline=False,
            baseline_status=BASELINE_INCOMPARABLE,
        ),
    )
    failed = format_delta_first_notification(
        "original",
        [_result()],
        "simple",
        delta_loader=lambda _code, _report_type: (_ for _ in ()).throw(RuntimeError("db")),
    )

    assert "暂时无法对比" in incomparable
    assert "incomparable_structure" in incomparable
    assert "Comparison unavailable (error)." in failed
    assert incomparable.endswith("original")
    assert failed.endswith("original")


def test_empty_results_leave_original_report_unchanged() -> None:
    assert format_delta_first_notification("original", [], "simple") == "original"
