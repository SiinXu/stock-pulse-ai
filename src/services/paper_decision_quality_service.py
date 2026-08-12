# -*- coding: utf-8 -*-
"""Paper-trading decision process-quality scores (Issue #1134).

Scores simulated trades on **process discipline**, not realized return:

1. Analysis support — was the trade backed by a DecisionSignal / analysis plan?
2. Risk-gate compliance — invalidation/stop, confidence, data quality, action alignment
3. Position discipline — size/concentration vs configured risk thresholds

Outcome metrics (win rate, avg return, calibration) are intentionally out of
scope here and remain owned by DecisionSignal post-hoc calibration (#987).
This module is the composable process-score producer for a personal-performance
view; it never redefines hit/miss or PnL semantics.
"""

from __future__ import annotations

import json
import math
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from data_provider.base import canonical_stock_code
from src.config import Config
from src.repositories.decision_signal_repo import DecisionSignalRepository
from src.services.decision_profile_policy import MIN_ACTIONABLE_CONFIDENCE
from src.services.decision_signal_data_quality import (
    DecisionSignalDataQuality,
    normalize_decision_signal_data_quality,
)
from src.services.decision_signal_service import (
    BULLISH_ACTIONS,
    DEFENSIVE_ACTIONS,
    DecisionSignalService,
)
from src.services.paper_portfolio_service import PaperAccountRequiredError
from src.services.portfolio_service import PortfolioService
from src.storage import DecisionSignalRecord


class PaperAccountNotFoundError(ValueError):
    """Raised when the target portfolio account is missing or inactive."""

    error_code = "account_not_found"

FORMULA_VERSION = "paper-decision-quality-v2"
SCORE_KIND = "process"

DIMENSION_WEIGHTS: Dict[str, float] = {
    "analysis_support": 0.40,
    "risk_gate_compliance": 0.35,
    "position_discipline": 0.25,
}

DIMENSION_KEYS: Tuple[str, ...] = (
    "analysis_support",
    "risk_gate_compliance",
    "position_discipline",
)

SIGNAL_LOOKBACK_DAYS = 7

BUY_ALIGNED_ACTIONS = frozenset(BULLISH_ACTIONS)
SELL_ALIGNED_ACTIONS = frozenset(DEFENSIVE_ACTIONS) | frozenset({"hold"})

DISCLAIMER = (
    "Paper decision quality is a process score (analysis support, risk-gate "
    "compliance, position discipline). It is not a return, win-rate, or PnL "
    "evaluation. Outcome metrics are owned by DecisionSignal post-hoc "
    "calibration (issue #987)."
)

IGNORED_RETURN_FIELDS = frozenset(
    {
        "realized_pnl",
        "realized_pnl_pct",
        "unrealized_pnl",
        "unrealized_pnl_pct",
        "return_pct",
        "stock_return_pct",
        "avg_return_pct",
        "hit",
        "miss",
        "win_rate",
        "outcome",
        "pnl",
        "pnl_pct",
    }
)


