# -*- coding: utf-8 -*-
"""Environment-backed settings for the optional planning pre-step.

Values are read from process environment so this module stays independent of
``src/core/config_registry_parts/`` (owned by a parallel task). Registry UI
wiring is documented as an Integration Point in the PR.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, *, minimum: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    return max(minimum, value)


def _env_float(name: str, default: float, *, minimum: float = 0.0) -> float:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        value = float(str(raw).strip())
    except (TypeError, ValueError):
        return default
    return max(minimum, value)


@dataclass(frozen=True)
class PlanningSettings:
    """Hard cost bounds and feature gate for planning."""

    enabled: bool = False
    strategy: str = "auto"  # auto | template | llm
    max_plan_steps: int = 8
    max_replans: int = 1
    max_tokens: int = 1500
    timeout_seconds: float = 30.0


def load_planning_settings() -> PlanningSettings:
    """Load planning settings from environment (default off)."""
    strategy = (os.getenv("AGENT_PLANNING_STRATEGY") or "auto").strip().lower()
    if strategy not in {"auto", "template", "llm"}:
        strategy = "auto"
    return PlanningSettings(
        enabled=_env_bool("AGENT_PLANNING_ENABLED", default=False),
        strategy=strategy,
        max_plan_steps=_env_int("AGENT_PLANNING_MAX_STEPS", 8, minimum=1),
        max_replans=_env_int("AGENT_PLANNING_MAX_REPLANS", 1, minimum=0),
        max_tokens=_env_int("AGENT_PLANNING_MAX_TOKENS", 1500, minimum=200),
        timeout_seconds=_env_float("AGENT_PLANNING_TIMEOUT_S", 30.0, minimum=1.0),
    )


def is_planning_enabled() -> bool:
    """Return True only when the opt-in planning gate is enabled."""
    return load_planning_settings().enabled
