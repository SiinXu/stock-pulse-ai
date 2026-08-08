# -*- coding: utf-8 -*-
"""Deterministic financial calculators: compound growth and goal planning.

Pure functions only — no I/O, no global state, no market or portfolio data.
Issue #240 / T09.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional, Union

Number = Union[int, float]

# Hard caps keep solvers bounded even under adversarial inputs.
MAX_PERIODS = 100 * 365  # 100 years of daily compounding
MAX_ABS_RATE = 10.0  # ±1000% annual nominal; beyond this is rejected as unrealistic
MAX_ABS_MONEY = 1e15


class CalculatorInputError(ValueError):
    """Raised when inputs are non-finite, out of domain, or otherwise invalid."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _is_bool(value: Any) -> bool:
    return isinstance(value, bool)


def _require_finite(name: str, value: Any) -> float:
    if _is_bool(value) or not isinstance(value, (int, float)):
        raise CalculatorInputError(
            "invalid_input",
            f"{name} must be a finite number",
        )
    number = float(value)
    if not math.isfinite(number):
        raise CalculatorInputError(
            "invalid_input",
            f"{name} must be a finite number (rejected NaN / ±Infinity)",
        )
    return number


def _require_finite_money(name: str, value: Any, *, allow_negative: bool = False) -> float:
    number = _require_finite(name, value)
    if not allow_negative and number < 0:
        raise CalculatorInputError("invalid_input", f"{name} must be >= 0")
    if abs(number) > MAX_ABS_MONEY:
        raise CalculatorInputError("invalid_input", f"{name} exceeds the supported magnitude")
    return number


def _require_periods_per_year(value: Any) -> int:
    if _is_bool(value) or not isinstance(value, (int, float)):
        raise CalculatorInputError("invalid_input", "periods_per_year must be a positive integer")
    if isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            raise CalculatorInputError(
                "invalid_input",
                "periods_per_year must be a positive integer",
            )
        periods = int(value)
    else:
        periods = int(value)
    if periods < 1:
        raise CalculatorInputError("invalid_input", "periods_per_year must be >= 1")
    if periods > 365:
        raise CalculatorInputError("invalid_input", "periods_per_year must be <= 365")
    return periods


def _require_years(value: Any) -> float:
    years = _require_finite("years", value)
    if years <= 0:
        raise CalculatorInputError("invalid_input", "years must be > 0")
    if years > 100:
        raise CalculatorInputError("invalid_input", "years must be <= 100")
    return years


def _period_rate(annual_rate: float, periods_per_year: int) -> float:
    return annual_rate / float(periods_per_year)


def _total_periods(years: float, periods_per_year: int) -> int:
    raw = years * periods_per_year
    # Accept only values that map cleanly to an integer number of periods.
    periods = int(round(raw))
    if periods < 1:
        raise CalculatorInputError("invalid_input", "horizon must cover at least one period")
    if abs(raw - periods) > 1e-9:
        raise CalculatorInputError(
            "invalid_input",
            "years * periods_per_year must resolve to an integer period count",
        )
    if periods > MAX_PERIODS:
        raise CalculatorInputError("invalid_input", "horizon exceeds the supported period cap")
    return periods


def _require_annual_rate(value: Any) -> float:
    rate = _require_finite("annual_rate", value)
    if abs(rate) > MAX_ABS_RATE:
        raise CalculatorInputError("invalid_input", "annual_rate exceeds the supported magnitude")
    # Period rate of -1 (or lower) would zero or invert balances mid-horizon.
    return rate


def _validate_period_rate(period_rate: float) -> None:
    if period_rate <= -1.0:
        raise CalculatorInputError(
            "invalid_input",
            "period rate must be greater than -100% (annual_rate / periods_per_year > -1)",
        )


def _future_value(
    principal: float,
    period_rate: float,
    periods: int,
    contribution_per_period: float,
) -> float:
    """Ordinary annuity: contribution applied at the end of each period."""
    if periods == 0:
        return principal
    if abs(period_rate) < 1e-15:
        return principal + contribution_per_period * periods
    growth = (1.0 + period_rate) ** periods
    return principal * growth + contribution_per_period * (growth - 1.0) / period_rate