class PaperDecisionQualityService:
    """Compute explainable process scores for paper-account trades."""

    def __init__(
        self,
        *,
        portfolio_service: Optional[PortfolioService] = None,
        signal_repo: Optional[DecisionSignalRepository] = None,
        config: Optional[Config] = None,
    ) -> None:
        self._portfolio = portfolio_service
        self._signal_repo = signal_repo
        self._config = config

    @property
    def portfolio(self) -> PortfolioService:
        """Create the persistence-backed portfolio dependency only when needed."""
        if self._portfolio is None:
            self._portfolio = PortfolioService()
        return self._portfolio

    @property
    def signal_repo(self) -> DecisionSignalRepository:
        if self._signal_repo is None:
            self._signal_repo = DecisionSignalRepository()
        return self._signal_repo

    @property
    def config(self) -> Config:
        if self._config is None:
            from src.application_services import get_application_services

            self._config = get_application_services().config
        return self._config

    def score_decision(self, context: Mapping[str, Any]) -> Dict[str, Any]:
        """Score one paper decision from an explicit context mapping.

        Return-like keys may be present (fixtures with matching PnL) but never
        affect the score.
        """
        ignored = sorted(key for key in context.keys() if key in IGNORED_RETURN_FIELDS)
        side = _normalize_side(context.get("side"))
        linked = _as_mapping(context.get("linked_signal"))
        position_weight_pct = _optional_nonnegative_finite(
            context.get("position_weight_pct")
        )
        notional_pct = _optional_nonnegative_finite(
            context.get("notional_pct_of_equity")
        )
        configured_threshold = getattr(
            self.config,
            "portfolio_risk_concentration_alert_pct",
            35.0,
        )
        concentration_alert_pct = _positive_percent(
            context.get("concentration_alert_pct", configured_threshold),
            default=_positive_percent(configured_threshold, default=35.0),
        )

        analysis = _score_analysis_support(linked_signal=linked, side=side)
        risk_gate = _score_risk_gate_compliance(linked_signal=linked, side=side)
        position = _score_position_discipline(
            position_weight_pct=position_weight_pct,
            notional_pct_of_equity=notional_pct,
            concentration_alert_pct=concentration_alert_pct,
            data_quality_level=_signal_data_quality(linked),
            side=side,
        )

        dimensions = {
            "analysis_support": analysis,
            "risk_gate_compliance": risk_gate,
            "position_discipline": position,
        }
        process_score, effective_weights = _combine_dimensions(dimensions)

        evidence = {
            "side": side,
            "symbol": _optional_str(context.get("symbol")),
            "trade_date": _optional_str(context.get("trade_date")),
            "linked_signal_id": linked.get("id") if linked else None,
            "linked_signal_action": linked.get("action") if linked else None,
            "linked_signal_plan_quality": linked.get("plan_quality") if linked else None,
            "position_weight_pct": position_weight_pct,
            "notional_pct_of_equity": notional_pct,
            "concentration_alert_pct": concentration_alert_pct,
            "ignored_return_fields": ignored,
        }

        return {
            "score_kind": SCORE_KIND,
            "formula_version": FORMULA_VERSION,
            "process_score": process_score,
            "dimensions": dimensions,
            "effective_weights": effective_weights,
            "reasons": _flatten_reasons(dimensions),
            "evidence": evidence,
            "disclaimer": DISCLAIMER,
        }

    def score_paper_account(
        self,
        *,
        account_id: int,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """Score paper trades for an account with linked DecisionSignals."""

        if date_from is not None and date_to is not None and date_from > date_to:
            raise ValueError("date_from must be <= date_to")

        if isinstance(account_id, bool) or int(account_id) <= 0:
            raise ValueError("account_id must be a positive integer")
        self._require_active_paper_account(int(account_id))

        safe_limit = max(1, min(int(limit), 200))
        trade_page = self.portfolio.list_trade_events(
            account_id=int(account_id),
            date_from=date_from,
            date_to=date_to,
            page=1,
            page_size=safe_limit,
        )
        trades = list(trade_page.get("items") or [])
        total_trade_count = max(
            len(trades),
            int(trade_page.get("total") or 0),
        )

        as_of = date_to or date.today()
        concentration_alert_pct = _positive_percent(
            getattr(
                self.config,
                "portfolio_risk_concentration_alert_pct",
                35.0,
            ),
            default=35.0,
        )
        # Equity is resolved per trade date so historical size discipline is
        # path-reproducible (not skewed by later deposits/trades).
        snapshot_by_date: Dict[date, Optional[Mapping[str, Any]]] = {}

        items: List[Dict[str, Any]] = []
        for trade in trades:
            items.append(
                self._score_trade_row(
                    account_id=int(account_id),
                    trade=trade,
                    snapshot_by_date=snapshot_by_date,
                    concentration_alert_pct=concentration_alert_pct,
                )
            )

        return {
            "score_kind": SCORE_KIND,
            "formula_version": FORMULA_VERSION,
            "disclaimer": DISCLAIMER,
            "account_id": int(account_id),
            "account_type": "paper",
            "as_of": as_of.isoformat(),
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
            "sample_size": len(items),
            "total_trade_count": total_trade_count,
            "truncated": total_trade_count > len(items),
            "aggregate": _aggregate_items(items),
            "items": items,
            "division_of_labor": {
                "this_issue": 1134,
                "owns": "process quality for paper trades",
                "does_not_own": "outcome / return / win-rate personal performance",
                "outcome_owner_issue": 987,
            },
        }

    def _require_active_paper_account(self, account_id: int) -> None:
        """Validate active paper account via public portfolio/repo surfaces only."""

        account = self.portfolio.repo.get_account(
            int(account_id), include_inactive=False
        )
        if account is None:
            raise PaperAccountNotFoundError(
                f"Active account not found: {account_id}"
            )
        kind_row = self.portfolio.kind_repo.get(account_id=int(account_id))
        if kind_row is None or str(getattr(kind_row, "account_type", "")) != "paper":
            raise PaperAccountRequiredError(
                f"Account {account_id} is not a paper trading account"
            )

    def _account_snapshot_as_of(
        self,
        *,
        account_id: int,
        as_of: date,
    ) -> Optional[Mapping[str, Any]]:
        """Replay without materializing derived rows and return the exact account."""
        snapshot = self.portfolio.preview_portfolio_snapshot(
            account_id=int(account_id),
            as_of=as_of,
            include_realtime=False,
        )
        return _account_snapshot(snapshot, account_id=int(account_id))

    def _score_trade_row(
        self,
        *,
        account_id: int,
        trade: Mapping[str, Any],
        snapshot_by_date: Dict[date, Optional[Mapping[str, Any]]],
        concentration_alert_pct: float,
    ) -> Dict[str, Any]:
        symbol = str(trade.get("symbol") or "")
        side = _normalize_side(trade.get("side"))
        trade_date = _parse_date(trade.get("trade_date"))
        quantity = _optional_finite(trade.get("quantity")) or 0.0
        price = _optional_finite(trade.get("price")) or 0.0
        notional = abs(quantity * price)

        notional_pct: Optional[float] = None
        equity_as_of: Optional[float] = None
        equity_basis = "unavailable"
        position_weight_pct: Optional[float] = None
        position_basis = "unavailable"
        if trade_date is not None:
            if trade_date not in snapshot_by_date:
                snapshot_by_date[trade_date] = self._account_snapshot_as_of(
                    account_id=account_id, as_of=trade_date
                )
            account_snapshot = snapshot_by_date[trade_date]
            equity_as_of = _equity_from_account_snapshot(account_snapshot)
            if equity_as_of is not None and equity_as_of > 0:
                notional_pct = notional / equity_as_of * 100.0
                equity_basis = "trade_date_snapshot"
                position_weight_pct = _position_weight_for_symbol(
                    account_snapshot,
                    symbol=symbol,
                    market=_optional_str(trade.get("market")),
                    equity=equity_as_of,
                )
                if position_weight_pct is not None:
                    position_basis = "trade_date_position"

        linkage = self._find_supporting_signal(
            symbol=symbol,
            market=_optional_str(trade.get("market")),
            trade_date=trade_date,
            trade_created_at=_parse_datetime(trade.get("created_at")),
            side=side,
        )
        linked_record = linkage.get("signal")
        linked = _signal_record_to_context(linked_record) if linked_record else None

        context = {
            "side": side,
            "symbol": symbol,
            "trade_date": trade_date.isoformat() if trade_date else None,
            "linked_signal": linked,
            # Never substitute one trade's notional for missing resulting-position
            # evidence. The real notional percentage is retained below as evidence.
            "notional_pct_of_equity": None,
            "position_weight_pct": position_weight_pct,
            "concentration_alert_pct": concentration_alert_pct,
        }
        scored = self.score_decision(context)
        evidence = dict(scored["evidence"])
        evidence.update(
            {
                "equity_as_of": equity_as_of,
                "equity_basis": equity_basis,
                "position_basis": position_basis,
                "notional_pct_of_equity": notional_pct,
                "signal_candidate_count": int(linkage.get("candidate_count") or 0),
                "signal_linkage_ambiguous": bool(
                    linkage.get("linkage_ambiguous")
                ),
                "signal_pool": linkage.get("pool") or "none",
                "signal_linkage_status": linkage.get("status") or "none",
            }
        )
        return {
            "trade_id": trade.get("id"),
            "symbol": symbol,
            "market": trade.get("market"),
            "side": side,
            "trade_date": trade.get("trade_date"),
            "quantity": quantity,
            "price": price,
            "linked_signal_id": linked.get("id") if linked else None,
            "process_score": scored["process_score"],
            "dimensions": scored["dimensions"],
            "effective_weights": scored["effective_weights"],
            "reasons": scored["reasons"],
            "evidence": evidence,
            "score_kind": SCORE_KIND,
            "formula_version": FORMULA_VERSION,
        }

    def _find_supporting_signal(
        self,
        *,
        symbol: str,
        market: Optional[str],
        trade_date: Optional[date],
        trade_created_at: Optional[datetime],
        side: str,
    ) -> Dict[str, Any]:
        empty = {
            "signal": None,
            "candidate_count": 0,
            "linkage_ambiguous": False,
            "pool": "none",
            "status": "none",
        }
        if not symbol or trade_date is None:
            return empty
        codes = _signal_lookup_codes(symbol, market=market)
        created_to = datetime.combine(trade_date, time(23, 59, 59))
        if trade_created_at is not None and trade_created_at.date() == trade_date:
            created_to = min(created_to, trade_created_at)
        created_from = datetime.combine(
            trade_date - timedelta(days=SIGNAL_LOOKBACK_DAYS),
            time.min,
        )
        rows, _total = self.signal_repo.list(
            stock_codes=list(codes),
            market=market,
            created_from=created_from,
            created_to=created_to,
            page=1,
            page_size=20,
        )
        if not rows:
            return empty
        preferred_actions = (
            BUY_ALIGNED_ACTIONS if side == "buy" else SELL_ALIGNED_ACTIONS
        )
        aligned = [
            row
            for row in rows
            if str(getattr(row, "action", "") or "") in preferred_actions
        ]
        pool_name = "action_aligned" if aligned else "any_in_lookback"
        pool = aligned or list(rows)
        plan_rank = {"complete": 0, "partial": 1, "minimal": 2, "unknown": 3}

        def sort_key(row: DecisionSignalRecord) -> Tuple[int, int, datetime, int]:
            source_rank = 0 if str(getattr(row, "source_type", "")) == "analysis" else 1
            quality = plan_rank.get(str(getattr(row, "plan_quality", "unknown")), 3)
            created = getattr(row, "created_at", None) or datetime.min
            return (
                -source_rank,
                -quality,
                created,
                int(getattr(row, "id", 0) or 0),
            )

        pool.sort(key=sort_key, reverse=True)
        ambiguous = len(pool) > 1
        return {
            # A heuristic cannot honestly identify one supporting decision when
            # multiple equally eligible records remain. Preserve the ambiguity
            # as evidence and score signal-dependent dimensions as unsupported.
            "signal": None if ambiguous else pool[0],
            "candidate_count": len(pool),
            "linkage_ambiguous": ambiguous,
            "pool": pool_name,
            "status": "ambiguous" if ambiguous else "unique_inferred",
        }


def _signal_lookup_codes(symbol: str, *, market: Optional[str]) -> List[str]:
    """Build stock-code lookup keys via public DecisionSignal normalizers only."""

    primary = DecisionSignalService.normalize_stock_code_for_signal(
        symbol, market=market
    )
    codes = [primary]
    if market is None:
        canonical = canonical_stock_code(symbol)
        if canonical and canonical not in codes:
            codes.append(canonical)
    return [code for code in codes if code]


def score_paper_decision_context(context: Mapping[str, Any]) -> Dict[str, Any]:
    """Module-level pure entry for fixtures and offline tests."""

    return PaperDecisionQualityService(config=Config()).score_decision(context)


def _score_analysis_support(
    *,
    linked_signal: Optional[Mapping[str, Any]],
    side: str,
) -> Dict[str, Any]:
    reasons: List[Dict[str, str]] = []
    if not linked_signal:
        reasons.append(
            {
                "code": "no_analysis_support",
                "message": "No DecisionSignal or analysis plan was linked to this trade.",
            }
        )
        return _dimension(score=0.0, reasons=reasons, status="ok")

    score = 40.0
    reasons.append(
        {
            "code": "signal_linked",
            "message": "A DecisionSignal was found within the lookback window.",
        }
    )

    action = str(linked_signal.get("action") or "").strip().lower()
    if _action_aligns(side, action):
        score += 20.0
        reasons.append(
            {
                "code": "action_aligned",
                "message": f"Signal action '{action}' aligns with trade side '{side}'.",
            }
        )
    else:
        score -= 10.0
        reasons.append(
            {
                "code": "action_misaligned",
                "message": (
                    f"Signal action '{action or 'missing'}' does not support "
                    f"trade side '{side}'."
                ),
            }
        )

    reason_text = _optional_str(linked_signal.get("reason"))
    if reason_text:
        score += 15.0
        reasons.append(
            {
                "code": "reason_present",
                "message": "Signal includes a human-readable reason.",
            }
        )
    else:
        reasons.append(
            {
                "code": "reason_missing",
                "message": "Signal has no reason text.",
            }
        )

    plan_quality = str(linked_signal.get("plan_quality") or "unknown").lower()
    if plan_quality in {"complete", "partial"}:
        score += 15.0
        reasons.append(
            {
                "code": "plan_quality_adequate",
                "message": f"Plan quality is '{plan_quality}'.",
            }
        )
    else:
        reasons.append(
            {
                "code": "plan_quality_weak",
                "message": f"Plan quality is '{plan_quality}' (prefer complete/partial).",
            }
        )

    source_type = str(linked_signal.get("source_type") or "").lower()
    if source_type == "analysis" or linked_signal.get("evidence"):
        score += 10.0
        reasons.append(
            {
                "code": "analysis_or_evidence",
                "message": "Signal is analysis-sourced or carries evidence.",
            }
        )

    return _dimension(score=_clamp(score), reasons=reasons, status="ok")


def _score_risk_gate_compliance(
    *,
    linked_signal: Optional[Mapping[str, Any]],
    side: str,
) -> Dict[str, Any]:
    reasons: List[Dict[str, str]] = []
    if not linked_signal:
        if side == "buy":
            reasons.append(
                {
                    "code": "risk_gate_unverifiable",
                    "message": (
                        "Buy without a linked signal cannot verify invalidation, "
                        "stop-loss, confidence, or data-quality gates."
                    ),
                }
            )
            return _dimension(score=15.0, reasons=reasons, status="ok")
        reasons.append(
            {
                "code": "risk_gate_unverifiable_sell",
                "message": "Sell without a linked signal; risk-gate check is limited.",
            }
        )
        return _dimension(score=55.0, reasons=reasons, status="ok")

    score = 100.0
    action = str(linked_signal.get("action") or "").strip().lower()
    invalidation = _optional_str(linked_signal.get("invalidation"))
    stop_loss = _optional_finite(linked_signal.get("stop_loss"))
    confidence = _optional_finite(linked_signal.get("confidence"))
    data_quality = _signal_data_quality(linked_signal)
    risk_summary = _optional_str(linked_signal.get("risk_summary"))

    if side == "buy":
        if not invalidation and stop_loss is None:
            score -= 40.0
            reasons.append(
                {
                    "code": "missing_invalidation_or_stop_loss",
                    "message": "Buy lacks both invalidation text and a stop-loss level.",
                }
            )
        else:
            reasons.append(
                {
                    "code": "invalidation_or_stop_present",
                    "message": "Buy has invalidation text and/or a stop-loss level.",
                }
            )

        if confidence is None:
            score -= 20.0
            reasons.append(
                {
                    "code": "missing_confidence",
                    "message": "Actionable buy is missing confidence.",
                }
            )
        elif confidence < MIN_ACTIONABLE_CONFIDENCE:
            score -= 20.0
            reasons.append(
                {
                    "code": "confidence_below_threshold",
                    "message": (
                        f"Confidence {confidence:.2f} is below the actionable "
                        f"threshold {MIN_ACTIONABLE_CONFIDENCE:.2f}."
                    ),
                }
            )
        else:
            reasons.append(
                {
                    "code": "confidence_ok",
                    "message": (
                        f"Confidence {confidence:.2f} meets the actionable threshold."
                    ),
                }
            )

        if data_quality in {"poor", "unknown"}:
            score -= 25.0
            reasons.append(
                {
                    "code": "insufficient_data_quality",
                    "message": (
                        f"Data quality '{data_quality}' is too weak for a full-size buy."
                    ),
                }
            )
        elif data_quality == "low":
            score -= 15.0
            reasons.append(
                {
                    "code": "elevated_data_gaps",
                    "message": (
                        "Data quality is low; size and confidence should be restrained."
                    ),
                }
            )
        else:
            reasons.append(
                {
                    "code": "data_quality_ok",
                    "message": (
                        f"Data quality '{data_quality}' supports an actionable plan."
                    ),
                }
            )

        if action in {"watch", "alert", "avoid", "sell", "reduce", "hold"}:
            score -= 30.0
            reasons.append(
                {
                    "code": "trade_against_risk_gate",
                    "message": (
                        f"Trade side buy conflicts with signal action '{action}' "
                        "(risk gate would not authorize a buy)."
                    ),
                }
            )
    else:
        if action in SELL_ALIGNED_ACTIONS or action in DEFENSIVE_ACTIONS:
            reasons.append(
                {
                    "code": "defensive_action_aligned",
                    "message": (
                        f"Sell aligns with defensive/neutral signal action '{action}'."
                    ),
                }
            )
        elif action in BUY_ALIGNED_ACTIONS:
            score -= 15.0
            reasons.append(
                {
                    "code": "sell_against_bullish_signal",
                    "message": (
                        f"Sell while the latest linked signal is still '{action}'."
                    ),
                }
            )
        if not invalidation and stop_loss is None and not risk_summary:
            score -= 10.0
            reasons.append(
                {
                    "code": "exit_plan_thin",
                    "message": "Exit has no invalidation, stop-loss, or risk summary.",
                }
            )

    if risk_summary and side == "buy":
        score = min(100.0, score + 5.0)
        reasons.append(
            {
                "code": "risk_notes_present",
                "message": "Signal includes a risk summary note.",
            }
        )

    return _dimension(score=_clamp(score), reasons=reasons, status="ok")


def _score_position_discipline(
    *,
    position_weight_pct: Optional[float],
    notional_pct_of_equity: Optional[float],
    concentration_alert_pct: float,
    data_quality_level: DecisionSignalDataQuality,
    side: str,
) -> Dict[str, Any]:
    reasons: List[Dict[str, str]] = []
    weight = position_weight_pct
    if weight is None:
        weight = notional_pct_of_equity
    if weight is None:
        reasons.append(
            {
                "code": "position_size_unavailable",
                "message": "Position weight / notional percent was not available.",
            }
        )
        return _dimension(score=None, reasons=reasons, status="unavailable")

    alert = max(1.0, float(concentration_alert_pct))
    ideal = alert * 0.5
    poor = alert * 2.0

    if weight <= ideal:
        score = 100.0
        reasons.append(
            {
                "code": "size_within_ideal",
                "message": (
                    f"Size {weight:.1f}% of equity is within the ideal band "
                    f"(≤ {ideal:.1f}%, half of concentration alert {alert:.1f}%)."
                ),
            }
        )
    elif weight >= poor:
        score = 0.0
        reasons.append(
            {
                "code": "size_exceeds_poor_band",
                "message": (
                    f"Size {weight:.1f}% of equity is at/above the poor band "
                    f"({poor:.1f}%, 2× concentration alert)."
                ),
            }
        )
    else:
        ratio = (weight - ideal) / (poor - ideal)
        score = 100.0 * (1.0 - ratio)
        reasons.append(
            {
                "code": "size_elevated",
                "message": (
                    f"Size {weight:.1f}% of equity is above ideal {ideal:.1f}% "
                    f"toward poor {poor:.1f}%."
                ),
            }
        )

    if data_quality_level in {"poor", "unknown", "low"} and weight > ideal:
        penalty = 25.0 if data_quality_level in {"poor", "unknown"} else 15.0
        score = max(0.0, score - penalty)
        reasons.append(
            {
                "code": "size_not_reduced_for_gaps",
                "message": (
                    f"Data quality '{data_quality_level}' with size {weight:.1f}% "
                    f"above ideal {ideal:.1f}% violates gap-aware position discipline."
                ),
            }
        )
    elif data_quality_level in {"poor", "unknown", "low"} and weight <= ideal:
        reasons.append(
            {
                "code": "size_restrained_for_gaps",
                "message": (
                    f"Size stayed restrained ({weight:.1f}%) despite data quality "
                    f"'{data_quality_level}'."
                ),
            }
        )

    if side == "sell":
        reasons.append(
            {
                "code": "sell_resulting_exposure_evaluated",
                "message": (
                    "Sell position discipline is based on the resulting exposure; "
                    "a sell is not automatically treated as disciplined."
                ),
            }
        )

    return _dimension(
        score=_clamp(score),
        reasons=reasons,
        status="ok",
        inputs={
            "position_weight_pct": weight,
            "concentration_alert_pct": alert,
            "ideal_pct": ideal,
            "poor_pct": poor,
        },
    )


def _combine_dimensions(
    dimensions: Mapping[str, Mapping[str, Any]],
) -> Tuple[float, Dict[str, float]]:
    available: List[Tuple[str, float, float]] = []
    for key in DIMENSION_KEYS:
        dim = dimensions[key]
        if dim.get("status") != "ok" or dim.get("score") is None:
            continue
        available.append((key, float(DIMENSION_WEIGHTS[key]), float(dim["score"])))

    if not available:
        return 0.0, {key: 0.0 for key in DIMENSION_KEYS}

    total_weight = sum(weight for _, weight, _ in available)
    if total_weight <= 0:
        return 0.0, {key: 0.0 for key in DIMENSION_KEYS}

    process_score = 0.0
    effective: Dict[str, float] = {key: 0.0 for key in DIMENSION_KEYS}
    for key, weight, score in available:
        share = weight / total_weight
        effective[key] = round(share, 6)
        process_score += share * score
    return round(_clamp(process_score), 2), effective


def _aggregate_items(items: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    if not items:
        return {
            "sample_size": 0,
            "process_score": None,
            "status": "empty",
            "dimensions": {
                key: {"score": None, "status": "unavailable"} for key in DIMENSION_KEYS
            },
        }

    scores = [float(item["process_score"]) for item in items]
    avg = round(sum(scores) / len(scores), 2)
    dim_avgs: Dict[str, Any] = {}
    for key in DIMENSION_KEYS:
        dim_scores = [
            float(item["dimensions"][key]["score"])
            for item in items
            if item.get("dimensions", {}).get(key, {}).get("score") is not None
        ]
        if not dim_scores:
            dim_avgs[key] = {"score": None, "status": "unavailable", "sample_size": 0}
        else:
            dim_avgs[key] = {
                "score": round(sum(dim_scores) / len(dim_scores), 2),
                "status": "ok",
                "sample_size": len(dim_scores),
            }
    return {
        "sample_size": len(items),
        "process_score": avg,
        "status": "ok",
        "dimensions": dim_avgs,
        "min_process_score": round(min(scores), 2),
        "max_process_score": round(max(scores), 2),
    }


def _dimension(
    *,
    score: Optional[float],
    reasons: List[Dict[str, str]],
    status: str,
    inputs: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    return {
        "status": status,
        "score": None if score is None else round(_clamp(float(score)), 2),
        "reasons": reasons,
        "inputs": inputs or {},
    }


def _flatten_reasons(
    dimensions: Mapping[str, Mapping[str, Any]],
) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for key in DIMENSION_KEYS:
        for reason in dimensions[key].get("reasons") or []:
            if isinstance(reason, Mapping):
                out.append(
                    {
                        "dimension": key,
                        "code": str(reason.get("code") or ""),
                        "message": str(reason.get("message") or ""),
                    }
                )
    return out


def _action_aligns(side: str, action: str) -> bool:
    if side == "buy":
        return action in BUY_ALIGNED_ACTIONS
    if side == "sell":
        return action in SELL_ALIGNED_ACTIONS or action in DEFENSIVE_ACTIONS
    return False


def _signal_data_quality(
    linked_signal: Optional[Mapping[str, Any]],
) -> DecisionSignalDataQuality:
    if not linked_signal:
        return "unknown"
    raw = linked_signal.get("data_quality_level")
    if raw is None:
        raw = linked_signal.get("data_quality_summary")
    return normalize_decision_signal_data_quality(raw)


def _signal_record_to_context(row: DecisionSignalRecord) -> Dict[str, Any]:
    evidence = None
    data_quality_summary = None
    try:
        raw_evidence = getattr(row, "evidence_json", None)
        if raw_evidence:
            evidence = json.loads(raw_evidence)
    except (TypeError, json.JSONDecodeError):
        evidence = None
    try:
        raw_dq = getattr(row, "data_quality_summary_json", None)
        if raw_dq:
            data_quality_summary = json.loads(raw_dq)
    except (TypeError, json.JSONDecodeError):
        data_quality_summary = None

    return {
        "id": getattr(row, "id", None),
        "action": getattr(row, "action", None),
        "confidence": getattr(row, "confidence", None),
        "invalidation": getattr(row, "invalidation", None),
        "stop_loss": getattr(row, "stop_loss", None),
        "reason": getattr(row, "reason", None),
        "risk_summary": getattr(row, "risk_summary", None),
        "plan_quality": getattr(row, "plan_quality", None),
        "source_type": getattr(row, "source_type", None),
        "evidence": evidence,
        "data_quality_summary": data_quality_summary,
        "data_quality_level": normalize_decision_signal_data_quality(
            data_quality_summary
        ),
    }


def _account_snapshot(
    snapshot: Mapping[str, Any],
    *,
    account_id: int,
) -> Optional[Mapping[str, Any]]:
    for entry in snapshot.get("accounts") or []:
        if not isinstance(entry, Mapping):
            continue
        try:
            matches = int(entry.get("account_id", -1)) == int(account_id)
        except (TypeError, ValueError):
            matches = False
        if matches:
            return entry
    return None


def _equity_from_account_snapshot(
    account_snapshot: Optional[Mapping[str, Any]],
) -> Optional[float]:
    if not account_snapshot:
        return None
    equity = _optional_finite(account_snapshot.get("total_equity"))
    return equity if equity is not None and equity > 0 else None


def _position_weight_for_symbol(
    account_snapshot: Optional[Mapping[str, Any]],
    *,
    symbol: str,
    market: Optional[str],
    equity: float,
) -> Optional[float]:
    if not account_snapshot or equity <= 0:
        return None
    target = canonical_stock_code(symbol)
    if not target:
        return None
    market_key = (market or "").strip().lower()
    positions = account_snapshot.get("positions")
    if not isinstance(positions, list):
        return None
    for position in positions:
        if not isinstance(position, Mapping):
            continue
        position_symbol = canonical_stock_code(str(position.get("symbol") or ""))
        position_market = str(position.get("market") or "").strip().lower()
        if position_symbol != target or (market_key and position_market != market_key):
            continue
        if position.get("price_available") is False:
            return None
        market_value = _optional_finite(position.get("market_value_base"))
        if market_value is None or market_value < 0:
            return None
        return market_value / equity * 100.0
    # A fully exited position is a real zero exposure, not missing evidence.
    return 0.0


def _normalize_side(value: Any) -> str:
    side = str(value or "").strip().lower()
    if side not in {"buy", "sell"}:
        raise ValueError("side must be buy or sell")
    return side


def _optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_finite(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool) or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _optional_nonnegative_finite(value: Any) -> Optional[float]:
    number = _optional_finite(value)
    if number is None or number < 0.0:
        return None
    return number


def _parse_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _parse_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    # Repository timestamps are naive local datetimes. Normalize an aware API
    # timestamp only for a safe ordering comparison against those rows.
    return parsed.replace(tzinfo=None)


def _positive_percent(value: Any, *, default: float) -> float:
    number = _optional_finite(value)
    if number is None or number <= 0.0 or number > 100.0:
        return float(default)
    return number


def _as_mapping(value: Any) -> Optional[Dict[str, Any]]:
    if isinstance(value, Mapping):
        return dict(value)
    return None


def _clamp(score: float) -> float:
    if not math.isfinite(score):
        return 0.0
    if score < 0.0:
        return 0.0
    if score > 100.0:
        return 100.0
    return float(score)
