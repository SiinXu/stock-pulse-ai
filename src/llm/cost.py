# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Shared LLM cost metering for usage attribution and mode budgets.

One measurement, two consumers:
1. Usage page — honest nullable USD + cost_status
2. Mode budget gate (#1213) — float; unpriced -> 0.0
"""

from __future__ import annotations

import json
import logging
import math
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

logger = logging.getLogger(__name__)

COST_STATUS_PROVIDER_REPORTED = "provider_reported"
COST_STATUS_PRICED = "priced"
COST_STATUS_UNPRICED = "unpriced"
COST_STATUS_DISABLED = "disabled"
_PROVIDER_COST_KEYS = ("response_cost", "completion_cost", "cost", "total_cost")
_pricing_lock = threading.Lock()
_pricing_cache: Optional[Dict[str, Dict[str, float]]] = None
_pricing_cache_path: Optional[str] = None


@dataclass(frozen=True)
class CostEstimate:
    cost_usd: Optional[float]
    status: str
    source: str = ""

    def as_budget_usd(self) -> float:
        if self.cost_usd is None or not math.isfinite(self.cost_usd) or self.cost_usd < 0:
            return 0.0
        return float(self.cost_usd)

    def to_usage_fields(self) -> Dict[str, Any]:
        return {
            "estimated_cost_usd": self.cost_usd,
            "cost_status": self.status,
            "cost_source": self.source or None,
        }


def is_usage_attribution_enabled(config: Any = None) -> bool:
    if config is not None:
        raw = getattr(config, "llm_usage_attribution_enabled", None)
        if raw is not None and raw != "":
            return _as_bool(raw, default=True)
    env = os.getenv("LLM_USAGE_ATTRIBUTION_ENABLED")
    if env is None or env == "":
        return True
    return _as_bool(env, default=True)


def estimate_usage_cost(usage: Optional[Mapping[str, Any]], model: str = "", *, enabled: Optional[bool] = None) -> CostEstimate:
    if enabled is False or (enabled is None and not is_usage_attribution_enabled()):
        return CostEstimate(None, COST_STATUS_DISABLED, "disabled")
    if not usage:
        return CostEstimate(None, COST_STATUS_UNPRICED, "no_usage")
    for key in _PROVIDER_COST_KEYS:
        value = _as_nonneg_float(usage.get(key))
        if value is not None:
            return CostEstimate(float(value), COST_STATUS_PROVIDER_REPORTED, key)
    prompt_tokens = _as_nonneg_int(usage.get("prompt_tokens") or usage.get("normalized_prompt_tokens") or usage.get("input_tokens"))
    completion_tokens = _as_nonneg_int(usage.get("completion_tokens") or usage.get("normalized_completion_tokens") or usage.get("output_tokens"))
    if prompt_tokens is None and completion_tokens is None:
        return CostEstimate(None, COST_STATUS_UNPRICED, "no_tokens")
    prompt_tokens = int(prompt_tokens or 0)
    completion_tokens = int(completion_tokens or 0)
    pricing = lookup_model_pricing(model)
    if not pricing:
        return CostEstimate(None, COST_STATUS_UNPRICED, "no_pricing")
    cost = prompt_tokens * float(pricing.get("input_cost_per_token") or 0.0) + completion_tokens * float(pricing.get("output_cost_per_token") or 0.0)
    if not math.isfinite(cost) or cost < 0:
        return CostEstimate(None, COST_STATUS_UNPRICED, "invalid_rate")
    return CostEstimate(float(cost), COST_STATUS_PRICED, str(pricing.get("source") or "pricing_table"))


def estimate_usage_cost_usd(usage: Optional[Mapping[str, Any]], model: str = "") -> float:
    """Budget-gate compatible float cost (0.0 when unpriced). Aligns with #1213."""
    return estimate_usage_cost(usage, model, enabled=True).as_budget_usd()


def enrich_usage_with_cost(usage: Optional[Mapping[str, Any]], model: str = "", *, enabled: Optional[bool] = None) -> Dict[str, Any]:
    base: Dict[str, Any] = dict(usage) if isinstance(usage, Mapping) else {}
    base.update(estimate_usage_cost(base, model, enabled=enabled).to_usage_fields())
    return base


def lookup_model_pricing(model: str) -> Optional[Dict[str, Any]]:
    if not model or not str(model).strip():
        return None
    wire = str(model).strip()
    table = _load_optional_pricing_table()
    if table:
        hit = _match_pricing_entry(table, wire)
        if hit is not None:
            return {**hit, "source": "pricing_path"}
    return _lookup_litellm_pricing(wire)


def _lookup_litellm_pricing(wire: str) -> Optional[Dict[str, Any]]:
    try:
        import litellm  # type: ignore
        cost_map = getattr(litellm, "model_cost", None)
        if not isinstance(cost_map, dict):
            return None
        if wire in cost_map and isinstance(cost_map[wire], dict):
            return {**cost_map[wire], "source": "litellm"}
        if "/" in wire:
            bare = wire.split("/", 1)[1]
            if bare in cost_map and isinstance(cost_map[bare], dict):
                return {**cost_map[bare], "source": "litellm"}
    except Exception:
        return None
    return None


def _load_optional_pricing_table() -> Dict[str, Dict[str, float]]:
    global _pricing_cache, _pricing_cache_path
    path = (os.getenv("LLM_COST_PRICING_PATH") or "").strip()
    if not path:
        with _pricing_lock:
            _pricing_cache = None
            _pricing_cache_path = None
        return {}
    with _pricing_lock:
        if _pricing_cache is not None and _pricing_cache_path == path:
            return _pricing_cache
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to load LLM_COST_PRICING_PATH=%s: %s", path, exc)
            _pricing_cache, _pricing_cache_path = {}, path
            return _pricing_cache
        parsed: Dict[str, Dict[str, float]] = {}
        if isinstance(raw, dict):
            for key, value in raw.items():
                entry = _normalize_pricing_entry(value)
                if entry is not None:
                    parsed[str(key)] = entry
        _pricing_cache, _pricing_cache_path = parsed, path
        return _pricing_cache


def _normalize_pricing_entry(value: Any) -> Optional[Dict[str, float]]:
    if not isinstance(value, Mapping):
        return None
    input_per_token = _as_nonneg_float(value.get("input_cost_per_token"))
    output_per_token = _as_nonneg_float(value.get("output_cost_per_token"))
    if input_per_token is None:
        per_m = _as_nonneg_float(value.get("input_cost_per_1m_tokens") or value.get("input_cost_per_million_tokens"))
        if per_m is not None:
            input_per_token = per_m / 1_000_000.0
    if output_per_token is None:
        per_m = _as_nonneg_float(value.get("output_cost_per_1m_tokens") or value.get("output_cost_per_million_tokens"))
        if per_m is not None:
            output_per_token = per_m / 1_000_000.0
    if input_per_token is None and output_per_token is None:
        return None
    return {"input_cost_per_token": float(input_per_token or 0.0), "output_cost_per_token": float(output_per_token or 0.0)}


def _match_pricing_entry(table: Mapping[str, Dict[str, float]], wire: str) -> Optional[Dict[str, float]]:
    if wire in table:
        return table[wire]
    if "/" in wire:
        bare = wire.split("/", 1)[1]
        if bare in table:
            return table[bare]
    return None


def _as_nonneg_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _as_nonneg_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return number


def _as_bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _reset_pricing_cache_for_tests() -> None:
    global _pricing_cache, _pricing_cache_path
    with _pricing_lock:
        _pricing_cache = None
        _pricing_cache_path = None
