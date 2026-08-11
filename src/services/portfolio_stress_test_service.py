# -*- coding: utf-8 -*-
"""Read-only, deterministic portfolio stress testing (issues #158 and #210)."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from src.config import Config
from src.services.portfolio_risk_metrics_service import compute_concentration_metrics
from src.services.portfolio_service import PortfolioService
from src.services.portfolio_stress_scenarios import (
    DEFAULT_EQUITY_RATE_SENSITIVITY_PCT_PER_100BP,
    FACTOR_FX,
    FACTOR_MARKET,
    FACTOR_RATE,
    FACTOR_SECTOR,
    active_scenarios,
    build_custom_scenario,
    get_active_scenario,
    get_scenario,
    load_scenarios,
)

_EPS = 1e-12
_RECONCILIATION_ABSOLUTE_TOLERANCE = 1e-4
SIMULATION_METHOD = "deterministic_factor_shock"
FORMULA_VERSION = "portfolio_stress_linear_v2"
SNAPSHOT_VERSION = "portfolio_snapshot_v1"
HISTORICAL_REPLAY_AVAILABLE = False
MAX_STRESS_POSITIONS = 512
MAX_INPUT_MAP_ITEMS = 256


class PortfolioStressTestService:
    """Estimate portfolio impact without materializing derived snapshot rows."""

    def __init__(
        self,
        *,
        portfolio_service: Optional[PortfolioService] = None,
        scenarios_path: Optional[str] = None,
        config: Optional[Config] = None,
    ) -> None:
        self.portfolio_service = portfolio_service or PortfolioService()
        self._uses_configured_catalog = scenarios_path is None
        resolved_config = config
        if scenarios_path is None and resolved_config is None:
            resolved_config = Config.get_instance()
        configured_path = (
            getattr(resolved_config, "portfolio_stress_scenarios_path", None)
            if resolved_config is not None
            else None
        )
        self.scenarios_path = scenarios_path if scenarios_path is not None else configured_path

    def list_scenarios(self) -> List[Dict[str, Any]]:
        if self._uses_configured_catalog:
            return active_scenarios(scenarios_path=self.scenarios_path)
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
        as_of_date = as_of or date.today()
        method = str(cost_method or "").strip().lower()
        if method not in {"fifo", "avg"}:
            raise ValueError("cost_method must be fifo or avg")
        rate_sensitivity = self._finite(
            rate_sensitivity_pct_per_100bp,
            field="rate_sensitivity_pct_per_100bp",
            minimum=_EPS,
            maximum=20.0,
        )
        scenario = self._resolve_scenario(
            scenario_id=scenario_id,
            custom_shocks=custom_shocks,
        )
        target_sector_norm = self._normalize_sector(target_sector)
        sector_lookup = self._normalize_sector_map(sector_map)
        beta_map = self._normalize_float_map(betas)
        if scenario.get("requires_target_sector") and not target_sector_norm:
            raise ValueError(f"scenario '{scenario['id']}' requires target_sector")
        if any(item["factor"] == FACTOR_SECTOR for item in scenario["shocks"]):
            if not sector_lookup:
                raise ValueError(
                    "sector scenarios are parameterized templates; POST must provide sector_map"
                )

        snapshot = self.portfolio_service.preview_portfolio_snapshot(
            account_id=account_id,
            as_of=as_of_date,
            cost_method=method,
            include_realtime=False,
        )
        response_currency = str(snapshot.get("currency") or "CNY").strip().upper()
        if not response_currency:
            raise ValueError("portfolio snapshot currency is unavailable")
        self._validate_snapshot_position_count(snapshot)
        positions, excluded = self._extract_positions(
            snapshot=snapshot,
            response_currency=response_currency,
            as_of_date=as_of_date,
        )
        portfolio_value = sum(item["market_value"] for item in positions)
        excluded_known_value = sum(
            float(item["known_market_value"])
            for item in excluded
            if item.get("known_market_value") is not None
        )
        excluded_unknown_value_count = sum(
            1 for item in excluded if item.get("known_market_value") is None
        )
        authoritative_value = self._finite(
            snapshot.get("total_market_value") or 0.0,
            field="snapshot total_market_value",
            minimum=0.0,
        )
        reconciliation_delta = (
            portfolio_value + excluded_known_value - authoritative_value
        )
        snapshot_hash = self._snapshot_hash(snapshot)
        calculated_at = datetime.now(timezone.utc).isoformat()
        snapshot_limitations = self._bounded_strings(snapshot.get("limitations"), maximum=128)
        snapshot_fx_stale = bool(snapshot.get("fx_stale"))
        snapshot_quality = "partial" if snapshot.get("data_quality") == "partial" else "ok"

        assumptions = self._build_assumptions(
            scenario=scenario,
            rate_sensitivity_pct_per_100bp=rate_sensitivity,
            betas_provided=bool(betas),
            sector_map_provided=bool(sector_lookup),
        )
        scenario_block = {
            key: scenario[key]
            for key in (
                "id",
                "name",
                "description",
                "category",
                "shocks",
                "requires_target_sector",
                "availability",
                "source",
                "version",
                "scenario_hash",
            )
        }
        scenario_block["target_sector"] = target_sector_norm
        base: Dict[str, Any] = {
            "as_of": as_of_date.isoformat(),
            "calculated_at": calculated_at,
            "snapshot_id": snapshot_hash,
            "snapshot_version": SNAPSHOT_VERSION,
            "account_id": account_id,
            "cost_method": method,
            "currency": response_currency,
            "portfolio_value": self._rounded(max(0.0, portfolio_value)),
            "authoritative_portfolio_value": self._rounded(authoritative_value),
            "reconciliation_delta": self._rounded(reconciliation_delta),
            "positions_used": len(positions),
            "excluded_position_count": len(excluded),
            "excluded_known_market_value": self._rounded(excluded_known_value),
            "excluded_unknown_value_count": excluded_unknown_value_count,
            "excluded_positions": excluded,
            "simulation_method": SIMULATION_METHOD,
            "historical_replay_available": HISTORICAL_REPLAY_AVAILABLE,
            "scenario": scenario_block,
            "assumptions": assumptions,
            "snapshot_fx_stale": snapshot_fx_stale,
            "snapshot_data_quality": snapshot_quality,
            "snapshot_limitations": snapshot_limitations,
        }

        if not positions:
            if excluded:
                status = "unavailable"
                message = "Held positions exist, but none has an available positive valuation."
                missing = ["position_valuation"]
            else:
                status = "empty_portfolio"
                message = "No held equity positions were present in the snapshot."
                missing = ["positions"]
            return {
                **base,
                "status": status,
                "status_message": message,
                "missing_data": missing,
                "portfolio_pnl": None,
                "portfolio_pnl_pct": None,
                "stressed_portfolio_value": None,
                "position_impacts": [],
                "top_losers": [],
                "top_winners": [],
                "concentration": compute_concentration_metrics({}),
            }

        needs_beta = any(item["factor"] == FACTOR_MARKET for item in scenario["shocks"])
        needs_sector = any(item["factor"] == FACTOR_SECTOR for item in scenario["shocks"])
        missing_data: List[str] = []
        simplified_flags = list(assumptions["simplified_assumptions"])
        unit_beta_used = False
        missing_sector_symbols: List[str] = []
        impacts: List[Dict[str, Any]] = []

        for position in positions:
            symbol = position["symbol"]
            beta = beta_map.get(symbol)
            sector = sector_lookup.get(symbol)
            shock_pct, position_missing, position_simplified = self._position_shock_pct(
                position=position,
                shocks=scenario["shocks"],
                beta=beta,
                sector=sector,
                target_sector=target_sector_norm,
                response_currency=response_currency,
                rate_sensitivity_pct_per_100bp=rate_sensitivity,
            )
            if shock_pct < -100.0 - _EPS:
                raise ValueError("composed position shock must not produce a return below -100%")
            shock_pct = max(-100.0, shock_pct)
            if "beta" in position_missing:
                unit_beta_used = True
            if "sector" in position_missing:
                missing_sector_symbols.append(symbol)
            for item in position_missing:
                if item not in missing_data:
                    missing_data.append(item)
            for item in position_simplified:
                if item not in simplified_flags:
                    simplified_flags.append(item)

            weight = position["market_value"] / portfolio_value
            pnl = position["market_value"] * shock_pct / 100.0
            stressed_value = position["market_value"] + pnl
            self._ensure_finite(pnl, stressed_value, weight, shock_pct)
            impacts.append(
                {
                    **position,
                    "source_market_value": self._rounded(position["source_market_value"]),
                    "market_value": self._rounded(position["market_value"]),
                    "weight_pct": self._rounded(weight * 100.0),
                    "shock_pct": self._rounded(shock_pct),
                    "pnl": self._rounded(pnl),
                    "stressed_market_value": self._rounded(max(0.0, stressed_value)),
                    "beta_used": (
                        self._rounded(beta) if beta is not None else (1.0 if needs_beta else None)
                    ),
                    "beta_source": (
                        "caller_provided" if beta is not None else ("unit_default" if needs_beta else None)
                    ),
                    "beta_as_of": None,
                    "sector": sector,
                    "classification_source": "caller_provided" if sector else None,
                    "classification_as_of": None,
                }
            )

        portfolio_pnl = sum(item["pnl"] for item in impacts)
        stressed_portfolio_value = portfolio_value + portfolio_pnl
        portfolio_pnl_pct = portfolio_pnl / portfolio_value * 100.0
        self._ensure_finite(portfolio_pnl, stressed_portfolio_value, portfolio_pnl_pct)
        if stressed_portfolio_value < -_EPS:
            raise ValueError("composed scenario produced a negative portfolio value")

        concentration = compute_concentration_metrics(
            {item["position_key"]: item["market_value"] for item in positions}
        )
        top_losers = sorted(
            (item for item in impacts if item["pnl"] < -_EPS),
            key=lambda item: (item["pnl"], item["position_key"]),
        )[:5]
        top_winners = sorted(
            (item for item in impacts if item["pnl"] > _EPS),
            key=lambda item: (-item["pnl"], item["position_key"]),
        )[:5]

        assumptions["simplified_assumptions"] = simplified_flags
        if unit_beta_used:
            assumptions["beta_policy"] = "missing_beta_defaults_to_1_with_label"
        quality_reasons: List[str] = []
        if excluded:
            quality_reasons.append("excluded_positions")
        if excluded_unknown_value_count:
            quality_reasons.append("excluded_position_value_unknown")
        if snapshot_fx_stale:
            quality_reasons.append("snapshot_fx_stale")
        if snapshot_quality == "partial" or snapshot_limitations:
            quality_reasons.append("snapshot_quality")
        if any(item["fx_stale"] or item["price_stale"] or item["data_quality"] == "partial" for item in positions):
            quality_reasons.append("position_quality")
        reconciliation_tolerance = max(
            _RECONCILIATION_ABSOLUTE_TOLERANCE,
            abs(authoritative_value) * 1e-8,
        )
        if abs(reconciliation_delta) > reconciliation_tolerance:
            quality_reasons.append("valuation_reconciliation")
            missing_data.append("valuation_reconciliation")
        status, message = self._overall_status(
            needs_beta=needs_beta,
            needs_sector=needs_sector,
            unit_beta_used=unit_beta_used,
            missing_sector_symbols=missing_sector_symbols,
            target_sector=target_sector_norm,
            sector_lookup=sector_lookup,
            positions=positions,
            missing_data=missing_data,
            quality_reasons=quality_reasons,
        )
        return {
            **base,
            "status": status,
            "status_message": message,
            "missing_data": missing_data,
            "portfolio_pnl": self._rounded(portfolio_pnl),
            "portfolio_pnl_pct": self._rounded(portfolio_pnl_pct),
            "stressed_portfolio_value": self._rounded(max(0.0, stressed_portfolio_value)),
            "position_impacts": impacts,
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
        if (scenario_id is None) == (custom_shocks is None):
            raise ValueError("exactly one of scenario_id or custom_shocks is required")
        if custom_shocks is not None:
            return build_custom_scenario(shocks=custom_shocks)
        if self._uses_configured_catalog:
            return get_active_scenario(
                str(scenario_id), scenarios_path=self.scenarios_path
            )
        return get_scenario(str(scenario_id), scenarios_path=self.scenarios_path)

    def _extract_positions(
        self,
        *,
        snapshot: Mapping[str, Any],
        response_currency: str,
        as_of_date: date,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        positions: List[Dict[str, Any]] = []
        excluded: List[Dict[str, Any]] = []
        for account_index, account in enumerate(snapshot.get("accounts", []) or []):
            account_id = int(account.get("account_id") or account_index + 1)
            account_currency = str(account.get("base_currency") or response_currency).upper()
            for position_index, raw in enumerate(account.get("positions", []) or []):
                symbol = str(raw.get("symbol") or "").strip().upper()
                if not symbol:
                    continue
                instrument_currency = str(raw.get("currency") or account_currency).upper()
                limitations = self._bounded_strings(raw.get("limitations"), maximum=32)
                excluded_base = {
                    "account_id": account_id,
                    "symbol": symbol,
                    "instrument_currency": instrument_currency,
                    "account_base_currency": account_currency,
                    "response_base_currency": response_currency,
                    "price_source": self._optional_text(raw.get("price_source"), 80),
                    "price_date": raw.get("price_date"),
                    "limitations": limitations,
                }
                if not bool(raw.get("price_available", True)):
                    excluded.append(
                        {
                            **excluded_base,
                            "reason": "price_unavailable",
                            "value_status": "unknown",
                            "known_market_value": None,
                        }
                    )
                    continue
                source_market_value = self._finite(
                    raw.get("market_value_base") or 0.0,
                    field=f"{symbol} market_value_base",
                    minimum=0.0,
                )
                if source_market_value <= _EPS:
                    excluded.append(
                        {
                            **excluded_base,
                            "reason": "non_positive_market_value",
                            "value_status": "known",
                            "known_market_value": 0.0,
                        }
                    )
                    continue
                conversion = self.portfolio_service.convert_amount_with_provenance(
                    amount=source_market_value,
                    from_currency=account_currency,
                    to_currency=response_currency,
                    as_of_date=as_of_date,
                )
                market_value = self._finite(
                    conversion.get("converted_amount"),
                    field=f"{symbol} converted market value",
                    minimum=0.0,
                )
                if market_value <= _EPS:
                    excluded.append(
                        {
                            **excluded_base,
                            "reason": "non_positive_market_value",
                            "value_status": "known",
                            "known_market_value": self._rounded(market_value),
                        }
                    )
                    continue
                fx_rate = self._finite(
                    conversion.get("rate"),
                    field=f"{symbol} FX rate",
                    minimum=_EPS,
                )
                position_key = f"{account_id}:{symbol}:{instrument_currency}:{position_index}"
                valuation_rate_raw = raw.get("valuation_fx_rate_to_account_base")
                if valuation_rate_raw is None and instrument_currency == account_currency:
                    valuation_rate = 1.0
                    valuation_source = "identity"
                    valuation_method = "identity"
                elif valuation_rate_raw is None:
                    valuation_rate = None
                    valuation_source = None
                    valuation_method = None
                else:
                    valuation_rate = self._finite(
                        valuation_rate_raw,
                        field=f"{symbol} valuation FX rate",
                        minimum=_EPS,
                    )
                    valuation_source = (
                        self._optional_text(raw.get("valuation_fx_rate_source"), 80)
                        or "unknown"
                    )
                    valuation_method = (
                        self._optional_text(raw.get("valuation_fx_rate_method"), 40)
                        or "unknown"
                    )
                positions.append(
                    {
                        "position_key": position_key,
                        "account_id": account_id,
                        "symbol": symbol,
                        "instrument_currency": instrument_currency,
                        "account_base_currency": account_currency,
                        "response_base_currency": response_currency,
                        "source_market_value": source_market_value,
                        "market_value": market_value,
                        "valuation_fx_rate_to_account_base": (
                            self._rounded(valuation_rate)
                            if valuation_rate is not None
                            else None
                        ),
                        "valuation_fx_rate_source": valuation_source,
                        "valuation_fx_rate_method": valuation_method,
                        "valuation_fx_as_of": raw.get("valuation_fx_as_of"),
                        "valuation_fx_stale": bool(raw.get("valuation_fx_stale")),
                        "fx_rate_to_response_base": self._rounded(fx_rate),
                        "fx_rate_source": self._optional_text(conversion.get("source"), 80) or "unknown",
                        "fx_rate_method": self._optional_text(conversion.get("method"), 40) or "unknown",
                        "fx_as_of": conversion.get("rate_date"),
                        "fx_stale": bool(conversion.get("is_stale")),
                        "price_source": self._optional_text(raw.get("price_source"), 80),
                        "price_provider": self._optional_text(raw.get("price_provider"), 80),
                        "price_date": raw.get("price_date"),
                        "price_stale": bool(raw.get("price_stale")),
                        "price_available": True,
                        "data_quality": "partial" if raw.get("data_quality") == "partial" else "ok",
                        "limitations": limitations,
                    }
                )
        return positions, excluded

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
            "formula_version": FORMULA_VERSION,
            "historical_replay": False,
            "linear_factor_additivity": True,
            "instantaneous_shock": True,
            "cash_excluded": True,
            "weight_basis": "response_base_market_value",
            "provider_calls_on_hot_path": False,
            "beta_policy": "caller_provided_betas" if betas_provided else "missing_beta_defaults_to_1_with_label",
            "sector_policy": "caller_provided_sector_map" if sector_map_provided else "sector_template_requires_caller_map",
            "fx_policy": "instrument-currency return versus response base; applies when instrument currency differs from response base",
            "rate_policy": "equity_return_pct = -rate_sensitivity_pct_per_100bp * (value_bp / 100)",
            "rate_sensitivity_pct_per_100bp": rate_sensitivity_pct_per_100bp,
            "reuses_risk_metrics_concentration": True,
            "data_source": "portfolio_read_only_replay",
            "simplified_assumptions": [
                "deterministic_instantaneous_factor_shock",
                "linear_additive_multi_factor_shocks",
                "no_second_order_correlation_or_liquidity_effects",
                "no_historical_path_replay",
            ],
            "scenario_category": scenario.get("category"),
        }

    def _position_shock_pct(
        self,
        *,
        position: Mapping[str, Any],
        shocks: Sequence[Mapping[str, Any]],
        beta: Optional[float],
        sector: Optional[str],
        target_sector: Optional[str],
        response_currency: str,
        rate_sensitivity_pct_per_100bp: float,
    ) -> Tuple[float, List[str], List[str]]:
        total = 0.0
        missing: List[str] = []
        simplified: List[str] = []
        for shock in shocks:
            factor = shock["factor"]
            if factor == FACTOR_MARKET:
                if beta is None:
                    used_beta = 1.0
                    missing.append("beta")
                    simplified.append("unit_beta_default")
                else:
                    used_beta = beta
                total += used_beta * float(shock["value_pct"])
            elif factor == FACTOR_SECTOR:
                if not sector:
                    missing.append("sector")
                elif sector == target_sector:
                    total += float(shock["value_pct"])
            elif factor == FACTOR_FX:
                if position["instrument_currency"] != response_currency:
                    total += float(shock["value_pct"])
            elif factor == FACTOR_RATE:
                total += -rate_sensitivity_pct_per_100bp * (float(shock["value_bp"]) / 100.0)
                simplified.append("uniform_equity_rate_sensitivity")
            self._ensure_finite(total)
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
        quality_reasons: Sequence[str],
    ) -> Tuple[str, str]:
        if needs_sector and target_sector:
            matched = [item for item in positions if sector_lookup.get(item["symbol"]) == target_sector]
            if not matched:
                return "partial", "No held position matched the caller-provided target-sector classification."
        if quality_reasons:
            return "partial", f"Stress result is partial; quality_reasons={list(quality_reasons)}"
        if needs_sector and missing_sector_symbols:
            return "partial", "Sector shock applied only to positions with caller-provided classifications."
        if needs_beta and unit_beta_used:
            return "partial", "Market shock used beta=1 for positions without caller-provided beta."
        if missing_data:
            return "partial", f"Stress result is partial; missing_data={list(missing_data)}"
        return "ok", "Deterministic factor shock applied to the read-only portfolio snapshot."

    @staticmethod
    def _normalize_float_map(raw: Optional[Mapping[str, float]]) -> Dict[str, float]:
        if raw is not None and len(raw) > MAX_INPUT_MAP_ITEMS:
            raise ValueError(f"betas must contain at most {MAX_INPUT_MAP_ITEMS} items")
        output: Dict[str, float] = {}
        for key, value in (raw or {}).items():
            symbol = str(key or "").strip().upper()
            if not symbol or len(symbol) > 64:
                raise ValueError("beta symbols must contain 1-64 characters")
            output[symbol] = PortfolioStressTestService._finite(
                value, field=f"beta for {symbol}", minimum=-5.0, maximum=5.0
            )
        return output

    @staticmethod
    def _normalize_sector_map(raw: Optional[Mapping[str, str]]) -> Dict[str, str]:
        if raw is not None and len(raw) > MAX_INPUT_MAP_ITEMS:
            raise ValueError(
                f"sector_map must contain at most {MAX_INPUT_MAP_ITEMS} items"
            )
        output: Dict[str, str] = {}
        for key, value in (raw or {}).items():
            symbol = str(key or "").strip().upper()
            sector = PortfolioStressTestService._normalize_sector(value)
            if not symbol or len(symbol) > 64:
                raise ValueError("sector-map symbols must contain 1-64 characters")
            if not sector or len(sector) > 80:
                raise ValueError("sector labels must contain 1-80 characters")
            output[symbol] = sector
        return output

    @staticmethod
    def _validate_snapshot_position_count(snapshot: Mapping[str, Any]) -> None:
        position_count = 0
        for account in snapshot.get("accounts", []) or []:
            position_count += len(account.get("positions", []) or [])
            if position_count > MAX_STRESS_POSITIONS:
                raise ValueError(
                    f"portfolio snapshot must contain at most {MAX_STRESS_POSITIONS} positions"
                )

    @staticmethod
    def _normalize_sector(value: Optional[str]) -> Optional[str]:
        text = str(value or "").strip()
        return text.casefold() if text else None

    @staticmethod
    def _finite(
        value: Any,
        *,
        field: str,
        minimum: Optional[float] = None,
        maximum: Optional[float] = None,
    ) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field} must be a finite number") from exc
        if not math.isfinite(parsed):
            raise ValueError(f"{field} must be a finite number")
        if minimum is not None and parsed < minimum:
            raise ValueError(f"{field} must be at least {minimum}")
        if maximum is not None and parsed > maximum:
            raise ValueError(f"{field} must be at most {maximum}")
        return parsed

    @staticmethod
    def _ensure_finite(*values: float) -> None:
        if not all(math.isfinite(float(value)) for value in values):
            raise ValueError("stress calculation produced a non-finite value")

    @staticmethod
    def _snapshot_hash(snapshot: Mapping[str, Any]) -> str:
        payload = json.dumps(snapshot, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _rounded(value: float) -> float:
        return round(float(value), 6)

    @staticmethod
    def _optional_text(value: Any, maximum: int) -> Optional[str]:
        text = str(value or "").strip()
        return text[:maximum] if text else None

    @staticmethod
    def _bounded_strings(value: Any, *, maximum: int) -> List[str]:
        if not isinstance(value, list):
            return []
        return [str(item)[:300] for item in value[:maximum] if str(item).strip()]
