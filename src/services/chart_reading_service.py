# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Chart understanding via the house Vision path (issue #253 phase 1).

Reuses image validation conventions from ``image_stock_extractor`` (MIME,
magic bytes, size cap) and calls the same LiteLLM vision surface. Degrades
honestly when no vision model/keys are available. Never executes image content.
"""

from __future__ import annotations

import base64
import json
import logging
import random
import sys
import time
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple

from src.config import Config, get_config
from src.llm.errors import guard_litellm_outbound_call
from src.llm.hermes import route_has_hermes
from src.services.image_stock_extractor import (
    ALLOWED_MIME,
    MAX_SIZE_BYTES,
    VISION_API_TIMEOUT,
    _get_api_keys_for_model,
    _resolve_vision_model,
    _verify_image_magic_bytes,
)
from src.services.pdf_parsing_service import resolve_safe_file_path
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

CHART_SCHEMA_VERSION = "chart-reading-v1"
CHART_DISCLAIMER = (
    "Chart reading is a model-assisted visual interpretation for research "
    "support only. Labels, levels, and trends may be approximate or incomplete. "
    "Not investment advice and not a substitute for raw market data."
)

# Keep in sync with docs/chart-read-prompt.md and the PR description when changed.
CHART_READ_PROMPT = """Analyze this financial chart image (K-line/candlestick, line, bar, or similar market chart).

Return ONLY a valid JSON object (no markdown fences, no commentary) with this shape:
{
  "chart_type": "candlestick|line|bar|area|unknown",
  "symbol_hints": ["optional ticker or name strings visible on the chart"],
  "timeframe_hint": "e.g. 1D, 1H, weekly, unknown",
  "trend": "up|down|sideways|unclear",
  "key_levels": [{"label": "support|resistance|ma|other", "value": "as shown or approximate", "confidence": "high|medium|low"}],
  "observations": ["short factual visual observations"],
  "confidence": "high|medium|low"
}

