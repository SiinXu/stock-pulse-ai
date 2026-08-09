# -*- coding: utf-8 -*-
"""Real HTTP contract tests for watchlist scores."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.v1.endpoints import watchlist_scores
from src.services.watchlist_score_service import WatchlistScoreService


def _client(monkeypatch, *, analyses=None, signals=None) -> TestClient:
    def factory() -> WatchlistScoreService:
        return WatchlistScoreService(
            analysis_loader=lambda _codes: analyses or {},
            signal_loader=lambda _codes: signals or {},
            clock=lambda: datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc),
        )

    monkeypatch.setattr(watchlist_scores, "WatchlistScoreService", factory)
    app = FastAPI()
    app.include_router(watchlist_scores.router, prefix="/api/v1/watchlist")
    return TestClient(app, raise_server_exceptions=False)


def test_real_endpoint_returns_strict_unanalyzed_contract(monkeypatch) -> None:
    response = _client(monkeypatch).post(
        "/api/v1/watchlist/scores",
        json={"stock_codes": ["AAPL", "600519"], "sort": "manual"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["formula_version"] == "watchlist_score_v1"
    assert payload["disclaimer_key"] == "watchlist_score.disclaimer"
    assert payload["source_rows"] == {"analysis": 0, "signals": 0}
    assert [item["score"] for item in payload["items"]] == [None, None]


def test_real_endpoint_serializes_aware_utc_and_factor_provenance(monkeypatch) -> None:
    analysis = SimpleNamespace(
        id=5,
        code="AAPL",
        sentiment_score=72,
        operation_advice="Buy <script>",
        created_at=datetime(2026, 8, 8, 9, 0, tzinfo=timezone.utc),
        report_type="detailed",
    )
    signal = SimpleNamespace(
        id=8,
        stock_code="AAPL",
        action="buy",
        confidence=0.8,
        status="active",
        source_type="analysis",
        source_report_id=5,
        decision_profile="balanced",
        created_at=datetime(2026, 8, 8, 10, 0),
        expires_at=datetime(2026, 8, 10, 10, 0),
    )
    response = _client(
        monkeypatch,
        analyses={"AAPL": analysis},
        signals={"AAPL": signal},
    ).post("/api/v1/watchlist/scores", json={"stock_codes": ["AAPL"]})
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["as_of"].endswith("Z")
    assert item["operation_advice"] == "Buy <script>"
    assert item["factors"][1]["source"]["source_report_id"] == 5
    assert "label" not in item["factors"][0]
    assert "detail" not in item["factors"][0]


def test_request_overflow_invalid_symbol_duplicate_and_sort_are_stable_422(monkeypatch) -> None:
    client = _client(monkeypatch)
    cases = [
        {"stock_codes": ["AAPL"] * 201},
        {"stock_codes": ["AAPL", "AAPL"]},
        {"stock_codes": ["bad symbol"]},
        {"stock_codes": ["AAPL"], "sort": "random"},
    ]
    for body in cases:
        response = client.post("/api/v1/watchlist/scores", json=body)
        assert response.status_code == 422

    alias_duplicate = client.post(
        "/api/v1/watchlist/scores",
        json={"stock_codes": ["00700", "HK00700"]},
    )
    assert alias_duplicate.status_code == 400
    assert alias_duplicate.json()["detail"]["error"] == "validation_error"


def test_openapi_exposes_enums_bounds_and_datetime_contract(monkeypatch) -> None:
    schema = _client(monkeypatch).app.openapi()
    components = schema["components"]["schemas"]
    request = components["WatchlistScoreRequest"]
    item = components["WatchlistScoreItem"]
    assert request["properties"]["stock_codes"]["maxItems"] == 200
    assert request["properties"]["sort"]["enum"] == ["manual", "score_desc", "score_asc"]
    assert item["properties"]["score"]["anyOf"][0]["maximum"] == 100
    assert item["properties"]["as_of"]["anyOf"][0]["format"] == "date-time"
