# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Run/stage/mode attribution context for LLM usage telemetry."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, Mapping, Optional

ROUTE_OUTCOME_PRIMARY_SUCCESS = "primary_success"
ROUTE_OUTCOME_FALLBACK_SUCCESS = "fallback_success"
ROUTE_OUTCOME_FAILED = "failed"
ROUTE_OUTCOME_NOT_APPLICABLE = "not_applicable"
_ATTRIBUTION: ContextVar[Optional["UsageAttribution"]] = ContextVar("llm_usage_attribution", default=None)


@dataclass(frozen=True)
class UsageAttribution:
    run_id: Optional[str] = None
    stage: Optional[str] = None
    agent_mode: Optional[str] = None
    stock_code: Optional[str] = None
    route_outcome: Optional[str] = None
    route_attempt: Optional[int] = None
    primary_model: Optional[str] = None
    latency_ms: Optional[int] = None
    call_success: Optional[bool] = None
    extra: Mapping[str, Any] = field(default_factory=dict)

    def merge(self, **overrides: Any) -> "UsageAttribution":
        data = {
            "run_id": self.run_id, "stage": self.stage, "agent_mode": self.agent_mode,
            "stock_code": self.stock_code, "route_outcome": self.route_outcome,
            "route_attempt": self.route_attempt, "primary_model": self.primary_model,
            "latency_ms": self.latency_ms, "call_success": self.call_success,
            "extra": dict(self.extra),
        }
        for key, value in overrides.items():
            if key == "extra" and isinstance(value, Mapping):
                data["extra"] = {**data["extra"], **dict(value)}
            elif key in data:
                data[key] = value
        return UsageAttribution(**data)

    def to_telemetry_fields(self) -> Dict[str, Any]:
        fields: Dict[str, Any] = {
            "run_id": _clip_str(self.run_id, 64),
            "stage": _clip_str(self.stage, 64),
            "agent_mode": _clip_str(self.agent_mode, 32),
            "route_outcome": _clip_str(self.route_outcome, 32),
            "route_attempt": _nonneg_int(self.route_attempt),
            "primary_model": _clip_str(self.primary_model, 128),
            "latency_ms": _nonneg_int(self.latency_ms),
            "call_success": _bool_as_int(self.call_success),
        }
        if self.stock_code:
            fields["stock_code"] = _clip_str(self.stock_code, 16)
        return fields


def get_usage_attribution() -> Optional[UsageAttribution]:
    return _ATTRIBUTION.get()

def set_usage_attribution(attribution: Optional[UsageAttribution]) -> Token:
    return _ATTRIBUTION.set(attribution)

def reset_usage_attribution(token: Token) -> None:
    _ATTRIBUTION.reset(token)

@contextmanager
def usage_attribution_scope(attribution: Optional[UsageAttribution] = None, **overrides: Any) -> Iterator[UsageAttribution]:
    parent = get_usage_attribution() or UsageAttribution()
    base = parent
    if attribution is not None:
        base = base.merge(
            run_id=attribution.run_id, stage=attribution.stage, agent_mode=attribution.agent_mode,
            stock_code=attribution.stock_code, route_outcome=attribution.route_outcome,
            route_attempt=attribution.route_attempt, primary_model=attribution.primary_model,
            latency_ms=attribution.latency_ms, call_success=attribution.call_success,
            extra=dict(attribution.extra),
        )
    if overrides:
        base = base.merge(**overrides)
    token = set_usage_attribution(base)
    try:
        yield base
    finally:
        reset_usage_attribution(token)

def resolve_attribution(**overrides: Any) -> UsageAttribution:
    current = get_usage_attribution() or UsageAttribution()
    return current.merge(**overrides) if overrides else current

def classify_route_outcome(*, attempt_index: int, success: bool) -> str:
    if not success:
        return ROUTE_OUTCOME_FAILED
    return ROUTE_OUTCOME_PRIMARY_SUCCESS if attempt_index <= 0 else ROUTE_OUTCOME_FALLBACK_SUCCESS

def _clip_str(value: Any, max_len: int) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text[:max_len] if text else None

def _nonneg_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None

def _bool_as_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)) and value in (0, 1):
        return int(value)
    return None
