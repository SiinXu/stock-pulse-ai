# -*- coding: utf-8 -*-
"""Unit tests for extracted Market Light metric helpers (Issue #1085 step 1)."""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from unittest.mock import patch

from src.core.market_profile import CN_PROFILE, JP_PROFILE, KR_PROFILE, US_PROFILE
from src.market.analyzer import MarketAnalyzer, MarketIndex, MarketOverview
from src.market.metrics import build_market_light_scores, build_market_temperature, market_light_status_from_score


def _defensive_cn_overview() -> MarketOverview:
    """Counterexample from test_market_light_snapshot_marks_defensive_market_red."""
    return MarketOverview(
        date="2026-03-06",
        indices=[
            MarketIndex(code="000001", name="上证指数", current=3200, change_pct=-1.8),
            MarketIndex(code="399001", name="深证成指", current=9800, change_pct=-2.4),
        ],
        up_count=900,
        down_count=4100,
        limit_up_count=10,
        limit_down_count=80,
        total_amount=9800.0,
    )


def _us_index_only_overview() -> MarketOverview:
    """Counterexample from test_market_light_snapshot_marks_us_without_breadth_as_partial."""
    return MarketOverview(
        date="2026-03-06",
        indices=[MarketIndex(code="SPX", name="S&P 500", current=5000, change_pct=0.5)],
    )


def _make_analyzer(*, region: str = "cn", report_language: str = "zh") -> MarketAnalyzer:
    analyzer = MarketAnalyzer.__new__(MarketAnalyzer)
    analyzer.region = region
    analyzer.profile = {
        "cn": CN_PROFILE,
        "us": US_PROFILE,
        "jp": JP_PROFILE,
        "kr": KR_PROFILE,
    }[region]
    analyzer.config = SimpleNamespace(report_language=report_language)
    return analyzer


def test_defensive_cn_overview_matches_existing_snapshot_counterexample() -> None:
    scores = build_market_light_scores(
        _defensive_cn_overview(),
        has_market_stats=True,
        review_language="zh",
    )

    assert scores["score"] == 19
    assert scores["score"] < 40
    assert scores["temperature_label"] == "偏弱"
    assert scores["data_quality"] == "ok"
    assert scores["dimensions"]["breadth"] == {"score": 18, "available": True}
    assert scores["dimensions"]["index"] == {"score": 24, "available": True}
    assert scores["dimensions"]["limit"] == {"score": 11, "available": True}
    assert market_light_status_from_score(scores["score"]) == "red"
    assert build_market_temperature(
        _defensive_cn_overview(),
        has_market_stats=True,
        review_language="zh",
    ) == (19, "偏弱")


def test_english_labels_use_same_numeric_scores() -> None:
    scores = build_market_light_scores(
        _defensive_cn_overview(),
        has_market_stats=True,
        review_language="en",
    )

    assert scores["score"] == 19
    assert scores["temperature_label"] == "defensive"
    assert market_light_status_from_score(scores["score"]) == "red"


def test_us_without_breadth_is_partial_with_neutral_fallbacks() -> None:
    scores = build_market_light_scores(
        _us_index_only_overview(),
        has_market_stats=False,
        review_language="en",
    )

    assert scores["data_quality"] == "partial"
    assert scores["dimensions"]["breadth"] == {"score": 50, "available": False}
    assert scores["dimensions"]["index"] == {"score": 56, "available": True}
    assert scores["dimensions"]["limit"] == {"score": 50, "available": False}
    assert scores["score"] == 52
    assert scores["temperature_label"] == "mixed"
    assert market_light_status_from_score(52) == "yellow"


def test_jp_and_kr_without_stats_match_us_partial_contract() -> None:
    overview = MarketOverview(
        date="2026-03-06",
        indices=[MarketIndex(code="N225", name="Nikkei 225", current=30000, change_pct=0.5)],
    )

    for has_stats in (JP_PROFILE.has_market_stats, KR_PROFILE.has_market_stats):
        scores = build_market_light_scores(
            overview,
            has_market_stats=has_stats,
            review_language="zh",
        )
        assert has_stats is False
        assert scores["data_quality"] == "partial"
        assert scores["dimensions"]["breadth"] == {"score": 50, "available": False}
        assert scores["dimensions"]["limit"] == {"score": 50, "available": False}
        assert scores["dimensions"]["index"]["available"] is True


