# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""API tests for GET /api/v1/capabilities."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.v1.endpoints import capabilities as capabilities_endpoint
from src.capability_registry import (
    REASON_FEATURE_DISABLED,
    REASON_MISSING_CONFIG,
    REASON_MISSING_DEPENDENCY,
    CapabilityRecord,
)


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(capabilities_endpoint.router, prefix="/api/v1/capabilities")
    return app


def test_list_capabilities_returns_aggregated_items(monkeypatch) -> None:
    sample = [
        CapabilityRecord(
            capability_id="data.provider:finnhub", domain="data", provider="FinnhubFetcher",
            available=False, reason_code=REASON_MISSING_CONFIG, reason_message="missing FINNHUB_API_KEY",
            display_name="FinnhubFetcher", details={"kind": "provider"},
        ),
        CapabilityRecord(
            capability_id="tool.optional:multimodal", domain="tool", provider="multimodal_tools",
            available=False, reason_code=REASON_FEATURE_DISABLED, reason_message="disabled",
        ),
        CapabilityRecord(
            capability_id="data.provider:efinance", domain="data", provider="EfinanceFetcher",
            available=True, display_name="EfinanceFetcher",
        ),
    ]
    monkeypatch.setattr(capabilities_endpoint, "collect_capability_records", lambda **kwargs: sample)
    client = TestClient(_app())
    response = client.get("/api/v1/capabilities")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["available_count"] == 1
    assert body["unavailable_count"] == 2
    finnhub = next(item for item in body["items"] if item["id"] == "data.provider:finnhub")
    assert finnhub["reason_code"] == REASON_MISSING_CONFIG


def test_list_capabilities_domain_filter_forwarded(monkeypatch) -> None:
    captured = {}
    def _fake_collect(**kwargs):
        captured.update(kwargs)
        return [CapabilityRecord(
            capability_id="data.provider:tickflow", domain="data", provider="TickFlowFetcher",
            available=False, reason_code=REASON_MISSING_DEPENDENCY, reason_message="tickflow missing",
        )]
    monkeypatch.setattr(capabilities_endpoint, "collect_capability_records", _fake_collect)
    client = TestClient(_app())
    response = client.get("/api/v1/capabilities", params=[("domain", "data")])
    assert response.status_code == 200
    assert list(captured.get("domains") or []) == ["data"]


def test_list_capabilities_invalid_domain(monkeypatch) -> None:
    monkeypatch.setattr(
        capabilities_endpoint,
        "collect_capability_records",
        lambda **kwargs: (_ for _ in ()).throw(ValueError("unsupported capability domains: ['nope']")),
    )
    client = TestClient(_app())
    response = client.get("/api/v1/capabilities", params=[("domain", "nope")])
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "invalid_capability_domain"


def test_list_capabilities_live_aggregation_smoke() -> None:
    client = TestClient(_app())
    response = client.get("/api/v1/capabilities", params=[("domain", "data")])
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    assert body["total"] == body["available_count"] + body["unavailable_count"]
    finnhub = next((item for item in body["items"] if item["id"] == "data.provider:finnhub"), None)
    assert finnhub is not None
