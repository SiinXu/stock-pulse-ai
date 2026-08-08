# -*- coding: utf-8 -*-
"""Daily portfolio health score and actionable insights (issue #151).

Aggregates existing portfolio snapshot and risk-metrics inputs into a
deterministic 0–100 health score plus rule-based insights.

Hard contract:
- Scores and dimension math are pure rule formulas with explicit weights.
- LLM (if used) may only polish insight *message* text; it must never change
  score, band, dimension values, or insight metrics/thresholds.
- Missing prices / stale FX / insufficient history mark the result ``partial``
  and list unavailable dimensions — never silent defaults that look complete.
"""

from __future__ import annotations

import logging
import os
from datetime import date
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from src.repositories.portfolio_health_repo import PortfolioHealthRepository
from src.services.portfolio_risk_metrics_service import PortfolioRiskMetricsService
from src.services.portfolio_service import PortfolioService
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

_EPS = 1e-12

# ---------------------------------------------------------------------------
# Explicit default weights (must sum to 1.0). Documented in docs/portfolio-health-score.md
# ---------------------------------------------------------------------------
DEFAULT_WEIGHTS: Dict[str, float] = {
    "concentration": 0.25,
    "risk_exposure": 0.25,
    "diversification": 0.20,
    "pnl": 0.15,
    "cash_ratio": 0.15,
}

DIMENSION_KEYS: Tuple[str, ...] = (
    "concentration",
    "risk_exposure",
    "diversification",
    "pnl",
    "cash_ratio",
)

# Concentration sub-score anchors (top position weight in percent of equity MV)
CONCENTRATION_IDEAL_TOP_PCT = 15.0
CONCENTRATION_POOR_TOP_PCT = 50.0

# Risk exposure anchors: 1-day historical VaR percent (positive loss points)
RISK_VAR_IDEAL_PCT = 1.0
RISK_VAR_POOR_PCT = 8.0

# Unrealized PnL percent of equity
PNL_STRONG_PCT = 10.0
PNL_NEUTRAL_SCORE = 70.0
PNL_POOR_PCT = -30.0

# Cash / equity ratio percent — ideal band scores 100
CASH_IDEAL_LOW_PCT = 5.0
CASH_IDEAL_HIGH_PCT = 25.0
CASH_POOR_HIGH_PCT = 80.0

# Insight thresholds (defaults align with portfolio risk concentration alert)
DEFAULT_CONCENTRATION_ALERT_PCT = 35.0
DEFAULT_CASH_LOW_ALERT_PCT = 2.0
DEFAULT_CASH_HIGH_ALERT_PCT = 50.0
DEFAULT_VAR_ALERT_PCT = 5.0
DEFAULT_DIVERSIFICATION_ALERT = 0.35
DEFAULT_PNL_LOSS_ALERT_PCT = -15.0

SCORE_BANDS: Tuple[Tuple[float, float, str], ...] = (
    (80.0, 100.0, "healthy"),
    (60.0, 80.0, "fair"),
    (40.0, 60.0, "caution"),
    (0.0, 40.0, "poor"),
)

DISCLAIMER = (
    "Portfolio health is a structural portfolio metric, not investment advice. "
    "Scores are deterministic and fully recomputable from documented formulas."
)

# Optional LLM polish: only rewrites insight message strings.
LlmInsightPolisher = Callable[[Sequence[Mapping[str, Any]]], List[Dict[str, Any]]]


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _linear_score(
    *,
    value: float,
    ideal: float,
    poor: float,
    higher_is_better: bool,
) -> float:
    """Map value onto [0, 100] with linear interpolation between ideal and poor."""
    if higher_is_better:
        if value >= ideal:
            return 100.0
        if value <= poor:
            return 0.0
        span = ideal - poor
        if abs(span) <= _EPS:
            return 100.0 if value >= ideal else 0.0
        return _clamp(100.0 * (value - poor) / span)

    # lower is better (e.g. concentration top weight, VaR)
    if value <= ideal:
        return 100.0
    if value >= poor:
        return 0.0
    span = poor - ideal
    if abs(span) <= _EPS:
        return 100.0 if value <= ideal else 0.0
    return _clamp(100.0 * (poor - value) / span)


