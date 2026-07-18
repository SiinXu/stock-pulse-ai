# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Native runtime adapter (AR-PY-01).

Wraps the existing factory products (``AgentExecutor`` /
``AgentOrchestrator`` / ``ResearchAgent``) behind the vendor-neutral
runtime contract without rewriting any of their internals. Results are
passed through unchanged so wrapper parity with the direct entrypoints
is structural, not reimplemented.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from src.agent.runtime.contract import (
    AgentExecution,
    ExecutionContext,
    ExecutionHandle,
    ExecutionMode,
    ExecutionState,
    ProgressCallback,
)
from src.agent.runtime.lifecycle import classify_terminal_state
from src.agent.public_contract import sanitize_agent_diagnostic

logger = logging.getLogger(__name__)

_DEFAULT_RESEARCH_TOKEN_BUDGET = 30000


class NativeRuntimeAdapter:
    """Default, permanent runtime adapter backed by the native agent stack."""

    def __init__(self, config: Any = None, skills: Optional[list] = None, executor: Any = None):
        self._config = config
        self._skills = skills
        self._executor = executor

    @property
    def name(self) -> str:
        return "native"

    def execute(
        self,
        context: ExecutionContext,
        *,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> ExecutionHandle:
        """Run synchronously and return a terminal handle.

        Exceptions raised by the native stack are recorded as ``FAILED``
        and re-raised unchanged: the adapter never converts an error into
        a silent degraded result.
        """
        execution = AgentExecution(context)
        handle = ExecutionHandle(execution)
        execution.start()
        try:
            result = self._dispatch(context, progress_callback)
        except Exception as exc:
            execution.finish(
                ExecutionState.FAILED,
                error=sanitize_agent_diagnostic(str(exc) or exc.__class__.__name__),
            )
            raise
        execution.finish(
            self._terminal_state_for(result),
            result=result,
            error=getattr(result, "error", None),
        )
        return handle

    def _dispatch(
        self,
        context: ExecutionContext,
        progress_callback: Optional[ProgressCallback],
    ) -> Any:
        request_context = dict(context.request_context) or None
        if context.mode is ExecutionMode.RUN:
            # Native run() has no progress channel; the callback only
            # applies to chat/research until typed events land (AR-PY-03).
            return self._resolve_executor().run(context.prompt, context=request_context)
        if context.mode is ExecutionMode.CHAT:
            return self._resolve_executor().chat(
                context.prompt,
                session_id=context.session_id,
                progress_callback=progress_callback,
                context=request_context,
            )
        if context.mode is ExecutionMode.RESEARCH:
            return self._run_research(context, progress_callback, request_context)
        raise ValueError(f"unsupported execution mode: {context.mode}")

    def _run_research(
        self,
        context: ExecutionContext,
        progress_callback: Optional[ProgressCallback],
        request_context: Optional[dict],
    ) -> Any:
        from src.agent.factory import get_tool_registry
        from src.agent.llm_adapter import LLMToolAdapter
        from src.agent.research import ResearchAgent

        config = self._resolve_config()
        agent = ResearchAgent(
            tool_registry=get_tool_registry(),
            llm_adapter=LLMToolAdapter(config),
            token_budget=getattr(
                config, "agent_deep_research_budget", _DEFAULT_RESEARCH_TOKEN_BUDGET
            ),
        )
        return agent.research(
            context.prompt,
            context=request_context,
            progress_callback=progress_callback,
            timeout_seconds=context.timeout_seconds,
        )

    def _resolve_config(self) -> Any:
        if self._config is None:
            from src.config import get_config

            self._config = get_config()
        return self._config

    def _resolve_executor(self) -> Any:
        if self._executor is None:
            from src.agent.factory import build_agent_executor

            self._executor = build_agent_executor(self._resolve_config(), skills=self._skills)
        return self._executor

    @staticmethod
    def _terminal_state_for(result: Any) -> ExecutionState:
        return classify_terminal_state(
            success=bool(getattr(result, "success", False)),
            cancelled=bool(getattr(result, "cancelled", False)),
            timed_out=bool(getattr(result, "timed_out", False)),
        )
