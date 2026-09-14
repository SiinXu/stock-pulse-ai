# -*- coding: utf-8 -*-
"""Fail-soft evolution episode persist for orchestrator pipeline runs (#1120)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

from src.agent.protocols import AgentContext
from src.utils.sanitize import log_safe_exception

if TYPE_CHECKING:
    from src.agent.orchestrator import OrchestratorResult

logger = logging.getLogger("src.agent.orchestrator")


class _PipelineEpisodeMethods:
    """Source container rebound onto ``AgentOrchestrator`` after pipeline methods."""

    def _execute_pipeline(
        self,
        ctx: AgentContext,
        parse_dashboard: bool = True,
        progress_callback: Optional[Callable] = None,
        cancelled_check: Optional[Callable[[], bool]] = None,
        timeout_seconds: Optional[float] = None,
    ) -> OrchestratorResult:
        """Run the agent pipeline according to ``self.mode`` and fail-soft persist."""
        from datetime import datetime, timezone

        started_at = datetime.now(timezone.utc)
        result = None
        try:
            result = self._run_pipeline_stages(
                ctx,
                parse_dashboard=parse_dashboard,
                progress_callback=progress_callback,
                cancelled_check=cancelled_check,
                timeout_seconds=timeout_seconds,
            )
            return result
        finally:
            self._try_record_pipeline_episode(ctx, result, started_at)

    def _try_record_pipeline_episode(
        self,
        ctx: AgentContext,
        result: Any,
        started_at: Any,
    ) -> None:
        """Fail-soft evolution episode write for dashboard/Chat full_repipeline runs."""
        if result is None:
            return
        config = getattr(self, "config", None)
        try:
            from src.services.agent_episode_service import (
                is_agent_episode_log_enabled,
                try_record_agent_episode_from_result,
            )

            if not is_agent_episode_log_enabled(config):
                return
            meta = getattr(ctx, "meta", None)
            decision = meta.get("router_decision") if isinstance(meta, dict) else None
            if isinstance(decision, dict):
                bag = dict(getattr(result, "planning_metadata", None) or {})
                bag["router_decision"] = dict(decision)
                result.planning_metadata = bag
            context: Dict[str, Any] = {}
            stock_code = getattr(ctx, "stock_code", None)
            if isinstance(stock_code, str) and stock_code.strip():
                context["stock_code"] = stock_code.strip()
            if isinstance(meta, dict):
                run_id = meta.get("run_id") or meta.get("task_id")
                if isinstance(run_id, str) and run_id.strip():
                    context["run_id"] = run_id.strip()
                market = meta.get("market")
                if isinstance(market, str) and market.strip():
                    context["market"] = market.strip()
            try_record_agent_episode_from_result(
                result=result,
                config=config,
                mode=str(getattr(self, "mode", None) or "multi"),
                context=context,
                started_at=started_at,
            )
        except Exception as exc:  # broad-exception: fallback_recorded - episode logging cannot mask pipeline result
            log_safe_exception(
                logger,
                "agent_episode_pipeline_finalizer_failed",
                exc,
                error_code="agent_episode_pipeline_finalizer_failed",
            )
