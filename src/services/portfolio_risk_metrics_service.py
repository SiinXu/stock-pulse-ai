# -*- coding: utf-8 -*-
"""Portfolio risk metrics: historical VaR, correlation, concentration (issue #239 V0).

Complements the existing concentration/drawdown/stop-loss report in
``portfolio_risk_service.py``. This module is read-only over stored daily bars
and portfolio holdings — it never calls market data providers on the hot path.
"""

from __future__ import annotations

import logging
import math
from datetime import date, timedelta
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from src.repositories.stock_repo import StockRepository
from src.services.portfolio_service import PortfolioService

logger = logging.getLogger(__name__)

DEFAULT_CONFIDENCE = 0.95
DEFAULT_HORIZON_DAYS = 1
DEFAULT_LOOKBACK_TRADING_DAYS = 252
MIN_RETURN_OBSERVATIONS = 60
MIN_CORRELATION_OBSERVATIONS = 30
MAX_HORIZON_DAYS = 30
MAX_LOOKBACK_TRADING_DAYS = 1000
# Calendar buffer so weekend/holiday gaps still yield enough trading bars.
_LOOKBACK_CALENDAR_FACTOR = 1.7
_EPS = 1e-12


class PortfolioRiskMetricsService:
    """Compute portfolio-level risk metrics from stored data only."""

    def __init__(
        self,
        *,
        portfolio_service: Optional[PortfolioService] = None,
        stock_repo: Optional[StockRepository] = None,
    ) -> None:
        self.portfolio_service = portfolio_service or PortfolioService()
        self.stock_repo = stock_repo or StockRepository()

    def get_risk_metrics(
        self,
        *,
        account_id: Optional[int] = None,
        as_of: Optional[date] = None,
        cost_method: str = "fifo",
        confidence: float = DEFAULT_CONFIDENCE,
        horizon_days: int = DEFAULT_HORIZON_DAYS,
        lookback_trading_days: int = DEFAULT_LOOKBACK_TRADING_DAYS,
    ) -> Dict[str, Any]:
        as_of_date = as_of or date.today()
        confidence_norm = self._validate_confidence(confidence)
        horizon_norm = self._validate_horizon(horizon_days)
        lookback_norm = self._validate_lookback(lookback_trading_days)

        # include_realtime=False: no provider calls on the hot path.
        snapshot = self.portfolio_service.get_portfolio_snapshot(
            account_id=account_id,
            as_of=as_of_date,
            cost_method=cost_method,
            include_realtime=False,
        )
        currency = str(snapshot.get("currency") or "CNY")
        weights, total_mv, _symbols = self._position_weights(snapshot)

        assumptions = self._build_assumptions(
            confidence=confidence_norm,
            horizon_days=horizon_norm,
            lookback_trading_days=lookback_norm,
        )

        base: Dict[str, Any] = {
            "as_of": as_of_date.isoformat(),
            "account_id": account_id,
            "cost_method": cost_method,
            "currency": currency,
            "portfolio_value": round(total_mv, 6) if total_mv > _EPS else 0.0,
            "positions_used": len(weights),
            "assumptions": assumptions,
        }

        if not weights or total_mv <= _EPS:
            return {
                **base,
                "status": "empty_portfolio",
                "status_message": "No held equity positions with positive market value.",
                "var": self._empty_var_block(status="unavailable", message="empty_portfolio"),
                "correlation": self._empty_correlation_block(
                    status="unavailable",
                    message="empty_portfolio",
                ),
                "concentration": self._empty_concentration_block(status="empty_portfolio"),
            }

        concentration = compute_concentration_metrics(weights)
        price_series = self._load_close_series(
            symbols=list(weights.keys()),
            as_of=as_of_date,
            lookback_trading_days=lookback_norm,
        )
        aligned_dates, return_matrix, ordered_symbols = align_simple_returns(
            price_series,
            lookback_trading_days=lookback_norm,
        )
        observation_count = len(aligned_dates)

        portfolio_returns = build_portfolio_returns(
            return_matrix,
            ordered_symbols,
            weights,
        )

        var_block = compute_historical_var_block(
            portfolio_returns=portfolio_returns,
            portfolio_value=total_mv,
            confidence=confidence_norm,
            horizon_days=horizon_norm,
            min_observations=MIN_RETURN_OBSERVATIONS,
            observation_count=observation_count,
        )
        correlation_block = compute_correlation_block(
            return_matrix=return_matrix,
            symbols=ordered_symbols,
            min_observations=MIN_CORRELATION_OBSERVATIONS,
            observation_count=observation_count,
        )

        overall_status, status_message = self._overall_status(
            var_status=str(var_block["status"]),
            correlation_status=str(correlation_block["status"]),
            observation_count=observation_count,
            min_observations=MIN_RETURN_OBSERVATIONS,
        )

        return {
            **base,
            "status": overall_status,
            "status_message": status_message,
            "var": var_block,
            "correlation": correlation_block,
            "concentration": concentration,
            "history": {
                "aligned_trading_days": observation_count,
                "lookback_trading_days_requested": lookback_norm,
                "price_series_symbols": sorted(price_series.keys()),
                "aligned_start": aligned_dates[0].isoformat() if aligned_dates else None,
                "aligned_end": aligned_dates[-1].isoformat() if aligned_dates else None,
            },
        }

    @staticmethod
    def _validate_confidence(confidence: float) -> float:
        try:
            value = float(confidence)
        except (TypeError, ValueError) as exc:
            raise ValueError("confidence must be a number") from exc
        if not (0.5 < value < 1.0):
            raise ValueError("confidence must be strictly between 0.5 and 1.0 (exclusive)")
        return value

    @staticmethod
    def _validate_horizon(horizon_days: int) -> int:
        try:
            value = int(horizon_days)
        except (TypeError, ValueError) as exc:
            raise ValueError("horizon_days must be an integer") from exc
        if value < 1 or value > MAX_HORIZON_DAYS:
            raise ValueError(f"horizon_days must be between 1 and {MAX_HORIZON_DAYS}")
        return value

    @staticmethod
    def _validate_lookback(lookback_trading_days: int) -> int:
        try:
            value = int(lookback_trading_days)
        except (TypeError, ValueError) as exc:
            raise ValueError("lookback_trading_days must be an integer") from exc
        if value < MIN_RETURN_OBSERVATIONS or value > MAX_LOOKBACK_TRADING_DAYS:
            raise ValueError(
                f"lookback_trading_days must be between {MIN_RETURN_OBSERVATIONS} "
                f"and {MAX_LOOKBACK_TRADING_DAYS}"
            )
        return value

    @staticmethod
    def _build_assumptions(
        *,
        confidence: float,
        horizon_days: int,
        lookback_trading_days: int,
    ) -> Dict[str, Any]:
        return {
            "var_method": "historical",
            "confidence": confidence,
            "horizon_days": horizon_days,
            "lookback_trading_days": lookback_trading_days,
            "min_return_observations": MIN_RETURN_OBSERVATIONS,
            "min_correlation_observations": MIN_CORRELATION_OBSERVATIONS,
            "return_definition": "simple_close_to_close",
            "portfolio_aggregation": "static_current_market_value_weights",
            "cash_excluded": True,
            "weight_basis": "market_value_base",
            "horizon_scaling": (
                "sqrt_time_iid_assumption" if horizon_days > 1 else "none"
            ),
            "distribution_assumption": (
                "empirical historical distribution of portfolio simple returns; "
                "no parametric normality assumption for historical VaR"
            ),
            "correlation_method": "pearson",
            "concentration_metrics": "hhi_effective_n_normalized_diversification_score",
            "data_source": "stored_stock_daily_closes_and_portfolio_holdings",
            "provider_calls_on_hot_path": False,
        }

    def _position_weights(
        self,
        snapshot: Mapping[str, Any],
    ) -> Tuple[Dict[str, float], float, List[str]]:
        exposure: Dict[str, float] = {}
        for account in snapshot.get("accounts", []) or []:
            for pos in account.get("positions", []) or []:
                symbol = str(pos.get("symbol") or "").strip().upper()
                if not symbol:
                    continue
                mv = float(pos.get("market_value_base") or 0.0)
                if mv <= _EPS:
                    continue
                exposure[symbol] = exposure.get(symbol, 0.0) + mv

        total = sum(exposure.values())
        if total <= _EPS:
            return {}, 0.0, []
        weights = {symbol: value / total for symbol, value in sorted(exposure.items())}
        return weights, total, list(weights.keys())

    def _load_close_series(
        self,
        *,
        symbols: Sequence[str],
        as_of: date,
        lookback_trading_days: int,
    ) -> Dict[str, Dict[date, float]]:
        calendar_span = max(
            lookback_trading_days + 5,
            int(math.ceil(lookback_trading_days * _LOOKBACK_CALENDAR_FACTOR)),
        )
        start = as_of - timedelta(days=calendar_span)
        series: Dict[str, Dict[date, float]] = {}
        for symbol in symbols:
            rows = self.stock_repo.get_range(symbol, start, as_of)
            closes: Dict[date, float] = {}
            for row in rows or []:
                close = getattr(row, "close", None)
                row_date = getattr(row, "date", None)
                if close is None or row_date is None:
                    continue
                try:
                    close_f = float(close)
                except (TypeError, ValueError):
                    continue
                if close_f <= 0:
                    continue
                closes[row_date] = close_f
            if closes:
                series[symbol] = closes
        return series

    @staticmethod
    def _overall_status(
        *,
        var_status: str,
        correlation_status: str,
        observation_count: int,
        min_observations: int,
    ) -> Tuple[str, str]:
        if var_status == "ok" and correlation_status == "ok":
            return "ok", "Risk metrics computed from stored daily history."
        if observation_count < min_observations:
            return (
                "insufficient_history",
                (
                    f"Insufficient aligned trading-day history "
                    f"({observation_count} < {min_observations} required)."
                ),
            )
        if var_status != "ok" or correlation_status != "ok":
            return (
                "partial",
                "Some risk blocks could not be computed; see per-block status.",
            )
        return "ok", "Risk metrics computed from stored daily history."

    @staticmethod
    def _empty_var_block(*, status: str, message: str) -> Dict[str, Any]:
        return {
            "status": status,
            "status_message": message,
            "confidence": None,
            "horizon_days": None,
            "var_pct": None,
            "var_value": None,
            "observation_count": 0,
            "percentile_used": None,
        }

    @staticmethod
    def _empty_correlation_block(*, status: str, message: str) -> Dict[str, Any]:
        return {
            "status": status,
            "status_message": message,
            "symbols": [],
            "matrix": [],
            "observation_count": 0,
        }

    @staticmethod
    def _empty_concentration_block(*, status: str) -> Dict[str, Any]:
        return {
            "status": status,
            "hhi": None,
            "effective_n": None,
            "diversification_score": None,
            "top_weight_pct": None,
            "position_count": 0,
            "weights": [],
        }


