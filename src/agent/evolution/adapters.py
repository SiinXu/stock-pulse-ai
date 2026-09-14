# -*- coding: utf-8 -*-
"""Gated online evolution adapters (Issue #1091 / #1106).

Wraps existing ``AgentMemory`` calibration. Tool ranking and route preference
are explicit identity stubs. Default-off. ``BaseAgent`` applies
``calibrate_confidence`` when ``AGENT_ONLINE_ADAPTERS_ENABLED`` is true.
When calibration actually applies, this module appends one system
``adapter.calibrate`` EvolutionEvent through an injected or services-layer
writer. When gated route preference actually steps to a richer mode, it
appends one ``adapter.route_preference`` event. Identity paths emit nothing.
Append failure is logged and does not change the returned confidence or mode.
This module does not import ``src.repositories``, edit Soul, ToolSurface,
episode storage, or AgentRouter, does not implement real tool ranking, and
does not expose HTTP list or auto-promote.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from pydantic import ValidationError

from src.agent.memory import AgentMemory
from src.agent.protocols import AgentContext
from src.schemas.evolution_event import EvolutionEventCreate, EvolutionEventReasonRefs
from src.utils.sanitize import log_safe_exception

ADAPTER_INFLUENCE_META_KEY = "adapter_influence"
DEFAULT_ONLINE_ADAPTERS_MIN_SAMPLES = 30
ADAPTER_CALIBRATE_EVENT_TYPE = "adapter.calibrate"
ADAPTER_ROUTE_EVENT_TYPE = "adapter.route_preference"
DEFAULT_ROUTE_PREFERENCE_MISS_RATE = 0.5
_MIN_CALIBRATION_FACTOR = 0.5
_MAX_CALIBRATION_FACTOR = 1.5
_ROUTE_RICHER = {"quick": "standard", "standard": "full"}

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

    from src.services.evolution_event_append import append_evolution_event_fail_soft

    append_evolution_event_fail_soft(
        payload,
        append_event=append_event,
        samples=samples,
        event_type=ADAPTER_CALIBRATE_EVENT_TYPE,
        log=logger,
    )


def _emit_applied_route_event(
    *,
    incoming: str,
    preferred: str,
    samples: int,
    miss_rate: float,
    reason_refs: Any = None,
    append_event: Optional[Callable[[EvolutionEventCreate], Any]] = None,
) -> None:
    """Append one system route-preference event. Fail-soft: never raise to callers."""
    try:
        payload = EvolutionEventCreate(
            event_type=ADAPTER_ROUTE_EVENT_TYPE,
            actor="system",
            reason_refs=_normalize_reason_refs(reason_refs),
            before={"applied": False, "mode": incoming},
            after={
                "applied": True,
                "mode": preferred,
                "samples": int(samples),
                "miss_rate": float(miss_rate),
            },
        )
    except ValidationError as exc:
        log_safe_exception(
            logger,
            "Online adapter route preference event payload was rejected",
            exc,
            error_code="adapter_route_event_invalid",
            level=logging.WARNING,
            context={"samples": int(samples), "miss_rate": float(miss_rate)},
        )
        return

    from src.services.evolution_event_append import append_evolution_event_fail_soft

    append_evolution_event_fail_soft(
        payload,
        append_event=append_event,
        samples=samples,
        event_type=ADAPTER_ROUTE_EVENT_TYPE,
        log=logger,
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


def prefer_route(
    mode: str,
    *,
    config: Any = None,
    stock_code: Optional[str] = None,
    min_samples: Optional[int] = None,
    repo: Any = None,
    stats: Optional[Dict[str, Any]] = None,
    reason_refs: Any = None,
    append_event: Optional[Callable[[EvolutionEventCreate], Any]] = None,
) -> str:
    """Return a one-rung-richer mode when gated miss-rate thresholds apply.

    Identity (incoming mode, zero events) when adapters are off, config is
    missing, samples are below min, miss-rate is below
    ``DEFAULT_ROUTE_PREFERENCE_MISS_RATE``, or there is no richer rung.
    ``quick`` may become ``standard`` and ``standard`` may become ``full``.
    Never invents ``chat``, never writes ``AGENT_ORCHESTRATOR_MODE``, and
    never calls AgentRouter. Append failure does not change the returned mode.
    """
    incoming = str(mode or "").strip() or "quick"
    if not is_online_adapters_enabled(config):
        return incoming

    raw_min = min_samples
    if raw_min is None:
        raw_min = getattr(config, "agent_online_adapters_min_samples", DEFAULT_ONLINE_ADAPTERS_MIN_SAMPLES)
    if raw_min is None:
        raw_min = DEFAULT_ONLINE_ADAPTERS_MIN_SAMPLES
    try:
        threshold = max(1, int(raw_min))
    except (TypeError, ValueError):
        threshold = DEFAULT_ONLINE_ADAPTERS_MIN_SAMPLES

    richer = _ROUTE_RICHER.get(incoming)
    if richer is None or richer == incoming:
        return incoming

    loaded = stats if isinstance(stats, dict) else None
    if loaded is None:
        from src.agent.evolution.outcome_ingest import load_route_preference_stats

        loaded = load_route_preference_stats(
            stock_code=stock_code,
            min_samples=threshold,
            repo=repo,
        )

    samples = _coerce_int(loaded.get("samples"), default=0)
    miss_rate = max(0.0, min(1.0, _coerce_float(loaded.get("miss_rate"), default=0.0)))
    used = bool(loaded.get("used", False))
    if not used or samples < threshold:
        return incoming
    if miss_rate < DEFAULT_ROUTE_PREFERENCE_MISS_RATE:
        return incoming

    _emit_applied_route_event(
        incoming=incoming,
        preferred=richer,
        samples=samples,
        miss_rate=miss_rate,
        reason_refs=reason_refs,
        append_event=append_event,
    )
    return richer


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


def _bounded_route_preference(payload: Dict[str, Any]) -> Dict[str, Any]:
    source = payload if isinstance(payload, dict) else {}
    raw = source.get("route_preference")
    if not isinstance(raw, dict):
        return {
            "applied": False,
            "reason": _STUB_NEUTRAL,
            "mode": _bounded_mode(source),
        }
    applied = bool(raw.get("applied", False))
    reason = raw.get("reason")
    if not isinstance(reason, str) or not reason:
        reason = _REASON_APPLIED if applied else _STUB_NEUTRAL
    mode = raw.get("mode")
    if not isinstance(mode, str):
        mode = _bounded_mode(source)
    bounded: Dict[str, Any] = {
        "applied": applied,
        "reason": reason,
        "mode": mode if isinstance(mode, str) else "",
    }
    if "samples" in raw:
        bounded["samples"] = _coerce_int(raw.get("samples"), default=0)
    if "miss_rate" in raw:
        bounded["miss_rate"] = max(0.0, min(1.0, _coerce_float(raw.get("miss_rate"), default=0.0)))
    return bounded


def _bounded_influence(payload: Dict[str, Any]) -> Dict[str, Any]:
    source = payload if isinstance(payload, dict) else {}
    return {
        "confidence": _bounded_confidence(source),
        "tool_effectiveness": {"applied": False, "reason": _STUB_NEUTRAL},
        "route_preference": _bounded_route_preference(source),
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
