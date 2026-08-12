# -*- coding: utf-8 -*-
"""Deterministic portfolio rebalancing and risk-adjusted position bands.

Issues #237 (allocation / rebalancing recommendations) and #126
(portfolio-aware position sizing).

Hard contract:
- Suggestions only — never executes trades or mutates the ledger.
- Every non-empty suggestion carries rationale + assumptions + top-level
  not-investment-advice disclaimer.
- Insufficient data / empty portfolio → explicit refusal (no invented trades).
- Weights use base-currency market values from the portfolio snapshot
  (cross-currency already normalized by PortfolioService via market_value_base).
- All numeric inputs and outputs must be finite; NaN/Inf are rejected.
- No market-data provider calls on the hot path.
"""

from __future__ import annotations

import logging
import math
import os
from datetime import date
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from src.services.portfolio_risk_metrics_service import (
    DEFAULT_CONFIDENCE,
    DEFAULT_HORIZON_DAYS,
    DEFAULT_LOOKBACK_TRADING_DAYS,
    PortfolioRiskMetricsService,
)
from src.services.portfolio_service import PortfolioService

logger = logging.getLogger(__name__)

_EPS = 1e-12
METHOD_VERSION = "risk_band_drift_v1"

RISK_TOLERANCE_VALUES = ("conservative", "moderate", "aggressive")
DEFAULT_RISK_TOLERANCE = "moderate"
DEFAULT_DRIFT_THRESHOLD_PCT = 5.0

# Soft global single-name cap used by portfolio-aware sizing (#126).
# Risk-band caps may be tighter or looser; effective cap = min(band, soft).
DEFAULT_MAX_SINGLE_NAME_WEIGHT = 0.15
DEFAULT_PORTFOLIO_AWARE_SIZING_ENABLED = True

DISCLAIMER = (
    "Research aid only — not investment advice. Rebalancing and position-band "
    "outputs are deterministic rule suggestions for human review; they do not "
    "execute trades, optimize taxes, or replace personal judgment."
)

# Risk-band target model (documented in docs/portfolio-rebalancing*.md).
# max_single_weight_pct is percent points (e.g. 25.0 means 25%).
RISK_BANDS: Dict[str, Dict[str, float]] = {
    "conservative": {
        "max_single_weight_pct": 15.0,
        "min_effective_n": 6.0,
        "max_hhi": 0.22,
        "target_var_pct_ceiling": 2.0,
    },
    "moderate": {
        "max_single_weight_pct": 25.0,
        "min_effective_n": 4.0,
        "max_hhi": 0.35,
        "target_var_pct_ceiling": 3.5,
    },
    "aggressive": {
        "max_single_weight_pct": 40.0,
        "min_effective_n": 2.5,
        "max_hhi": 0.50,
        "target_var_pct_ceiling": 6.0,
    },
}

# Signal → fraction of the effective single-name cap for target midpoint.
_SIGNAL_CAP_FRACTIONS: Dict[str, float] = {
    "buy": 0.85,
    "strong_buy": 1.0,
    "hold": 0.55,
    "watch": 0.45,
    "sell": 0.15,
    "reduce": 0.20,
    "strong_sell": 0.0,
    "exit": 0.0,
}

COMMON_ASSUMPTIONS = [
    "Static current market-value weights in the portfolio base currency; cash excluded.",
    "Targets are rule-based risk bands, not personal financial advice.",
    "Tax lots, commissions, and market impact are not modeled (not_modeled_v1).",
    "Suggestions are for human review only and are never auto-executed.",
]


def _finite_number(
    value: Any,
    field: str,
    *,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} must be a finite number")
    if minimum is not None and number < minimum:
        raise ValueError(f"{field} must be >= {minimum}")
    if maximum is not None and number > maximum:
        raise ValueError(f"{field} must be <= {maximum}")
    return number


def _optional_env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    text = str(raw).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean (true/false)")


def _optional_env_float(
    name: str,
    default: float,
    *,
    minimum: float,
    maximum: float,
) -> float:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    return _finite_number(raw, name, minimum=minimum, maximum=maximum)


def normalize_risk_tolerance(value: Any) -> str:
    text = str(value or DEFAULT_RISK_TOLERANCE).strip().lower()
    if text not in RISK_TOLERANCE_VALUES:
        raise ValueError(
            "risk_tolerance must be one of: "
            + ", ".join(RISK_TOLERANCE_VALUES)
        )
    return text


def risk_band_for(risk_tolerance: str) -> Dict[str, float]:
    key = normalize_risk_tolerance(risk_tolerance)
    return dict(RISK_BANDS[key])


