# -*- coding: utf-8 -*-
"""Log-safe exception helpers built on shared sanitizers."""

from __future__ import annotations

import logging
import re
from typing import Any, Callable, Iterable, Mapping, Optional

from .redaction import (
    _REDACTED,
    _SAFE_EXCEPTION_SUMMARY_MAX_LENGTH,
    _SAFE_RENDER_FAILURE,
    _matching_exception_snapshot,
    _normalize_redaction_values,
    _safe_string,
)
from .text import (
    _is_sensitive_mapping_key_text,
    exception_chain_redaction_values,
    safe_exception_type_name,
    sanitize_diagnostic_text,
    sanitize_exception_chain,
)

def _safe_log_context_fields(
    context: Optional[Mapping[str, Any]],
    *,
    redaction_values: Optional[Iterable[Any]] = None,
) -> list[str]:
    """Render structured log context as sanitized key-value fields."""
    fields: list[str] = []
    if context is None:
        return fields
    try:
        for key, value in context.items():
            rendered_key = _safe_string(key)
            if rendered_key == _SAFE_RENDER_FAILURE:
                return [f"context={_SAFE_RENDER_FAILURE}"]
            safe_key = re.sub(r"[^A-Za-z0-9_.-]", "_", rendered_key)[:80]
            if not safe_key:
                continue
            safe_value = (
                _REDACTED
                if _is_sensitive_mapping_key_text(rendered_key)
                else sanitize_diagnostic_text(
                    value,
                    max_length=180,
                    redaction_values=redaction_values,
                )
            )
            if safe_key and safe_value:
                fields.append(f"{safe_key}={safe_value}")
    except BaseException:
        return [f"context={_SAFE_RENDER_FAILURE}"]
    return fields


def _collapse_redacted_exception_diagnostics(summary: str) -> str:
    """Keep chain types while removing labels from already-redacted diagnostics."""

    collapsed_parts = []
    for part in summary.split(" <- "):
        exception_type, separator, diagnostic = part.partition(": ")
        if not separator:
            collapsed_parts.append(part)
            continue
        markers = []
        if "[REDACTED]" in diagnostic:
            markers.append("[REDACTED]")
        if "[REDACTED_URL]" in diagnostic:
            markers.append("[REDACTED_URL]")
        collapsed_parts.append(
            f"{exception_type}: {' '.join(markers) if markers else diagnostic}"
        )
    return " <- ".join(collapsed_parts)


def _collapse_log_exception_summaries(message: str) -> str:
    prefix, summary_separator, summaries = message.rpartition(" summary=")
    if not summary_separator:
        return message
    summary, diagnostic_separator, diagnostic = summaries.partition(" diagnostic=")
    if not diagnostic_separator:
        return message
    return (
        f"{prefix}{summary_separator}"
        f"{_collapse_redacted_exception_diagnostics(summary)}"
        f"{diagnostic_separator}"
        f"{_collapse_redacted_exception_diagnostics(diagnostic)}"
    )


