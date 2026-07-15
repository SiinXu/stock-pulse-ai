# -*- coding: utf-8 -*-
"""Stable public failure values for Agent API and persisted chat history."""

from __future__ import annotations

from typing import Any, Dict, Mapping

from src.utils.sanitize import sanitize_diagnostic_text


AGENT_CHAT_FAILED = "agent_chat_failed"
AGENT_RESEARCH_FAILED = "agent_research_failed"
AGENT_STREAM_FAILED = "agent_stream_failed"
AGENT_STREAM_TIMEOUT = "agent_stream_timeout"

AGENT_CHAT_FAILURE_MESSAGE = "Agent chat failed"
AGENT_RESEARCH_FAILURE_MESSAGE = "Agent research failed"
AGENT_STREAM_FAILURE_MESSAGE = "Agent stream failed"
AGENT_STREAM_TIMEOUT_MESSAGE = "Agent stream timed out"

AGENT_CHAT_FAILURE_HISTORY_MESSAGE = "[分析失败] Agent chat failed"
_LEGACY_AGENT_CHAT_FAILURE_PREFIX = "[分析失败]"


def sanitize_agent_diagnostic(value: Any) -> str:
    """Return a bounded diagnostic that is safe to emit in Agent logs."""
    return sanitize_diagnostic_text(value, max_length=300) or "unknown"


def sanitize_agent_history_content(role: str, content: Any) -> str:
    """Replace legacy persisted provider failures at every history read boundary."""
    text = str(content or "")
    if role == "assistant" and text.lstrip().startswith(_LEGACY_AGENT_CHAT_FAILURE_PREFIX):
        return AGENT_CHAT_FAILURE_HISTORY_MESSAGE
    return text


def sanitize_stream_event(event: Mapping[str, Any], *, trace_id: str) -> Dict[str, Any]:
    """Replace callback error events with the stable public SSE envelope."""
    if event.get("type") != "error":
        return dict(event)
    return {
        "type": "error",
        "error": AGENT_STREAM_FAILED,
        "message": AGENT_STREAM_FAILURE_MESSAGE,
        "params": {},
        "details": None,
        "trace_id": trace_id,
    }
