# -*- coding: utf-8 -*-
"""Declarative portfolio stress-test scenarios (issue #158 / T07).

Scenarios are data, not control-flow. Built-in presets always work without
configuration. An optional YAML file can add or override scenarios when
``PORTFOLIO_STRESS_SCENARIOS_PATH`` points at a readable file.
"""

from __future__ import annotations

import logging
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

logger = logging.getLogger(__name__)

# Factor kinds supported by the deterministic shock engine.
FACTOR_MARKET = "market"
FACTOR_SECTOR = "sector"
FACTOR_FX = "fx"
FACTOR_RATE = "rate"
SUPPORTED_FACTORS = frozenset({FACTOR_MARKET, FACTOR_SECTOR, FACTOR_FX, FACTOR_RATE})

# Default equity sensitivity used only for rate shocks when no per-name
# duration / rate-beta is supplied. Documented as a simplification.
DEFAULT_EQUITY_RATE_SENSITIVITY_PCT_PER_100BP = 2.0

# Built-in declarative scenarios (id must be stable for API clients).
_BUILTIN_SCENARIOS: List[Dict[str, Any]] = [
    {
        "id": "market_down_10",
        "name": "Broad market -10%",
        "description": "Instantaneous equity market factor shock of -10%.",
        "category": "market",
        "shocks": [{"factor": FACTOR_MARKET, "value_pct": -10.0}],
    },
    {
        "id": "market_down_20",
        "name": "Broad market -20%",
        "description": "Instantaneous equity market factor shock of -20%.",
        "category": "market",
        "shocks": [{"factor": FACTOR_MARKET, "value_pct": -20.0}],
    },
    {
        "id": "sector_down_30",
        "name": "Single sector -30%",
        "description": (
            "Named sector equity factor shock of -30%. Requires target_sector "
            "and sector classification for held names."
        ),
        "category": "sector",
        "shocks": [{"factor": FACTOR_SECTOR, "value_pct": -30.0}],
        "requires_target_sector": True,
    },
    {
        "id": "fx_up_5",
        "name": "Foreign currency +5%",
        "description": (
            "FX move of +5% applied to positions whose valuation currency "
            "differs from the portfolio base currency."
        ),
        "category": "fx",
        "shocks": [{"factor": FACTOR_FX, "value_pct": 5.0}],
    },
    {
        "id": "fx_down_5",
        "name": "Foreign currency -5%",
        "description": (
            "FX move of -5% applied to positions whose valuation currency "
            "differs from the portfolio base currency."
        ),
        "category": "fx",
        "shocks": [{"factor": FACTOR_FX, "value_pct": -5.0}],
    },
    {
        "id": "rate_up_100bp",
        "name": "Policy rates +100bp",
        "description": (
            "Parallel rate move of +100 basis points mapped to equity via a "
            "simplified rate-sensitivity assumption."
        ),
        "category": "rate",
        "shocks": [{"factor": FACTOR_RATE, "value_bp": 100.0}],
    },
]


def _normalize_shock(raw: Mapping[str, Any]) -> Dict[str, Any]:
    factor = str(raw.get("factor") or "").strip().lower()
    if factor not in SUPPORTED_FACTORS:
        raise ValueError(
            f"Unsupported stress factor '{factor}'. "
            f"Supported: {sorted(SUPPORTED_FACTORS)}"
        )
    shock: Dict[str, Any] = {"factor": factor}
    if factor == FACTOR_RATE:
        if "value_bp" not in raw and "value_pct" not in raw:
            raise ValueError("rate shock requires value_bp (or value_pct as bp/100 proxy)")
        if "value_bp" in raw and raw["value_bp"] is not None:
            shock["value_bp"] = float(raw["value_bp"])
        else:
            # Allow value_pct=1.0 to mean +100bp when callers use percent points.
            shock["value_bp"] = float(raw["value_pct"]) * 100.0
    else:
        if "value_pct" not in raw or raw["value_pct"] is None:
            raise ValueError(f"{factor} shock requires value_pct")
        shock["value_pct"] = float(raw["value_pct"])
    return shock


