# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Observational plugin hooks for the initial analysis lifecycle events."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Literal, Mapping, TypeAlias

from src.utils.sanitize import log_safe_exception, sanitize_diagnostic_text

from .registry import (
    ExtensionContract,
    ExtensionRegistration,
    JSONValue,
    freeze_json_metadata,
)


logger = logging.getLogger(__name__)

EventName = Literal[
    "analysis.started",
    "analysis.completed",
    "analysis.failed",
    "market_review.started",
    "market_review.completed",
    "market_review.failed",
]
AnalysisEventName = Literal[
    "analysis.started",
    "analysis.completed",
    "analysis.failed",
]
MarketReviewEventName = Literal[
    "market_review.started",
    "market_review.completed",
    "market_review.failed",
]
EventHook: TypeAlias = Callable[["PluginEvent"], None]

EVENT_HOOK_SCHEMA_VERSION = 1
EVENT_HOOK_NAMES: frozenset[str] = frozenset(
    {
        "analysis.started",
        "analysis.completed",
        "analysis.failed",
        "market_review.started",
        "market_review.completed",
        "market_review.failed",
    }
)
_ANALYSIS_EVENT_NAMES = frozenset(
    {"analysis.started", "analysis.completed", "analysis.failed"}
)
_MARKET_REVIEW_EVENT_NAMES = frozenset(
    {
        "market_review.started",
        "market_review.completed",
        "market_review.failed",
    }
)


