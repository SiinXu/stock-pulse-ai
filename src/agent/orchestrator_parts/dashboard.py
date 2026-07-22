# -*- coding: utf-8 -*-
"""Context, dashboard finalization, and risk-overlay methods."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from src.agent.dashboard_payload import sanitize_agent_dashboard_payload
from src.agent.protocols import AgentContext, normalize_decision_signal
from src.agent.risk_override import (
    RiskOverrideApplication,
    build_risk_override_application,
    build_risk_override_plan,
)
from src.agent.runner import parse_dashboard_json
from src.report_language import normalize_report_language

if TYPE_CHECKING:
    from src.agent.orchestrator import (
        _adjust_operation_advice,
        _adjust_sentiment_score,
        _coerce_level_value,
        _confidence_label,
        _default_position_advice,
        _default_position_size,
        _estimate_sentiment_score,
        _extract_latest_news_title,
        _extract_stock_code,
        _first_non_empty_text,
        _level_values_equal,
        _normalize_operation_advice_value,
        _pick_first_level,
        _post_risk_position_advice,
        _signal_to_operation,
        _signal_to_signal_type,
        _truncate_text,
    )

logger = logging.getLogger("src.agent.orchestrator")
_PREPARED_DECISION_TYPE_INSERTED = "_prepared_dashboard_decision_type_inserted"


class _DashboardMethods:
    """Source container rebound onto ``AgentOrchestrator`` by the facade."""

    # -----------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------

    def _build_context(self, task: str, context: Optional[Dict[str, Any]] = None) -> AgentContext:
        """Seed an ``AgentContext`` from the user request."""
        ctx = AgentContext(query=task)

        if context:
            ctx.stock_code = context.get("stock_code", "")
            ctx.stock_name = context.get("stock_name", "")
            requested_skills = context.get("skills")
            if requested_skills is None:
                requested_skills = context.get("strategies", [])
            ctx.meta["skills_requested"] = requested_skills or []
            ctx.meta["strategies_requested"] = requested_skills or []
            ctx.meta["report_language"] = normalize_report_language(context.get("report_language", "zh"))
            if context.get("market_phase_context"):
                ctx.meta["market_phase_context"] = context["market_phase_context"]
            daily_market_context = context.get("daily_market_context")
            if isinstance(daily_market_context, dict) and daily_market_context:
                ctx.meta["daily_market_context"] = dict(daily_market_context)
            market_structure_context = context.get("market_structure_context")
            if isinstance(market_structure_context, dict) and market_structure_context:
                ctx.meta["market_structure_context"] = dict(market_structure_context)
            analysis_context_pack_summary = context.get("analysis_context_pack_summary")
            if isinstance(analysis_context_pack_summary, str) and analysis_context_pack_summary:
                ctx.meta["analysis_context_pack_summary"] = analysis_context_pack_summary

            # Pre-populate data fields that the caller already has
            for data_key in ("realtime_quote", "daily_history", "chip_distribution",
                             "trend_result", "news_context"):
                if context.get(data_key):
                    ctx.set_data(data_key, context[data_key])

        # Try to extract stock code from the query text
        if not ctx.stock_code:
            ctx.stock_code = _extract_stock_code(task)

        if "report_language" not in ctx.meta:
            ctx.meta["report_language"] = "zh"

        return ctx

    @staticmethod
    def _fallback_summary(ctx: AgentContext) -> str:
        """Build a plaintext summary when dashboard JSON is unavailable."""
        lines = [f"# Analysis Summary: {ctx.stock_code} ({ctx.stock_name})", ""]
        for op in ctx.opinions:
            lines.append(f"## {op.agent_name}")
            lines.append(f"Signal: {op.signal} (confidence: {op.confidence:.0%})")
            lines.append(op.reasoning)
            lines.append("")
        if ctx.risk_flags:
            lines.append("## Risk Flags")
            for rf in ctx.risk_flags:
                lines.append(f"- [{rf['severity']}] {rf['description']}")
        return "\n".join(lines)

    def _resolve_final_output(
        self,
        ctx: AgentContext,
        *,
        parse_dashboard: bool,
    ) -> tuple[Optional[Dict[str, Any]], str]:
        """Resolve the best available final output from context.

        For dashboard mode, prefer:
        1. Parsed/normalized decision dashboard
        2. Parsed raw dashboard text
        3. Synthesised dashboard from completed opinions
        4. Plaintext fallback summary
        """
        final_dashboard = ctx.get_data("final_dashboard")
        final_raw = ctx.get_data("final_dashboard_raw")
        final_text = ctx.get_data("final_response_text")
        chat_mode = ctx.meta.get("response_mode") == "chat"

        if parse_dashboard:
            dashboard = self._resolve_dashboard_payload(ctx, final_dashboard, final_raw)
            if dashboard is not None:
                return dashboard, json.dumps(dashboard, ensure_ascii=False, indent=2)
            if ctx.opinions:
                return None, self._fallback_summary(ctx)
            return None, ""

        if chat_mode and isinstance(final_text, str) and final_text.strip():
            return None, final_text.strip()
        if isinstance(final_raw, str) and final_raw.strip():
            return None, final_raw
        if isinstance(final_dashboard, dict):
            dashboard = self._finalize_dashboard_payload(final_dashboard, ctx)
            if dashboard is not None:
                return dashboard, json.dumps(dashboard, ensure_ascii=False, indent=2)
        if ctx.opinions:
            return None, self._fallback_summary(ctx)
        return None, ""

    def _resolve_dashboard_payload(
        self,
        ctx: AgentContext,
        final_dashboard: Any,
        final_raw: Any,
    ) -> Optional[Dict[str, Any]]:
        """Resolve one dashboard, apply risk once, then derive signal fields."""
        candidate: Optional[Dict[str, Any]] = None

        if isinstance(final_dashboard, dict):
            candidate = final_dashboard
        elif isinstance(final_raw, str) and final_raw.strip():
            parsed = parse_dashboard_json(final_raw)
            if isinstance(parsed, dict):
                candidate = parsed

        prepared = self._prepare_dashboard_payload(candidate or {}, ctx)
        if prepared is None:
            return None

        ctx.set_data("final_dashboard", prepared)
        self._apply_risk_override(ctx)
        post_risk = ctx.get_data("final_dashboard")
        if not isinstance(post_risk, dict):
            return None

        dashboard = self._finalize_dashboard_payload(post_risk, ctx)
        if dashboard is None:
            return None
        ctx.set_data("final_dashboard", dashboard)
        return dashboard

    def _prepare_dashboard_payload(
        self,
        payload: Optional[Dict[str, Any]],
        ctx: AgentContext,
    ) -> Optional[Dict[str, Any]]:
        """Select a safe payload and canonical signal without deriving advice."""
        prepared = sanitize_agent_dashboard_payload(dict(payload or {}))
        meaningful_data_keys = (
            "realtime_quote",
            "daily_history",
            "chip_distribution",
            "trend_result",
            "news_context",
            "intel_opinion",
            "fundamental_context",
        )
        has_meaningful_context = any(
            ctx.get_data(key) is not None for key in meaningful_data_keys
        )
        if not prepared and not ctx.opinions and not has_meaningful_context:
            return None

        base_opinion = self._select_base_opinion(ctx)
        ctx.meta[_PREPARED_DECISION_TYPE_INSERTED] = "decision_type" not in prepared
        prepared["decision_type"] = normalize_decision_signal(
            prepared.get("decision_type")
            or (base_opinion.signal if base_opinion else "hold")
        )
        return prepared

    def _finalize_dashboard_payload(
        self,
        payload: Optional[Dict[str, Any]],
        ctx: AgentContext,
    ) -> Optional[Dict[str, Any]]:
        """Derive the downstream dashboard shape from the post-risk signal."""
        payload = sanitize_agent_dashboard_payload(dict(payload or {}))
        if ctx.meta.pop(_PREPARED_DECISION_TYPE_INSERTED, False):
            payload.pop("decision_type", None)
        meaningful_data_keys = (
            "realtime_quote",
            "daily_history",
            "chip_distribution",
            "trend_result",
            "news_context",
            "intel_opinion",
            "fundamental_context",
        )
        has_meaningful_context = any(ctx.get_data(key) is not None for key in meaningful_data_keys)
        if not payload and not ctx.opinions and not has_meaningful_context:
            return None

        base_opinion = self._select_base_opinion(ctx)
        application = ctx.meta.get("risk_override_application")
        risk_applied = isinstance(application, RiskOverrideApplication) and application.applied
        decision_type = (
            application.post_risk_signal.value
            if risk_applied
            else normalize_decision_signal(
                payload.get("decision_type")
                or (base_opinion.signal if base_opinion else "hold")
            )
        )
        confidence = float(base_opinion.confidence if base_opinion is not None else 0.5)
        sentiment_score = payload.get("sentiment_score")
        try:
            sentiment_score = int(sentiment_score)
        except (TypeError, ValueError):
            sentiment_score = _estimate_sentiment_score(decision_type, confidence)
        if risk_applied:
            sentiment_score = _adjust_sentiment_score(sentiment_score, decision_type)

        dashboard_block = payload.get("dashboard")
        if not isinstance(dashboard_block, dict):
            dashboard_block = {}
        else:
            dashboard_block = dict(dashboard_block)
            # Strip any LLM-written strategy_synthesis; StrategyEngine is the sole writer.
            dashboard_block.pop("strategy_synthesis", None)

        core = dashboard_block.get("core_conclusion")
        if not isinstance(core, dict):
            core = {}
        else:
            core = dict(core)

        intelligence = dashboard_block.get("intelligence")
        if not isinstance(intelligence, dict):
            intelligence = {}
        else:
            intelligence = dict(intelligence)

        battle = dashboard_block.get("battle_plan")
        if not isinstance(battle, dict):
            battle = {}
        else:
            battle = dict(battle)

        analysis_summary = _first_non_empty_text(
            payload.get("analysis_summary"),
            core.get("one_sentence"),
            getattr(base_opinion, "reasoning", ""),
        )
        if not analysis_summary:
            analysis_summary = f"多 Agent 未生成完整仪表盘，当前按{_signal_to_operation(decision_type)}处理。"
        if risk_applied:
            transition_prefix = (
                f"[风控下调: {application.from_signal.value} -> "
                f"{application.post_risk_signal.value}]"
            )
            if not analysis_summary.startswith(transition_prefix):
                analysis_summary = f"{transition_prefix} {analysis_summary}"
        analysis_summary = _truncate_text(analysis_summary, 220)

        trend_prediction = _first_non_empty_text(
            payload.get("trend_prediction"),
            (getattr(base_opinion, "raw_data", {}) or {}).get("trend_summary")
            if base_opinion is not None else "",
        )
        if not trend_prediction:
            technical = self._latest_opinion(ctx, {"technical"})
            tech_raw = technical.raw_data if technical and isinstance(technical.raw_data, dict) else {}
            ma_alignment = tech_raw.get("ma_alignment")
            trend_score = tech_raw.get("trend_score")
            if ma_alignment or trend_score is not None:
                trend_prediction = f"技术面{ma_alignment or 'neutral'}，趋势评分 {trend_score if trend_score is not None else 'N/A'}"
            else:
                trend_prediction = "待结合更多阶段结果确认"

        operation_advice_raw = payload.get("operation_advice")
        if risk_applied:
            pre_risk_advice = _normalize_operation_advice_value(
                operation_advice_raw,
                application.from_signal.value,
            )
            operation_advice = _adjust_operation_advice(
                pre_risk_advice,
                decision_type,
            )
        else:
            operation_advice = _normalize_operation_advice_value(
                operation_advice_raw,
                decision_type,
            )

        existing_position = core.get("position_advice")
        if risk_applied:
            position_advice = _post_risk_position_advice(decision_type)
        else:
            position_advice = (
                dict(existing_position)
                if isinstance(existing_position, dict)
                else {}
            )
            if isinstance(operation_advice_raw, dict):
                no_position = _first_non_empty_text(
                    operation_advice_raw.get("no_position"),
                    operation_advice_raw.get("empty_position"),
                )
                has_position = _first_non_empty_text(
                    operation_advice_raw.get("has_position"),
                    operation_advice_raw.get("holding_position"),
                )
                if no_position and "no_position" not in position_advice:
                    position_advice["no_position"] = no_position
                if has_position and "has_position" not in position_advice:
                    position_advice["has_position"] = has_position
            defaults = _default_position_advice(decision_type)
            position_advice.setdefault("no_position", defaults["no_position"])
            position_advice.setdefault("has_position", defaults["has_position"])

        key_levels = self._collect_key_levels(ctx, payload, dashboard_block)
        sniper = battle.get("sniper_points")
        if not isinstance(sniper, dict):
            sniper = {}
        else:
            sniper = dict(sniper)

        ideal_buy = _pick_first_level(
            sniper.get("ideal_buy"),
            key_levels.get("ideal_buy_if_valuation_improves"),
            key_levels.get("ideal_buy"),
            key_levels.get("support"),
            key_levels.get("immediate_support"),
        )
        sniper["ideal_buy"] = ideal_buy if ideal_buy is not None else "N/A"

        secondary_buy = _coerce_level_value(sniper.get("secondary_buy"))
        if secondary_buy is None:
            secondary_buy = _pick_first_level(
                key_levels.get("secondary_buy"),
                key_levels.get("support"),
                key_levels.get("immediate_support"),
            )
        if _level_values_equal(secondary_buy, sniper.get("ideal_buy")):
            secondary_buy = None
        sniper["secondary_buy"] = secondary_buy if secondary_buy is not None else "N/A"
        sniper.setdefault(
            "stop_loss",
            key_levels.get("stop_loss")
            or key_levels.get("strong_support_stop_loss")
            or "待补充",
        )
        sniper.setdefault(
            "take_profit",
            key_levels.get("take_profit")
            or key_levels.get("next_breakout_target")
            or key_levels.get("current_resistance")
            or key_levels.get("resistance")
            or "N/A",
        )

        risk_alerts = self._collect_risk_alerts(ctx, intelligence)
        positive_catalysts = self._collect_positive_catalysts(ctx, intelligence)
        latest_news = _extract_latest_news_title(intelligence)

        if not intelligence.get("risk_alerts"):
            intelligence["risk_alerts"] = risk_alerts
        if positive_catalysts and not intelligence.get("positive_catalysts"):
            intelligence["positive_catalysts"] = positive_catalysts
        if latest_news and not intelligence.get("latest_news"):
            intelligence["latest_news"] = latest_news

        one_sentence = _first_non_empty_text(
            core.get("one_sentence"),
            analysis_summary,
        )
        if risk_applied and not one_sentence.startswith(transition_prefix):
            one_sentence = f"{transition_prefix} {one_sentence}"
        core["one_sentence"] = _truncate_text(one_sentence, 60)
        if not core.get("time_sensitivity"):
            core["time_sensitivity"] = "本周内"
        if risk_applied:
            core["signal_type"] = {
                "hold": "🟡持有观望",
                "sell": "🔴卖出信号",
            }.get(decision_type, _signal_to_signal_type(decision_type))
        elif not core.get("signal_type"):
            core["signal_type"] = _signal_to_signal_type(decision_type)
        core["position_advice"] = position_advice

        battle["sniper_points"] = sniper
        if "action_checklist" not in battle:
            battle["action_checklist"] = []
        position_strategy = battle.get("position_strategy")
        if risk_applied:
            position_strategy = (
                dict(position_strategy)
                if isinstance(position_strategy, dict)
                else {}
            )
            position_strategy["suggested_position"] = _default_position_size(decision_type)
            position_strategy["entry_plan"] = position_advice["no_position"]
            position_strategy.setdefault(
                "risk_control",
                f"止损参考 {sniper.get('stop_loss', '待补充')}",
            )
            battle["position_strategy"] = position_strategy
        elif not isinstance(position_strategy, dict) or not position_strategy:
            battle["position_strategy"] = {
                "suggested_position": _default_position_size(decision_type),
                "entry_plan": position_advice["no_position"],
                "risk_control": f"止损参考 {sniper.get('stop_loss', '待补充')}",
            }

        data_perspective = dashboard_block.get("data_perspective")
        if not isinstance(data_perspective, dict):
            data_perspective = {}
        if not data_perspective:
            built_data_perspective = self._build_data_perspective(ctx, key_levels)
            if built_data_perspective:
                data_perspective = built_data_perspective
        if data_perspective:
            dashboard_block["data_perspective"] = data_perspective

        strategy_synthesis = self._collect_strategy_synthesis(ctx, dashboard_block)
        if strategy_synthesis:
            dashboard_block["strategy_synthesis"] = strategy_synthesis

        dashboard_block["core_conclusion"] = core
        dashboard_block["intelligence"] = intelligence
        dashboard_block["battle_plan"] = battle

        key_points = payload.get("key_points")
        if not isinstance(key_points, list) or not key_points:
            key_points = [
                _truncate_text(op.reasoning, 120)
                for op in ctx.opinions
                if isinstance(op.reasoning, str) and op.reasoning.strip()
            ][:5]

        risk_warning = _first_non_empty_text(
            payload.get("risk_warning"),
            "；".join(risk_alerts[:3]),
            getattr(self._latest_opinion(ctx, {"risk"}), "reasoning", ""),
        )
        if not risk_warning:
            risk_warning = "暂无额外风险提示"
        if risk_applied:
            risk_opinion = self._latest_opinion(ctx, {"risk"})
            risk_raw = (
                risk_opinion.raw_data
                if risk_opinion and isinstance(risk_opinion.raw_data, dict)
                else {}
            )
            risk_warning = self._merge_risk_warning(
                risk_warning,
                risk_raw,
                ctx.risk_flags,
                decision_type,
            )

        payload["stock_name"] = _first_non_empty_text(payload.get("stock_name"), ctx.stock_name, ctx.stock_code)
        payload["sentiment_score"] = sentiment_score
        payload["trend_prediction"] = trend_prediction
        payload["operation_advice"] = operation_advice
        payload["decision_type"] = decision_type
        payload["confidence_level"] = _confidence_label(confidence)
        payload["analysis_summary"] = analysis_summary
        payload["key_points"] = key_points
        payload["risk_warning"] = risk_warning
        payload["dashboard"] = dashboard_block
        if risk_applied:
            for opinion in reversed(ctx.opinions):
                if opinion.agent_name == "decision":
                    opinion.signal = decision_type
                    opinion.reasoning = analysis_summary
                    opinion.raw_data = payload
                    break
        return payload

    def _collect_key_levels(
        self,
        ctx: AgentContext,
        payload: Dict[str, Any],
        dashboard_block: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Collect key price levels from dashboard payloads and agent opinions."""
        levels: Dict[str, Any] = {}

        def absorb(source: Any) -> None:
            if not isinstance(source, dict):
                return
            for key, value in source.items():
                normalized = _coerce_level_value(value)
                if normalized is not None and key not in levels:
                    levels[key] = normalized

        absorb(payload.get("key_levels"))
        absorb(dashboard_block.get("key_levels"))
        for opinion in reversed(ctx.opinions):
            absorb(getattr(opinion, "key_levels", {}))
            raw = opinion.raw_data if isinstance(opinion.raw_data, dict) else {}
            absorb(raw.get("key_levels"))
        return levels

    def _build_data_perspective(
        self,
        ctx: AgentContext,
        key_levels: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build a lightweight data_perspective block from cached market data."""
        realtime = ctx.get_data("realtime_quote")
        chip = ctx.get_data("chip_distribution")
        trend = ctx.get_data("trend_result")
        technical = self._latest_opinion(ctx, {"technical"})
        tech_raw = technical.raw_data if technical and isinstance(technical.raw_data, dict) else {}
        trend_dict = trend if isinstance(trend, dict) else {}

        data_perspective: Dict[str, Any] = {}
        ma_alignment = tech_raw.get("ma_alignment")
        trend_score = tech_raw.get("trend_score")
        if ma_alignment or trend_score is not None:
            data_perspective["trend_status"] = {
                "ma_alignment": ma_alignment or "N/A",
                "trend_score": trend_score if trend_score is not None else "N/A",
                "is_bullish": str(ma_alignment).lower() == "bullish",
            }

        def _bias_label(bias):
            if not isinstance(bias, (int, float)):
                return ""
            if bias > 5:
                return "超买"
            elif bias > 2:
                return "偏高"
            elif bias < -5:
                return "超卖"
            elif bias < -2:
                return "偏低"
            return "中性"

        def _r(val, n=2):
            """Round numeric values for display."""
            return round(val, n) if isinstance(val, (int, float)) else val

        def _pick(primary_dict, primary_key, fallback_dict, fallback_key, default="N/A"):
            """Pick first non-None value, avoiding falsy-zero trap."""
            v = primary_dict.get(primary_key)
            if v is not None:
                return v
            v2 = fallback_dict.get(fallback_key, default)
            return v2 if v2 is not None else default

        if isinstance(realtime, dict) or trend_dict:
            data_perspective["price_position"] = {
                "current_price": _r(_pick(trend_dict, "current_price", realtime or {}, "price")),
                "ma5": _r(_pick(trend_dict, "ma5", tech_raw, "ma5")),
                "ma10": _r(_pick(trend_dict, "ma10", tech_raw, "ma10")),
                "ma20": _r(_pick(trend_dict, "ma20", tech_raw, "ma20")),
                "bias_ma5": _r(_pick(trend_dict, "bias_ma5", tech_raw, "bias_ma5")),
                "bias_status": _bias_label(trend_dict.get("bias_ma5")) or tech_raw.get("bias_status", "N/A"),
                "support_level": key_levels.get("support") or key_levels.get("immediate_support") or "N/A",
                "resistance_level": key_levels.get("resistance") or key_levels.get("current_resistance") or "N/A",
            }
            data_perspective["volume_analysis"] = {
                "volume_ratio": (realtime or {}).get("volume_ratio", "N/A"),
                "turnover_rate": (realtime or {}).get("turnover_rate", "N/A"),
                "volume_status": trend_dict.get("volume_status") or tech_raw.get("volume_status", "N/A"),
                "volume_meaning": tech_raw.get("reasoning", "") if tech_raw else "",
            }

        if isinstance(chip, dict):
            concentration = chip.get("concentration_90")
            if concentration is None:
                concentration = chip.get("concentration")
            data_perspective["chip_structure"] = {
                "profit_ratio": chip.get("profit_ratio", "N/A"),
                "avg_cost": chip.get("avg_cost", "N/A"),
                "concentration": concentration if concentration is not None else "N/A",
                "chip_health": chip.get("chip_health", "一般"),
            }

        return data_perspective

    def _collect_risk_alerts(
        self,
        ctx: AgentContext,
        intelligence: Dict[str, Any],
    ) -> List[str]:
        alerts: List[str] = []

        def absorb(values: Any) -> None:
            if not isinstance(values, list):
                return
            for item in values:
                text = ""
                if isinstance(item, str):
                    text = item.strip()
                elif isinstance(item, dict):
                    text = str(item.get("description") or item.get("title") or "").strip()
                if text and text not in alerts:
                    alerts.append(text)

        absorb(intelligence.get("risk_alerts"))
        intel = self._latest_opinion(ctx, {"intel"})
        intel_raw = intel.raw_data if intel and isinstance(intel.raw_data, dict) else {}
        absorb(intel_raw.get("risk_alerts"))
        risk = self._latest_opinion(ctx, {"risk"})
        risk_raw = risk.raw_data if risk and isinstance(risk.raw_data, dict) else {}
        absorb(risk_raw.get("flags"))
        for flag in ctx.risk_flags:
            description = str(flag.get("description", "")).strip()
            if description and description not in alerts:
                alerts.append(description)
        return alerts[:8]

    def _collect_positive_catalysts(
        self,
        ctx: AgentContext,
        intelligence: Dict[str, Any],
    ) -> List[str]:
        catalysts: List[str] = []

        def absorb(values: Any) -> None:
            if not isinstance(values, list):
                return
            for item in values:
                text = str(item).strip()
                if text and text not in catalysts:
                    catalysts.append(text)

        absorb(intelligence.get("positive_catalysts"))
        intel = self._latest_opinion(ctx, {"intel"})
        intel_raw = intel.raw_data if intel and isinstance(intel.raw_data, dict) else {}
        absorb(intel_raw.get("positive_catalysts"))
        return catalysts[:8]

    @staticmethod
    def _latest_opinion(ctx: AgentContext, names: set[str]) -> Optional[Any]:
        for opinion in reversed(ctx.opinions):
            if opinion.agent_name in names:
                return opinion
        return None

    def _select_base_opinion(self, ctx: AgentContext) -> Optional[Any]:
        preferred_groups = (
            {"decision"},
            {"skill_consensus", "strategy_consensus"},
            {"technical"},
            {"intel"},
            {"risk"},
        )
        for names in preferred_groups:
            opinion = self._latest_opinion(ctx, names)
            if opinion is not None:
                return opinion
        if ctx.opinions:
            return ctx.opinions[-1]
        return None

    @staticmethod
    def _mark_partial_dashboard(
        dashboard: Dict[str, Any],
        *,
        note: str,
    ) -> Dict[str, Any]:
        tagged = dict(dashboard)
        summary = _first_non_empty_text(tagged.get("analysis_summary"))
        prefix = "[降级结果] "
        if summary and not summary.startswith(prefix):
            tagged["analysis_summary"] = prefix + summary
        elif not summary:
            tagged["analysis_summary"] = prefix + note

        warning = _first_non_empty_text(tagged.get("risk_warning"))
        tagged["risk_warning"] = f"{note} {warning}".strip() if warning else note

        nested = tagged.get("dashboard")
        if isinstance(nested, dict):
            nested = dict(nested)
            core = nested.get("core_conclusion")
            if isinstance(core, dict):
                core = dict(core)
                one_sentence = _first_non_empty_text(core.get("one_sentence"), tagged.get("analysis_summary"))
                if one_sentence and not str(one_sentence).startswith(prefix):
                    core["one_sentence"] = prefix + str(one_sentence)
                nested["core_conclusion"] = core
            tagged["dashboard"] = nested
        return tagged

    def _apply_risk_override(self, ctx: AgentContext) -> Optional[RiskOverrideApplication]:
        """Apply risk rules and retain their validated actual outcome."""
        dashboard = ctx.get_data("final_dashboard")
        if not isinstance(dashboard, dict):
            return None

        current_signal = normalize_decision_signal(dashboard.get("decision_type", "hold"))
        existing = ctx.meta.get("risk_override_application")
        if (
            isinstance(existing, RiskOverrideApplication)
            and existing.post_risk_signal.value == current_signal
        ):
            return existing

        plan = build_risk_override_plan(
            ctx,
            current_signal=current_signal,
            override_enabled=getattr(self.config, "agent_risk_override", True),
        )
        application = build_risk_override_application(plan)
        ctx.meta["risk_override_application"] = application
        if not application.applied:
            return application

        current_signal = application.from_signal.value
        new_signal = application.to_signal.value
        dashboard["decision_type"] = new_signal

        ctx.set_data("final_dashboard", dashboard)
        ctx.set_data("risk_override_applied", {
            "from": current_signal,
            "to": new_signal,
            "adjustment": plan.adjustment or ("veto" if plan.veto_buy else "none"),
            "reason": plan.reason,
        })

        logger.info(
            "[Orchestrator] risk override applied: %s -> %s (adjustment=%s, high_flag=%s)",
            current_signal,
            new_signal,
            plan.adjustment or ("veto" if plan.veto_buy else "none"),
            plan.has_high_flag,
        )
        return application

    @staticmethod
    def _merge_risk_warning(
        existing_warning: Any,
        risk_raw: Dict[str, Any],
        risk_flags: List[Dict[str, Any]],
        signal: str,
    ) -> str:
        """Build a concise risk warning after a forced downgrade."""
        prefix = f"风控接管：最终信号已下调为 {signal}。"
        warnings: List[str] = []

        def append_warning(value: Any) -> None:
            """Append one non-empty warning unless an equivalent detail exists."""
            text = str(value or "").strip()
            if text and not any(text == item or text in item for item in warnings):
                warnings.append(text)

        if isinstance(existing_warning, str) and existing_warning.strip():
            existing = existing_warning.strip()
            if existing.startswith(prefix):
                existing = existing[len(prefix):].strip()
            append_warning(existing)
        if isinstance(risk_raw.get("reasoning"), str) and risk_raw["reasoning"].strip():
            append_warning(risk_raw["reasoning"])
        for flag in risk_flags[:3]:
            description = str(flag.get("description", "")).strip()
            severity = str(flag.get("severity", "")).lower()
            if description:
                append_warning(f"[{severity or 'risk'}] {description}")
        merged = " ".join(dict.fromkeys([prefix] + warnings))
        return merged[:500]
