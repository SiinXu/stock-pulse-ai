# -*- coding: utf-8 -*-
"""Single- and multi-symbol chat orchestration methods."""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from src.agent.chat_context import (
    build_agent_chat_market_context,
    build_visible_chat_history,
)
from src.agent.protocols import AgentContext
from src.agent.public_contract import (
    AGENT_CHAT_FAILURE_HISTORY_SENTINEL,
    AGENT_CHAT_FAILURE_MESSAGE,
    sanitize_agent_diagnostic,
)
from src.agent.runner import run_agent_loop
from src.agent.runtime.contract import ExecutionState
from src.agent.runtime.lifecycle import classify_result_terminal_state
from src.agent.soul import compose_agent_soul_prompt as _compose_agent_soul_prompt
from src.agent.stock_scope import StockScope, resolve_stock_scope
from src.agent.tools.registry import ToolRegistry
from src.config import get_config
from src.report_language import normalize_report_language
from src.utils.sanitize import log_safe_exception

if TYPE_CHECKING:
    from src.agent.executor import AgentResult
    from src.agent.orchestrator import OrchestratorResult

logger = logging.getLogger("src.agent.orchestrator")


class _ChatMethods:
    """Source container rebound onto ``AgentOrchestrator`` by the facade."""

    # -----------------------------------------------------------------
    # Public interface (mirrors AgentExecutor)
    # -----------------------------------------------------------------

    def run(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None,
        cancelled_check: Optional[Callable[[], bool]] = None,
    ) -> "AgentResult":
        """Run the multi-agent pipeline for a dashboard analysis.

        Returns an ``AgentResult`` (same type as ``AgentExecutor.run``).
        """
        from src.agent.executor import AgentResult

        ctx = self._build_context(task, context)
        ctx.meta["response_mode"] = "dashboard"
        orch_result = self._execute_pipeline(
            ctx, parse_dashboard=True, cancelled_check=cancelled_check
        )

        return AgentResult(
            success=orch_result.success,
            content=orch_result.content,
            dashboard=orch_result.dashboard,
            tool_calls_log=orch_result.tool_calls_log,
            total_steps=orch_result.total_steps,
            total_tokens=orch_result.total_tokens,
            provider=orch_result.provider,
            model=orch_result.model,
            error=orch_result.error,
            runtime_facts=orch_result.runtime_facts,
            cancelled=orch_result.cancelled,
            timed_out=orch_result.timed_out,
        )

    def chat(
        self,
        message: str,
        session_id: str,
        progress_callback: Optional[Callable] = None,
        context: Optional[Dict[str, Any]] = None,
        cancelled_check: Optional[Callable[[], bool]] = None,
    ) -> "AgentResult":
        """Run the pipeline in chat mode (free-form answer, no dashboard parse).

        Conversation history is managed externally by the caller (via
        ``conversation_manager``); the orchestrator focuses on multi-agent
        coordination.
        """
        from src.agent.executor import AgentResult
        from src.agent.conversation import conversation_manager

        session = conversation_manager.get_or_create(session_id)
        stored_context = session.get_market_context()
        resolution_context = dict(stored_context) if isinstance(stored_context, dict) else {}
        resolution_context.update(context or {})
        scope_resolution = resolve_stock_scope(message, resolution_context)

        config = self.config or getattr(self.llm_adapter, "_config", None) or get_config()
        history = build_visible_chat_history(session_id, self.llm_adapter, config)
        report_language = normalize_report_language(
            scope_resolution.effective_context.get("report_language", "zh")
        )
        market_context = build_agent_chat_market_context(
            scope_resolution.effective_context,
            scope_resolution.stock_scope,
            report_language,
            per_symbol_tool_scopes=bool(
                scope_resolution.stock_scope is not None
                and scope_resolution.stock_scope.mode == "compare"
                and len(scope_resolution.stock_scope.allowed_stock_codes) > 1
            ),
        )

        # Persist user turn
        user_message_id = conversation_manager.add_message(
            session_id,
            "user",
            message,
        )
        session.update_market_context(
            scope_resolution.effective_context,
            anchor_user_message_id=user_message_id,
        )

        try:
            stock_scope = scope_resolution.stock_scope
            if (
                stock_scope is not None
                and stock_scope.mode == "compare"
                and len(stock_scope.allowed_stock_codes) > 1
            ):
                orch_result = self._execute_multi_symbol_chat(
                    message=message,
                    session_id=session_id,
                    context=scope_resolution.effective_context,
                    stock_scope=stock_scope,
                    history=history,
                    market_context=market_context,
                    report_language=report_language,
                    progress_callback=progress_callback,
                    cancelled_check=cancelled_check,
                )
            else:
                ctx = self._build_chat_pipeline_context(
                    message=message,
                    session_id=session_id,
                    context=scope_resolution.effective_context,
                    stock_scope=stock_scope,
                    history=history,
                    market_context=market_context,
                )
                orch_result = self._execute_pipeline(
                    ctx,
                    parse_dashboard=False,
                    progress_callback=progress_callback,
                    cancelled_check=cancelled_check,
                )
        except Exception as exc:  # broad-exception: fallback_recorded - Safe logging and the failure sentinel preserve the Chat boundary.
            log_safe_exception(
                logger,
                "Agent orchestrator chat raised",
                exc,
                error_code="agent_chat_failed",
                context={"session_id": session_id},
            )
            conversation_manager.add_message(
                session_id,
                "assistant",
                AGENT_CHAT_FAILURE_HISTORY_SENTINEL,
            )
            return AgentResult(
                success=False,
                content="",
                error=AGENT_CHAT_FAILURE_MESSAGE,
            )

        # Persist assistant response through the single shared terminal
        # classifier so the multi-agent write fence matches the single-agent
        # and SSE paths exactly. A cancelled run is user intent, not an agent
        # failure: skip the failure sentinel so the cancelled turn leaves no
        # misleading "analysis failed" assistant message in the visible history.
        terminal_state = classify_result_terminal_state(orch_result)
        if terminal_state is ExecutionState.SUCCEEDED:
            conversation_manager.add_message(session_id, "assistant", orch_result.content)
        elif terminal_state is ExecutionState.CANCELLED:
            logger.info(
                "Agent orchestrator chat cancelled: session_id=%s", session_id
            )
        else:
            logger.error(
                "Agent orchestrator chat failed: session_id=%s diagnostic=%s",
                session_id,
                sanitize_agent_diagnostic(orch_result.error),
            )
            conversation_manager.add_message(
                session_id,
                "assistant",
                AGENT_CHAT_FAILURE_HISTORY_SENTINEL,
            )

        return AgentResult(
            success=orch_result.success,
            content=orch_result.content,
            dashboard=orch_result.dashboard,
            tool_calls_log=orch_result.tool_calls_log,
            total_steps=orch_result.total_steps,
            total_tokens=orch_result.total_tokens,
            provider=orch_result.provider,
            model=orch_result.model,
            error=orch_result.error,
            runtime_facts=orch_result.runtime_facts,
            cancelled=orch_result.cancelled,
            timed_out=orch_result.timed_out,
        )

    def _build_chat_pipeline_context(
        self,
        *,
        message: str,
        session_id: str,
        context: Dict[str, Any],
        stock_scope: Optional[StockScope],
        history: List[Dict[str, Any]],
        market_context: Any,
    ) -> AgentContext:
        """Build one Chat-only pipeline context with an isolated market surface."""
        ctx = self._build_context(message, context)
        if stock_scope is not None:
            # Chat scope resolution is authoritative; legacy dashboard extraction
            # must not reinterpret a rejected token from the original message.
            ctx.stock_code = context.get("stock_code", "")
            ctx.stock_name = context.get("stock_name", "")
        ctx.session_id = session_id
        ctx.meta["response_mode"] = "chat"
        ctx.meta["agent_chat_market_context"] = market_context
        if stock_scope is not None:
            ctx.meta["stock_scope"] = stock_scope

        scoped_history = list(history)
        if market_context.prompt_section:
            scoped_history.insert(
                0,
                {"role": "user", "content": market_context.prompt_section},
            )
        if scoped_history:
            ctx.meta["conversation_history"] = scoped_history
        return ctx

    @staticmethod
    def _build_multi_symbol_cancelled_result(
        per_symbol_results: List[tuple[str, OrchestratorResult]],
        *,
        error: Optional[str] = None,
    ) -> OrchestratorResult:
        """Discard partial comparison content while retaining audit metadata."""
        models = [result.model for _, result in per_symbol_results if result.model]
        return OrchestratorResult(
            success=False,
            content="",
            tool_calls_log=[
                call
                for _, result in per_symbol_results
                for call in result.tool_calls_log
            ],
            total_steps=sum(
                result.total_steps for _, result in per_symbol_results
            ),
            total_tokens=sum(
                result.total_tokens for _, result in per_symbol_results
            ),
            provider=next(
                (result.provider for _, result in per_symbol_results if result.provider),
                "",
            ),
            model=", ".join(dict.fromkeys(models)),
            error=error or "Pipeline cancelled",
            cancelled=True,
        )

    def _execute_multi_symbol_chat(
        self,
        *,
        message: str,
        session_id: str,
        context: Dict[str, Any],
        stock_scope: StockScope,
        history: List[Dict[str, Any]],
        market_context: Any,
        report_language: str,
        progress_callback: Optional[Callable],
        cancelled_check: Optional[Callable[[], bool]],
    ) -> OrchestratorResult:
        """Run one guarded specialist pipeline per comparison symbol."""
        allowed = set(stock_scope.allowed_stock_codes)
        stock_codes = [
            code for code in market_context.stock_codes if code in allowed
        ]
        per_symbol_results: List[tuple[str, OrchestratorResult]] = []
        timeout_seconds = self._get_timeout_seconds()
        deadline = (
            time.monotonic() + timeout_seconds
            if timeout_seconds > 0
            else None
        )

        for stock_code in stock_codes:
            if cancelled_check is not None and cancelled_check():
                return self._build_multi_symbol_cancelled_result(
                    per_symbol_results
                )
            remaining_timeout = (
                max(0.0, deadline - time.monotonic())
                if deadline is not None
                else None
            )
            if remaining_timeout is not None and remaining_timeout <= 0:
                per_symbol_results.extend(
                    (
                        pending_code,
                        OrchestratorResult(
                            success=False,
                            error="Comparison timeout exhausted before analysis.",
                            timed_out=True,
                        ),
                    )
                    for pending_code in stock_codes[len(per_symbol_results):]
                )
                return self._synthesize_multi_symbol_chat(
                    message=message,
                    market_context=market_context,
                    report_language=report_language,
                    per_symbol_results=per_symbol_results,
                    cancelled_check=cancelled_check,
                    timeout_seconds=0,
                )
            symbol_resolution = resolve_stock_scope(f"analyze {stock_code}", context)
            symbol_scope = StockScope(
                expected_stock_code=stock_code,
                allowed_stock_codes={stock_code},
                mode="switch",
            )
            symbol_context = dict(symbol_resolution.effective_context)
            symbol_context["stock_code"] = stock_code
            symbol_context["stock_name"] = ""
            symbol_market_context = build_agent_chat_market_context(
                symbol_context,
                symbol_scope,
                report_language,
            )
            ctx = self._build_chat_pipeline_context(
                message=(
                    f"Analyze {stock_code} as one isolated leg of a later comparison. "
                    "Return a standalone evidence-based analysis for this symbol only."
                ),
                session_id=session_id,
                context=symbol_context,
                stock_scope=symbol_scope,
                history=history,
                market_context=symbol_market_context,
            )
            ctx.meta["comparison_stock_codes"] = list(stock_codes)
            result = self._execute_pipeline(
                ctx,
                parse_dashboard=False,
                progress_callback=progress_callback,
                cancelled_check=cancelled_check,
                timeout_seconds=remaining_timeout,
            )
            per_symbol_results.append((stock_code, result))
            if result.cancelled:
                return self._build_multi_symbol_cancelled_result(
                    per_symbol_results,
                    error=result.error,
                )
            if cancelled_check is not None and cancelled_check():
                return self._build_multi_symbol_cancelled_result(
                    per_symbol_results
                )

        remaining_timeout = (
            max(0.0, deadline - time.monotonic())
            if deadline is not None
            else None
        )
        return self._synthesize_multi_symbol_chat(
            message=message,
            market_context=market_context,
            report_language=report_language,
            per_symbol_results=per_symbol_results,
            cancelled_check=cancelled_check,
            timeout_seconds=remaining_timeout,
        )

    def _synthesize_multi_symbol_chat(
        self,
        *,
        message: str,
        market_context: Any,
        report_language: str,
        per_symbol_results: List[tuple[str, OrchestratorResult]],
        cancelled_check: Optional[Callable[[], bool]],
        timeout_seconds: Optional[float],
    ) -> OrchestratorResult:
        """Synthesize isolated per-symbol evidence without exposing tools."""
        if cancelled_check is not None and cancelled_check():
            return self._build_multi_symbol_cancelled_result(
                per_symbol_results
            )

        language = normalize_report_language(report_language)
        if language in {"en", "ko"}:
            system_prompt = (
                "You synthesize cross-market stock comparisons. Use only the supplied "
                "per-symbol analyses, compare like-for-like evidence, preserve currency "
                "and timezone differences, and state every missing-data limitation."
            )
        else:
            system_prompt = (
                "你负责综合跨市场股票比较。只能使用给定的逐标的分析，必须按同口径比较，"
                "保留币种与时区差异，并明确说明所有数据缺口。"
            )
        system_prompt = _compose_agent_soul_prompt(system_prompt)

        evidence = []
        for stock_code, result in per_symbol_results:
            status = (
                "partial"
                if result.success and result.content and result.timed_out
                else "available"
                if result.success and result.content
                else "unavailable"
            )
            evidence.append({
                "stock_code": stock_code,
                "status": status,
                "analysis": result.content if result.success else "",
                "diagnostic": (
                    ""
                    if status == "available"
                    else sanitize_agent_diagnostic(
                        result.error
                        or (
                            "Analysis timed out before all stages completed."
                            if result.timed_out
                            else AGENT_CHAT_FAILURE_MESSAGE
                        )
                    )
                ),
            })
        user_prompt = "\n\n".join(
            [
                market_context.prompt_section,
                f"Original comparison request:\n{message}",
                "Per-symbol analysis evidence:\n"
                + json.dumps(evidence, ensure_ascii=False, default=str),
            ]
        )
        synthesis_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        has_usable_evidence = any(
            result.success and bool(result.content)
            for _, result in per_symbol_results
        )
        loop_result = None
        if has_usable_evidence and (
            timeout_seconds is None or timeout_seconds > 0
        ):
            loop_result = run_agent_loop(
                messages=synthesis_messages,
                tool_registry=ToolRegistry(),
                llm_adapter=self.llm_adapter,
                max_steps=1,
                max_wall_clock_seconds=timeout_seconds,
                emit_stage_events=False,
                cancelled_check=cancelled_check,
                runtime_guard_policy=self.runtime_guard_policy,
            )
        if loop_result is not None and loop_result.cancelled:
            return self._build_multi_symbol_cancelled_result(
                per_symbol_results,
                error=loop_result.error,
            )
        if cancelled_check is not None and cancelled_check():
            return self._build_multi_symbol_cancelled_result(
                per_symbol_results
            )

        synthesis_succeeded = bool(
            loop_result is not None
            and loop_result.success
            and loop_result.content
        )
        fallback_content = self._build_multi_symbol_fallback(
            per_symbol_results,
            language,
        )
        if synthesis_succeeded:
            content = loop_result.content
            limitations = self._build_multi_symbol_limitations(
                per_symbol_results,
                language,
            )
            if limitations:
                content = f"{content}\n\n{limitations}"
        else:
            content = fallback_content if has_usable_evidence else ""
        if not synthesis_succeeded:
            if not has_usable_evidence:
                diagnostic = "no_usable_comparison_evidence"
            elif loop_result is None:
                diagnostic = "comparison_timeout"
            else:
                diagnostic = sanitize_agent_diagnostic(loop_result.error)
            logger.warning(
                "Multi-symbol Chat synthesis degraded: diagnostic=%s",
                diagnostic,
            )

        models = [
            result.model
            for _, result in per_symbol_results
            if result.model
        ]
        if loop_result is not None and loop_result.model:
            models.append(loop_result.model)
        return OrchestratorResult(
            success=bool(content) and has_usable_evidence,
            content=content,
            tool_calls_log=[
                call
                for _, result in per_symbol_results
                for call in result.tool_calls_log
            ],
            total_steps=(
                sum(result.total_steps for _, result in per_symbol_results)
                + (loop_result.total_steps if loop_result is not None else 0)
            ),
            total_tokens=(
                sum(result.total_tokens for _, result in per_symbol_results)
                + (loop_result.total_tokens if loop_result is not None else 0)
            ),
            provider=(
                (loop_result.provider if loop_result is not None else "")
                or next(
                    (result.provider for _, result in per_symbol_results if result.provider),
                    "",
                )
            ),
            model=", ".join(dict.fromkeys(models)),
            error=(
                None
                if content and has_usable_evidence
                else AGENT_CHAT_FAILURE_MESSAGE
            ),
            timed_out=(
                any(result.timed_out for _, result in per_symbol_results)
                or bool(
                    has_usable_evidence
                    and (
                        loop_result is None
                        or bool(loop_result.timed_out)
                    )
                )
            ),
        )

    @staticmethod
    def _build_multi_symbol_limitations(
        per_symbol_results: List[tuple[str, OrchestratorResult]],
        report_language: str,
    ) -> str:
        """Build deterministic missing/partial-leg disclosure for synthesis."""
        english = report_language in {"en", "ko"}
        entries = []
        for stock_code, result in per_symbol_results:
            if result.success and result.content and not result.timed_out:
                continue
            diagnostic = sanitize_agent_diagnostic(
                result.error
                or (
                    "Analysis timed out before all stages completed."
                    if result.timed_out
                    else AGENT_CHAT_FAILURE_MESSAGE
                )
            )
            if result.timed_out:
                label = "Timed out or partial" if english else "超时或仅部分完成"
            else:
                label = "Unavailable" if english else "不可用"
            entries.append(f"- `{stock_code}`: {label}: {diagnostic}")
        if not entries:
            return ""
        heading = "### Data limitations" if english else "### 数据限制"
        return "\n".join([heading, *entries])

    @staticmethod
    def _build_multi_symbol_fallback(
        per_symbol_results: List[tuple[str, OrchestratorResult]],
        report_language: str,
    ) -> str:
        """Return an explicit per-symbol fallback when synthesis is unavailable."""
        if not per_symbol_results:
            return ""
        heading = (
            "Cross-market synthesis was unavailable; per-symbol analyses follow."
            if report_language in {"en", "ko"}
            else "跨市场综合暂不可用，以下为逐标的分析。"
        )
        sections = [heading]
        for stock_code, result in per_symbol_results:
            if result.success and result.content:
                body = result.content
                if result.timed_out:
                    diagnostic = sanitize_agent_diagnostic(
                        result.error
                        or "Analysis timed out before all stages completed."
                    )
                    limitation = (
                        f"Limitation: timed out or partial: {diagnostic}"
                        if report_language in {"en", "ko"}
                        else f"限制：超时或仅部分完成：{diagnostic}"
                    )
                    body = f"{body}\n\n{limitation}"
            else:
                diagnostic = sanitize_agent_diagnostic(
                    result.error
                    or (
                        "Analysis timed out."
                        if result.timed_out
                        else AGENT_CHAT_FAILURE_MESSAGE
                    )
                )
                body = (
                    f"Unavailable: {diagnostic}"
                    if report_language in {"en", "ko"}
                    else f"不可用：{diagnostic}"
                )
            sections.append(f"## {stock_code}\n{body}")
        return "\n\n".join(sections)
