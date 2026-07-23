# -*- coding: utf-8 -*-
"""Tests for image_stock_extractor Vision LLM layer.

Covers:
- _resolve_vision_model(): priority chain (vision_model > openai_vision_model > litellm_model > inferred)
- _get_api_keys_for_model(): provider key routing
- _call_litellm_vision(): request payload / timeout / error handling
- extract_stock_codes_from_image(): magic bytes check, parsing
"""
import io
import logging
import sys
from unittest.mock import MagicMock

# Stub out litellm and heavy chain-imports before any project code is loaded,
# so these tests run without the package installed in this environment.
if "litellm" not in sys.modules:
    sys.modules["litellm"] = MagicMock()
# Stub google.generativeai if absent (imported transitively by some modules)
for _stub in ("google.generativeai", "google.genai", "anthropic"):
    if _stub not in sys.modules:
        sys.modules[_stub] = MagicMock()

import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers
from unittest.mock import patch

from api.v1.endpoints.stocks import extract_from_image
from src.services.image_stock_extractor import (
    _resolve_vision_model,
    _get_api_keys_for_model,
    _call_litellm_vision,
    _parse_codes_from_text,
    _parse_items_from_text,
    extract_stock_codes_from_image,
    VISION_API_TIMEOUT,
)
from src.config import Config
from src.security.outbound_policy import OutboundPolicyError
from src.llm.model_ref import encode_model_ref


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_GEMINI_KEY = "sk-gemini-testkey-1234"   # len >= 8
_ANTHROPIC_KEY = "sk-anthropic-testkey-1234"
_OPENAI_KEY = "sk-openai-testkey-1234"


def _cfg(**kwargs) -> Config:
    """Minimal Config for extractor tests."""
    defaults = dict(
        stock_list=["600519"],
        tushare_token=None,
        llm_model_list=[],
        llm_channels=[],
        litellm_config_path=None,
        litellm_model="",
        litellm_fallback_models=[],
        vision_model="",
        vision_provider_priority="gemini,anthropic,openai",
        gemini_api_keys=[],
        gemini_model="gemini-3.1-pro-preview",
        anthropic_api_keys=[],
        anthropic_model="claude-sonnet-4-6",
        openai_api_keys=[],
        openai_model="gpt-5.5",
        openai_base_url=None,
        openai_vision_model=None,
        deepseek_api_keys=[],
        config_validate_mode="warn",
    )
    defaults.update(kwargs)
    return Config(**defaults)


def _make_jpeg_bytes() -> bytes:
    """Return minimal valid JPEG bytes (correct magic bytes + padding)."""
    return b"\xff\xd8\xff" + b"\x00" * 20


# ---------------------------------------------------------------------------
# _resolve_vision_model
# ---------------------------------------------------------------------------

class TestResolveVisionModel:
    def test_uses_vision_model_first(self):
        cfg = _cfg(vision_model="gemini/gemini-2.0-flash", openai_vision_model="openai/gpt-4o")
        with patch("src.services.image_stock_extractor.get_config", return_value=cfg):
            assert _resolve_vision_model() == "gemini/gemini-2.0-flash"

    def test_uses_openai_vision_model_first(self):
        cfg = _cfg(vision_model="", openai_vision_model="openai/gpt-4o", litellm_model="gemini/gemini-2.5-flash")
        with patch("src.services.image_stock_extractor.get_config", return_value=cfg):
            assert _resolve_vision_model() == "openai/gpt-4o"

    def test_falls_back_to_litellm_model(self):
        cfg = _cfg(openai_vision_model=None, litellm_model="gemini/gemini-2.5-flash")
        with patch("src.services.image_stock_extractor.get_config", return_value=cfg):
            assert _resolve_vision_model() == "gemini/gemini-2.5-flash"

    def test_infers_gemini_from_api_keys(self):
        cfg = _cfg(openai_vision_model=None, litellm_model="", gemini_api_keys=[_GEMINI_KEY])
        with patch("src.services.image_stock_extractor.get_config", return_value=cfg):
            assert _resolve_vision_model() == "gemini/gemini-3.1-pro-preview"

    def test_infers_anthropic_when_no_gemini_key(self):
        cfg = _cfg(openai_vision_model=None, litellm_model="", gemini_api_keys=[], anthropic_api_keys=[_ANTHROPIC_KEY])
        with patch("src.services.image_stock_extractor.get_config", return_value=cfg):
            result = _resolve_vision_model()
            assert result.startswith("anthropic/")

    def test_infers_openai_when_only_openai_key(self):
        cfg = _cfg(openai_vision_model=None, litellm_model="", openai_api_keys=[_OPENAI_KEY])
        with patch("src.services.image_stock_extractor.get_config", return_value=cfg):
            result = _resolve_vision_model()
            assert result.startswith("openai/")

    def test_keeps_gemini3_vision_model(self):
        cfg = _cfg(openai_vision_model="gemini/gemini-3.1-pro-preview")
        with patch("src.services.image_stock_extractor.get_config", return_value=cfg):
            assert _resolve_vision_model() == "gemini/gemini-3.1-pro-preview"

    def test_returns_empty_when_no_model_and_no_keys(self):
        cfg = _cfg(openai_vision_model=None, litellm_model="", gemini_api_keys=[], anthropic_api_keys=[], openai_api_keys=[])
        with patch("src.services.image_stock_extractor.get_config", return_value=cfg):
            assert _resolve_vision_model() == ""


