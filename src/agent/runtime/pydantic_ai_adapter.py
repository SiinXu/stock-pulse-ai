# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Experimental PydanticAI runtime adapter (AR-PY-04, 方案 B).

An **isolated, opt-in** ``AgentRuntime`` backed by PydanticAI. It is never
wired into the default product path: Native remains the permanent default
(see ``docs/architecture/ADR-001-agent-runtime.md``). PydanticAI is an
*optional* dependency; every import is lazy so a StockPulse install
without ``pydantic-ai-slim`` starts and runs Native unaffected, and asking
for this runtime without the dependency raises one explicit error rather
than degrading silently.

方案 B was selected over 方案 A by the AR-PY-04 model-integration Spike
(``.claude/reviews/ar-py-04-model-integration-spike.md``): PydanticAI 2.12
ships no LiteLLM *Model* — only a proxy-oriented ``LiteLLMProvider`` — so a
custom ``Model`` that reuses StockPulse's in-process ``LLMToolAdapter`` is
the faithful, small-surface bridge. The ``Model`` abstract surface is just
``model_name`` / ``system`` / ``request``.

Scope of this first slice (审批点 4: one minimal representative path):
- Only ``ExecutionMode.RUN`` (Single Agent run). Other modes raise a clear
  not-implemented error rather than silently falling back.
- The PydanticAI ``Model`` is an internal injection point (test doubles or
  an internal factory arg); this module ships a minimal text-only
  StockPulse-backed model builder. Tool/Toolset bridging via
  ``BoundToolSession``, Multi/Research migration, MCP, Graph and durable
  execution are explicitly out of scope here.
