# -*- coding: utf-8 -*-
"""Stable run-diagnostic schema, sanitization, and serialization helpers.

Collection and export consume these types. Callers should keep importing the
public names from ``src.services.run_diagnostics``.
"""

from __future__ import annotations

import math
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.utils.sanitize import (
    is_sensitive_key,
    redact_sensitive_data,
    redact_sensitive_text,
)

PIPELINE_STAGE_NAMES = (
    "resolve",
    "fetch",
    "intelligence",
    "context",
    "analyze",
    "persist",
    "render",
    "dispatch",
)
PIPELINE_STAGE_STATUSES = frozenset({"success", "degraded", "failed", "skipped"})

_EXISTING_REDACTION_SENTINEL = '"__STOCKPULSE_EXISTING_REDACTION__"'
_LOCAL_ABSOLUTE_PATH_RE = re.compile(
    r"(?<![\w:/.-])(?:/(?:home|Users|root|var|tmp|opt|etc)/[^\s,;]+|[A-Za-z]:\\[^\s,;]+)"
)


def build_trace_id() -> str:
    """Build a compact trace id suitable for logs, API responses, and SSE."""
    return uuid.uuid4().hex


def _localize_redaction_text(text: str) -> str:
    """Keep the established diagnostics marker format after central redaction."""

    localized = text.replace("[REDACTED]@", "<redacted>:<redacted>@")
    localized = localized.replace("[REDACTED_URL]", "<redacted-url>")
    localized = localized.replace("[REDACTED]", "<redacted>")
    return re.sub(
        r"(?i)\b(authorization|proxy[_-]?authorization)\s*[:=]\s*<redacted>",
        r"\1=<redacted>",
        localized,
    )