def log_safe_exception(
    target_logger: logging.Logger,
    event: str,
    exc: BaseException,
    *,
    error_code: str,
    level: int = logging.ERROR,
    trace_id: Optional[str] = None,
    method: Optional[str] = None,
    path: Optional[str] = None,
    context: Optional[Mapping[str, Any]] = None,
    redaction_values: Optional[Iterable[Any]] = None,
    exception_redaction_values: Optional[Iterable[Any]] = None,
) -> None:
    """Log a sanitized exception summary without attaching raw exception info."""
    structural_values = _normalize_redaction_values(redaction_values)
    exception_values = _normalize_redaction_values(exception_redaction_values)
    if structural_values is None or exception_values is None:
        message = _SAFE_RENDER_FAILURE
    else:
        try:
            snapshot = (
                _matching_exception_snapshot(exception_values, exc)
                or _matching_exception_snapshot(structural_values, exc)
            )
            summary_values = _normalize_redaction_values(
                (*structural_values, *exception_values)
            )
            if summary_values is None:
                raise ValueError("unsafe exception redaction values")
            fields = [
                sanitize_diagnostic_text(
                    event,
                    max_length=160,
                    redaction_values=structural_values,
                ) or "Unhandled exception",
                "error_code="
                f"{sanitize_diagnostic_text(error_code, max_length=120, redaction_values=structural_values) or 'unknown_error'}",
            ]
            for field_name, value, field_limit in (
                ("trace_id", trace_id, 128),
                ("method", method, 16),
                ("path", path, 240),
            ):
                if value is None:
                    continue
                safe_value = sanitize_diagnostic_text(
                    value,
                    max_length=field_limit,
                    redaction_values=structural_values,
                )
                if safe_value:
                    fields.append(f"{field_name}={safe_value}")
            fields.extend(
                _safe_log_context_fields(context, redaction_values=structural_values)
            )
            if snapshot is not None:
                summary = sanitize_diagnostic_text(
                    snapshot.summary,
                    max_length=_SAFE_EXCEPTION_SUMMARY_MAX_LENGTH,
                    redaction_values=summary_values,
                )
            elif (
                structural_values.exception_snapshots
                or exception_values.exception_snapshots
                or exception_redaction_values is not None
            ):
                summary = sanitize_exception_chain(
                    exc,
                    redaction_values=summary_values,
                    redact_diagnostics=True,
                )
            else:
                summary = sanitize_exception_chain(
                    exc,
                    redaction_values=summary_values,
                )
            fields.extend(
                (
                    f"exception_type={safe_exception_type_name(exc)}",
                    f"summary={summary}",
                    f"diagnostic={summary}",
                )
            )
            message = " ".join(fields)
        except BaseException:
            message = _SAFE_RENDER_FAILURE
    message = _collapse_log_exception_summaries(message)
    target_logger.log(level, message)


def safe_before_sleep_log(
    target_logger: logging.Logger,
    level: int = logging.WARNING,
    *,
    event: str,
    error_code: str,
    context: Optional[Mapping[str, Any]] = None,
    redaction_values: Optional[Iterable[Any]] = None,
) -> Callable[[Any], None]:
    """Build a Tenacity-compatible retry callback without logging raw outcomes."""
    context_snapshot_failed = False
    try:
        static_context = dict(context.items()) if context is not None else {}
    except BaseException:
        static_context = {}
        context_snapshot_failed = True
    exact_values = _normalize_redaction_values(redaction_values)

    def _log_retry(retry_state: Any) -> None:
        """Log one retry state without exposing its raw outcome."""
        if exact_values is None:
            target_logger.log(level, _SAFE_RENDER_FAILURE)
            return
        retry_context = dict(static_context)
        if context_snapshot_failed:
            retry_context["context"] = _SAFE_RENDER_FAILURE
        retry_exception: Optional[BaseException] = None
        try:
            attempt_number = getattr(retry_state, "attempt_number", None)
            if isinstance(attempt_number, int) and not isinstance(attempt_number, bool):
                retry_context["attempt"] = attempt_number

            next_action = getattr(retry_state, "next_action", None)
            wait_seconds = getattr(next_action, "sleep", None)
            if isinstance(wait_seconds, (int, float)) and not isinstance(wait_seconds, bool):
                retry_context["retry_in_seconds"] = wait_seconds

            outcome = getattr(retry_state, "outcome", None)
            exception_getter = getattr(outcome, "exception", None)
            if callable(exception_getter):
                candidate = exception_getter()
                if isinstance(candidate, BaseException):
                    retry_exception = candidate
        except BaseException as state_error:
            retry_exception = state_error

        if retry_exception is not None:
            try:
                retry_redaction_values = exception_chain_redaction_values(retry_exception)
            except BaseException:
                retry_redaction_values = None
            if retry_redaction_values is None:
                target_logger.log(level, _SAFE_RENDER_FAILURE)
                return
            log_safe_exception(
                target_logger,
                event,
                retry_exception,
                error_code=error_code,
                level=level,
                context=retry_context,
                redaction_values=exact_values,
                exception_redaction_values=retry_redaction_values,
            )
            return

        safe_error_code = sanitize_diagnostic_text(
            error_code,
            max_length=120,
            redaction_values=exact_values,
        )
        fields = [
            sanitize_diagnostic_text(
                event,
                max_length=160,
                redaction_values=exact_values,
            ) or "Retry scheduled",
            f"error_code={safe_error_code or 'retry_scheduled'}",
            *_safe_log_context_fields(
                retry_context,
                redaction_values=exact_values,
            ),
            "exception_type=none",
            "summary=retry scheduled without an exception outcome",
        ]
        target_logger.log(level, " ".join(fields))

    return _log_retry
