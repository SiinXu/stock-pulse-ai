# -*- coding: utf-8 -*-
"""Lightweight run diagnostic context for one analysis trace.

This module intentionally keeps Phase 1 diagnostics in memory and fail-open.
Persistence can reuse existing analysis context snapshots until a dedicated
diagnostic store is introduced.
"""

from __future__ import annotations

import logging
import time  # noqa: F401  # patch seam: tests/core/test_pipeline_stage_observability.py
from collections.abc import Mapping
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from src.utils.sanitize import log_safe_exception

from src.services.diagnostics.schema import (
    PIPELINE_STAGE_NAMES,
    PIPELINE_STAGE_STATUSES,
    DataQualityEvidenceRecord,
    HistoryRun,
    LLMRun,
    NotificationRun,
    PipelineStageRun,
    ProviderRun,
    RunDiagnosticComponent,
    RunDiagnosticSummary,
    _redact_diagnostic_payload,
    build_trace_id,
    safe_diagnostic_key,
    sanitize_diagnostic_metadata,
    sanitize_diagnostic_text,
    sanitize_finite_diagnostic_metadata,
)
from src.services.diagnostics import collect as _diagnostics_collect
from src.services.diagnostics.collect import (
    PipelineStageObservation,
    _agent_flow_event,
    _history_flow_event,
    _llm_flow_event,
    _llm_pending_key,
    _llm_started_flow_event,
    _notification_flow_event,
    _provider_flow_event,
    _provider_pending_key,
    _provider_started_flow_event,
    _public_prompt_artifact_versions,
    _safe_event_key,
    attach_prompt_artifact_versions,
    observe_pipeline_stage,
    record_missing_pipeline_stages_as_skipped,
)
from src.services.diagnostics.export import (
    build_run_diagnostic_summary,
    format_copyable_diagnostics,
)

logger = logging.getLogger(__name__)

_CURRENT_CONTEXT: ContextVar[Optional["RunDiagnosticContext"]] = ContextVar(
    "run_diagnostic_context",
    default=None,
)


