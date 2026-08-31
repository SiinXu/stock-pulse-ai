# -*- coding: utf-8 -*-
"""Generation-diagnostic redaction for market-review error surfaces.

Issue #1085 step 8. These two helpers decide what of a generation failure is
safe to log or surface: the redaction value set, and the sanitized diagnostic
text built from it.

This module must not import ``MarketAnalyzer``; both functions receive
``owner`` and read ``owner.config`` through it, so class-level and
instance-level overrides stay effective.
"""

from __future__ import annotations

from inspect import getattr_static
from typing import Any, Optional

from src.llm.generation_backend import GenerationError, GenerationErrorCode
from src.utils.sanitize import (
    exception_chain_redaction_values,
    has_matching_exception_snapshot,
    sanitize_diagnostic_text,
)

__all__ = (
    "generation_log_redaction_values",
    "sanitize_generation_diagnostic",
)


def generation_log_redaction_values(owner: Any, error: Any = None) -> set[str]:
    """Return exact generation secrets without depending on analyzer internals."""
    analyzer = getattr(owner, "analyzer", None)
    if analyzer is None:
        return exception_chain_redaction_values(error)
    static_method = getattr_static(
        analyzer,
        "get_generation_log_redaction_values",
        None,
    )
    if static_method is None:
        return exception_chain_redaction_values(error)
    method = getattr(analyzer, "get_generation_log_redaction_values", None)
    if not callable(method):
        return exception_chain_redaction_values(error)
    try:
        model = str(getattr(owner.config, "litellm_model", "") or "")
        values = method(model, fallback_error=error)
        static_values = values if isinstance(values, set) else set(values or ())
    except Exception:  # broad-exception: optional_metadata - optional redaction lookup falls back safely
        return exception_chain_redaction_values(error)
    if has_matching_exception_snapshot(error, static_values):
        return static_values
    exception_values = exception_chain_redaction_values(error)
    exception_values.update(static_values)
    return exception_values


def sanitize_generation_diagnostic(
    owner: Any,
    error: Any,
    *,
    redaction_values: Optional[set[str]] = None,
) -> str:
    """Sanitize an analyzer failure before persistence or user diagnostics."""
    if redaction_values is None:
        redaction_values = owner._generation_log_redaction_values(error)
    if isinstance(error, GenerationError):
        error_code = (
            error.error_code.value
            if isinstance(error.error_code, GenerationErrorCode)
            else GenerationErrorCode.UNKNOWN_BACKEND_ERROR.value
        )
        return f"GenerationError: {error_code}"
    if has_matching_exception_snapshot(error, redaction_values):
        return sanitize_diagnostic_text(
            error,
            max_length=500,
            redaction_values=redaction_values,
        )
    analyzer = getattr(owner, "analyzer", None)
    static_method = (
        getattr_static(analyzer, "sanitize_generation_diagnostic", None)
        if analyzer is not None
        else None
    )
    method = (
        getattr(analyzer, "sanitize_generation_diagnostic", None)
        if static_method is not None
        else None
    )
    if callable(method):
        try:
            model = str(getattr(owner.config, "litellm_model", "") or "")
            return sanitize_diagnostic_text(
                method(error, model=model),
                max_length=500,
                redaction_values=redaction_values,
            )
        except Exception:  # broad-exception: optional_metadata - optional sanitizer falls back safely
            pass
    return sanitize_diagnostic_text(
        error,
        max_length=500,
        redaction_values=redaction_values,
    )
