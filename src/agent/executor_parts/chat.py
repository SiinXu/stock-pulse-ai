# -*- coding: utf-8 -*-
"""Chat context, terminal persistence, and provider-trace methods."""

from __future__ import annotations

import json
import logging
import uuid
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from src.agent.chat_context import (
    build_agent_chat_chip_instruction,
    build_agent_chat_context_bundle,
    build_agent_chat_market_context,
    build_agent_chat_tool_registry,
)
from src.agent.provider_trace import extract_provider_trace_turns
from src.agent.public_contract import (
    AGENT_CHAT_FAILURE_HISTORY_SENTINEL,
    AGENT_CHAT_FAILURE_MESSAGE,
    sanitize_agent_diagnostic,
)
from src.agent.runtime.contract import ExecutionState
from src.agent.runtime.lifecycle import classify_result_terminal_state
from src.agent.stock_scope import resolve_stock_scope
from src.config import get_config
from src.market_structure_prompt import format_market_structure_prompt_section
from src.report_language import normalize_report_language
from src.services.daily_market_context import format_daily_market_context_prompt_section
from src.storage import get_db
from src.utils.sanitize import log_safe_exception

if TYPE_CHECKING:
    from src.agent.executor import (
        CHAT_SYSTEM_PROMPT,
        LEGACY_DEFAULT_CHAT_SYSTEM_PROMPT,
        AgentResult,
        _CHAT_TOOL_REGISTRY,
        _build_language_section,
    )

logger = logging.getLogger("src.agent.executor")


