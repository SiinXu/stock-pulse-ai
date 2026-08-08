# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""HTTP contract tests for reasoning-trace export endpoint."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.middlewares.error_handler import add_error_handlers
from api.v1.endpoints import reasoning_trace as endpoint
from src.services.reasoning_trace_export_service import (
    ReasoningTraceExportResult,
    ReasoningTraceNotFound,
)


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(endpoint.router, prefix="/api/v1/reasoning-trace")
    add_error_handlers(app)
    return TestClient(app)


def _enabled_config(*, enabled: bool = True) -> SimpleNamespace:
    return SimpleNamespace(reasoning_trace_export_enabled=enabled)


def _patch_services_config(enabled: bool = True):
    services = SimpleNamespace(config=_enabled_config(enabled=enabled))
    return patch.object(endpoint, "get_application_services", return_value=services)


def test_export_disabled_returns_404_without_side_effects() -> None:
    with _patch_services_config(enabled=False):
        response = _client().get("/api/v1/reasoning-trace/1")
    assert response.status_code == 404
    body = response.json()
    assert body["error"] == "reasoning_trace_export_disabled"


def test_export_requires_admin_session_when_auth_enabled() -> None:
    with _patch_services_config(enabled=True), patch.object(
        endpoint, "is_auth_enabled", return_value=True
    ), patch.object(endpoint, "verify_session", return_value=False):
        response = _client().get(
            "/api/v1/reasoning-trace/1",
            cookies={"dsa_session": "invalid"},
        )
    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"


def test_export_json_success() -> None:
    package = {
        "schema_version": "reasoning-trace-v1",
        "run": {"run_id": "q-1", "stock_code": "600519"},
        "agents": [{"role": "research", "tool_calls": [], "events": []}],
        "synthesis": {"final_conclusion": {"final_signal": "buy"}},
        "data_sources": {},
        "coverage": {"recorded": [], "not_recorded": []},
        "truncated": False,
    }
    service = MagicMock()
    service.export_for_record.return_value = ReasoningTraceExportResult(
        package=package,
        markdown="# Reasoning Trace",
        truncated=False,
    )
    with _patch_services_config(enabled=True), patch.object(
        endpoint, "is_auth_enabled", return_value=False
    ), patch.object(endpoint, "HistoryService", return_value=MagicMock()), patch.object(
        endpoint, "ReasoningTraceExportService", return_value=service
    ):
        app = FastAPI()
        app.include_router(endpoint.router, prefix="/api/v1/reasoning-trace")
        add_error_handlers(app)
        from api import deps as api_deps

        app.dependency_overrides[api_deps.get_database_manager] = lambda: MagicMock()
        client = TestClient(app)
        response = client.get("/api/v1/reasoning-trace/42")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "reasoning-trace-v1"
    assert body["run"]["stock_code"] == "600519"
    service.export_for_record.assert_called_once()


def test_export_not_found() -> None:
    service = MagicMock()
    service.export_for_record.side_effect = ReasoningTraceNotFound()
    with _patch_services_config(enabled=True), patch.object(
        endpoint, "is_auth_enabled", return_value=False
    ), patch.object(endpoint, "HistoryService", return_value=MagicMock()), patch.object(
        endpoint, "ReasoningTraceExportService", return_value=service
    ):
        app = FastAPI()
        app.include_router(endpoint.router, prefix="/api/v1/reasoning-trace")
        add_error_handlers(app)
        from api import deps as api_deps

        app.dependency_overrides[api_deps.get_database_manager] = lambda: MagicMock()
        response = TestClient(app).get("/api/v1/reasoning-trace/999")
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


def test_export_markdown_format() -> None:
    service = MagicMock()
    service.export_for_record.return_value = ReasoningTraceExportResult(
        package={
            "schema_version": "reasoning-trace-v1",
            "run": {},
            "agents": [],
            "synthesis": {},
            "data_sources": {},
            "coverage": {},
            "truncated": False,
        },
        markdown="# Reasoning Trace\n\n- run_id: `q-1`\n",
        truncated=False,
    )
    with _patch_services_config(enabled=True), patch.object(
        endpoint, "is_auth_enabled", return_value=False
    ), patch.object(endpoint, "HistoryService", return_value=MagicMock()), patch.object(
        endpoint, "ReasoningTraceExportService", return_value=service
    ):
        app = FastAPI()
        app.include_router(endpoint.router, prefix="/api/v1/reasoning-trace")
        add_error_handlers(app)
        from api import deps as api_deps

        app.dependency_overrides[api_deps.get_database_manager] = lambda: MagicMock()
        response = TestClient(app).get(
            "/api/v1/reasoning-trace/1",
            params={"format": "markdown"},
        )
    assert response.status_code == 200
    assert "text/markdown" in response.headers.get("content-type", "")
    assert response.text.startswith("# Reasoning Trace")