def _build_balance_series(
    principal: float,
    period_rate: float,
    periods: int,
    contribution_per_period: float,
) -> List[Dict[str, Any]]:
    balance = float(principal)
    total_contributed = float(principal)
    series: List[Dict[str, Any]] = [
        {
            "period": 0,
            "balance": balance,
            "total_contributed": total_contributed,
            "gain": 0.0,
        }
    ]
    for period in range(1, periods + 1):
        balance = balance * (1.0 + period_rate) + contribution_per_period
        total_contributed = principal + contribution_per_period * period
        # Guard against non-finite intermediate values under extreme rates.
        if not math.isfinite(balance):
            raise CalculatorInputError(
                "invalid_input",
                "computation overflowed to a non-finite balance; reduce rate, horizon, or amounts",
            )
        series.append(
            {
                "period": period,
                "balance": float(balance),
                "total_contributed": float(total_contributed),
                "gain": float(balance - total_contributed),
            }
        )
    return series


def compute_compound_growth(
    principal: float,
    annual_rate: float,
    years: float,
    contribution_per_period: float = 0.0,
    periods_per_year: int = 12,
) -> Dict[str, Any]:
    """Compute period-by-period balances and terminal value for compound growth.

    Returns a dict with ``status="ok"`` and series / terminal breakdown.
    Raises :class:`CalculatorInputError` for invalid inputs.
    """
    principal_v = _require_finite_money("principal", principal)
    annual_rate_v = _require_annual_rate(annual_rate)
    years_v = _require_years(years)
    contribution_v = _require_finite_money(
        "contribution_per_period",
        contribution_per_period,
        allow_negative=True,
    )
    periods_per_year_v = _require_periods_per_year(periods_per_year)
    periods = _total_periods(years_v, periods_per_year_v)
    period_rate = _period_rate(annual_rate_v, periods_per_year_v)
    _validate_period_rate(period_rate)

    series = _build_balance_series(principal_v, period_rate, periods, contribution_v)
    final = series[-1]
    total_contributed = float(final["total_contributed"])
    final_value = float(final["balance"])
    total_gain = float(final["gain"])

    return {
        "status": "ok",
        "principal": principal_v,
        "annual_rate": annual_rate_v,
        "years": years_v,
        "contribution_per_period": contribution_v,
        "periods_per_year": periods_per_year_v,
        "period_count": periods,
        "period_rate": period_rate,
        "final_value": final_value,
        "total_contributed": total_contributed,
        "total_gain": total_gain,
        "series": series,
    }


def solve_target_contribution(
    target: float,
    principal: float,
    annual_rate: float,
    years: float,
    periods_per_year: int = 12,
) -> Dict[str, Any]:
    """Solve the end-of-period contribution needed to reach ``target`` in ``years``."""
    target_v = _require_finite_money("target", target)
    principal_v = _require_finite_money("principal", principal)
    annual_rate_v = _require_annual_rate(annual_rate)
    years_v = _require_years(years)
    periods_per_year_v = _require_periods_per_year(periods_per_year)
    periods = _total_periods(years_v, periods_per_year_v)
    period_rate = _period_rate(annual_rate_v, periods_per_year_v)
    _validate_period_rate(period_rate)

    base = {
        "target": target_v,
        "principal": principal_v,
        "annual_rate": annual_rate_v,
        "years": years_v,
        "periods_per_year": periods_per_year_v,
        "period_count": periods,
        "period_rate": period_rate,
        "contribution_per_period": None,
    }

    grown_principal = _future_value(principal_v, period_rate, periods, 0.0)
    if not math.isfinite(grown_principal):
        raise CalculatorInputError(
            "invalid_input",
            "computation overflowed; reduce rate, horizon, or amounts",
        )

    if grown_principal >= target_v:
        return {
            **base,
            "status": "already_met",
            "contribution_per_period": 0.0,
            "message": "Principal growth alone meets or exceeds the target; no contribution is required.",
        }

    shortfall = target_v - grown_principal
    if abs(period_rate) < 1e-15:
        # Linear accumulation: need positive contribution each period.
        contribution = shortfall / float(periods)
    else:
        growth = (1.0 + period_rate) ** periods
        denom = (growth - 1.0) / period_rate
        if abs(denom) < 1e-15 or not math.isfinite(denom):
            return {
                **base,
                "status": "unreachable",
                "message": "Target cannot be reached under the given rate and horizon.",
            }
        contribution = shortfall / denom

    if not math.isfinite(contribution):
        return {
            **base,
            "status": "unreachable",
            "message": "Target cannot be reached under the given rate and horizon.",
        }

    # Negative contribution means the user would need to withdraw — treat as ok with signed amount.
    return {
        **base,
        "status": "ok",
        "contribution_per_period": float(contribution),
        "message": None,
    }