class _ChatMethods:
    """Source container rebound onto ``AgentExecutor`` by the facade."""

    def chat(self, message: str, session_id: str, progress_callback: Optional[Callable] = None, context: Optional[Dict[str, Any]] = None, cancelled_check: Optional[Callable[[], bool]] = None) -> AgentResult:
        """Execute the agent loop for a free-form chat message.

        Args:
            message: The user's chat message.
            session_id: The conversation session ID.
            progress_callback: Optional callback for streaming progress events.
            context: Optional context dict from previous analysis for data reuse.

        Returns:
            AgentResult with the text response.
        """
        from src.agent.conversation import conversation_manager

        session = conversation_manager.get_or_create(session_id)
        stored_context = session.get_market_context()
        resolution_context = dict(stored_context) if isinstance(stored_context, dict) else {}
        resolution_context.update(context or {})
        scope_resolution = resolve_stock_scope(message, resolution_context)
        context = scope_resolution.effective_context

        # Build system prompt with skills
        skills_section = ""
        if self.skill_instructions:
            skills_section = f"## 激活的交易技能\n\n{self.skill_instructions}"
        default_skill_policy_section = ""
        if self.default_skill_policy:
            default_skill_policy_section = f"\n{self.default_skill_policy}\n"
        report_language = normalize_report_language((context or {}).get("report_language", "zh"))
        market_context = build_agent_chat_market_context(
            context,
            scope_resolution.stock_scope,
            report_language,
        )
        prompt_template = (
            LEGACY_DEFAULT_CHAT_SYSTEM_PROMPT
            if self.use_legacy_default_prompt
            else CHAT_SYSTEM_PROMPT
        )
        system_prompt = prompt_template.format(
            market_role=market_context.market_role,
            market_guidelines=market_context.market_guidelines,
            chip_distribution_instruction=build_agent_chat_chip_instruction(
                market_context
            ),
            default_skill_policy_section=default_skill_policy_section,
            skills_section=skills_section,
            language_section=_build_language_section(report_language, chat_mode=True),
        )

        chat_tool_registry = build_agent_chat_tool_registry(
            self.tool_registry,
            market_context,
        )
        tool_decls = chat_tool_registry.to_openai_tools()

        # Get conversation history
        config = getattr(self.llm_adapter, "_config", None) or get_config()
        bundle = build_agent_chat_context_bundle(session_id, self.llm_adapter, config)

        # Initialize conversation
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
        ]
        messages.extend(bundle.context_messages)

        # Inject previous analysis context if provided (data reuse from report follow-up)
        context_parts = []
        if market_context.prompt_section:
            context_parts.append(market_context.prompt_section)
        has_historical_context = any(
            (context or {}).get(key)
            for key in (
                "previous_price",
                "previous_change_pct",
                "previous_analysis_summary",
                "previous_strategy",
                "daily_market_context",
                "market_structure_context",
            )
        )
        if context:
            if context.get("stock_code"):
                context_parts.append(f"股票代码: {context['stock_code']}")
            if context.get("stock_name"):
                context_parts.append(f"股票名称: {context['stock_name']}")
            if context.get("previous_price"):
                context_parts.append(f"上次分析价格: {context['previous_price']}")
            if context.get("previous_change_pct"):
                context_parts.append(f"上次涨跌幅: {context['previous_change_pct']}%")
            if context.get("previous_analysis_summary"):
                summary = context["previous_analysis_summary"]
                summary_text = json.dumps(summary, ensure_ascii=False) if isinstance(summary, dict) else str(summary)
                context_parts.append(f"上次分析摘要:\n{summary_text}")
            if context.get("previous_strategy"):
                strategy = context["previous_strategy"]
                strategy_text = json.dumps(strategy, ensure_ascii=False) if isinstance(strategy, dict) else str(strategy)
                context_parts.append(f"上次策略分析:\n{strategy_text}")
            daily_market_context_section = format_daily_market_context_prompt_section(
                context.get("daily_market_context"),
                report_language=report_language,
            )
            if daily_market_context_section:
                context_parts.append(daily_market_context_section.strip())
            market_structure_section = format_market_structure_prompt_section(
                context.get("market_structure_context"),
                report_language=report_language,
            )
            if market_structure_section:
                context_parts.append(market_structure_section.strip())
        if context_parts:
            if has_historical_context:
                context_label = "[系统提供的历史分析上下文，可供参考对比]"
                acknowledgement = "好的，我已了解该股票的历史分析数据。请告诉我你想了解什么？"
            else:
                context_label = "[系统提供的本轮股票与市场上下文]"
                acknowledgement = "好的，我会按本轮股票与市场上下文回答。"
            context_msg = context_label + "\n" + "\n".join(context_parts)
            messages.append({"role": "user", "content": context_msg})
            messages.append({"role": "assistant", "content": acknowledgement})

        messages.append({"role": "user", "content": message})
        baseline_len = len(messages)
        run_id = str(uuid.uuid4())

        # Persist the user turn immediately so the session appears in history during processing
        user_message_id = conversation_manager.add_message(session_id, "user", message)
        session.update_market_context(
            context,
            anchor_user_message_id=user_message_id,
        )

        try:
            registry_token = _CHAT_TOOL_REGISTRY.set(chat_tool_registry)
            try:
                result = self._run_loop(
                    messages,
                    tool_decls,
                    parse_dashboard=False,
                    progress_callback=progress_callback,
                    stock_scope=scope_resolution.stock_scope,
                    cancelled_check=cancelled_check,
                )
            finally:
                _CHAT_TOOL_REGISTRY.reset(registry_token)
        except Exception as exc:  # broad-exception: fallback_recorded - Safe logging and the failure sentinel preserve the Chat boundary.
            log_safe_exception(
                logger,
                "Agent chat execution raised",
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

        # Persist assistant reply (or error note) for context continuity.
        # The terminal state is classified through the single shared authority
        # so this write fence stays byte-identical to the SSE endpoint's
        # lifecycle classification. A cancelled run is user intent, not an
        # agent failure: skip the failure sentinel and the provider trace so
        # the cancelled turn leaves no misleading "analysis failed" assistant
        # message and no late partial trace behind.
        terminal_state = classify_result_terminal_state(result)
        if terminal_state is ExecutionState.SUCCEEDED:
            assistant_message_id = conversation_manager.add_message(session_id, "assistant", result.content)
            self._persist_provider_trace(
                session_id=session_id,
                run_id=run_id,
                messages=result.messages,
                baseline_len=baseline_len,
                user_message_id=user_message_id,
                assistant_message_id=assistant_message_id,
            )
        elif terminal_state is ExecutionState.CANCELLED:
            logger.info("Agent chat cancelled: session_id=%s", session_id)
        else:
            logger.error(
                "Agent chat failed: session_id=%s diagnostic=%s",
                session_id,
                sanitize_agent_diagnostic(result.error),
            )
            conversation_manager.add_message(
                session_id,
                "assistant",
                AGENT_CHAT_FAILURE_HISTORY_SENTINEL,
            )

        return result

    def _persist_provider_trace(
        self,
        *,
        session_id: str,
        run_id: str,
        messages: List[Dict[str, Any]],
        baseline_len: int,
        user_message_id: int,
        assistant_message_id: int,
    ) -> None:
        try:
            turns, diagnostics = extract_provider_trace_turns(
                messages,
                baseline_len=baseline_len,
                session_id=session_id,
                run_id=run_id,
                anchor_user_message_id=user_message_id,
                anchor_assistant_message_id=assistant_message_id,
            )
        except Exception as exc:  # broad-exception: optional_metadata - Provider-trace extraction is safely logged and may be skipped.
            log_safe_exception(
                logger,
                "Provider trace extraction failed",
                exc,
                error_code="agent_provider_trace_extraction_failed",
                level=logging.WARNING,
                context={"session_id": session_id, "run_id": run_id},
            )
            return

        if diagnostics.trace_dropped_reason:
            logger.debug(
                "Provider trace skipped for session %s run %s: %s",
                session_id,
                run_id,
                diagnostics.trace_dropped_reason,
            )
        if not turns:
            return

        try:
            db = get_db()
        except Exception as exc:  # broad-exception: optional_metadata - Provider-trace storage is optional and unavailability is safely logged.
            log_safe_exception(
                logger,
                "Provider trace storage unavailable",
                exc,
                error_code="agent_provider_trace_storage_unavailable",
                level=logging.WARNING,
                context={"session_id": session_id, "run_id": run_id},
            )
            return

        for turn in turns:
            try:
                db.save_agent_provider_turn(
                    session_id=turn.session_id,
                    run_id=turn.run_id,
                    provider=turn.provider,
                    model=turn.model,
                    anchor_user_message_id=user_message_id,
                    anchor_assistant_message_id=assistant_message_id,
                    messages=turn.messages,
                    contains_reasoning=turn.contains_reasoning,
                    contains_tool_calls=turn.contains_tool_calls,
                    contains_thinking_blocks=turn.contains_thinking_blocks,
                    must_roundtrip=turn.must_roundtrip,
                    estimated_tokens=turn.estimated_tokens,
                )
            except Exception as exc:  # broad-exception: optional_metadata - One provider-trace persistence failure is safely logged and isolated.
                log_safe_exception(
                    logger,
                    "Provider trace persistence failed",
                    exc,
                    error_code="agent_provider_trace_persistence_failed",
                    level=logging.WARNING,
                    context={
                        "session_id": session_id,
                        "run_id": run_id,
                        "provider": turn.provider,
                        "model": turn.model,
                    },
                )
