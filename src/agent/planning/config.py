# -*- coding: utf-8 -*-
"""Strict settings for the explicit plan-proposal foundation."""

from __future__ import annotations

import math
from dataclasses import dataclass

MAX_PLAN_STEPS = 16
MAX_REPLANS = 3
MAX_PLANNER_TOKENS = 8_192
MAX_PLANNER_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True)
class PlanningSettings:
    """Finite proposal-only bounds supplied explicitly by an offline caller."""

    enabled: bool = False
    strategy: str = "template"
    max_plan_steps: int = 8
    max_replans: int = 1
    max_tokens: int = 1_500
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        if type(self.enabled) is not bool:
            raise ValueError("enabled must be an exact boolean")
        if self.strategy not in {"template", "llm"}:
            raise ValueError("strategy must be 'template' or 'llm'")
        _bounded_int("max_plan_steps", self.max_plan_steps, 1, MAX_PLAN_STEPS)
        _bounded_int("max_replans", self.max_replans, 0, MAX_REPLANS)
        _bounded_int("max_tokens", self.max_tokens, 1, MAX_PLANNER_TOKENS)
        if type(self.timeout_seconds) not in (int, float):
            raise ValueError("timeout_seconds must be numeric")
        if not math.isfinite(float(self.timeout_seconds)):
            raise ValueError("timeout_seconds must be finite")
        if not 0.1 <= float(self.timeout_seconds) <= MAX_PLANNER_TIMEOUT_SECONDS:
            raise ValueError(
                f"timeout_seconds must be within [0.1, {MAX_PLANNER_TIMEOUT_SECONDS}]"
            )


def _bounded_int(name: str, value: int, minimum: int, maximum: int) -> None:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer within [{minimum}, {maximum}]")
