# -*- coding: utf-8 -*-
"""API tests for watchlist score endpoint (Issue #147 / T25)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, Sequence

from api.v1.endpoints.watchlist_scores import score_watchlist_symbols
from api.v1.schemas.watchlist_scores import WatchlistScoreRequest
from src.services.watchlist_score_service import WatchlistScoreService


def test_score_endpoint_returns_unanalyzed_without_fabricated_score(monkeypatch) -> None:
    def _factory() -> WatchlistScoreService:
        return WatchlistScoreService(
            analysis_loader=lambda _codes: {},
            signal_loader=lambda _codes: {},
            clock=lambda: datetime(2026, 8, 9, tzinfo=timezone.utc),
        )

    monkeypatch.setattr(
        "api.v1.endpoints.watchlist_scores.WatchlistScoreService",
        _factory,
    )
    response = score_watchlist_symbols(
        WatchlistScoreRequest(stock_codes=["AAPL", "600519"], sort="manual")
    )
    assert response.scoring_mode == "aggregate_existing"
    assert response.sort == "manual"
    assert len(response.items) == 2
    for item in response.items:
        assert item.status == "unanalyzed"
        assert item.score is None


def test_score_endpoint_manual_default_and_batch_query_count(monkeypatch) -> None:
    analyses: Dict[str, Any] = {
        "MSFT": SimpleNamespace(
            id=2,
            code="MSFT",
            sentiment_score=88,
            operation_advice="Buy",
            created_at=datetime(2026, 8, 9, 1, 0, tzinfo=timezone.utc),
            report_type="detailed",
        ),
        "AAPL": SimpleNamespace(
            id=1,
            code="AAPL",
            sentiment_score=40,
            operation_advice="Hold",
            created_at=datetime(2026, 8, 8, 1, 0, tzinfo=timezone.utc),
            report_type="detailed",
        ),
    }

    def _factory() -> WatchlistScoreService:
        return WatchlistScoreService(
            analysis_loader=lambda codes: analyses,
            signal_loader=lambda codes: {},
            clock=lambda: datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc),
        )

    monkeypatch.setattr(
        "api.v1.endpoints.watchlist_scores.WatchlistScoreService",
        _factory,
    )
    response = score_watchlist_symbols(
        WatchlistScoreRequest(stock_codes=["AAPL", "MSFT"])
    )
    assert [item.stock_code for item in response.items] == ["AAPL", "MSFT"]
    assert response.query_count.analysis == 1
    assert response.query_count.signals == 1
    assert "not investment advice" in response.disclaimer.lower()
