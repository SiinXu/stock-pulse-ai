# -*- coding: utf-8 -*-
"""Read-only run-diagnostic collection helpers.

These helpers record into the active diagnostic context only. They must not
mutate analysis inputs, analysis outcomes, or unrelated global runtime state.
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta
from itertools import islice
from typing import Any, Dict, List, Optional, TYPE_CHECKING

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
    safe_diagnostic_key,
    sanitize_diagnostic_metadata,
    sanitize_diagnostic_text,
    sanitize_finite_diagnostic_metadata,
)

if TYPE_CHECKING:
    from src.services.run_diagnostics import RunDiagnosticContext

logger = logging.getLogger("src.services.run_diagnostics")


class PipelineStageObservation:
    """Measure one Pipeline stage without changing caller control flow."""

    def __init__(
        self,
        stage: str,
        *,
        input_summary: Optional[Mapping[str, Any]] = None,
        retryable: bool = False,
    ) -> None:
        """Start a stage timer with a sanitized low-sensitivity input summary."""
        self.stage = stage
        self.retryable = bool(retryable)
        self.started_at = datetime.now().isoformat()
        self._started_monotonic = time.monotonic()
        self._finished = False
        self.input_summary: Dict[str, Any] = {}
        try:
            self.input_summary = _sanitize_stage_summary(input_summary)
        except Exception as exc:  # broad-exception: fallback_recorded - Summary sanitization failures are logged and leave a safe empty summary.
            log_safe_exception(
                logger,
                "Pipeline stage input summary sanitization failed",
                exc,
                error_code="pipeline_stage_input_sanitization_failed",
                level=logging.WARNING,
                context={"stage": stage},
            )

    @property
    def finished(self) -> bool:
        """Return whether a terminal observation has already been recorded."""
        return self._finished

    def finish(
        self,
        *,
        status: str = "success",
        output_summary: Optional[Mapping[str, Any]] = None,
        degradation_reason: Optional[Any] = None,
        retryable: Optional[bool] = None,
        error: Optional[BaseException] = None,
    ) -> None:
        """Record one terminal stage outcome exactly once."""
        if self._finished:
            return
        self._finished = True
        duration_ms = max(
            0,
            int((time.monotonic() - self._started_monotonic) * 1000),
        )
        try:
            record_pipeline_stage(
                stage=self.stage,
                status=status,
                input_summary=self.input_summary,
                output_summary=output_summary,
                duration_ms=duration_ms,
                degradation_reason=degradation_reason,
                retryable=self.retryable if retryable is None else bool(retryable),
                error_type=type(error).__name__ if error is not None else None,
                error_message=error,
                started_at=self.started_at,
            )
        except Exception as exc:  # broad-exception: fallback_recorded - Observation failures are logged and cannot replace Pipeline outcomes.
            log_safe_exception(
                logger,
                "Pipeline stage observation failed",
                exc,
                error_code="pipeline_stage_observation_failed",
                level=logging.WARNING,
                context={"stage": self.stage},
            )
        # Opt-in perf baseline mirror (Issue #227). No-op when collection is off
        # or no collector is active — must never affect pipeline control flow.
        try:
            from src.perf.collector import record_span

            record_span(
                f"pipeline.{self.stage}",
                float(duration_ms),
                category="pipeline_stage",
                attrs={"status": str(status or "success")},
            )
        except Exception as exc:  # broad-exception: fallback_recorded - Perf mirror must not break diagnostics.
            log_safe_exception(
                logger,
                "Pipeline stage perf mirror failed",
                exc,
                error_code="pipeline_stage_perf_mirror_failed",
                level=logging.DEBUG,
                context={"stage": self.stage},
            )

    def __enter__(self) -> "PipelineStageObservation":
        """Return this observation for explicit status completion."""
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        """Record uncaught failures and never suppress the original exception."""
        _ = (exc_type, traceback)
        if not self._finished:
            self.finish(status="failed" if exc is not None else "success", error=exc)
        return False


def _public_prompt_artifact_versions(trace: Mapping[str, Any]) -> Dict[str, Any]:
    """Project low-sensitivity version identity safe for diagnostic snapshots.

    Central redaction treats some ``*version*`` keys as sensitive; version
    labels and content hashes are public run identity, so re-attach them
    through this allowlisted projector after redaction.
    """
    def _text(value: Any, *, maximum: int = 128) -> Optional[str]:
        text = str(value or "").strip()
        if not text:
            return None
        return text[:maximum]

    def _items(value: Any) -> List[Any]:
        if isinstance(value, (str, bytes, bytearray, Mapping)):
            return []
        try:
            return list(islice(iter(value or ()), 128))
        except TypeError:
            return []

    skills: List[Dict[str, Any]] = []
    for item in _items(trace.get("skills")):
        if not isinstance(item, Mapping):
            continue
        entry = {
            "kind": _text(item.get("kind"), maximum=16) or "skill",
            "artifact_id": _text(item.get("artifact_id")),
            "version": _text(item.get("version"), maximum=64),
            "content_hash": _text(item.get("content_hash"), maximum=80),
            "lifecycle": _text(item.get("lifecycle"), maximum=16) or "active",
        }
        source_version = item.get("source_version")
        if (
            isinstance(source_version, int)
            and not isinstance(source_version, bool)
            and 0 < source_version <= 2_147_483_647
        ):
            entry["source_version"] = source_version
        if entry["artifact_id"]:
            skills.append(entry)

    prompts: List[Dict[str, Any]] = []
    for item in _items(trace.get("prompts")):
        if not isinstance(item, Mapping):
            continue
        entry = {
            "kind": _text(item.get("kind"), maximum=16) or "prompt",
            "artifact_id": _text(item.get("artifact_id")),
            "version": _text(item.get("version"), maximum=64),
            "content_hash": _text(item.get("content_hash"), maximum=80),
            "lifecycle": _text(item.get("lifecycle"), maximum=16) or "active",
        }
        source_version = item.get("source_version")
        if (
            isinstance(source_version, int)
            and not isinstance(source_version, bool)
            and 0 < source_version <= 2_147_483_647
        ):
            entry["source_version"] = source_version
        if entry["artifact_id"]:
            prompts.append(entry)

    active_ids = [
        str(item).strip()[:128]
        for item in _items(trace.get("active_skill_ids"))
        if str(item).strip()
    ]
    skill_versions: Dict[str, str] = {}
    raw_versions = trace.get("skill_versions")
    if isinstance(raw_versions, Mapping):
        for key, value in islice(raw_versions.items(), 128):
            kid = _text(key)
            ver = _text(value, maximum=64)
            if kid and ver:
                skill_versions[kid] = ver

    return {
        "schema_version": _text(trace.get("schema_version"), maximum=16) or "1",
        "skills": skills,
        "prompts": prompts,
        "active_skill_ids": active_ids,
        "skill_versions": skill_versions,
        "prompt_version": _text(trace.get("prompt_version"), maximum=64),
    }


def attach_prompt_artifact_versions(trace: Optional[Dict[str, Any]]) -> bool:
    """Merge Skill/prompt version identity into the active diagnostic context."""
    from src.services.run_diagnostics import get_current_diagnostic_context

    if not isinstance(trace, dict):
        return False
    context = get_current_diagnostic_context()
    if context is None:
        return False
    try:
        incoming = _public_prompt_artifact_versions(trace)
        existing = _public_prompt_artifact_versions(
            context.prompt_artifact_versions or {}
        )

        def _merge_entries(key: str) -> List[Dict[str, Any]]:
            merged: Dict[str, Dict[str, Any]] = {}
            for item in [*existing.get(key, []), *incoming.get(key, [])]:
                artifact_id = str(item.get("artifact_id") or "").strip()
                if artifact_id:
                    merged[artifact_id] = dict(item)
            return list(merged.values())[:128]

        active_skill_ids = incoming.get("active_skill_ids") or existing.get(
            "active_skill_ids", []
        )
        context.prompt_artifact_versions = {
            "schema_version": incoming.get("schema_version") or existing.get(
                "schema_version", "1"
            ),
            "skills": _merge_entries("skills"),
            "prompts": _merge_entries("prompts"),
            "active_skill_ids": list(active_skill_ids)[:128],
            "skill_versions": {
                **existing.get("skill_versions", {}),
                **incoming.get("skill_versions", {}),
            },
            "prompt_version": incoming.get("prompt_version") or existing.get(
                "prompt_version"
            ),
        }
    except Exception as exc:  # broad-exception: optional_metadata - diagnostics must not raise.
        log_safe_exception(
            logger,
            "Attach prompt artifact versions failed",
            exc,
            error_code="prompt_artifact_versions_attach_failed",
            level=logging.DEBUG,
        )
        return False
    return True


def _sanitize_stage_summary(value: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """Return a bounded, sanitized mapping for stage inputs or outputs."""
    if not isinstance(value, Mapping):
        return {}
    sanitized = sanitize_diagnostic_metadata(dict(value))
    if _contains_unrenderable_marker(sanitized):
        raise ValueError("Pipeline stage summary contains an unrenderable value")
    return dict(sanitized) if isinstance(sanitized, Mapping) else {}


def _contains_unrenderable_marker(value: Any) -> bool:
    if type(value) is dict:
        return any(_contains_unrenderable_marker(item) for item in value.values())
    if type(value) in {list, tuple}:
        return any(_contains_unrenderable_marker(item) for item in value)
    return value == "[UNRENDERABLE]"


def observe_pipeline_stage(
    stage: str,
    *,
    input_summary: Optional[Mapping[str, Any]] = None,
    retryable: bool = False,
) -> PipelineStageObservation:
    """Start a fail-open observation for one fixed Pipeline stage."""
    return PipelineStageObservation(
        stage,
        input_summary=input_summary,
        retryable=retryable,
    )


def record_pipeline_stage(
    *,
    stage: str,
    status: str,
    input_summary: Optional[Mapping[str, Any]] = None,
    output_summary: Optional[Mapping[str, Any]] = None,
    duration_ms: int = 0,
    degradation_reason: Optional[Any] = None,
    retryable: bool = False,
    error_type: Optional[str] = None,
    error_message: Optional[Any] = None,
    started_at: Optional[str] = None,
) -> None:
    """Append a sanitized Pipeline stage result without affecting callers."""
    from src.services.run_diagnostics import get_current_diagnostic_context

    context = get_current_diagnostic_context()
    if context is None:
        return
    try:
        if stage not in PIPELINE_STAGE_NAMES:
            raise ValueError(f"unsupported Pipeline stage: {stage}")
        if status not in PIPELINE_STAGE_STATUSES:
            raise ValueError(f"unsupported Pipeline stage status: {status}")
        context.record_pipeline_stage(
            PipelineStageRun(
                trace_id=context.trace_id,
                stage=stage,
                status=status,
                input_summary=_sanitize_stage_summary(input_summary),
                output_summary=_sanitize_stage_summary(output_summary),
                duration_ms=max(0, int(duration_ms)),
                degraded=status == "degraded",
                degradation_reason=sanitize_diagnostic_text(degradation_reason),
                retryable=bool(retryable),
                error_type=sanitize_diagnostic_text(error_type, max_length=120),
                error_message_sanitized=sanitize_diagnostic_text(error_message),
                started_at=started_at or datetime.now().isoformat(),
                ended_at=datetime.now().isoformat(),
            )
        )
    except Exception as exc:  # broad-exception: fallback_recorded - Diagnostic recording failures are safely logged and cannot affect analysis.
        log_safe_exception(
            logger,
            "Pipeline stage diagnostic record failed",
            exc,
            error_code="pipeline_stage_diagnostic_record_failed",
            level=logging.WARNING,
            trace_id=context.trace_id,
        )


def record_missing_pipeline_stages_as_skipped(
    stages: Iterable[str],
    *,
    input_summary: Optional[Mapping[str, Any]] = None,
    reason: str,
) -> int:
    """Fill unobserved stage boundaries as skipped without duplicating records."""
    from src.services.run_diagnostics import get_current_diagnostic_context

    context = get_current_diagnostic_context()
    if context is None:
        return 0
    try:
        recorded_stages = {run.stage for run in context.pipeline_stage_runs}
        added_count = 0
        for stage in stages:
            if stage in recorded_stages:
                continue
            before_count = len(context.pipeline_stage_runs)
            record_pipeline_stage(
                stage=stage,
                status="skipped",
                input_summary=input_summary,
                output_summary={"reason": reason},
                retryable=False,
            )
            if len(context.pipeline_stage_runs) > before_count:
                recorded_stages.add(stage)
                added_count += 1
        return added_count
    except Exception as exc:  # broad-exception: fallback_recorded - Missing-stage diagnostics are logged and cannot affect Pipeline outcomes.
        log_safe_exception(
            logger,
            "Pipeline skipped-stage diagnostic fill failed",
            exc,
            error_code="pipeline_skipped_stage_fill_failed",
            level=logging.WARNING,
            trace_id=context.trace_id,
        )
        return 0


_DATA_TYPE_LABELS = {
    "realtime_quote": "实时行情",
    "daily_data": "日线K线",
    "daily_bars": "日线K线",
    "technical": "技术指标",
    "news": "新闻舆情",
    "news_search": "新闻舆情",
    "fundamental": "基本面",
    "fundamentals": "基本面",
    "belong_boards": "所属板块",
    "chip": "筹码结构",
}


def _safe_event_key(value: Any) -> str:
    return safe_diagnostic_key(value)


def _clean_metadata(value: Dict[str, Any]) -> Dict[str, Any]:
    return {
        str(key): item
        for key, item in value.items()
        if item not in (None, "", [], {})
    }


def _provider_pending_key(data_type: Any, provider: Any, operation: Any) -> str:
    return "|".join(
        (
            _safe_event_key(data_type) or "provider",
            _safe_event_key(provider) or "unknown",
            _safe_event_key(operation) or "operation",
        )
    )


def _llm_pending_key(call_type: Any, provider: Any, model: Any) -> str:
    _ = (provider, model)
    return _safe_event_key(call_type) or "analysis"


def _flow_status_for_success(success: bool, *, fallback: bool = False, skipped: bool = False) -> str:
    if skipped:
        return "skipped"
    if success:
        return "fallback" if fallback else "success"
    return "failed"


def _started_at_from_end_and_duration(end: Any, duration_ms: Optional[int]) -> Optional[str]:
    if duration_ms is None or duration_ms < 0:
        return None
    if isinstance(end, datetime):
        parsed = end
    elif isinstance(end, str) and "T" in end:
        normalized = end[:-1] + "+00:00" if end.endswith("Z") else end
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
    else:
        return None
    return (parsed - timedelta(milliseconds=duration_ms)).isoformat()


def _agent_flow_event(
    context: "RunDiagnosticContext",
    event: Mapping[str, Any],
) -> Dict[str, Any]:
    """Map one agent observability event into a run-flow event payload."""
    event_type = _safe_event_key(event.get("event_type")) or "agent_event"
    name = sanitize_diagnostic_text(event.get("name"), max_length=80) or "agent"
    phase = sanitize_diagnostic_text(event.get("phase"), max_length=64)
    status = sanitize_diagnostic_text(event.get("status"), max_length=32) or "unknown"
    duration_ms = event.get("duration_ms")
    try:
        duration_ms_int = int(duration_ms) if duration_ms is not None else None
    except (TypeError, ValueError, OverflowError):
        duration_ms_int = None
    if duration_ms_int is not None and duration_ms_int < 0:
        duration_ms_int = 0
    step = event.get("step")
    try:
        step_int = int(step) if step is not None else None
    except (TypeError, ValueError, OverflowError):
        step_int = None

    sequence = event.get("sequence")
    try:
        sequence_int = int(sequence) if sequence is not None else None
    except (TypeError, ValueError, OverflowError):
        sequence_int = None
    if sequence_int is not None and sequence_int < 1:
        sequence_int = None

    schema_version = event.get("schema_version")
    try:
        schema_version_int = int(schema_version) if schema_version is not None else None
    except (TypeError, ValueError, OverflowError):
        schema_version_int = None
    if schema_version_int is not None and schema_version_int < 1:
        schema_version_int = None

    is_tool = event_type in {"agent_tool_start", "agent_tool_end"}
    is_model = event_type in {"agent_model_start", "agent_model_end"}
    is_phase = event_type in {"agent_phase_start", "agent_phase_end"}
    is_start = event_type.endswith("_start")
    span_key = _safe_event_key(event.get("span_id")) or ""

    if is_tool:
        if is_start:
            context.agent_tool_index += 1
        tool_index = max(1, context.agent_tool_index)
        node_id = (
            f"agent_tool_{span_key}"
            if span_key
            else f"agent_tool_{_safe_event_key(name) or 'tool'}_{tool_index}"
        )
        label = f"工具 · {name}"
        lane = "analysis"
        kind = "analysis"
        title = f"工具开始: {name}" if is_start else f"工具完成: {name}"
    elif is_model:
        node_id = (
            f"agent_model_{span_key}"
            if span_key
            else f"agent_model_{_safe_event_key(name) or 'model'}"
        )
        label = f"模型 · {name}"
        lane = "analysis"
        kind = "model"
        title = f"模型开始: {name}" if is_start else f"模型完成: {name}"
    elif is_phase:
        node_id = (
            f"agent_phase_{span_key}"
            if span_key
            else f"agent_phase_{_safe_event_key(name) or 'phase'}"
        )
        label = f"阶段 · {name}"
        lane = "analysis"
        kind = "analysis"
        title = f"阶段开始: {name}" if is_start else f"阶段结束: {name}"
    else:
        node_id = (
            f"agent_{span_key}"
            if span_key
            else f"agent_{event_type}_{_safe_event_key(name) or 'event'}"
        )
        label = f"Agent · {name}"
        lane = "analysis"
        kind = "analysis"
        title = f"Agent: {name}"

    flow_status = "running" if is_start else _agent_status_to_flow(status)
    severity = "info" if is_start else (
        "success" if flow_status in {"success", "fallback"} else (
            "danger" if flow_status == "failed" else "warning"
        )
    )
    timestamp = sanitize_diagnostic_text(event.get("timestamp"), max_length=64) or datetime.now().isoformat()
    started_at = timestamp if is_start else _started_at_from_end_and_duration(timestamp, duration_ms_int)
    ended_at = None if is_start else timestamp
    message_bits = [name]
    if phase and phase != name:
        message_bits.append(f"phase={phase}")
    if step_int is not None:
        message_bits.append(f"step={step_int}")
    if duration_ms_int is not None and not is_start:
        message_bits.append(f"{duration_ms_int}ms")
    if status and not is_start:
        message_bits.append(status)
    message = sanitize_diagnostic_text(" · ".join(message_bits), max_length=220)

    attrs = event.get("attrs") if isinstance(event.get("attrs"), Mapping) else {}
    payload = event.get("payload") if isinstance(event.get("payload"), Mapping) else {}
    safe_attrs, attrs_finite = sanitize_finite_diagnostic_metadata(attrs)
    safe_payload, payload_finite = sanitize_finite_diagnostic_metadata(payload)
    detail_integrity = sanitize_diagnostic_text(event.get("detail_integrity"), max_length=40)
    if not attrs_finite or not payload_finite:
        detail_integrity = "invalid_non_finite"
    elif not detail_integrity:
        detail_integrity = "valid"
    metadata = _clean_metadata(
        {
            "schema_version": schema_version_int,
            "sequence": sequence_int,
            "trace_id": event.get("trace_id") or context.trace_id,
            "span_id": event.get("span_id"),
            "parent_span_id": event.get("parent_span_id"),
            "event_type": event.get("event_type") or event_type,
            "phase": phase,
            "step": step_int,
            "duration_ms": duration_ms_int,
            "status": status,
            "tool": name if is_tool else None,
            "model": name if is_model else None,
            "success": attrs.get("success") if isinstance(attrs, Mapping) else None,
            "attrs": safe_attrs if attrs else None,
            "payload": safe_payload if payload else None,
            "detail_integrity": detail_integrity,
            "capture": event.get("capture") if isinstance(event.get("capture"), Mapping) else None,
            "node": {
                "id": node_id,
                "lane": lane,
                "kind": kind,
                "label": label,
                "status": flow_status,
                "provider": name if (is_tool or is_model) else None,
                "started_at": started_at,
                "ended_at": ended_at,
                "duration_ms": duration_ms_int,
                "message": message,
            },
        }
    )
    return {
        "timestamp": timestamp,
        "severity": severity,
        "type": event_type if event_type.startswith("agent_") else f"agent_{event_type}",
        "node_id": node_id,
        "title": sanitize_diagnostic_text(title, max_length=100) or "Agent 事件",
        "message": message,
        "metadata": metadata,
    }


def _agent_status_to_flow(status: Optional[str]) -> str:
    normalized = (status or "").strip().lower()
    if normalized in {"success", "ok", "completed", "done"}:
        return "success"
    if normalized in {"failed", "error", "fail"}:
        return "failed"
    if normalized in {"running", "started", "in_progress"}:
        return "running"
    if normalized in {"cancelled", "cancel_requested", "timeout", "skipped", "degraded", "fallback"}:
        return normalized
    if normalized:
        return "degraded"
    return "unknown"


def _provider_started_flow_event(
    context: RunDiagnosticContext,
    *,
    data_type: str,
    provider: str,
    operation: str,
    index: int,
) -> Dict[str, Any]:
    data_type_key = _safe_event_key(data_type) or "provider"
    provider_key = _safe_event_key(provider) or "unknown"
    label = _DATA_TYPE_LABELS.get(data_type_key, data_type_key)
    node_id = f"provider_{data_type_key}_{provider_key}_{index}"
    timestamp = datetime.now().isoformat()
    message = f"{label} {provider} 调用中"
    return {
        "timestamp": timestamp,
        "severity": "info",
        "type": "provider_run_started",
        "node_id": node_id,
        "title": f"{label}开始",
        "message": sanitize_diagnostic_text(message, max_length=220),
        "metadata": _clean_metadata(
            {
                "trace_id": context.trace_id,
                "provider": provider,
                "data_type": data_type,
                "operation": operation,
                "node": {
                    "id": node_id,
                    "lane": "data_source",
                    "kind": "data_source",
                    "label": f"{label} · {provider}",
                    "status": "running",
                    "provider": provider,
                    "started_at": timestamp,
                    "attempts": 1,
                    "message": message,
                },
            }
        ),
    }


def _provider_flow_event(
    context: RunDiagnosticContext,
    run: ProviderRun,
    index: int,
) -> Dict[str, Any]:
    data_type = _safe_event_key(run.data_type) or "provider"
    provider_key = _safe_event_key(run.provider) or "unknown"
    label = _DATA_TYPE_LABELS.get(data_type, data_type)
    fallback = bool(run.fallback_from or run.fallback_to)
    status = _flow_status_for_success(run.success, fallback=fallback)
    node_id = f"provider_{data_type}_{provider_key}_{index}"
    started_at = _started_at_from_end_and_duration(run.created_at, run.latency_ms)
    message = (
        f"{label} {run.provider} 成功"
        if run.success
        else f"{label} {run.provider} 失败：{run.error_message_sanitized or run.error_type or '未知错误'}"
    )
    return {
        "timestamp": run.created_at,
        "severity": "success" if run.success else "warning",
        "type": "provider_run",
        "node_id": node_id,
        "title": f"{label}{'成功' if run.success else '失败'}",
        "message": sanitize_diagnostic_text(message, max_length=220),
        "metadata": _clean_metadata(
            {
                "trace_id": context.trace_id,
                "provider": run.provider,
                "data_type": run.data_type,
                "operation": run.operation,
                "duration_ms": run.latency_ms,
                "record_count": run.record_count,
                "fallback_from": run.fallback_from,
                "fallback_to": run.fallback_to,
                "error_type": run.error_type,
                "node": {
                    "id": node_id,
                    "lane": "data_source",
                    "kind": "data_source",
                    "label": f"{label} · {run.provider}",
                    "status": status,
                    "provider": run.provider,
                    "started_at": started_at,
                    "ended_at": run.created_at,
                    "duration_ms": run.latency_ms,
                    "record_count": run.record_count,
                    "message": message,
                },
            }
        ),
    }


def _llm_started_flow_event(
    context: RunDiagnosticContext,
    *,
    call_type: str,
    provider: Optional[str],
    model: Optional[str],
    index: int,
) -> Dict[str, Any]:
    call_type_key = _safe_event_key(call_type) or "analysis"
    display_model = model or provider or "unknown"
    node_id = f"llm_{call_type_key}_{index}"
    timestamp = datetime.now().isoformat()
    message = f"LLM {display_model} 调用中"
    return {
        "timestamp": timestamp,
        "severity": "info",
        "type": "llm_run_started",
        "node_id": node_id,
        "title": "LLM 开始",
        "message": sanitize_diagnostic_text(message, max_length=220),
        "metadata": _clean_metadata(
            {
                "trace_id": context.trace_id,
                "provider": provider,
                "model": model,
                "call_type": call_type,
                "node": {
                    "id": node_id,
                    "lane": "analysis",
                    "kind": "model",
                    "label": "LLM 生成",
                    "status": "running",
                    "provider": display_model,
                    "started_at": timestamp,
                    "attempts": 1,
                    "message": message,
                },
            }
        ),
    }


def _llm_flow_event(
    context: RunDiagnosticContext,
    run: LLMRun,
    index: int,
) -> Dict[str, Any]:
    call_type = _safe_event_key(run.call_type) or "analysis"
    model = run.model or run.provider or "unknown"
    status = _flow_status_for_success(run.success, fallback=bool(run.fallback_model or index > 1))
    node_id = f"llm_{call_type}_{index}"
    started_at = _started_at_from_end_and_duration(run.created_at, run.duration_ms)
    message = (
        f"LLM {model} 成功"
        if run.success
        else f"LLM {model} 失败：{run.error_message_sanitized or run.error_type or '未知错误'}"
    )
    return {
        "timestamp": run.created_at,
        "severity": "success" if run.success else "danger",
        "type": "llm_run",
        "node_id": node_id,
        "title": f"LLM {'成功' if run.success else '失败'}",
        "message": sanitize_diagnostic_text(message, max_length=220),
        "metadata": _clean_metadata(
            {
                "trace_id": context.trace_id,
                "provider": run.provider,
                "model": run.model,
                "call_type": run.call_type,
                "duration_ms": run.duration_ms,
                "fallback_model": run.fallback_model,
                "error_type": run.error_type,
                "node": {
                    "id": node_id,
                    "lane": "analysis",
                    "kind": "model",
                    "label": "LLM 生成",
                    "status": status,
                    "provider": model,
                    "started_at": started_at,
                    "ended_at": run.created_at,
                    "duration_ms": run.duration_ms,
                    "message": message,
                },
            }
        ),
    }


def _history_flow_event(
    context: RunDiagnosticContext,
    run: HistoryRun,
    index: int,
) -> Dict[str, Any]:
    node_id = "history_save" if index == 1 else f"history_save_{index}"
    status = "success" if run.report_saved else "failed"
    message = "报告历史已保存" if run.report_saved else f"报告历史保存失败：{run.error_message_sanitized or '未知错误'}"
    return {
        "timestamp": run.created_at,
        "severity": "success" if run.report_saved else "danger",
        "type": "history_run",
        "node_id": node_id,
        "title": "历史保存成功" if run.report_saved else "历史保存失败",
        "message": sanitize_diagnostic_text(message, max_length=220),
        "metadata": _clean_metadata(
            {
                "trace_id": context.trace_id,
                "metadata_saved": run.metadata_saved,
                "analysis_history_id": run.analysis_history_id,
                "node": {
                    "id": node_id,
                    "lane": "artifact",
                    "kind": "artifact",
                    "label": "保存报告",
                    "status": status,
                    "message": message,
                },
            }
        ),
    }


def _notification_flow_event(
    context: RunDiagnosticContext,
    run: NotificationRun,
    index: int,
) -> Dict[str, Any]:
    channel = run.channel or "unknown"
    channel_key = _safe_event_key(channel) or "unknown"
    skipped = run.status in {"skipped", "not_configured"}
    status = _flow_status_for_success(run.success, skipped=skipped)
    node_id = f"notification_{channel_key}_{index}"
    if status == "success":
        title = "通知发送成功"
        message = f"{channel} 通知发送成功"
    elif status == "skipped":
        title = "通知跳过"
        message = f"{channel} 通知跳过"
    else:
        title = "通知失败"
        message = f"{channel} 通知失败：{run.error_message_sanitized or run.status or '未知错误'}"
    return {
        "timestamp": run.created_at,
        "severity": "success" if status == "success" else ("warning" if status == "skipped" else "danger"),
        "type": "notification_run",
        "node_id": node_id,
        "title": title,
        "message": sanitize_diagnostic_text(message, max_length=220),
        "metadata": _clean_metadata(
            {
                "trace_id": context.trace_id,
                "channel": channel,
                "status": run.status,
                "attempts": run.attempts,
                "node": {
                    "id": node_id,
                    "lane": "artifact",
                    "kind": "notification",
                    "label": f"推送通知 · {channel}",
                    "status": status,
                    "provider": channel,
                    "attempts": run.attempts,
                    "message": message,
                },
            }
        ),
    }


def _finite_diagnostic_value(value: Any, *, depth: int = 0) -> Any:
    """Constrain validation evidence before storage and strict JSON encoding."""
    if depth > 4:
        return "<truncated>"
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, str):
        return sanitize_diagnostic_text(value, max_length=160)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Mapping):
        result: Dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= 20:
                result["truncated"] = True
                break
            safe_key = safe_diagnostic_key(key)
            if safe_key:
                result[safe_key] = _finite_diagnostic_value(
                    item,
                    depth=depth + 1,
                )
        return result
    if isinstance(value, (list, tuple)):
        return [
            _finite_diagnostic_value(item, depth=depth + 1)
            for item in list(value)[:24]
        ]
    return sanitize_diagnostic_text(value, max_length=160)


def record_data_quality_evidence(
    *,
    data_type: str,
    severity: str,
    symbol: Optional[str],
    provider: Optional[str],
    market: Optional[str],
    instrument_type: Optional[str],
    rejected: bool,
    issues: Iterable[Mapping[str, Any]],
    issue_count: Optional[int] = None,
    truncated: bool = False,
    schema_version: str = "data_quality_evidence.v1",
    provenance: Optional[Mapping[str, Any]] = None,
) -> None:
    """Log and persist one sanitized validation finding set."""
    from src.services.run_diagnostics import get_current_diagnostic_context

    normalized_severity = str(severity or "warn").strip().lower()
    if normalized_severity not in {"warn", "reject"}:
        normalized_severity = "warn"
    safe_issues: List[Dict[str, Any]] = []
    for index, issue in enumerate(issues):
        if index >= 24:
            truncated = True
            break
        if not isinstance(issue, Mapping):
            continue
        safe_issue = _finite_diagnostic_value(issue)
        if isinstance(safe_issue, dict):
            safe_issues.append(safe_issue)
    safe_symbol = sanitize_diagnostic_text(symbol, max_length=80)
    safe_provider = sanitize_diagnostic_text(provider, max_length=120)
    safe_market = sanitize_diagnostic_text(market, max_length=16) or "unknown"
    safe_instrument = (
        sanitize_diagnostic_text(instrument_type, max_length=24) or "equity"
    )
    codes = sorted(
        {
            str(issue.get("code"))
            for issue in safe_issues
            if issue.get("code")
        }
    )
    log_method = logger.warning if normalized_severity == "reject" else logger.info
    log_method(
        "data_quality event=validation severity=%s symbol=%s provider=%s "
        "market=%s instrument_type=%s rejected=%s codes=%s",
        normalized_severity,
        safe_symbol or "unknown",
        safe_provider or "unknown",
        safe_market,
        safe_instrument,
        bool(rejected),
        ",".join(codes) or "unknown",
    )

    context = get_current_diagnostic_context()
    if context is None:
        return
    try:
        context.record_data_quality_evidence(
            DataQualityEvidenceRecord(
                schema_version=sanitize_diagnostic_text(
                    schema_version,
                    max_length=48,
                )
                or "data_quality_evidence.v1",
                data_type=sanitize_diagnostic_text(data_type, max_length=64)
                or "unknown",
                severity=normalized_severity,
                symbol=safe_symbol,
                provider=safe_provider,
                market=safe_market,
                instrument_type=safe_instrument,
                rejected=bool(rejected),
                issues=safe_issues,
                issue_count=min(
                    1_000_000,
                    max(len(safe_issues), int(issue_count or 0)),
                ),
                truncated=bool(truncated),
                provenance=(
                    _finite_diagnostic_value(provenance)
                    if isinstance(provenance, Mapping)
                    else {}
                ),
            )
        )
    except Exception as exc:  # broad-exception: fallback_recorded - Data-quality diagnostic failures are safely logged and cannot affect analysis.
        log_safe_exception(
            logger,
            "Data-quality diagnostic record failed",
            exc,
            error_code="data_quality_diagnostic_record_failed",
            level=logging.WARNING,
            trace_id=context.trace_id,
        )