def score_concentration(top_weight_pct: float) -> float:
    """Sub-score from top single-name weight percent (lower concentration → healthier)."""
    return round(
        _linear_score(
            value=float(top_weight_pct),
            ideal=CONCENTRATION_IDEAL_TOP_PCT,
            poor=CONCENTRATION_POOR_TOP_PCT,
            higher_is_better=False,
        ),
        4,
    )


def score_risk_exposure(var_pct: float) -> float:
    """Sub-score from 1-day historical VaR percent (lower VaR → healthier)."""
    return round(
        _linear_score(
            value=float(var_pct),
            ideal=RISK_VAR_IDEAL_PCT,
            poor=RISK_VAR_POOR_PCT,
            higher_is_better=False,
        ),
        4,
    )


def score_diversification(diversification_score: float) -> float:
    """Sub-score from risk-metrics diversification_score in [0, 1]."""
    return round(_clamp(float(diversification_score) * 100.0), 4)


def score_pnl(unrealized_pnl_pct: float) -> float:
    """Sub-score from unrealized PnL as percent of equity.

    Piecewise linear: PNL_STRONG_PCT → 100, 0% → PNL_NEUTRAL_SCORE, PNL_POOR_PCT → 0.
    """
    pnl = float(unrealized_pnl_pct)
    if pnl >= PNL_STRONG_PCT:
        return 100.0
    if pnl >= 0.0:
        # 0 → 70, strong → 100
        span = PNL_STRONG_PCT
        if span <= _EPS:
            return 100.0
        return round(PNL_NEUTRAL_SCORE + (100.0 - PNL_NEUTRAL_SCORE) * (pnl / span), 4)
    if pnl <= PNL_POOR_PCT:
        return 0.0
    # 0 → 70, poor → 0
    span = abs(PNL_POOR_PCT)
    if span <= _EPS:
        return 0.0
    return round(PNL_NEUTRAL_SCORE * (1.0 - abs(pnl) / span), 4)


def score_cash_ratio(cash_pct: float) -> float:
    """Sub-score from cash / equity percent; ideal band scores 100."""
    cash = float(cash_pct)
    if CASH_IDEAL_LOW_PCT <= cash <= CASH_IDEAL_HIGH_PCT:
        return 100.0
    if cash < CASH_IDEAL_LOW_PCT:
        if cash <= 0.0:
            return 0.0
        return round(100.0 * (cash / CASH_IDEAL_LOW_PCT), 4)
    # above ideal high
    if cash >= CASH_POOR_HIGH_PCT:
        return 0.0
    span = CASH_POOR_HIGH_PCT - CASH_IDEAL_HIGH_PCT
    if span <= _EPS:
        return 0.0
    return round(100.0 * (CASH_POOR_HIGH_PCT - cash) / span, 4)


def band_for_score(score: Optional[float]) -> Optional[str]:
    if score is None:
        return None
    value = float(score)
    for low, high, name in SCORE_BANDS:
        if low <= value < high or (name == "healthy" and value == 100.0):
            return name
        if name == "healthy" and value >= 80.0:
            return name
    if value >= 80.0:
        return "healthy"
    if value >= 60.0:
        return "fair"
    if value >= 40.0:
        return "caution"
    return "poor"


def resolve_weights(overrides: Optional[Mapping[str, float]] = None) -> Dict[str, float]:
    """Return normalized positive weights for all dimensions.

    Env overrides (optional, still sum-normalized):
    PORTFOLIO_HEALTH_WEIGHT_CONCENTRATION, _RISK_EXPOSURE, _DIVERSIFICATION, _PNL, _CASH_RATIO
    """
    weights = dict(DEFAULT_WEIGHTS)
    env_map = {
        "concentration": "PORTFOLIO_HEALTH_WEIGHT_CONCENTRATION",
        "risk_exposure": "PORTFOLIO_HEALTH_WEIGHT_RISK_EXPOSURE",
        "diversification": "PORTFOLIO_HEALTH_WEIGHT_DIVERSIFICATION",
        "pnl": "PORTFOLIO_HEALTH_WEIGHT_PNL",
        "cash_ratio": "PORTFOLIO_HEALTH_WEIGHT_CASH_RATIO",
    }
    for key, env_name in env_map.items():
        raw = os.environ.get(env_name)
        if raw is None or str(raw).strip() == "":
            continue
        try:
            weights[key] = float(raw)
        except (TypeError, ValueError):
            logger.warning("Ignoring invalid %s=%r", env_name, raw)

    if overrides:
        for key, value in overrides.items():
            if key in weights:
                weights[key] = float(value)

    for key in DIMENSION_KEYS:
        if weights[key] < 0:
            raise ValueError(f"weight for {key} must be non-negative")

    total = sum(weights[k] for k in DIMENSION_KEYS)
    if total <= _EPS:
        raise ValueError("weights must sum to a positive value")
    return {k: weights[k] / total for k in DIMENSION_KEYS}


