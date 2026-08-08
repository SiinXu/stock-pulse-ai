# -*- coding: utf-8 -*-
"""Unit tests for watchlist AI score aggregation (Issue #147 / T25)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Mapping, Sequence

import pytest

from src.services.watchlist_score_service import (
    SCORE_STATUS_SCORED,
    SCORE_STATUS_UNANALYZED,
    SORT_MANUAL,
    SORT_SCORE_ASC,
    SORT_SCORE_DESC,
    WatchlistScoreService,
)


def _fixed_clock(iso: str = "2026-08-09T12:00:00+00:00"):
    dt = datetime.fromisoformat(iso)

    def _clock() -> datetime:
        return dt

    return _clock


def _analysis(
    *,
    code: str,
    sentiment_score: int | None = 70,
    operation_advice: str = "Buy",
    created_at: datetime | None = None,
    analysis_id: int = 1,
    report_type: str = "detailed",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=analysis_id,
        code=code,
        sentiment_score=sentiment_score,
        operation_advice=operation_advice,
        created_at=created_at or datetime(2026, 8, 8, 9, 0, tzinfo=timezone.utc),
        report_type=report_type,
    )


def _signal(
    *,
    stock_code: str,
    action: str = "buy",
    confidence: float | None = 0.8,
    signal_id: int = 10,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=signal_id,
        stock_code=stock_code,
        action=action,
        action_label=action.title(),
        confidence=confidence,
        created_at=datetime(2026, 8, 8, 10, 0, tzinfo=timezone.utc),
    )


def _service(
    analyses: Mapping[str, Any] | None = None,
    signals: Mapping[str, Any] | None = None,
) -> WatchlistScoreService:
    analysis_map = dict(analyses or {})
    signal_map = dict(signals or {})
    query_log: List[str] = []

    def analysis_loader(codes: Sequence[str]) -> Dict[str, Any]:
        query_log.append(f"analysis:{len(codes)}")
        return analysis_map

    def signal_loader(codes: Sequence[str]) -> Dict[str, Any]:
        query_log.append(f"signals:{len(codes)}")
        return signal_map

    service = WatchlistScoreService(
        analysis_loader=analysis_loader,
        signal_loader=signal_loader,
        clock=_fixed_clock(),
    )
    service._query_log = query_log  # type: ignore[attr-defined]
    return service


def test_unanalyzed_when_no_history_never_invents_zero() -> None:
    service = _service()
    payload = service.score_symbols(["AAPL", "600519"])

    assert payload["scoring_mode"] == "aggregate_existing"
    assert payload["sort"] == SORT_MANUAL
    assert len(payload["items"]) == 2
    for item in payload["items"]:
        assert item["status"] == SCORE_STATUS_UNANALYZED
        assert item["score"] is None
        assert item["score"] != 0
        assert item["factors"] == []
        assert item["as_of"] is None


def test_unanalyzed_when_history_missing_sentiment_score() -> None:
    service = _service(
        analyses={"AAPL": _analysis(code="AAPL", sentiment_score=None)},
    )
    payload = service.score_symbols(["AAPL"])
    item = payload["items"][0]
    assert item["status"] == SCORE_STATUS_UNANALYZED
    assert item["score"] is None
    assert item["analysis_id"] == 1


def test_scored_from_sentiment_with_explainable_factors() -> None:
    service = _service(
        analyses={"600519": _analysis(code="600519", sentiment_score=72, analysis_id=5)},
        signals={"600519": _signal(stock_code="600519", action="buy", confidence=0.9)},
    )
    payload = service.score_symbols(["600519"])
    item = payload["items"][0]

    assert item["status"] == SCORE_STATUS_SCORED
    assert isinstance(item["score"], int)
    assert 0 <= item["score"] <= 100
    assert item["score"] != 0 or item["status"] == SCORE_STATUS_SCORED
    assert item["as_of"] is not None
    assert item["age_days"] == 1
    assert item["freshness"] == "1d"
    keys = [f["key"] for f in item["factors"]]
    assert "analysis_sentiment" in keys
    assert "decision_signal" in keys


def test_manual_sort_preserves_input_order_by_default() -> None:
    service = _service(
        analyses={
            "AAPL": _analysis(code="AAPL", sentiment_score=40, analysis_id=1),
            "MSFT": _analysis(code="MSFT", sentiment_score=90, analysis_id=2),
            "600519": _analysis(code="600519", sentiment_score=70, analysis_id=3),
        }
    )
    payload = service.score_symbols(["AAPL", "MSFT", "600519"])
    codes = [item["stock_code"] for item in payload["items"]]
    assert codes == ["AAPL", "MSFT", "600519"]
    assert payload["sort"] == SORT_MANUAL


def test_score_desc_sort_is_optional_view() -> None:
    service = _service(
        analyses={
            "AAPL": _analysis(code="AAPL", sentiment_score=40, analysis_id=1),
            "MSFT": _analysis(code="MSFT", sentiment_score=90, analysis_id=2),
            "NVDA": _analysis(code="NVDA", sentiment_score=None, analysis_id=3),
        }
    )
    payload = service.score_symbols(
        ["AAPL", "MSFT", "NVDA"],
        sort=SORT_SCORE_DESC,
    )
    codes = [item["stock_code"] for item in payload["items"]]
    # Scored high→low, then unanalyzed at end
    assert codes[0] == "MSFT"
    assert codes[1] == "AAPL"
    assert codes[2] == "NVDA"
    assert payload["items"][2]["status"] == SCORE_STATUS_UNANALYZED


def test_score_asc_sort() -> None:
    service = _service(
        analyses={
            "AAPL": _analysis(code="AAPL", sentiment_score=40),
            "MSFT": _analysis(code="MSFT", sentiment_score=90),
        }
    )
    payload = service.score_symbols(["MSFT", "AAPL"], sort=SORT_SCORE_ASC)
    codes = [item["stock_code"] for item in payload["items"]]
    assert codes == ["AAPL", "MSFT"]


def test_batch_loaders_called_once_not_n_plus_one() -> None:
    service = _service(
        analyses={
            "AAPL": _analysis(code="AAPL", sentiment_score=55),
            "MSFT": _analysis(code="MSFT", sentiment_score=66),
        }
    )
    service.score_symbols(["AAPL", "MSFT", "GOOG", "TSLA"])
    log = service._query_log  # type: ignore[attr-defined]
    assert log.count([x for x in log if x.startswith("analysis:")][0]) >= 1
    analysis_calls = [x for x in log if x.startswith("analysis:")]
    signal_calls = [x for x in log if x.startswith("signals:")]
    assert len(analysis_calls) == 1
    assert len(signal_calls) == 1
    # Payload reports batch query counts for observability.
    payload = service.score_symbols(["AAPL", "MSFT"])
    assert payload["query_count"]["analysis"] == 1
    assert payload["query_count"]["signals"] == 1


def test_invalid_sort_raises() -> None:
    service = _service()
    with pytest.raises(ValueError, match="Unsupported sort mode"):
        service.score_symbols(["AAPL"], sort="random")


def test_empty_codes_returns_empty_items() -> None:
    service = _service()
    payload = service.score_symbols([])
    assert payload["items"] == []
    assert payload["query_count"] == {"analysis": 0, "signals": 0}


def test_order_items_manual_is_stable_helper() -> None:
    items = [
        {"stock_code": "B", "status": SCORE_STATUS_SCORED, "score": 10},
        {"stock_code": "A", "status": SCORE_STATUS_SCORED, "score": 90},
    ]
    ordered = WatchlistScoreService.order_items(
        items, sort_mode=SORT_MANUAL, input_codes=["A", "B"]
    )
    assert [row["stock_code"] for row in ordered] == ["A", "B"]