def _localize_redaction_markers(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _localize_redaction_markers(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_localize_redaction_markers(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_localize_redaction_markers(item) for item in value)
    if isinstance(value, str):
        return _localize_redaction_text(value)
    return value


def _replace_redaction_markers(value: Any, old: str, new: str) -> Any:
    if type(value) is dict:
        return {
            key: _replace_redaction_markers(item, old, new)
            for key, item in value.items()
        }
    if type(value) is list:
        return [
            _replace_redaction_markers(item, old, new)
            for item in value
        ]
    if type(value) is tuple:
        return tuple(
            _replace_redaction_markers(item, old, new)
            for item in value
        )
    if type(value) is str:
        return value.replace(old, new)
    return value


def _redact_diagnostic_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Apply central redaction while preserving already-public marker spelling."""

    protected = _replace_redaction_markers(
        payload,
        "[REDACTED]",
        _EXISTING_REDACTION_SENTINEL,
    )
    redacted = redact_sensitive_data(
        protected,
        preserve_http_credential_hosts=True,
    )
    localized = _localize_redaction_markers(redacted)
    restored = _replace_redaction_markers(
        localized,
        _EXISTING_REDACTION_SENTINEL,
        "[REDACTED]",
    )
    return (
        restored
        if isinstance(restored, dict)
        else {"redaction_error": "<redacted>"}
    )


def sanitize_diagnostic_text(value: Any, *, max_length: int = 300) -> Optional[str]:
    """Return a short diagnostic string with sensitive details redacted."""
    if value is None:
        return None

    protected = _replace_redaction_markers(
        value,
        "[REDACTED]",
        _EXISTING_REDACTION_SENTINEL,
    )
    redacted = redact_sensitive_text(
        protected,
        preserve_http_credential_hosts=True,
    )
    localized = _localize_redaction_text(redacted)
    restored = _replace_redaction_markers(
        localized,
        _EXISTING_REDACTION_SENTINEL,
        "[REDACTED]",
    )
    text = " ".join(str(restored).split())
    if not text:
        return None

    text = _LOCAL_ABSOLUTE_PATH_RE.sub("<redacted-path>", text)

    if len(text) > max_length:
        return f"{text[:max_length].rstrip()}..."
    return text


def safe_diagnostic_key(value: Any) -> str:
    """Normalize a diagnostic object key after applying text redaction."""
    text = sanitize_diagnostic_text(value, max_length=80) or ""
    return re.sub(r"[^A-Za-z0-9_]+", "_", text.strip().lower()).strip("_")[:80]


def sanitize_diagnostic_metadata(value: Any, *, depth: int = 0) -> Any:
    """Recursively redact diagnostic metadata before it reaches API/SSE payloads."""
    if depth > 3:
        return "<truncated>"
    if isinstance(value, Mapping):
        sanitized: Dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= 20:
                sanitized["truncated"] = True
                break
            safe_key = safe_diagnostic_key(key)
            if not safe_key:
                continue
            if is_sensitive_key(key):
                sanitized[safe_key] = "<redacted>"
                continue
            safe_value = sanitize_diagnostic_metadata(item, depth=depth + 1)
            if safe_value not in (None, "", [], {}):
                sanitized[safe_key] = safe_value
        return sanitized
    if isinstance(value, list):
        items = [sanitize_diagnostic_metadata(item, depth=depth + 1) for item in value[:8]]
        return [item for item in items if item not in (None, "", [], {})]
    if isinstance(value, tuple):
        return sanitize_diagnostic_metadata(list(value), depth=depth)
    if isinstance(value, (int, float, bool)):
        return value
    return sanitize_diagnostic_text(value, max_length=160)


def sanitize_finite_diagnostic_metadata(value: Any) -> tuple[Any, bool]:
    """Sanitize diagnostic metadata and omit non-finite numeric values.

    The boolean reports whether the input was fully finite so consumers can
    surface an integrity failure instead of silently treating an omitted value
    as complete replay evidence.
    """

    def omit_non_finite(item: Any) -> tuple[Any, bool]:
        if isinstance(item, float) and not math.isfinite(item):
            return None, False
        if isinstance(item, Mapping):
            result: Dict[str, Any] = {}
            valid = True
            for key, child in item.items():
                safe_child, child_valid = omit_non_finite(child)
                valid = valid and child_valid
                if safe_child not in (None, "", [], {}):
                    result[str(key)] = safe_child
            return result, valid
        if isinstance(item, list):
            result_list: List[Any] = []
            valid = True
            for child in item:
                safe_child, child_valid = omit_non_finite(child)
                valid = valid and child_valid
                if safe_child not in (None, "", [], {}):
                    result_list.append(safe_child)
            return result_list, valid
        return item, True

    return omit_non_finite(sanitize_diagnostic_metadata(value))


@dataclass
class ProviderRun:
    """One provider attempt in a trace."""

    trace_id: str
    data_type: str
    provider: str
    operation: str
    success: bool
    latency_ms: Optional[int] = None
    error_type: Optional[str] = None
    error_message_sanitized: Optional[str] = None
    fallback_from: Optional[str] = None
    fallback_to: Optional[str] = None
    cache_hit: Optional[bool] = None
    stale_seconds: Optional[int] = None
    record_count: Optional[int] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "trace_id": self.trace_id,
            "data_type": self.data_type,
            "provider": self.provider,
            "operation": self.operation,
            "success": self.success,
            "latency_ms": self.latency_ms,
            "error_type": self.error_type,
            "error_message_sanitized": self.error_message_sanitized,
            "fallback_from": self.fallback_from,
            "fallback_to": self.fallback_to,
            "cache_hit": self.cache_hit,
            "stale_seconds": self.stale_seconds,
            "record_count": self.record_count,
            "created_at": self.created_at,
        }
        return {key: value for key, value in payload.items() if value is not None}


@dataclass(frozen=True)
class DataQualityEvidenceRecord:
    """Finite, bounded validation evidence owned by run diagnostics."""

    schema_version: str
    data_type: str
    severity: str
    symbol: Optional[str]
    provider: Optional[str]
    market: str
    instrument_type: str
    rejected: bool
    issues: List[Dict[str, Any]]
    issue_count: int
    truncated: bool
    provenance: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "data_type": self.data_type,
            "severity": self.severity,
            "symbol": self.symbol,
            "provider": self.provider,
            "market": self.market,
            "instrument_type": self.instrument_type,
            "rejected": self.rejected,
            "issues": list(self.issues),
            "issue_count": self.issue_count,
            "truncated": self.truncated,
            "created_at": self.created_at,
        }
        if self.provenance:
            payload["provenance"] = dict(self.provenance)
        return payload


@dataclass
class LLMRun:
    """One LLM call result in a trace."""

    trace_id: str
    provider: Optional[str] = None
    model: Optional[str] = None
    call_type: str = "analysis"
    success: bool = True
    tokens: Optional[int] = None
    duration_ms: Optional[int] = None
    fallback_model: Optional[str] = None
    error_type: Optional[str] = None
    error_message_sanitized: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "trace_id": self.trace_id,
            "provider": self.provider,
            "model": self.model,
            "call_type": self.call_type,
            "success": self.success,
            "tokens": self.tokens,
            "duration_ms": self.duration_ms,
            "fallback_model": self.fallback_model,
            "error_type": self.error_type,
            "error_message_sanitized": self.error_message_sanitized,
            "created_at": self.created_at,
        }
        return {key: value for key, value in payload.items() if value is not None}


@dataclass
class NotificationRun:
    """Notification dispatch result in a trace."""

    trace_id: str
    channel: str
    status: str
    success: bool
    attempts: int = 1
    error_message_sanitized: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "trace_id": self.trace_id,
            "channel": self.channel,
            "status": self.status,
            "success": self.success,
            "attempts": self.attempts,
            "error_message_sanitized": self.error_message_sanitized,
            "created_at": self.created_at,
        }
        return {key: value for key, value in payload.items() if value is not None}


@dataclass
class HistoryRun:
    """History persistence result in a trace."""

    trace_id: str
    report_saved: bool
    metadata_saved: Optional[bool] = None
    analysis_history_id: Optional[int] = None
    error_message_sanitized: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "trace_id": self.trace_id,
            "report_saved": self.report_saved,
            "metadata_saved": self.metadata_saved,
            "analysis_history_id": self.analysis_history_id,
            "error_message_sanitized": self.error_message_sanitized,
            "created_at": self.created_at,
        }
        return {key: value for key, value in payload.items() if value is not None}


@dataclass
class PipelineStageRun:
    """One completed, skipped, or failed Pipeline stage observation."""

    trace_id: str
    stage: str
    status: str
    input_summary: Dict[str, Any]
    duration_ms: int
    degraded: bool
    retryable: bool
    started_at: str
    ended_at: str
    output_summary: Dict[str, Any] = field(default_factory=dict)
    degradation_reason: Optional[str] = None
    error_type: Optional[str] = None
    error_message_sanitized: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Return a sanitized snapshot payload for persistence and diagnostics."""
        payload = {
            "trace_id": self.trace_id,
            "stage": self.stage,
            "status": self.status,
            "input_summary": self.input_summary,
            "output_summary": self.output_summary,
            "duration_ms": self.duration_ms,
            "degraded": self.degraded,
            "degradation_reason": self.degradation_reason,
            "retryable": self.retryable,
            "error_type": self.error_type,
            "error_message_sanitized": self.error_message_sanitized,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
        }
        return {key: value for key, value in payload.items() if value is not None}


@dataclass
class RunDiagnosticComponent:
    """User-facing status for one diagnostic component."""

    key: str
    label: str
    status: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "key": self.key,
            "label": self.label,
            "status": self.status,
            "message": self.message,
            "details": self.details,
        }
        return {key: value for key, value in payload.items() if value not in (None, {}, [])}


@dataclass
class RunDiagnosticSummary:
    """User-facing diagnostic summary for one analysis run."""

    status: str
    status_label: str
    reason: str
    trace_id: Optional[str] = None
    task_id: Optional[str] = None
    query_id: Optional[str] = None
    stock_code: Optional[str] = None
    trigger_source: Optional[str] = None
    components: Dict[str, RunDiagnosticComponent] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "trace_id": self.trace_id,
            "task_id": self.task_id,
            "query_id": self.query_id,
            "stock_code": self.stock_code,
            "trigger_source": self.trigger_source,
            "status": self.status,
            "status_label": self.status_label,
            "reason": self.reason,
            "components": {
                key: component.to_dict()
                for key, component in self.components.items()
            },
        }
        from src.services.diagnostics.export import format_copyable_diagnostics

        payload["copy_text"] = format_copyable_diagnostics(payload)
        compact = {key: value for key, value in payload.items() if value is not None}
        return _redact_diagnostic_payload(compact)