def solve_target_duration(
    target: float,
    principal: float,
    annual_rate: float,
    contribution_per_period: float,
    periods_per_year: int = 12,
) -> Dict[str, Any]:
    """Solve how many periods are needed to reach ``target``.

    Returns ``status="unreachable"`` with an explicit message when the trajectory
    cannot hit the target (for example non-positive effective growth and
    insufficient contributions). Never returns ``inf``.
    """
    target_v = _require_finite_money("target", target)
    principal_v = _require_finite_money("principal", principal)
    annual_rate_v = _require_annual_rate(annual_rate)
    contribution_v = _require_finite_money(
        "contribution_per_period",
        contribution_per_period,
        allow_negative=True,
    )
    periods_per_year_v = _require_periods_per_year(periods_per_year)
    period_rate = _period_rate(annual_rate_v, periods_per_year_v)
    _validate_period_rate(period_rate)

    base = {
        "target": target_v,
        "principal": principal_v,
        "annual_rate": annual_rate_v,
        "contribution_per_period": contribution_v,
        "periods_per_year": periods_per_year_v,
        "period_rate": period_rate,
        "period_count": None,
        "years": None,
    }

    if principal_v >= target_v:
        return {
            **base,
            "status": "already_met",
            "period_count": 0,
            "years": 0.0,
            "message": "Principal already meets or exceeds the target.",
        }

    # Zero rate: pure linear accumulation.
    if abs(period_rate) < 1e-15:
        if contribution_v <= 0:
            return {
                **base,
                "status": "unreachable",
                "message": (
                    "With a zero rate and non-positive contribution the target is unreachable."
                ),
            }
        periods_needed = math.ceil((target_v - principal_v) / contribution_v)
        if periods_needed > MAX_PERIODS:
            return {
                **base,
                "status": "unreachable",
                "message": "Target requires more periods than the supported horizon cap.",
            }
        return {
            **base,
            "status": "ok",
            "period_count": int(periods_needed),
            "years": float(periods_needed) / float(periods_per_year_v),
            "message": None,
        }

    # Closed form for ordinary annuity:
    # target = P*(1+r)^n + c*((1+r)^n - 1)/r
    # => (1+r)^n = (target*r + c) / (P*r + c)
    numerator = target_v * period_rate + contribution_v
    denominator = principal_v * period_rate + contribution_v

    if abs(denominator) < 1e-15:
        return {
            **base,
            "status": "unreachable",
            "message": "Target cannot be reached under the given rate and contribution.",
        }

    ratio = numerator / denominator
    # Need (1+r)^n = ratio with 1+r > 0 already validated.
    growth_base = 1.0 + period_rate
    if ratio <= 0 or not math.isfinite(ratio):
        return {
            **base,
            "status": "unreachable",
            "message": "Target cannot be reached under the given rate and contribution.",
        }

    # When r > 0 we need ratio > 1 to grow toward a higher target.
    # When -1 < r < 0, growth_base in (0, 1); reaching a higher target usually needs
    # enough contribution — ratio must be in (0, 1) with log signs aligning.
    try:
        n_exact = math.log(ratio) / math.log(growth_base)
    except ValueError:
        return {
            **base,
            "status": "unreachable",
            "message": "Target cannot be reached under the given rate and contribution.",
        }

    if not math.isfinite(n_exact) or n_exact < 0:
        return {
            **base,
            "status": "unreachable",
            "message": "Target cannot be reached under the given rate and contribution.",
        }

    periods_needed = int(math.ceil(n_exact - 1e-12))
    if periods_needed < 1:
        periods_needed = 1
    if periods_needed > MAX_PERIODS:
        return {
            **base,
            "status": "unreachable",
            "message": "Target requires more periods than the supported horizon cap.",
        }

    # Verify forward (handles float edge cases near boundaries).
    reached = _future_value(principal_v, period_rate, periods_needed, contribution_v)
    if not math.isfinite(reached) or reached + 1e-6 < target_v:
        # Walk forward up to a small bound if ceil undershoots due to float noise.
        found: Optional[int] = None
        balance = principal_v
        for period in range(1, min(periods_needed + 5, MAX_PERIODS) + 1):
            balance = balance * growth_base + contribution_v
            if not math.isfinite(balance):
                break
            if balance + 1e-6 >= target_v:
                found = period
                break
        if found is None:
            return {
                **base,
                "status": "unreachable",
                "message": "Target cannot be reached under the given rate and contribution.",
            }
        periods_needed = found

    return {
        **base,
        "status": "ok",
        "period_count": int(periods_needed),
        "years": float(periods_needed) / float(periods_per_year_v),
        "message": None,
    }


def result_to_public_dict(result: Mapping[str, Any]) -> Dict[str, Any]:
    """Return a JSON-friendly shallow copy (lists/dicts already plain)."""
    return dict(result)
