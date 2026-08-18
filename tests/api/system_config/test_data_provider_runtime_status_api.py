# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""API contract tests for data provider runtime status."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.endpoints import system_config as system_config_endpoint
from src.services.data_provider_runtime_status_service import SCHEMA_VERSION


def _router_app() -> FastAPI:
    app = FastAPI()
    app.include_router(system_config_endpoint.router, prefix="/api/v1/system")
    return app


def test_runtime_status_endpoint_returns_projection(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.services.data_provider_runtime_status_service.build_data_provider_runtime_status",
        lambda **_kwargs: {
            "schema_version": SCHEMA_VERSION,
            "as_of": "2026-08-12T00:00:00+00:00",
            "partial": False,
            "source_state": "ok",
            "error_code": None,
            "error_message": None,
            "markets": [
                {
                    "market": "cn",
                    "data_type": "daily_data",
                    "ordered_provider_ids": ["akshare"],
                    "primary_provider_id": "akshare",
                    "fallback_provider_ids": [],
                    "primary_selection": "first_eligible_unobserved",
                    "quality": "unknown",
                    "as_of": None,
                }
            ],
            "providers": [
                {
                    "provider_id": "akshare",
                    "display_name": "AkshareFetcher",
                    "role": "baseline",
                    "markets": ["cn"],
                    "capabilities": ["daily_data"],
                    "configured": None,
                    "available": True,
                    "health_status": "unknown",
                    "health_score": None,
                    "circuit_state": None,
                    "sample_count": 0,
                    "static_priority": 5,
                    "last_success_at": None,
                    "last_failure_at": None,
                    "failure_reason": None,
                    "is_primary_for": ["daily_data:cn"],
                    "is_fallback_for": [],
                    "config_directory": False,
                }
            ],
            "cache": {
                "enabled": True,
                "fetch_mode": "auto",
                "hits": 0,
                "misses": 0,
                "stale_hits": 0,
                "writes": 0,
                "quality": "idle",
                "note": None,
            },
        },
    )
    response = TestClient(_router_app()).get(
        "/api/v1/system/config/data-providers/runtime-status"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == SCHEMA_VERSION
    assert body["providers"][0]["health_status"] == "unknown"
    assert body["providers"][0]["health_status"] != "healthy"


def test_runtime_status_endpoint_surfaces_partial_owner(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.services.data_provider_runtime_status_service.build_data_provider_runtime_status",
        lambda **_kwargs: {
            "schema_version": SCHEMA_VERSION,
            "as_of": "2026-08-12T00:00:00+00:00",
            "partial": True,
            "source_state": "not_initialized",
            "error_code": "data_runtime_not_initialized",
            "error_message": "not ready",
            "markets": [],
            "providers": [],
            "cache": None,
        },
    )
    body = TestClient(_router_app()).get(
        "/api/v1/system/config/data-providers/runtime-status"
    ).json()
    assert body["partial"] is True
    assert body["source_state"] == "not_initialized"
    assert body["providers"] == []
