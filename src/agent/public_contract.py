# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Stable public failure values for Agent API and persisted chat history."""

from __future__ import annotations

import json
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
AGENT_RESEARCH_FAILURE_HISTORY_SENTINEL = "agent_error:v1:agent_research_failed"
_LEGACY_AGENT_CHAT_FAILURE_PREFIX = "[分析失败]"
_AGENT_HISTORY_THINKING_STEPS_KEY = "thinking_steps"
_MAX_HISTORY_TOOL_STEPS = 32
_MAX_TOOL_ARGUMENTS_CHARS = 2000
_MAX_TOOL_RESULT_PREVIEW_CHARS = 1200


def _bounded_public_tool_arguments(value: Any) -> Dict[str, Any]:
    redacted = redact_sensitive_data(value)
    if not isinstance(redacted, dict):
        return {}
    rendered = json.dumps(redacted, ensure_ascii=False, default=str)
    if len(rendered) <= _MAX_TOOL_ARGUMENTS_CHARS:
        return redacted
    return {
        "preview": rendered[:_MAX_TOOL_ARGUMENTS_CHARS],
        "truncated": True,
    }


def _bounded_public_tool_result(value: Any) -> str:
    redacted = redact_sensitive_data(value)
    rendered = (
        redacted
        if isinstance(redacted, str)
        else json.dumps(redacted, ensure_ascii=False, default=str)
    )
    return rendered[:_MAX_TOOL_RESULT_PREVIEW_CHARS]


def _normalize_public_tool_step(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    source_meta = value.get("meta") if isinstance(value.get("meta"), Mapping) else value
    tool = sanitize_diagnostic_text(value.get("tool"), max_length=100)
    if not tool:
        return {}
    step: Dict[str, Any] = {
        "type": "tool_done",
        "tool": tool,
        "success": bool(value.get("success")),
    }
    if isinstance(value.get("step"), int):
        step["step"] = value["step"]
    if isinstance(value.get("duration"), (int, float)):
        step["duration"] = max(0, round(float(value["duration"]), 3))

    meta: Dict[str, Any] = {}
    arguments = _bounded_public_tool_arguments(source_meta.get("arguments"))
    if arguments:
        meta["arguments"] = arguments
    if isinstance(source_meta.get("cached"), bool):
        meta["cached"] = source_meta["cached"]
    if isinstance(source_meta.get("result_length"), int):
        meta["result_length"] = max(0, source_meta["result_length"])
    if source_meta.get("result_preview") not in (None, ""):
        meta["result_preview"] = _bounded_public_tool_result(
            source_meta["result_preview"]
        )
    if meta:
        step["meta"] = meta
    return step


def build_agent_tool_history_context(tool_calls: Any) -> Dict[str, Any]:
    """Build bounded, redacted tool details for visible conversation history."""
    if not isinstance(tool_calls, (list, tuple)):
        return {}
    steps = [
        normalized
        for item in list(tool_calls)[:_MAX_HISTORY_TOOL_STEPS]
        if (normalized := _normalize_public_tool_step(item))
    ]
    return {_AGENT_HISTORY_THINKING_STEPS_KEY: steps} if steps else {}


def agent_history_public_params(
    role: str,
    content: Any,
    context: Any,
) -> Dict[str, Any]:
    """Expose only bounded tool metadata from stored message context."""
    if _agent_failure_history_fields(role, content):
        return {}
    if role != "assistant" or not isinstance(context, Mapping):
        return {}
    return build_agent_tool_history_context(
        context.get(_AGENT_HISTORY_THINKING_STEPS_KEY)
    )


def _agent_failure_history_fields(role: str, content: Any) -> Dict[str, str]:
    if role != "assistant":
        return {}
    normalized = str(content or "").strip()
    if normalized == AGENT_RESEARCH_FAILURE_HISTORY_SENTINEL:
        return {
            "error": AGENT_RESEARCH_FAILED,
            "message": AGENT_RESEARCH_FAILURE_MESSAGE,
        }
    if (
        normalized == AGENT_CHAT_FAILURE_HISTORY_SENTINEL
        or normalized.startswith(_LEGACY_AGENT_CHAT_FAILURE_PREFIX)
    ):
        return {
            "error": AGENT_CHAT_FAILED,
            "message": AGENT_CHAT_FAILURE_MESSAGE,
        }
    return {}


def sanitize_agent_diagnostic(value: Any) -> str:
    """Return a bounded diagnostic that is safe to emit in Agent logs."""
    return sanitize_diagnostic_text(value, max_length=300) or "unknown"


def is_agent_failure_history_content(role: str, content: Any) -> bool:
    """Return whether persisted content represents a generic Agent failure."""
    return bool(_agent_failure_history_fields(role, content))


def sanitize_agent_history_content(role: str, content: Any) -> str:
    """Replace persisted Agent failures with a safe compatibility fallback."""
    text = str(content or "")
    failure = _agent_failure_history_fields(role, text)
    if failure:
        return failure["message"]
    return text


def agent_history_public_fields(role: str, content: Any) -> Dict[str, Any]:
    """Build public history fields while retaining the legacy content field."""
    fields: Dict[str, Any] = {
        "content": sanitize_agent_history_content(role, content),
    }
    failure = _agent_failure_history_fields(role, content)
    if failure:
        fields.update({
            "error": failure["error"],
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