@dataclass
class RunDiagnosticContext:
    """Diagnostic state for one analysis run."""

    trace_id: str
    task_id: Optional[str] = None
    query_id: Optional[str] = None
    stock_code: Optional[str] = None
    trigger_source: Optional[str] = None
    scope: Optional[str] = None
    provider_runs: List[ProviderRun] = field(default_factory=list)
    data_quality_evidence: List[DataQualityEvidenceRecord] = field(default_factory=list)
    llm_runs: List[LLMRun] = field(default_factory=list)
    notification_runs: List[NotificationRun] = field(default_factory=list)
    history_runs: List[HistoryRun] = field(default_factory=list)
    pipeline_stage_runs: List[PipelineStageRun] = field(default_factory=list)
    agent_events: List[Dict[str, Any]] = field(default_factory=list)
    agent_events_original_count: int = 0
    agent_events_dropped_count: int = 0
    event_sink: Optional[Callable[[Dict[str, Any]], None]] = None
    flow_event_index: int = 0
    agent_event_index: int = 0
    agent_tool_index: int = 0
    provider_attempt_index_by_type: Dict[str, int] = field(default_factory=dict)
    provider_pending_attempt_index_by_key: Dict[str, List[int]] = field(default_factory=dict)
    llm_attempt_index_by_type: Dict[str, int] = field(default_factory=dict)
    llm_pending_attempt_index_by_key: Dict[str, List[int]] = field(default_factory=dict)
    llm_pending_attempt_index_by_call_type: Dict[str, List[int]] = field(default_factory=dict)
    # Skill / key-prompt version identity for the active run (issue #249).
    prompt_artifact_versions: Optional[Dict[str, Any]] = None

    def record_provider_run(self, provider_run: ProviderRun) -> None:
        self.provider_runs.append(provider_run)
        data_type_key = _safe_event_key(provider_run.data_type) or "provider"
        pending_key = _provider_pending_key(
            provider_run.data_type,
            provider_run.provider,
            provider_run.operation,
        )
        pending_indexes = self.provider_pending_attempt_index_by_key.get(pending_key) or []
        if pending_indexes:
            attempt_index = pending_indexes.pop(0)
            if pending_indexes:
                self.provider_pending_attempt_index_by_key[pending_key] = pending_indexes
            else:
                self.provider_pending_attempt_index_by_key.pop(pending_key, None)
        else:
            attempt_index = self.provider_attempt_index_by_type.get(data_type_key, 0) + 1
            self.provider_attempt_index_by_type[data_type_key] = attempt_index
        self._emit_flow_event(_provider_flow_event(self, provider_run, attempt_index))

    def record_data_quality_evidence(
        self,
        evidence: DataQualityEvidenceRecord,
    ) -> None:
        """Append one bounded finding set and suppress immediate duplicates."""
        if self.data_quality_evidence:
            previous = self.data_quality_evidence[-1]
            if (
                previous.data_type == evidence.data_type
                and previous.symbol == evidence.symbol
                and previous.provider == evidence.provider
                and previous.severity == evidence.severity
                and previous.rejected == evidence.rejected
                and previous.issues == evidence.issues
            ):
                return
        self.data_quality_evidence.append(evidence)
        if len(self.data_quality_evidence) > 100:
            del self.data_quality_evidence[: len(self.data_quality_evidence) - 100]

    def record_provider_run_started(
        self,
        *,
        data_type: str,
        provider: str,
        operation: str,
    ) -> None:
        data_type_key = _safe_event_key(data_type) or "provider"
        attempt_index = self.provider_attempt_index_by_type.get(data_type_key, 0) + 1
        self.provider_attempt_index_by_type[data_type_key] = attempt_index
        pending_key = _provider_pending_key(data_type, provider, operation)
        pending_indexes = self.provider_pending_attempt_index_by_key.get(pending_key) or []
        pending_indexes.append(attempt_index)
        self.provider_pending_attempt_index_by_key[pending_key] = pending_indexes
        self._emit_flow_event(
            _provider_started_flow_event(
                self,
                data_type=data_type,
                provider=provider,
                operation=operation,
                index=attempt_index,
            )
        )

    def record_llm_run(self, llm_run: LLMRun) -> None:
        self.llm_runs.append(llm_run)
        call_type_key = _safe_event_key(llm_run.call_type) or "analysis"
        pending_key = _llm_pending_key(llm_run.call_type, llm_run.provider, llm_run.model)
        pending_indexes = self.llm_pending_attempt_index_by_key.get(pending_key) or []
        if pending_indexes:
            attempt_index = pending_indexes.pop(0)
            if pending_indexes:
                self.llm_pending_attempt_index_by_key[pending_key] = pending_indexes
            else:
                self.llm_pending_attempt_index_by_key.pop(pending_key, None)
            self._remove_llm_pending_call_type_index(call_type_key, attempt_index)
        else:
            call_type_pending_indexes = self.llm_pending_attempt_index_by_call_type.get(call_type_key) or []
            if call_type_pending_indexes:
                attempt_index = call_type_pending_indexes.pop(0)
                if call_type_pending_indexes:
                    self.llm_pending_attempt_index_by_call_type[call_type_key] = call_type_pending_indexes
                else:
                    self.llm_pending_attempt_index_by_call_type.pop(call_type_key, None)
                self._remove_llm_pending_exact_index(attempt_index)
            else:
                attempt_index = self.llm_attempt_index_by_type.get(call_type_key, 0) + 1
                self.llm_attempt_index_by_type[call_type_key] = attempt_index
        self._emit_flow_event(_llm_flow_event(self, llm_run, attempt_index))

    def _remove_llm_pending_call_type_index(self, call_type_key: str, attempt_index: int) -> None:
        pending_indexes = self.llm_pending_attempt_index_by_call_type.get(call_type_key) or []
        if attempt_index not in pending_indexes:
            return
        pending_indexes = [index for index in pending_indexes if index != attempt_index]
        if pending_indexes:
            self.llm_pending_attempt_index_by_call_type[call_type_key] = pending_indexes
        else:
            self.llm_pending_attempt_index_by_call_type.pop(call_type_key, None)

    def _remove_llm_pending_exact_index(self, attempt_index: int) -> None:
        for pending_key, pending_indexes in list(self.llm_pending_attempt_index_by_key.items()):
            if attempt_index not in pending_indexes:
                continue
            pending_indexes = [index for index in pending_indexes if index != attempt_index]
            if pending_indexes:
                self.llm_pending_attempt_index_by_key[pending_key] = pending_indexes
            else:
                self.llm_pending_attempt_index_by_key.pop(pending_key, None)

    def record_llm_run_started(
        self,
        *,
        call_type: str = "analysis",
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        call_type_key = _safe_event_key(call_type) or "analysis"
        attempt_index = self.llm_attempt_index_by_type.get(call_type_key, 0) + 1
        self.llm_attempt_index_by_type[call_type_key] = attempt_index
        pending_key = _llm_pending_key(call_type, provider, model)
        pending_indexes = self.llm_pending_attempt_index_by_key.get(pending_key) or []
        pending_indexes.append(attempt_index)
        self.llm_pending_attempt_index_by_key[pending_key] = pending_indexes
        call_type_pending_indexes = self.llm_pending_attempt_index_by_call_type.get(call_type_key) or []
        call_type_pending_indexes.append(attempt_index)
        self.llm_pending_attempt_index_by_call_type[call_type_key] = call_type_pending_indexes
        self._emit_flow_event(
            _llm_started_flow_event(
                self,
                call_type=call_type,
                provider=provider,
                model=model,
                index=attempt_index,
            )
        )

    def record_notification_run(self, notification_run: NotificationRun) -> None:
        self.notification_runs.append(notification_run)
        self._emit_flow_event(_notification_flow_event(self, notification_run, len(self.notification_runs)))

    def record_history_run(self, history_run: HistoryRun) -> None:
        self.history_runs.append(history_run)
        self._emit_flow_event(_history_flow_event(self, history_run, len(self.history_runs)))

    def record_pipeline_stage(self, stage_run: PipelineStageRun) -> None:
        """Append a Pipeline stage without changing existing Run Flow events."""
        self.pipeline_stage_runs.append(stage_run)

    def record_agent_event(self, event: Mapping[str, Any]) -> None:
        """Append one sanitized agent observability event and mirror it to run-flow."""
        payload = dict(event) if isinstance(event, Mapping) else {}
        if not payload:
            return
        sanitized, finite = sanitize_finite_diagnostic_metadata(payload)
        if not isinstance(sanitized, Mapping):
            return
        entry = dict(sanitized)
        if not finite:
            entry["detail_integrity"] = "invalid_non_finite"
        self.agent_events_original_count += 1
        self.agent_events.append(entry)
        max_events = 200
        if len(self.agent_events) > max_events:
            dropped = len(self.agent_events) - max_events
            self.agent_events_dropped_count += dropped
            del self.agent_events[:dropped]
        live_entry = {
            **entry,
            "capture": {
                "original_count": self.agent_events_original_count,
                "returned_count": len(self.agent_events),
                "dropped_count": self.agent_events_dropped_count,
                "truncated": self.agent_events_dropped_count > 0,
            },
        }
        self._emit_flow_event(_agent_flow_event(self, live_entry))

    def _emit_flow_event(self, event: Dict[str, Any]) -> None:
        if self.event_sink is None:
            return
        try:
            self.flow_event_index += 1
            event_payload = sanitize_diagnostic_metadata(event)
            event_payload = dict(event_payload) if isinstance(event_payload, Mapping) else {}
            event_payload["id"] = event_payload.get("id") or f"flow_{self.flow_event_index:04d}"
            self.event_sink(event_payload)
        except Exception as exc:  # pragma: no cover - defensive fail-open guard
            log_safe_exception(
                logger,
                "Run Flow event sink failed",
                exc,
                error_code="run_flow_event_sink_failed",
                level=logging.WARNING,
                trace_id=self.trace_id,
            )

    def snapshot(self) -> Dict[str, Any]:
        payload = {
            "trace_id": self.trace_id,
            "task_id": self.task_id,
            "query_id": self.query_id,
            "stock_code": self.stock_code,
            "trigger_source": self.trigger_source,
            "scope": self.scope,
            "provider_runs": [run.to_dict() for run in self.provider_runs],
            "data_quality_evidence": [
                evidence.to_dict() for evidence in self.data_quality_evidence
            ],
            "llm_runs": [run.to_dict() for run in self.llm_runs],
            "notification_runs": [run.to_dict() for run in self.notification_runs],
            "history_runs": [run.to_dict() for run in self.history_runs],
            "pipeline_stage_runs": [run.to_dict() for run in self.pipeline_stage_runs],
            "agent_events": list(self.agent_events),
            "agent_events_capture": {
                "original_count": self.agent_events_original_count,
                "returned_count": len(self.agent_events),
                "dropped_count": self.agent_events_dropped_count,
                "truncated": self.agent_events_dropped_count > 0,
            },
        }
        redacted = _redact_diagnostic_payload(payload)
        if isinstance(self.prompt_artifact_versions, dict):
            public = _public_prompt_artifact_versions(self.prompt_artifact_versions)
            redacted["prompt_artifact_versions"] = public
            if public.get("prompt_version") is not None:
                redacted["prompt_version"] = public["prompt_version"]
            if public.get("skill_versions"):
                redacted["skill_versions"] = dict(public["skill_versions"])
        return redacted


record_data_quality_evidence = _diagnostics_collect.record_data_quality_evidence
record_pipeline_stage = _diagnostics_collect.record_pipeline_stage


def get_current_diagnostic_context() -> Optional[RunDiagnosticContext]:
    return _CURRENT_CONTEXT.get()


def activate_run_diagnostic_context(
    *,
    trace_id: Optional[str] = None,
    task_id: Optional[str] = None,
    query_id: Optional[str] = None,
    stock_code: Optional[str] = None,
    trigger_source: Optional[str] = None,
    scope: Optional[str] = None,
    event_sink: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Token:
    """Activate a diagnostic context and return its reset token."""
    context = RunDiagnosticContext(
        trace_id=trace_id or query_id or task_id or build_trace_id(),
        task_id=task_id,
        query_id=query_id,
        stock_code=stock_code,
        trigger_source=trigger_source,
        scope=scope,
        event_sink=event_sink,
    )
    return _CURRENT_CONTEXT.set(context)


def reset_run_diagnostic_context(token: Optional[Token]) -> None:
    if token is None:
        return
    try:
        _CURRENT_CONTEXT.reset(token)
    except Exception as exc:  # pragma: no cover - defensive fail-open guard
        log_safe_exception(
            logger,
            "Run diagnostic context reset failed",
            exc,
            error_code="run_diagnostic_context_reset_failed",
            level=logging.WARNING,
        )


def current_diagnostic_snapshot() -> Optional[Dict[str, Any]]:
    context = get_current_diagnostic_context()
    if context is None:
        return None
    try:
        return context.snapshot()
    except Exception as exc:  # pragma: no cover - defensive fail-open guard
        log_safe_exception(
            logger,
            "Run diagnostic snapshot failed",
            exc,
            error_code="run_diagnostic_snapshot_failed",
            level=logging.WARNING,
            trace_id=context.trace_id,
        )
        return None


def record_provider_run(
    *,
    data_type: str,
    provider: str,
    operation: str,
    success: bool,
    latency_ms: Optional[int] = None,
    error_type: Optional[str] = None,
    error_message: Optional[Any] = None,
    fallback_from: Optional[str] = None,
    fallback_to: Optional[str] = None,
    cache_hit: Optional[bool] = None,
    stale_seconds: Optional[int] = None,
    record_count: Optional[int] = None,
) -> None:
    """Append a provider attempt to the active context without affecting callers."""
    context = get_current_diagnostic_context()
    if context is None:
        return

    try:
        context.record_provider_run(
            ProviderRun(
                trace_id=context.trace_id,
                data_type=data_type,
                provider=provider,
                operation=operation,
                success=success,
                latency_ms=latency_ms,
                error_type=error_type,
                error_message_sanitized=sanitize_diagnostic_text(error_message),
                fallback_from=fallback_from,
                fallback_to=fallback_to,
                cache_hit=cache_hit,
                stale_seconds=stale_seconds,
                record_count=record_count,
            )
        )
    except Exception as exc:  # pragma: no cover - defensive fail-open guard
        log_safe_exception(
            logger,
            "Provider diagnostic record failed",
            exc,
            error_code="provider_diagnostic_record_failed",
            level=logging.WARNING,
            trace_id=context.trace_id,
        )


def record_provider_run_started(
    *,
    data_type: str,
    provider: str,
    operation: str,
) -> None:
    """Emit a live provider-start event without changing persisted diagnostics."""
    context = get_current_diagnostic_context()
    if context is None:
        return

    try:
        context.record_provider_run_started(
            data_type=data_type,
            provider=provider,
            operation=operation,
        )
    except Exception as exc:  # pragma: no cover - defensive fail-open guard
        log_safe_exception(
            logger,
            "Provider start diagnostic record failed",
            exc,
            error_code="provider_start_diagnostic_record_failed",
            level=logging.WARNING,
            trace_id=context.trace_id,
        )


def record_llm_run(
    *,
    success: bool,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    call_type: str = "analysis",
    tokens: Optional[int] = None,
    duration_ms: Optional[int] = None,
    fallback_model: Optional[str] = None,
    error_type: Optional[str] = None,
    error_message: Optional[Any] = None,
) -> None:
    """Append an LLM call result to the active context without affecting callers."""
    context = get_current_diagnostic_context()
    if context is None:
        return

    try:
        context.record_llm_run(
            LLMRun(
                trace_id=context.trace_id,
                provider=provider,
                model=model,
                call_type=call_type,
                success=success,
                tokens=tokens,
                duration_ms=duration_ms,
                fallback_model=fallback_model,
                error_type=error_type,
                error_message_sanitized=sanitize_diagnostic_text(error_message),
            )
        )
    except Exception as exc:  # pragma: no cover - defensive fail-open guard
        log_safe_exception(
            logger,
            "LLM diagnostic record failed",
            exc,
            error_code="llm_diagnostic_record_failed",
            level=logging.WARNING,
            trace_id=context.trace_id,
        )


def record_llm_run_started(
    *,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    call_type: str = "analysis",
) -> None:
    """Emit a live LLM-start event without changing persisted diagnostics."""
    context = get_current_diagnostic_context()
    if context is None:
        return

    try:
        context.record_llm_run_started(
            provider=provider,
            model=model,
            call_type=call_type,
        )
    except Exception as exc:  # pragma: no cover - defensive fail-open guard
        log_safe_exception(
            logger,
            "LLM start diagnostic record failed",
            exc,
            error_code="llm_start_diagnostic_record_failed",
            level=logging.WARNING,
            trace_id=context.trace_id,
        )


def record_notification_run(
    *,
    channel: str,
    status: str,
    success: bool,
    attempts: int = 1,
    error_message: Optional[Any] = None,
) -> None:
    """Append a notification result to the active context without affecting callers."""
    context = get_current_diagnostic_context()
    if context is None:
        return

    try:
        context.record_notification_run(
            NotificationRun(
                trace_id=context.trace_id,
                channel=channel,
                status=status,
                success=success,
                attempts=attempts,
                error_message_sanitized=sanitize_diagnostic_text(error_message),
            )
        )
    except Exception as exc:  # pragma: no cover - defensive fail-open guard
        log_safe_exception(
            logger,
            "Notification diagnostic record failed",
            exc,
            error_code="notification_diagnostic_record_failed",
            level=logging.WARNING,
            trace_id=context.trace_id,
        )


def record_history_run(
    *,
    report_saved: bool,
    metadata_saved: Optional[bool] = None,
    analysis_history_id: Optional[int] = None,
    error_message: Optional[Any] = None,
) -> None:
    """Append a history persistence result to the active context without affecting callers."""
    context = get_current_diagnostic_context()
    if context is None:
        return

    try:
        context.record_history_run(
            HistoryRun(
                trace_id=context.trace_id,
                report_saved=report_saved,
                metadata_saved=metadata_saved,
                analysis_history_id=analysis_history_id,
                error_message_sanitized=sanitize_diagnostic_text(error_message),
            )
        )
    except Exception as exc:  # pragma: no cover - defensive fail-open guard
        log_safe_exception(
            logger,
            "History diagnostic record failed",
            exc,
            error_code="history_diagnostic_record_failed",
            level=logging.WARNING,
            trace_id=context.trace_id,
        )


__all__ = (
    "PIPELINE_STAGE_NAMES",
    "PIPELINE_STAGE_STATUSES",
    "DataQualityEvidenceRecord",
    "HistoryRun",
    "LLMRun",
    "NotificationRun",
    "PipelineStageObservation",
    "PipelineStageRun",
    "ProviderRun",
    "RunDiagnosticComponent",
    "RunDiagnosticContext",
    "RunDiagnosticSummary",
    "activate_run_diagnostic_context",
    "attach_prompt_artifact_versions",
    "build_run_diagnostic_summary",
    "build_trace_id",
    "current_diagnostic_snapshot",
    "format_copyable_diagnostics",
    "get_current_diagnostic_context",
    "observe_pipeline_stage",
    "record_data_quality_evidence",
    "record_history_run",
    "record_llm_run",
    "record_llm_run_started",
    "record_missing_pipeline_stages_as_skipped",
    "record_notification_run",
    "record_pipeline_stage",
    "record_provider_run",
    "record_provider_run_started",
    "reset_run_diagnostic_context",
    "safe_diagnostic_key",
    "sanitize_diagnostic_metadata",
    "sanitize_diagnostic_text",
    "sanitize_finite_diagnostic_metadata",
)
