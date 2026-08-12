# -*- coding: utf-8 -*-
"""LLM usage persistence and reporting methods."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, case, desc, func, select

from src.storage import (
    LLMUsage,
    _LLM_USAGE_DROPPED_FREE_TEXT_COLUMNS,
    _LLM_USAGE_TELEMETRY_COLUMN_SQL,
)


class _UsageMethods:
    """Source container rebound onto ``DatabaseManager`` by the facade."""

    def record_llm_usage(
        self,
        call_type: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        stock_code: Optional[str] = None,
        **telemetry: Any,
    ) -> None:
        """Append one LLM call record to llm_usage."""
        row_values: Dict[str, Any] = {
            "call_type": call_type,
            "model": model or "unknown",
            "stock_code": stock_code,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }
        for column in _LLM_USAGE_TELEMETRY_COLUMN_SQL:
            row_values[column] = (
                None if column in _LLM_USAGE_DROPPED_FREE_TEXT_COLUMNS else telemetry.get(column)
            )
        row = LLMUsage(**row_values)
        with self.session_scope() as session:
            session.add(row)

    def get_llm_usage_summary(self, from_dt: datetime, to_dt: datetime) -> Dict[str, Any]:
        """Return aggregated token and cost usage between from_dt and to_dt."""
        with self.session_scope() as session:
            base_filter = and_(LLMUsage.called_at >= from_dt, LLMUsage.called_at <= to_dt)
            totals = session.execute(
                select(
                    func.count(LLMUsage.id).label("calls"),
                    func.coalesce(func.sum(LLMUsage.prompt_tokens), 0).label("prompt_tokens"),
                    func.coalesce(func.sum(LLMUsage.completion_tokens), 0).label("completion_tokens"),
                    func.coalesce(func.sum(LLMUsage.total_tokens), 0).label("tokens"),
                    func.sum(LLMUsage.estimated_cost_usd).label("cost_usd"),
                    func.coalesce(func.sum(case((LLMUsage.estimated_cost_usd.is_not(None), 1), else_=0)), 0).label("priced_calls"),
                    func.coalesce(func.sum(case((LLMUsage.cost_status == "unpriced", 1), else_=0)), 0).label("unpriced_calls"),
                    func.coalesce(func.sum(case((LLMUsage.route_outcome == "primary_success", 1), else_=0)), 0).label("route_primary"),
                    func.coalesce(func.sum(case((LLMUsage.route_outcome == "fallback_success", 1), else_=0)), 0).label("route_fallback"),
                    func.coalesce(func.sum(case((LLMUsage.route_outcome == "failed", 1), else_=0)), 0).label("route_failed"),
                ).where(base_filter)
            ).one()
            by_type_rows = session.execute(
                select(
                    LLMUsage.call_type,
                    func.count(LLMUsage.id).label("calls"),
                    func.coalesce(func.sum(LLMUsage.prompt_tokens), 0).label("prompt_tokens"),
                    func.coalesce(func.sum(LLMUsage.completion_tokens), 0).label("completion_tokens"),
                    func.coalesce(func.sum(LLMUsage.total_tokens), 0).label("tokens"),
                    func.sum(LLMUsage.estimated_cost_usd).label("cost_usd"),
                ).where(base_filter).group_by(LLMUsage.call_type).order_by(desc(func.sum(LLMUsage.total_tokens)))
            ).all()
            by_model_rows = session.execute(
                select(
                    LLMUsage.model,
                    func.count(LLMUsage.id).label("calls"),
                    func.coalesce(func.sum(LLMUsage.prompt_tokens), 0).label("prompt_tokens"),
                    func.coalesce(func.sum(LLMUsage.completion_tokens), 0).label("completion_tokens"),
                    func.coalesce(func.sum(LLMUsage.total_tokens), 0).label("tokens"),
                    func.coalesce(func.max(LLMUsage.total_tokens), 0).label("max_total_tokens"),
                    func.sum(LLMUsage.estimated_cost_usd).label("cost_usd"),
                ).where(base_filter).group_by(LLMUsage.model).order_by(desc(func.sum(LLMUsage.total_tokens)))
            ).all()
            by_stage_rows = session.execute(
                select(
                    LLMUsage.stage,
                    func.count(LLMUsage.id).label("calls"),
                    func.coalesce(func.sum(LLMUsage.prompt_tokens), 0).label("prompt_tokens"),
                    func.coalesce(func.sum(LLMUsage.completion_tokens), 0).label("completion_tokens"),
                    func.coalesce(func.sum(LLMUsage.total_tokens), 0).label("tokens"),
                    func.sum(LLMUsage.estimated_cost_usd).label("cost_usd"),
                    func.coalesce(func.sum(case((LLMUsage.call_success == 1, 1), else_=0)), 0).label("success_calls"),
                    func.coalesce(func.avg(LLMUsage.latency_ms), 0).label("avg_latency_ms"),
                ).where(and_(base_filter, LLMUsage.stage.is_not(None))).group_by(LLMUsage.stage).order_by(desc(func.sum(LLMUsage.total_tokens)))
            ).all()
            by_mode_rows = session.execute(
                select(
                    LLMUsage.agent_mode,
                    func.count(LLMUsage.id).label("calls"),
                    func.coalesce(func.sum(LLMUsage.prompt_tokens), 0).label("prompt_tokens"),
                    func.coalesce(func.sum(LLMUsage.completion_tokens), 0).label("completion_tokens"),
                    func.coalesce(func.sum(LLMUsage.total_tokens), 0).label("tokens"),
                    func.sum(LLMUsage.estimated_cost_usd).label("cost_usd"),
                ).where(and_(base_filter, LLMUsage.agent_mode.is_not(None))).group_by(LLMUsage.agent_mode).order_by(desc(func.sum(LLMUsage.total_tokens)))
            ).all()

        route_primary = int(totals.route_primary or 0)
        route_fallback = int(totals.route_fallback or 0)
        route_failed = int(totals.route_failed or 0)
        routed = route_primary + route_fallback + route_failed
        success_routed = route_primary + route_fallback
        return {
            "total_calls": totals.calls,
            "total_prompt_tokens": totals.prompt_tokens,
            "total_completion_tokens": totals.completion_tokens,
            "total_tokens": totals.tokens,
            "total_estimated_cost_usd": float(totals.cost_usd) if totals.cost_usd is not None else None,
            "priced_calls": int(totals.priced_calls or 0),
            "unpriced_calls": int(totals.unpriced_calls or 0),
            "routing_primary_success": route_primary,
            "routing_fallback_success": route_fallback,
            "routing_failed": route_failed,
            "routing_success_rate": (success_routed / routed) if routed else None,
            "routing_fallback_rate": (route_fallback / success_routed) if success_routed else None,
            "by_call_type": [
                {
                    "call_type": r.call_type, "calls": r.calls, "prompt_tokens": r.prompt_tokens,
                    "completion_tokens": r.completion_tokens, "total_tokens": r.tokens,
                    "estimated_cost_usd": float(r.cost_usd) if r.cost_usd is not None else None,
                }
                for r in by_type_rows
            ],
            "by_model": [
                {
                    "model": r.model, "calls": r.calls, "prompt_tokens": r.prompt_tokens,
                    "completion_tokens": r.completion_tokens, "total_tokens": r.tokens,
                    "max_total_tokens": r.max_total_tokens,
                    "estimated_cost_usd": float(r.cost_usd) if r.cost_usd is not None else None,
                }
                for r in by_model_rows
            ],
            "by_stage": [
                {
                    "stage": r.stage or "unknown", "calls": r.calls, "prompt_tokens": r.prompt_tokens,
                    "completion_tokens": r.completion_tokens, "total_tokens": r.tokens,
                    "estimated_cost_usd": float(r.cost_usd) if r.cost_usd is not None else None,
                    "success_calls": int(r.success_calls or 0), "avg_latency_ms": int(r.avg_latency_ms or 0),
                }
                for r in by_stage_rows
            ],
            "by_agent_mode": [
                {
                    "agent_mode": r.agent_mode or "unknown", "calls": r.calls, "prompt_tokens": r.prompt_tokens,
                    "completion_tokens": r.completion_tokens, "total_tokens": r.tokens,
                    "estimated_cost_usd": float(r.cost_usd) if r.cost_usd is not None else None,
                }
                for r in by_mode_rows
            ],
        }

    def get_llm_usage_records(self, from_dt: datetime, to_dt: datetime, limit: int = 50) -> List[Dict[str, Any]]:
        """Return recent LLM usage audit rows between from_dt and to_dt."""
        normalized_limit = max(1, min(int(limit or 50), 200))
        with self.session_scope() as session:
            rows = session.execute(
                select(
                    LLMUsage.id, LLMUsage.call_type, LLMUsage.model, LLMUsage.stock_code,
                    LLMUsage.prompt_tokens, LLMUsage.completion_tokens, LLMUsage.total_tokens,
                    LLMUsage.run_id, LLMUsage.stage, LLMUsage.agent_mode,
                    LLMUsage.estimated_cost_usd, LLMUsage.cost_status, LLMUsage.route_outcome,
                    LLMUsage.route_attempt, LLMUsage.primary_model, LLMUsage.latency_ms,
                    LLMUsage.call_success, LLMUsage.called_at,
                )
                .where(and_(LLMUsage.called_at >= from_dt, LLMUsage.called_at <= to_dt))
                .order_by(desc(LLMUsage.called_at), desc(LLMUsage.id))
                .limit(normalized_limit)
            ).all()
        return [
            {
                "id": r.id, "call_type": r.call_type, "model": r.model, "stock_code": r.stock_code,
                "prompt_tokens": r.prompt_tokens, "completion_tokens": r.completion_tokens,
                "total_tokens": r.total_tokens, "run_id": r.run_id, "stage": r.stage,
                "agent_mode": r.agent_mode,
                "estimated_cost_usd": float(r.estimated_cost_usd) if r.estimated_cost_usd is not None else None,
                "cost_status": r.cost_status, "route_outcome": r.route_outcome,
                "route_attempt": r.route_attempt, "primary_model": r.primary_model,
                "latency_ms": r.latency_ms,
                "call_success": bool(r.call_success) if r.call_success is not None else None,
                "called_at": r.called_at,
            }
            for r in rows
        ]
