# -*- coding: utf-8 -*-
"""Multi-symbol portfolio-level analysis for a code list (issue #128).

Accepts a watchlist / explicit basket of symbols and produces **portfolio-level**
metrics (correlation, concentration, shared risk, structural health, optional
stress) instead of stacking per-symbol conclusions.

Hard contracts:
- Reuses the existing portfolio snapshot shape and the data planes of
  ``PortfolioRiskMetricsService``, ``PortfolioHealthService``, and
  ``PortfolioStressTestService``. No parallel holdings model is introduced.
- Missing single-symbol price history never fails the whole basket; those
  symbols are excluded from weights, annotated under ``degraded_symbols``, and
  the result status becomes ``partial`` when any symbol is missing.
- Explicit size bound (``MAX_SYMBOLS``) with a clear over-limit error.
"""

from __future__ import annotations

import logging
import math
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from src.repositories.stock_repo import StockRepository
from src.services.portfolio_health_service import PortfolioHealthService
from src.services.portfolio_risk_metrics_service import (
    DEFAULT_CONFIDENCE,
    DEFAULT_HORIZON_DAYS,
    DEFAULT_LOOKBACK_TRADING_DAYS,
    PortfolioRiskMetricsService,
)
from src.services.portfolio_stress_test_service import PortfolioStressTestService
from src.services.watchlist_score_service import WatchlistScoreService

logger = logging.getLogger(__name__)

FORMULA_VERSION = "portfolio_level_analysis_v1"
WEIGHTING_MODE_EQUAL = "equal_weight"
WEIGHTING_MODE_CUSTOM = "custom_weight"
SNAPSHOT_KIND = "synthetic_basket_v1"
DEFAULT_UNIT_MARKET_VALUE = 10_000.0
MAX_SYMBOLS = 20
HIGH_CORRELATION_THRESHOLD = 0.70
MAX_CORRELATION_HIGHLIGHTS = 12
MAX_SHARED_RISK_CLUSTERS = 8
DEFAULT_STRESS_SCENARIO_ID = "market_down_10"
_STOCK_CODE_RE = re.compile(r"^[A-Za-z0-9^][A-Za-z0-9.^_-]{0,15}$")
_EPS = 1e-12

DISCLAIMER = (
    "Portfolio-level analysis is a structural risk view over a symbol basket, "
    "not investment advice. Equal-weight baskets without holdings omit real "
    "cash and PnL context; health dimensions that depend on those inputs are "
    "reported as partial when unavailable."
)


