# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Experimental PydanticAI runtime adapter (AR-PY-04 / RF-05, 方案 B).

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

RF-05 scope — one provable Single RUN path:

- Only ``ExecutionMode.RUN``. ``CHAT`` / ``RESEARCH`` raise a stable
  ``unsupported_capability`` error rather than silently degrading; CHAT is
  frozen until the RF-06 conformance decision.
- The StockPulse-backed ``Model`` is the real bridge: it forwards the
  per-request tool schema from PydanticAI to ``call_with_tools`` (never a
  fixed empty array), maps tool calls / tool results / reasoning / provider
  blocks losslessly across turns, threads the execution's remaining timeout
  into every wire call, honors cooperative cancellation, and records usage
  once per call through StockPulse's single recorder (reusing
  ``LLMResponse.usage`` so provider telemetry and the input/output token
  columns are preserved).
- StockPulse still owns the system/skill prompt, dashboard constraints,
  model route, fallback and thinking payload: when an ``AgentExecutor`` is
  injected the adapter seeds the PydanticAI agent from
  ``AgentExecutor.build_run_messages`` and never builds a second set of
  business rules.
- Every tool still routes through the RF-03 ``BoundToolSession`` gates.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Callable, List, Optional, Tuple

from src.agent.runtime.contract import (
    AgentExecution,
    ExecutionContext,
    ExecutionHandle,
    ExecutionMode,
    ExecutionState,
    ProgressCallback,
    deep_thaw,
)
from src.agent.runtime.lifecycle import classify_terminal_state, get_default_usage_recorder
from src.agent.public_contract import sanitize_agent_diagnostic

_PYDANTIC_AI_DIST = "pydantic-ai-slim"


class PydanticAIRuntimeUnavailableError(RuntimeError):
    """Raised when the PydanticAI runtime is used without its optional dep."""


class _ExecutionCancelled(Exception):
    """Cooperative cancellation was observed at a bridge checkpoint."""


class _ExecutionTimedOut(Exception):
    """The execution deadline elapsed at a bridge checkpoint."""


class _ProviderBridgeError(Exception):
    """The StockPulse backend returned a sanitized provider failure."""


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


