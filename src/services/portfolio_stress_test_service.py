# -*- coding: utf-8 -*-
"""Portfolio stress testing via deterministic factor shocks (issue #158 / T07).

This module applies declarative scenario shocks to current holdings and
estimates portfolio impact. It reuses position weights from the portfolio
snapshot path used by risk metrics and reuses concentration helpers from
``portfolio_risk_metrics_service`` — it does **not** modify that service.

Scope (this delivery):
- Deterministic instantaneous factor shocks (market / sector / FX / rate)
- Explicit simplification labels (e.g. unit beta when beta is missing)
- ``partial`` status when required classification or beta data is incomplete

Out of scope (remaining):
- Historical extreme-period replay
- Monte Carlo / full revaluation paths
- Web UI presentation
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from src.services.portfolio_risk_metrics_service import compute_concentration_metrics
from src.services.portfolio_service import PortfolioService
from src.services.portfolio_stress_scenarios import (
    DEFAULT_EQUITY_RATE_SENSITIVITY_PCT_PER_100BP,
    FACTOR_FX,
    FACTOR_MARKET,
    FACTOR_RATE,
    FACTOR_SECTOR,
    build_custom_scenario,
    get_scenario,
    load_scenarios,
)

logger = logging.getLogger(__name__)

_EPS = 1e-12
SIMULATION_METHOD = "deterministic_factor_shock"
# Historical extreme-window replay is intentionally not implemented in this
# delivery; callers and docs must not claim otherwise.
HISTORICAL_REPLAY_AVAILABLE = False


class PortfolioStressTestService:
    """Estimate portfolio impact under declarative stress scenarios."""

    def __init__(
        self,
        *,
        portfolio_service: Optional[PortfolioService] = None,
        scenarios_path: Optional[str] = None,
    ) -> None:
        self.portfolio_service = portfolio_service or PortfolioService()
        self.scenarios_path = scenarios_path

    def list_scenarios(self) -> List[Dict[str, Any]]:
        """Return available scenarios (built-in + optional YAML overrides)."""
        return load_scenarios(scenarios_path=self.scenarios_path)

    def run_stress_test(
        self,
        *,
        account_id: Optional[int] = None,
        as_of: Optional[date] = None,
        cost_method: str = "fifo",
        scenario_id: Optional[str] = None,
        target_sector: Optional[str] = None,
        betas: Optional[Mapping[str, float]] = None,
        sector_map: Optional[Mapping[str, str]] = None,
        custom_shocks: Optional[Sequence[Mapping[str, Any]]] = None,
        rate_sensitivity_pct_per_100bp: float = DEFAULT_EQUITY_RATE_SENSITIVITY_PCT_PER_100BP,
    ) -> Dict[str, Any]:
        """Run a single deterministic stress scenario against current holdings.

        Provide either ``scenario_id`` (preset / YAML) or ``custom_shocks``.
        """
        as_of_date = as_of or date.today()
        scenario = self._resolve_scenario(
            scenario_id=scenario_id,
            custom_shocks=custom_shocks,
        )
        target_sector_norm = self._normalize_sector(target_sector)
        if scenario.get("requires_target_sector") and not target_sector_norm:
            raise ValueError(
                f"scenario '{scenario['id']}' requires target_sector "
                "(sector name to shock)"
            )

        # include_realtime=False: no provider calls on the hot path (same
        # contract as portfolio risk metrics).
        snapshot = self.portfolio_service.get_portfolio_snapshot(
            account_id=account_id,
            as_of=as_of_date,
            cost_method=cost_method,
            include_realtime=False,
        )
        currency = str(snapshot.get("currency") or "CNY")
        positions = self._extract_positions(snapshot)
        portfolio_value = sum(p["market_value"] for p in positions)

        assumptions = self._build_assumptions(
            scenario=scenario,
            rate_sensitivity_pct_per_100bp=rate_sensitivity_pct_per_100bp,
            betas_provided=bool(betas),
            sector_map_provided=bool(sector_map),
        )
        base: Dict[str, Any] = {
            "as_of": as_of_date.isoformat(),
            "account_id": account_id,
            "cost_method": cost_method,
            "currency": currency,
            "portfolio_value": round(portfolio_value, 6) if portfolio_value > _EPS else 0.0,
            "positions_used": len(positions),
            "simulation_method": SIMULATION_METHOD,
            "historical_replay_available": HISTORICAL_REPLAY_AVAILABLE,
            "scenario": {
                "id": scenario["id"],
                "name": scenario["name"],
                "description": scenario.get("description") or "",
                "category": scenario.get("category") or "custom",
                "shocks": scenario["shocks"],
                "target_sector": target_sector_norm,
            },
            "assumptions": assumptions,
        }

        if not positions or portfolio_value <= _EPS:
            return {
                **base,
                "status": "empty_portfolio",
                "status_message": "No held equity positions with positive market value.",
                "missing_data": ["positions"],
                "portfolio_pnl": None,
                "portfolio_pnl_pct": None,
                "stressed_portfolio_value": None,
                "position_impacts": [],
                "top_losers": [],
                "top_winners": [],
                "concentration": compute_concentration_metrics({}),
            }

        beta_map = self._normalize_float_map(betas)
        sector_lookup = self._normalize_sector_map(sector_map)
        # Fill sector from position payload when present and not overridden.
        for pos in positions:
            symbol = pos["symbol"]
            if symbol not in sector_lookup and pos.get("sector"):
                sector_lookup[symbol] = self._normalize_sector(pos["sector"]) or ""

        position_impacts: List[Dict[str, Any]] = []
        missing_data: List[str] = []
        simplified_flags: List[str] = list(assumptions["simplified_assumptions"])

        needs_beta = any(s["factor"] == FACTOR_MARKET for s in scenario["shocks"])
        needs_sector = any(s["factor"] == FACTOR_SECTOR for s in scenario["shocks"])
        unit_beta_used = False
        missing_sector_symbols: List[str] = []

        for pos in positions:
            symbol = pos["symbol"]
            weight = pos["market_value"] / portfolio_value
            shock_pct, pos_missing, pos_simplified = self._position_shock_pct(
                position=pos,
                shocks=scenario["shocks"],
                beta=beta_map.get(symbol),
                sector=sector_lookup.get(symbol),
                target_sector=target_sector_norm,
                base_currency=currency,
                rate_sensitivity_pct_per_100bp=rate_sensitivity_pct_per_100bp,
            )
            if "beta" in pos_missing:
                unit_beta_used = True
            if "sector" in pos_missing:
                missing_sector_symbols.append(symbol)
            for item in pos_missing:
                if item not in missing_data:
                    missing_data.append(item)
            for item in pos_simplified:
                if item not in simplified_flags:
                    simplified_flags.append(item)

            pnl = pos["market_value"] * (shock_pct / 100.0)
            stressed_value = pos["market_value"] + pnl
            position_impacts.append(
                {
                    "symbol": symbol,
                    "market_value": round(pos["market_value"], 6),
                    "weight_pct": round(weight * 100.0, 6),
                    "shock_pct": round(shock_pct, 6),
                    "pnl": round(pnl, 6),
                    "stressed_market_value": round(stressed_value, 6),
                    "beta_used": (
                        round(float(beta_map[symbol]), 6)
                        if symbol in beta_map
                        else (1.0 if needs_beta else None)
                    ),
                    "beta_source": (
                        "provided"
                        if symbol in beta_map
                        else ("unit_default" if needs_beta else None)
                    ),
                    "sector": sector_lookup.get(symbol) or None,
                    "valuation_currency": pos.get("valuation_currency") or currency,
                }
            )

        portfolio_pnl = sum(item["pnl"] for item in position_impacts)
        stressed_value = portfolio_value + portfolio_pnl
        portfolio_pnl_pct = (portfolio_pnl / portfolio_value) * 100.0

        weights = {p["symbol"]: p["market_value"] / portfolio_value for p in positions}
        concentration = compute_concentration_metrics(weights)

        sorted_by_pnl = sorted(position_impacts, key=lambda row: row["pnl"])
        top_losers = sorted_by_pnl[:5]
        top_winners = list(reversed(sorted_by_pnl[-5:])) if sorted_by_pnl else []

        assumptions["simplified_assumptions"] = simplified_flags
        if unit_beta_used:
            assumptions["beta_policy"] = "missing_beta_defaults_to_1_with_label"
            if "unit_beta_default" not in simplified_flags:
                simplified_flags.append("unit_beta_default")
                assumptions["simplified_assumptions"] = simplified_flags

        status, status_message = self._overall_status(
            needs_beta=needs_beta,
            needs_sector=needs_sector,
            unit_beta_used=unit_beta_used,
            missing_sector_symbols=missing_sector_symbols,
            target_sector=target_sector_norm,
            sector_lookup=sector_lookup,
            positions=positions,
            missing_data=missing_data,
        )

        return {
            **base,
            "status": status,
            "status_message": status_message,
            "missing_data": missing_data,
            "portfolio_pnl": round(portfolio_pnl, 6),
            "portfolio_pnl_pct": round(portfolio_pnl_pct, 6),
            "stressed_portfolio_value": round(stressed_value, 6),
            "position_impacts": position_impacts,
            "top_losers": top_losers,
            "top_winners": top_winners,
            "concentration": concentration,
            "assumptions": assumptions,
        }

    def _resolve_scenario(
        self,
        *,
        scenario_id: Optional[str],
        custom_shocks: Optional[Sequence[Mapping[str, Any]]],
    ) -> Dict[str, Any]:
        if custom_shocks:
            return build_custom_scenario(shocks=custom_shocks)
        if not scenario_id:
            raise ValueError("scenario_id is required when custom_shocks is not provided")
        return get_scenario(scenario_id, scenarios_path=self.scenarios_path)

    @staticmethod
    def _build_assumptions(
        *,
        scenario: Mapping[str, Any],
        rate_sensitivity_pct_per_100bp: float,
        betas_provided: bool,
        sector_map_provided: bool,
    ) -> Dict[str, Any]:
        return {
            "simulation_method": SIMULATION_METHOD,
            "historical_replay": False,
            "linear_factor_additivity": True,
            "instantaneous_shock": True,
            "cash_excluded": True,
            "weight_basis": "market_value_base",
            "provider_calls_on_hot_path": False,
            "beta_policy": (
                "caller_provided_betas"
                if betas_provided
                else "missing_beta_defaults_to_1_with_label"
            ),
            "sector_policy": (
                "caller_provided_sector_map_with_position_fallback"
                if sector_map_provided
                else "position_sector_field_or_missing"
            ),
            "fx_policy": (
                "apply_only_when_valuation_currency_differs_from_portfolio_base"
            ),
            "rate_policy": (
                f"equity_return_pct = -rate_sensitivity_pct_per_100bp "
                f"* (value_bp / 100); default sensitivity "
                f"{rate_sensitivity_pct_per_100bp} pct per +100bp"
            ),
            "rate_sensitivity_pct_per_100bp": float(rate_sensitivity_pct_per_100bp),
            "reuses_risk_metrics_concentration": True,
            "data_source": "portfolio_holdings_snapshot_only",
            "simplified_assumptions": [
                "deterministic_instantaneous_factor_shock",
                "linear_additive_multi_factor_shocks",
                "no_second_order_correlation_or_liquidity_effects",
                "no_historical_path_replay",
            ],
            "scenario_category": scenario.get("category"),
        }

    @staticmethod
    def _extract_positions(snapshot: Mapping[str, Any]) -> List[Dict[str, Any]]:
        exposure: Dict[str, Dict[str, Any]] = {}
        for account in snapshot.get("accounts", []) or []:
            account_currency = str(
                account.get("base_currency") or snapshot.get("currency") or "CNY"
            )
            for pos in account.get("positions", []) or []:
                symbol = str(pos.get("symbol") or "").strip().upper()
                if not symbol:
                    continue
                mv = float(pos.get("market_value_base") or 0.0)
                if mv <= _EPS:
                    continue
                valuation_currency = str(
                    pos.get("valuation_currency")
                    or pos.get("currency")
                    or account_currency
                ).upper()
                sector = pos.get("sector") or pos.get("industry") or None
                if symbol in exposure:
                    exposure[symbol]["market_value"] += mv
                else:
                    exposure[symbol] = {
                        "symbol": symbol,
                        "market_value": mv,
                        "valuation_currency": valuation_currency,
                        "sector": sector,
                        "market": str(pos.get("market") or account.get("market") or ""),
                    }
        return [exposure[key] for key in sorted(exposure.keys())]

    @staticmethod
    def _normalize_float_map(
        raw: Optional[Mapping[str, float]],
    ) -> Dict[str, float]:
        if not raw:
            return {}
        out: Dict[str, float] = {}
        for key, value in raw.items():
            symbol = str(key or "").strip().upper()
            if not symbol:
                continue
            out[symbol] = float(value)
        return out

    @staticmethod
    def _normalize_sector_map(
        raw: Optional[Mapping[str, str]],
    ) -> Dict[str, str]:
        if not raw:
            return {}
        out: Dict[str, str] = {}
        for key, value in raw.items():
            symbol = str(key or "").strip().upper()
            sector = PortfolioStressTestService._normalize_sector(value)
            if symbol and sector:
                out[symbol] = sector
        return out

    @staticmethod
    def _normalize_sector(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        return text.casefold()

    def _position_shock_pct(
        self,
        *,
        position: Mapping[str, Any],
        shocks: Sequence[Mapping[str, Any]],
        beta: Optional[float],
        sector: Optional[str],
        target_sector: Optional[str],
        base_currency: str,
        rate_sensitivity_pct_per_100bp: float,
    ) -> Tuple[float, List[str], List[str]]:
        """Return (shock_pct, missing_data_keys, simplified_flags)."""
        total = 0.0
        missing: List[str] = []
        simplified: List[str] = []
        base_ccy = str(base_currency or "CNY").upper()
        pos_ccy = str(position.get("valuation_currency") or base_ccy).upper()

        for shock in shocks:
            factor = shock["factor"]
            if factor == FACTOR_MARKET:
                if beta is None:
                    used_beta = 1.0
                    missing.append("beta")
                    simplified.append("unit_beta_default")
                else:
                    used_beta = float(beta)
                total += used_beta * float(shock["value_pct"])
            elif factor == FACTOR_SECTOR:
                if not target_sector:
                    # Should be blocked earlier; treat as no-op with missing.
                    missing.append("target_sector")
                    continue
                if not sector:
                    missing.append("sector")
                    continue
                if sector == target_sector:
                    total += float(shock["value_pct"])
            elif factor == FACTOR_FX:
                if pos_ccy != base_ccy:
                    total += float(shock["value_pct"])
                else:
                    # Domestic base-currency name: FX factor does not apply.
                    pass
            elif factor == FACTOR_RATE:
                value_bp = float(shock.get("value_bp") or 0.0)
                # +100bp with sensitivity 2.0 → equity -2.0%
                total += -float(rate_sensitivity_pct_per_100bp) * (value_bp / 100.0)
                simplified.append("uniform_equity_rate_sensitivity")
            else:
                missing.append(f"unsupported_factor:{factor}")
        return total, missing, simplified

    @staticmethod
    def _overall_status(
        *,
        needs_beta: bool,
        needs_sector: bool,
        unit_beta_used: bool,
        missing_sector_symbols: Sequence[str],
        target_sector: Optional[str],
        sector_lookup: Mapping[str, str],
        positions: Sequence[Mapping[str, Any]],
        missing_data: Sequence[str],
    ) -> Tuple[str, str]:
        if needs_sector and target_sector:
            matched = [
                p["symbol"]
                for p in positions
                if sector_lookup.get(p["symbol"]) == target_sector
            ]
            if not matched and missing_sector_symbols:
                return (
                    "partial",
                    (
                        "Sector shock could not be applied to any position because "
                        "sector classification is missing for held names. "
                        f"missing_sector_symbols={list(missing_sector_symbols)}"
                    ),
                )
            if not matched:
                return (
                    "partial",
                    (
                        f"No held position classified as target_sector "
                        f"'{target_sector}'. Portfolio shock is zero for the "
                        "sector factor; provide sector_map or choose another sector."
                    ),
                )
            if missing_sector_symbols:
                return (
                    "partial",
                    (
                        "Sector shock applied to classified names only; "
                        f"{len(missing_sector_symbols)} position(s) lack sector "
                        "and were excluded from the sector factor."
                    ),
                )

        if needs_beta and unit_beta_used:
            return (
                "partial",
                (
                    "Market shock applied with unit beta (beta=1) for one or more "
                    "names where beta was not provided. This is a simplification, "
                    "not a calibrated market beta. Supply betas to improve fidelity."
                ),
            )

        if missing_data:
            return (
                "partial",
                f"Stress result is partial; missing_data={list(missing_data)}",
            )

        return (
            "ok",
            "Deterministic factor shock applied to current holdings.",
        )
