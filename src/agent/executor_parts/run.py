# -*- coding: utf-8 -*-
"""Single-run prompt assembly and execution methods."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple

from src.agent.stock_scope import resolve_stock_scope
from src.market_context import get_market_guidelines, get_market_role
from src.report_language import normalize_report_language

if TYPE_CHECKING:
    from src.agent.executor import (
        AGENT_SYSTEM_PROMPT,
        LEGACY_DEFAULT_AGENT_SYSTEM_PROMPT,
        AgentResult,
        _build_language_section,
    )


class _RunMethods:
    """Source container rebound onto ``AgentExecutor`` by the facade."""

    def run(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None,
        cancelled_check: Optional[Callable[[], bool]] = None,
    ) -> AgentResult:
        """Execute the agent loop for a given task.

        Args:
            task: The user task / analysis request.
            context: Optional context dict (e.g., {"stock_code": "600519"}).
            cancelled_check: Optional cooperative-cancellation probe threaded
                into the shared runner.

        Returns:
            AgentResult with parsed dashboard or error.
        """
        scope_resolution = resolve_stock_scope(task, context)
        system_prompt, user_message, tool_decls = self.build_run_messages(
            task,
            scope_resolution.effective_context,
        )

        # Initialize conversation
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        return self._run_loop(
            messages,
            tool_decls,
            parse_dashboard=True,
            stock_scope=scope_resolution.stock_scope,
            cancelled_check=cancelled_check,
        )

    def build_run_messages(
        self, task: str, context: Optional[Dict[str, Any]] = None
    ) -> Tuple[str, str, List[Dict[str, Any]]]:
        """Assemble the resolved single-run prompt inputs.

        Single authority for the Single RUN system prompt, user message and
        OpenAI tool declarations so every runtime (native loop and the
        experimental PydanticAI adapter) seeds from the same resolved skill,
        market and dashboard constraints instead of rebuilding them.

        Returns ``(system_prompt, user_message, tool_decls)``.
        """
        skills_section = ""
        if self.skill_instructions:
            skills_section = f"## 激活的交易技能\n\n{self.skill_instructions}"
        default_skill_policy_section = ""
        if self.default_skill_policy:
            default_skill_policy_section = f"\n{self.default_skill_policy}\n"
        report_language = normalize_report_language((context or {}).get("report_language", "zh"))
        stock_code = (context or {}).get("stock_code", "")
        market_role = get_market_role(stock_code, report_language)
        market_guidelines = get_market_guidelines(stock_code, report_language)
        prompt_template = (
            LEGACY_DEFAULT_AGENT_SYSTEM_PROMPT
            if self.use_legacy_default_prompt
            else AGENT_SYSTEM_PROMPT
        )
        system_prompt = prompt_template.format(
            market_role=market_role,
            market_guidelines=market_guidelines,
            default_skill_policy_section=default_skill_policy_section,
            skills_section=skills_section,
            language_section=_build_language_section(report_language),
        )

        # Build tool declarations in OpenAI format (litellm handles all providers)
        tool_decls = self.tool_registry.to_openai_tools()
        user_message = self._build_user_message(task, context)
        return system_prompt, user_message, tool_decls