def _normalize_scenario(raw: Mapping[str, Any]) -> Dict[str, Any]:
    scenario_id = str(raw.get("id") or "").strip()
    if not scenario_id:
        raise ValueError("scenario id is required")
    name = str(raw.get("name") or scenario_id).strip()
    description = str(raw.get("description") or "").strip()
    category = str(raw.get("category") or "custom").strip().lower()
    shocks_raw = raw.get("shocks") or []
    if not isinstance(shocks_raw, Sequence) or isinstance(shocks_raw, (str, bytes)):
        raise ValueError(f"scenario '{scenario_id}' shocks must be a list")
    shocks = [_normalize_shock(item) for item in shocks_raw]
    if not shocks:
        raise ValueError(f"scenario '{scenario_id}' must declare at least one shock")
    requires_target_sector = bool(
        raw.get("requires_target_sector")
        or any(s["factor"] == FACTOR_SECTOR for s in shocks)
    )
    return {
        "id": scenario_id,
        "name": name,
        "description": description,
        "category": category,
        "shocks": shocks,
        "requires_target_sector": requires_target_sector,
    }


def _load_yaml_scenarios(path: Path) -> List[Dict[str, Any]]:
    try:
        import yaml  # type: ignore
    except ImportError as exc:  # pragma: no cover - PyYAML is a project dependency
        raise ValueError(f"Cannot load YAML scenarios from {path}: {exc}") from exc

    text = path.read_text(encoding="utf-8")
    payload = yaml.safe_load(text)
    if payload is None:
        return []
    if isinstance(payload, dict) and "scenarios" in payload:
        items = payload["scenarios"]
    elif isinstance(payload, list):
        items = payload
    else:
        raise ValueError(
            f"Scenario YAML at {path} must be a list or a mapping with 'scenarios'"
        )
    if not isinstance(items, list):
        raise ValueError(f"Scenario YAML 'scenarios' at {path} must be a list")
    return [_normalize_scenario(item) for item in items]


def builtin_scenarios() -> List[Dict[str, Any]]:
    """Return a deep copy of built-in scenarios."""
    return deepcopy(_BUILTIN_SCENARIOS)


def load_scenarios(
    *,
    scenarios_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Load built-in scenarios, optionally merged with a user YAML file.

    User scenarios with the same ``id`` override built-ins. When the path is
    unset or empty, only built-ins are returned (works without configuration).
    """
    merged: Dict[str, Dict[str, Any]] = {
        item["id"]: deepcopy(item) for item in _BUILTIN_SCENARIOS
    }
    path_raw = (
        scenarios_path
        if scenarios_path is not None
        else os.environ.get("PORTFOLIO_STRESS_SCENARIOS_PATH", "")
    )
    path_raw = str(path_raw or "").strip()
    if not path_raw:
        return [merged[key] for key in sorted(merged.keys())]

    path = Path(path_raw).expanduser()
    if not path.is_file():
        raise ValueError(f"PORTFOLIO_STRESS_SCENARIOS_PATH is not a readable file: {path}")
    for item in _load_yaml_scenarios(path):
        merged[item["id"]] = item
    return [merged[key] for key in sorted(merged.keys())]


def get_scenario(
    scenario_id: str,
    *,
    scenarios_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Resolve a single scenario by id or raise ValueError."""
    target = str(scenario_id or "").strip()
    if not target:
        raise ValueError("scenario_id is required")
    for item in load_scenarios(scenarios_path=scenarios_path):
        if item["id"] == target:
            return deepcopy(item)
    known = ", ".join(s["id"] for s in load_scenarios(scenarios_path=scenarios_path))
    raise ValueError(f"Unknown scenario_id '{target}'. Known: {known}")


def build_custom_scenario(
    *,
    shocks: Sequence[Mapping[str, Any]],
    scenario_id: str = "custom",
    name: str = "Custom scenario",
    description: str = "Caller-supplied deterministic factor shocks.",
) -> Dict[str, Any]:
    """Build a normalized custom scenario from raw shocks."""
    return _normalize_scenario(
        {
            "id": scenario_id,
            "name": name,
            "description": description,
            "category": "custom",
            "shocks": list(shocks),
        }
    )