def test_index_unavailable_when_indices_missing_or_change_pct_none() -> None:
    empty = MarketOverview(date="2026-03-06", up_count=10, down_count=5)
    none_index = MarketIndex(code="000001", name="上证指数", current=3200)
    none_index.change_pct = None  # type: ignore[assignment]
    none_changes = MarketOverview(
        date="2026-03-06",
        indices=[none_index],
        up_count=10,
        down_count=5,
        limit_up_count=1,
        limit_down_count=1,
    )

    empty_scores = build_market_light_scores(
        empty, has_market_stats=True, review_language="zh"
    )
    none_scores = build_market_light_scores(
        none_changes, has_market_stats=True, review_language="zh"
    )

    assert empty_scores["data_quality"] == "unavailable"
    assert empty_scores["dimensions"]["index"] == {"score": 50, "available": False}
    assert none_scores["data_quality"] == "unavailable"
    assert none_scores["dimensions"]["index"]["available"] is False


def test_zero_change_pct_is_available_and_keeps_neutral_index_score() -> None:
    overview = MarketOverview(
        date="2026-03-06",
        indices=[MarketIndex(code="000001", name="上证指数", current=3200, change_pct=0.0)],
    )

    scores = build_market_light_scores(
        overview, has_market_stats=False, review_language="zh"
    )

    assert scores["dimensions"]["index"] == {"score": 50, "available": True}
    assert scores["data_quality"] == "partial"


def test_index_score_clamps_to_0_and_100() -> None:
    crash = MarketOverview(
        date="2026-03-06",
        indices=[MarketIndex(code="000001", name="上证指数", current=1, change_pct=-20.0)],
    )
    melt_up = MarketOverview(
        date="2026-03-06",
        indices=[MarketIndex(code="000001", name="上证指数", current=1, change_pct=20.0)],
    )

    assert build_market_light_scores(
        crash, has_market_stats=False, review_language="zh"
    )["dimensions"]["index"]["score"] == 0
    assert build_market_light_scores(
        melt_up, has_market_stats=False, review_language="zh"
    )["dimensions"]["index"]["score"] == 100


def test_dimension_scores_truncate_toward_zero() -> None:
    overview = MarketOverview(
        date="2026-03-06",
        indices=[MarketIndex(code="000001", name="上证指数", current=3200, change_pct=0.1)],
        up_count=1,
        down_count=2,
        limit_up_count=1,
        limit_down_count=2,
    )

    scores = build_market_light_scores(
        overview, has_market_stats=True, review_language="zh"
    )

    assert scores["dimensions"]["breadth"]["score"] == 33
    assert scores["dimensions"]["limit"]["score"] == 33
    assert scores["dimensions"]["index"]["score"] == 51


def test_has_market_stats_false_ignores_present_breadth_counts() -> None:
    overview = MarketOverview(
        date="2026-03-06",
        indices=[MarketIndex(code="SPX", name="S&P 500", current=5000, change_pct=0.6)],
        up_count=1000,
        down_count=400,
        limit_up_count=10,
        limit_down_count=0,
        total_amount=9800.0,
    )

    scores = build_market_light_scores(
        overview, has_market_stats=False, review_language="zh"
    )

    assert scores["dimensions"]["breadth"] == {"score": 50, "available": False}
    assert scores["dimensions"]["limit"] == {"score": 50, "available": False}


def test_zero_participants_or_limits_keep_fallback_score() -> None:
    overview = MarketOverview(
        date="2026-03-06",
        indices=[MarketIndex(code="000001", name="上证指数", current=3200, change_pct=0.6)],
        up_count=0,
        down_count=0,
        limit_up_count=0,
        limit_down_count=0,
    )

    scores = build_market_light_scores(
        overview, has_market_stats=True, review_language="zh"
    )

    assert scores["dimensions"]["breadth"] == {"score": 50, "available": False}
    assert scores["dimensions"]["limit"] == {"score": 50, "available": False}
    assert scores["data_quality"] == "partial"


def _uniform_dimension_overview(score: int) -> MarketOverview:
    """Build an overview whose breadth, index, and limit scores all equal ``score``."""
    change_pct = (score - 50) / 12
    return MarketOverview(
        date="2026-03-06",
        indices=[MarketIndex(code="000001", name="上证指数", current=3200, change_pct=change_pct)],
        up_count=score,
        down_count=100 - score,
        limit_up_count=score,
        limit_down_count=100 - score,
    )


