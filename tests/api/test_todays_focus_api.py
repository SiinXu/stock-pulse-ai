# -*- coding: utf-8 -*-
"""Real HTTP contract tests for Today's Focus."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.v1.endpoints import todays_focus


def _payload() -> Dict[str, Any]:
    return {
        "pack_version": "todays_focus/2.1",
        "generated_at": "2026-08-09T08:00:00+00:00",
        "status": "ok",
        "max_items": 5,
        "item_count": 1,
        "items": [
            {
                "code": "HK00700",
                "name": "Tencent",
                "reason_code": "alert_triggered",
                "reason_display": "Alert triggered: price crossed threshold",
                "priority": 100,
                "weight_pct": None,
                "secondary_reason_codes": ["analysis_reversal"],
                "evidence": {
                    "type": "alert",
                    "trigger_id": 7,
                    "rule_id": 2,
                    "observed_at": "2026-08-09T07:30:00+00:00",
                    "status": "triggered",
                    "source": "local_alert_store",
                },
            }
        ],
        "empty_reason": None,
        "empty_message": None,
        "sources_used": ["alerts"],
        "degraded_sources": [],
        "temporal_policy": {
            "semantics": "per_market_local_calendar_day",
            "cross_market_rule": "evidence_uses_target_symbol_market_timezone",
            "fallback_timezone": "Asia/Shanghai",
            "window_end": "2026-08-09T08:00:00+00:00",
            "naive_timestamp_policy": "assume_utc",
            "missing_timestamp_policy": "exclude",
            "non_trading_day_policy": "same_local_day_only",
            "markets": [
                {
                    "market": "cn",
                    "timezone": "Asia/Shanghai",
                    "local_date": "2026-08-09",
                    "window_start": "2026-08-08T16:00:00+00:00",
                    "window_end": "2026-08-09T08:00:00+00:00",
                    "is_trading_day": True,
                },
                {
                    "market": "hk",
                    "timezone": "Asia/Hong_Kong",
                    "local_date": "2026-08-09",
                    "window_start": "2026-08-08T16:00:00+00:00",
                    "window_end": "2026-08-09T08:00:00+00:00",
                    "is_trading_day": True,
                },
                {
                    "market": "us",
                    "timezone": "America/New_York",
                    "local_date": "2026-08-09",
                    "window_start": "2026-08-09T04:00:00+00:00",
                    "window_end": "2026-08-09T08:00:00+00:00",
                    "is_trading_day": False,
                },
                {
                    "market": "unknown",
                    "timezone": "Asia/Shanghai",
                    "local_date": "2026-08-09",
                    "window_start": "2026-08-08T16:00:00+00:00",
                    "window_end": "2026-08-09T08:00:00+00:00",
                    "is_trading_day": None,
                },
            ],
        },
        "universe_contract": {
            "symbol_count": 1,
            "hard_cap": 1000,
            "truncated": False,
            "sources": ["watchlist_config"],
            "excluded_non_finite_positions": 0,
            "data_notes": [],
        },
        "cost_contract": {
            "alert_repository_calls": 1,
            "portfolio_repository_calls": 1,
            "analysis_history_repository_calls": 1,
            "event_repository_calls": 0,
            "database_writes": 0,
            "provider_calls": 0,
            "analysis_runs_triggered": 0,
            "zero_extra_fetch": True,
            "read_only": True,
        },
        "presentation_boundary": {
            "alerts_owned_by": "signal_center",
            "focus_shows": "prioritized_symbols_with_evidence_links",
            "duplicate_alert_ui": False,
        },
    }


def _client(monkeypatch: pytest.MonkeyPatch, payload: Dict[str, Any]) -> TestClient:
    class FakeService:
        def build_focus(self, **_kwargs: Any) -> Dict[str, Any]:
            return deepcopy(payload)

    monkeypatch.setattr(todays_focus, "TodaysFocusService", FakeService)
    app = FastAPI()
    app.include_router(todays_focus.router, prefix="/api/v1/focus")
    return TestClient(app, raise_server_exceptions=False)


def test_real_endpoint_returns_typed_evidence_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _client(monkeypatch, _payload()).get("/api/v1/focus/today")
    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["code"] == "HK00700"
    assert payload["items"][0]["evidence"]["type"] == "alert"
    assert payload["temporal_policy"]["semantics"] == "per_market_local_calendar_day"
    assert {window["market"] for window in payload["temporal_policy"]["markets"]} == {
        "cn", "hk", "us", "unknown",
    }
    assert payload["cost_contract"]["read_only"] is True


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_response_is_a_sanitized_500(
    monkeypatch: pytest.MonkeyPatch,
    invalid: float,
) -> None:
    payload = _payload()
    payload["items"][0]["weight_pct"] = invalid
    response = _client(monkeypatch, payload).get("/api/v1/focus/today")
    assert response.status_code == 500
    assert "NaN" not in response.text
    assert "Infinity" not in response.text


def test_openapi_exposes_discriminator_bounds_and_datetime_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema = _client(monkeypatch, _payload()).app.openapi()
    components = schema["components"]["schemas"]
    item = components["TodaysFocusItem"]
    response = components["TodaysFocusResponse"]
    evidence = item["properties"]["evidence"]
    assert evidence["discriminator"]["propertyName"] == "type"
    assert item["properties"]["weight_pct"]["anyOf"][0]["maximum"] == 100
    assert response["properties"]["items"]["maxItems"] == 10
    assert response["properties"]["generated_at"]["format"] == "date-time"
    temporal = components["TodaysFocusTemporalPolicy"]
    assert temporal["properties"]["semantics"]["const"] == "per_market_local_calendar_day"
