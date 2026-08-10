# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Offline demo analysis fixture contract tests."""

from __future__ import annotations

import pytest

from src.services.demo_analysis_fixture import DEMO_STOCK_CODE, build_demo_analysis


def test_demo_fixture_is_always_sample_and_offline() -> None:
    zh = build_demo_analysis(report_language="zh")
    en = build_demo_analysis(report_language="en")
    ko = build_demo_analysis(report_language="ko")
    assert zh["is_sample"] is True
    assert en["is_sample"] is True
    assert ko["is_sample"] is True
    assert zh["stock_code"] == DEMO_STOCK_CODE
    assert "示例" in zh["sample_banner"]
    assert "sample" in en["sample_banner"].lower()
    assert zh["report"]["meta"]["model_used"] == "demo-fixture/offline"
    assert en["report"]["summary"]["action"] == "watch"
    assert ko["report"]["summary"]["sentiment_label"] == "중립"


def test_demo_fixture_rejects_unsupported_report_language() -> None:
    with pytest.raises(ValueError):
        build_demo_analysis(report_language="ja")