"""

from __future__ import annotations

import asyncio
from typing import Any, List, Optional

from src.agent.runtime.contract import (
    AgentExecution,
    ExecutionContext,
    ExecutionHandle,
    ExecutionMode,
    ExecutionState,
    ProgressCallback,
)
from src.agent.runtime.lifecycle import classify_terminal_state, get_default_usage_recorder
from src.agent.public_contract import sanitize_agent_diagnostic

_PYDANTIC_AI_DIST = "pydantic-ai-slim"


class PydanticAIRuntimeUnavailableError(RuntimeError):
    """Raised when the PydanticAI runtime is used without its optional dep."""


def is_pydantic_ai_available() -> bool:
    """Return whether the optional PydanticAI dependency can be imported."""
    import importlib.util

    return importlib.util.find_spec("pydantic_ai") is not None


def _require_pydantic_ai() -> Any:
    try:
        import pydantic_ai  # noqa: F401  (imported for availability + re-export)

        return pydantic_ai
    except ImportError as exc:  # pragma: no cover - exercised via monkeypatch
        raise PydanticAIRuntimeUnavailableError(
            "PydanticAI runtime requested but the optional dependency is not "
            f"installed. Install '{_PYDANTIC_AI_DIST}' (see "
            "requirements-pydanticai.txt) or use the Native runtime."
        ) from exc


def _to_stockpulse_messages(messages: List[Any]) -> List[dict]:
    """Convert PydanticAI ``ModelMessage`` history to StockPulse messages.

    Only the text-carrying parts needed by the minimal single-run path are
    mapped; tool parts are intentionally skipped in this first slice.
    """
    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        SystemPromptPart,
        TextPart,
        UserPromptPart,
    )

    converted: List[dict] = []
    for message in messages:
        if isinstance(message, ModelRequest):
            for part in message.parts:
                if isinstance(part, SystemPromptPart):
                    converted.append({"role": "system", "content": str(part.content)})
                elif isinstance(part, UserPromptPart):
                    converted.append({"role": "user", "content": str(part.content)})
        elif isinstance(message, ModelResponse):
            for part in message.parts:
                if isinstance(part, TextPart):
                    converted.append({"role": "assistant", "content": str(part.content)})
    return converted


def build_stockpulse_backed_model(llm_adapter: Any) -> Any:
    """Build a minimal PydanticAI ``Model`` backed by StockPulse's adapter.

    This is the 方案 B bridge: PydanticAI drives the agent loop while the
    actual wire call reuses StockPulse's already-resolved routing, timeout
    and thinking payload via ``LLMToolAdapter``. This first slice covers a
    text-only completion (no tool calls); the tool bridge lands with the
    ``BoundToolSession`` wiring in a later slice.
    """
    _require_pydantic_ai()
    from pydantic_ai.messages import ModelResponse, TextPart
    from pydantic_ai.models import Model
    from pydantic_ai.usage import RequestUsage

    class _StockPulseModel(Model):
        @property
        def model_name(self) -> str:
            return getattr(llm_adapter, "primary_model", "") or "stockpulse"

        @property
        def system(self) -> str:
            return "stockpulse"

        async def request(self, messages, model_settings, model_request_parameters):
            sp_messages = _to_stockpulse_messages(list(messages))
            response = await asyncio.to_thread(
                llm_adapter.call_with_tools, sp_messages, []
            )
            usage = response.usage or {}
            return ModelResponse(
                parts=[TextPart(content=response.content or "")],
                usage=RequestUsage(
                    input_tokens=int(usage.get("prompt_tokens", 0) or 0),
                    output_tokens=int(usage.get("completion_tokens", 0) or 0),
                ),
                model_name=getattr(response, "model", "") or self.model_name,
            )

    return _StockPulseModel()


class PydanticAIRuntimeAdapter:
    """Opt-in experimental runtime backed by PydanticAI (方案 B).

    ``model`` is an internal injection point: tests pass a deterministic
    fake ``Model``; internal wiring passes a StockPulse-backed model. There
    is no default construction from global config — this runtime is never
    the product default.
    """

    def __init__(
        self,
        *,
        model: Any = None,
        llm_adapter: Any = None,
        tool_session: Any = None,
        usage_recorder: Any = None,
        event_emitter: Any = None,
    ):
        if model is None and llm_adapter is None:
            raise ValueError(
                "PydanticAIRuntimeAdapter requires an explicit 'model' or an "
                "'llm_adapter' to build one; it is never auto-wired from config."
            )
        self._model = model
        self._llm_adapter = llm_adapter
        self._tool_session = tool_session
        self._usage_recorder = usage_recorder
        self._event_emitter = event_emitter

    @property
    def name(self) -> str:
        return "pydantic_ai_experimental"

    def _resolve_model(self) -> Any:
        if self._model is None:
            self._model = build_stockpulse_backed_model(self._llm_adapter)
        return self._model

    def execute(
        self,
        context: ExecutionContext,
        *,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> ExecutionHandle:
        """Run one single-agent execution synchronously; return a terminal handle.

        Two representative single-agent paths are supported: ``RUN`` (parses a
        Decision Dashboard) and ``CHAT`` (free-form answer, no dashboard).
        ``RESEARCH`` — like Multi-agent — is deliberately out of scope for the
        experimental adapter and raises rather than degrading.
        """
        if context.mode not in (ExecutionMode.RUN, ExecutionMode.CHAT):
            raise NotImplementedError(
                "PydanticAI runtime POC supports ExecutionMode.RUN / CHAT only; "
                f"mode {context.mode.value!r} is not migrated."
            )

        _require_pydantic_ai()
        execution = AgentExecution(context)
        handle = ExecutionHandle(execution)
        execution.start()
        try:
            result = self._dispatch(context, parse_dashboard=context.mode is ExecutionMode.RUN)
        except Exception as exc:
            execution.finish(
                ExecutionState.FAILED,
                error=sanitize_agent_diagnostic(str(exc) or exc.__class__.__name__),
            )
            raise
        execution.finish(
            classify_terminal_state(
                success=bool(getattr(result, "success", False)),
                cancelled=bool(getattr(result, "cancelled", False)),
                timed_out=bool(getattr(result, "timed_out", False)),
            ),
            result=result,
            error=getattr(result, "error", None),
        )
        return handle

    def _dispatch(self, context: ExecutionContext, *, parse_dashboard: bool) -> Any:
        from pydantic_ai import Agent

        from src.agent.executor import AgentResult
        from src.agent.runner import parse_dashboard_json

        toolsets = []
        if self._tool_session is not None:
            from src.agent.runtime.pydantic_ai_toolset import build_bound_session_toolset

            toolsets.append(
                build_bound_session_toolset(
                    self._tool_session, event_emitter=self._event_emitter
                )
            )
        agent = Agent(model=self._resolve_model(), toolsets=toolsets)
        run_result = agent.run_sync(context.prompt)
        content = str(run_result.output or "")
        usage = run_result.usage
        self._record_usage(usage, self._resolve_model().model_name)
        total_tokens = int(getattr(usage, "total_tokens", 0) or 0)
        model = self._resolve_model().model_name

        if not parse_dashboard:
            # Free-form CHAT path: success is a non-empty answer, no dashboard.
            return AgentResult(
                success=bool(content.strip()),
                content=content,
                dashboard=None,
                total_tokens=total_tokens,
                model=model,
                error=None if content.strip() else "Empty agent response",
            )

        dashboard = parse_dashboard_json(content)
        return AgentResult(
            success=dashboard is not None,
            content=content,
            dashboard=dashboard,
            total_tokens=total_tokens,
            model=model,
            error=None if dashboard is not None else "Failed to parse dashboard JSON from agent response",
        )

    def _record_usage(self, usage: Any, model: str) -> None:
        """Persist PydanticAI usage through StockPulse's single recorder.

        Mapping PydanticAI ``RunUsage`` onto the shared ``UsageRecorder`` keeps
        one usage authority: this experimental runtime never opens a second
        telemetry path (an AR-PY-05 hard gate).
        """
        recorder = self._usage_recorder or get_default_usage_recorder()
        usage_dict = {
            "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
            "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
            "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
        }
        recorder.record(usage_dict, model, call_type="agent")
