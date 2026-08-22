# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Fail-closed Soul-marker and oversize reject for memory writes (#1124 DAG-2).

User-writable memory text is rejected, not stripped, truncated, or stored, when
it carries Soul-boundary tokens, exceeds the field cap, or hides markers with
C0 control characters. This is the write-path contract. Prompt isolation still
truncates on inject and is not a substitute for reject-on-write.

This module does not stamp provenance (DAG-3) or add product feedback APIs
(#1105). Soul charter bytes, version, and hash are unchanged.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

# Shared token used by Soul composition (`AGENT_SOUL_MARKER` /
# `AGENT_SOUL_END_MARKER`) and research-persona custom_text. Case-insensitive
# substring match covers the HTML comments, mixed-case spoofs, and a bare token.
SOUL_BOUNDARY_TOKEN = "stockpulse-agent-soul"

FEEDBACK_NOTE_MAX_LENGTH = 1000
FEEDBACK_REASON_CODE_MAX_LENGTH = 64

_ALLOWED_CONTROLS = frozenset({"\n", "\r", "\t"})


class MemoryWriteRejectedError(ValueError):
    """Raised when a memory write contains Soul markers, oversize, or illegal controls."""


def _contains_illegal_control(text: str) -> bool:
    return any(ord(char) < 32 and char not in _ALLOWED_CONTROLS for char in text)


def _contains_soul_boundary(text: str) -> bool:
    return SOUL_BOUNDARY_TOKEN in text.lower()


def reject_memory_write_text(
    value: Any,
    *,
    field_name: str,
    max_length: int,
) -> Optional[str]:
    """Return ``value`` unchanged, or raise if the write must fail closed.

    ``None`` is allowed so optional fields stay optional. Non-string values,
    C0 controls other than newline/tab, oversize, and Soul-boundary tokens are
    rejected. Callers must not strip a marker and persist the remainder.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise MemoryWriteRejectedError(f"{field_name} must be a string")
    if _contains_illegal_control(value):
        raise MemoryWriteRejectedError(f"{field_name} contains control characters")
    if len(value) > max_length:
        raise MemoryWriteRejectedError(
            f"{field_name} must be at most {max_length} characters"
        )
    if _contains_soul_boundary(value):
        raise MemoryWriteRejectedError(
            f"{field_name} cannot contain Agent Soul boundary markers"
        )
    return value


def reject_feedback_write_fields(fields: Mapping[str, Any]) -> Mapping[str, Any]:
    """Reject ``note`` / ``reason_code`` on the repository feedback write path."""
    if not isinstance(fields, Mapping):
        raise TypeError("fields must be a mapping")
    if "note" in fields:
        reject_memory_write_text(
            fields["note"],
            field_name="note",
            max_length=FEEDBACK_NOTE_MAX_LENGTH,
        )
    if "reason_code" in fields:
        reject_memory_write_text(
            fields["reason_code"],
            field_name="reason_code",
            max_length=FEEDBACK_REASON_CODE_MAX_LENGTH,
        )
    return fields


__all__ = [
    "FEEDBACK_NOTE_MAX_LENGTH",
    "FEEDBACK_REASON_CODE_MAX_LENGTH",
    "MemoryWriteRejectedError",
    "SOUL_BOUNDARY_TOKEN",
    "reject_feedback_write_fields",
    "reject_memory_write_text",
]