# ---------------------------------------------------------------------------
# _get_api_keys_for_model
# ---------------------------------------------------------------------------

class TestGetApiKeysForModel:
    def test_returns_gemini_keys_for_gemini_model(self):
        cfg = _cfg(gemini_api_keys=[_GEMINI_KEY], openai_api_keys=[_OPENAI_KEY])
        keys = _get_api_keys_for_model("gemini/gemini-2.0-flash", cfg)
        assert _GEMINI_KEY in keys

    def test_returns_anthropic_keys_for_anthropic_model(self):
        cfg = _cfg(anthropic_api_keys=[_ANTHROPIC_KEY], openai_api_keys=[_OPENAI_KEY])
        keys = _get_api_keys_for_model("anthropic/claude-3-5-sonnet-20241022", cfg)
        assert _ANTHROPIC_KEY in keys

    def test_returns_openai_keys_for_openai_model(self):
        cfg = _cfg(openai_api_keys=[_OPENAI_KEY], gemini_api_keys=[_GEMINI_KEY])
        keys = _get_api_keys_for_model("openai/gpt-4o-mini", cfg)
        assert _OPENAI_KEY in keys

    def test_filters_out_short_keys(self):
        cfg = _cfg(gemini_api_keys=["short", _GEMINI_KEY])
        keys = _get_api_keys_for_model("gemini/gemini-2.0-flash", cfg)
        assert "short" not in keys
        assert _GEMINI_KEY in keys

    def test_model_ref_uses_only_exact_connection_keys(self):
        model_ref = encode_model_ref("work", "openai/gpt-4o")
        cfg = _cfg(
            openai_api_keys=[_OPENAI_KEY],
            llm_model_list=[
                {
                    "model_name": model_ref,
                    "litellm_params": {
                        "model": "openai/gpt-4o",
                        "api_key": "sk-work-exact-key",
                    },
                }
            ],
        )
        assert _get_api_keys_for_model(model_ref, cfg) == ["sk-work-exact-key"]


# ---------------------------------------------------------------------------
# _call_litellm_vision
# ---------------------------------------------------------------------------

