# -*- coding: utf-8 -*-
"""Bounded, versioned scenario catalog for portfolio stress testing."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

FACTOR_MARKET = "market"
FACTOR_SECTOR = "sector"
FACTOR_FX = "fx"
FACTOR_RATE = "rate"
SUPPORTED_FACTORS = frozenset({FACTOR_MARKET, FACTOR_SECTOR, FACTOR_FX, FACTOR_RATE})
DEFAULT_EQUITY_RATE_SENSITIVITY_PCT_PER_100BP = 2.0

MAX_CATALOG_BYTES = 256 * 1024
MAX_SCENARIOS = 64
MAX_SHOCKS = 16
MAX_YAML_ALIASES = 32
MAX_NESTING_DEPTH = 8


class ScenarioCatalogUnavailableError(ValueError):
    """A configured catalog could not be safely loaded."""


_BUILTIN_SCENARIOS: List[Dict[str, Any]] = [
    {"id": "market_down_10", "name": "Broad market -10%", "description": "Instantaneous equity market factor shock of -10%.", "category": "market", "shocks": [{"factor": FACTOR_MARKET, "value_pct": -10.0}]},
    {"id": "market_down_20", "name": "Broad market -20%", "description": "Instantaneous equity market factor shock of -20%.", "category": "market", "shocks": [{"factor": FACTOR_MARKET, "value_pct": -20.0}]},
    {"id": "sector_down_30", "name": "Single sector -30% template", "description": "Parameterized sector template; POST must supply target_sector and a complete sector_map.", "category": "sector", "shocks": [{"factor": FACTOR_SECTOR, "value_pct": -30.0}], "requires_target_sector": True, "availability": "requires_parameters"},
    {"id": "fx_up_5", "name": "Instrument currency +5%", "description": "Instrument currency appreciates 5% against the response base currency.", "category": "fx", "shocks": [{"factor": FACTOR_FX, "value_pct": 5.0}]},
    {"id": "fx_down_5", "name": "Instrument currency -5%", "description": "Instrument currency depreciates 5% against the response base currency.", "category": "fx", "shocks": [{"factor": FACTOR_FX, "value_pct": -5.0}]},
    {"id": "rate_up_100bp", "name": "Policy rates +100bp", "description": "Parallel +100bp rate move using the disclosed uniform equity sensitivity.", "category": "rate", "shocks": [{"factor": FACTOR_RATE, "value_bp": 100.0}]},
]

_catalog_lock = threading.RLock()
_last_good: Dict[str, tuple[int, List[Dict[str, Any]]]] = {}


def _bounded_text(value: Any, *, field: str, maximum: int, required: bool = False) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise ValueError(f"{field} is required")
    if len(text) > maximum:
        raise ValueError(f"{field} exceeds {maximum} characters")
    return text


def _finite(value: Any, *, field: str, minimum: float, maximum: float) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < minimum or parsed > maximum:
        raise ValueError(f"{field} must be finite and within [{minimum}, {maximum}]")
    return parsed


def _normalize_shock(raw: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValueError("each shock must be an object")
    factor = _bounded_text(raw.get("factor"), field="factor", maximum=16, required=True).lower()
    if factor not in SUPPORTED_FACTORS:
        raise ValueError(f"unsupported stress factor '{factor}'")
    allowed = {"factor", "value_bp"} if factor == FACTOR_RATE else {"factor", "value_pct"}
    extras = set(raw) - allowed
    if extras:
        raise ValueError(f"shock contains unsupported fields: {sorted(extras)}")
    if factor == FACTOR_RATE:
        if raw.get("value_bp") is None:
            raise ValueError("rate shock requires value_bp")
        return {"factor": factor, "value_bp": _finite(raw["value_bp"], field="value_bp", minimum=-1000, maximum=1000)}
    if raw.get("value_pct") is None:
        raise ValueError(f"{factor} shock requires value_pct")
    return {"factor": factor, "value_pct": _finite(raw["value_pct"], field="value_pct", minimum=-100, maximum=100)}


def _scenario_hash(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _normalize_scenario(raw: Mapping[str, Any], *, source: str) -> Dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValueError("each scenario must be an object")
    allowed = {
        "id",
        "name",
        "description",
        "category",
        "shocks",
        "requires_target_sector",
        "availability",
    }
    extras = set(raw) - allowed
    if extras:
        raise ValueError(f"scenario contains unsupported fields: {sorted(extras)}")
    scenario_id = _bounded_text(raw.get("id"), field="scenario id", maximum=64, required=True)
    name = _bounded_text(raw.get("name") or scenario_id, field="scenario name", maximum=120, required=True)
    description = _bounded_text(raw.get("description"), field="scenario description", maximum=500)
    category = _bounded_text(raw.get("category") or "custom", field="scenario category", maximum=16).lower()
    if category not in {"market", "sector", "fx", "rate", "custom"}:
        raise ValueError("scenario category is invalid")
    shocks_raw = raw.get("shocks")
    if not isinstance(shocks_raw, list) or not 1 <= len(shocks_raw) <= MAX_SHOCKS:
        raise ValueError(f"scenario '{scenario_id}' must declare 1-{MAX_SHOCKS} shocks")
    shocks = [_normalize_shock(item) for item in shocks_raw]
    requires_sector = bool(raw.get("requires_target_sector") or any(item["factor"] == FACTOR_SECTOR for item in shocks))
    normalized = {
        "id": scenario_id,
        "name": name,
        "description": description,
        "category": category,
        "shocks": shocks,
        "requires_target_sector": requires_sector,
        "availability": "requires_parameters" if requires_sector else "ready",
        "source": source,
        "version": 1,
    }
    normalized["scenario_hash"] = _scenario_hash(normalized)
    return normalized


def _validate_depth(value: Any, *, depth: int = 0) -> None:
    if depth > MAX_NESTING_DEPTH:
        raise ValueError("scenario catalog nesting is too deep")
    if isinstance(value, dict):
        for key, item in value.items():
            _validate_depth(key, depth=depth + 1)
            _validate_depth(item, depth=depth + 1)
    elif isinstance(value, list):
        for item in value:
            _validate_depth(item, depth=depth + 1)


def _load_yaml_scenarios(path: Path) -> List[Dict[str, Any]]:
    import yaml  # type: ignore

    size = path.stat().st_size
    if size > MAX_CATALOG_BYTES:
        raise ValueError("scenario catalog exceeds the byte limit")
    text = path.read_text(encoding="utf-8")
    if text.count("&") + text.count("*") > MAX_YAML_ALIASES:
        raise ValueError("scenario catalog contains too many YAML aliases")
    payload = yaml.safe_load(text)
    _validate_depth(payload)
    items = payload.get("scenarios") if isinstance(payload, dict) else payload
    if not isinstance(items, list) or len(items) > MAX_SCENARIOS:
        raise ValueError(f"scenario catalog must contain at most {MAX_SCENARIOS} items")
    return [_normalize_scenario(item, source="yaml") for item in items]


def builtin_scenarios() -> List[Dict[str, Any]]:
    return [_normalize_scenario(item, source="built_in") for item in _BUILTIN_SCENARIOS]


def load_scenarios(*, scenarios_path: Optional[str] = None) -> List[Dict[str, Any]]:
    merged = {item["id"]: item for item in builtin_scenarios()}
    path_raw = str(scenarios_path or "").strip()
    if not path_raw:
        return [deepcopy(merged[key]) for key in sorted(merged)]
    if len(path_raw) > 1024:
        raise ScenarioCatalogUnavailableError("Configured scenario catalog is unavailable")

    path = Path(path_raw).expanduser()
    cache_key = str(path.resolve(strict=False))
    try:
        mtime_ns = path.stat().st_mtime_ns
        with _catalog_lock:
            cached = _last_good.get(cache_key)
            if cached and cached[0] == mtime_ns:
                return deepcopy(cached[1])
        items = _load_yaml_scenarios(path)
        for item in items:
            merged[item["id"]] = item
        result = [deepcopy(merged[key]) for key in sorted(merged)]
        with _catalog_lock:
            _last_good[cache_key] = (mtime_ns, deepcopy(result))
        return result
    except Exception as exc:  # broad-exception: fallback_recorded - retain a validated last-known-good catalog and expose only a sanitized public error.
        log_safe_exception(logger, "Portfolio stress scenario catalog reload failed", exc, error_code="portfolio_stress_catalog_invalid")
        with _catalog_lock:
            cached = _last_good.get(cache_key)
            if cached:
                return deepcopy(cached[1])
        raise ScenarioCatalogUnavailableError("Configured scenario catalog is unavailable") from exc


def get_scenario(scenario_id: str, *, scenarios_path: Optional[str] = None) -> Dict[str, Any]:
    target = _bounded_text(scenario_id, field="scenario_id", maximum=64, required=True)
    scenarios = load_scenarios(scenarios_path=scenarios_path)
    for item in scenarios:
        if item["id"] == target:
            return deepcopy(item)
    raise ValueError(f"Unknown scenario_id '{target}'")


def build_custom_scenario(
    *,
    shocks: Sequence[Mapping[str, Any]],
    scenario_id: str = "custom",
    name: str = "Custom scenario",
    description: str = "Caller-supplied deterministic factor shocks.",
) -> Dict[str, Any]:
    return _normalize_scenario(
        {"id": scenario_id, "name": name, "description": description, "category": "custom", "shocks": list(shocks)},
        source="custom_api",
    )