def _coerce_tool_args(args: Any) -> dict:
    """Normalize a PydanticAI ``ToolCallPart.args`` into StockPulse kwargs.

    ``args`` may arrive as a JSON string, a dict or ``None`` depending on the
    provider; StockPulse's assistant tool-call history always stores a dict.
    """
    if isinstance(args, dict):
        return args
    if isinstance(args, str) and args.strip():
        try:
            parsed = json.loads(args)
        except (ValueError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _stringify_tool_content(content: Any) -> str:
    """Render a tool return / retry payload as the string StockPulse expects."""
    if isinstance(content, str):
        return content
    try:
        return json.dumps(content, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(content)


# Namespaced keys under a PydanticAI part's ``provider_details`` used to carry
# StockPulse's must-roundtrip provider trace across the loop without loss
# (RF-05 #4). PydanticAI 2.12 preserves ``provider_details`` verbatim between
# turns, so the trace re-emerges intact in the next request's history.
_PROVIDER_BLOCKS_KEY = "stockpulse_provider_blocks"
_THOUGHT_SIGNATURE_KEY = "stockpulse_thought_signature"
_PROVIDER_SPECIFIC_KEY = "stockpulse_provider_specific_fields"


def _tool_call_trace(tool_call: Any) -> dict:
    """Encode per-tool-call provider trace for a ``ToolCallPart``.

    ``thought_signature`` and ``provider_specific_fields`` must round-trip back
    to the provider on the next call (some providers reject a tool result that
    drops them); ``provider_details`` is the lossless carrier.
    """
    trace: dict = {}
    signature = getattr(tool_call, "thought_signature", None)
    if signature is not None:
        trace[_THOUGHT_SIGNATURE_KEY] = signature
    provider_specific = getattr(tool_call, "provider_specific_fields", None)
    if provider_specific:
        trace[_PROVIDER_SPECIFIC_KEY] = dict(provider_specific)
    return trace


def _to_stockpulse_messages(messages: List[Any]) -> List[dict]:
    """Convert PydanticAI ``ModelMessage`` history to StockPulse messages.

    Maps the parts the single-run tool loop depends on: system / user text,
    assistant text, assistant ``ToolCallPart`` (as a StockPulse assistant
    message carrying ``tool_calls``) and ``ToolReturnPart`` / ``RetryPromptPart``
    (as ``role: tool`` results), so the next model request sees the tool
    outcome exactly like the native loop does (``runner.py`` history).
    """
    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        RetryPromptPart,
        SystemPromptPart,
        TextPart,
        ThinkingPart,
        ToolCallPart,
        ToolReturnPart,
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
                elif isinstance(part, (ToolReturnPart, RetryPromptPart)):
                    converted.append(
                        {
                            "role": "tool",
                            "name": part.tool_name or "",
                            "tool_call_id": part.tool_call_id,
                            "content": _stringify_tool_content(part.content),
                        }
                    )
        elif isinstance(message, ModelResponse):
            text_chunks: List[str] = []
            tool_calls: List[dict] = []
            reasoning_content: Optional[str] = None
            provider_blocks: List[dict] = []
            for part in message.parts:
                if isinstance(part, ThinkingPart):
                    # RF-05 #4: restore assistant-level provider trace.
                    if part.content and reasoning_content is None:
                        reasoning_content = str(part.content)
                    details = getattr(part, "provider_details", None) or {}
                    blocks = details.get(_PROVIDER_BLOCKS_KEY)
                    if blocks:
                        provider_blocks.extend(blocks)
                elif isinstance(part, TextPart):
                    text_chunks.append(str(part.content))
                elif isinstance(part, ToolCallPart):
                    tool_call = {
                        "id": part.tool_call_id,
                        "name": part.tool_name,
                        "arguments": _coerce_tool_args(part.args),
                    }
                    details = getattr(part, "provider_details", None) or {}
                    if _THOUGHT_SIGNATURE_KEY in details:
                        tool_call["thought_signature"] = details[_THOUGHT_SIGNATURE_KEY]
                    if details.get(_PROVIDER_SPECIFIC_KEY):
                        tool_call["provider_specific_fields"] = details[_PROVIDER_SPECIFIC_KEY]
                    tool_calls.append(tool_call)
            text = "".join(text_chunks)
            if tool_calls or text_chunks:
                assistant: dict = {"role": "assistant", "content": text or None}
                if tool_calls:
                    assistant["tool_calls"] = tool_calls
                else:
                    assistant["content"] = text
                if reasoning_content is not None:
                    assistant["reasoning_content"] = reasoning_content
                if provider_blocks:
                    assistant["provider_blocks"] = provider_blocks
                converted.append(assistant)
    return converted


def _tools_from_request_parameters(model_request_parameters: Any) -> List[dict]:
    """Map PydanticAI ``function_tools`` to StockPulse openai-tools schema.

    RF-05 #1: the model bridge must forward the *real* tool definitions the
    PydanticAI agent registered (from its toolsets) to
    ``LLMToolAdapter.call_with_tools`` — never a fixed empty array — using the
    same ``{"type": "function", "function": {...}}`` shape as
    ``ToolRegistry.to_openai_tools`` (registry.py).
    """
    function_tools = getattr(model_request_parameters, "function_tools", None) or []
    tools: List[dict] = []
    for tool_def in function_tools:
        name = getattr(tool_def, "name", None)
        if not name:
            continue
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": getattr(tool_def, "description", None) or "",
                    "parameters": getattr(tool_def, "parameters_json_schema", None)
                    or {"type": "object", "properties": {}},
                },
            }
        )
    return tools