def test_temperature_and_status_thresholds() -> None:
    assert market_light_status_from_score(60) == "green"
    assert market_light_status_from_score(59) == "yellow"
    assert market_light_status_from_score(40) == "yellow"
    assert market_light_status_from_score(39) == "red"

    labels_zh = {
        70: "强势",
        69: "偏暖",
        55: "偏暖",
        54: "震荡",
        40: "震荡",
        39: "偏弱",
    }
    labels_en = {
        70: "risk-on",
        69: "constructive",
        55: "constructive",
        54: "mixed",
        40: "mixed",
        39: "defensive",
    }
    for score, label in labels_zh.items():
        result = build_market_light_scores(
            _uniform_dimension_overview(score),
            has_market_stats=True,
            review_language="zh",
        )
        assert result["score"] == score
        assert result["temperature_label"] == label
        assert result["data_quality"] == "ok"
    for score, label in labels_en.items():
        result = build_market_light_scores(
            _uniform_dimension_overview(score),
            has_market_stats=True,
            review_language="en",
        )
        assert result["score"] == score
        assert result["temperature_label"] == label


def test_weighted_score_uses_python_round_then_int() -> None:
    overview = SimpleNamespace(
        up_count=1,
        down_count=1,
        limit_up_count=1,
        limit_down_count=1,
        indices=[SimpleNamespace(change_pct=0.0)],
    )
    scores = build_market_light_scores(
        overview, has_market_stats=True, review_language="zh"
    )
    assert scores["dimensions"]["breadth"]["score"] == 50
    assert scores["dimensions"]["index"]["score"] == 50
    assert scores["dimensions"]["limit"]["score"] == 50
    assert scores["score"] == 50


def test_analyzer_methods_delegate_through_module_level_seams() -> None:
    import src.market.analyzer as analyzer_mod
    import src.market.metrics as metrics_mod

    assert analyzer_mod.build_market_light_scores is metrics_mod.build_market_light_scores
    assert analyzer_mod.build_market_temperature is metrics_mod.build_market_temperature
    assert (
        analyzer_mod.market_light_status_from_score
        is metrics_mod.market_light_status_from_score
    )

    ma = _make_analyzer(region="cn", report_language="zh")
    overview = _defensive_cn_overview()
    sentinel = {
        "score": 7,
        "temperature_label": "patched",
        "dimensions": {},
        "data_quality": "ok",
    }

    with patch.object(
        analyzer_mod, "build_market_light_scores", return_value=sentinel
    ) as patched_scores:
        assert ma._build_market_light_scores(overview) is sentinel
        patched_scores.assert_called_once_with(
            overview,
            has_market_stats=CN_PROFILE.has_market_stats,
            review_language="zh",
        )

    with patch.object(
        analyzer_mod, "market_light_status_from_score", return_value="yellow"
    ) as patched_status:
        snapshot = ma.build_market_light_snapshot(overview)
        patched_status.assert_called_once_with(19)
        assert snapshot["status"] == "yellow"
        assert snapshot["score"] == 19
        assert snapshot["temperature_label"] == "偏弱"


def test_analyzer_temperature_wrapper_uses_instance_score_method() -> None:
    ma = _make_analyzer(region="cn", report_language="en")
    overview = _defensive_cn_overview()
    sentinel = {
        "score": 88,
        "temperature_label": "override",
        "dimensions": {},
        "data_quality": "ok",
    }

    with patch.object(ma, "_build_market_light_scores", return_value=sentinel):
        assert ma._build_market_temperature(overview) == (88, "override")


def test_public_analyzer_signatures_remain_compatible() -> None:
    score_params = list(inspect.signature(MarketAnalyzer._build_market_light_scores).parameters)
    temperature_params = list(
        inspect.signature(MarketAnalyzer._build_market_temperature).parameters
    )
    snapshot_params = list(
        inspect.signature(MarketAnalyzer.build_market_light_snapshot).parameters
    )

    assert score_params == ["self", "overview"]
    assert temperature_params == ["self", "overview"]
    assert snapshot_params == ["self", "overview"]
    init_params = list(inspect.signature(MarketAnalyzer.__init__).parameters)
    assert init_params == ["self", "search_service", "analyzer", "region", "config"]
    assert MarketIndex is not None
    assert MarketOverview is not None


def test_korean_report_language_uses_english_temperature_labels() -> None:
    ma = _make_analyzer(region="cn", report_language="ko")
    scores = ma._build_market_light_scores(_defensive_cn_overview())
    snapshot = ma.build_market_light_snapshot(_defensive_cn_overview())

    assert scores["temperature_label"] == "defensive"
    assert snapshot["status"] == "red"
    assert snapshot["label"] == "risk-off"
