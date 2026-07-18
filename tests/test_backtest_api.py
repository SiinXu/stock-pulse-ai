# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""HTTP regressions for the Backtest API error contract."""

import logging
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.middlewares.error_handler import add_error_handlers
from api.v1.endpoints import backtest as backtest_endpoint
from src.services.backtest_service import BacktestService, BacktestValidationError


SENSITIVE_ERROR = (
    "provider token=super-secret at "
    "https://private.example/v1?token=super-secret"
)


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    add_error_handlers(app)
    app.include_router(backtest_endpoint.router, prefix="/api/v1/backtest")
    app.dependency_overrides[backtest_endpoint.get_database_manager] = lambda: MagicMock()
    return TestClient(app, raise_server_exceptions=False)


def _assert_safe_internal_error(response) -> None:
    assert response.status_code == 500
    payload = response.json()
    assert payload["error"] == "internal_error"
    assert payload["message"] == "Internal server error"
    assert payload["params"] == {}
    assert payload["details"] is None
    assert payload["trace_id"]
    assert "super-secret" not in response.text
    assert "private.example" not in response.text


@pytest.mark.parametrize(
    ("method", "path", "service_method"),
    [
        ("POST", "/api/v1/backtest/run", "run_backtest"),
        ("GET", "/api/v1/backtest/results", "get_recent_evaluations"),
        ("GET", "/api/v1/backtest/performance", "get_summary"),
        ("GET", "/api/v1/backtest/performance/600519", "get_summary"),
    ],
)
def test_unexpected_value_error_is_safe_internal_error(
    client: TestClient,
    caplog,
    method: str,
    path: str,
    service_method: str,
) -> None:
    service = MagicMock()
    getattr(service, service_method).side_effect = ValueError(SENSITIVE_ERROR)

    caplog.set_level(logging.ERROR, logger="api.v1.endpoints.backtest")
    with patch.object(backtest_endpoint, "BacktestService", return_value=service):
        response = client.request(method, path, json={} if method == "POST" else None)

    _assert_safe_internal_error(response)
    rendered_logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "super-secret" not in rendered_logs
    assert "private.example" not in rendered_logs
    assert "error_code=internal_error" in rendered_logs
    assert "exception_type=ValueError" in rendered_logs
    assert all(record.exc_info is None for record in caplog.records)


def test_response_validation_error_is_safe_internal_error(client: TestClient) -> None:
    service = MagicMock()
    service.run_backtest.return_value = {
        "processed": SENSITIVE_ERROR,
        "saved": 0,
        "completed": 0,
        "insufficient": 0,
        "errors": 0,
        "applied_eval_window_days": 10,
    }

    with patch.object(backtest_endpoint, "BacktestService", return_value=service):
        response = client.post("/api/v1/backtest/run", json={})

    _assert_safe_internal_error(response)


def test_controlled_validation_error_remains_invalid_params(client: TestClient) -> None:
    service = MagicMock()
    service.run_backtest.side_effect = BacktestValidationError("非法股票代码格式: invalid")

    with patch.object(backtest_endpoint, "BacktestService", return_value=service):
        response = client.post("/api/v1/backtest/run", json={"code": "invalid"})

    payload = response.json()
    assert response.status_code == 400
    assert payload["error"] == "invalid_params"
    assert payload["message"] == "非法股票代码格式: invalid"
    assert payload["params"] == {}
    assert payload["details"] is None
    assert payload["trace_id"]


def test_invalid_stock_code_uses_controlled_validation_error() -> None:
    with pytest.raises(BacktestValidationError, match="非法股票代码格式"):
        BacktestService._normalize_code("invalid")
