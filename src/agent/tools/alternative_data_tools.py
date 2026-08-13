# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""ToolSurface contract for alternative-data briefs (Issues #139 / #1144).

Default-off: the factory is intentionally absent from the process tool catalog.
A composition caller or trusted plugin must register the definition explicitly.
Every call requires ``alt_data:read``; missing capability is denied by ToolSurface.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Literal, Protocol

from pydantic import ValidationError

from src.agent.tools.execution import _normalize_tool_stock_code
from src.agent.tools.registry import ToolDefinition, ToolParameter, ToolPolicy
from src.schemas.alternative_data import (
    ALT_DATA_DISCLAIMER,
    ALT_DATA_PERMISSION,
    ALTERNATIVE_DATA_SCHEMA_VERSION,
    AlternativeDataCitation,
    AlternativeDataCoverage,
    AlternativeDataObservation,
    AlternativeDataReasonCode,
    AlternativeDataResult,
    AlternativeDataResultStatus,
    CorporateEventItem,
)
from src.utils.sanitize import (
    exception_chain_redaction_values,
    log_safe_exception,
    redact_sensitive_text,
)

logger = logging.getLogger(__name__)

CORPORATE_EVENTS_TOOL_NAME = "get_corporate_events_brief"
CORPORATE_EVENTS_CATEGORY: Literal["corporate_events"] = "corporate_events"
ALT_DATA_DEFAULT_WINDOW_DAYS = 30
ALT_DATA_MAX_WINDOW_DAYS = 90
ALT_DATA_MAX_RESULT_BYTES = 8 * 1024

_STOCK_CODE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9.-]{0,15}$"

_ALT_DATA_POLICY = ToolPolicy.declared(
    read_only=True,
    side_effects=["network_read"],
    permissions=[ALT_DATA_PERMISSION],
    scope_dimensions=["stock"],
)

_DEGRADED_SUMMARIES: dict[AlternativeDataReasonCode, str] = {
    "partial_coverage": "Alternative corporate-event coverage is partial.",
    "provider_not_configured": "Alternative corporate-event data is not configured.",
    "provider_timeout": "Alternative corporate-event data was not available within the bounded time window.",
    "no_data": "No alternative corporate-event data was available for the requested stock and window.",
    "provider_error": "Alternative corporate-event data is temporarily unavailable.",
    "invalid_provider_output": "Alternative corporate-event data was rejected because its contract was invalid.",
    "output_too_large": "Alternative corporate-event data was rejected because its bounded payload limit was exceeded.",
    "feature_disabled": "Alternative corporate-event data is disabled for this deployment.",
    "capability_denied": "Session lacks alt_data:read capability for alternative data.",
}


class CorporateEventsProvider(Protocol):
    @property
    def is_configured(self) -> bool: ...

    def get_events(
        self,
        *,
        stock_code: str,
        window_days: int,
        language_hint: Literal["zh", "en"],
    ) -> AlternativeDataObservation | None: ...


def _canonical_code(stock_code: str) -> str:
    canonical = _normalize_tool_stock_code(stock_code)
    if not isinstance(canonical, str):
        raise ValueError("stock code must normalize to a string")
    return canonical


def _safe_text(value: str, max_chars: int) -> str:
    return redact_sensitive_text(value, redact_opaque_tokens=True)[:max_chars]


def _safe_identifier(value: str) -> str:
    safe = redact_sensitive_text(value, redact_opaque_tokens=True)
    if safe != value:
        raise ValueError("source identity contained sensitive material")
    return safe


def _result_dict(result: AlternativeDataResult) -> dict[str, Any]:
    return result.model_dump(mode="json")


def _serialized_size(payload: dict[str, Any]) -> int:
    return len(
        json.dumps(payload, ensure_ascii=False, allow_nan=False, default=str).encode(
            "utf-8"
        )
    )


