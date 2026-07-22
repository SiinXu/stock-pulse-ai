# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Stable public failure values for Agent API and persisted chat history."""

from __future__ import annotations

from typing import Any, Dict, Mapping

from src.utils.sanitize import (
    redact_sensitive_data,
    redact_sensitive_text,
    sanitize_diagnostic_text,
)


AGENT_CHAT_FAILED = "agent_chat_failed"
AGENT_RESEARCH_FAILED = "agent_research_failed"
AGENT_STREAM_FAILED = "agent_stream_failed"
AGENT_STREAM_TIMEOUT = "agent_stream_timeout"

AGENT_CHAT_FAILURE_MESSAGE = "Agent chat failed"
AGENT_RESEARCH_FAILURE_MESSAGE = "Agent research failed"
AGENT_STREAM_FAILURE_MESSAGE = "Agent stream failed"
AGENT_STREAM_TIMEOUT_MESSAGE = "Agent stream timed out"
AGENT_EXECUTION_FAILURE_MESSAGE = "Agent execution failed"
AGENT_LLM_FAILURE_MESSAGE = "All LLM models failed"

# Deprecated compatibility export. New writes use the versioned sentinel below.
AGENT_CHAT_FAILURE_HISTORY_MESSAGE = "[分析失败] Agent chat failed"
AGENT_CHAT_FAILURE_HISTORY_SENTINEL = "agent_error:v1:agent_chat_failed"
_LEGACY_AGENT_CHAT_FAILURE_PREFIX = "[分析失败]"


def sanitize_agent_diagnostic(value: Any) -> str:
    """Return a bounded diagnostic that is safe to emit in Agent logs."""
    return sanitize_diagnostic_text(value, max_length=300) or "unknown"


def is_agent_failure_history_content(role: str, content: Any) -> bool:
    """Return whether persisted content represents a generic Agent failure."""
    text = str(content or "")
    if role != "assistant":
        return False
    normalized = text.strip()
    return (
        normalized == AGENT_CHAT_FAILURE_HISTORY_SENTINEL
        or normalized.startswith(_LEGACY_AGENT_CHAT_FAILURE_PREFIX)
    )


def sanitize_agent_history_content(role: str, content: Any) -> str:
    """Replace persisted Agent failures with a safe compatibility fallback."""
    text = str(content or "")
    if is_agent_failure_history_content(role, text):
        return AGENT_CHAT_FAILURE_MESSAGE
    return text


def agent_history_public_fields(role: str, content: Any) -> Dict[str, Any]:
    """Build public history fields while retaining the legacy content field."""
    fields: Dict[str, Any] = {
        "content": sanitize_agent_history_content(role, content),
    }
    if is_agent_failure_history_content(role, content):
        fields.update({
            "error": AGENT_CHAT_FAILED,
            "params": {},
        })
    return fields


def sanitize_stream_event(event: Mapping[str, Any], *, trace_id: str) -> Dict[str, Any]:
    """Replace callback error events with the stable public SSE envelope."""
    redacted = redact_sensitive_data(event)
    if isinstance(redacted, dict) and redacted.get("type") != "error":
        return redacted
    return {
        "type": "error",
        "error": AGENT_STREAM_FAILED,
        "message": AGENT_STREAM_FAILURE_MESSAGE,
        "params": {},
        "details": None,
        "trace_id": redact_sensitive_text(trace_id),
    }
