# -*- coding: utf-8 -*-
"""Timeout, isolation, and child-agent execution methods."""

from __future__ import annotations

import contextvars
import copy
import inspect
import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import fields as dataclass_fields
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from src.agent.protocols import (
    AgentContext,
    AgentRunStats,
    StageFailureReason,
    StageResult,
    StageStatus,
)
from src.agent.public_contract import AGENT_EXECUTION_FAILURE_MESSAGE
from src.agent.runtime_facts import build_agent_runtime_facts
from src.config import AGENT_MAX_STEPS_DEFAULT

if TYPE_CHECKING:
    from src.agent.orchestrator import OrchestratorResult, _StageProgressFence


class _ExecutionMethods:
    """Source container rebound onto ``AgentOrchestrator`` by the facade."""

    def _get_timeout_seconds(self) -> int:
        """Return the pipeline timeout in seconds.

        ``0`` means disabled. In-flight stages stop waiting at the remaining
        pipeline deadline and cannot commit late context mutations.
        """
        raw_value = getattr(self.config, "agent_orchestrator_timeout_s", 0)
        try:
            return max(0, int(raw_value or 0))
        except (TypeError, ValueError):
            return 0

    def _get_sub_agent_timeout_map(self) -> Dict[str, float]:
        """Return per-agent timeout clamps from config, skipping disabled (0) entries."""
        config = self.config
        if config is None:
            return {}
        entries = [
            ("technical", "agent_technical_agent_timeout_s"),
            ("intel", "agent_intel_agent_timeout_s"),
            ("risk", "agent_risk_agent_timeout_s"),
            ("decision", "agent_decision_agent_timeout_s"),
            ("portfolio", "agent_portfolio_agent_timeout_s"),
            ("skill", "agent_skill_agent_timeout_s"),
        ]
        return {
            key: float(val)
            for key, attr in entries
            if (val := getattr(config, attr, None)) is not None and val > 0
        }

    def _resolve_stage_timeout_seconds(
        self,
        agent_name: str,
        timeout_seconds: Optional[float],
    ) -> Optional[float]:
        """Clamp the remaining run budget by one configured stage limit."""
        sub_agent_timeout_map = self._get_sub_agent_timeout_map()
        agent_limit = sub_agent_timeout_map.get(agent_name)
        if (
            agent_limit is None
            and agent_name in getattr(self, "_skill_agent_names", set())
        ):
            agent_limit = sub_agent_timeout_map.get("skill")
        if agent_limit is None:
            return timeout_seconds
        if timeout_seconds is None:
            return agent_limit
        return min(timeout_seconds, agent_limit)

    def _build_timeout_result(
        self,
        stats: AgentRunStats,
        all_tool_calls: List[Dict[str, Any]],
        models_used: List[str],
        elapsed_s: float,
        timeout_s: int,
        ctx: Optional[AgentContext] = None,
        parse_dashboard: bool = True,
    ) -> OrchestratorResult:
        """Build a standard timeout result payload."""
        stats.total_duration_s = round(elapsed_s, 2)
        stats.models_used = list(dict.fromkeys(models_used))
        error = f"Pipeline timed out after {elapsed_s:.2f}s (limit: {timeout_s}s)"
        provider = stats.models_used[0] if stats.models_used else ""
        model = ", ".join(stats.models_used)

        dashboard = None
        content = ""
        if ctx is not None:
            dashboard, content = self._resolve_final_output(ctx, parse_dashboard=parse_dashboard)
            if parse_dashboard and dashboard is not None:
                dashboard = self._mark_partial_dashboard(
                    dashboard,
                    note="多 Agent 超时，以下结论基于已完成阶段自动降级生成。",
                )
                ctx.set_data("final_dashboard", dashboard)
                content = json.dumps(dashboard, ensure_ascii=False, indent=2)

        return OrchestratorResult(
            success=bool(content) if (not parse_dashboard or dashboard is not None) else False,
            content=content,
            dashboard=dashboard,
            error=error,
            stats=stats,
            total_steps=stats.total_stages,
            total_tokens=stats.total_tokens,
            tool_calls_log=all_tool_calls,
            provider=provider,
            model=model,
            runtime_facts=build_agent_runtime_facts(ctx) if ctx is not None else None,
            timed_out=True,
        )

    def _build_budget_skip_result(
        self,
        stats: AgentRunStats,
        all_tool_calls: List[Dict[str, Any]],
        models_used: List[str],
        elapsed_s: float,
        timeout_s: int,
        stage_name: str,
        remaining_budget: float,
        min_stage_budget_s: int,
        ctx: Optional[AgentContext] = None,
        parse_dashboard: bool = True,
    ) -> OrchestratorResult:
        """Build a result for budget-insufficient stage skip (non-timeout semantics)."""
        stats.total_duration_s = round(elapsed_s, 2)
        stats.models_used = list(dict.fromkeys(models_used))
        dashboard = None
        content = ""
        if ctx is not None:
            dashboard, content = self._resolve_final_output(ctx, parse_dashboard=parse_dashboard)
            if parse_dashboard and dashboard is not None:
                dashboard = self._mark_partial_dashboard(
                    dashboard,
                    note="多 Agent 预算不足，以下结论基于已完成阶段自动降级生成。",
                )
                ctx.set_data("final_dashboard", dashboard)
                content = json.dumps(dashboard, ensure_ascii=False, indent=2)

        return OrchestratorResult(
            success=bool(content) if (not parse_dashboard or dashboard is not None) else False,
            content=content,
            dashboard=dashboard,
            error=(
                f"Pipeline skipped before stage '{stage_name}' due to insufficient budget "
                f"({remaining_budget:.1f}s remaining, minimum {min_stage_budget_s}s required)"
            ),
            stats=stats,
            total_steps=stats.total_stages,
            total_tokens=stats.total_tokens,
            tool_calls_log=all_tool_calls,
            provider=stats.models_used[0] if stats.models_used else "",
            model=", ".join(stats.models_used),
            runtime_facts=build_agent_runtime_facts(ctx) if ctx is not None else None,
        )

    def _build_cancelled_result(
        self,
        stats: AgentRunStats,
        all_tool_calls: List[Dict[str, Any]],
        models_used: List[str],
        elapsed_s: float,
        ctx: Optional[AgentContext] = None,
    ) -> OrchestratorResult:
        """Build a cancelled result.

        Cancellation must never masquerade as a degraded pseudo-success:
        no partial dashboard is synthesized and ``success`` stays False so
        the terminal state classifies as ``CANCELLED`` rather than
        ``SUCCEEDED``.
        """
        stats.total_duration_s = round(elapsed_s, 2)
        stats.models_used = list(dict.fromkeys(models_used))
        return OrchestratorResult(
            success=False,
            content="",
            dashboard=None,
            error="Pipeline cancelled",
            stats=stats,
            total_steps=stats.total_stages,
            total_tokens=stats.total_tokens,
            tool_calls_log=all_tool_calls,
            provider=stats.models_used[0] if stats.models_used else "",
            model=", ".join(stats.models_used),
            runtime_facts=build_agent_runtime_facts(ctx) if ctx is not None else None,
            cancelled=True,
        )

    def _prepare_agent(self, agent: Any) -> Any:
        """Apply orchestrator-level runtime settings to a child agent.

        When the orchestrator-level ``max_steps`` equals the default
        (``AGENT_MAX_STEPS_DEFAULT``),
        each agent keeps its own per-agent limit — this prevents inflating
        a decision agent (designed for 3 steps) to 10 steps.

        When the user **explicitly** raises the global limit above the
        default, all agents adopt the global value so the user's intent to
        allow more steps is respected.

        When the user **lowers** the global limit below an agent's default,
        the agent is capped at the global value.
        """
        if hasattr(agent, "max_steps"):
            if self.max_steps > AGENT_MAX_STEPS_DEFAULT:
                # User explicitly raised the limit — apply to all agents.
                agent.max_steps = self.max_steps
            else:
                # Default or lowered — keep per-agent limit as ceiling.
                agent.max_steps = min(agent.max_steps, self.max_steps)
        agent.runtime_guard_policy = self.runtime_guard_policy
        return agent

    def _callable_accepts_kwarg(self, func: Any, param_name: str) -> Optional[bool]:
        """Return whether a callable accepts ``param_name`` when inspectable."""
        if not callable(func):
            return None
        try:
            signature = inspect.signature(func)
        except (TypeError, ValueError):
            return None

        if param_name in signature.parameters:
            return True
        return any(
            param.kind is inspect.Parameter.VAR_KEYWORD
            for param in signature.parameters.values()
        )

    def _agent_run_accepts_kwarg(self, run_callable: Any, param_name: str) -> bool:
        """Best-effort compatibility check for legacy test doubles / custom agents."""
        side_effect = getattr(run_callable, "side_effect", None)
        accepts = self._callable_accepts_kwarg(side_effect, param_name)
        if accepts is not None:
            return accepts

        accepts = self._callable_accepts_kwarg(run_callable, param_name)
        if accepts is not None:
            return accepts

        return True

    @staticmethod
    def _commit_stage_context(target: AgentContext, staged: AgentContext) -> None:
        """Commit one completed isolated stage while preserving container identity."""
        for context_field in dataclass_fields(AgentContext):
            name = context_field.name
            current_value = getattr(target, name)
            staged_value = getattr(staged, name)
            if isinstance(current_value, dict) and isinstance(staged_value, dict):
                current_value.clear()
                current_value.update(staged_value)
            elif isinstance(current_value, list) and isinstance(staged_value, list):
                current_value[:] = staged_value
            else:
                setattr(target, name, staged_value)

    def _execute_isolated_stage(
        self,
        agent: Any,
        ctx: AgentContext,
        *,
        stage_name: str,
        progress_callback: Optional[Callable],
        timeout_seconds: Optional[float],
        cancelled_check: Optional[Callable[[], bool]],
    ) -> tuple[StageResult, AgentContext]:
        """Run a whole stage against a copy and fence late state or progress."""
        staged_ctx = copy.deepcopy(ctx)
        progress_fence = _StageProgressFence()

        def _stage_cancelled() -> bool:
            """Combine external cancellation with the stage completion fence."""
            return progress_fence.is_closed() or (
                cancelled_check is not None and cancelled_check()
            )

        def _stage_progress(event: Dict[str, Any]) -> None:
            """Drop progress emitted after the stage reached its local deadline."""
            if progress_callback is not None:
                progress_fence.emit(progress_callback, event)

        def _execute() -> StageResult:
            """Execute decision preparation and the agent as one timed stage."""
            if stage_name == "decision":
                self._run_strategy_engine(staged_ctx)
                self._prepare_decision_context(staged_ctx)
            return self._run_stage_agent(
                agent,
                staged_ctx,
                progress_callback=(
                    _stage_progress if progress_callback is not None else None
                ),
                timeout_seconds=timeout_seconds,
                cancelled_check=_stage_cancelled,
            )

        if timeout_seconds is None or timeout_seconds <= 0:
            return _execute(), staged_ctx

        pool = ThreadPoolExecutor(max_workers=1)
        timeout_triggered = False
        try:
            future = pool.submit(contextvars.copy_context().run, _execute)
            try:
                result = future.result(timeout=timeout_seconds)
            except FuturesTimeoutError:
                timeout_triggered = True
                progress_fence.close()
                future.cancel()
                result = StageResult(
                    stage_name=stage_name,
                    status=StageStatus.FAILED,
                    error=AGENT_EXECUTION_FAILURE_MESSAGE,
                    failure_reason=StageFailureReason.TIMEOUT,
                    meta={"runtime_guard_event": "stage_timeout"},
                )
            return result, staged_ctx
        finally:
            progress_fence.close()
            pool.shutdown(
                wait=not timeout_triggered,
                cancel_futures=timeout_triggered,
            )

    def _run_stage_agent(
        self,
        agent: Any,
        ctx: AgentContext,
        progress_callback: Optional[Callable] = None,
        timeout_seconds: Optional[float] = None,
        cancelled_check: Optional[Callable[[], bool]] = None,
    ) -> StageResult:
        """Run a stage agent while preserving compatibility with older call signatures."""
        timeout_seconds = self._resolve_stage_timeout_seconds(
            agent.agent_name,
            timeout_seconds,
        )
        run_kwargs = {"progress_callback": progress_callback}
        if (
            timeout_seconds is not None
            and timeout_seconds > 0
            and self._agent_run_accepts_kwarg(agent.run, "timeout_seconds")
        ):
            run_kwargs["timeout_seconds"] = timeout_seconds
        if (
            cancelled_check is not None
            and self._agent_run_accepts_kwarg(agent.run, "cancelled_check")
        ):
            run_kwargs["cancelled_check"] = cancelled_check
        return agent.run(ctx, **run_kwargs)