def build_stockpulse_backed_model(
    llm_adapter: Any,
    *,
    remaining_timeout: Optional[Callable[[], Optional[float]]] = None,
    cancelled_check: Optional[Callable[[], bool]] = None,
    usage_recorder: Any = None,
) -> Any:
    """Build a PydanticAI ``Model`` backed by StockPulse's adapter (方案 B).

    PydanticAI drives the agent loop while the actual wire call reuses
    StockPulse's already-resolved routing, thinking payload and error
    handling via ``LLMToolAdapter.call_with_tools``. The bridge:

    - forwards the real tool definitions the agent registered (RF-05 #1);
    - maps StockPulse ``tool_calls`` back to ``ToolCallPart`` (RF-05 #2) so
      PydanticAI can drive the ``BoundToolSession`` toolset;
    - carries the assistant-level provider trace losslessly (RF-05 #4);
    - threads the remaining timeout into the wire call and stops before the
      call when the deadline elapsed or cancellation was requested
      (RF-05 #6 / #7);
    - records usage once per wire call through StockPulse's single recorder,
      reusing ``LLMResponse.usage`` so provider telemetry and the
      prompt/completion token columns are preserved (RF-05 #8).
    """
    _require_pydantic_ai()
    from pydantic_ai.messages import ModelResponse, TextPart, ThinkingPart, ToolCallPart
    from pydantic_ai.models import Model
    from pydantic_ai.usage import RequestUsage

    recorder = usage_recorder

    class _StockPulseModel(Model):
        def __init__(self) -> None:
            # Aggregated over the run so the adapter can attribute the actual
            # StockPulse model(s) and token totals, not PydanticAI's guess.
            self.models_used: List[str] = []
            self.total_tokens = 0

        @property
        def model_name(self) -> str:
            return getattr(llm_adapter, "primary_model", "") or "stockpulse"

        @property
        def system(self) -> str:
            return "stockpulse"

        async def request(self, messages, model_settings, model_request_parameters):
            # Cooperative cancel / deadline win over a fresh wire call: check
            # before spending another billed request (RF-05 #6 / #7).
            if cancelled_check is not None and cancelled_check():
                raise _ExecutionCancelled()
            timeout = remaining_timeout() if remaining_timeout is not None else None
            if timeout is not None and timeout <= 0:
                raise _ExecutionTimedOut()

            sp_messages = _to_stockpulse_messages(list(messages))
            tools = _tools_from_request_parameters(model_request_parameters)
            response = await asyncio.to_thread(
                llm_adapter.call_with_tools, sp_messages, tools, timeout=timeout
            )

            if getattr(response, "provider", "") == "error":
                # A sanitized public failure message: surface it as a bridge
                # error so it never masquerades as a final dashboard answer.
                raise _ProviderBridgeError(
                    sanitize_agent_diagnostic(response.content or "LLM provider error")
                )

            model_used = getattr(response, "model", "") or getattr(response, "provider", "")
            usage = response.usage or {}
            if recorder is not None and model_used and model_used != "error":
                recorder.record(usage, model_used, call_type="agent")
            if model_used and model_used != "error":
                self.models_used.append(model_used)
            self.total_tokens += int(usage.get("total_tokens", 0) or 0)

            parts: List[Any] = []
            # RF-05 #4: carry the assistant-level provider trace (reasoning /
            # opaque provider blocks) losslessly so the next turn can round it
            # back to the wire call — dropping it silently is forbidden.
            reasoning = getattr(response, "reasoning_content", None)
            provider_blocks = getattr(response, "provider_blocks", None)
            if reasoning is not None or provider_blocks:
                parts.append(
                    ThinkingPart(
                        content=reasoning or "",
                        provider_details=(
                            {_PROVIDER_BLOCKS_KEY: list(provider_blocks)}
                            if provider_blocks
                            else None
                        ),
                    )
                )
            if response.content:
                parts.append(TextPart(content=response.content))
            for tool_call in response.tool_calls or []:
                parts.append(
                    ToolCallPart(
                        tool_name=tool_call.name,
                        args=tool_call.arguments,
                        tool_call_id=tool_call.id,
                        provider_details=_tool_call_trace(tool_call) or None,
                    )
                )
            if not parts:
                parts.append(TextPart(content=""))
            return ModelResponse(
                parts=parts,
                usage=RequestUsage(
                    input_tokens=int(usage.get("prompt_tokens", 0) or 0),
                    output_tokens=int(usage.get("completion_tokens", 0) or 0),
                ),
                model_name=model_used or self.model_name,
            )

    return _StockPulseModel()