class TestCallLitellmVision:
    def _good_response(self):
        msg = MagicMock()
        msg.content = '["600519"]'
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]
        return resp

    def test_calls_litellm_with_image(self):
        cfg = _cfg(openai_vision_model=None, litellm_model="", gemini_api_keys=[_GEMINI_KEY])
        with patch("src.services.image_stock_extractor.get_config", return_value=cfg), \
             patch("src.services.image_stock_extractor.litellm.completion",
                   return_value=self._good_response()) as mock_comp:
            result = _call_litellm_vision("base64data", "image/jpeg")
            assert result == '["600519"]'
            mock_comp.assert_called_once()
            kwargs = mock_comp.call_args[1]
            assert kwargs["timeout"] == VISION_API_TIMEOUT
            assert kwargs["max_tokens"] == 1024

    def test_openai_model_uses_api_base_without_sponsored_headers(self):
        cfg = _cfg(
            openai_vision_model="openai/gpt-4o-mini",
            openai_api_keys=[_OPENAI_KEY],
            openai_base_url="https://aihubmix.com/v1",
        )
        with patch("src.services.image_stock_extractor.get_config", return_value=cfg), \
             patch("src.services.image_stock_extractor.litellm.completion",
                   return_value=self._good_response()) as mock_comp:
            _call_litellm_vision("b64", "image/jpeg")
            kwargs = mock_comp.call_args[1]
            assert kwargs["api_base"] == "https://aihubmix.com/v1"
            assert "extra_headers" not in kwargs

    def test_model_ref_uses_exact_connection_deployment(self):
        model_ref = encode_model_ref("work", "openai/gpt-4o")
        cfg = _cfg(
            vision_model=model_ref,
            openai_api_keys=[_OPENAI_KEY],
            llm_model_list=[
                {
                    "model_name": model_ref,
                    "litellm_params": {
                        "model": "openai/gpt-4o",
                        "api_key": "sk-work-exact-key",
                        "api_base": "https://work.example/v1",
                        "extra_headers": {"X-Workspace": "work"},
                    },
                }
            ],
        )
        with patch("src.services.image_stock_extractor.get_config", return_value=cfg), \
             patch("src.services.image_stock_extractor.litellm.completion",
                   return_value=self._good_response()) as mock_comp:
            _call_litellm_vision("b64", "image/jpeg")

        kwargs = mock_comp.call_args.kwargs
        assert kwargs["model"] == "openai/gpt-4o"
        assert kwargs["api_key"] == "sk-work-exact-key"
        assert kwargs["api_base"] == "https://work.example/v1"
        assert kwargs["extra_headers"] == {"X-Workspace": "work"}

    def test_private_connection_base_is_rejected_before_completion(self):
        model_ref = encode_model_ref("private", "openai/gpt-4o")
        cfg = _cfg(
            vision_model=model_ref,
            llm_model_list=[
                {
                    "model_name": model_ref,
                    "litellm_params": {
                        "model": "openai/gpt-4o",
                        "api_key": "sk-private-exact-key",
                        "api_base": "http://127.0.0.1:8080/v1",
                    },
                }
            ],
        )
        with patch("src.services.image_stock_extractor.get_config", return_value=cfg), \
             patch("src.services.image_stock_extractor.litellm.completion") as mock_comp:
            with pytest.raises(OutboundPolicyError, match="private_ip_blocked"):
                _call_litellm_vision("b64", "image/jpeg")

        mock_comp.assert_not_called()

    def test_raises_when_model_not_configured(self):
        cfg = _cfg(openai_vision_model=None, litellm_model="", gemini_api_keys=[], anthropic_api_keys=[], openai_api_keys=[])
        with patch("src.services.image_stock_extractor.get_config", return_value=cfg):
            with pytest.raises(ValueError, match="未配置 Vision API"):
                _call_litellm_vision("b64", "image/jpeg")

    def test_raises_when_no_key_for_model(self):
        cfg = _cfg(openai_vision_model="openai/gpt-4o-mini", openai_api_keys=[])
        with patch("src.services.image_stock_extractor.get_config", return_value=cfg):
            with pytest.raises(ValueError, match="No API key found"):
                _call_litellm_vision("b64", "image/jpeg")

    def test_raises_when_completion_returns_empty(self):
        cfg = _cfg(gemini_api_keys=[_GEMINI_KEY])
        empty_resp = MagicMock()
        empty_resp.choices = []
        with patch("src.services.image_stock_extractor.get_config", return_value=cfg), \
             patch("src.services.image_stock_extractor.litellm.completion",
                   return_value=empty_resp):
            with pytest.raises(ValueError, match="returned empty response"):
                _call_litellm_vision("b64", "image/jpeg")

    def test_rejects_hermes_route_without_calling_litellm(self):
        cfg = _cfg(
            vision_model="openai/hermes-agent",
            llm_model_list=[
                {
                    "model_name": "openai/hermes-agent",
                    "litellm_params": {
                        "model": "openai/hermes-agent",
                        "api_key": "sk-hermes-test-value",
                        "api_base": "http://127.0.0.1:8642/v1",
                    },
                    "model_info": {"dsa_channel": "hermes"},
                }
            ],
            openai_api_keys=[_OPENAI_KEY],
        )
        with patch("src.services.image_stock_extractor.get_config", return_value=cfg), \
             patch("src.services.image_stock_extractor.litellm.completion") as mock_comp:
            with pytest.raises(ValueError, match="Hermes Vision"):
                _call_litellm_vision("b64", "image/jpeg")
        mock_comp.assert_not_called()

    def test_rejects_bare_hermes_route_without_calling_litellm(self):
        cfg = _cfg(
            vision_model="hermes-agent",
            llm_model_list=[
                {
                    "model_name": "openai/hermes-agent",
                    "litellm_params": {
                        "model": "openai/hermes-agent",
                        "api_key": "sk-hermes-test-value",
                        "api_base": "http://127.0.0.1:8642/v1",
                    },
                    "model_info": {"dsa_channel": "hermes"},
                }
            ],
            openai_api_keys=[_OPENAI_KEY],
        )
        with patch("src.services.image_stock_extractor.get_config", return_value=cfg), \
             patch("src.services.image_stock_extractor.litellm.completion") as mock_comp:
            with pytest.raises(ValueError, match="Hermes Vision"):
                _call_litellm_vision("b64", "image/jpeg")
        mock_comp.assert_not_called()

    def test_rejects_bare_mixed_hermes_route_without_calling_litellm(self):
        cfg = _cfg(
            vision_model="shared-route",
            llm_model_list=[
                {
                    "model_name": "openai/shared-route",
                    "litellm_params": {
                        "model": "openai/hermes-agent",
                        "api_key": "sk-hermes-test-value",
                        "api_base": "http://127.0.0.1:8642/v1",
                    },
                    "model_info": {"dsa_channel": "hermes"},
                },
                {
                    "model_name": "openai/shared-route",
                    "litellm_params": {
                        "model": "openai/gpt-4o-mini",
                        "api_key": _OPENAI_KEY,
                    },
                },
            ],
            openai_api_keys=[_OPENAI_KEY],
        )
        with patch("src.services.image_stock_extractor.get_config", return_value=cfg), \
             patch("src.services.image_stock_extractor.litellm.completion") as mock_comp:
            with pytest.raises(ValueError, match="Hermes Vision"):
                _call_litellm_vision("b64", "image/jpeg")
        mock_comp.assert_not_called()