def resolve_soft_max_single_name_weight(
    override: Optional[float] = None,
) -> float:
    """Return soft max single-name weight as a fraction in (0, 1]."""
    if override is not None:
        return _finite_number(
            override,
            "max_single_name_weight",
            minimum=_EPS,
            maximum=1.0,
        )
    return _optional_env_float(
        "PORTFOLIO_MAX_SINGLE_NAME_WEIGHT",
        DEFAULT_MAX_SINGLE_NAME_WEIGHT,
        minimum=_EPS,
        maximum=1.0,
    )


def is_portfolio_aware_sizing_enabled(
    override: Optional[bool] = None,
) -> bool:
    if override is not None:
        return bool(override)
    return _optional_env_bool(
        "PORTFOLIO_AWARE_SIZING_ENABLED",
        DEFAULT_PORTFOLIO_AWARE_SIZING_ENABLED,
    )


def effective_single_name_cap_pct(
    *,
    risk_tolerance: str,
    soft_max_weight: Optional[float] = None,
) -> float:
    """Effective single-name cap in percent points = min(band, soft*100)."""
    band = risk_band_for(risk_tolerance)
    band_cap = _finite_number(
        band["max_single_weight_pct"],
        "max_single_weight_pct",
        minimum=_EPS,
        maximum=100.0,
    )
    soft = resolve_soft_max_single_name_weight(soft_max_weight)
    soft_pct = soft * 100.0
    return min(band_cap, soft_pct)


def _normalize_signal(signal: Any) -> str:
    text = str(signal or "hold").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "strongbuy": "strong_buy",
        "strongsell": "strong_sell",
        "add": "buy",
        "long": "buy",
        "short": "sell",
        "trim": "reduce",
        "neutral": "hold",
    }
    return aliases.get(text, text)


