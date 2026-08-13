# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Deterministic chart-reading tests with vision mocked at the provider boundary."""

from __future__ import annotations

import json
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.services import chart_reading_service as chart_service
from src.services.chart_reading_service import (
    CHART_DISCLAIMER,
    CHART_MODEL_DIRECTIVE,
    CHART_READ_PROMPT,
    CHART_SCHEMA_VERSION,
    ChartReadingService,
    assess_vision_readiness,
    clamp_chart_read_timeout,
    read_chart_bytes,
    read_chart_path,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "multimodal"
SAMPLE_PNG = FIXTURES / "sample_chart.png"
GARBAGE_SOLID = FIXTURES / "garbage_solid.png"
GARBAGE_TINY = FIXTURES / "garbage_tiny.png"

MOCK_CHART_JSON = {
    "is_market_chart": True,
    "chart_type": "candlestick",
    "symbol_hints": ["600519"],
    "timeframe_hint": "1D",
    "trend": "up",
    "patterns": [{"name": "higher_highs", "confidence": "high"}],
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
    assert "is_market_chart" in CHART_READ_PROMPT
    assert "patterns" in CHART_READ_PROMPT
    assert "buy/sell" in CHART_READ_PROMPT.lower() or "non-advisory" in CHART_READ_PROMPT


def test_clamp_chart_read_timeout() -> None:
    assert clamp_chart_read_timeout(None) == 30
    assert clamp_chart_read_timeout(0) == 1
    assert clamp_chart_read_timeout(999) == 120
    assert clamp_chart_read_timeout(45) == 45


def test_timeout_config_fallback_records_a_safe_diagnostic(caplog) -> None:
    with (
        patch.object(
            chart_service,
            "_resolve_process_config",
            side_effect=RuntimeError("sensitive config detail"),
        ),
        caplog.at_level("DEBUG", logger="src.services.chart_reading_service"),
    ):
        timeout = chart_service._timeout_from_config()

    assert timeout == 30
    assert "error_code=chart_read_timeout_config_unavailable" in caplog.text
    assert "exception_type=RuntimeError" in caplog.text
    assert "sensitive config detail" not in caplog.text


def test_read_chart_bytes_with_injected_vision() -> None:
    def fake_vision(_b64: str, _mime: str) -> str:
        return json.dumps(MOCK_CHART_JSON)

    result = read_chart_bytes(
        _png_bytes(),
        "image/png",
        vision_caller=fake_vision,
        timeout_seconds=30,
    )
    assert result["schema_version"] == CHART_SCHEMA_VERSION
    assert result["status"] == "available"
    assert result["chart_type"] == "candlestick"
    assert result["trend"] == "up"
    assert result["patterns"][0]["name"] == "higher_highs"
    assert result["symbol_hints"] == ["600519"]
    assert result["key_levels"][0]["value"] == "1800"
    assert result["disclaimer"] == CHART_DISCLAIMER
    assert result["model_directive"] == CHART_MODEL_DIRECTIVE
    assert result["trust"]["classification"] == "untrusted_user_document"
    assert result["trust"]["authoritative_for_decisions"] is False
    assert result["trust"]["observation_not_fact"] is True
    assert result["content"]["observation_not_fact"] is True
    assert result["content"]["decision_authority"] is False
    assert result["timeout_seconds"] == 30


def test_redacts_sensitive_observation_text() -> None:
    payload = dict(MOCK_CHART_JSON)
    payload["observations"] = [
        "Contact trader@example.com with api_key=sk-live-ABCDEF123456",
        "Account number: ACCT-998877",
    ]
    payload["symbol_hints"] = ["secret=hunter2"]

    def fake_vision(_b64: str, _mime: str) -> str:
        return json.dumps(payload)

    result = read_chart_bytes(_png_bytes(), "image/png", vision_caller=fake_vision)
    blob = json.dumps(result, ensure_ascii=False)
    assert "trader@example.com" not in blob
    assert "sk-live-ABCDEF123456" not in blob
    assert "ACCT-998877" not in blob
    assert result["content"]["redacted"] is True
    assert result["status"] == "available"


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
        chart_read_timeout_seconds=30,
    )
    with patch(
        "src.services.chart_reading_service._resolve_process_config", return_value=cfg
    ), patch(
        "src.services.image_stock_extractor.get_config", return_value=cfg
    ), patch(
        "src.services.image_stock_extractor._resolve_vision_model", return_value=""
    ):
        readiness = assess_vision_readiness(cfg)
        assert readiness["ready"] is False
        result = read_chart_bytes(_png_bytes(), "image/png")
    assert result["status"] == "unavailable"
    assert result["reason_code"] == "vision_model_unavailable"
    assert result["trust"]["classification"] == "untrusted_user_document"


def test_read_chart_rejects_bad_mime() -> None:
    result = read_chart_bytes(b"not-an-image", "application/pdf")
    assert result["status"] == "rejected"
    assert result["reason_code"] == "unsupported_type"


def test_garbage_solid_image_is_explicitly_rejected() -> None:
    """Counterexample: solid non-chart image must not become soft available facts."""
    result = read_chart_bytes(
        GARBAGE_SOLID.read_bytes(),
        "image/png",
        vision_caller=lambda _b, _m: json.dumps(MOCK_CHART_JSON),
    )
    assert result["status"] == "rejected"
    assert result["reason_code"] == "garbage_image"
    assert result["trust"]["authoritative_for_decisions"] is False
    assert result["content"]["observation_not_fact"] is True


def test_garbage_tiny_image_is_explicitly_rejected() -> None:
    result = read_chart_bytes(
        GARBAGE_TINY.read_bytes(),
        "image/png",
        vision_caller=lambda _b, _m: json.dumps(MOCK_CHART_JSON),
    )
    assert result["status"] == "rejected"
    assert result["reason_code"] == "garbage_image"


def test_vision_not_a_chart_is_explicitly_rejected() -> None:
    def fake_vision(_b64: str, _mime: str) -> str:
        return json.dumps(
            {
                "is_market_chart": False,
                "chart_type": "unknown",
                "symbol_hints": [],
                "timeframe_hint": "unknown",
                "trend": "unclear",
                "patterns": [],
                "key_levels": [{"label": "support", "value": "1", "confidence": "high"}],
                "observations": ["This is a photo of a cat, not a price chart."],
                "confidence": "low",
            }
        )

    result = read_chart_bytes(_png_bytes(), "image/png", vision_caller=fake_vision)
    assert result["status"] == "rejected"
    assert result["reason_code"] == "not_a_chart"
    assert result["key_levels"] == []
    assert result["patterns"] == []
    assert result["confidence"] == "low"
    assert any("cat" in obs.lower() or "not" in obs.lower() for obs in result["observations"])


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
    assert result["patterns"]


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
        chart_read_timeout_seconds=25,
    )
    msg = MagicMock()
    msg.content = json.dumps(MOCK_CHART_JSON)
    choice = MagicMock()
    choice.message = msg
    response = MagicMock()
    response.choices = [choice]

    with patch(
        "src.services.chart_reading_service._resolve_process_config", return_value=cfg
    ), patch(
        "src.services.image_stock_extractor.get_config", return_value=cfg
    ), patch(
        "src.services.image_stock_extractor._resolve_vision_model",
        return_value="openai/gpt-4o-mini",
    ), patch(
        "src.services.chart_reading_service.litellm.completion",
        return_value=response,
    ) as mock_completion, patch(
        "src.services.chart_reading_service.guard_litellm_outbound_call"
    ):
        result = read_chart_bytes(_png_bytes(), "image/png", timeout_seconds=25)

    assert result["status"] == "available"
    mock_completion.assert_called_once()
    kwargs = mock_completion.call_args.kwargs
    assert 0 < kwargs["timeout"] <= 25
    content = kwargs["messages"][0]["content"]
    assert content[0]["type"] == "text"
    assert "chart" in content[0]["text"].lower() or "JSON" in content[0]["text"]
    assert content[1]["type"] == "image_url"