# ---------------------------------------------------------------------------
# _parse_codes_from_text
# ---------------------------------------------------------------------------

class TestParseCodesFromText:
    def test_parses_json_array(self):
        text = '["600519", "300750", "AAPL"]'
        assert _parse_codes_from_text(text) == ["600519", "300750", "AAPL"]

    def test_parses_fallback_from_plain_text(self):
        text = "关注 600519、300750 和 AAPL。"
        codes = _parse_codes_from_text(text)
        assert "600519" in codes
        assert "300750" in codes
        assert "AAPL" in codes

    def test_filters_fake_codes_in_legacy_format(self):
        """Legacy JSON array or regex fallback should not include CODE, NAME, HIGH, JSON, etc."""
        assert _parse_codes_from_text('["CODE","159887","NAME","512880","HIGH"]') == ["159887", "512880"]
        assert _parse_codes_from_text('["JSON","159887","512880"]') == ["159887", "512880"]
        text = "CODE 159887 NAME 512880 HIGH"
        codes = _parse_codes_from_text(text)
        assert "CODE" not in codes
        assert "NAME" not in codes
        assert "HIGH" not in codes
        assert "159887" in codes
        assert "512880" in codes


class TestParseItemsFromText:
    def test_parses_new_format(self):
        text = '[{"code":"600519","name":"贵州茅台","confidence":"high"},{"code":"00700","name":"腾讯控股","confidence":"medium"}]'
        items = _parse_items_from_text(text)
        assert len(items) == 2
        assert items[0] == ("600519", "贵州茅台", "high")
        assert items[1] == ("00700", "腾讯控股", "medium")

    def test_fallback_to_legacy_format(self):
        text = '["600519", "300750"]'
        items = _parse_items_from_text(text)
        assert [(i[0], i[1], i[2]) for i in items] == [("600519", None, "medium"), ("300750", None, "medium")]

    def test_normalizes_invalid_confidence(self):
        text = '[{"code":"600519","name":"茅台","confidence":"invalid"}]'
        items = _parse_items_from_text(text)
        assert items[0][2] == "medium"

    def test_filters_fake_codes_from_llm_field_names(self):
        """LLM sometimes returns JSON field names (CODE, NAME, HIGH) as items; filter them out."""
        text = '[{"code":"CODE","name":"field"},{"code":"159887","name":"ETF"},{"code":"NAME","name":"x"},{"code":"512880","name":"证券ETF"},{"code":"HIGH","name":"y"}]'
        items = _parse_items_from_text(text)
        codes = [i[0] for i in items]
        assert "CODE" not in codes
        assert "NAME" not in codes
        assert "HIGH" not in codes
        assert "159887" in codes
        assert "512880" in codes
        assert len(items) == 2

    def test_parses_markdown_wrapped_json_preserves_names(self):
        """LLM often wraps JSON in ```json...```; strip only opening fence to avoid wiping content."""
        text = '\n\n```json\n[{"code":"159887","name":"银行ETF","confidence":"high"},{"code":"512880","name":"证券ETF","confidence":"high"}]\n```'
        items = _parse_items_from_text(text)
        assert len(items) == 2
        assert items[0] == ("159887", "银行ETF", "high")
        assert items[1] == ("512880", "证券ETF", "high")

    def test_uses_json_repair_when_json_invalid(self):
        text = '[{"code":"600519","name":"贵州茅台","confidence":"high"'
        items = _parse_items_from_text(text)
        assert items == [("600519", "贵州茅台", "high")]