def aggregate_score(
    dimension_scores: Mapping[str, Optional[float]],
    weights: Mapping[str, float],
) -> Tuple[Optional[float], List[str], Dict[str, float]]:
    """Weighted average over available dimensions; reweights when some are missing.

    Returns (score_or_None, unavailable_keys, effective_weights_used).
    """
    available: Dict[str, float] = {}
    unavailable: List[str] = []
    for key in DIMENSION_KEYS:
        value = dimension_scores.get(key)
        if value is None:
            unavailable.append(key)
            continue
        available[key] = float(value)

    if not available:
        return None, unavailable, {}

    weight_sum = sum(float(weights[k]) for k in available)
    if weight_sum <= _EPS:
        return None, unavailable, {}

    effective = {k: float(weights[k]) / weight_sum for k in available}
    score = sum(available[k] * effective[k] for k in available)
    return round(_clamp(score), 4), unavailable, effective


def build_rule_insights(
    *,
    concentration: Mapping[str, Any],
    risk_var_pct: Optional[float],
    diversification_score: Optional[float],
    cash_pct: Optional[float],
    unrealized_pnl_pct: Optional[float],
    concentration_alert_pct: float,
    cash_low_alert_pct: float,
    cash_high_alert_pct: float,
    var_alert_pct: float,
    diversification_alert: float,
    pnl_loss_alert_pct: float,
) -> List[Dict[str, Any]]:
    """Build actionable, threshold-bound insights from concrete metrics."""
    insights: List[Dict[str, Any]] = []

    weights = list(concentration.get("weights") or [])
    top_weight_pct = concentration.get("top_weight_pct")
    if weights and top_weight_pct is not None:
        top = weights[0]
        symbol = str(top.get("symbol") or "").strip().upper() or "UNKNOWN"
        w = float(top.get("weight_pct") or top_weight_pct)
        if w >= concentration_alert_pct:
            insights.append(
                {
                    "code": "concentration_top_name",
                    "severity": "warning",
                    "message": (
                        f"Position {symbol} weight {w:.1f}% exceeds concentration "
                        f"threshold {concentration_alert_pct:.1f}%; consider reducing "
                        f"or hedging this single-name exposure."
                    ),
                    "symbol": symbol,
                    "metric": "top_weight_pct",
                    "value": round(w, 4),
                    "threshold": float(concentration_alert_pct),
                    "source": "rule",
                }
            )
        # Secondary names over threshold
        for row in weights[1:5]:
            symbol_i = str(row.get("symbol") or "").strip().upper()
            w_i = float(row.get("weight_pct") or 0.0)
            if symbol_i and w_i >= concentration_alert_pct:
                insights.append(
                    {
                        "code": "concentration_name",
                        "severity": "warning",
                        "message": (
                            f"Position {symbol_i} weight {w_i:.1f}% exceeds concentration "
                            f"threshold {concentration_alert_pct:.1f}%; consider reducing "
                            f"or hedging."
                        ),
                        "symbol": symbol_i,
                        "metric": "weight_pct",
                        "value": round(w_i, 4),
                        "threshold": float(concentration_alert_pct),
                        "source": "rule",
                    }
                )

    if (
        diversification_score is not None
        and float(diversification_score) < diversification_alert
    ):
        insights.append(
            {
                "code": "low_diversification",
                "severity": "warning",
                "message": (
                    f"Diversification score {float(diversification_score):.2f} is below "
                    f"threshold {diversification_alert:.2f} (1.0 = equal-weight); "
                    f"consider adding uncorrelated names or rebalancing toward equal weight."
                ),
                "symbol": None,
                "metric": "diversification_score",
                "value": round(float(diversification_score), 6),
                "threshold": float(diversification_alert),
                "source": "rule",
            }
        )

    if risk_var_pct is not None and float(risk_var_pct) >= var_alert_pct:
        insights.append(
            {
                "code": "elevated_var",
                "severity": "warning",
                "message": (
                    f"1-day historical VaR is {float(risk_var_pct):.2f}%, at or above "
                    f"alert threshold {var_alert_pct:.2f}%; risk exposure is elevated "
                    f"relative to configured tolerance."
                ),
                "symbol": None,
                "metric": "var_pct",
                "value": round(float(risk_var_pct), 4),
                "threshold": float(var_alert_pct),
                "source": "rule",
            }
        )

    if cash_pct is not None:
        cash = float(cash_pct)
        if cash <= cash_low_alert_pct:
            insights.append(
                {
                    "code": "cash_low",
                    "severity": "info",
                    "message": (
                        f"Cash ratio {cash:.1f}% is at or below {cash_low_alert_pct:.1f}%; "
                        f"limited dry powder for drawdowns or new opportunities."
                    ),
                    "symbol": None,
                    "metric": "cash_pct",
                    "value": round(cash, 4),
                    "threshold": float(cash_low_alert_pct),
                    "source": "rule",
                }
            )
        elif cash >= cash_high_alert_pct:
            insights.append(
                {
                    "code": "cash_high",
                    "severity": "info",
                    "message": (
                        f"Cash ratio {cash:.1f}% is at or above {cash_high_alert_pct:.1f}%; "
                        f"equity deployment is low relative to total equity."
                    ),
                    "symbol": None,
                    "metric": "cash_pct",
                    "value": round(cash, 4),
                    "threshold": float(cash_high_alert_pct),
                    "source": "rule",
                }
            )

    if unrealized_pnl_pct is not None and float(unrealized_pnl_pct) <= pnl_loss_alert_pct:
        insights.append(
            {
                "code": "unrealized_loss",
                "severity": "warning",
                "message": (
                    f"Unrealized PnL is {float(unrealized_pnl_pct):.1f}% of equity, "
                    f"at or below loss alert {pnl_loss_alert_pct:.1f}%; review stop-loss "
                    f"and position sizing on largest losers."
                ),
                "symbol": None,
                "metric": "unrealized_pnl_pct",
                "value": round(float(unrealized_pnl_pct), 4),
                "threshold": float(pnl_loss_alert_pct),
                "source": "rule",
            }
        )

    if not insights:
        insights.append(
            {
                "code": "within_thresholds",
                "severity": "info",
                "message": (
                    "No concentration, VaR, cash, or unrealized-loss threshold breaches "
                    "detected for this snapshot."
                ),
                "symbol": None,
                "metric": None,
                "value": None,
                "threshold": None,
                "source": "rule",
            }
        )

    return insights