def weights_from_snapshot(
    snapshot: Mapping[str, Any],
) -> Tuple[Dict[str, float], float, str]:
    """Build equity weights from base-currency market values.

    Cross-currency holdings are already normalized into ``market_value_base``
    by PortfolioService; this function never mixes raw local currencies.
    Non-finite market values are rejected.
    """
    currency = str(snapshot.get("currency") or "CNY").strip().upper() or "CNY"
    exposure: Dict[str, float] = {}
    for account in snapshot.get("accounts", []) or []:
        for pos in account.get("positions", []) or []:
            symbol = str(pos.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            mv = _finite_number(
                pos.get("market_value_base") or 0.0,
                f"position.{symbol}.market_value_base",
            )
            if mv <= _EPS:
                continue
            exposure[symbol] = exposure.get(symbol, 0.0) + mv

    total = sum(exposure.values())
    if total <= _EPS or not math.isfinite(total):
        return {}, 0.0, currency
    weights = {
        symbol: value / total
        for symbol, value in sorted(exposure.items())
    }
    for symbol, weight in weights.items():
        _finite_number(weight, f"weight.{symbol}", minimum=0.0, maximum=1.0)
    return weights, total, currency


def current_weight_pct(
    weights: Mapping[str, float],
    symbol: str,
) -> float:
    key = str(symbol or "").strip().upper()
    if not key:
        return 0.0
    return _finite_number(
        float(weights.get(key, 0.0)) * 100.0,
        f"weight_pct.{key}",
        minimum=0.0,
        maximum=100.0,
    )


def avg_pairwise_correlation(
    *,
    symbol: str,
    symbols: Sequence[str],
    matrix: Sequence[Sequence[Optional[float]]],
) -> Optional[float]:
    """Average correlation of symbol to other names; None when unavailable."""
    key = str(symbol or "").strip().upper()
    ordered = [str(s).strip().upper() for s in symbols]
    if key not in ordered or not matrix:
        return None
    idx = ordered.index(key)
    if idx >= len(matrix):
        return None
    row = matrix[idx]
    values: List[float] = []
    for j, other in enumerate(ordered):
        if j == idx or j >= len(row):
            continue
        cell = row[j]
        if cell is None:
            continue
        try:
            value = _finite_number(cell, f"corr.{key}.{other}", minimum=-1.0, maximum=1.0)
        except ValueError:
            continue
        values.append(value)
    if not values:
        return None
    avg = sum(values) / len(values)
    return _finite_number(avg, f"avg_corr.{key}", minimum=-1.0, maximum=1.0)


def compute_position_band(
    *,
    symbol: str,
    current_weight_pct_value: float,
    risk_tolerance: str = DEFAULT_RISK_TOLERANCE,
    signal: str = "hold",
    soft_max_weight: Optional[float] = None,
    portfolio_aware_enabled: Optional[bool] = None,
    has_portfolio: bool = True,
) -> Dict[str, Any]:
    """Deterministic risk-adjusted target weight band for one name.

    When portfolio data is unavailable or sizing is disabled, falls back to a
    stock-only band using the risk-band single-name cap (still explainable).
    """
    sym = str(symbol or "").strip().upper()
    if not sym:
        raise ValueError("symbol is required")

    current = _finite_number(
        current_weight_pct_value,
        "current_weight_pct",
        minimum=0.0,
        maximum=100.0,
    )
    enabled = is_portfolio_aware_sizing_enabled(portfolio_aware_enabled)
    signal_norm = _normalize_signal(signal)
    fraction = _SIGNAL_CAP_FRACTIONS.get(signal_norm, 0.55)
    fraction = _finite_number(fraction, "signal_cap_fraction", minimum=0.0, maximum=1.0)

    if enabled and has_portfolio:
        cap_pct = effective_single_name_cap_pct(
            risk_tolerance=risk_tolerance,
            soft_max_weight=soft_max_weight,
        )
        mode = "portfolio_aware"
    else:
        band = risk_band_for(risk_tolerance)
        cap_pct = _finite_number(
            band["max_single_weight_pct"],
            "max_single_weight_pct",
            minimum=_EPS,
            maximum=100.0,
        )
        mode = "stock_only_fallback" if not has_portfolio else "sizing_disabled"

    target_mid = round(cap_pct * fraction, 6)
    half_width = max(1.0, min(cap_pct * 0.30, max(target_mid * 0.30, 1.0)))
    low = max(0.0, round(target_mid - half_width, 6))
    high = min(cap_pct, round(target_mid + half_width, 6))
    if high < low:
        high = low

    action = _action_for_band(current=current, low=low, high=high, signal=signal_norm)
    rationale = (
        f"{sym}: current weight {current:.2f}% vs target band "
        f"[{low:.2f}%, {high:.2f}%] (mid {target_mid:.2f}%) under "
        f"risk_tolerance={normalize_risk_tolerance(risk_tolerance)}, "
        f"signal={signal_norm}, effective_cap={cap_pct:.2f}%, mode={mode}."
    )
    return {
        "symbol": sym,
        "action": action,
        "current_weight_pct": round(current, 6),
        "target_weight_pct_low": low,
        "target_weight_pct_mid": target_mid,
        "target_weight_pct_high": high,
        "effective_cap_pct": round(cap_pct, 6),
        "signal": signal_norm,
        "mode": mode,
        "rationale": rationale,
        "assumptions": list(COMMON_ASSUMPTIONS)
        + [
            f"Signal-to-cap fraction for '{signal_norm}' is {fraction:.2f}.",
            f"Effective single-name cap is min(risk_band, soft_max) = {cap_pct:.2f}%.",
        ],
        "is_suggestion_only": True,
        "auto_execute": False,
    }


def _action_for_band(
    *,
    current: float,
    low: float,
    high: float,
    signal: str,
) -> str:
    if signal in {"exit", "strong_sell"} or (high <= _EPS and current > _EPS):
        return "exit" if current > _EPS else "hold"
    if current > high + _EPS:
        return "reduce"
    if current < low - _EPS:
        return "add"
    return "hold"


def build_breaches(
    *,
    weights_pct: Mapping[str, float],
    risk_tolerance: str,
    concentration: Mapping[str, Any],
    var_pct: Optional[float],
    soft_max_weight: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Detect concentration / band breaches with numeric evidence."""
    band = risk_band_for(risk_tolerance)
    cap = effective_single_name_cap_pct(
        risk_tolerance=risk_tolerance,
        soft_max_weight=soft_max_weight,
    )
    breaches: List[Dict[str, Any]] = []

    for symbol, weight_pct in sorted(
        weights_pct.items(),
        key=lambda item: (-item[1], item[0]),
    ):
        w = _finite_number(weight_pct, f"weight_pct.{symbol}", minimum=0.0, maximum=100.0)
        if w > cap + _EPS:
            breaches.append(
                {
                    "kind": "single_name_cap",
                    "symbol": symbol,
                    "current_pct": round(w, 6),
                    "limit_pct": round(cap, 6),
                    "drift_pct": round(w - cap, 6),
                }
            )

    hhi = concentration.get("hhi")
    effective_n = concentration.get("effective_n")
    if hhi is not None:
        hhi_f = _finite_number(hhi, "hhi", minimum=0.0, maximum=1.0)
        max_hhi = _finite_number(band["max_hhi"], "max_hhi", minimum=0.0, maximum=1.0)
        if hhi_f > max_hhi + _EPS:
            breaches.append(
                {
                    "kind": "hhi_ceiling",
                    "symbol": None,
                    "current_pct": round(hhi_f, 6),
                    "limit_pct": round(max_hhi, 6),
                    "drift_pct": round(hhi_f - max_hhi, 6),
                }
            )
    if effective_n is not None:
        n_f = _finite_number(effective_n, "effective_n", minimum=0.0)
        min_n = _finite_number(band["min_effective_n"], "min_effective_n", minimum=0.0)
        if n_f + _EPS < min_n:
            breaches.append(
                {
                    "kind": "effective_n_floor",
                    "symbol": None,
                    "current_pct": round(n_f, 6),
                    "limit_pct": round(min_n, 6),
                    "drift_pct": round(min_n - n_f, 6),
                }
            )

    if var_pct is not None:
        var_f = _finite_number(var_pct, "var_pct", minimum=0.0)
        ceiling = _finite_number(
            band["target_var_pct_ceiling"],
            "target_var_pct_ceiling",
            minimum=0.0,
        )
        if var_f > ceiling + _EPS:
            breaches.append(
                {
                    "kind": "var_ceiling",
                    "symbol": None,
                    "current_pct": round(var_f, 6),
                    "limit_pct": round(ceiling, 6),
                    "drift_pct": round(var_f - ceiling, 6),
                }
            )
    return breaches


def build_rebalance_suggestions(
    *,
    weights_pct: Mapping[str, float],
    portfolio_value: float,
    risk_tolerance: str,
    drift_threshold_pct: float,
    breaches: Sequence[Mapping[str, Any]],
    correlation: Optional[Mapping[str, Any]] = None,
    soft_max_weight: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Build trim suggestions for hard single-name caps and risk breaches.

    V1 emits trims only (deterministic). Residual redistribution is noted in
    assumptions rather than inventing add targets without investable universe.
    """
    cap = effective_single_name_cap_pct(
        risk_tolerance=risk_tolerance,
        soft_max_weight=soft_max_weight,
    )
    threshold = _finite_number(
        drift_threshold_pct,
        "drift_threshold_pct",
        minimum=0.0,
        maximum=100.0,
    )
    value = _finite_number(portfolio_value, "portfolio_value", minimum=0.0)

    corr_symbols: List[str] = []
    corr_matrix: List[List[Optional[float]]] = []
    if correlation and str(correlation.get("status") or "") == "ok":
        corr_symbols = [str(s).strip().upper() for s in (correlation.get("symbols") or [])]
        raw_matrix = correlation.get("matrix") or []
        if isinstance(raw_matrix, list):
            corr_matrix = raw_matrix  # type: ignore[assignment]

    candidates: List[Tuple[float, float, str, float]] = []
    for symbol, weight_pct in weights_pct.items():
        w = _finite_number(weight_pct, f"weight_pct.{symbol}", minimum=0.0, maximum=100.0)
        avg_corr = avg_pairwise_correlation(
            symbol=symbol,
            symbols=corr_symbols,
            matrix=corr_matrix,
        )
        corr_key = avg_corr if avg_corr is not None else -2.0
        candidates.append((w, corr_key, symbol, avg_corr if avg_corr is not None else float("nan")))

    candidates.sort(key=lambda row: (-row[0], -row[1], row[2]))

    hard_cap_symbols = {
        str(b.get("symbol") or "").strip().upper()
        for b in breaches
        if b.get("kind") == "single_name_cap" and b.get("symbol")
    }
    needs_diversify = any(
        b.get("kind") in {"hhi_ceiling", "effective_n_floor", "var_ceiling"}
        for b in breaches
    )

    suggestions: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for weight_pct, _corr_key, symbol, avg_corr in candidates:
        if symbol in seen:
            continue
        hard = symbol in hard_cap_symbols
        over_cap = weight_pct - cap
        if hard or over_cap > threshold + _EPS:
            target = cap
            delta = target - weight_pct
            if abs(delta) < threshold - _EPS and not hard:
                continue
            if abs(delta) <= _EPS:
                continue
            rationale = (
                f"Trim {symbol}: weight {weight_pct:.2f}% exceeds effective "
                f"single-name cap {cap:.2f}% for risk_tolerance="
                f"{normalize_risk_tolerance(risk_tolerance)} "
                f"(drift {weight_pct - cap:.2f} pp)."
            )
            if avg_corr == avg_corr:  # not NaN
                rationale += f" Average pairwise correlation {avg_corr:.3f}."
            suggestions.append(
                _suggestion_row(
                    action="trim",
                    symbol=symbol,
                    from_weight_pct=weight_pct,
                    to_weight_pct=target,
                    portfolio_value=value,
                    rationale=rationale,
                    extra_assumptions=[
                        f"Hard single-name cap breach={hard}.",
                    ],
                )
            )
            seen.add(symbol)
            continue

        if needs_diversify and weight_pct > cap * 0.75 and weight_pct > threshold:
            target = max(cap * 0.75, weight_pct - max(threshold, weight_pct * 0.15))
            target = min(target, weight_pct)
            delta = target - weight_pct
            if abs(delta) < threshold - _EPS:
                continue
            rationale = (
                f"Trim {symbol} for diversification / risk-band pressure: "
                f"weight {weight_pct:.2f}% contributes to HHI/effective_n/VaR "
                f"breach under risk_tolerance="
                f"{normalize_risk_tolerance(risk_tolerance)}; "
                f"suggest {target:.2f}% (delta {delta:.2f} pp)."
            )
            if avg_corr == avg_corr:
                rationale += f" Average pairwise correlation {avg_corr:.3f}."
            suggestions.append(
                _suggestion_row(
                    action="trim",
                    symbol=symbol,
                    from_weight_pct=weight_pct,
                    to_weight_pct=target,
                    portfolio_value=value,
                    rationale=rationale,
                    extra_assumptions=[
                        "Diversifying trim: residual capital is not auto-reallocated "
                        "to other names in V1 (no investable universe).",
                    ],
                )
            )
            seen.add(symbol)

    return suggestions


def _suggestion_row(
    *,
    action: str,
    symbol: str,
    from_weight_pct: float,
    to_weight_pct: float,
    portfolio_value: float,
    rationale: str,
    extra_assumptions: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    frm = _finite_number(from_weight_pct, "from_weight_pct", minimum=0.0, maximum=100.0)
    to = _finite_number(to_weight_pct, "to_weight_pct", minimum=0.0, maximum=100.0)
    delta = round(to - frm, 6)
    notional = round(portfolio_value * (delta / 100.0), 6) if portfolio_value > _EPS else 0.0
    _finite_number(notional, "approx_notional")
    assumptions = list(COMMON_ASSUMPTIONS)
    if extra_assumptions:
        assumptions.extend(str(a) for a in extra_assumptions)
    return {
        "action": action,
        "symbol": symbol,
        "from_weight_pct": round(frm, 6),
        "to_weight_pct": round(to, 6),
        "delta_weight_pct": delta,
        "approx_notional": notional,
        "rationale": rationale,
        "assumptions": assumptions,
        "is_suggestion_only": True,
        "auto_execute": False,
    }


class PortfolioRebalancingService:
    """Read-only rebalancing + risk-adjusted position band recommendations."""

    def __init__(
        self,
        *,
        portfolio_service: Optional[PortfolioService] = None,
        risk_metrics_service: Optional[PortfolioRiskMetricsService] = None,
    ) -> None:
        self.portfolio_service = portfolio_service or PortfolioService()
        self.risk_metrics_service = risk_metrics_service or PortfolioRiskMetricsService(
            portfolio_service=self.portfolio_service
        )

    def get_recommendations(
        self,
        *,
        account_id: Optional[int] = None,
        as_of: Optional[date] = None,
        cost_method: str = "fifo",
        risk_tolerance: str = DEFAULT_RISK_TOLERANCE,
        drift_threshold_pct: float = DEFAULT_DRIFT_THRESHOLD_PCT,
        confidence: float = DEFAULT_CONFIDENCE,
        horizon_days: int = DEFAULT_HORIZON_DAYS,
        lookback_trading_days: int = DEFAULT_LOOKBACK_TRADING_DAYS,
        soft_max_weight: Optional[float] = None,
        portfolio_aware_enabled: Optional[bool] = None,
        snapshot: Optional[Mapping[str, Any]] = None,
        risk_metrics: Optional[Mapping[str, Any]] = None,
        stock_signals: Optional[Mapping[str, str]] = None,
    ) -> Dict[str, Any]:
        as_of_date = as_of or date.today()
        tolerance = normalize_risk_tolerance(risk_tolerance)
        threshold = _finite_number(
            drift_threshold_pct,
            "drift_threshold_pct",
            minimum=0.0,
            maximum=100.0,
        )
        band = risk_band_for(tolerance)
        cap_pct = effective_single_name_cap_pct(
            risk_tolerance=tolerance,
            soft_max_weight=soft_max_weight,
        )
        soft_frac = resolve_soft_max_single_name_weight(soft_max_weight)
        sizing_enabled = is_portfolio_aware_sizing_enabled(portfolio_aware_enabled)

        snapshot_payload = snapshot
        if snapshot_payload is None:
            snapshot_payload = self.portfolio_service.get_portfolio_snapshot(
                account_id=account_id,
                as_of=as_of_date,
                cost_method=cost_method,
                include_realtime=False,
            )

        weights, total_mv, currency = weights_from_snapshot(snapshot_payload)
        weights_pct = {
            symbol: _finite_number(w * 100.0, f"weight_pct.{symbol}", minimum=0.0, maximum=100.0)
            for symbol, w in weights.items()
        }

        base: Dict[str, Any] = {
            "as_of": as_of_date.isoformat(),
            "account_id": account_id,
            "cost_method": cost_method,
            "currency": currency,
            "disclaimer": DISCLAIMER,
            "risk_tolerance": tolerance,
            "is_suggestion_only": True,
            "auto_execute": False,
            "target_model": {
                "name": "risk_band_v1",
                "description": (
                    "Rule-based risk bands for single-name cap, HHI, effective N, "
                    "and illustrative VaR ceiling. Not mean-variance optimization."
                ),
                "max_single_weight_pct": round(cap_pct, 6),
                "band_max_single_weight_pct": round(band["max_single_weight_pct"], 6),
                "soft_max_single_name_weight": round(soft_frac, 6),
                "min_effective_n": band["min_effective_n"],
                "max_hhi": band["max_hhi"],
                "target_var_pct_ceiling": band["target_var_pct_ceiling"],
                "notes": [
                    "Effective single-name cap = min(risk_band cap, PORTFOLIO_MAX_SINGLE_NAME_WEIGHT*100).",
                    "Cash is excluded from equity weights.",
                    "Cross-currency positions use market_value_base (snapshot base currency).",
                ],
            },
            "assumptions": {
                "method": METHOD_VERSION,
                "uses_risk_metrics": True,
                "risk_metrics_source": "PortfolioRiskMetricsService",
                "provider_calls_on_hot_path": False,
                "tax_and_transaction_costs": "not_modeled_v1",
                "recommendation_honesty": "explicit_refusal_when_insufficient_data",
                "weight_basis": "market_value_base",
                "cross_currency": "normalized_via_portfolio_snapshot_market_value_base",
                "portfolio_aware_sizing_enabled": sizing_enabled,
                "drift_threshold_pct": threshold,
            },
        }

        if not weights or total_mv <= _EPS:
            return {
                **base,
                "status": "empty_portfolio",
                "status_message": "No held equity positions with positive market value.",
                "current": {
                    "portfolio_value": 0.0,
                    "weights": [],
                    "risk_status": "empty_portfolio",
                    "var_pct": None,
                    "hhi": None,
                    "effective_n": None,
                    "diversification_score": None,
                },
                "drift": {"max_abs_weight_drift_pct": 0.0, "breaches": []},
                "suggestions": [],
                "position_bands": [],
                "risk_metrics_summary": {
                    "status": "empty_portfolio",
                    "var_status": "unavailable",
                    "correlation_status": "unavailable",
                    "concentration_status": "empty_portfolio",
                },
            }

        risk_payload = risk_metrics
        if risk_payload is None:
            risk_payload = self.risk_metrics_service.get_risk_metrics(
                account_id=account_id,
                as_of=as_of_date,
                cost_method=cost_method,
                confidence=confidence,
                horizon_days=horizon_days,
                lookback_trading_days=lookback_trading_days,
                snapshot=snapshot_payload,
            )

        risk_status = str(risk_payload.get("status") or "")
        var_block = dict(risk_payload.get("var") or {})
        corr_block = dict(risk_payload.get("correlation") or {})
        conc_block = dict(risk_payload.get("concentration") or {})
        var_status = str(var_block.get("status") or "")
        corr_status = str(corr_block.get("status") or "")
        conc_status = str(conc_block.get("status") or "")

        if risk_status == "empty_portfolio" or conc_status == "empty_portfolio":
            return {
                **base,
                "status": "empty_portfolio",
                "status_message": "Risk metrics reported an empty portfolio; no suggestions.",
                "current": self._current_block(
                    weights_pct=weights_pct,
                    portfolio_value=total_mv,
                    risk_status=risk_status,
                    var_block=var_block,
                    conc_block=conc_block,
                ),
                "drift": {"max_abs_weight_drift_pct": 0.0, "breaches": []},
                "suggestions": [],
                "position_bands": [],
                "risk_metrics_summary": {
                    "status": risk_status,
                    "var_status": var_status,
                    "correlation_status": corr_status,
                    "concentration_status": conc_status,
                },
            }

        if var_status == "insufficient_history" or risk_status == "insufficient_history":
            return {
                **base,
                "status": "insufficient_data",
                "status_message": (
                    "Insufficient risk-metrics history to form honest rebalancing "
                    "recommendations; refused rather than inventing trades."
                ),
                "current": self._current_block(
                    weights_pct=weights_pct,
                    portfolio_value=total_mv,
                    risk_status=risk_status,
                    var_block=var_block,
                    conc_block=conc_block,
                ),
                "drift": {"max_abs_weight_drift_pct": 0.0, "breaches": []},
                "suggestions": [],
                "position_bands": self._position_bands(
                    weights_pct=weights_pct,
                    risk_tolerance=tolerance,
                    soft_max_weight=soft_max_weight,
                    sizing_enabled=sizing_enabled,
                    stock_signals=stock_signals,
                ),
                "risk_metrics_summary": {
                    "status": risk_status,
                    "var_status": var_status,
                    "correlation_status": corr_status,
                    "concentration_status": conc_status,
                },
            }

        if conc_status != "ok":
            return {
                **base,
                "status": "insufficient_data",
                "status_message": (
                    "Concentration metrics unavailable; refused rather than inventing weights."
                ),
                "current": self._current_block(
                    weights_pct=weights_pct,
                    portfolio_value=total_mv,
                    risk_status=risk_status,
                    var_block=var_block,
                    conc_block=conc_block,
                ),
                "drift": {"max_abs_weight_drift_pct": 0.0, "breaches": []},
                "suggestions": [],
                "position_bands": self._position_bands(
                    weights_pct=weights_pct,
                    risk_tolerance=tolerance,
                    soft_max_weight=soft_max_weight,
                    sizing_enabled=sizing_enabled,
                    stock_signals=stock_signals,
                ),
                "risk_metrics_summary": {
                    "status": risk_status,
                    "var_status": var_status,
                    "correlation_status": corr_status,
                    "concentration_status": conc_status,
                },
            }

        var_pct = var_block.get("var_pct")
        if var_pct is not None:
            var_pct = _finite_number(var_pct, "var.var_pct", minimum=0.0)

        conc_weights = conc_block.get("weights") or []
        if conc_weights:
            rebuilt: Dict[str, float] = {}
            for item in conc_weights:
                if not isinstance(item, Mapping):
                    continue
                sym = str(item.get("symbol") or "").strip().upper()
                if not sym:
                    continue
                rebuilt[sym] = _finite_number(
                    item.get("weight_pct") or 0.0,
                    f"concentration.weight_pct.{sym}",
                    minimum=0.0,
                    maximum=100.0,
                )
            if rebuilt:
                weights_pct = rebuilt

        breaches = build_breaches(
            weights_pct=weights_pct,
            risk_tolerance=tolerance,
            concentration=conc_block,
            var_pct=var_pct if var_status == "ok" else None,
            soft_max_weight=soft_max_weight,
        )
        suggestions = build_rebalance_suggestions(
            weights_pct=weights_pct,
            portfolio_value=total_mv,
            risk_tolerance=tolerance,
            drift_threshold_pct=threshold,
            breaches=breaches,
            correlation=corr_block if corr_status == "ok" else None,
            soft_max_weight=soft_max_weight,
        )
        position_bands = self._position_bands(
            weights_pct=weights_pct,
            risk_tolerance=tolerance,
            soft_max_weight=soft_max_weight,
            sizing_enabled=sizing_enabled,
            stock_signals=stock_signals,
        )

        max_drift = 0.0
        for b in breaches:
            max_drift = max(
                max_drift,
                abs(_finite_number(b.get("drift_pct") or 0.0, "breach.drift_pct")),
            )
        for s in suggestions:
            max_drift = max(
                max_drift,
                abs(_finite_number(s.get("delta_weight_pct") or 0.0, "delta_weight_pct")),
            )

        if suggestions:
            status = "ok"
            status_message = (
                f"{len(suggestions)} rebalancing suggestion(s) for human review "
                f"(not auto-executed)."
            )
        else:
            status = "ok"
            status_message = (
                "Portfolio weights and risk metrics are within the selected risk band "
                "and drift threshold; no rebalancing suggestion."
            )

        return {
            **base,
            "status": status,
            "status_message": status_message,
            "current": self._current_block(
                weights_pct=weights_pct,
                portfolio_value=total_mv,
                risk_status=risk_status,
                var_block=var_block,
                conc_block=conc_block,
            ),
            "drift": {
                "max_abs_weight_drift_pct": round(max_drift, 6),
                "breaches": list(breaches),
            },
            "suggestions": suggestions,
            "position_bands": position_bands,
            "risk_metrics_summary": {
                "status": risk_status,
                "var_status": var_status,
                "correlation_status": corr_status,
                "concentration_status": conc_status,
            },
        }

    def suggest_position_for_symbol(
        self,
        *,
        symbol: str,
        signal: str = "hold",
        risk_tolerance: str = DEFAULT_RISK_TOLERANCE,
        account_id: Optional[int] = None,
        as_of: Optional[date] = None,
        cost_method: str = "fifo",
        soft_max_weight: Optional[float] = None,
        portfolio_aware_enabled: Optional[bool] = None,
        snapshot: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Portfolio-aware (or stock-only fallback) band for one symbol."""
        as_of_date = as_of or date.today()
        snapshot_payload = snapshot
        has_portfolio = True
        weights_pct: Dict[str, float] = {}
        currency: Optional[str] = "CNY"
        try:
            if snapshot_payload is None:
                snapshot_payload = self.portfolio_service.get_portfolio_snapshot(
                    account_id=account_id,
                    as_of=as_of_date,
                    cost_method=cost_method,
                    include_realtime=False,
                )
            weights, total_mv, currency = weights_from_snapshot(snapshot_payload)
            if not weights or total_mv <= _EPS:
                has_portfolio = False
            else:
                weights_pct = {
                    s: _finite_number(w * 100.0, f"weight_pct.{s}", minimum=0.0, maximum=100.0)
                    for s, w in weights.items()
                }
        except Exception as exc:  # broad-exception: fallback_recorded - stock-only sizing
            logger.debug("Portfolio snapshot unavailable for sizing: %s", exc)
            has_portfolio = False
            currency = None

        sym = str(symbol or "").strip().upper()
        current = current_weight_pct(weights_pct, sym) if has_portfolio else 0.0
        band = compute_position_band(
            symbol=sym,
            current_weight_pct_value=current,
            risk_tolerance=risk_tolerance,
            signal=signal,
            soft_max_weight=soft_max_weight,
            portfolio_aware_enabled=portfolio_aware_enabled,
            has_portfolio=has_portfolio,
        )
        return {
            **band,
            "as_of": as_of_date.isoformat(),
            "account_id": account_id,
            "currency": currency if has_portfolio else None,
            "disclaimer": DISCLAIMER,
            "has_portfolio": has_portfolio,
        }

    @staticmethod
    def _current_block(
        *,
        weights_pct: Mapping[str, float],
        portfolio_value: float,
        risk_status: str,
        var_block: Mapping[str, Any],
        conc_block: Mapping[str, Any],
    ) -> Dict[str, Any]:
        weights_list = [
            {
                "symbol": symbol,
                "weight_pct": round(
                    _finite_number(w, f"weight_pct.{symbol}", minimum=0.0, maximum=100.0),
                    6,
                ),
            }
            for symbol, w in sorted(weights_pct.items(), key=lambda item: (-item[1], item[0]))
        ]
        var_pct = var_block.get("var_pct")
        if var_pct is not None:
            var_pct = round(_finite_number(var_pct, "var_pct", minimum=0.0), 6)
        hhi = conc_block.get("hhi")
        effective_n = conc_block.get("effective_n")
        diversification = conc_block.get("diversification_score")
        return {
            "portfolio_value": round(
                _finite_number(portfolio_value, "portfolio_value", minimum=0.0), 6
            ),
            "weights": weights_list,
            "risk_status": risk_status,
            "var_pct": var_pct,
            "hhi": (
                round(_finite_number(hhi, "hhi", minimum=0.0, maximum=1.0), 6)
                if hhi is not None
                else None
            ),
            "effective_n": (
                round(_finite_number(effective_n, "effective_n", minimum=0.0), 6)
                if effective_n is not None
                else None
            ),
            "diversification_score": (
                round(
                    _finite_number(
                        diversification,
                        "diversification_score",
                        minimum=0.0,
                        maximum=1.0,
                    ),
                    6,
                )
                if diversification is not None
                else None
            ),
        }

    @staticmethod
    def _position_bands(
        *,
        weights_pct: Mapping[str, float],
        risk_tolerance: str,
        soft_max_weight: Optional[float],
        sizing_enabled: bool,
        stock_signals: Optional[Mapping[str, str]],
    ) -> List[Dict[str, Any]]:
        signals = {
            str(k).strip().upper(): str(v)
            for k, v in (stock_signals or {}).items()
            if str(k or "").strip()
        }
        bands: List[Dict[str, Any]] = []
        for symbol, weight_pct in sorted(
            weights_pct.items(), key=lambda item: (-item[1], item[0])
        ):
            signal = signals.get(symbol, "hold")
            bands.append(
                compute_position_band(
                    symbol=symbol,
                    current_weight_pct_value=weight_pct,
                    risk_tolerance=risk_tolerance,
                    signal=signal,
                    soft_max_weight=soft_max_weight,
                    portfolio_aware_enabled=sizing_enabled,
                    has_portfolio=True,
                )
            )
        return bands