# ---------------------------------------------------------------------------
# extract_stock_codes_from_image (integration smoke)
# ---------------------------------------------------------------------------

class TestExtractStockCodesFromImage:
    def _good_vision_response(self, codes='["600519", "300750"]'):
        msg = MagicMock()
        msg.content = codes
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]
        return resp

    def test_returns_items_and_raw(self):
        cfg = _cfg(gemini_api_keys=[_GEMINI_KEY])
        jpeg = _make_jpeg_bytes()
        with patch("src.services.image_stock_extractor.get_config", return_value=cfg), \
             patch("src.services.image_stock_extractor.litellm.completion",
                   return_value=self._good_vision_response()):
            items, raw = extract_stock_codes_from_image(jpeg, "image/jpeg")
            codes = [i[0] for i in items]
            assert "600519" in codes
            assert "300750" in codes
            assert isinstance(raw, str)

    def test_rejects_unsupported_mime(self):
        jpeg = _make_jpeg_bytes()
        with pytest.raises(ValueError, match="不支持的图片类型"):
            extract_stock_codes_from_image(jpeg, "image/bmp")

    def test_rejects_empty_bytes(self):
        with pytest.raises(ValueError, match="图片内容为空"):
            extract_stock_codes_from_image(b"", "image/jpeg")

    def test_rejects_wrong_magic_bytes(self):
        fake = b"\x00\x00\x00" + b"\x00" * 20  # not a JPEG
        with pytest.raises(ValueError):
            extract_stock_codes_from_image(fake, "image/jpeg")

    def test_wraps_litellm_error_message(self, caplog):
        cfg = _cfg(gemini_api_keys=[_GEMINI_KEY])
        jpeg = _make_jpeg_bytes()
        caplog.set_level(logging.WARNING, logger="src.services.image_stock_extractor")
        with patch("src.services.image_stock_extractor.get_config", return_value=cfg), \
             patch("src.services.image_stock_extractor.litellm.completion",
                   side_effect=RuntimeError(
                       "network down token=super-secret at https://private.example/internal"
                   )):
            with pytest.raises(ValueError, match="^Vision API 调用失败$") as exc_info:
                extract_stock_codes_from_image(jpeg, "image/jpeg")
        assert "super-secret" not in str(exc_info.value)
        assert "private.example" not in str(exc_info.value)
        rendered_logs = "\n".join(record.getMessage() for record in caplog.records)
        assert "super-secret" not in rendered_logs
        assert "private.example" not in rendered_logs
        assert "error_code=vision_provider_failed" in rendered_logs
        assert "exception_type=RuntimeError" in rendered_logs
        assert all(record.exc_info is None for record in caplog.records)

    def test_image_api_hides_litellm_provider_error(self):
        cfg = _cfg(gemini_api_keys=[_GEMINI_KEY])
        upload = UploadFile(
            io.BytesIO(_make_jpeg_bytes()),
            filename="stocks.jpg",
            headers=Headers({"content-type": "image/jpeg"}),
        )
        with patch("src.services.image_stock_extractor.get_config", return_value=cfg), \
             patch(
                 "src.services.image_stock_extractor.litellm.completion",
                 side_effect=RuntimeError(
                     "provider failed token=super-secret at https://private.example/internal"
                 ),
             ), \
             pytest.raises(HTTPException) as exc_info:
            extract_from_image(file=upload, include_raw=False)

        serialized = str(exc_info.value.detail)
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == {
            "error": "extract_failed",
            "message": "Vision API 调用失败",
        }
        assert "super-secret" not in serialized
        assert "private.example" not in serialized
