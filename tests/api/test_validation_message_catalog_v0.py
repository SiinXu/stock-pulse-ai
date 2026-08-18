# -*- coding: utf-8 -*-
"""HTTP contract coverage for stable user-facing validation error codes."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import deps as api_deps
from src.api.middlewares.error_handler import add_error_handlers
from src.api.v1.endpoints import analysis, stocks
from src.services.image_stock_extractor import MAX_SIZE_BYTES
from tests.security_audit_test_utils import SecurityAuditRecorderStub


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(analysis.router, prefix="/api/v1/analysis")
    app.include_router(stocks.router, prefix="/api/v1/stocks")
    add_error_handlers(app)
    app.dependency_overrides[api_deps.get_config_dep] = lambda: SimpleNamespace()
    app.dependency_overrides[api_deps.require_security_audit_service] = (
        SecurityAuditRecorderStub
    )
    app.dependency_overrides[api_deps.get_system_config_service] = (
        lambda: SimpleNamespace()
    )
    return TestClient(app)


def _assert_error(
    response: Any,
    code: str,
    *,
    message: str | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    assert response.status_code == 400
    body = response.json()
    assert set(body) == {
        "error",
        "message",
        "params",
        "details",
        "detail",
        "category",
        "severity",
        "trace_id",
    }
    assert body["error"] == code
    assert isinstance(body["category"], str) and body["category"]
    assert body["severity"] in {"info", "warning", "error", "critical"}
    if message is not None:
        assert body["message"] == message
    if params is not None:
        assert body["params"] == params
    assert body["details"] is None
    assert body["detail"] is None
    assert isinstance(body["trace_id"], str) and body["trace_id"]
    assert response.headers["x-trace-id"] == body["trace_id"]
    return body


def test_analysis_missing_stock_params_uses_stable_http_envelope() -> None:
    response = _client().post("/api/v1/analysis/analyze", json={"async_mode": True})

    _assert_error(
        response,
        "missing_stock_params",
        message="必须提供 stock_code 或 stock_codes 参数",
    )


def test_analysis_invalid_stock_or_name_uses_stable_http_envelope() -> None:
    response = _client().post(
        "/api/v1/analysis/analyze",
        json={"stock_code": "AAPL!", "async_mode": True},
    )

    _assert_error(
        response,
        "invalid_stock_or_name",
        message="请输入有效的股票代码或股票名称",
    )


def test_analysis_whitespace_stock_code_uses_stable_http_envelope() -> None:
    response = _client().post(
        "/api/v1/analysis/analyze",
        json={"stock_code": "   ", "async_mode": True},
    )

    _assert_error(
        response,
        "empty_stock_code",
        message="股票代码不能为空或仅包含空白字符",
    )


def test_analysis_batch_limit_includes_interpolation_param() -> None:
    response = _client().post(
        "/api/v1/analysis/analyze",
        json={
            "stock_codes": [str(600000 + offset) for offset in range(51)],
            "async_mode": True,
        },
    )

    _assert_error(
        response,
        "analysis_batch_limit_exceeded",
        message="单次分析请求最多支持 50 只股票",
        params={"max_batch_size": 50},
    )


def test_analysis_sync_batch_uses_stable_http_envelope() -> None:
    response = _client().post(
        "/api/v1/analysis/analyze",
        json={"stock_codes": ["600519", "000858"], "async_mode": False},
    )

    _assert_error(
        response,
        "sync_mode_batch_unsupported",
        message="同步模式仅支持单只股票分析，请使用 async_mode=true 进行批量分析",
    )


def test_watchlist_stock_code_validation_distinguishes_empty_and_invalid() -> None:
    client = _client()

    empty = client.post("/api/v1/stocks/watchlist/add", json={"stock_code": "   "})
    _assert_error(empty, "empty_stock_code", message="股票代码不能为空")

    invalid = client.post("/api/v1/stocks/watchlist/add", json={"stock_code": "!!!"})
    _assert_error(
        invalid,
        "invalid_stock_code",
        message="'!!!' 不是合法的股票代码格式",
        params={"stock_code": "!!!"},
    )


def test_image_upload_validation_uses_stable_codes_and_params() -> None:
    client = _client()

    missing = client.post("/api/v1/stocks/extract-from-image")
    _assert_error(
        missing,
        "missing_upload_file",
        message="未提供文件，请使用表单字段 file 上传图片",
        params={"field": "file"},
    )

    unsupported = client.post(
        "/api/v1/stocks/extract-from-image",
        files={"file": ("symbols.txt", b"AAPL", "text/plain")},
    )
    body = _assert_error(unsupported, "unsupported_type")
    assert body["params"]["content_type"] == "text/plain"
    assert "image/png" in body["params"]["allowed"]

    oversized = client.post(
        "/api/v1/stocks/extract-from-image",
        files={"file": ("large.png", b"x" * (MAX_SIZE_BYTES + 1), "image/png")},
    )
    _assert_error(
        oversized,
        "file_too_large",
        message="图片超过 5MB 限制",
        params={"limit_mb": 5, "kind": "image"},
    )


def test_import_request_validation_uses_stable_codes_and_params() -> None:
    client = _client()

    missing_text = client.post("/api/v1/stocks/parse-import", json={})
    _assert_error(
        missing_text,
        "missing_import_text",
        message='未提供 text，请使用 {"text": "..."}',
        params={"field": "text"},
    )

    missing_file = client.post(
        "/api/v1/stocks/parse-import",
        files={"another": ("symbols.csv", b"AAPL", "text/csv")},
    )
    _assert_error(
        missing_file,
        "missing_upload_file",
        message="未提供文件，请使用表单字段 file",
        params={"field": "file"},
    )

    unsupported = client.post(
        "/api/v1/stocks/parse-import",
        content="AAPL",
        headers={"content-type": "text/plain"},
    )
    _assert_error(
        unsupported,
        "unsupported_content_type",
        params={"content_type": "text/plain"},
    )
