# -*- coding: utf-8 -*-
"""Single-run prompt assembly and execution methods."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple

from src.agent.runtime_facts import (
    build_agent_soul_runtime_facts as _build_agent_soul_runtime_facts,
)
from src.agent.stock_scope import resolve_stock_scope
from src.agent.soul import compose_agent_soul_prompt as _compose_agent_soul_prompt
from src.market_context import get_market_guidelines, get_market_role
from src.report_language import normalize_report_language
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger("src.agent.executor")

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
        # Opt-in plan→act→observe product path (#199). Default-off via Config.
        from src.agent.planning.product import try_run_with_planning

        planned = try_run_with_planning(
            self,
            task=task,
            context=context,
            cancelled_check=cancelled_check,
        )
        if planned is not None:
            if planned.runtime_facts is None:
                # Keep soul runtime facts even when planning short-circuits.
                scope_resolution = resolve_stock_scope(task, context)
                system_prompt, _, _ = self.build_run_messages(
                    task,
                    scope_resolution.effective_context,
                )
                planned.runtime_facts = _build_agent_soul_runtime_facts(system_prompt)
            return planned

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

        result = self._run_loop(
            messages,
            tool_decls,
            parse_dashboard=True,
            stock_scope=scope_resolution.stock_scope,
            cancelled_check=cancelled_check,
        )
        result.runtime_facts = _build_agent_soul_runtime_facts(system_prompt)
        return result

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
        try:
            from src.services.research_persona_prompt import (
                append_research_persona_to_system_prompt,
                inject_research_persona_into_analysis_context,
            )

            persona_context = dict(context or {})
            inject_research_persona_into_analysis_context(
                persona_context,
                config=getattr(self, "config", None),
                report_language=report_language,
            )
            system_prompt = append_research_persona_to_system_prompt(
                system_prompt,
                context=persona_context,
            )
        except Exception as exc:  # broad-exception: fallback_recorded - Optional persona failures are logged and leave the canonical prompt unchanged.
            log_safe_exception(
                logger,
                "Agent run research persona assembly failed",
                exc,
                error_code="agent_run_research_persona_failed",
                level=logging.WARNING,
            )
        system_prompt = _compose_agent_soul_prompt(system_prompt)

        # Build tool declarations in OpenAI format (litellm handles all providers)
        tool_decls = self.tool_registry.to_openai_tools()
        user_message = self._build_user_message(task, context)
        return system_prompt, user_message, tool_decls