class PortfolioLevelAnalysisService:
    """Orchestrate basket-level metrics on top of existing portfolio services."""

    def __init__(
        self,
        *,
        stock_repo: Optional[StockRepository] = None,
        risk_metrics_service: Optional[PortfolioRiskMetricsService] = None,
        health_service: Optional[PortfolioHealthService] = None,
        stress_service: Optional[PortfolioStressTestService] = None,
        watchlist_score_service: Optional[WatchlistScoreService] = None,
        price_loader: Optional[
            Callable[[Sequence[str], date], Mapping[str, Optional[float]]]
        ] = None,
    ) -> None:
        self.stock_repo = stock_repo or StockRepository()
        self.risk_metrics_service = risk_metrics_service or PortfolioRiskMetricsService(
            stock_repo=self.stock_repo
        )
        self.health_service = health_service or PortfolioHealthService(
            risk_metrics_service=self.risk_metrics_service
        )
        self.stress_service = stress_service or PortfolioStressTestService()
        self.watchlist_score_service = watchlist_score_service or WatchlistScoreService()
        self._price_loader = price_loader

    def analyze(
        self,
        stock_codes: Optional[Sequence[str]] = None,
        *,
        weights: Optional[Mapping[str, float]] = None,
        as_of: Optional[date] = None,
        lookback_trading_days: int = DEFAULT_LOOKBACK_TRADING_DAYS,
        confidence: float = DEFAULT_CONFIDENCE,
        horizon_days: int = DEFAULT_HORIZON_DAYS,
        include_stress: bool = True,
        scenario_id: str = DEFAULT_STRESS_SCENARIO_ID,
        sector_map: Optional[Mapping[str, str]] = None,
        high_correlation_threshold: float = HIGH_CORRELATION_THRESHOLD,
        currency: str = "CNY",
    ) -> Dict[str, Any]:
        as_of_date = as_of or date.today()
        ordered_codes = self._normalize_codes(stock_codes)
        if not ordered_codes:
            raise ValueError("stock_codes must contain at least one symbol")
        if len(ordered_codes) > MAX_SYMBOLS:
            raise ValueError(
                f"stock_codes exceeds the portfolio-level analysis limit of "
                f"{MAX_SYMBOLS} symbols (got {len(ordered_codes)}). "
                f"Split the basket or remove symbols and retry."
            )

        threshold = self._finite(
            high_correlation_threshold,
            "high_correlation_threshold",
            minimum=0.0,
            maximum=1.0,
        )
        response_currency = str(currency or "CNY").strip().upper() or "CNY"
        requested_weights = self._normalize_weights(weights, ordered_codes)

        prices = self._load_latest_prices(ordered_codes, as_of_date)
        usable: List[str] = []
        degraded: List[Dict[str, Any]] = []
        for code in ordered_codes:
            price = prices.get(code)
            if price is None or price <= _EPS:
                degraded.append(
                    {
                        "stock_code": code,
                        "reason": "price_unavailable",
                        "detail": "No usable stored daily close for this symbol.",
                    }
                )
                continue
            usable.append(code)

        annotations: List[str] = []
        if degraded:
            annotations.append(
                f"{len(degraded)} of {len(ordered_codes)} symbols excluded due to "
                "missing or non-positive price data; remaining weights were rebased."
            )

        if not usable:
            return self._empty_all_missing_payload(
                ordered_codes=ordered_codes,
                degraded=degraded,
                as_of_date=as_of_date,
                annotations=annotations,
                currency=response_currency,
            )

        weight_map, weighting_mode = self._resolve_usable_weights(
            usable_codes=usable,
            requested=requested_weights,
        )
        snapshot = self.build_synthetic_snapshot(
            weights=weight_map,
            prices={code: float(prices[code]) for code in usable},
            as_of=as_of_date,
            currency=response_currency,
            degraded_codes=[row["stock_code"] for row in degraded],
        )

        risk = self.risk_metrics_service.get_risk_metrics(
            as_of=as_of_date,
            cost_method="fifo",
            confidence=confidence,
            horizon_days=horizon_days,
            lookback_trading_days=lookback_trading_days,
            snapshot=snapshot,
        )
        health = self.health_service.get_health(
            as_of=as_of_date,
            cost_method="fifo",
            persist=False,
            snapshot=snapshot,
            risk=risk,
        )

        stress: Optional[Dict[str, Any]] = None
        if include_stress:
            try:
                stress = self.stress_service.run_stress_test(
                    as_of=as_of_date,
                    cost_method="fifo",
                    scenario_id=scenario_id,
                    sector_map=sector_map,
                    snapshot=snapshot,
                )
            except Exception as exc:  # broad-exception: fallback_recorded - stress optional
                logger.warning(
                    "Portfolio-level stress overlay skipped: %s",
                    type(exc).__name__,
                )
                annotations.append(
                    f"Stress overlay unavailable ({type(exc).__name__}); "
                    "correlation and concentration blocks remain."
                )
                stress = {
                    "status": "unavailable",
                    "status_message": f"Stress overlay failed: {type(exc).__name__}",
                    "scenario": {"id": scenario_id},
                }

        correlation = dict(risk.get("correlation") or {})
        highlights = self._correlation_highlights(
            correlation,
            threshold=threshold,
        )
        shared_risks = self._shared_risk_exposures(
            highlights=highlights,
            sector_map=sector_map,
            concentration=dict(risk.get("concentration") or {}),
        )
        stance = self._stance_distribution(ordered_codes)

        status, status_message = self._overall_status(
            risk_status=str(risk.get("status") or ""),
            health_status=str(health.get("status") or ""),
            degraded_count=len(degraded),
            usable_count=len(usable),
            requested_count=len(ordered_codes),
        )

        return {
            "formula_version": FORMULA_VERSION,
            "analysis_mode": "portfolio_level_basket",
            "snapshot_kind": SNAPSHOT_KIND,
            "as_of": as_of_date.isoformat(),
            "currency": response_currency,
            "status": status,
            "status_message": status_message,
            "disclaimer": DISCLAIMER,
            "requested_symbols": list(ordered_codes),
            "symbols_used": list(usable),
            "symbols_requested_count": len(ordered_codes),
            "symbols_used_count": len(usable),
            "max_symbols": MAX_SYMBOLS,
            "weighting_mode": weighting_mode,
            "weights": [
                {"symbol": code, "weight_pct": round(weight_map[code] * 100.0, 6)}
                for code in usable
            ],
            "degraded_symbols": degraded,
            "annotations": annotations,
            "correlation": correlation,
            "correlation_highlights": highlights,
            "concentration": dict(risk.get("concentration") or {}),
            "var": dict(risk.get("var") or {}),
            "shared_risk_exposures": shared_risks,
            "stance_distribution": stance,
            "health": self._project_health(health),
            "stress": stress,
            "risk_metrics_status": risk.get("status"),
            "risk_history": dict(risk.get("history") or {}),
            "assumptions": {
                **dict(risk.get("assumptions") or {}),
                "basket_weighting": weighting_mode,
                "synthetic_snapshot": True,
                "cash_and_pnl_not_from_holdings": True,
                "missing_symbol_policy": "exclude_and_annotate_partial",
                "high_correlation_threshold": threshold,
                "max_symbols": MAX_SYMBOLS,
                "provider_calls_on_hot_path": False,
            },
            "calculated_at": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # Snapshot construction (same position shape as portfolio services)
    # ------------------------------------------------------------------

    def build_synthetic_snapshot(
        self,
        *,
        weights: Mapping[str, float],
        prices: Mapping[str, float],
        as_of: date,
        currency: str = "CNY",
        degraded_codes: Optional[Sequence[str]] = None,
        unit_portfolio_value: float = DEFAULT_UNIT_MARKET_VALUE * 10,
    ) -> Dict[str, Any]:
        """Build a synthetic equal/custom-weight snapshot in holdings shape."""
        if not weights:
            raise ValueError("weights must not be empty")
        total_weight = sum(float(v) for v in weights.values())
        if total_weight <= _EPS:
            raise ValueError("weights must sum to a positive total")

        positions: List[Dict[str, Any]] = []
        total_mv = 0.0
        for symbol in sorted(weights.keys()):
            weight = float(weights[symbol]) / total_weight
            market_value = unit_portfolio_value * weight
            price = float(prices.get(symbol) or 0.0)
            quantity = market_value / price if price > _EPS else 0.0
            total_mv += market_value
            positions.append(
                {
                    "symbol": symbol,
                    "market": self._infer_market(symbol),
                    "currency": currency,
                    "quantity": round(quantity, 8),
                    "market_value_base": round(market_value, 6),
                    "valuation_currency": currency,
                    "price_source": "stored_daily_close",
                    "price_provider": "stock_daily",
                    "price_date": as_of.isoformat(),
                    "price_stale": False,
                    "price_available": True,
                    "data_quality": "ok",
                    "limitations": [],
                }
            )

        limitations = [
            "synthetic_basket_equal_or_custom_weights",
            "no_cash_ledger",
            "no_realized_or_unrealized_holdings_pnl",
        ]
        degraded = [str(code).strip().upper() for code in (degraded_codes or []) if code]
        if degraded:
            limitations.append("partial_symbol_price_coverage")

        return {
            "as_of": as_of.isoformat(),
            "cost_method": "fifo",
            "currency": currency,
            "total_market_value": round(total_mv, 6),
            "total_equity": round(total_mv, 6),
            "total_cash": 0.0,
            "unrealized_pnl": 0.0,
            "realized_pnl": 0.0,
            "fx_stale": False,
            "data_quality": "partial" if degraded else "ok",
            "limitations": limitations,
            "snapshot_kind": SNAPSHOT_KIND,
            "accounts": [
                {
                    "account_id": 0,
                    "base_currency": currency,
                    "positions": positions,
                }
            ],
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _load_latest_prices(
        self,
        codes: Sequence[str],
        as_of: date,
    ) -> Dict[str, Optional[float]]:
        if self._price_loader is not None:
            loaded = dict(self._price_loader(codes, as_of) or {})
            return {str(code).strip().upper(): loaded.get(code) for code in codes}

        # Prefer a short recent window so one missing bar does not exclude a symbol
        # that still has usable history for correlation lookback.
        start = as_of - timedelta(days=45)
        out: Dict[str, Optional[float]] = {}
        for code in codes:
            rows = self.stock_repo.get_range(code, start, as_of) or []
            latest: Optional[float] = None
            for row in rows:
                close = getattr(row, "close", None)
                if close is None:
                    continue
                try:
                    close_f = float(close)
                except (TypeError, ValueError):
                    continue
                if close_f > _EPS and math.isfinite(close_f):
                    latest = close_f
            out[code] = latest
        return out

    def _stance_distribution(self, codes: Sequence[str]) -> Dict[str, Any]:
        try:
            scored = self.watchlist_score_service.score_symbols(list(codes))
        except Exception as exc:  # broad-exception: fallback_recorded - stance optional
            logger.warning(
                "Stance distribution unavailable: %s", type(exc).__name__
            )
            return {
                "status": "unavailable",
                "status_message": f"Could not load stance sources ({type(exc).__name__}).",
                "scored_count": 0,
                "unanalyzed_count": len(codes),
                "average_score": None,
                "by_operation_advice": {},
                "items": [],
            }

        items = list(scored.get("items") or [])
        by_advice: Dict[str, int] = {}
        scores: List[float] = []
        projected: List[Dict[str, Any]] = []
        scored_count = 0
        unanalyzed_count = 0
        for item in items:
            status = str(item.get("status") or "")
            advice = item.get("operation_advice")
            advice_key = str(advice).strip().lower() if advice else "unknown"
            if status == "scored":
                scored_count += 1
                if item.get("score") is not None:
                    try:
                        scores.append(float(item["score"]))
                    except (TypeError, ValueError):
                        pass
                by_advice[advice_key] = by_advice.get(advice_key, 0) + 1
            else:
                unanalyzed_count += 1
                by_advice["unanalyzed"] = by_advice.get("unanalyzed", 0) + 1
            projected.append(
                {
                    "stock_code": item.get("stock_code"),
                    "status": status,
                    "score": item.get("score"),
                    "operation_advice": item.get("operation_advice"),
                    "freshness": item.get("freshness"),
                }
            )

        avg = round(sum(scores) / len(scores), 4) if scores else None
        stance_status = "ok"
        if scored_count == 0:
            stance_status = "empty"
        elif unanalyzed_count > 0:
            stance_status = "partial"

        return {
            "status": stance_status,
            "status_message": (
                "Aggregated from existing analysis history and decision signals "
                "(no new LLM calls)."
            ),
            "scored_count": scored_count,
            "unanalyzed_count": unanalyzed_count,
            "average_score": avg,
            "by_operation_advice": by_advice,
            "items": projected,
            "formula_version": scored.get("formula_version"),
        }

    @staticmethod
    def _correlation_highlights(
        correlation: Mapping[str, Any],
        *,
        threshold: float,
    ) -> List[Dict[str, Any]]:
        if str(correlation.get("status") or "") != "ok":
            return []
        symbols = [str(s) for s in (correlation.get("symbols") or [])]
        matrix = correlation.get("matrix") or []
        if len(symbols) < 2 or not matrix:
            return []

        pairs: List[Dict[str, Any]] = []
        for i, left in enumerate(symbols):
            row = matrix[i] if i < len(matrix) else []
            for j in range(i + 1, len(symbols)):
                right = symbols[j]
                raw = row[j] if j < len(row) else None
                if raw is None:
                    continue
                try:
                    value = float(raw)
                except (TypeError, ValueError):
                    continue
                if not math.isfinite(value):
                    continue
                if abs(value) + _EPS < threshold:
                    continue
                pairs.append(
                    {
                        "left": left,
                        "right": right,
                        "correlation": round(value, 6),
                        "abs_correlation": round(abs(value), 6),
                        "direction": "positive" if value >= 0 else "negative",
                    }
                )
        pairs.sort(key=lambda item: item["abs_correlation"], reverse=True)
        return pairs[:MAX_CORRELATION_HIGHLIGHTS]

    @staticmethod
    def _shared_risk_exposures(
        *,
        highlights: Sequence[Mapping[str, Any]],
        sector_map: Optional[Mapping[str, str]],
        concentration: Mapping[str, Any],
    ) -> List[Dict[str, Any]]:
        exposures: List[Dict[str, Any]] = []

        # Union-find style clusters from high-correlation edges.
        parent: Dict[str, str] = {}

        def find(node: str) -> str:
            parent.setdefault(node, node)
            while parent[node] != node:
                parent[node] = parent[parent[node]]
                node = parent[node]
            return node

        def union(a: str, b: str) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        for pair in highlights:
            if pair.get("direction") != "positive":
                continue
            left = str(pair.get("left") or "")
            right = str(pair.get("right") or "")
            if left and right:
                union(left, right)

        clusters: Dict[str, List[str]] = {}
        for node in list(parent.keys()):
            root = find(node)
            clusters.setdefault(root, []).append(node)
        cluster_lists = [
            sorted(members)
            for members in clusters.values()
            if len(members) >= 2
        ]
        cluster_lists.sort(key=lambda members: (-len(members), members[0]))
        for index, members in enumerate(cluster_lists[:MAX_SHARED_RISK_CLUSTERS]):
            exposures.append(
                {
                    "kind": "high_correlation_cluster",
                    "symbols": members,
                    "size": len(members),
                    "summary": (
                        f"{len(members)} symbols share elevated pairwise "
                        "correlation (common return factor risk)."
                    ),
                    "rank": index + 1,
                }
            )

        if sector_map:
            by_sector: Dict[str, List[str]] = {}
            for raw_symbol, raw_sector in sector_map.items():
                symbol = str(raw_symbol or "").strip().upper()
                sector = str(raw_sector or "").strip()
                if not symbol or not sector:
                    continue
                by_sector.setdefault(sector, []).append(symbol)
            for sector, members in sorted(
                by_sector.items(), key=lambda item: (-len(item[1]), item[0])
            ):
                if len(members) < 2:
                    continue
                exposures.append(
                    {
                        "kind": "sector_concentration",
                        "sector": sector,
                        "symbols": sorted(set(members)),
                        "size": len(set(members)),
                        "summary": (
                            f"{len(set(members))} symbols share sector "
                            f"classification '{sector}'."
                        ),
                    }
                )

        top_weight = concentration.get("top_weight_pct")
        if (
            str(concentration.get("status") or "") == "ok"
            and top_weight is not None
            and float(top_weight) >= 35.0
        ):
            top_symbol = None
            for item in concentration.get("weights") or []:
                if not isinstance(item, Mapping):
                    continue
                if abs(float(item.get("weight_pct") or 0.0) - float(top_weight)) <= 1e-6:
                    top_symbol = item.get("symbol")
                    break
            exposures.append(
                {
                    "kind": "name_concentration",
                    "symbols": [top_symbol] if top_symbol else [],
                    "top_weight_pct": float(top_weight),
                    "summary": (
                        f"Top single-name weight is {float(top_weight):.1f}% of the basket."
                    ),
                }
            )

        return exposures

    @staticmethod
    def _project_health(health: Mapping[str, Any]) -> Dict[str, Any]:
        """Keep health payload bounded for the portfolio-level response."""
        keys = (
            "status",
            "status_message",
            "score",
            "partial_score",
            "band",
            "comparable",
            "coverage_ratio",
            "dimensions",
            "unavailable_dimensions",
            "effective_weights",
            "insights",
            "data_quality",
            "inputs",
            "formula_version",
            "disclaimer",
        )
        return {key: health.get(key) for key in keys if key in health}

    @staticmethod
    def _overall_status(
        *,
        risk_status: str,
        health_status: str,
        degraded_count: int,
        usable_count: int,
        requested_count: int,
    ) -> Tuple[str, str]:
        if usable_count <= 0:
            return (
                "unavailable",
                "No symbols had usable price data for portfolio-level analysis.",
            )
        if degraded_count > 0:
            return (
                "partial",
                (
                    f"Analyzed {usable_count}/{requested_count} symbols; "
                    f"{degraded_count} excluded due to missing data."
                ),
            )
        if risk_status in {"insufficient_history", "partial"}:
            return (
                "partial",
                (
                    f"Basket assembled for {usable_count} symbols, but risk metrics "
                    f"are {risk_status}."
                ),
            )
        if health_status in {"partial", "unavailable"}:
            return (
                "partial",
                (
                    "Structural health is partial for synthetic baskets without "
                    "holdings cash/PnL context; correlation and concentration remain."
                ),
            )
        if risk_status == "ok":
            return "ok", "Portfolio-level metrics computed for the requested basket."
        return risk_status or "partial", f"Risk metrics status: {risk_status or 'unknown'}"

    def _empty_all_missing_payload(
        self,
        *,
        ordered_codes: Sequence[str],
        degraded: Sequence[Mapping[str, Any]],
        as_of_date: date,
        annotations: Sequence[str],
        currency: str,
    ) -> Dict[str, Any]:
        return {
            "formula_version": FORMULA_VERSION,
            "analysis_mode": "portfolio_level_basket",
            "snapshot_kind": SNAPSHOT_KIND,
            "as_of": as_of_date.isoformat(),
            "currency": currency,
            "status": "unavailable",
            "status_message": (
                "No symbols had usable stored prices; portfolio-level metrics "
                "were not computed."
            ),
            "disclaimer": DISCLAIMER,
            "requested_symbols": list(ordered_codes),
            "symbols_used": [],
            "symbols_requested_count": len(ordered_codes),
            "symbols_used_count": 0,
            "max_symbols": MAX_SYMBOLS,
            "weighting_mode": WEIGHTING_MODE_EQUAL,
            "weights": [],
            "degraded_symbols": list(degraded),
            "annotations": list(annotations),
            "correlation": {
                "status": "unavailable",
                "status_message": "No usable symbols.",
                "symbols": [],
                "matrix": [],
                "observation_count": 0,
            },
            "correlation_highlights": [],
            "concentration": {
                "status": "empty_portfolio",
                "hhi": None,
                "effective_n": None,
                "diversification_score": None,
                "top_weight_pct": None,
                "position_count": 0,
                "weights": [],
            },
            "var": {
                "status": "unavailable",
                "status_message": "No usable symbols.",
                "confidence": None,
                "horizon_days": None,
                "var_pct": None,
                "var_value": None,
                "observation_count": 0,
                "percentile_used": None,
            },
            "shared_risk_exposures": [],
            "stance_distribution": self._stance_distribution(ordered_codes),
            "health": {
                "status": "unavailable",
                "score": None,
                "partial_score": None,
                "band": None,
                "comparable": False,
            },
            "stress": None,
            "risk_metrics_status": "empty_portfolio",
            "risk_history": {},
            "assumptions": {
                "synthetic_snapshot": True,
                "missing_symbol_policy": "exclude_and_annotate_partial",
                "max_symbols": MAX_SYMBOLS,
                "provider_calls_on_hot_path": False,
            },
            "calculated_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _normalize_codes(stock_codes: Optional[Sequence[str]]) -> List[str]:
        if stock_codes is None:
            return []
        ordered: List[str] = []
        seen = set()
        for raw in stock_codes:
            code = str(raw or "").strip().upper()
            if not code:
                raise ValueError("stock_codes must not contain empty values")
            if not _STOCK_CODE_RE.match(code):
                raise ValueError(f"invalid stock code: {code}")
            if code in seen:
                raise ValueError("stock_codes must not contain duplicates")
            seen.add(code)
            ordered.append(code)
        return ordered

    @staticmethod
    def _normalize_weights(
        weights: Optional[Mapping[str, float]],
        ordered_codes: Sequence[str],
    ) -> Optional[Dict[str, float]]:
        if weights is None:
            return None
        allowed = set(ordered_codes)
        out: Dict[str, float] = {}
        for raw_key, raw_value in weights.items():
            key = str(raw_key or "").strip().upper()
            if key not in allowed:
                raise ValueError(f"weights contains symbol not in stock_codes: {key}")
            try:
                value = float(raw_value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"weight for {key} must be a finite number") from exc
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"weight for {key} must be a finite non-negative number")
            if value <= _EPS:
                continue
            out[key] = value
        if not out:
            raise ValueError("weights must include at least one positive value")
        return out

    @staticmethod
    def _resolve_usable_weights(
        *,
        usable_codes: Sequence[str],
        requested: Optional[Mapping[str, float]],
    ) -> Tuple[Dict[str, float], str]:
        if not usable_codes:
            return {}, WEIGHTING_MODE_EQUAL
        if requested is None:
            equal = 1.0 / float(len(usable_codes))
            return {code: equal for code in usable_codes}, WEIGHTING_MODE_EQUAL

        selected = {
            code: float(requested[code])
            for code in usable_codes
            if code in requested and float(requested[code]) > _EPS
        }
        if not selected:
            equal = 1.0 / float(len(usable_codes))
            return {code: equal for code in usable_codes}, WEIGHTING_MODE_EQUAL
        total = sum(selected.values())
        return (
            {code: value / total for code, value in selected.items()},
            WEIGHTING_MODE_CUSTOM,
        )

    @staticmethod
    def _infer_market(symbol: str) -> str:
        code = symbol.upper()
        if code.startswith("HK") or code.endswith(".HK"):
            return "HK"
        if code.isalpha() and not code.isdigit():
            return "US"
        return "CN"

    @staticmethod
    def _finite(
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