class PydanticAIRuntimeAdapter:
    """Opt-in experimental runtime backed by PydanticAI (方案 B, RF-05).

    Injection points keep this off the product default: ``model`` is a
    deterministic test double or the StockPulse-backed model, ``executor`` is
    the native ``AgentExecutor`` whose ``build_run_messages`` supplies the
    single resolved prompt authority, and ``tool_session`` is the RF-03
    ``BoundToolSession``. There is no default construction from global config.
    """

    def __init__(
        self,
        *,
        model: Any = None,
        llm_adapter: Any = None,
        executor: Any = None,
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
        self._executor = executor
        self._tool_session = tool_session
        self._usage_recorder = usage_recorder
        self._event_emitter = event_emitter
        self._deadline_monotonic: Optional[float] = None
        self._execution: Optional[AgentExecution] = None

    @property
    def name(self) -> str:
        return "pydantic_ai_experimental"

    def _remaining_timeout(self) -> Optional[float]:
        """Remaining wall-clock budget for the model/tool call (RF-05 #6)."""
        if self._deadline_monotonic is None:
            return None
        return max(0.0, self._deadline_monotonic - time.monotonic())

    def _cancel_requested(self) -> bool:
        """Cooperative cancellation probe bound to the live execution."""
        return self._execution is not None and self._execution.cancel_requested

    def _resolve_model(self) -> Any:
        if self._model is None:
            self._model = build_stockpulse_backed_model(
                self._llm_adapter,
                remaining_timeout=self._remaining_timeout,
                cancelled_check=self._cancel_requested,
                usage_recorder=self._usage_recorder or get_default_usage_recorder(),
            )
        return self._model

    def start(
        self,
        context: ExecutionContext,
        *,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> ExecutionHandle:
        """Synchronous start: run to terminal and return the handle.

        The experimental adapter drives PydanticAI's synchronous ``run_sync``
        loop, so ``start`` and ``execute`` share one implementation and return
        an already-terminal handle.
        """
        return self.execute(context, progress_callback=progress_callback)

    def execute(
        self,
        context: ExecutionContext,
        *,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> ExecutionHandle:
        """Run one Single-Agent RUN execution; return a terminal handle.

        Only ``ExecutionMode.RUN`` is supported. ``CHAT`` and ``RESEARCH``
        raise a stable ``unsupported_capability`` error rather than degrading:
        CHAT is frozen until the RF-06 conformance decision.
        """
        _require_pydantic_ai()
        if context.mode is not ExecutionMode.RUN:
            raise NotImplementedError(
                "unsupported_capability: the PydanticAI runtime POC supports "
                f"ExecutionMode.RUN only; mode {context.mode.value!r} is frozen "
                "until the RF-06 conformance decision."
            )

        self._deadline_monotonic = (
            time.monotonic() + context.timeout_seconds
            if context.timeout_seconds
            else None
        )
        execution = AgentExecution(context)
        self._execution = execution
        handle = ExecutionHandle(execution)
        execution.start()

        from src.agent.executor import AgentResult

        try:
            result = self._dispatch(context)
        except _ExecutionCancelled:
            result = AgentResult(
                success=False, content="", dashboard=None,
                error="Agent execution cancelled", cancelled=True,
            )
        except _ExecutionTimedOut:
            result = AgentResult(
                success=False, content="", dashboard=None,
                error="Agent execution timed out", timed_out=True,
            )
        except _ProviderBridgeError as exc:
            result = AgentResult(
                success=False, content="", dashboard=None, error=str(exc)
            )
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

    def _dispatch(self, context: ExecutionContext) -> Any:
        from pydantic_ai import Agent

        from src.agent.executor import AgentResult
        from src.agent.runner import parse_dashboard_json

        model = self._resolve_model()

        toolsets: List[Any] = []
        if self._tool_session is not None:
            from src.agent.runtime.pydantic_ai_toolset import build_bound_session_toolset

            toolsets.append(
                build_bound_session_toolset(
                    self._tool_session, event_emitter=self._event_emitter
                )
            )

        system_prompt, user_message = self._resolve_prompt(context)
        agent_kwargs: dict = {"model": model, "toolsets": toolsets}
        if system_prompt:
            agent_kwargs["system_prompt"] = system_prompt
        agent = Agent(**agent_kwargs)

        run_result = agent.run_sync(user_message)
        content = str(run_result.output or "")
        total_tokens = getattr(model, "total_tokens", 0) or int(
            getattr(run_result.usage, "total_tokens", 0) or 0
        )
        model_str = self._model_string(model)

        dashboard = parse_dashboard_json(content)
        return AgentResult(
            success=dashboard is not None,
            content=content,
            dashboard=dashboard,
            total_tokens=total_tokens,
            model=model_str,
            error=None
            if dashboard is not None
            else "Failed to parse dashboard JSON from agent response",
        )

    def _resolve_prompt(self, context: ExecutionContext) -> Tuple[Optional[str], str]:
        """Reuse the native single-run prompt authority when an executor exists.

        StockPulse owns the resolved system/skill prompt, dashboard constraints
        and user-message enrichment (RF-05 #5); the adapter never rebuilds them.
        When no executor is injected (deterministic model doubles), the raw
        prompt is used with no system prompt.
        """
        if self._executor is not None:
            request_context = deep_thaw(context.request_context) or None
            system_prompt, user_message, _ = self._executor.build_run_messages(
                context.prompt, request_context
            )
            return system_prompt, user_message
        return None, context.prompt

    @staticmethod
    def _model_string(model: Any) -> str:
        models = getattr(model, "models_used", None)
        if models:
            joined = ", ".join(dict.fromkeys(m for m in models if m))
            if joined:
                return joined
        return getattr(model, "model_name", "") or ""