def degraded_corporate_events_result(
    *,
    stock_code: str,
    language: Literal["zh", "en"],
    reason_code: AlternativeDataReasonCode,
    status: Literal["degraded", "unavailable"] = "unavailable",
    gaps: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Build a typed non-success payload without inventing events or confidence."""

    merged_gaps = tuple(dict.fromkeys((reason_code, *gaps)))[:12]
    return _result_dict(
        AlternativeDataResult(
            status=status,
            degraded=True,
            reason_code=reason_code,
            category=CORPORATE_EVENTS_CATEGORY,
            stock_code=stock_code,
            language=language,
            as_of=None,
            summary=_DEGRADED_SUMMARIES[reason_code],
            confidence=None,
            confidence_basis="No confidence score is reported without validated source evidence.",
            events=(),
            coverage=(),
            citations=(),
            gaps=merged_gaps,
            authority="non_authoritative",
            role="supporting_only",
            disclaimer=ALT_DATA_DISCLAIMER,
        )
    )


def _project_observation(
    observation: AlternativeDataObservation,
    *,
    stock_code: str,
    language: Literal["zh", "en"],
) -> dict[str, Any]:
    if (
        _canonical_code(observation.stock_code) != stock_code
        or observation.language != language
        or observation.category != CORPORATE_EVENTS_CATEGORY
    ):
        raise ValueError("provider observation does not match the requested scope")
    coverage = tuple(
        AlternativeDataCoverage(
            source_id=_safe_identifier(item.source_id),
            status=item.status,
            as_of=item.as_of,
        )
        for item in observation.coverage
    )
    citations = tuple(
        AlternativeDataCitation(
            source_id=_safe_identifier(item.source_id),
            reference_id=_safe_text(item.reference_id, 160),
            url=_safe_text(item.url, 500) if item.url is not None else None,
        )
        for item in observation.citations
    )
    events = tuple(
        CorporateEventItem(
            event_id=_safe_text(item.event_id, 64),
            event_type=_safe_text(item.event_type, 64),
            title=_safe_text(item.title, 240),
            event_date=_safe_text(item.event_date, 40),
            impact_hint=item.impact_hint,
            source_id=_safe_identifier(item.source_id),
            confidence=item.confidence,
        )
        for item in observation.events
    )
    gaps = tuple(_safe_text(item, 120) for item in observation.gaps)
    is_partial = bool(gaps) or any(item.status != "available" for item in coverage)
    status: AlternativeDataResultStatus = "degraded" if is_partial else "available"
    reason_code: AlternativeDataReasonCode | None = (
        "partial_coverage" if is_partial else None
    )
    return _result_dict(
        AlternativeDataResult(
            status=status,
            degraded=is_partial,
            reason_code=reason_code,
            category=CORPORATE_EVENTS_CATEGORY,
            stock_code=stock_code,
            language=language,
            as_of=observation.as_of,
            summary=_safe_text(observation.summary, 1200),
            confidence=observation.confidence,
            confidence_basis=_safe_text(observation.confidence_basis, 240),
            events=events,
            coverage=coverage,
            citations=citations,
            gaps=gaps,
            authority="non_authoritative",
            role="supporting_only",
            disclaimer=ALT_DATA_DISCLAIMER,
        )
    )


class _CorporateEventsToolHandler:
    def __init__(self, provider: CorporateEventsProvider | None) -> None:
        self._provider = provider

    def __call__(
        self,
        stock_code: str,
        window_days: int = ALT_DATA_DEFAULT_WINDOW_DAYS,
        language_hint: Literal["zh", "en"] = "en",
    ) -> dict[str, Any]:
        canonical_code = _canonical_code(stock_code)
        try:
            resolved_window = int(window_days)
        except (TypeError, ValueError):
            resolved_window = ALT_DATA_DEFAULT_WINDOW_DAYS
        if resolved_window < 1:
            resolved_window = 1
        if resolved_window > ALT_DATA_MAX_WINDOW_DAYS:
            resolved_window = ALT_DATA_MAX_WINDOW_DAYS
        if self._provider is None:
            return degraded_corporate_events_result(
                stock_code=canonical_code,
                language=language_hint,
                reason_code="provider_not_configured",
                status="unavailable",
            )
        try:
            configured = self._provider.is_configured
            if type(configured) is not bool:
                return degraded_corporate_events_result(
                    stock_code=canonical_code,
                    language=language_hint,
                    reason_code="invalid_provider_output",
                    status="degraded",
                )
            if not configured:
                return degraded_corporate_events_result(
                    stock_code=canonical_code,
                    language=language_hint,
                    reason_code="provider_not_configured",
                    status="unavailable",
                )
            observation = self._provider.get_events(
                stock_code=canonical_code,
                window_days=resolved_window,
                language_hint=language_hint,
            )
        except TimeoutError as exc:
            log_safe_exception(
                logger,
                "Alternative corporate-events provider timed out",
                exc,
                error_code="alt_data_provider_timeout",
                level=logging.WARNING,
                context={"stock_code": canonical_code},
                exception_redaction_values=exception_chain_redaction_values(exc),
            )
            return degraded_corporate_events_result(
                stock_code=canonical_code,
                language=language_hint,
                reason_code="provider_timeout",
                status="degraded",
            )
        except Exception as exc:  # broad-exception: fallback_recorded - Typed optional-provider degradation.
            log_safe_exception(
                logger,
                "Alternative corporate-events provider failed",
                exc,
                error_code="alt_data_provider_failed",
                level=logging.WARNING,
                context={"stock_code": canonical_code},
                exception_redaction_values=exception_chain_redaction_values(exc),
            )
            return degraded_corporate_events_result(
                stock_code=canonical_code,
                language=language_hint,
                reason_code="provider_error",
                status="degraded",
            )
        if observation is None:
            return degraded_corporate_events_result(
                stock_code=canonical_code,
                language=language_hint,
                reason_code="no_data",
                status="unavailable",
            )
        if not isinstance(observation, AlternativeDataObservation):
            return degraded_corporate_events_result(
                stock_code=canonical_code,
                language=language_hint,
                reason_code="invalid_provider_output",
                status="degraded",
            )
        try:
            observation = AlternativeDataObservation.model_validate(observation)
            payload = _project_observation(
                observation,
                stock_code=canonical_code,
                language=language_hint,
            )
        except (AttributeError, TypeError, ValueError, ValidationError):
            return degraded_corporate_events_result(
                stock_code=canonical_code,
                language=language_hint,
                reason_code="invalid_provider_output",
                status="degraded",
            )
        if _serialized_size(payload) > ALT_DATA_MAX_RESULT_BYTES:
            return degraded_corporate_events_result(
                stock_code=canonical_code,
                language=language_hint,
                reason_code="output_too_large",
                status="degraded",
            )
        return payload


def build_corporate_events_tool(
    provider: CorporateEventsProvider | None = None,
) -> ToolDefinition:
    """Build an explicitly registered corporate-events alternative-data tool.

    Not registered in the default process catalog. Requires ``alt_data:read``.
    """

    return ToolDefinition(
        name=CORPORATE_EVENTS_TOOL_NAME,
        description=(
            "Return a bounded, non-authoritative corporate-events brief for the "
            "stock already authorized in the current analysis scope. Supporting "
            "evidence only; never treat as verified fact or trading authority."
        ),
        parameters=[
            ToolParameter(
                name="stock_code",
                type="string",
                description="Stock code already authorized by the current analysis scope.",
                pattern=_STOCK_CODE_PATTERN,
            ),
            ToolParameter(
                name="window_days",
                type="integer",
                description="Bounded event window in calendar days (1-90).",
                required=False,
                default=ALT_DATA_DEFAULT_WINDOW_DAYS,
                minimum=1,
                maximum=ALT_DATA_MAX_WINDOW_DAYS,
            ),
            ToolParameter(
                name="language_hint",
                type="string",
                description="Preferred brief language.",
                required=False,
                default="en",
                enum=["zh", "en"],
            ),
        ],
        handler=_CorporateEventsToolHandler(provider),
        category="data",
        policy=_ALT_DATA_POLICY,
        enforce_contract=True,
    )


__all__ = [
    "ALT_DATA_DISCLAIMER",
    "ALT_DATA_MAX_RESULT_BYTES",
    "ALT_DATA_PERMISSION",
    "ALTERNATIVE_DATA_SCHEMA_VERSION",
    "CORPORATE_EVENTS_CATEGORY",
    "CORPORATE_EVENTS_TOOL_NAME",
    "CorporateEventsProvider",
    "build_corporate_events_tool",
    "degraded_corporate_events_result",
]
