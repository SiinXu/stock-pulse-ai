# -*- coding: utf-8 -*-
"""HTTP contract tests for POST /api/v1/analysis/portfolio (issue #128)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.endpoints import portfolio_level_analysis
from src.services.portfolio_level_analysis_service import MAX_SYMBOLS


def _client(monkeypatch, *, payload=None, error: Exception | None = None) -> TestClient:
    class _Service:
        def analyze(self, *args, **kwargs):
            if error is not None:
                raise error
            return payload or {
                "formula_version": "portfolio_level_analysis_v1",
                "analysis_mode": "portfolio_level_basket",
                "snapshot_kind": "synthetic_basket_v1",
                "as_of": "2026-06-01",
                "currency": "CNY",
                "status": "partial",
                "status_message": "Analyzed 2/3 symbols; 1 excluded due to missing data.",
                "disclaimer": "test",
                "requested_symbols": ["AAA", "BBB", "CCC"],
                "symbols_used": ["AAA", "BBB"],
                "symbols_requested_count": 3,
                "symbols_used_count": 2,
                "max_symbols": MAX_SYMBOLS,
                "weighting_mode": "equal_weight",
                "weights": [
                    {"symbol": "AAA", "weight_pct": 50.0},
                    {"symbol": "BBB", "weight_pct": 50.0},
                ],
                "degraded_symbols": [
                    {
                        "stock_code": "CCC",
                        "reason": "price_unavailable",
                        "detail": "No usable stored daily close for this symbol.",
                    }
                ],
                "annotations": ["1 of 3 symbols excluded due to missing or non-positive price data; remaining weights were rebased."],
                "correlation": {
                    "status": "ok",
                    "symbols": ["AAA", "BBB"],
                    "matrix": [[1.0, 0.9], [0.9, 1.0]],
                    "observation_count": 80,
                },
                "correlation_highlights": [
                    {
                        "left": "AAA",
                        "right": "BBB",
                        "correlation": 0.9,
                        "abs_correlation": 0.9,
                        "direction": "positive",
                    }
                ],
                "concentration": {
                    "status": "ok",
                    "hhi": 0.5,
                    "effective_n": 2.0,
                    "diversification_score": 1.0,
                    "top_weight_pct": 50.0,
                    "position_count": 2,
                    "weights": [
                        {"symbol": "AAA", "weight_pct": 50.0},
                        {"symbol": "BBB", "weight_pct": 50.0},
                    ],
                },
                "var": {
                    "status": "ok",
                    "var_pct": 2.5,
                    "var_value": 250.0,
                    "observation_count": 80,
                },
                "shared_risk_exposures": [
                    {
                        "kind": "high_correlation_cluster",
                        "symbols": ["AAA", "BBB"],
                        "size": 2,
                        "summary": "2 symbols share elevated pairwise correlation (common return factor risk).",
                        "rank": 1,
                    }
                ],
                "stance_distribution": {
                    "status": "partial",
                    "status_message": "Aggregated from existing analysis history and decision signals (no new LLM calls).",
                    "scored_count": 1,
                    "unanalyzed_count": 2,
                    "average_score": 70.0,
                    "by_operation_advice": {"buy": 1, "unanalyzed": 2},
                    "items": [],
                    "formula_version": "watchlist_score_v1",
                },
                "health": {
                    "status": "partial",
                    "score": None,
                    "partial_score": 40.0,
                    "band": None,
                    "comparable": False,
                },
                "stress": {"status": "ok", "scenario": {"id": "market_down_10"}},
                "risk_metrics_status": "ok",
                "risk_history": {},
                "assumptions": {
                    "synthetic_snapshot": True,
                    "max_symbols": MAX_SYMBOLS,
                    "provider_calls_on_hot_path": False,
                },
                "calculated_at": "2026-06-01T00:00:00+00:00",
            }

    monkeypatch.setattr(
        portfolio_level_analysis,
        "PortfolioLevelAnalysisService",
        lambda: _Service(),
    )
    app = FastAPI()
    app.include_router(portfolio_level_analysis.router, prefix="/api/v1/analysis")
    return TestClient(app, raise_server_exceptions=False)


def test_portfolio_level_endpoint_returns_partial_degradation(monkeypatch) -> None:
    response = _client(monkeypatch).post(
        "/api/v1/analysis/portfolio",
        json={"stock_codes": ["AAA", "BBB", "CCC"], "include_stress": True},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["formula_version"] == "portfolio_level_analysis_v1"
    assert payload["status"] == "partial"
    assert payload["degraded_symbols"][0]["stock_code"] == "CCC"
    assert payload["concentration"]["position_count"] == 2
    assert payload["correlation_highlights"][0]["left"] == "AAA"
    assert payload["assumptions"]["synthetic_snapshot"] is True


def test_over_limit_and_duplicates_are_rejected(monkeypatch) -> None:
    client = _client(monkeypatch)
    overflow = client.post(
        "/api/v1/analysis/portfolio",
        json={"stock_codes": [f"S{i:02d}" for i in range(MAX_SYMBOLS + 1)]},
    )
    assert overflow.status_code == 422

    duplicate = client.post(
        "/api/v1/analysis/portfolio",
        json={"stock_codes": ["AAA", "AAA"]},
    )
    assert duplicate.status_code == 422


def test_service_validation_error_maps_to_400(monkeypatch) -> None:
    response = _client(monkeypatch, error=ValueError("weights contains symbol not in stock_codes: ZZZ")).post(
        "/api/v1/analysis/portfolio",
        json={"stock_codes": ["AAA"], "weights": {"AAA": 1.0}},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "validation_error"


def test_openapi_registers_operation(monkeypatch) -> None:
    schema = _client(monkeypatch).app.openapi()
    path = schema["paths"]["/api/v1/analysis/portfolio"]["post"]
    assert path["operationId"] == "analyzePortfolioLevel"

def test_invalid_scenario_maps_to_400(monkeypatch) -> None:
    response = _client(
        monkeypatch,
        error=ValueError("unknown scenario id: does_not_exist"),
    ).post(
        "/api/v1/analysis/portfolio",
        json={
            "stock_codes": ["AAA", "BBB"],
            "include_stress": True,
            "scenario_id": "does_not_exist",
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "validation_error"