def compute_simple_returns(closes: Sequence[float]) -> List[float]:
    """Close-to-close simple returns. Requires strictly positive closes."""
    if len(closes) < 2:
        return []
    returns: List[float] = []
    for prev, curr in zip(closes[:-1], closes[1:]):
        if prev <= 0:
            continue
        returns.append((curr / prev) - 1.0)
    return returns


def align_simple_returns(
    price_series: Mapping[str, Mapping[date, float]],
    *,
    lookback_trading_days: int,
) -> Tuple[List[date], Dict[str, List[float]], List[str]]:
    """Align multi-asset closes on common dates and return simple return series.

    Only dates present in every requested symbol series are used (inner join).
    The last ``lookback_trading_days`` common closes produce
    ``lookback_trading_days - 1`` return observations when enough history exists.
    """
    symbols = sorted(price_series.keys())
    if not symbols:
        return [], {}, []

    common_dates: Optional[set[date]] = None
    for symbol in symbols:
        dates = set(price_series[symbol].keys())
        common_dates = dates if common_dates is None else (common_dates & dates)
    if not common_dates:
        return [], {s: [] for s in symbols}, symbols

    ordered_dates = sorted(common_dates)
    # Need lookback_trading_days closes → lookback_trading_days - 1 returns.
    if len(ordered_dates) > lookback_trading_days:
        ordered_dates = ordered_dates[-lookback_trading_days:]

    if len(ordered_dates) < 2:
        return ordered_dates, {s: [] for s in symbols}, symbols

    return_matrix: Dict[str, List[float]] = {}
    for symbol in symbols:
        closes = [float(price_series[symbol][d]) for d in ordered_dates]
        return_matrix[symbol] = compute_simple_returns(closes)

    # Return observation dates are the later date of each consecutive pair.
    return_dates = ordered_dates[1:]
    return return_dates, return_matrix, symbols