def apply_llm_polish(
    rule_insights: Sequence[Mapping[str, Any]],
    polished: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Merge LLM-polished messages onto rule insights without changing metrics.

    Contract: only the ``message`` field may change. Score-related fields
    (code, severity, symbol, metric, value, threshold) stay from the rule set.
    Extra LLM rows are dropped. Missing rows keep the rule message.
    """
    result: List[Dict[str, Any]] = []
    polished_by_code: Dict[str, Mapping[str, Any]] = {}
    for item in polished or []:
        code = str(item.get("code") or "")
        if code:
            polished_by_code[code] = item

    for rule in rule_insights:
        row = dict(rule)
        code = str(row.get("code") or "")
        alt = polished_by_code.get(code)
        if alt is not None:
            message = alt.get("message")
            if isinstance(message, str) and message.strip():
                row["message"] = message.strip()
                row["source"] = "rule+llm_polish"
            else:
                row["source"] = "rule"
        else:
            row["source"] = "rule"
        # Hard restore non-message contract fields from the rule insight.
        for key in ("code", "severity", "symbol", "metric", "value", "threshold"):
            row[key] = rule.get(key)
        result.append(row)
    return result


class PortfolioHealthService:
    """Compute, persist, and load daily portfolio health scores."""

    def __init__(
        self,
        *,
        portfolio_service: Optional[PortfolioService] = None,
        risk_metrics_service: Optional[PortfolioRiskMetricsService] = None,
        health_repo: Optional[PortfolioHealthRepository] = None,
        llm_polisher: Optional[LlmInsightPolisher] = None,
    ) -> None:
        self.portfolio_service = portfolio_service or PortfolioService()
        self.risk_metrics_service = risk_metrics_service or PortfolioRiskMetricsService(
            portfolio_service=self.portfolio_service
        )
        self.health_repo = health_repo or PortfolioHealthRepository()
        self.llm_polisher = llm_polisher

    def get_health(
        self,
        *,
        account_id: Optional[int] = None,
        as_of: Optional[date] = None,
        cost_method: str = "fifo",
        persist: bool = True,
        weights: Optional[Mapping[str, float]] = None,
        concentration_alert_pct: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Compute health for (account_id, as_of), optionally upserting the daily snapshot."""
        as_of_date = as_of or date.today()
        method = str(cost_method or "fifo").strip().lower() or "fifo"
        weight_map = resolve_weights(weights)
        conc_alert = float(
            concentration_alert_pct
            if concentration_alert_pct is not None
            else os.environ.get(
                "PORTFOLIO_HEALTH_CONCENTRATION_ALERT_PCT",
                os.environ.get(
                    "PORTFOLIO_RISK_CONCENTRATION_ALERT_PCT",
                    str(DEFAULT_CONCENTRATION_ALERT_PCT),
                ),
            )
        )

        snapshot = self.portfolio_service.get_portfolio_snapshot(
            account_id=account_id,
            as_of=as_of_date,
            cost_method=method,
            include_realtime=False,
        )
        risk = self.risk_metrics_service.get_risk_metrics(
            account_id=account_id,
            as_of=as_of_date,
            cost_method=method,
        )

        result = self._score_from_inputs(
            snapshot=snapshot,
            risk=risk,
            account_id=account_id,
            as_of_date=as_of_date,
            cost_method=method,
            weights=weight_map,
            concentration_alert_pct=conc_alert,
        )

        if persist:
            self.health_repo.upsert_snapshot(
                account_id=account_id,
                snapshot_date=as_of_date,
                cost_method=method,
                payload=result,
            )
            result["persisted"] = True
        else:
            result["persisted"] = False

        return result

    def get_stored_health(
        self,
        *,
        account_id: Optional[int] = None,
        as_of: Optional[date] = None,
        cost_method: str = "fifo",
    ) -> Optional[Dict[str, Any]]:
        """Return the last persisted snapshot for the day, or None."""
        as_of_date = as_of or date.today()
        method = str(cost_method or "fifo").strip().lower() or "fifo"
        return self.health_repo.get_snapshot(
            account_id=account_id,
            snapshot_date=as_of_date,
            cost_method=method,
        )

    def _score_from_inputs(
        self,
        *,
        snapshot: Mapping[str, Any],
        risk: Mapping[str, Any],
        account_id: Optional[int],
        as_of_date: date,
        cost_method: str,
        weights: Mapping[str, float],
        concentration_alert_pct: float,
    ) -> Dict[str, Any]:
        currency = str(snapshot.get("currency") or risk.get("currency") or "CNY")
        total_equity = float(snapshot.get("total_equity") or 0.0)
        total_cash = float(snapshot.get("total_cash") or 0.0)
        total_mv = float(snapshot.get("total_market_value") or 0.0)
        unrealized = float(snapshot.get("unrealized_pnl") or 0.0)
        fx_stale = bool(snapshot.get("fx_stale"))
        data_quality = str(snapshot.get("data_quality") or "ok")
        limitations = list(snapshot.get("limitations") or [])

        concentration = dict(risk.get("concentration") or {})
        var_block = dict(risk.get("var") or {})
        risk_status = str(risk.get("status") or "")

        base: Dict[str, Any] = {
            "as_of": as_of_date.isoformat(),
            "account_id": account_id,
            "cost_method": cost_method,
            "currency": currency,
            "disclaimer": DISCLAIMER,
            "score_source": "rules",
            "llm_can_modify_score": False,
            "weights": {k: round(float(weights[k]), 6) for k in DIMENSION_KEYS},
            "bands": [
                {"name": name, "min_inclusive": low, "max_exclusive": high if name != "healthy" else 100.0}
                for low, high, name in SCORE_BANDS
            ],
            "formula_version": "portfolio_health_v1",
        }

        # Empty portfolio: no equity MV and no cash positions of interest
        position_count = int(concentration.get("position_count") or 0)
        if position_count <= 0 and total_mv <= _EPS:
            return {
                **base,
                "status": "empty_portfolio",
                "status_message": "No held equity positions with positive market value.",
                "score": None,
                "band": None,
                "dimensions": self._empty_dimensions(),
                "unavailable_dimensions": list(DIMENSION_KEYS),
                "effective_weights": {},
                "insights": [],
                "data_quality": {
                    "status": "empty",
                    "fx_stale": fx_stale,
                    "snapshot_data_quality": data_quality,
                    "limitations": limitations,
                    "missing_price_symbols": [],
                    "risk_metrics_status": risk_status,
                },
                "inputs": {
                    "top_weight_pct": None,
                    "var_pct": None,
                    "diversification_score": None,
                    "unrealized_pnl_pct": None,
                    "cash_pct": None,
                    "total_equity": round(total_equity, 6),
                    "total_cash": round(total_cash, 6),
                    "total_market_value": round(total_mv, 6),
                },
            }

        missing_price_symbols = self._missing_price_symbols(snapshot)
        partial_reasons: List[str] = []
        if fx_stale:
            partial_reasons.append("fx_stale")
        if missing_price_symbols:
            partial_reasons.append("missing_or_stale_prices")
        if data_quality == "partial":
            partial_reasons.append("snapshot_data_quality_partial")
        if limitations:
            partial_reasons.append("snapshot_limitations")

        dim_scores: Dict[str, Optional[float]] = {
            "concentration": None,
            "risk_exposure": None,
            "diversification": None,
            "pnl": None,
            "cash_ratio": None,
        }
        dim_details: Dict[str, Dict[str, Any]] = {}

        # --- concentration ---
        top_weight = concentration.get("top_weight_pct")
        if concentration.get("status") == "ok" and top_weight is not None:
            dim_scores["concentration"] = score_concentration(float(top_weight))
            dim_details["concentration"] = {
                "status": "ok",
                "score": dim_scores["concentration"],
                "input": {"top_weight_pct": float(top_weight)},
                "formula": (
                    f"linear map top_weight_pct: "
                    f"<={CONCENTRATION_IDEAL_TOP_PCT}→100, "
                    f">={CONCENTRATION_POOR_TOP_PCT}→0"
                ),
            }
        else:
            dim_details["concentration"] = {
                "status": "unavailable",
                "score": None,
                "reason": "concentration_block_unavailable",
            }
            partial_reasons.append("concentration_unavailable")

        # --- risk exposure (VaR) ---
        var_status = str(var_block.get("status") or "")
        var_pct = var_block.get("var_pct")
        if var_status == "ok" and var_pct is not None:
            dim_scores["risk_exposure"] = score_risk_exposure(float(var_pct))
            dim_details["risk_exposure"] = {
                "status": "ok",
                "score": dim_scores["risk_exposure"],
                "input": {"var_pct": float(var_pct)},
                "formula": (
                    f"linear map var_pct: <={RISK_VAR_IDEAL_PCT}→100, "
                    f">={RISK_VAR_POOR_PCT}→0"
                ),
            }
        else:
            reason = var_status or "var_unavailable"
            dim_details["risk_exposure"] = {
                "status": "unavailable",
                "score": None,
                "reason": reason,
                "status_message": var_block.get("status_message"),
            }
            partial_reasons.append(f"risk_exposure_{reason}")

        # --- diversification ---
        div_score = concentration.get("diversification_score")
        if concentration.get("status") == "ok" and div_score is not None:
            dim_scores["diversification"] = score_diversification(float(div_score))
            dim_details["diversification"] = {
                "status": "ok",
                "score": dim_scores["diversification"],
                "input": {"diversification_score": float(div_score)},
                "formula": "diversification_score * 100",
            }
        else:
            dim_details["diversification"] = {
                "status": "unavailable",
                "score": None,
                "reason": "diversification_unavailable",
            }
            partial_reasons.append("diversification_unavailable")

        # --- pnl ---
        # Prefer equity as base; if equity ~0 but we have cost context, skip.
        if total_equity > _EPS:
            pnl_pct = unrealized / total_equity * 100.0
            # If prices missing, PnL is not trustworthy
            if missing_price_symbols or fx_stale:
                dim_details["pnl"] = {
                    "status": "unavailable",
                    "score": None,
                    "reason": "price_or_fx_quality_partial",
                    "input": {"unrealized_pnl_pct": round(pnl_pct, 6)},
                }
                partial_reasons.append("pnl_data_quality")
            else:
                dim_scores["pnl"] = score_pnl(pnl_pct)
                dim_details["pnl"] = {
                    "status": "ok",
                    "score": dim_scores["pnl"],
                    "input": {"unrealized_pnl_pct": round(pnl_pct, 6)},
                    "formula": (
                        f"piecewise: >={PNL_STRONG_PCT}%→100, 0%→{PNL_NEUTRAL_SCORE}, "
                        f"<={PNL_POOR_PCT}%→0"
                    ),
                }
        else:
            dim_details["pnl"] = {
                "status": "unavailable",
                "score": None,
                "reason": "zero_equity",
            }
            partial_reasons.append("pnl_zero_equity")

        # --- cash ratio ---
        if total_equity > _EPS:
            cash_pct = total_cash / total_equity * 100.0
            if fx_stale:
                dim_details["cash_ratio"] = {
                    "status": "unavailable",
                    "score": None,
                    "reason": "fx_stale",
                    "input": {"cash_pct": round(cash_pct, 6)},
                }
                partial_reasons.append("cash_fx_stale")
            else:
                dim_scores["cash_ratio"] = score_cash_ratio(cash_pct)
                dim_details["cash_ratio"] = {
                    "status": "ok",
                    "score": dim_scores["cash_ratio"],
                    "input": {"cash_pct": round(cash_pct, 6)},
                    "formula": (
                        f"ideal band [{CASH_IDEAL_LOW_PCT}, {CASH_IDEAL_HIGH_PCT}]→100; "
                        f"0%→0; >={CASH_POOR_HIGH_PCT}%→0"
                    ),
                }
        else:
            dim_details["cash_ratio"] = {
                "status": "unavailable",
                "score": None,
                "reason": "zero_equity",
            }
            partial_reasons.append("cash_zero_equity")

        overall, unavailable, effective = aggregate_score(dim_scores, weights)

        # Status honesty
        if overall is None:
            status = "unavailable"
            status_message = "No health dimensions could be scored from available data."
        elif unavailable or partial_reasons:
            status = "partial"
            status_message = (
                "Health score uses available dimensions only; "
                f"unavailable={unavailable or []}; reasons={sorted(set(partial_reasons))}."
            )
        else:
            status = "ok"
            status_message = "All health dimensions scored from portfolio snapshot and risk metrics."

        inputs = {
            "top_weight_pct": (
                float(top_weight) if top_weight is not None else None
            ),
            "var_pct": float(var_pct) if var_pct is not None else None,
            "diversification_score": (
                float(div_score) if div_score is not None else None
            ),
            "unrealized_pnl_pct": (
                round(unrealized / total_equity * 100.0, 6)
                if total_equity > _EPS
                else None
            ),
            "cash_pct": (
                round(total_cash / total_equity * 100.0, 6)
                if total_equity > _EPS
                else None
            ),
            "total_equity": round(total_equity, 6),
            "total_cash": round(total_cash, 6),
            "total_market_value": round(total_mv, 6),
        }

        rule_insights = build_rule_insights(
            concentration=concentration,
            risk_var_pct=inputs["var_pct"],
            diversification_score=inputs["diversification_score"],
            cash_pct=inputs["cash_pct"],
            unrealized_pnl_pct=inputs["unrealized_pnl_pct"],
            concentration_alert_pct=concentration_alert_pct,
            cash_low_alert_pct=float(
                os.environ.get(
                    "PORTFOLIO_HEALTH_CASH_LOW_ALERT_PCT",
                    str(DEFAULT_CASH_LOW_ALERT_PCT),
                )
            ),
            cash_high_alert_pct=float(
                os.environ.get(
                    "PORTFOLIO_HEALTH_CASH_HIGH_ALERT_PCT",
                    str(DEFAULT_CASH_HIGH_ALERT_PCT),
                )
            ),
            var_alert_pct=float(
                os.environ.get(
                    "PORTFOLIO_HEALTH_VAR_ALERT_PCT",
                    str(DEFAULT_VAR_ALERT_PCT),
                )
            ),
            diversification_alert=float(
                os.environ.get(
                    "PORTFOLIO_HEALTH_DIVERSIFICATION_ALERT",
                    str(DEFAULT_DIVERSIFICATION_ALERT),
                )
            ),
            pnl_loss_alert_pct=float(
                os.environ.get(
                    "PORTFOLIO_HEALTH_PNL_LOSS_ALERT_PCT",
                    str(DEFAULT_PNL_LOSS_ALERT_PCT),
                )
            ),
        )
        insights = self._finalize_insights(rule_insights)

        # Freeze score before any insight path (LLM cannot touch this).
        score_locked = overall
        band_locked = band_for_score(score_locked)

        return {
            **base,
            "status": status,
            "status_message": status_message,
            "score": score_locked,
            "band": band_locked,
            "dimensions": dim_details,
            "unavailable_dimensions": unavailable,
            "effective_weights": {k: round(v, 6) for k, v in effective.items()},
            "insights": insights,
            "data_quality": {
                "status": "partial" if status == "partial" else ("ok" if status == "ok" else status),
                "fx_stale": fx_stale,
                "snapshot_data_quality": data_quality,
                "limitations": limitations,
                "missing_price_symbols": missing_price_symbols,
                "risk_metrics_status": risk_status,
                "partial_reasons": sorted(set(partial_reasons)),
            },
            "inputs": inputs,
        }

    def _finalize_insights(
        self,
        rule_insights: Sequence[Mapping[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Apply optional LLM polish with hard non-score contract enforcement."""
        base = [dict(item) for item in rule_insights]
        if self.llm_polisher is None:
            return base
        try:
            polished = self.llm_polisher(base)
        except Exception as exc:  # broad-exception: fallback_recorded - keep rule insights
            log_safe_exception(
                logger,
                "LLM insight polish failed; using rule insights only",
                exc,
                error_code="portfolio_health_llm_polish_failed",
            )
            return base
        if not isinstance(polished, (list, tuple)):
            return base
        return apply_llm_polish(base, polished)

    @staticmethod
    def _missing_price_symbols(snapshot: Mapping[str, Any]) -> List[str]:
        missing: List[str] = []
        for account in snapshot.get("accounts", []) or []:
            for pos in account.get("positions", []) or []:
                symbol = str(pos.get("symbol") or "").strip().upper()
                if not symbol:
                    continue
                mv = float(pos.get("market_value_base") or 0.0)
                price_stale = bool(pos.get("price_stale"))
                qty = float(pos.get("quantity") or pos.get("qty") or 0.0)
                # Held quantity without usable market value or explicitly stale price.
                if qty > _EPS and (mv <= _EPS or price_stale):
                    missing.append(symbol)
                elif price_stale:
                    missing.append(symbol)
        # de-dupe preserve order
        seen = set()
        ordered: List[str] = []
        for symbol in missing:
            if symbol not in seen:
                seen.add(symbol)
                ordered.append(symbol)
        return ordered

    @staticmethod
    def _empty_dimensions() -> Dict[str, Dict[str, Any]]:
        return {
            key: {"status": "unavailable", "score": None, "reason": "empty_portfolio"}
            for key in DIMENSION_KEYS
        }
