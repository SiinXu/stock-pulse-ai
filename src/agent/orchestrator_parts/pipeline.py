# -*- coding: utf-8 -*-
"""Agent-chain construction, execution, and degradation methods."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from src.agent.chat_context import build_agent_chat_tool_registry
from src.agent.disagreement import build_agent_disagreement_summary
from src.agent.protocols import (
    AgentContext,
    AgentRunStats,
    StageFailureReason,
    StageResult,
    StageStatus,
    normalize_stage_failure_reason,
)
from src.agent.public_contract import AGENT_EXECUTION_FAILURE_MESSAGE
from src.agent.runtime.guards import (
    StageFailurePolicy,
    log_runtime_guard_event,
)
from src.agent.runtime_facts import (
    DegradationBoundary,
    DegradedEvent,
    PipelineTerminationFact,
    build_agent_runtime_facts,
)
from src.agent.skills.engine import StrategyResultStatus
from src.agent.stream_events import stream_event
from src.agent.tools.registry import ToolRegistry
from src.utils.sanitize import log_safe_exception

if TYPE_CHECKING:
    from src.agent.orchestrator import OrchestratorResult

logger = logging.getLogger("src.agent.orchestrator")
NON_CRITICAL_BASE_STAGES = frozenset({"intel", "risk"})


class _PipelineMethods:
    """Source container rebound onto ``AgentOrchestrator`` by the facade."""

    # -----------------------------------------------------------------
    # Pipeline execution
    # -----------------------------------------------------------------

    def _execute_pipeline(
        self,
        ctx: AgentContext,
        parse_dashboard: bool = True,
        progress_callback: Optional[Callable] = None,
        cancelled_check: Optional[Callable[[], bool]] = None,
        timeout_seconds: Optional[float] = None,
    ) -> OrchestratorResult:
        """Run the agent pipeline according to ``self.mode``."""
        stats = AgentRunStats()
        all_tool_calls: List[Dict[str, Any]] = []
        models_used: List[str] = []
        t0 = time.time()
        timeout_s = (
            self._get_timeout_seconds()
            if timeout_seconds is None
            else max(0.0, float(timeout_seconds))
        )

        agents = self._build_agent_chain(ctx)
        specialist_agents_inserted = False
        stage_entry_counts: Dict[str, int] = {}
        index = 0

        # Minimum seconds required for a stage to do useful work.  Starting
        # a stage with less budget virtually guarantees a timeout that wastes
        # an LLM billing cycle.  Only enforced after at least one stage has
        # completed so that the first stage always gets a chance to run
        # even when the total budget is small.
        _MIN_STAGE_BUDGET_S = 15

        while index < len(agents):
            agent = agents[index]
            elapsed_s = time.time() - t0

            # Cancellation wins over timeout / degradation: probe before any
            # other pre-stage gate so a cancelled run terminates as CANCELLED
            # rather than masquerading as a degraded timeout pseudo-success.
            if cancelled_check is not None and cancelled_check():
                logger.info("[Orchestrator] pipeline cancelled before stage '%s'", agent.agent_name)
                return self._build_cancelled_result(
                    stats, all_tool_calls, models_used, elapsed_s, ctx=ctx
                )

            remaining_budget = timeout_s - elapsed_s if timeout_s else None
            stage_min_budget_s = (
                _MIN_STAGE_BUDGET_S
            )
            timeout_exhausted = (
                timeout_s
                and remaining_budget is not None
                and remaining_budget <= 0
            )
            budget_guard_triggered = (
                timeout_s
                and remaining_budget is not None
                and index > 0
                and remaining_budget < stage_min_budget_s
            )
            if timeout_exhausted:
                log_runtime_guard_event(
                    logger,
                    "run_timeout",
                    level=logging.ERROR,
                    scope="orchestrator",
                    phase="before_stage",
                    stage=agent.agent_name,
                    elapsed_seconds=round(elapsed_s, 3),
                    limit_seconds=timeout_s,
                )
                self._record_degraded_event(
                    ctx,
                    stage=agent.agent_name,
                    reason=StageFailureReason.TIMEOUT,
                    boundary=DegradationBoundary.BEFORE_STAGE,
                )
                if progress_callback:
                    progress_callback(stream_event(
                        "pipeline_timeout",
                        stage=agent.agent_name,
                        elapsed=round(elapsed_s, 2),
                        timeout=timeout_s,
                    ))
                if ctx is not None:
                    self._apply_partition_fallback(ctx)
                return self._build_timeout_result(
                    stats,
                    all_tool_calls,
                    models_used,
                    elapsed_s,
                    timeout_s,
                    ctx=ctx,
                    parse_dashboard=parse_dashboard,
                )

            if budget_guard_triggered:
                logger.warning(
                    "[Orchestrator] pipeline insufficient budget before stage '%s' (%.1fs remaining, min %ds)",
                    agent.agent_name,
                    remaining_budget,
                    stage_min_budget_s,
                )
                self._record_degraded_event(
                    ctx,
                    stage=agent.agent_name,
                    reason=StageFailureReason.BUDGET_SKIP,
                    boundary=DegradationBoundary.BEFORE_STAGE,
                )
                if progress_callback:
                    progress_callback(stream_event(
                        "pipeline_budget_skipped",
                        stage=agent.agent_name,
                        elapsed=round(elapsed_s, 2),
                        timeout=timeout_s,
                        remaining=round(remaining_budget, 2),
                        minimum=stage_min_budget_s,
                        reason="insufficient_budget",
                        message=(
                            f"Skipped {agent.agent_name} analysis due to insufficient "
                            "remaining budget"
                        ),
                    ))
                if ctx is not None:
                    self._apply_partition_fallback(ctx)
                return self._build_budget_skip_result(
                    stats,
                    all_tool_calls,
                    models_used,
                    elapsed_s,
                    timeout_s,
                    agent.agent_name,
                    remaining_budget,
                    stage_min_budget_s,
                    ctx=ctx,
                    parse_dashboard=parse_dashboard,
                )

            if (
                self.mode == "specialist"
                and agent.agent_name == "decision"
                and not specialist_agents_inserted
            ):
                specialist_agents = self._build_specialist_agents(ctx)
                self._skill_agent_names = {a.agent_name for a in specialist_agents}
                specialist_agents_inserted = True
                if specialist_agents:
                    agents[index:index] = specialist_agents
                    continue

            stage_name = str(agent.agent_name or "")
            observed_entries = stage_entry_counts.get(stage_name, 0) + 1
            stage_entry_limit = self.runtime_guard_policy.max_stage_entries
            if stage_entry_limit > 0 and observed_entries > stage_entry_limit:
                log_runtime_guard_event(
                    logger,
                    "stage_loop_detected",
                    level=logging.ERROR,
                    scope="stage",
                    stage=stage_name,
                    observed=observed_entries,
                    limit=stage_entry_limit,
                    action="stop",
                )
                guard_result = StageResult(
                    stage_name=stage_name,
                    status=StageStatus.FAILED,
                    error="Stage re-entry limit exceeded",
                    failure_reason=StageFailureReason.LOOP_DETECTED,
                    meta={"runtime_guard_event": "stage_loop_detected"},
                )
                stats.record_stage(guard_result)
                stats.total_duration_s = round(elapsed_s, 2)
                stats.models_used = list(dict.fromkeys(models_used))
                self._record_degraded_event(
                    ctx,
                    stage=stage_name,
                    reason=StageFailureReason.LOOP_DETECTED,
                    boundary=DegradationBoundary.BEFORE_STAGE,
                )
                return OrchestratorResult(
                    success=False,
                    error=f"Stage '{stage_name}' exceeded the re-entry limit",
                    stats=stats,
                    total_steps=stats.total_stages,
                    total_tokens=stats.total_tokens,
                    tool_calls_log=all_tool_calls,
                    provider=stats.models_used[0] if stats.models_used else "",
                    model=", ".join(stats.models_used),
                    runtime_facts=build_agent_runtime_facts(ctx),
                )
            stage_entry_counts[stage_name] = observed_entries

            if progress_callback:
                progress_callback(stream_event(
                    "stage_start",
                    stage=agent.agent_name,
                    message=f"Starting {agent.agent_name} analysis...",
                ))

            remaining_timeout_s = (
                max(0.0, timeout_s - elapsed_s)
                if timeout_s
                else None
            )
            effective_stage_timeout_s = self._resolve_stage_timeout_seconds(
                stage_name,
                remaining_timeout_s,
            )
            stage_started_elapsed_s = elapsed_s
            try:
                result, staged_ctx = self._execute_isolated_stage(
                    agent,
                    ctx,
                    stage_name=stage_name,
                    progress_callback=progress_callback,
                    timeout_seconds=effective_stage_timeout_s,
                    cancelled_check=cancelled_check,
                )
                if not isinstance(result, StageResult):
                    raise TypeError("Stage agent returned an invalid result")
                if result.status == StageStatus.COMPLETED:
                    self._commit_stage_context(ctx, staged_ctx)
            except TimeoutError as exc:
                log_safe_exception(
                    logger,
                    "[Orchestrator] stage execution timed out",
                    exc,
                    error_code="agent_stage_timeout",
                    level=logging.WARNING,
                    context={"stage": stage_name},
                )
                log_runtime_guard_event(
                    logger,
                    "stage_exception_captured",
                    scope="stage",
                    stage=stage_name,
                    exception_type=type(exc).__name__,
                    reason=StageFailureReason.TIMEOUT.value,
                )
                result = StageResult(
                    stage_name=stage_name,
                    status=StageStatus.FAILED,
                    error=AGENT_EXECUTION_FAILURE_MESSAGE,
                    failure_reason=StageFailureReason.TIMEOUT,
                    meta={"runtime_guard_event": "stage_exception_captured"},
                )
            except Exception as exc:  # broad-exception: fallback_recorded - Escaped stage failures become typed results at the isolation boundary.
                log_safe_exception(
                    logger,
                    "[Orchestrator] stage execution failed",
                    exc,
                    error_code="agent_stage_exception",
                    level=logging.WARNING,
                    context={"stage": stage_name},
                )
                log_runtime_guard_event(
                    logger,
                    "stage_exception_captured",
                    scope="stage",
                    stage=stage_name,
                    exception_type=type(exc).__name__,
                    reason=StageFailureReason.STAGE_FAILURE.value,
                )
                result = StageResult(
                    stage_name=stage_name,
                    status=StageStatus.FAILED,
                    error=AGENT_EXECUTION_FAILURE_MESSAGE,
                    failure_reason=StageFailureReason.STAGE_FAILURE,
                    meta={"runtime_guard_event": "stage_exception_captured"},
                )
            elapsed_s = time.time() - t0
            if result.meta.get("runtime_guard_event") in {
                "stage_exception_captured",
                "stage_timeout",
            }:
                result.duration_s = round(
                    max(0.0, elapsed_s - stage_started_elapsed_s),
                    2,
                )
            stats.record_stage(result)
            all_tool_calls.extend(
                tc for tc in (result.meta.get("tool_calls_log") or [])
            )
            models_used.extend(result.meta.get("models_used", []))
            if progress_callback:
                progress_callback(stream_event(
                    "stage_done",
                    stage=agent.agent_name,
                    status=result.status.value,
                    duration=result.duration_s,
                ))

            # Cancellation wins over the post-stage timeout / degradation
            # gates below, so a run cancelled mid-stage terminates cleanly.
            if cancelled_check is not None and cancelled_check():
                logger.info("[Orchestrator] pipeline cancelled after stage '%s'", agent.agent_name)
                return self._build_cancelled_result(
                    stats, all_tool_calls, models_used, elapsed_s, ctx=ctx
                )

            if ctx.meta.get("response_mode") == "chat" and agent.agent_name == "decision":
                final_text = result.meta.get("raw_text")
                if isinstance(final_text, str) and final_text.strip():
                    ctx.set_data("final_response_text", final_text.strip())

            failure_reason = None
            if result.status == StageStatus.FAILED:
                failure_reason = normalize_stage_failure_reason(result.failure_reason)
                if failure_reason == StageFailureReason.TIMEOUT:
                    log_runtime_guard_event(
                        logger,
                        "stage_timeout",
                        scope="stage",
                        stage=stage_name,
                        limit_seconds=effective_stage_timeout_s,
                    )

            if timeout_s and elapsed_s >= timeout_s:
                if result.status == StageStatus.FAILED:
                    self._record_degraded_stage(ctx, stage_name, result)
                log_runtime_guard_event(
                    logger,
                    "run_timeout",
                    level=logging.ERROR,
                    scope="orchestrator",
                    phase="after_stage",
                    stage=stage_name,
                    elapsed_seconds=round(elapsed_s, 3),
                    limit_seconds=timeout_s,
                )
                last_completed_stage = next(
                    (
                        stage.stage_name
                        for stage in reversed(stats.stage_results)
                        if stage.status == StageStatus.COMPLETED
                    ),
                    None,
                )
                self._record_pipeline_termination(
                    ctx,
                    last_completed_stage=last_completed_stage,
                )
                if progress_callback:
                    progress_callback(stream_event(
                        "pipeline_timeout",
                        stage=agent.agent_name,
                        elapsed=round(elapsed_s, 2),
                        timeout=timeout_s,
                    ))
                self._apply_partition_fallback(ctx)
                return self._build_timeout_result(
                    stats,
                    all_tool_calls,
                    models_used,
                    elapsed_s,
                    timeout_s,
                    ctx=ctx,
                    parse_dashboard=parse_dashboard,
                )

            # Isolate eligible support-stage failures unless fail-fast is explicit.
            if result.status == StageStatus.FAILED:
                should_isolate = (
                    self.runtime_guard_policy.stage_failure_policy
                    == StageFailurePolicy.ISOLATE
                    and self._is_non_critical_stage(stage_name)
                )
                if not should_isolate:
                    log_runtime_guard_event(
                        logger,
                        "stage_failure_fail_fast",
                        level=logging.ERROR,
                        scope="stage",
                        stage=stage_name,
                        reason=failure_reason.value,
                        policy=self.runtime_guard_policy.stage_failure_policy.value,
                        action="stop",
                    )
                    return OrchestratorResult(
                        success=False,
                        error=f"Stage '{stage_name}' failed",
                        stats=stats,
                        total_tokens=stats.total_tokens,
                        tool_calls_log=all_tool_calls,
                        runtime_facts=build_agent_runtime_facts(ctx),
                    )
                else:
                    self._record_degraded_stage(ctx, stage_name, result)
                    log_runtime_guard_event(
                        logger,
                        "stage_failure_isolated",
                        scope="stage",
                        stage=stage_name,
                        reason=failure_reason.value,
                        policy=self.runtime_guard_policy.stage_failure_policy.value,
                        action="continue",
                    )

            index += 1

        # Assemble final output
        total_duration = round(time.time() - t0, 2)
        stats.total_duration_s = total_duration
        stats.models_used = list(dict.fromkeys(models_used))

        dashboard, content = self._resolve_final_output(ctx, parse_dashboard=parse_dashboard)

        model_str = ", ".join(dict.fromkeys(m for m in models_used if m))
        provider = stats.models_used[0] if stats.models_used else ""

        if parse_dashboard and dashboard is None:
            return OrchestratorResult(
                success=False,
                content=content,
                dashboard=None,
                tool_calls_log=all_tool_calls,
                total_steps=stats.total_stages,
                total_tokens=stats.total_tokens,
                provider=provider,
                model=model_str,
                error="Failed to parse dashboard JSON from agent response",
                stats=stats,
                runtime_facts=build_agent_runtime_facts(ctx),
            )

        return OrchestratorResult(
            success=bool(content),
            content=content,
            dashboard=dashboard,
            tool_calls_log=all_tool_calls,
            total_steps=stats.total_stages,
            total_tokens=stats.total_tokens,
            provider=provider,
            model=model_str,
            stats=stats,
            runtime_facts=build_agent_runtime_facts(ctx),
        )

    # -----------------------------------------------------------------
    # Agent chain construction
    # -----------------------------------------------------------------

    def _tool_registry_for_context(self, ctx: AgentContext) -> ToolRegistry:
        """Resolve a request-local Chat registry without mutating shared state."""
        market_context = ctx.meta.get("agent_chat_market_context")
        if ctx.meta.get("response_mode") != "chat" or market_context is None:
            return self.tool_registry
        return build_agent_chat_tool_registry(self.tool_registry, market_context)

    @staticmethod
    def _trim_agent_tool_names(agent: Any, tool_registry: ToolRegistry) -> None:
        """Keep a child agent's declared subset inside the request-local surface."""
        tool_names = getattr(agent, "tool_names", None)
        if tool_names is not None:
            agent.tool_names = [
                name for name in tool_names if tool_registry.get(name) is not None
            ]

    def _build_agent_chain(self, ctx: AgentContext) -> list:
        """Instantiate the ordered agent list based on ``self.mode``."""
        from src.agent.agents.technical_agent import TechnicalAgent
        from src.agent.agents.intel_agent import IntelAgent
        from src.agent.agents.decision_agent import DecisionAgent
        from src.agent.agents.risk_agent import RiskAgent

        self._skill_agent_names = set()

        tool_registry = self._tool_registry_for_context(ctx)
        common_kwargs = dict(
            tool_registry=tool_registry,
            llm_adapter=self.llm_adapter,
            skill_instructions=self.skill_instructions,
            technical_skill_policy=self.technical_skill_policy,
        )

        technical = self._prepare_agent(TechnicalAgent(**common_kwargs))
        intel = self._prepare_agent(IntelAgent(**common_kwargs))
        risk = self._prepare_agent(RiskAgent(**common_kwargs))
        decision = self._prepare_agent(DecisionAgent(**common_kwargs))
        if tool_registry is not self.tool_registry:
            for agent in (technical, intel, risk, decision):
                self._trim_agent_tool_names(agent, tool_registry)

        if self.mode == "quick":
            return [technical, decision]
        elif self.mode == "standard":
            return [technical, intel, decision]
        elif self.mode == "full":
            return [technical, intel, risk, decision]
        elif self.mode == "specialist":
            # Specialist agents are inserted lazily right before the decision
            # stage so the router can see the finished technical opinion.
            return [technical, intel, risk, decision]
        else:
            return [technical, intel, decision]

    def _build_specialist_agents(self, ctx: AgentContext) -> list:
        """Build specialist sub-agents based on requested skills.

        Uses the skill router to select applicable skills, then creates
        lightweight agent wrappers for each.
        """
        try:
            from src.agent.skills.router import SkillRouter
            tool_registry = self._tool_registry_for_context(ctx)
            common_kwargs = dict(
                tool_registry=tool_registry,
                llm_adapter=self.llm_adapter,
                skill_instructions=self.skill_instructions,
                technical_skill_policy=self.technical_skill_policy,
            )
            router = SkillRouter()
            selected = router.select_skills(ctx)
            if not selected:
                return []

            from src.agent.skills.skill_agent import SkillAgent
            agents = []
            for skill_id in selected[:3]:  # cap at 3 concurrent skills
                agent = self._prepare_agent(SkillAgent(
                    skill_id=skill_id,
                    **common_kwargs,
                ))
                if tool_registry is not self.tool_registry:
                    self._trim_agent_tool_names(agent, tool_registry)
                agents.append(agent)
            return agents
        except Exception as exc:  # broad-exception: fallback_recorded - Optional Chat specialists are safe-logged and skipped.
            log_safe_exception(
                logger,
                "[Orchestrator] failed to build skill agents",
                exc,
                error_code="agent_skill_build_failed",
                level=logging.WARNING,
            )
            return []

    def _build_skill_agents(self, ctx: AgentContext) -> list:
        """Compatibility wrapper for legacy imports."""
        return self._build_specialist_agents(ctx)

    def _build_strategy_agents(self, ctx: AgentContext) -> list:
        """Compatibility wrapper for legacy tests/imports."""
        return self._build_specialist_agents(ctx)

    # -----------------------------------------------------------------
    # Skill aggregation
    # -----------------------------------------------------------------

    def _aggregate_skill_opinions(self, ctx: AgentContext) -> None:
        """Run SkillAggregator to produce a consensus opinion.

        Merges individual skill-agent opinions into a single weighted
        consensus and stores it in context so the decision agent can use it.
        """
        try:
            from src.agent.skills.aggregator import SkillAggregator
            aggregator = SkillAggregator()
            consensus = aggregator.aggregate(ctx)
            if consensus:
                ctx.opinions.append(consensus)
                ctx.set_data("skill_consensus", {
                    "signal": consensus.signal,
                    "confidence": consensus.confidence,
                    "reasoning": consensus.reasoning,
                })
                logger.info(
                    "[Orchestrator] skill consensus: signal=%s confidence=%.2f",
                    consensus.signal, consensus.confidence,
                )
            else:
                logger.info("[Orchestrator] no skill opinions to aggregate")
        except Exception as exc:  # broad-exception: fallback_recorded - Skill aggregation is optional and failures are safely logged.
            log_safe_exception(
                logger,
                "[Orchestrator] skill aggregation failed",
                exc,
                error_code="agent_skill_aggregation_failed",
                level=logging.WARNING,
            )

    def _aggregate_strategy_opinions(self, ctx: AgentContext) -> None:
        """Compatibility wrapper for legacy tests/imports."""
        self._aggregate_skill_opinions(ctx)

    def _run_strategy_engine(self, ctx: AgentContext) -> None:
        """Run the full skill pipeline via StrategyEngine and update ctx.

        The engine is the single authoritative owner of strategy_synthesis:
        it partitions valid/invalid skill opinions, moves invalid ones to
        ``ctx.meta["invalid_opinions"]`` (Diagnostics only), and rebuilds
        ``ctx.opinions`` as non-skill evidence + valid skills + consensus.
        """
        result = self.strategy_engine.process(ctx.opinions)

        ctx.meta["invalid_opinions"] = list(result.invalid_records)
        ctx.opinions = list(result.non_skill_opinions) + list(result.valid_skill_opinions)
        if result.consensus_opinion is not None:
            ctx.opinions.append(result.consensus_opinion)

        if result.skill_consensus_data is not None:
            ctx.set_data("skill_consensus", result.skill_consensus_data)

        if result.status == StrategyResultStatus.CONSENSUS:
            logger.info(
                "[Orchestrator] strategy engine: signal=%s confidence=%.2f",
                result.consensus_opinion.signal,
                result.consensus_opinion.confidence,
            )
        elif result.status == StrategyResultStatus.NO_CONSENSUS:
            logger.info(
                "[Orchestrator] strategy engine: NO_CONSENSUS invalid_count=%d",
                result.invalid_count,
            )
        else:
            logger.info("[Orchestrator] strategy engine: NO_SKILLS")

    def _apply_partition_fallback(self, ctx: AgentContext) -> None:
        """Partition skill opinions on timeout/budget-skip early-exit paths.

        Does not aggregate — only preserves invalid diagnostics in
        ``ctx.meta["invalid_opinions"]`` before the pipeline bails out.
        Idempotent: skips if the engine already ran fully (consensus present).
        """
        if ctx.get_data("skill_consensus") is not None:
            return

        partition = self.strategy_engine.partition_only(ctx.opinions)
        ctx.opinions = list(partition.non_skill_opinions) + list(partition.valid_skill_opinions)
        invalid_bucket = ctx.meta.get("invalid_opinions")
        if not isinstance(invalid_bucket, list):
            invalid_bucket = []
        invalid_bucket.extend(partition.invalid_records)
        ctx.meta["invalid_opinions"] = invalid_bucket

    def _collect_strategy_synthesis(
        self,
        ctx: AgentContext,
        dashboard_block: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Return the deterministic strategy_synthesis, never the LLM-written one."""
        consensus_data = ctx.get_data("skill_consensus")
        if isinstance(consensus_data, dict):
            synthesis = consensus_data.get("strategy_synthesis")
            if isinstance(synthesis, dict) and synthesis:
                return synthesis
            raw_data = consensus_data.get("raw_data")
            if isinstance(raw_data, dict):
                synthesis = raw_data.get("strategy_synthesis")
                if isinstance(synthesis, dict) and synthesis:
                    return synthesis

        for opinion in reversed(ctx.opinions):
            if getattr(opinion, "agent_name", "") != "skill_consensus":
                continue
            raw_data = opinion.raw_data if isinstance(opinion.raw_data, dict) else {}
            synthesis = raw_data.get("strategy_synthesis")
            if isinstance(synthesis, dict) and synthesis:
                return synthesis
        return None

    def _prepare_decision_context(self, ctx: AgentContext) -> None:
        """Populate low-sensitivity summaries consumed by DecisionAgent."""
        ctx.meta["agent_disagreement_summary"] = build_agent_disagreement_summary(
            ctx,
            risk_override_enabled=getattr(self.config, "agent_risk_override", True),
        )

    def _record_degraded_stage(
        self,
        ctx: AgentContext,
        agent_name: str,
        result: StageResult,
    ) -> None:
        """Record a low-sensitivity degraded stage marker for downstream synthesis."""
        if result.status != StageStatus.FAILED:
            raise ValueError("degraded stage markers are only produced for failed stages")

        degraded_stages = ctx.meta.setdefault("degraded_stages", [])
        if not isinstance(degraded_stages, list):
            degraded_stages = []
            ctx.meta["degraded_stages"] = degraded_stages
        degraded_stages.append({
            "stage_name": agent_name,
            "status": result.status.value,
            "non_critical": self._is_non_critical_stage(agent_name),
        })
        self._record_degraded_event(
            ctx,
            stage=agent_name,
            reason=normalize_stage_failure_reason(result.failure_reason),
            boundary=DegradationBoundary.DURING_STAGE,
        )

    @staticmethod
    def _record_degraded_event(
        ctx: AgentContext,
        *,
        stage: str,
        reason: Any,
        boundary: DegradationBoundary,
    ) -> None:
        """Record one deduplicated fact for an incomplete stage."""
        normalized = DegradedEvent(
            stage=stage,
            reason=reason,
            boundary=boundary,
        )
        event = {
            "stage": normalized.stage,
            "reason": normalized.reason.value,
            "boundary": normalized.boundary.value,
        }
        events = ctx.meta.setdefault("degraded_events", [])
        if not isinstance(events, list):
            events = []
            ctx.meta["degraded_events"] = events
        if event not in events:
            events.append(event)

    @staticmethod
    def _record_pipeline_termination(
        ctx: AgentContext,
        *,
        last_completed_stage: Optional[str],
    ) -> None:
        """Record a pipeline timeout without attributing it to a stage."""
        termination = PipelineTerminationFact(
            reason=StageFailureReason.TIMEOUT,
            last_completed_stage=last_completed_stage,
        )
        ctx.meta["pipeline_termination"] = {
            "reason": termination.reason.value,
            "last_completed_stage": termination.last_completed_stage,
        }

    def _is_non_critical_stage(self, agent_name: str) -> bool:
        """Return whether a failed stage should degrade instead of aborting."""
        normalized_name = str(agent_name or "").strip()
        return (
            normalized_name in NON_CRITICAL_BASE_STAGES
            or normalized_name in getattr(self, "_skill_agent_names", set())
        )
