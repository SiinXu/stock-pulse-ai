# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Deterministic chart-reading tests with vision mocked at the provider boundary."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.services.chart_reading_service import (
    CHART_DISCLAIMER,
    CHART_READ_PROMPT,
    CHART_SCHEMA_VERSION,
    ChartReadingService,
    assess_vision_readiness,
    read_chart_bytes,
    read_chart_path,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "multimodal"
SAMPLE_PNG = FIXTURES / "sample_chart.png"

MOCK_CHART_JSON = {
    "chart_type": "candlestick",
    "symbol_hints": ["600519"],
    "timeframe_hint": "1D",
    "trend": "up",
    "key_levels": [
        {"label": "support", "value": "1800", "confidence": "high"},
        {"label": "resistance", "value": "2000", "confidence": "medium"},
    ],
    "observations": ["Higher lows visible on recent candles"],
    "confidence": "high",
}


def _png_bytes() -> bytes:
    return SAMPLE_PNG.read_bytes()


def test_chart_read_prompt_is_stable_contract() -> None:
    assert "Return ONLY a valid JSON object" in CHART_READ_PROMPT
    assert "chart_type" in CHART_READ_PROMPT
    assert "buy/sell" in CHART_READ_PROMPT.lower() or "non-advisory" in CHART_READ_PROMPT


def test_read_chart_bytes_with_injected_vision() -> None:
    def fake_vision(_b64: str, _mime: str) -> str:
        return json.dumps(MOCK_CHART_JSON)

    result = read_chart_bytes(
        _png_bytes(),
        "image/png",
        vision_caller=fake_vision,
    )
    assert result["schema_version"] == CHART_SCHEMA_VERSION
    assert result["status"] == "available"
    assert result["chart_type"] == "candlestick"
    assert result["trend"] == "up"
    assert result["symbol_hints"] == ["600519"]
    assert result["key_levels"][0]["value"] == "1800"
    assert result["disclaimer"] == CHART_DISCLAIMER


def test_read_chart_degrades_without_vision_model() -> None:
    cfg = SimpleNamespace(
        vision_model="",
        openai_vision_model=None,
        litellm_model="",
        gemini_api_keys=[],
        anthropic_api_keys=[],
        openai_api_keys=[],
        gemini_model=None,
        anthropic_model=None,
        openai_model=None,
        llm_model_list=[],
    )
    with patch("src.services.chart_reading_service.get_config", return_value=cfg), patch(
        "src.services.image_stock_extractor.get_config", return_value=cfg
    ):
        readiness = assess_vision_readiness(cfg)
        assert readiness["ready"] is False
        result = read_chart_bytes(_png_bytes(), "image/png")
    assert result["status"] == "unavailable"
    assert result["reason_code"] == "vision_model_unavailable"


def test_read_chart_rejects_bad_mime() -> None:
    result = read_chart_bytes(b"not-an-image", "application/pdf")
    assert result["status"] == "unavailable"
    assert result["reason_code"] == "unsupported_type"


def test_read_chart_path_under_root(tmp_path: Path) -> None:
    chart = tmp_path / "chart.png"
    chart.write_bytes(_png_bytes())

    def fake_vision(_b64: str, _mime: str) -> str:
        return json.dumps(MOCK_CHART_JSON)

    result = read_chart_path(
        "chart.png",
        file_root=str(tmp_path),
        vision_caller=fake_vision,
    )
    assert result["status"] == "available"
    assert result["chart_type"] == "candlestick"


def test_litellm_completion_patch_target_for_chart_vision() -> None:
    cfg = SimpleNamespace(
        vision_model="openai/gpt-4o-mini",
        openai_vision_model=None,
        litellm_model="",
        gemini_api_keys=[],
        anthropic_api_keys=[],
        openai_api_keys=["sk-test-key-12345678"],
        gemini_model=None,
        anthropic_model=None,
        openai_model="gpt-4o-mini",
        openai_base_url=None,
        llm_model_list=[],
    )
    msg = MagicMock()
    msg.content = json.dumps(MOCK_CHART_JSON)
    choice = MagicMock()
    choice.message = msg
    response = MagicMock()
    response.choices = [choice]

    with patch("src.services.chart_reading_service.get_config", return_value=cfg), patch(
        "src.services.image_stock_extractor.get_config", return_value=cfg
    ), patch(
        "src.services.chart_reading_service.litellm.completion",
        return_value=response,
    ) as mock_completion, patch(
        "src.services.chart_reading_service.guard_litellm_outbound_call"
    ):
        result = read_chart_bytes(_png_bytes(), "image/png")

    assert result["status"] == "available"
    mock_completion.assert_called_once()
    kwargs = mock_completion.call_args.kwargs
    assert kwargs["model"]
    content = kwargs["messages"][0]["content"]
    assert content[0]["type"] == "text"
    assert "chart" in content[0]["text"].lower() or "JSON" in content[0]["text"]
    assert content[1]["type"] == "image_url"


def test_service_wrapper() -> None:
    service = ChartReadingService(
        vision_caller=lambda _b, _m: json.dumps(MOCK_CHART_JSON),
    )
    result = service.read_bytes(_png_bytes(), "image/png")
    assert result["status"] == "available"