def build_portfolio_returns(
    return_matrix: Mapping[str, Sequence[float]],
    symbols: Sequence[str],
    weights: Mapping[str, float],
) -> List[float]:
    """Static-weight portfolio simple returns on the aligned observation grid."""
    if not symbols:
        return []
    length = len(return_matrix[symbols[0]]) if symbols[0] in return_matrix else 0
    if length == 0:
        return []
    for symbol in symbols:
        if len(return_matrix.get(symbol, [])) != length:
            raise ValueError("return series length mismatch across symbols")

    weight_sum = sum(float(weights.get(s, 0.0)) for s in symbols)
    if weight_sum <= _EPS:
        return []
    normalized = {s: float(weights.get(s, 0.0)) / weight_sum for s in symbols}

    portfolio: List[float] = []
    for idx in range(length):
        day_ret = 0.0
        for symbol in symbols:
            day_ret += normalized[symbol] * float(return_matrix[symbol][idx])
        portfolio.append(day_ret)
    return portfolio


def historical_var_pct(returns: Sequence[float], confidence: float) -> float:
    """Historical VaR as a positive loss fraction (not percent points).

    Uses the empirical left-tail quantile at ``alpha = 1 - confidence`` via
    NumPy linear percentile interpolation, then negates so a loss is positive.
    """
    if not returns:
        raise ValueError("returns must not be empty")
    if not (0.5 < confidence < 1.0):
        raise ValueError("confidence out of range")
    alpha = (1.0 - confidence) * 100.0
    quantile = float(np.percentile(np.asarray(returns, dtype=float), alpha, method="linear"))
    # VaR is the loss magnitude; if the left-tail quantile is already positive
    # (unusual), clamp loss to zero rather than inventing a negative VaR.
    return max(0.0, -quantile)


