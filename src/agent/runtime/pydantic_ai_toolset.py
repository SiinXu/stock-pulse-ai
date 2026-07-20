# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""BoundToolSession -> PydanticAI toolset bridge (AR-PY-04, 方案 B).

The single bridge point between StockPulse's execution-bound tool surface
(AR-PY-02 ``BoundToolSession``) and PydanticAI. Every tool the PydanticAI
agent can call is built from the session's *public* descriptors and routes
back through ``BoundToolSession.execute`` — so the fail-closed gates
(allowlist, per-call limits, session budget, deadline, cancellation and the
late-result fence) stay the one and only dispatch authority. PydanticAI
never sees a tool handler and can never bypass a gate.

``Tool.from_schema`` is the stable public entrypoint for schema-driven
(dynamic) tools: it takes an explicit args JSON schema and calls the
function by keyword, which matches StockPulse's dynamic ``ToolRegistry``
exactly and avoids depending on PydanticAI's internal tool-validator types.
"""

from __future__ import annotations

from typing import Any

_EMPTY_SCHEMA = {"type": "object", "properties": {}}


def build_bound_session_toolset(session: Any, *, event_emitter: Any = None) -> Any:
    """Build a PydanticAI ``FunctionToolset`` backed by a ``BoundToolSession``.

    Only the session's allowed tools are exposed, and each call is dispatched
    through the session's fail-closed gates. The structured result dict
    (success or the shared error contract) is returned to the model unchanged.

    When ``event_emitter`` (an AR-PY-03 ``RuntimeEventEmitter``) is provided,
    each call emits ``tool_start`` / ``tool_done`` through that single event
    stream, so PydanticAI tool activity shares the same versioned event path
    and late-write fence as the native runtime.
    """
    from src.agent.runtime.pydantic_ai_adapter import _require_pydantic_ai

    _require_pydantic_ai()
    from pydantic_ai.tools import Tool
    from pydantic_ai.toolsets import FunctionToolset

    def _make_caller(tool_name: str):
        def _call(**kwargs: Any) -> Any:
            if event_emitter is not None:
                event_emitter.emit("tool_start", tool=tool_name)
            result = session.execute(tool_name, kwargs)
            if event_emitter is not None:
                succeeded = not (isinstance(result, dict) and result.get("error"))
                event_emitter.emit("tool_done", tool=tool_name, success=succeeded)
            return result

        return _call

    tools = []
    for descriptor in session.describe_tools():
        name = descriptor.get("name")
        if not name:
            continue
        tools.append(
            Tool.from_schema(
                function=_make_caller(name),
                name=name,
                description=descriptor.get("description") or "",
                json_schema=descriptor.get("parameters") or _EMPTY_SCHEMA,
            )
        )
    return FunctionToolset(tools=tools)
