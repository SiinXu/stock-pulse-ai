# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""DCF and relative valuation estimation with explicit assumptions.

Phase 1 (issue #238) provides transparent, deterministic valuation models that
consume fundamentals only through existing DataFetcherManager interfaces. Every
estimate carries its assumptions and a sensitivity range. Missing fundamentals
yield an explicit ``insufficient_fundamentals`` status rather than a fabricated
number.
"""

from __future__ import annotations

import logging
import math
import statistics
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional, Sequence

from src.utils.sanitize import (
    exception_chain_redaction_values,
    log_safe_exception,
)

logger = logging.getLogger(__name__)

VALUATION_SCHEMA_VERSION = "valuation-estimate-v1"
VALUATION_DISCLAIMER = (
    "Model estimate for research support only. Results depend entirely on the "
    "stated assumptions and available fundamentals; they are not investment "
    "advice and do not guarantee future performance."
)
INSUFFICIENT_FUNDAMENTALS = "insufficient_fundamentals"

DEFAULT_DISCOUNT_RATE = 0.10
DEFAULT_TERMINAL_GROWTH_RATE = 0.03
DEFAULT_PROJECTION_YEARS = 5
DEFAULT_GROWTH_RATE = 0.05
MIN_PROJECTION_YEARS = 1
MAX_PROJECTION_YEARS = 15
MIN_DISCOUNT_RATE = 0.01
MAX_DISCOUNT_RATE = 0.50
MIN_GROWTH_RATE = -0.50
MAX_GROWTH_RATE = 0.50
MIN_TERMINAL_GROWTH_RATE = -0.05
MAX_TERMINAL_GROWTH_RATE = 0.10
# Cap auto-derived growth so a single high YoY print does not dominate.
AUTO_GROWTH_CAP = 0.25
SENSITIVITY_GROWTH_DELTAS = (-0.02, 0.0, 0.02)
SENSITIVITY_DISCOUNT_DELTAS = (-0.01, 0.0, 0.01)

FundamentalProvider = Callable[[str], Mapping[str, Any]]
QuoteProvider = Callable[[str], Mapping[str, Any]]


def _safe_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _round_money(value: float) -> float:
    return round(value, 6)


def _block_data(context: Mapping[str, Any], block: str) -> dict[str, Any]:
    payload = context.get(block)
    if not isinstance(payload, Mapping):
        return {}
    data = payload.get("data")
    return dict(data) if isinstance(data, Mapping) else {}


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _median(values: Sequence[float]) -> Optional[float]:
    clean = [v for v in values if math.isfinite(v)]
    if not clean:
        return None
    return float(statistics.median(clean))


def _percent_to_ratio(value: Optional[float]) -> Optional[float]:
    """Convert provider growth percentages (e.g. 12.5) into decimal ratios."""
    if value is None:
        return None
    # Values already in [-1, 1] are treated as ratios; larger magnitudes as %.
    if abs(value) <= 1.0:
        return value
    return value / 100.0


@dataclass(frozen=True)
class DcfAssumptions:
    """Explicit DCF inputs exposed in every response."""

    base_fcf: float
    cash_flow_source: str
    growth_rate: float
    discount_rate: float
    terminal_growth_rate: float
    projection_years: int
    growth_source: str
    net_debt_assumption: str = (
        "net_debt_unavailable_equity_value_equals_enterprise_value"
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_fcf": self.base_fcf,
            "cash_flow_source": self.cash_flow_source,
            "growth_rate": self.growth_rate,
            "discount_rate": self.discount_rate,
            "terminal_growth_rate": self.terminal_growth_rate,
            "projection_years": self.projection_years,
            "growth_source": self.growth_source,
            "net_debt_assumption": self.net_debt_assumption,
        }


def compute_dcf(
    base_fcf: float,
    *,
    growth_rate: float,
    discount_rate: float,
    projection_years: int = DEFAULT_PROJECTION_YEARS,
    terminal_growth_rate: float = DEFAULT_TERMINAL_GROWTH_RATE,
) -> dict[str, Any]:
    """Compute a Gordon-growth terminal DCF with explicit projected cash flows.

    Parameters are decimal rates (0.10 = 10%). The function is pure and
    deterministic for known-answer tests.
    """
    if base_fcf is None or not math.isfinite(base_fcf) or base_fcf <= 0:
        raise ValueError("base_fcf must be a positive finite number")
    if not (MIN_GROWTH_RATE <= growth_rate <= MAX_GROWTH_RATE):
        raise ValueError("growth_rate out of supported range")
    if not (MIN_DISCOUNT_RATE <= discount_rate <= MAX_DISCOUNT_RATE):
        raise ValueError("discount_rate out of supported range")
    if not (MIN_TERMINAL_GROWTH_RATE <= terminal_growth_rate <= MAX_TERMINAL_GROWTH_RATE):
        raise ValueError("terminal_growth_rate out of supported range")
    if not (MIN_PROJECTION_YEARS <= projection_years <= MAX_PROJECTION_YEARS):
        raise ValueError("projection_years out of supported range")
    if terminal_growth_rate >= discount_rate:
        raise ValueError("terminal_growth_rate must be strictly below discount_rate")

    projections: list[dict[str, float]] = []
    fcf = float(base_fcf)
    present_value_sum = 0.0
    for year in range(1, projection_years + 1):
        fcf = fcf * (1.0 + growth_rate)
        discount_factor = (1.0 + discount_rate) ** year
        present_value = fcf / discount_factor
        present_value_sum += present_value
        projections.append(
            {
                "year": float(year),
                "fcf": _round_money(fcf),
                "present_value": _round_money(present_value),
            }
        )

    terminal_fcf = fcf * (1.0 + terminal_growth_rate)
    terminal_value = terminal_fcf / (discount_rate - terminal_growth_rate)
    terminal_pv = terminal_value / ((1.0 + discount_rate) ** projection_years)
    enterprise_value = present_value_sum + terminal_pv

    return {
        "status": "ok",
        "enterprise_value": _round_money(enterprise_value),
        "equity_value": _round_money(enterprise_value),
        "present_value_projected_fcf": _round_money(present_value_sum),
        "terminal_value": _round_money(terminal_value),
        "terminal_value_present": _round_money(terminal_pv),
        "projections": projections,
    }


def build_dcf_sensitivity(
    base_fcf: float,
    *,
    growth_rate: float,
    discount_rate: float,
    projection_years: int,
    terminal_growth_rate: float,
) -> dict[str, Any]:
    """Build a growth × discount equity-value sensitivity table."""
    rows: list[dict[str, Any]] = []
    values: list[float] = []
    for growth_delta in SENSITIVITY_GROWTH_DELTAS:
        for discount_delta in SENSITIVITY_DISCOUNT_DELTAS:
            g = _clamp(growth_rate + growth_delta, MIN_GROWTH_RATE, MAX_GROWTH_RATE)
            r = _clamp(
                discount_rate + discount_delta,
                MIN_DISCOUNT_RATE,
                MAX_DISCOUNT_RATE,
            )
            # Keep terminal growth strictly below the scenario discount rate.
            g_term = min(terminal_growth_rate, r - 0.005)
            g_term = _clamp(
                g_term,
                MIN_TERMINAL_GROWTH_RATE,
                MAX_TERMINAL_GROWTH_RATE,
            )
            if g_term >= r:
                continue
            try:
                result = compute_dcf(
                    base_fcf,
                    growth_rate=g,
                    discount_rate=r,
                    projection_years=projection_years,
                    terminal_growth_rate=g_term,
                )
            except ValueError:
                continue
            equity_value = float(result["equity_value"])
            values.append(equity_value)
            rows.append(
                {
                    "growth_rate": round(g, 6),
                    "discount_rate": round(r, 6),
                    "terminal_growth_rate": round(g_term, 6),
                    "equity_value": equity_value,
                }
            )

    if not values:
        return {
            "rows": [],
            "equity_value_low": None,
            "equity_value_high": None,
            "equity_value_mid": None,
        }
    return {
        "rows": rows,
        "equity_value_low": _round_money(min(values)),
        "equity_value_high": _round_money(max(values)),
        "equity_value_mid": _round_money(statistics.median(values)),
    }



def compute_ev_ebitda(
    *,
    ebitda: Optional[float],
    market_cap: Optional[float],
    net_debt: Optional[float],
) -> Optional[float]:
    """Return EV/EBITDA only when market cap, net debt, and positive EBITDA exist.

    Enterprise value is ``market_cap + net_debt``. Net debt may be zero or
    negative (net cash). Missing any required input yields ``None`` — never an
    invented proxy (for example total liabilities as debt).
    """
    if ebitda is None or not math.isfinite(ebitda) or ebitda <= 0:
        return None
    if market_cap is None or not math.isfinite(market_cap) or market_cap <= 0:
        return None
    if net_debt is None or not math.isfinite(net_debt):
        return None
    enterprise_value = market_cap + net_debt
    if enterprise_value <= 0:
        return None
    return _round_money(enterprise_value / ebitda)


def compute_relative_valuation(
    *,
    target_pe: Optional[float],
    target_pb: Optional[float],
    current_price: Optional[float],
    peer_pe_values: Sequence[float],
    peer_pb_values: Sequence[float],
    target_ebitda: Optional[float] = None,
    target_market_cap: Optional[float] = None,
    target_net_debt: Optional[float] = None,
    peer_ev_ebitda_values: Sequence[float] = (),
) -> dict[str, Any]:
    """Compare target multiples against peer medians from fundamental data.

    EV/EBITDA is computed only when explicit EBITDA, market cap, and net debt
    are supplied for the target and at least one peer multiple is available.
    Missing EV/EBITDA inputs never fabricate numbers and do not block PE/PB.
    """
    peer_pe_median = _median(peer_pe_values)
    peer_pb_median = _median(peer_pb_values)
    peer_ev_ebitda_median = _median(
        [v for v in peer_ev_ebitda_values if v is not None and v > 0]
    )

    pe_usable = (
        target_pe is not None
        and target_pe > 0
        and peer_pe_median is not None
        and peer_pe_median > 0
        and current_price is not None
        and current_price > 0
    )
    pb_usable = (
        target_pb is not None
        and target_pb > 0
        and peer_pb_median is not None
        and peer_pb_median > 0
        and current_price is not None
        and current_price > 0
    )
    target_ev = None
    if (
        target_market_cap is not None
        and math.isfinite(target_market_cap)
        and target_market_cap > 0
        and target_net_debt is not None
        and math.isfinite(target_net_debt)
    ):
        target_ev = target_market_cap + target_net_debt
    target_ev_ebitda = compute_ev_ebitda(
        ebitda=target_ebitda,
        market_cap=target_market_cap,
        net_debt=target_net_debt,
    )
    ev_ebitda_usable = (
        target_ev_ebitda is not None
        and target_ev_ebitda > 0
        and peer_ev_ebitda_median is not None
        and peer_ev_ebitda_median > 0
        and target_ebitda is not None
        and target_ebitda > 0
        and target_net_debt is not None
        and math.isfinite(target_net_debt)
    )

    if not pe_usable and not pb_usable and not ev_ebitda_usable:
        missing: list[str] = []
        if target_pe is None or target_pe <= 0:
            missing.append("target_pe")
        if target_pb is None or target_pb <= 0:
            missing.append("target_pb")
        if current_price is None or current_price <= 0:
            missing.append("current_price")
        if peer_pe_median is None and peer_pb_median is None and peer_ev_ebitda_median is None:
            missing.append("peer_multiples")
        if target_ev_ebitda is None:
            if target_ebitda is None or target_ebitda <= 0:
                missing.append("target_ebitda")
            if target_market_cap is None or target_market_cap <= 0:
                missing.append("target_market_cap")
            if target_net_debt is None:
                missing.append("target_net_debt")
        elif peer_ev_ebitda_median is None:
            missing.append("peer_ev_ebitda")
        missing = list(dict.fromkeys(missing))
        return {
            "status": INSUFFICIENT_FUNDAMENTALS,
            "reason": INSUFFICIENT_FUNDAMENTALS,
            "message": (
                "Insufficient fundamentals for relative valuation: "
                + ", ".join(missing)
            ),
            "missing_inputs": missing,
            "target": {
                "pe_ratio": target_pe,
                "pb_ratio": target_pb,
                "current_price": current_price,
                "ebitda": target_ebitda,
                "market_cap": target_market_cap,
                "net_debt": target_net_debt,
                "enterprise_value": (
                    _round_money(target_ev) if target_ev is not None else None
                ),
                "ev_ebitda": target_ev_ebitda,
            },
            "peers": {
                "count_pe": len([v for v in peer_pe_values if v > 0]),
                "count_pb": len([v for v in peer_pb_values if v > 0]),
                "count_ev_ebitda": len([v for v in peer_ev_ebitda_values if v > 0]),
                "pe_median": peer_pe_median,
                "pb_median": peer_pb_median,
                "ev_ebitda_median": peer_ev_ebitda_median,
            },
            "implied_prices": {},
            "premium_discount": {},
            "ev_ebitda": {
                "status": INSUFFICIENT_FUNDAMENTALS,
                "target_multiple": target_ev_ebitda,
                "peer_median": peer_ev_ebitda_median,
            },
        }

    implied: dict[str, Any] = {}
    premium: dict[str, Any] = {}
    if pe_usable and target_pe is not None and peer_pe_median is not None:
        eps = current_price / target_pe  # type: ignore[operator]
        implied_pe_price = eps * peer_pe_median
        implied["pe_based"] = _round_money(implied_pe_price)
        premium["pe_vs_peers_pct"] = _round_money(
            ((target_pe / peer_pe_median) - 1.0) * 100.0
        )
    if pb_usable and target_pb is not None and peer_pb_median is not None:
        book_per_share = current_price / target_pb  # type: ignore[operator]
        implied_pb_price = book_per_share * peer_pb_median
        implied["pb_based"] = _round_money(implied_pb_price)
        premium["pb_vs_peers_pct"] = _round_money(
            ((target_pb / peer_pb_median) - 1.0) * 100.0
        )

    if ev_ebitda_usable and peer_ev_ebitda_median is not None and target_ebitda is not None:
        implied_ev = peer_ev_ebitda_median * target_ebitda
        implied_equity = implied_ev - float(target_net_debt)  # type: ignore[arg-type]
        implied["ev_ebitda_enterprise_value"] = _round_money(implied_ev)
        implied["ev_ebitda_equity_value"] = _round_money(implied_equity)
        premium["ev_ebitda_vs_peers_pct"] = _round_money(
            ((float(target_ev_ebitda) / peer_ev_ebitda_median) - 1.0) * 100.0  # type: ignore[arg-type]
        )
        ev_ebitda_section: dict[str, Any] = {
            "status": "ok",
            "target_multiple": target_ev_ebitda,
            "peer_median": _round_money(peer_ev_ebitda_median),
            "enterprise_value": (
                _round_money(target_ev) if target_ev is not None else None
            ),
            "implied_enterprise_value": _round_money(implied_ev),
            "implied_equity_value": _round_money(implied_equity),
        }
    else:
        missing_ev: list[str] = []
        if target_ebitda is None or target_ebitda <= 0:
            missing_ev.append("target_ebitda")
        if target_market_cap is None or target_market_cap <= 0:
            missing_ev.append("target_market_cap")
        if target_net_debt is None:
            missing_ev.append("target_net_debt")
        if peer_ev_ebitda_median is None:
            missing_ev.append("peer_ev_ebitda")
        ev_ebitda_section = {
            "status": INSUFFICIENT_FUNDAMENTALS,
            "target_multiple": target_ev_ebitda,
            "peer_median": (
                _round_money(peer_ev_ebitda_median)
                if peer_ev_ebitda_median is not None
                else None
            ),
            "missing_inputs": missing_ev,
            "message": (
                "EV/EBITDA not computed: requires positive EBITDA, positive "
                "market cap, explicit net debt (may be zero/negative), and at "
                "least one peer EV/EBITDA multiple. No estimated proxies."
            ),
        }

    method_notes = [
        "Peer medians are computed only from positive PE/PB/EV-EBITDA values "
        "supplied by existing fundamental/quote data for the requested peer codes.",
        "EV/EBITDA uses enterprise value = market_cap + net_debt only when all "
        "three of EBITDA, market_cap, and net_debt are explicitly available; "
        "missing inputs are reported rather than estimated.",
    ]

    return {
        "status": "ok",
        "target": {
            "pe_ratio": target_pe,
            "pb_ratio": target_pb,
            "current_price": current_price,
            "ebitda": target_ebitda,
            "market_cap": target_market_cap,
            "net_debt": target_net_debt,
            "enterprise_value": (
                _round_money(target_ev) if target_ev is not None else None
            ),
            "ev_ebitda": target_ev_ebitda,
        },
        "peers": {
            "count_pe": len([v for v in peer_pe_values if v > 0]),
            "count_pb": len([v for v in peer_pb_values if v > 0]),
            "count_ev_ebitda": len([v for v in peer_ev_ebitda_values if v > 0]),
            "pe_median": (
                _round_money(peer_pe_median) if peer_pe_median is not None else None
            ),
            "pb_median": (
                _round_money(peer_pb_median) if peer_pb_median is not None else None
            ),
            "ev_ebitda_median": (
                _round_money(peer_ev_ebitda_median)
                if peer_ev_ebitda_median is not None
                else None
            ),
        },
        "implied_prices": implied,
        "premium_discount": premium,
        "ev_ebitda": ev_ebitda_section,
        "method_notes": method_notes,
    }


def _extract_ebitda(earnings: Mapping[str, Any], valuation: Mapping[str, Any]) -> Optional[float]:
    """Read an explicit EBITDA field only; never derive from operating profit."""
    for source in (valuation, earnings):
        for key in ("ebitda", "ebitda_ttm", "EBITDA", "EBITDA_TTM"):
            value = _safe_float(source.get(key))
            if value is not None and value > 0:
                return value
    return None


def _extract_net_debt(
    earnings: Mapping[str, Any],
    valuation: Mapping[str, Any],
    fundamentals: Mapping[str, Any],
) -> Optional[float]:
    """Read explicit net debt only; total liabilities are not accepted as debt."""
    balance = _block_data(fundamentals, "balance") if isinstance(fundamentals, Mapping) else {}
    for source in (valuation, earnings, balance, fundamentals):
        if not isinstance(source, Mapping):
            continue
        for key in ("net_debt", "netDebt", "NET_DEBT"):
            value = _safe_float(source.get(key))
            if value is not None:
                return value
    return None

def _extract_base_cash_flow(
    earnings: Mapping[str, Any],
) -> tuple[Optional[float], Optional[str]]:
    operating_cf = _safe_float(earnings.get("operating_cash_flow"))
    if operating_cf is not None and operating_cf > 0:
        return operating_cf, "operating_cash_flow"
    net_profit = _safe_float(earnings.get("net_profit_parent"))
    if net_profit is not None and net_profit > 0:
        return net_profit, "net_profit_parent_proxy"
    return None, None


def _extract_default_growth(
    growth: Mapping[str, Any],
) -> tuple[float, str]:
    candidates: list[tuple[str, float]] = []
    for key in ("revenue_yoy", "net_profit_yoy"):
        ratio = _percent_to_ratio(_safe_float(growth.get(key)))
        if ratio is not None:
            candidates.append((key, ratio))
    if not candidates:
        return DEFAULT_GROWTH_RATE, "default_constant"
    # Prefer the more conservative (lower) of available growth signals.
    key, value = min(candidates, key=lambda item: item[1])
    capped = _clamp(value, MIN_GROWTH_RATE, AUTO_GROWTH_CAP)
    return capped, f"fundamental:{key}"


def _normalize_rate(
    value: Any,
    *,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    number = _safe_float(value)
    if number is None:
        return default
    return _clamp(number, minimum, maximum)


def _normalize_years(value: Any) -> int:
    number = _safe_float(value)
    if number is None:
        return DEFAULT_PROJECTION_YEARS
    return int(
        _clamp(int(number), MIN_PROJECTION_YEARS, MAX_PROJECTION_YEARS)
    )


class ValuationService:
    """Estimate DCF and relative valuation using manager-provided fundamentals."""

    def __init__(
        self,
        *,
        fundamental_provider: Optional[FundamentalProvider] = None,
        quote_provider: Optional[QuoteProvider] = None,
    ) -> None:
        self._fundamental_provider = fundamental_provider
        self._quote_provider = quote_provider

    def _default_fundamental_provider(self, stock_code: str) -> Mapping[str, Any]:
        from data_provider import DataFetcherManager

        manager = DataFetcherManager()
        return manager.get_fundamental_context(stock_code)

    def _default_quote_provider(self, stock_code: str) -> Mapping[str, Any]:
        from data_provider import DataFetcherManager

        manager = DataFetcherManager()
        quote = manager.get_realtime_quote(stock_code)
        if quote is None:
            return {}
        if hasattr(quote, "to_dict"):
            return quote.to_dict()
        return {
            "price": getattr(quote, "price", None),
            "pe_ratio": getattr(quote, "pe_ratio", None),
            "pb_ratio": getattr(quote, "pb_ratio", None),
            "total_mv": getattr(quote, "total_mv", None),
            "circ_mv": getattr(quote, "circ_mv", None),
        }

    def _load_fundamentals(self, stock_code: str) -> Mapping[str, Any]:
        provider = self._fundamental_provider or self._default_fundamental_provider
        try:
            payload = provider(stock_code)
        except Exception as exc:  # broad-exception: fallback_recorded - valuation degrades to insufficient instead of failing the agent turn.
            log_safe_exception(
                logger,
                "Valuation fundamental lookup failed",
                exc,
                error_code="valuation_fundamental_lookup_failed",
                level=logging.WARNING,
                context={"stock_code": stock_code},
                exception_redaction_values=exception_chain_redaction_values(exc),
            )
            return {}
        return payload if isinstance(payload, Mapping) else {}

    def _load_quote(self, stock_code: str) -> Mapping[str, Any]:
        provider = self._quote_provider or self._default_quote_provider
        try:
            payload = provider(stock_code)
        except Exception as exc:  # broad-exception: fallback_recorded - quote is optional for DCF equity total.
            log_safe_exception(
                logger,
                "Valuation quote lookup failed",
                exc,
                error_code="valuation_quote_lookup_failed",
                level=logging.WARNING,
                context={"stock_code": stock_code},
                exception_redaction_values=exception_chain_redaction_values(exc),
            )
            return {}
        return payload if isinstance(payload, Mapping) else {}

    def estimate(
        self,
        stock_code: str,
        *,
        growth_rate: Optional[float] = None,
        discount_rate: Optional[float] = None,
        terminal_growth_rate: Optional[float] = None,
        projection_years: Optional[int] = None,
        peer_codes: Optional[Sequence[str]] = None,
    ) -> dict[str, Any]:
        """Return DCF + relative valuation for one stock with full assumptions."""
        code = str(stock_code or "").strip()
        if not code:
            return self._empty_result(
                stock_code="",
                reason="invalid_stock_code",
                message="stock_code is required",
            )

        fundamentals = self._load_fundamentals(code)
        quote = self._load_quote(code)
        valuation = _block_data(fundamentals, "valuation")
        growth = _block_data(fundamentals, "growth")
        earnings = _block_data(fundamentals, "earnings")

        pe_ratio = _safe_float(valuation.get("pe_ratio"))
        if pe_ratio is None:
            pe_ratio = _safe_float(quote.get("pe_ratio"))
        pb_ratio = _safe_float(valuation.get("pb_ratio"))
        if pb_ratio is None:
            pb_ratio = _safe_float(quote.get("pb_ratio"))
        total_mv = _safe_float(valuation.get("total_mv"))
        if total_mv is None:
            total_mv = _safe_float(quote.get("total_mv"))
        current_price = _safe_float(quote.get("price"))

        base_fcf, cash_flow_source = _extract_base_cash_flow(earnings)
        auto_growth, growth_source = _extract_default_growth(growth)
        resolved_growth = (
            _clamp(float(growth_rate), MIN_GROWTH_RATE, MAX_GROWTH_RATE)
            if growth_rate is not None and _safe_float(growth_rate) is not None
            else auto_growth
        )
        if growth_rate is not None and _safe_float(growth_rate) is not None:
            growth_source = "caller_override"
        resolved_discount = _normalize_rate(
            discount_rate,
            default=DEFAULT_DISCOUNT_RATE,
            minimum=MIN_DISCOUNT_RATE,
            maximum=MAX_DISCOUNT_RATE,
        )
        resolved_terminal = _normalize_rate(
            terminal_growth_rate,
            default=DEFAULT_TERMINAL_GROWTH_RATE,
            minimum=MIN_TERMINAL_GROWTH_RATE,
            maximum=MAX_TERMINAL_GROWTH_RATE,
        )
        resolved_years = _normalize_years(projection_years)

        dcf_section: dict[str, Any]
        if base_fcf is None or cash_flow_source is None:
            dcf_section = {
                "status": INSUFFICIENT_FUNDAMENTALS,
                "reason": INSUFFICIENT_FUNDAMENTALS,
                "message": (
                    "Insufficient fundamentals for DCF: positive operating cash "
                    "flow or net profit is required."
                ),
                "missing_inputs": ["operating_cash_flow", "net_profit_parent"],
                "assumptions": {
                    "growth_rate": resolved_growth,
                    "discount_rate": resolved_discount,
                    "terminal_growth_rate": resolved_terminal,
                    "projection_years": resolved_years,
                    "growth_source": growth_source,
                    "cash_flow_source": None,
                    "base_fcf": None,
                },
                "sensitivity": {
                    "rows": [],
                    "equity_value_low": None,
                    "equity_value_high": None,
                    "equity_value_mid": None,
                },
            }
        elif resolved_terminal >= resolved_discount:
            dcf_section = {
                "status": "invalid_assumptions",
                "reason": "terminal_growth_gte_discount",
                "message": (
                    "terminal_growth_rate must be strictly below discount_rate"
                ),
                "assumptions": DcfAssumptions(
                    base_fcf=base_fcf,
                    cash_flow_source=cash_flow_source,
                    growth_rate=resolved_growth,
                    discount_rate=resolved_discount,
                    terminal_growth_rate=resolved_terminal,
                    projection_years=resolved_years,
                    growth_source=growth_source,
                ).to_dict(),
                "sensitivity": {
                    "rows": [],
                    "equity_value_low": None,
                    "equity_value_high": None,
                    "equity_value_mid": None,
                },
            }
        else:
            assumptions = DcfAssumptions(
                base_fcf=base_fcf,
                cash_flow_source=cash_flow_source,
                growth_rate=resolved_growth,
                discount_rate=resolved_discount,
                terminal_growth_rate=resolved_terminal,
                projection_years=resolved_years,
                growth_source=growth_source,
            )
            dcf_core = compute_dcf(
                base_fcf,
                growth_rate=resolved_growth,
                discount_rate=resolved_discount,
                projection_years=resolved_years,
                terminal_growth_rate=resolved_terminal,
            )
            sensitivity = build_dcf_sensitivity(
                base_fcf,
                growth_rate=resolved_growth,
                discount_rate=resolved_discount,
                projection_years=resolved_years,
                terminal_growth_rate=resolved_terminal,
            )
            per_share = None
            shares_outstanding = None
            if (
                current_price is not None
                and current_price > 0
                and total_mv is not None
                and total_mv > 0
            ):
                shares_outstanding = total_mv / current_price
                if shares_outstanding > 0:
                    per_share = _round_money(
                        float(dcf_core["equity_value"]) / shares_outstanding
                    )
            dcf_section = {
                **dcf_core,
                "assumptions": assumptions.to_dict(),
                "sensitivity": sensitivity,
                "shares_outstanding_estimate": (
                    _round_money(shares_outstanding)
                    if shares_outstanding is not None
                    else None
                ),
                "intrinsic_value_per_share": per_share,
                "market": {
                    "current_price": current_price,
                    "total_mv": total_mv,
                    "upside_vs_price_pct": (
                        _round_money(((per_share / current_price) - 1.0) * 100.0)
                        if per_share is not None
                        and current_price is not None
                        and current_price > 0
                        else None
                    ),
                },
            }

        target_ebitda = _extract_ebitda(earnings, valuation)
        target_net_debt = _extract_net_debt(earnings, valuation, fundamentals)

        peer_list = [
            str(item).strip()
            for item in (peer_codes or [])
            if str(item).strip() and str(item).strip().upper() != code.upper()
        ]
        peer_pe_values: list[float] = []
        peer_pb_values: list[float] = []
        peer_ev_ebitda_values: list[float] = []
        peer_details: list[dict[str, Any]] = []
        for peer in peer_list[:12]:
            peer_ctx = self._load_fundamentals(peer)
            peer_quote = self._load_quote(peer)
            peer_val = _block_data(peer_ctx, "valuation")
            peer_earn = _block_data(peer_ctx, "earnings")
            peer_pe = _safe_float(peer_val.get("pe_ratio"))
            if peer_pe is None:
                peer_pe = _safe_float(peer_quote.get("pe_ratio"))
            peer_pb = _safe_float(peer_val.get("pb_ratio"))
            if peer_pb is None:
                peer_pb = _safe_float(peer_quote.get("pb_ratio"))
            peer_mv = _safe_float(peer_val.get("total_mv"))
            if peer_mv is None:
                peer_mv = _safe_float(peer_quote.get("total_mv"))
            peer_ebitda = _extract_ebitda(peer_earn, peer_val)
            peer_net_debt = _extract_net_debt(peer_earn, peer_val, peer_ctx)
            peer_ev_ebitda = compute_ev_ebitda(
                ebitda=peer_ebitda,
                market_cap=peer_mv,
                net_debt=peer_net_debt,
            )
            if peer_pe is not None and peer_pe > 0:
                peer_pe_values.append(peer_pe)
            if peer_pb is not None and peer_pb > 0:
                peer_pb_values.append(peer_pb)
            if peer_ev_ebitda is not None and peer_ev_ebitda > 0:
                peer_ev_ebitda_values.append(peer_ev_ebitda)
            peer_details.append(
                {
                    "stock_code": peer,
                    "pe_ratio": peer_pe,
                    "pb_ratio": peer_pb,
                    "ebitda": peer_ebitda,
                    "market_cap": peer_mv,
                    "net_debt": peer_net_debt,
                    "ev_ebitda": peer_ev_ebitda,
                }
            )

        relative_section = compute_relative_valuation(
            target_pe=pe_ratio,
            target_pb=pb_ratio,
            current_price=current_price,
            peer_pe_values=peer_pe_values,
            peer_pb_values=peer_pb_values,
            target_ebitda=target_ebitda,
            target_market_cap=total_mv,
            target_net_debt=target_net_debt,
            peer_ev_ebitda_values=peer_ev_ebitda_values,
        )
        relative_section["peer_details"] = peer_details
        relative_section["assumptions"] = {
            "peer_codes": peer_list[:12],
            "multiples": ["pe_ratio", "pb_ratio", "ev_ebitda"],
            "peer_aggregation": "median_of_positive_values",
            "ev_ebitda": (
                "computed_when_ebitda_market_cap_and_net_debt_available"
                if relative_section.get("ev_ebitda", {}).get("status") == "ok"
                else "insufficient_explicit_inputs"
            ),
            "ev_definition": "market_cap + net_debt",
            "net_debt_policy": "explicit_net_debt_only_no_liability_proxy",
        }

        overall_status = "ok"
        if (
            dcf_section.get("status") != "ok"
            and relative_section.get("status") != "ok"
        ):
            overall_status = INSUFFICIENT_FUNDAMENTALS
        elif (
            dcf_section.get("status") != "ok"
            or relative_section.get("status") != "ok"
        ):
            overall_status = "partial"

        return {
            "schema_version": VALUATION_SCHEMA_VERSION,
            "status": overall_status,
            "stock_code": code,
            "dcf": dcf_section,
            "relative": relative_section,
            "fundamentals_snapshot": {
                "pe_ratio": pe_ratio,
                "pb_ratio": pb_ratio,
                "total_mv": total_mv,
                "current_price": current_price,
                "ebitda": target_ebitda,
                "net_debt": target_net_debt,
                "operating_cash_flow": _safe_float(earnings.get("operating_cash_flow")),
                "net_profit_parent": _safe_float(earnings.get("net_profit_parent")),
                "revenue_yoy": _safe_float(growth.get("revenue_yoy")),
                "net_profit_yoy": _safe_float(growth.get("net_profit_yoy")),
                "fundamental_status": fundamentals.get("status"),
            },
            "disclaimer": VALUATION_DISCLAIMER,
        }

    def _empty_result(
        self,
        *,
        stock_code: str,
        reason: str,
        message: str,
    ) -> dict[str, Any]:
        return {
            "schema_version": VALUATION_SCHEMA_VERSION,
            "status": INSUFFICIENT_FUNDAMENTALS,
            "stock_code": stock_code,
            "reason": reason,
            "message": message,
            "dcf": {
                "status": INSUFFICIENT_FUNDAMENTALS,
                "reason": reason,
                "message": message,
                "assumptions": {},
                "sensitivity": {
                    "rows": [],
                    "equity_value_low": None,
                    "equity_value_high": None,
                    "equity_value_mid": None,
                },
            },
            "relative": {
                "status": INSUFFICIENT_FUNDAMENTALS,
                "reason": reason,
                "message": message,
                "assumptions": {},
            },
            "disclaimer": VALUATION_DISCLAIMER,
        }
