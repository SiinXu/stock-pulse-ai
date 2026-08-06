# -*- coding: utf-8 -*-
"""Regression: get_stock_info tool schema must not look A-share-only (upstream 9b1b4bb8)."""

from src.agent.tools.data_tools import get_stock_info_tool


def test_get_stock_info_parameter_description_covers_us_and_hk() -> None:
    params = {param.name: param.description for param in get_stock_info_tool.parameters}
    description = params["stock_code"]
    lowered = description.lower()
    assert "600519" in description
    assert "aapl" in lowered
    # Must not present the tool as A-share-only (agents skip US/HK when it does).
    assert "a-share stock code, e.g." not in lowered
    assert "us" in lowered or "aapl" in lowered
    assert "hk" in lowered or "00700" in description or "hk00700" in lowered