def test_service_wrapper() -> None:
    service = ChartReadingService(
        vision_caller=lambda _b, _m: json.dumps(MOCK_CHART_JSON),
        timeout_seconds=40,
    )
    result = service.read_bytes(_png_bytes(), "image/png")
    assert result["status"] == "available"
    assert result["timeout_seconds"] == 40


def _vision_ready_cfg(timeout_seconds: int = 30) -> SimpleNamespace:
    return SimpleNamespace(
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
        chart_read_timeout_seconds=timeout_seconds,
    )


def _chart_vision_runtime(cfg: SimpleNamespace, completion, clock: dict):
    stack = ExitStack()
    stack.enter_context(
        patch(
            "src.services.chart_reading_service._resolve_process_config",
            return_value=cfg,
        )
    )
    stack.enter_context(
        patch("src.services.image_stock_extractor.get_config", return_value=cfg)
    )
    stack.enter_context(
        patch(
            "src.services.image_stock_extractor._resolve_vision_model",
            return_value="openai/gpt-4o-mini",
        )
    )
    stack.enter_context(
        patch(
            "src.services.chart_reading_service.litellm.completion",
            side_effect=completion,
        )
    )
    stack.enter_context(
        patch("src.services.chart_reading_service.guard_litellm_outbound_call")
    )
    stack.enter_context(
        patch(
            "src.services.chart_reading_service.time.monotonic",
            side_effect=lambda: clock["now"],
        )
    )
    stack.enter_context(
        patch(
            "src.services.chart_reading_service.time.sleep",
            side_effect=lambda seconds: clock.__setitem__(
                "now", clock["now"] + float(seconds)
            ),
        )
    )
    return stack


def test_wall_clock_timeout_is_shared_across_retries_not_multiplied() -> None:
    """A hung provider must not get a fresh full timeout on each retry."""
    cfg = _vision_ready_cfg(30)
    clock = {"now": 1_000.0}
    call_timeouts: list[float] = []

    def fake_completion(**kwargs):
        budget = float(kwargs["timeout"])
        call_timeouts.append(budget)
        clock["now"] += budget
        raise ValueError("vision_empty_response")

    with _chart_vision_runtime(cfg, fake_completion, clock):
        result = read_chart_bytes(_png_bytes(), "image/png", timeout_seconds=30)

    assert call_timeouts == [30]
    assert result["status"] == "unavailable"
    assert result["reason_code"] == "vision_timeout"
    assert result["duration_ms"] >= 30_000
    assert result["timeout_seconds"] == 30


def test_retries_use_remaining_wall_clock_budget() -> None:
    cfg = _vision_ready_cfg(30)
    clock = {"now": 1_000.0}
    call_timeouts: list[float] = []

    def fake_completion(**kwargs):
        call_timeouts.append(float(kwargs["timeout"]))
        raise RuntimeError("transient provider error")

    with _chart_vision_runtime(cfg, fake_completion, clock):
        result = read_chart_bytes(_png_bytes(), "image/png", timeout_seconds=30)

    assert len(call_timeouts) == 3
    assert call_timeouts[0] == 30
    assert call_timeouts[1] == pytest.approx(29)
    assert call_timeouts[2] == pytest.approx(27)
    assert result["status"] == "degraded"
    assert result["reason_code"] == "vision_provider_failed"
    assert result["duration_ms"] == pytest.approx(3_000, abs=5)