Rules:
- Do not invent prices or indicators that are not visible.
- If the image is not a market chart, set chart_type to "unknown", trend to "unclear", confidence to "low", and explain in observations.
- Cap symbol_hints to 8, key_levels to 12, observations to 12.
- observation strings must be concise and non-advisory (no buy/sell instructions).
"""

_VALID_CHART_TYPES = frozenset({"candlestick", "line", "bar", "area", "unknown"})
_VALID_TRENDS = frozenset({"up", "down", "sideways", "unclear"})
_VALID_CONFIDENCE = frozenset({"high", "medium", "low"})

ALLOWED_CHART_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif"})
MIME_BY_SUFFIX = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


class _LiteLLMPlaceholder:
    completion = None


litellm = sys.modules.get("litellm") or _LiteLLMPlaceholder()

VisionCaller = Callable[[str, str], str]


def _result(
    *,
    status: str,
    reason_code: Optional[str] = None,
    chart_type: str = "unknown",
    symbol_hints: Optional[List[str]] = None,
    timeframe_hint: str = "unknown",
    trend: str = "unclear",
    key_levels: Optional[List[dict[str, Any]]] = None,
    observations: Optional[List[str]] = None,
    confidence: str = "low",
    vision_model: str = "",
    raw_model_text: Optional[str] = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": CHART_SCHEMA_VERSION,
        "status": status,
        "reason_code": reason_code,
        "chart_type": chart_type if chart_type in _VALID_CHART_TYPES else "unknown",
        "symbol_hints": list(symbol_hints or [])[:8],
        "timeframe_hint": (timeframe_hint or "unknown")[:64],
        "trend": trend if trend in _VALID_TRENDS else "unclear",
        "key_levels": list(key_levels or [])[:12],
        "observations": list(observations or [])[:12],
        "confidence": confidence if confidence in _VALID_CONFIDENCE else "low",
        "vision_model": vision_model or "",
        "disclaimer": CHART_DISCLAIMER,
    }
    if raw_model_text is not None:
        payload["raw_model_text"] = raw_model_text[:4000]
    return payload


def _strip_fences(text: str) -> str:
    cleaned = text.strip()
    for start in ("```json", "```"):
        if cleaned.startswith(start):
            cleaned = cleaned[len(start) :].strip()
            break
    end_idx = cleaned.rfind("```")
    if end_idx >= 0:
        cleaned = cleaned[:end_idx].strip()
    return cleaned


def _parse_chart_json(text: str) -> dict[str, Any]:
    cleaned = _strip_fences(text)
    data: Any = None
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        try:
            from json_repair import repair_json

            data = repair_json(cleaned, return_objects=True)
        except Exception:
            data = None
    if not isinstance(data, dict):
        raise ValueError("invalid_chart_json")

    chart_type = str(data.get("chart_type") or "unknown").strip().lower()
    trend = str(data.get("trend") or "unclear").strip().lower()
    confidence = str(data.get("confidence") or "low").strip().lower()
    timeframe_hint = str(data.get("timeframe_hint") or "unknown").strip()

    symbol_hints: list[str] = []
    raw_symbols = data.get("symbol_hints")
    if isinstance(raw_symbols, list):
        for item in raw_symbols[:8]:
            if isinstance(item, str) and item.strip():
                symbol_hints.append(item.strip()[:64])

    key_levels: list[dict[str, Any]] = []
    raw_levels = data.get("key_levels")
    if isinstance(raw_levels, list):
        for item in raw_levels[:12]:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "other").strip()[:64]
            value = str(item.get("value") or "").strip()[:64]
            conf = str(item.get("confidence") or "medium").strip().lower()
            if conf not in _VALID_CONFIDENCE:
                conf = "medium"
            if not value:
                continue
            key_levels.append({"label": label, "value": value, "confidence": conf})

    observations: list[str] = []
    raw_obs = data.get("observations")
    if isinstance(raw_obs, list):
        for item in raw_obs[:12]:
            if isinstance(item, str) and item.strip():
                observations.append(item.strip()[:240])

    return {
        "chart_type": chart_type if chart_type in _VALID_CHART_TYPES else "unknown",
        "symbol_hints": symbol_hints,
        "timeframe_hint": timeframe_hint or "unknown",
        "trend": trend if trend in _VALID_TRENDS else "unclear",
        "key_levels": key_levels,
        "observations": observations,
        "confidence": confidence if confidence in _VALID_CONFIDENCE else "low",
    }


def _call_litellm_chart_vision(
    image_b64: str,
    mime_type: str,
    *,
    api_key: Optional[str] = None,
    prompt: str = CHART_READ_PROMPT,
) -> Tuple[str, str]:
    """Call LiteLLM vision with the chart prompt. Returns (raw_text, model)."""
    global litellm
    cfg = get_config()
    model_list = getattr(cfg, "llm_model_list", []) or []
    model = _resolve_vision_model()
    if not model:
        raise ValueError("vision_model_unavailable")
    if route_has_hermes(model_list, model):
        raise ValueError("hermes_vision_unsupported")

    keys = _get_api_keys_for_model(model, cfg)
    if not keys:
        raise ValueError("vision_api_key_missing")
    key = api_key if api_key and api_key in keys else random.choice(keys)

    deployment_params = next(
        (
            dict(entry.get("litellm_params") or {})
            for entry in model_list
            if str(entry.get("model_name") or "").strip() == model
            and str((entry.get("litellm_params") or {}).get("api_key") or "").strip() == key
        ),
        {},
    )
    wire_model = str(deployment_params.get("model") or model).strip()
    data_url = f"data:{mime_type};base64,{image_b64}"
    call_kwargs: dict = {
        "model": wire_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        "max_tokens": 1024,
        "api_key": key,
        "timeout": VISION_API_TIMEOUT,
    }
    api_base = str(deployment_params.get("api_base") or "").strip()
    if api_base:
        call_kwargs["api_base"] = api_base
    elif not wire_model.startswith(("gemini/", "anthropic/", "vertex_ai/")) and cfg.openai_base_url:
        call_kwargs["api_base"] = cfg.openai_base_url
    if deployment_params.get("extra_headers"):
        call_kwargs["extra_headers"] = dict(deployment_params["extra_headers"])

    if getattr(litellm, "completion", None) is None:
        import litellm as litellm_module

        litellm = litellm_module
    with guard_litellm_outbound_call(
        model=wire_model,
        call_kwargs=call_kwargs,
        model_list=model_list,
    ):
        response = litellm.completion(**call_kwargs)
    if response and response.choices and response.choices[0].message.content:
        return str(response.choices[0].message.content), model
    raise ValueError("vision_empty_response")


def assess_vision_readiness(cfg: Optional[Config] = None) -> dict[str, Any]:
    """Return whether chart vision can run with the current config."""
    cfg = cfg or get_config()
    model = _resolve_vision_model()
    if not model:
        return {"ready": False, "reason": "vision_model_unavailable", "model": ""}
    model_list = getattr(cfg, "llm_model_list", []) or []
    if route_has_hermes(model_list, model):
        return {"ready": False, "reason": "hermes_vision_unsupported", "model": model}
    keys = _get_api_keys_for_model(model, cfg)
    if not keys:
        return {"ready": False, "reason": "vision_api_key_missing", "model": model}
    return {"ready": True, "reason": "ready", "model": model}


def read_chart_bytes(
    image_bytes: bytes,
    mime_type: str,
    *,
    include_raw: bool = False,
    vision_caller: Optional[VisionCaller] = None,
    max_retries: int = 2,
) -> dict[str, Any]:
    """Read a chart image into a structured observation dict."""
    mime_type = (mime_type or "image/png").strip().lower().split(";")[0].strip()
    if mime_type not in ALLOWED_MIME:
        return _result(status="unavailable", reason_code="unsupported_type")
    if not image_bytes:
        return _result(status="unavailable", reason_code="empty_input")
    if len(image_bytes) > MAX_SIZE_BYTES:
        return _result(status="unavailable", reason_code="file_too_large")
    try:
        _verify_image_magic_bytes(image_bytes, mime_type)
    except ValueError:
        return _result(status="unavailable", reason_code="mime_mismatch")

    readiness = assess_vision_readiness()
    if not readiness["ready"] and vision_caller is None:
        return _result(
            status="unavailable",
            reason_code=str(readiness["reason"]),
            vision_model=str(readiness.get("model") or ""),
        )

    image_b64 = base64.b64encode(image_bytes).decode("ascii")
    last_error: Optional[Exception] = None
    attempts = max(1, int(max_retries) + 1)
    for attempt in range(attempts):
        try:
            if vision_caller is not None:
                raw = vision_caller(image_b64, mime_type)
                model = readiness.get("model") or "injected"
            else:
                raw, model = _call_litellm_chart_vision(image_b64, mime_type)
            parsed = _parse_chart_json(raw)
            return _result(
                status="available",
                reason_code=None,
                chart_type=parsed["chart_type"],
                symbol_hints=parsed["symbol_hints"],
                timeframe_hint=parsed["timeframe_hint"],
                trend=parsed["trend"],
                key_levels=parsed["key_levels"],
                observations=parsed["observations"],
                confidence=parsed["confidence"],
                vision_model=str(model or ""),
                raw_model_text=raw if include_raw else None,
            )
        except ValueError as exc:
            last_error = exc
            reason = str(exc)
            if reason in {
                "vision_model_unavailable",
                "vision_api_key_missing",
                "hermes_vision_unsupported",
            }:
                return _result(
                    status="unavailable",
                    reason_code=reason,
                    vision_model=str(readiness.get("model") or ""),
                )
            if reason == "invalid_chart_json":
                return _result(
                    status="degraded",
                    reason_code="invalid_model_output",
                    vision_model=str(readiness.get("model") or ""),
                    observations=["Model returned non-JSON or unusable chart structure."],
                    raw_model_text=None,
                )
            if attempt + 1 < attempts:
                time.sleep(2 ** attempt)
        except Exception as exc:  # broad-exception: fallback_recorded - isolate provider failures.
            last_error = exc
            log_safe_exception(
                logger,
                "Chart vision provider call failed",
                exc,
                error_code="chart_vision_provider_failed",
                level=logging.WARNING,
                context={"attempt": f"{attempt + 1}/{attempts}"},
            )
            if attempt + 1 < attempts:
                time.sleep(2 ** attempt)

    return _result(
        status="degraded",
        reason_code="vision_provider_failed",
        vision_model=str(readiness.get("model") or ""),
        observations=[
            "Vision provider failed after retries; no structured chart reading available."
        ],
    )


def _guess_mime(path: Path, fallback: str = "image/png") -> str:
    return MIME_BY_SUFFIX.get(path.suffix.lower(), fallback)


def read_chart_path(
    file_path: str,
    *,
    file_root: Optional[str] = None,
    include_raw: bool = False,
    vision_caller: Optional[VisionCaller] = None,
) -> dict[str, Any]:
    """Read a chart image from a sanitized local path."""
    try:
        resolved = resolve_safe_file_path(file_path, file_root=file_root)
    except ValueError as exc:
        return _result(status="unavailable", reason_code=str(exc))

    if resolved.suffix.lower() not in ALLOWED_CHART_SUFFIXES:
        return _result(status="unavailable", reason_code="unsupported_type")

    size = resolved.stat().st_size
    if size > MAX_SIZE_BYTES:
        return _result(status="unavailable", reason_code="file_too_large")

    with resolved.open("rb") as handle:
        data = handle.read(MAX_SIZE_BYTES + 1)
    if len(data) > MAX_SIZE_BYTES:
        return _result(status="unavailable", reason_code="file_too_large")

    mime = _guess_mime(resolved)
    return read_chart_bytes(
        data,
        mime,
        include_raw=include_raw,
        vision_caller=vision_caller,
    )


class ChartReadingService:
    """Service wrapper for Agent tools and deterministic tests."""

    def __init__(
        self,
        *,
        file_root: Optional[str] = None,
        vision_caller: Optional[VisionCaller] = None,
    ) -> None:
        self._file_root = file_root
        self._vision_caller = vision_caller

    def read_bytes(
        self,
        image_bytes: bytes,
        mime_type: str,
        *,
        include_raw: bool = False,
    ) -> dict[str, Any]:
        return read_chart_bytes(
            image_bytes,
            mime_type,
            include_raw=include_raw,
            vision_caller=self._vision_caller,
        )

    def read_path(self, file_path: str, *, include_raw: bool = False) -> dict[str, Any]:
        return read_chart_path(
            file_path,
            file_root=self._file_root,
            include_raw=include_raw,
            vision_caller=self._vision_caller,
        )