def compute_historical_var_block(
    *,
    portfolio_returns: Sequence[float],
    portfolio_value: float,
    confidence: float,
    horizon_days: int,
    min_observations: int,
    observation_count: int,
) -> Dict[str, Any]:
    usable = len(portfolio_returns)
    if usable < min_observations:
        return {
            "status": "insufficient_history",
            "status_message": (
                f"Need at least {min_observations} aligned portfolio return "
                f"observations; have {usable}."
            ),
            "confidence": confidence,
            "horizon_days": horizon_days,
            "var_pct": None,
            "var_value": None,
            "observation_count": usable,
            "percentile_used": 1.0 - confidence,
        }

    one_day_var = historical_var_pct(portfolio_returns, confidence)
    if horizon_days > 1:
        # Documented i.i.d. sqrt-time scaling for multi-day horizon (V0).
        scaled = one_day_var * math.sqrt(float(horizon_days))
    else:
        scaled = one_day_var

    var_pct_points = scaled * 100.0
    var_value = scaled * float(portfolio_value)
    return {
        "status": "ok",
        "status_message": "Historical VaR computed from empirical portfolio returns.",
        "confidence": confidence,
        "horizon_days": horizon_days,
        "var_pct": round(var_pct_points, 6),
        "var_value": round(var_value, 6),
        "observation_count": usable,
        "percentile_used": round(1.0 - confidence, 8),
        "one_day_var_pct": round(one_day_var * 100.0, 6),
    }


