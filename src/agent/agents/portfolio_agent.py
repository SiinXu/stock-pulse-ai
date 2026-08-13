# -*- coding: utf-8 -*-
"""
PortfolioAgent — analyses a *set* of stocks as a whole portfolio,
rather than one-by-one.

Responsibilities:
- Position sizing suggestions (equal-weight / volatility-adjusted)
- Correlation & sector concentration warnings
- Portfolio-level risk metrics (beta, drawdown, sector exposure)
- Cross-market linkage (A-share ↔ HK ↔ US spillover)
- Overlay of deterministic rebalancing / position-band base (#237, #126)

The PortfolioAgent consumes pre-computed per-stock opinions
(from the normal orchestrator pipeline) and overlays portfolio
analytics. Deterministic rebalancing math is the explainable base;
the LLM may only polish narrative text and must not invent numbers
that contradict the base block when present.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from src.agent.agents.base_agent import BaseAgent
from src.agent.protocols import AgentContext, AgentOpinion
from src.agent.runner import try_parse_json
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)


def _build_deterministic_portfolio_base(ctx: AgentContext) -> Optional[Dict[str, Any]]:
    """Compute explainable rebalancing / position bands when portfolio data exists.

    Returns None when the deterministic path is unavailable (no holdings, service
    error). Callers must still work in stock-list-only mode.
    """
    try:
        from src.services.portfolio_rebalancing_service import (
            DEFAULT_RISK_TOLERANCE,
            PortfolioRebalancingService,
        )
    except Exception as exc:  # broad-exception: fallback_recorded - agent keeps LLM path
        log_safe_exception(
            logger,
            "PortfolioAgent rebalancing service unavailable",
            exc,
            error_code="portfolio_agent_rebalancing_service_unavailable",
        )
        return None

    risk_tolerance = (
        ctx.data.get("risk_tolerance")
        or ctx.meta.get("risk_tolerance")
        or DEFAULT_RISK_TOLERANCE
    )
    account_id = ctx.data.get("account_id") or ctx.meta.get("account_id")
    try:
        account_id_int = int(account_id) if account_id is not None else None
    except (TypeError, ValueError):
        account_id_int = None

    stock_signals: Dict[str, str] = {}
    stock_opinions = ctx.data.get("stock_opinions") or {}
    if isinstance(stock_opinions, dict):
        for code, opinion in stock_opinions.items():
            if isinstance(opinion, AgentOpinion):
                stock_signals[str(code)] = str(opinion.signal or "hold")
            elif isinstance(opinion, dict):
                stock_signals[str(code)] = str(opinion.get("signal") or "hold")

    try:
        service = PortfolioRebalancingService()
        result = service.get_recommendations(
            account_id=account_id_int,
            risk_tolerance=str(risk_tolerance),
            stock_signals=stock_signals or None,
        )
    except Exception as exc:  # broad-exception: fallback_recorded - LLM-only narrative
        log_safe_exception(
            logger,
            "PortfolioAgent deterministic rebalancing failed",
            exc,
            error_code="portfolio_agent_rebalancing_failed",
        )
        return None

    if not isinstance(result, dict):
        return None
    return result


def _suggestions_as_strings(base: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    for item in base.get("suggestions") or []:
        if not isinstance(item, dict):
            continue
        symbol = item.get("symbol")
        action = item.get("action")
        rationale = item.get("rationale") or ""
        delta = item.get("delta_weight_pct")
        if symbol and action:
            delta_text = f", delta={delta}pp" if delta is not None else ""
            lines.append(f"{action} {symbol}{delta_text}: {rationale}")
        elif rationale:
            lines.append(str(rationale))
    return lines


class PortfolioAgent(BaseAgent):
    """Portfolio-level analysis agent.

    This agent operates *after* per-stock analysis is already done.
    It reads per-stock opinions from ``ctx.data["stock_opinions"]``
    (a dict of stock_code → opinion) and produces a portfolio-level
    assessment.
    """

    agent_name = "portfolio"
    description = "Portfolio-level risk and allocation analysis"

    tool_names = [
        "get_realtime_quote",
        "get_stock_info",
        "get_portfolio_snapshot",
    ]

    def system_prompt(self, ctx: AgentContext) -> str:
        return (
            "You are a professional **portfolio analyst** specializing in "
            "multi-asset allocation for A-share, HK, and US equity portfolios.\n\n"
            "## Your task\n"
            "Given individual stock analysis opinions, produce a **Portfolio Assessment** "
            "that covers:\n"
            "1. **Position Sizing** — suggested weight per stock (equal-weight baseline, "
            "adjusted by conviction and volatility).\n"
            "2. **Sector Concentration** — warn if > 40% in one sector.\n"
            "3. **Correlation Risk** — flag highly correlated pairs.\n"
            "4. **Cross-Market Linkage** — note HK/US spill-over effects on A-shares.\n"
            "5. **Portfolio Risk Score** — 1-10 scale.\n"
            "6. **Rebalance Suggestions** — trim/add recommendations.\n\n"
            "## Deterministic base (mandatory when provided)\n"
            "When the user message includes a **Deterministic Rebalancing Base** JSON "
            "block, treat it as the sole source of numeric rebalancing suggestions and "
            "position weight bands:\n"
            "- Copy suggestion actions/weights/deltas from that base; do not invent "
            "conflicting numbers.\n"
            "- You may polish narrative `summary` / notes only.\n"
            "- Every suggestion is for human review only — never imply auto-execution.\n"
            "- Always include that outputs are research aid, not investment advice.\n"
            "- If the base status is empty_portfolio or insufficient_data, do not "
            "fabricate rebalance trades; explain the refusal.\n\n"
            "## Output format\n"
            "Return a single JSON object:\n"
            "```json\n"
            "{\n"
            '  "portfolio_risk_score": 6,\n'
            '  "total_stocks": 5,\n'
            '  "positions": [\n'
            '    {"code": "600519", "suggested_weight": 0.25, "signal": "buy", "note": "..."},\n'
            "    ...\n"
            "  ],\n"
            '  "sector_warnings": ["Consumer sector > 40%"],\n'
            '  "correlation_warnings": ["600519 & 000858 high correlation"],\n'
            '  "cross_market_notes": ["US tariff risk may impact export-heavy positions"],\n'
            '  "rebalance_suggestions": ["Trim 000858: ..."],\n'
            '  "summary": "Portfolio is moderately concentrated ...",\n'
            '  "disclaimer": "Research aid only — not investment advice."\n'
            "}\n"
            "```\n"
        )

    def build_user_message(self, ctx: AgentContext) -> str:
        stock_opinions = ctx.data.get("stock_opinions", {})
        stock_list = ctx.data.get("stock_list", [])

        parts = [f"Analyze the following portfolio of {len(stock_list) or len(stock_opinions)} stocks:\n"]

        if stock_opinions:
            for code, opinion in stock_opinions.items():
                if isinstance(opinion, AgentOpinion):
                    parts.append(
                        f"- **{code}**: signal={opinion.signal}, "
                        f"confidence={opinion.confidence:.0%}, "
                        f"summary={opinion.reasoning[:200]}"
                    )
                elif isinstance(opinion, dict):
                    parts.append(
                        f"- **{code}**: signal={opinion.get('signal', 'unknown')}, "
                        f"confidence={opinion.get('confidence', 'N/A')}, "
                        f"summary={str(opinion.get('summary', ''))[:200]}"
                    )
        elif stock_list:
            for code in stock_list:
                parts.append(f"- {code}")

        if ctx.risk_flags:
            parts.append("\n### Risk Flags from Individual Analysis:")
            for flag in ctx.risk_flags:
                parts.append(f"- ⚠️ {flag}")

        if ctx.query:
            parts.append(f"\nUser request: {ctx.query}")

        base = _build_deterministic_portfolio_base(ctx)
        if base is not None:
            ctx.data["portfolio_rebalancing_base"] = base
            parts.append(
                "\n## Deterministic Rebalancing Base (authoritative numbers)\n"
                "Use the following JSON as the sole numeric source for rebalance "
                "suggestions and position bands. Do not contradict these figures.\n"
                "```json\n"
                f"{json.dumps(base, ensure_ascii=False, default=str)[:12000]}\n"
                "```\n"
            )

        return "\n".join(parts)

    def post_process(self, ctx: AgentContext, raw_response: str) -> Optional[AgentOpinion]:
        """Extract portfolio assessment and merge deterministic base."""
        data = try_parse_json(raw_response)
        base = ctx.data.get("portfolio_rebalancing_base")
        if not isinstance(base, dict):
            base = None

        if data is None:
            logger.debug("[PortfolioAgent] post_process: failed to parse JSON")
            if base is None:
                return AgentOpinion(
                    agent_name="portfolio",
                    signal="hold",
                    confidence=0.3,
                    reasoning=raw_response[:500],
                    raw_data={"raw": raw_response[:1000]},
                )
            data = {
                "portfolio_risk_score": 5,
                "summary": raw_response[:500],
                "rebalance_suggestions": [],
                "positions": [],
            }

        if base is not None:
            det_suggestions = _suggestions_as_strings(base)
            if det_suggestions:
                data["rebalance_suggestions"] = det_suggestions
            elif base.get("status") in {"empty_portfolio", "insufficient_data", "refused"}:
                data["rebalance_suggestions"] = [
                    str(base.get("status_message") or base.get("status"))
                ]
            else:
                # Within-band / no-trim still overwrites so the LLM cannot invent trades.
                data["rebalance_suggestions"] = []
            data["deterministic_rebalancing"] = {
                "status": base.get("status"),
                "status_message": base.get("status_message"),
                "suggestions": base.get("suggestions") or [],
                "position_bands": base.get("position_bands") or [],
                "drift": base.get("drift") or {},
                "target_model": base.get("target_model") or {},
                "assumptions": base.get("assumptions") or {},
                "disclaimer": base.get("disclaimer"),
                "is_suggestion_only": True,
                "auto_execute": False,
                "source": "PortfolioRebalancingService",
            }
            bands = base.get("position_bands") or []
            if bands:
                data["positions"] = [
                    {
                        "code": b.get("symbol"),
                        "suggested_weight": (
                            float(b["target_weight_pct_mid"]) / 100.0
                            if b.get("target_weight_pct_mid") is not None
                            else None
                        ),
                        "target_weight_pct_low": b.get("target_weight_pct_low"),
                        "target_weight_pct_high": b.get("target_weight_pct_high"),
                        "signal": b.get("signal"),
                        "action": b.get("action"),
                        "note": b.get("rationale"),
                    }
                    for b in bands
                    if isinstance(b, dict)
                ]
            data.setdefault(
                "disclaimer",
                base.get("disclaimer")
                or "Research aid only — not investment advice.",
            )

        ctx.data["portfolio_assessment"] = data

        risk_score = data.get("portfolio_risk_score", 5)
        signal = "hold"
        try:
            score_f = float(risk_score)
        except (TypeError, ValueError):
            score_f = 5.0
        if score_f <= 3:
            signal = "buy"
        elif score_f >= 7:
            signal = "sell"

        return AgentOpinion(
            agent_name="portfolio",
            signal=signal,
            confidence=0.6,
            reasoning=data.get("summary", raw_response[:300]),
            raw_data=data,
        )