@dataclass(frozen=True, slots=True)
class PluginEvent:
    """Detached immutable event passed to one observational plugin callback."""

    name: EventName
    schema_version: int
    occurred_at: datetime
    trace_id: str | None
    payload: Mapping[str, JSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.name not in EVENT_HOOK_NAMES:
            raise ValueError("unsupported plugin event name")
        if type(self.schema_version) is not int or self.schema_version != EVENT_HOOK_SCHEMA_VERSION:
            raise ValueError("unsupported plugin event schema version")
        if not isinstance(self.occurred_at, datetime) or self.occurred_at.tzinfo is None:
            raise ValueError("plugin event timestamps must be timezone-aware")
        if self.trace_id is not None and type(self.trace_id) is not str:
            raise TypeError("plugin event trace_id must be a string or None")
        object.__setattr__(self, "payload", freeze_json_metadata(self.payload))


@dataclass(frozen=True, slots=True)
class EventHookRegistration:
    """Canonical plugin registration for one or more allowed event names."""

    hook_id: str
    event_names: frozenset[EventName]
    callback: EventHook


def validate_event_hook_registration(implementation: object) -> bool:
    """Return whether a registration satisfies the version-one hook contract."""

    return bool(
        type(implementation) is EventHookRegistration
        and type(implementation.hook_id) is str
        and bool(implementation.hook_id)
        and type(implementation.event_names) is frozenset
        and bool(implementation.event_names)
        and implementation.event_names <= EVENT_HOOK_NAMES
        and callable(implementation.callback)
    )


def event_hook_extension_contract() -> ExtensionContract:
    """Return the configured unified-registry contract for event hooks."""

    return ExtensionContract(
        identity_resolver=lambda implementation: implementation.hook_id,
        validator=validate_event_hook_registration,
    )


def _sanitize_event_text(
    value: object,
    *,
    fallback: str,
    max_length: int,
) -> str:
    sanitized = sanitize_diagnostic_text(value, max_length=max_length)
    return sanitized or fallback


def _resolve_event_hook_registrations() -> tuple[ExtensionRegistration, ...]:
    from src.application_services import get_application_services

    return get_application_services().plugin_manager.registrations("event_hook")


def _dispatch_event(
    name: EventName,
    *,
    trace_id: str | None,
    payload: Mapping[str, object],
) -> None:
    """Dispatch one immutable snapshot without exposing callback outcomes."""

    try:
        registrations = _resolve_event_hook_registrations()
    except Exception as exc:  # broad-exception: fallback_recorded - Hook discovery cannot change the analysis outcome.
        log_safe_exception(
            logger,
            "Plugin event hook discovery failed",
            exc,
            error_code="plugin_event_hook_discovery_failed",
            level=logging.WARNING,
            context={"event_name": name},
        )
        return
    if not registrations:
        return

    matching = tuple(
        registration
        for registration in registrations
        if name in registration.implementation.event_names
    )
    if not matching:
        return

    try:
        event = PluginEvent(
            name=name,
            schema_version=EVENT_HOOK_SCHEMA_VERSION,
            occurred_at=datetime.now(timezone.utc),
            trace_id=(
                _sanitize_event_text(
                    trace_id,
                    fallback="unknown",
                    max_length=128,
                )
                if trace_id is not None
                else None
            ),
            payload=payload,
        )
    except Exception as exc:  # broad-exception: fallback_recorded - Invalid core event data is recorded and never reaches the analysis path.
        log_safe_exception(
            logger,
            "Plugin event snapshot construction failed",
            exc,
            error_code="plugin_event_snapshot_invalid",
            level=logging.WARNING,
            context={"event_name": name},
        )
        return

    for registration in matching:
        try:
            registration.implementation.callback(event)
        except Exception as exc:  # broad-exception: fallback_recorded - Every hook failure is isolated before later callbacks continue.
            log_safe_exception(
                logger,
                "Plugin event hook callback failed",
                exc,
                error_code="plugin_event_hook_callback_failed",
                level=logging.WARNING,
                context={
                    "event_name": name,
                    "hook_id": registration.registration_id,
                    "plugin_id": registration.plugin_id,
                },
            )


def dispatch_analysis_event(
    name: AnalysisEventName,
    *,
    task_id: str,
    trace_id: str | None,
    stock_code: str,
    trigger_source: str,
    result_reference: str | None = None,
    error_code: str | None = None,
) -> None:
    """Project and dispatch one stock-analysis lifecycle event."""

    if name not in _ANALYSIS_EVENT_NAMES:
        return
    payload: dict[str, object] = {
        "task_id": _sanitize_event_text(task_id, fallback="unknown", max_length=128),
        "stock_code": _sanitize_event_text(stock_code, fallback="unknown", max_length=64),
    }
    if name == "analysis.started":
        payload["trigger_source"] = _sanitize_event_text(
            trigger_source,
            fallback="unknown",
            max_length=64,
        )
    else:
        payload["terminal_status"] = "completed" if name == "analysis.completed" else "failed"
    if name == "analysis.completed" and result_reference:
        payload["result_reference"] = _sanitize_event_text(
            result_reference,
            fallback="unknown",
            max_length=128,
        )
    if name == "analysis.failed":
        payload["error_code"] = _sanitize_event_text(
            error_code,
            fallback="analysis_failed",
            max_length=64,
        )
    _dispatch_event(name, trace_id=trace_id, payload=payload)


def dispatch_market_review_event(
    name: MarketReviewEventName,
    *,
    task_id: str,
    trace_id: str | None,
    market_region: str,
    trigger_source: str,
    result_reference: str | None = None,
    error_code: str | None = None,
) -> None:
    """Project and dispatch one market-review lifecycle event."""

    if name not in _MARKET_REVIEW_EVENT_NAMES:
        return
    payload: dict[str, object] = {
        "task_id": _sanitize_event_text(task_id, fallback="unknown", max_length=128),
        "market_region": _sanitize_event_text(
            market_region,
            fallback="unknown",
            max_length=64,
        ),
    }
    if name == "market_review.started":
        payload["trigger_source"] = _sanitize_event_text(
            trigger_source,
            fallback="unknown",
            max_length=64,
        )
    else:
        payload["terminal_status"] = (
            "completed" if name == "market_review.completed" else "failed"
        )
    if name == "market_review.completed" and result_reference:
        payload["result_reference"] = _sanitize_event_text(
            result_reference,
            fallback="unknown",
            max_length=128,
        )
    if name == "market_review.failed":
        payload["error_code"] = _sanitize_event_text(
            error_code,
            fallback="market_review_failed",
            max_length=64,
        )
    _dispatch_event(name, trace_id=trace_id, payload=payload)


__all__ = [
    "AnalysisEventName",
    "EVENT_HOOK_NAMES",
    "EVENT_HOOK_SCHEMA_VERSION",
    "EventHook",
    "EventHookRegistration",
    "EventName",
    "MarketReviewEventName",
    "PluginEvent",
    "dispatch_analysis_event",
    "dispatch_market_review_event",
    "event_hook_extension_contract",
    "validate_event_hook_registration",
]
