# -*- coding: utf-8 -*-
"""Gated online evolution adapters (Issue #1091).

Wraps existing ``AgentMemory`` calibration. Tool ranking and route preference
are explicit identity stubs. Default-off. ``BaseAgent`` applies
``calibrate_confidence`` when ``AGENT_ONLINE_ADAPTERS_ENABLED`` is true.
This module does not edit Soul, ToolSurface, episode storage, or orchestrator
route, and does not implement real tool ranking or route preference.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.agent.memory import AgentMemory
from src.agent.protocols import AgentContext

ADAPTER_INFLUENCE_META_KEY = "adapter_influence"
DEFAULT_ONLINE_ADAPTERS_MIN_SAMPLES = 30
_MIN_CALIBRATION_FACTOR = 0.5
_MAX_CALIBRATION_FACTOR = 1.5

_STUB_NEUTRAL = "stub_neutral"
_REASON_ADAPTERS_DISABLED = "adapters_disabled"
_REASON_MEMORY_DISABLED = "memory_disabled"
_REASON_INSUFFICIENT_SAMPLES = "insufficient_samples"
_REASON_APPLIED = "applied"


def is_online_adapters_enabled(config: Any = None) -> bool:
    """True only when AGENT_ONLINE_ADAPTERS_ENABLED is true. Default false."""
    if config is None:
        return False
    return getattr(config, "agent_online_adapters_enabled", False) is True


def _identity_confidence(*, samples: int = 0, reason: str) -> Dict[str, Any]:
    return {
        "applied": False,
        "factor": 1.0,
        "samples": int(samples),
        "reason": reason,
    }


def _clamp_factor(factor: float) -> float:
    return min(_MAX_CALIBRATION_FACTOR, max(_MIN_CALIBRATION_FACTOR, float(factor)))


def _clamp_confidence(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _coerce_float(value: Any, default: float) -> float:
    """Parse a numeric field. Preserve 0.0; do not treat it as missing."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_int(value: Any, default: int = 0) -> int:
    """Parse an integer field. Preserve 0; do not treat it as missing."""
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def calibrate_confidence(
    raw: float,
    *,
    memory: AgentMemory,
    agent_name: str,
    stock_code: Optional[str],
    min_samples: int,
    config: Any = None,
) -> Tuple[float, Dict[str, Any]]:
    """Wrap AgentMemory.get_calibration.

    Identity if adapters off, memory off, samples < min, or not calibrated.
    When applied, multiplies ``raw`` by the stored ``calibration_factor``
    (AgentMemory already clamps ``historical_accuracy / avg_confidence``
    to ``0.5..1.5``, including ``historical_accuracy=0.0``).
    """
    if not is_online_adapters_enabled(config):
        return float(raw), _identity_confidence(reason=_REASON_ADAPTERS_DISABLED)

    threshold = max(1, int(min_samples))
    if memory is None or not getattr(memory, "enabled", False):
        return float(raw), _identity_confidence(reason=_REASON_MEMORY_DISABLED)

    cal = memory.get_calibration(agent_name, stock_code=stock_code)
    samples = _coerce_int(getattr(cal, "total_samples", 0), default=0)
    if samples < threshold:
        return float(raw), _identity_confidence(
            samples=samples,
            reason=_REASON_INSUFFICIENT_SAMPLES,
        )
    if not getattr(cal, "calibrated", False):
        return float(raw), _identity_confidence(
            samples=samples,
            reason=_REASON_INSUFFICIENT_SAMPLES,
        )

    factor = _clamp_factor(
        _coerce_float(getattr(cal, "calibration_factor", 1.0), default=1.0)
    )
    adjusted = _clamp_confidence(float(raw) * factor)
    return adjusted, {
        "applied": True,
        "factor": factor,
        "samples": samples,
        "reason": _REASON_APPLIED,
    }


def rank_tools(
    tool_names: Sequence[str],
    *,
    denied_names: Sequence[str] = (),
) -> List[str]:
    """Slice-1 stub: return input order. Never insert or promote a denied name."""
    incoming = list(tool_names)
    denied = {name for name in denied_names if isinstance(name, str) and name}
    if not denied:
        return incoming
    # Identity order keeps any denied name at its original rank and never
    # inserts a denied name that the caller did not already supply.
    return incoming


def prefer_route(mode: str) -> str:
    """Slice-1 stub: return the same mode. Do not write AGENT_ORCHESTRATOR_MODE."""
    return mode


def _bounded_confidence(payload: Dict[str, Any]) -> Dict[str, Any]:
    raw = payload.get("confidence") if isinstance(payload, dict) else None
    if not isinstance(raw, dict):
        return _identity_confidence(reason=_REASON_ADAPTERS_DISABLED)
    try:
        factor = float(raw.get("factor", 1.0))
    except (TypeError, ValueError):
        factor = 1.0
    try:
        samples = int(raw.get("samples", 0) or 0)
    except (TypeError, ValueError):
        samples = 0
    reason = raw.get("reason")
    return {
        "applied": bool(raw.get("applied", False)),
        "factor": factor,
        "samples": samples,
        "reason": reason if isinstance(reason, str) else "",
    }


def _bounded_mode(payload: Dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        return ""
    route = payload.get("route_preference")
    if isinstance(route, dict):
        mode = route.get("mode")
        if isinstance(mode, str):
            return mode
    mode = payload.get("mode")
    return mode if isinstance(mode, str) else ""


def _bounded_influence(payload: Dict[str, Any]) -> Dict[str, Any]:
    source = payload if isinstance(payload, dict) else {}
    return {
        "confidence": _bounded_confidence(source),
        "tool_effectiveness": {"applied": False, "reason": _STUB_NEUTRAL},
        "route_preference": {
            "applied": False,
            "reason": _STUB_NEUTRAL,
            "mode": _bounded_mode(source),
        },
    }


def record_adapter_influence(
    ctx: AgentContext,
    payload: dict,
    *,
    config: Any = None,
) -> None:
    """If enabled, set ctx.meta[ADAPTER_INFLUENCE_META_KEY] to a bounded dict.

    If disabled, do not set the key (identity vs current main).
    """
    if not is_online_adapters_enabled(config):
        return
    if ctx is None:
        return
    meta = getattr(ctx, "meta", None)
    if not isinstance(meta, dict):
        return
    meta[ADAPTER_INFLUENCE_META_KEY] = _bounded_influence(payload)
