# -*- coding: utf-8 -*-
"""Gated online evolution adapters (Issue #1091 first slice).

Wraps existing ``AgentMemory`` calibration. Tool ranking and route preference
are explicit identity stubs. Default-off. This module does not edit BaseAgent,
the orchestrator, Soul, ToolSurface, or episode storage.
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


def _factor_from_stats(accuracy: float, avg_confidence: float) -> float:
    if avg_confidence > 0:
        return _clamp_factor(accuracy / avg_confidence)
    return 1.0


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

    Identity if adapters off, memory off, or samples < min.
    """
    if not is_online_adapters_enabled(config):
        return float(raw), _identity_confidence(reason=_REASON_ADAPTERS_DISABLED)

    threshold = max(1, int(min_samples))
    if memory is None or not getattr(memory, "enabled", False):
        return float(raw), _identity_confidence(reason=_REASON_MEMORY_DISABLED)

    cal = memory.get_calibration(agent_name, stock_code=stock_code)
    samples = int(getattr(cal, "total_samples", 0) or 0)
    if samples < threshold:
        return float(raw), _identity_confidence(
            samples=samples,
            reason=_REASON_INSUFFICIENT_SAMPLES,
        )

    factor = _factor_from_stats(
        float(getattr(cal, "historical_accuracy", 0.5) or 0.5),
        float(getattr(cal, "avg_confidence", 0.5) or 0.0),
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
