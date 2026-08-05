# -*- coding: utf-8 -*-
"""Phase-1 backend validation message catalog: stable codes + Chinese fallbacks."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from api.v1.endpoints.analysis import trigger_analysis
from api.v1.endpoints.stocks import _validate_and_normalize_stock_code


def _analyze_request(**overrides):
    base = dict(
        stock_code=None,
        stock_codes=None,
        stock_name=None,
        original_query=None,
        selection_source="manual",
        report_type="detailed",
        force_refresh=False,
        async_mode=True,
        notify=True,
        analysis_phase="auto",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_missing_stock_params_emits_stable_code() -> None:
    with pytest.raises(HTTPException) as exc_info:
        trigger_analysis(request=_analyze_request(), config=SimpleNamespace())
    detail = exc_info.value.detail
    assert exc_info.value.status_code == 400
    assert detail["error"] == "missing_stock_params"
    assert detail["message"] == "必须提供 stock_code 或 stock_codes 参数"


def test_invalid_stock_or_name_emits_stable_code_with_chinese_fallback() -> None:
    with patch("api.v1.endpoints.analysis.resolve_name_to_code", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            trigger_analysis(
                request=_analyze_request(stock_code="aaaaaaa"),
                config=SimpleNamespace(),
            )
    detail = exc_info.value.detail
    assert detail["error"] == "invalid_stock_or_name"
    assert detail["message"] == "请输入有效的股票代码或股票名称"


def test_empty_stock_code_after_whitespace_filter() -> None:
    with pytest.raises(HTTPException) as exc_info:
        trigger_analysis(
            request=_analyze_request(stock_code="   ", stock_codes=["  "]),
            config=SimpleNamespace(),
        )
    detail = exc_info.value.detail
    assert detail["error"] == "empty_stock_code"
    assert "空白" in detail["message"]


def test_analysis_batch_limit_exceeded_includes_max_param() -> None:
    codes = [f"{600000 + i}" for i in range(51)]
    with patch("api.v1.endpoints.analysis.is_code_like", return_value=True), patch(
        "api.v1.endpoints.analysis.resolve_index_stock_code_for_analysis",
        side_effect=lambda c: c,
    ), patch(
        "api.v1.endpoints.analysis.normalize_stock_code",
        side_effect=lambda c: c,
    ):
        with pytest.raises(HTTPException) as exc_info:
            trigger_analysis(
                request=_analyze_request(stock_codes=codes),
                config=SimpleNamespace(),
            )
    detail = exc_info.value.detail
    assert detail["error"] == "analysis_batch_limit_exceeded"
    assert detail["params"]["max_batch_size"] == 50
    assert "50" in detail["message"]


def test_sync_mode_batch_unsupported() -> None:
    with patch("api.v1.endpoints.analysis.is_code_like", return_value=True), patch(
        "api.v1.endpoints.analysis.resolve_index_stock_code_for_analysis",
        side_effect=lambda c: c,
    ), patch(
        "api.v1.endpoints.analysis.normalize_stock_code",
        side_effect=lambda c: c,
    ):
        with pytest.raises(HTTPException) as exc_info:
            trigger_analysis(
                request=_analyze_request(
                    stock_codes=["600519", "000858"],
                    async_mode=False,
                ),
                config=SimpleNamespace(),
            )
    detail = exc_info.value.detail
    assert detail["error"] == "sync_mode_batch_unsupported"
    assert "async_mode=true" in detail["message"]


def test_stocks_empty_and_invalid_code_stable_codes() -> None:
    with pytest.raises(HTTPException) as empty:
        _validate_and_normalize_stock_code("   ")
    assert empty.value.detail["error"] == "empty_stock_code"
    assert empty.value.detail["message"] == "股票代码不能为空"

    with pytest.raises(HTTPException) as invalid:
        _validate_and_normalize_stock_code("!!!")
    assert invalid.value.detail["error"] == "invalid_stock_code"
    assert invalid.value.detail["params"]["stock_code"] == "!!!"
    assert "不是合法的股票代码格式" in invalid.value.detail["message"]
