# -*- coding: utf-8 -*-
"""Shared-loop adaptation and user-message assembly methods."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from src.agent.runner import parse_dashboard_json_result, run_agent_loop
from src.agent.stock_scope import StockScope
from src.market_phase_prompt import format_market_phase_prompt_section
from src.market_structure_prompt import format_market_structure_prompt_section
from src.report_language import normalize_report_language
from src.services.daily_market_context import format_daily_market_context_prompt_section

if TYPE_CHECKING:
    from src.agent.executor import AgentResult, _CHAT_TOOL_REGISTRY


class _LoopMethods:
    """Source container rebound onto ``AgentExecutor`` by the facade."""

    def _run_loop(
        self,
        messages: List[Dict[str, Any]],
        tool_decls: List[Dict[str, Any]],
        parse_dashboard: bool,
        progress_callback: Optional[Callable] = None,
        stock_scope: Optional[StockScope] = None,
        cancelled_check: Optional[Callable[[], bool]] = None,
    ) -> AgentResult:
        """Delegate to the shared runner and adapt the result.

        Dashboard mode preserves the raw answer unless deterministic
        post-processing removes a reserved model-authored field. Free-form
        mode always preserves the raw text.
        """
        chat_tool_registry = _CHAT_TOOL_REGISTRY.get()
        loop_result = run_agent_loop(
            messages=messages,
            tool_registry=(
                chat_tool_registry
                if chat_tool_registry is not None
                else self.tool_registry
            ),
            llm_adapter=self.llm_adapter,
            max_steps=self.max_steps,
            progress_callback=progress_callback,
            max_wall_clock_seconds=self.timeout_seconds,
            stock_scope=stock_scope,
            cancelled_check=cancelled_check,
        )

        model_str = loop_result.model

        if parse_dashboard and loop_result.success:
            parse_result = parse_dashboard_json_result(loop_result.content)
            dashboard = parse_result.payload if parse_result is not None else None
            return AgentResult(
                success=dashboard is not None,
                content=(
                    json.dumps(dashboard, ensure_ascii=False, indent=2)
                    if parse_result is not None and parse_result.reserved_field_removed
                    else loop_result.content
                ),
                dashboard=dashboard,
                tool_calls_log=loop_result.tool_calls_log,
                total_steps=loop_result.total_steps,
                total_tokens=loop_result.total_tokens,
                provider=loop_result.provider,
                model=model_str,
                error=None if dashboard else "Failed to parse dashboard JSON from agent response",
                messages=loop_result.messages,
                cancelled=loop_result.cancelled,
                timed_out=loop_result.timed_out,
            )

        return AgentResult(
            success=loop_result.success,
            content=loop_result.content,
            dashboard=None,
            tool_calls_log=loop_result.tool_calls_log,
            total_steps=loop_result.total_steps,
            total_tokens=loop_result.total_tokens,
            provider=loop_result.provider,
            model=model_str,
            error=loop_result.error,
            messages=loop_result.messages,
            cancelled=loop_result.cancelled,
            timed_out=loop_result.timed_out,
        )

    def _build_user_message(self, task: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Build the initial user message."""
        parts = [task]
        if context:
            report_language = normalize_report_language(context.get("report_language", "zh"))
            if context.get("stock_code"):
                parts.append(f"\n股票代码: {context['stock_code']}")
            if context.get("report_type"):
                parts.append(f"报告类型: {context['report_type']}")
            if report_language == "en":
                parts.append("输出语言: English（所有 JSON 键名保持不变，所有面向用户的文本值使用英文）")
            elif report_language == "ko":
                parts.append("출력 언어: 한국어（모든 JSON 키는 그대로 유지하고, 사용자 노출 텍스트 값은 한국어로 작성）")
            else:
                parts.append("输出语言: 中文（所有 JSON 键名保持不变，所有面向用户的文本值使用中文）")

            market_phase_section = format_market_phase_prompt_section(
                context.get("market_phase_context"),
                report_language=report_language,
            )
            if market_phase_section:
                parts.append(market_phase_section)

            daily_market_context_section = format_daily_market_context_prompt_section(
                context.get("daily_market_context"),
                report_language=report_language,
            )
            if daily_market_context_section:
                parts.append(daily_market_context_section)

            market_structure_section = format_market_structure_prompt_section(
                context.get("market_structure_context"),
                report_language=report_language,
            )
            if market_structure_section:
                parts.append(market_structure_section)

            analysis_context_pack_summary = context.get("analysis_context_pack_summary")
            if isinstance(analysis_context_pack_summary, str) and analysis_context_pack_summary:
                parts.append(analysis_context_pack_summary)

            # Inject pre-fetched context data to avoid redundant fetches
            if context.get("realtime_quote"):
                parts.append(f"\n[系统已获取的实时行情]\n{json.dumps(context['realtime_quote'], ensure_ascii=False)}")
            if context.get("chip_distribution"):
                parts.append(f"\n[系统已获取的筹码分布]\n{json.dumps(context['chip_distribution'], ensure_ascii=False)}")
            if context.get("news_context"):
                parts.append(f"\n[系统已获取的新闻与舆情情报]\n{context['news_context']}")

        parts.append("\n请使用可用工具获取缺失的数据（如历史K线、新闻等），然后以决策仪表盘 JSON 格式输出分析结果。")
        return "\n".join(parts)