def pearson_correlation_matrix(
    return_matrix: Mapping[str, Sequence[float]],
    symbols: Sequence[str],
) -> List[List[Optional[float]]]:
    """Pairwise Pearson correlation; diagonal is 1.0; insufficient variance → None."""
    n = len(symbols)
    matrix: List[List[Optional[float]]] = [[None] * n for _ in range(n)]
    arrays = {
        symbol: np.asarray(return_matrix[symbol], dtype=float)
        for symbol in symbols
    }
    for i, left in enumerate(symbols):
        matrix[i][i] = 1.0
        for j in range(i + 1, n):
            right = symbols[j]
            a = arrays[left]
            b = arrays[right]
            if a.size < 2 or b.size < 2:
                corr: Optional[float] = None
            elif float(np.std(a, ddof=0)) <= _EPS or float(np.std(b, ddof=0)) <= _EPS:
                corr = None
            else:
                corr = float(np.corrcoef(a, b)[0, 1])
                if math.isnan(corr):
                    corr = None
                else:
                    corr = round(corr, 8)
            matrix[i][j] = corr
            matrix[j][i] = corr
    return matrix


def compute_correlation_block(
    *,
    return_matrix: Mapping[str, Sequence[float]],
    symbols: Sequence[str],
    min_observations: int,
    observation_count: int,
) -> Dict[str, Any]:
    if len(symbols) < 2:
        return {
            "status": "unavailable",
            "status_message": "Correlation requires at least two held symbols.",
            "symbols": list(symbols),
            "matrix": [[1.0]] if len(symbols) == 1 else [],
            "observation_count": observation_count,
        }
    usable = observation_count
    if usable < min_observations:
        return {
            "status": "insufficient_history",
            "status_message": (
                f"Need at least {min_observations} aligned return observations "
                f"for correlation; have {usable}."
            ),
            "symbols": list(symbols),
            "matrix": [],
            "observation_count": usable,
        }
    matrix = pearson_correlation_matrix(return_matrix, symbols)
    return {
        "status": "ok",
        "status_message": "Pairwise Pearson correlation of aligned simple returns.",
        "symbols": list(symbols),
        "matrix": matrix,
        "observation_count": usable,
    }


def compute_concentration_metrics(weights: Mapping[str, float]) -> Dict[str, Any]:
    """HHI, effective N, and a normalized diversification score in [0, 1].

    diversification_score = (1 - HHI) / (1 - 1/n) for n > 1, else 0.
    Equal-weight portfolios score 1.0; a single 100% position scores 0.0.
    """
    if not weights:
        return {
            "status": "empty_portfolio",
            "hhi": None,
            "effective_n": None,
            "diversification_score": None,
            "top_weight_pct": None,
            "position_count": 0,
            "weights": [],
        }

    total = sum(float(v) for v in weights.values())
    if total <= _EPS:
        return {
            "status": "empty_portfolio",
            "hhi": None,
            "effective_n": None,
            "diversification_score": None,
            "top_weight_pct": None,
            "position_count": 0,
            "weights": [],
        }

    normalized = {k: float(v) / total for k, v in sorted(weights.items())}
    hhi = sum(w * w for w in normalized.values())
    n = len(normalized)
    effective_n = (1.0 / hhi) if hhi > _EPS else 0.0
    if n <= 1:
        diversification_score = 0.0
    else:
        denom = 1.0 - (1.0 / n)
        diversification_score = (
            max(0.0, min(1.0, (1.0 - hhi) / denom)) if denom > _EPS else 0.0
        )
    top_weight = max(normalized.values()) if normalized else 0.0
    weight_rows = [
        {"symbol": symbol, "weight_pct": round(w * 100.0, 6)}
        for symbol, w in sorted(normalized.items(), key=lambda item: item[1], reverse=True)
    ]
    return {
        "status": "ok",
        "hhi": round(hhi, 8),
        "effective_n": round(effective_n, 6),
        "diversification_score": round(diversification_score, 6),
        "top_weight_pct": round(top_weight * 100.0, 6),
        "position_count": n,
        "weights": weight_rows,
    }
