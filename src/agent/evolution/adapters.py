# -*- coding: utf-8 -*-
"""Gated online evolution adapters (Issue #1091 / #1106).

Wraps existing ``AgentMemory`` calibration. Tool ranking and route preference
are explicit identity stubs. Default-off. ``BaseAgent`` applies
``calibrate_confidence`` when ``AGENT_ONLINE_ADAPTERS_ENABLED`` is true.
When calibration actually applies, this module appends one system
``adapter.calibrate`` EvolutionEvent. Identity paths emit nothing. Append
failure is logged and does not change the returned confidence. This module
does not edit Soul, ToolSurface, episode storage, or orchestrator route,
does not implement real tool ranking or route preference, and does not
expose HTTP list or auto-promote.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from src.agent.memory import AgentMemory
from src.agent.protocols import AgentContext
from src.repositories.base import RepositoryError
from src.schemas.evolution_event import EvolutionEventCreate, EvolutionEventReasonRefs
from src.utils.sanitize import log_safe_exception

ADAPTER_INFLUENCE_META_KEY = "adapter_influence"
DEFAULT_ONLINE_ADAPTERS_MIN_SAMPLES = 30
ADAPTER_CALIBRATE_EVENT_TYPE = "adapter.calibrate"
_MIN_CALIBRATION_FACTOR = 0.5
_MAX_CALIBRATION_FACTOR = 1.5

logger = logging.getLogger(__name__)

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


def _normalize_reason_refs(reason_refs: Any) -> EvolutionEventReasonRefs:
    if reason_refs is None:
        return EvolutionEventReasonRefs()
    if isinstance(reason_refs, EvolutionEventReasonRefs):
        return reason_refs
    return EvolutionEventReasonRefs.model_validate(reason_refs)


def _default_append_evolution_event(event: EvolutionEventCreate) -> Any:
    from src.repositories.agent_evolution_event_repo import AgentEvolutionEventRepository

    return AgentEvolutionEventRepository().append(event)


def _emit_applied_calibration_event(
    *,
    factor: float,
    samples: int,
    reason_refs: Any = None,
    append_event: Optional[Callable[[EvolutionEventCreate], Any]] = None,
) -> None:
    """Append one system calibration event. Fail-soft: never raise to callers."""
    try:
        payload = EvolutionEventCreate(
            event_type=ADAPTER_CALIBRATE_EVENT_TYPE,
            actor="system",
            reason_refs=_normalize_reason_refs(reason_refs),
            before={"applied": False, "factor": 1.0},
            after={
                "applied": True,
                "factor": float(factor),
                "samples": int(samples),
            },
        )
    except ValidationError as exc:
        log_safe_exception(
            logger,
            "Online adapter calibration event payload was rejected",
            exc,
            error_code="adapter_calibrate_event_invalid",
            level=logging.WARNING,
            context={"samples": int(samples)},
        )
        return

    writer = append_event if append_event is not None else _default_append_evolution_event
    try:
        writer(payload)
    except (RepositoryError, ValidationError, SQLAlchemyError) as exc:
        log_safe_exception(
            logger,
            "Online adapter calibration event append failed",
            exc,
            error_code="adapter_calibrate_event_append_failed",
            level=logging.WARNING,
            context={"event_type": ADAPTER_CALIBRATE_EVENT_TYPE, "samples": int(samples)},
        )


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
    reason_refs: Any = None,
    append_event: Optional[Callable[[EvolutionEventCreate], Any]] = None,
) -> Tuple[float, Dict[str, Any]]:
    """Wrap AgentMemory.get_calibration.

    Identity if adapters off, memory off, samples < min, or not calibrated.
    When applied, multiplies ``raw`` by the stored ``calibration_factor``
    (AgentMemory already clamps ``historical_accuracy / avg_confidence``
    to ``0.5..1.5``, including ``historical_accuracy=0.0``) and appends one
    ``adapter.calibrate`` EvolutionEvent. Append failure does not change the
    returned ``(adjusted, meta)``. Do not invent prediction ids for reason_refs.
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
    meta = {
        "applied": True,
        "factor": factor,
        "samples": samples,
        "reason": _REASON_APPLIED,
    }
    _emit_applied_calibration_event(
        factor=factor,
        samples=samples,
        reason_refs=reason_refs,
        append_event=append_event,
    )
    return adjusted, meta


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
