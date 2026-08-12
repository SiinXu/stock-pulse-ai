# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Peer relative-value canvas built on existing valuation estimates (issue #1139).

Reuses :class:`ValuationService.estimate` for multiples and peer medians — this
module does not recompute DCF or relative medians. Absolute estimate fields are
normalized into a single base currency when FX conversion is available.
Peers with missing metrics stay in the grid and are explicitly annotated.
"""

from __future__ import annotations

import logging
import math
from datetime import date
from typing import Any, Callable, Mapping, Optional, Sequence

from src.market.context import detect_market
from src.services.valuation_service import (
    INSUFFICIENT_FUNDAMENTALS,
    VALUATION_DISCLAIMER,
    ValuationService,
)
from src.utils.sanitize import (
    exception_chain_redaction_values,
    log_safe_exception,
)

logger = logging.getLogger(__name__)

PEER_CANVAS_SCHEMA_VERSION = "peer-valuation-canvas-v1"
MAX_PEER_CODES = 12

MULTIPLE_METRICS: tuple[str, ...] = ("pe_ratio", "pb_ratio", "ev_ebitda")
CURRENCY_METRICS: tuple[str, ...] = (
    "market_cap",
    "current_price",
    "ebitda",
    "net_debt",
    "equity_value",
)
CANVAS_METRICS: tuple[str, ...] = MULTIPLE_METRICS + CURRENCY_METRICS

PEER_SOURCE_CUSTOM = "custom"
PEER_SOURCE_INDUSTRY = "industry"
VALID_PEER_SOURCES = frozenset({PEER_SOURCE_CUSTOM, PEER_SOURCE_INDUSTRY})

MARKET_DEFAULT_CURRENCY = {
    "cn": "CNY",
    "hk": "HKD",
    "us": "USD",
    "jp": "JPY",
    "kr": "KRW",
    "tw": "TWD",
    "crypto": "USD",
}

FxConvertFn = Callable[[float, str, str], Mapping[str, Any]]
IndustryResolverFn = Callable[[str, Mapping[str, Any]], Optional[str]]


def default_currency_for_stock(stock_code: str) -> str:
    """Return the conventional listing currency for a stock code's market."""
    market = detect_market(stock_code)
    return MARKET_DEFAULT_CURRENCY.get(market, "CNY")


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


def _normalize_currency(value: Optional[str], *, fallback: str) -> str:
    text = str(value or "").strip().upper()
    if not text or len(text) < 3:
        return str(fallback or "CNY").strip().upper() or "CNY"
    return text


def _normalize_code(value: Any) -> str:
    return str(value or "").strip()


def _dedupe_codes(codes: Sequence[str], *, exclude: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    exclude_key = exclude.upper()
    for raw in codes:
        code = _normalize_code(raw)
        if not code:
            continue
        key = code.upper()
        if key == exclude_key or key in seen:
            continue
        seen.add(key)
        out.append(code)
        if len(out) >= MAX_PEER_CODES:
            break
    return out


def resolve_industry_label(
    stock_code: str,
    fundamentals: Mapping[str, Any],
    *,
    industry_label: Optional[str] = None,
) -> Optional[str]:
    """Explainable industry label from caller override or fundamentals."""
    override = str(industry_label or "").strip()
    if override:
        return override

    boards = fundamentals.get("belong_boards")
    if isinstance(boards, list):
        for item in boards:
            if not isinstance(item, Mapping):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            board_type = str(item.get("type") or "").strip().lower()
            if (
                "行业" in board_type
                or board_type in {"industry", "sector", "ind"}
                or "industry" in board_type
                or "sector" in board_type
            ):
                return name
        for item in boards:
            if isinstance(item, Mapping):
                name = str(item.get("name") or "").strip()
                if name:
                    return name

    for block_name in ("profile", "valuation", "company"):
        block = fundamentals.get(block_name)
        if isinstance(block, Mapping) and isinstance(block.get("data"), Mapping):
            data = block["data"]  # type: ignore[assignment]
        elif isinstance(block, Mapping):
            data = block
        else:
            continue
        for key in ("industry", "sector", "industry_name", "sector_name"):
            label = str(data.get(key) or "").strip()
            if label:
                return label

    _ = stock_code
    return None


def _extract_native_currency(
    stock_code: str,
    fundamentals: Mapping[str, Any],
    quote: Mapping[str, Any],
) -> str:
    for source in (quote, fundamentals):
        if not isinstance(source, Mapping):
            continue
        for key in ("currency", "quote_currency", "trading_currency"):
            raw = source.get(key)
            if raw:
                return _normalize_currency(str(raw), fallback=default_currency_for_stock(stock_code))
    earnings = fundamentals.get("earnings")
    if isinstance(earnings, Mapping):
        data = earnings.get("data") if isinstance(earnings.get("data"), Mapping) else earnings
        if isinstance(data, Mapping):
            report = data.get("financial_report")
            if isinstance(report, Mapping) and report.get("currency"):
                return _normalize_currency(
                    str(report.get("currency")),
                    fallback=default_currency_for_stock(stock_code),
                )
            if data.get("currency"):
                return _normalize_currency(
                    str(data.get("currency")),
                    fallback=default_currency_for_stock(stock_code),
                )
    return default_currency_for_stock(stock_code)


def _identity_fx(
    amount: float,
    from_currency: str,
    to_currency: str,
) -> dict[str, Any]:
    from_norm = _normalize_currency(from_currency, fallback="CNY")
    to_norm = _normalize_currency(to_currency, fallback="CNY")
    if from_norm == to_norm:
        return {
            "converted_amount": float(amount),
            "rate": 1.0,
            "is_stale": False,
            "method": "identity",
            "source": "identity",
            "rate_date": None,
        }
    return {
        "converted_amount": float(amount),
        "rate": 1.0,
        "is_stale": True,
        "method": "fx_unavailable_identity",
        "source": "unavailable",
        "rate_date": None,
    }


def _portfolio_fx_converter() -> FxConvertFn:
    def convert(amount: float, from_currency: str, to_currency: str) -> Mapping[str, Any]:
        try:
            from src.services.portfolio_service import PortfolioService

            service = PortfolioService()
            return service.convert_amount_with_provenance(
                amount=amount,
                from_currency=from_currency,
                to_currency=to_currency,
                as_of_date=date.today(),
            )
        except Exception as exc:  # broad-exception: fallback_recorded
            log_safe_exception(
                logger,
                "Peer canvas FX conversion fell back to identity",
                exc,
                error_code="peer_canvas_fx_fallback",
                level=logging.WARNING,
                exception_redaction_values=exception_chain_redaction_values(exc),
            )
            return _identity_fx(amount, from_currency, to_currency)

    return convert


def _metric_cell(
    *,
    metric: str,
    native_value: Optional[float],
    native_currency: str,
    base_currency: str,
    fx_convert: FxConvertFn,
) -> dict[str, Any]:
    if native_value is None:
        return {
            "value": None,
            "status": "missing",
            "missing_reason": "unavailable",
            "currency": base_currency if metric in CURRENCY_METRICS else None,
            "native_value": None,
            "native_currency": native_currency if metric in CURRENCY_METRICS else None,
        }

    if metric in MULTIPLE_METRICS:
        return {
            "value": _round_money(native_value),
            "status": "ok",
            "currency": None,
            "native_value": _round_money(native_value),
            "native_currency": None,
        }

    conversion = dict(fx_convert(float(native_value), native_currency, base_currency) or {})
    converted = _safe_float(conversion.get("converted_amount"))
    rate = _safe_float(conversion.get("rate"))
    is_stale = bool(conversion.get("is_stale"))
    method = str(conversion.get("method") or "unknown")
    if converted is None:
        return {
            "value": None,
            "status": "missing",
            "missing_reason": "fx_conversion_failed",
            "currency": base_currency,
            "native_value": _round_money(native_value),
            "native_currency": native_currency,
            "fx": {
                "rate": rate,
                "is_stale": True,
                "method": method,
                "source": conversion.get("source"),
            },
        }
    status = "ok"
    if is_stale and method not in {"identity", "zero"}:
        status = "fx_stale"
    return {
        "value": _round_money(converted),
        "status": status,
        "currency": base_currency,
        "native_value": _round_money(native_value),
        "native_currency": native_currency,
        "fx": {
            "rate": rate,
            "is_stale": is_stale,
            "method": method,
            "source": conversion.get("source"),
            "rate_date": conversion.get("rate_date"),
        },
    }


def _row_data_status(metrics: Mapping[str, Mapping[str, Any]]) -> str:
    statuses = [str(cell.get("status") or "missing") for cell in metrics.values()]
    if statuses and all(s == "ok" for s in statuses):
        return "ok"
    if any(s in {"ok", "fx_stale"} for s in statuses):
        return "partial"
    return "missing"


def _build_row(
    *,
    stock_code: str,
    role: str,
    raw: Mapping[str, Any],
    native_currency: str,
    base_currency: str,
    fx_convert: FxConvertFn,
) -> dict[str, Any]:
    native_metrics: dict[str, Optional[float]] = {
        "pe_ratio": _safe_float(raw.get("pe_ratio")),
        "pb_ratio": _safe_float(raw.get("pb_ratio")),
        "ev_ebitda": _safe_float(raw.get("ev_ebitda")),
        "market_cap": _safe_float(raw.get("market_cap")),
        "current_price": _safe_float(raw.get("current_price")),
        "ebitda": _safe_float(raw.get("ebitda")),
        "net_debt": _safe_float(raw.get("net_debt")),
        "equity_value": _safe_float(raw.get("equity_value")),
    }
    metrics: dict[str, Any] = {}
    for metric in CANVAS_METRICS:
        metrics[metric] = _metric_cell(
            metric=metric,
            native_value=native_metrics.get(metric),
            native_currency=native_currency,
            base_currency=base_currency,
            fx_convert=fx_convert,
        )
    missing = [name for name, cell in metrics.items() if cell.get("status") == "missing"]
    return {
        "stock_code": stock_code,
        "role": role,
        "currency": base_currency,
        "native_currency": native_currency,
        "metrics": metrics,
        "data_status": _row_data_status(metrics),
        "missing_metrics": missing,
    }


def _heatmap_cells(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Project unitless multiples into RiskHeatmap-compatible cells."""
    cells: list[dict[str, Any]] = []
    for row in rows:
        code = str(row.get("stock_code") or "")
        role = str(row.get("role") or "peer")
        label = f"{code}{' *' if role == 'target' else ''}"
        metrics = row.get("metrics") if isinstance(row.get("metrics"), Mapping) else {}
        for metric in MULTIPLE_METRICS:
            cell = metrics.get(metric) if isinstance(metrics, Mapping) else None
            value = None
            if isinstance(cell, Mapping):
                value = _safe_float(cell.get("value"))
            score = None
            if value is not None and value > 0:
                score = max(0.0, min(100.0, (value / 50.0) * 100.0))
            cells.append(
                {
                    "row_id": code,
                    "row_label": label,
                    "column_id": metric,
                    "column_label": metric.upper().replace("_", "/"),
                    "score": score,
                    "metric_value": value,
                    "metric_status": (
                        cell.get("status") if isinstance(cell, Mapping) else "missing"
                    ),
                }
            )
    return cells


class PeerValuationCanvasService:
    """Build a constrained peer valuation comparison canvas."""

    def __init__(
        self,
        *,
        valuation_service: Optional[ValuationService] = None,
        fx_convert: Optional[FxConvertFn] = None,
        industry_resolver: Optional[IndustryResolverFn] = None,
        fundamental_provider: Optional[Callable[[str], Mapping[str, Any]]] = None,
        quote_provider: Optional[Callable[[str], Mapping[str, Any]]] = None,
    ) -> None:
        self._valuation_service = valuation_service
        self._fx_convert = fx_convert or _portfolio_fx_converter()
        self._industry_resolver = industry_resolver or (
            lambda code, fundamentals: resolve_industry_label(code, fundamentals)
        )
        self._fundamental_provider = fundamental_provider
        self._quote_provider = quote_provider

    def _valuation(self) -> ValuationService:
        if self._valuation_service is not None:
            return self._valuation_service
        return ValuationService(
            fundamental_provider=self._fundamental_provider,
            quote_provider=self._quote_provider,
        )

    def _load_fundamentals(self, stock_code: str) -> Mapping[str, Any]:
        if self._fundamental_provider is not None:
            try:
                payload = self._fundamental_provider(stock_code)
                return payload if isinstance(payload, Mapping) else {}
            except Exception as exc:  # broad-exception: fallback_recorded
                log_safe_exception(
                    logger,
                    "Peer canvas fundamental lookup failed",
                    exc,
                    error_code="peer_canvas_fundamental_lookup_failed",
                    level=logging.WARNING,
                    context={"stock_code": stock_code},
                    exception_redaction_values=exception_chain_redaction_values(exc),
                )
                return {}
        service = self._valuation()
        return service._load_fundamentals(stock_code)  # noqa: SLF001

    def _load_quote(self, stock_code: str) -> Mapping[str, Any]:
        if self._quote_provider is not None:
            try:
                payload = self._quote_provider(stock_code)
                return payload if isinstance(payload, Mapping) else {}
            except Exception as exc:  # broad-exception: fallback_recorded
                log_safe_exception(
                    logger,
                    "Peer canvas quote lookup failed",
                    exc,
                    error_code="peer_canvas_quote_lookup_failed",
                    level=logging.WARNING,
                    context={"stock_code": stock_code},
                    exception_redaction_values=exception_chain_redaction_values(exc),
                )
                return {}
        service = self._valuation()
        return service._load_quote(stock_code)  # noqa: SLF001

    def build(
        self,
        stock_code: str,
        *,
        peer_source: str = PEER_SOURCE_CUSTOM,
        peer_codes: Optional[Sequence[str]] = None,
        industry_label: Optional[str] = None,
        base_currency: Optional[str] = None,
    ) -> dict[str, Any]:
        """Return target + peer valuation comparison canvas."""
        code = _normalize_code(stock_code)
        if not code:
            return {
                "schema_version": PEER_CANVAS_SCHEMA_VERSION,
                "status": "invalid_request",
                "reason": "invalid_stock_code",
                "message": "stock_code is required",
                "rows": [],
                "metrics": list(CANVAS_METRICS),
                "disclaimer": VALUATION_DISCLAIMER,
            }

        source = str(peer_source or PEER_SOURCE_CUSTOM).strip().lower()
        if source not in VALID_PEER_SOURCES:
            return {
                "schema_version": PEER_CANVAS_SCHEMA_VERSION,
                "status": "invalid_request",
                "reason": "invalid_peer_source",
                "message": (
                    f"peer_source must be one of: "
                    f"{', '.join(sorted(VALID_PEER_SOURCES))}"
                ),
                "rows": [],
                "metrics": list(CANVAS_METRICS),
                "disclaimer": VALUATION_DISCLAIMER,
            }

        fundamentals = self._load_fundamentals(code)
        quote = self._load_quote(code)
        resolved_industry = self._industry_resolver(code, fundamentals)
        if industry_label and str(industry_label).strip():
            resolved_industry = str(industry_label).strip()

        requested = _dedupe_codes(list(peer_codes or []), exclude=code)

        if source == PEER_SOURCE_CUSTOM:
            peer_set_explanation: dict[str, Any] = {
                "source": PEER_SOURCE_CUSTOM,
                "source_label": "custom",
                "explanation": "Caller-supplied peer codes (manual set).",
                "industry_label": resolved_industry,
                "requested_codes": list(requested),
                "auto_resolved": False,
            }
            if not requested:
                return {
                    "schema_version": PEER_CANVAS_SCHEMA_VERSION,
                    "status": "insufficient_peers",
                    "reason": "custom_peers_required",
                    "message": (
                        "Custom peer source requires at least one peer_codes entry."
                    ),
                    "stock_code": code,
                    "peer_set": peer_set_explanation,
                    "rows": [],
                    "metrics": list(CANVAS_METRICS),
                    "disclaimer": VALUATION_DISCLAIMER,
                }
        else:
            if not resolved_industry:
                peer_set_explanation = {
                    "source": PEER_SOURCE_INDUSTRY,
                    "source_label": None,
                    "explanation": (
                        "Industry peer source selected but no industry label is "
                        "available from fundamentals or caller override; peers "
                        "were not invented."
                    ),
                    "industry_label": None,
                    "requested_codes": list(requested),
                    "auto_resolved": False,
                }
                return {
                    "schema_version": PEER_CANVAS_SCHEMA_VERSION,
                    "status": "insufficient_peers",
                    "reason": "industry_label_unavailable",
                    "message": (
                        "Industry peer source requires a resolvable industry "
                        "label (fundamentals belong_boards/industry or "
                        "industry_label override)."
                    ),
                    "stock_code": code,
                    "peer_set": peer_set_explanation,
                    "rows": [],
                    "metrics": list(CANVAS_METRICS),
                    "disclaimer": VALUATION_DISCLAIMER,
                }
            peer_set_explanation = {
                "source": PEER_SOURCE_INDUSTRY,
                "source_label": resolved_industry,
                "explanation": (
                    f"Industry-constrained peer set for '{resolved_industry}'. "
                    "Peer codes are caller-supplied under this industry label; "
                    "missing peer metrics are kept and annotated."
                ),
                "industry_label": resolved_industry,
                "requested_codes": list(requested),
                "auto_resolved": (not bool(industry_label)) and bool(resolved_industry),
            }
            if not requested:
                return {
                    "schema_version": PEER_CANVAS_SCHEMA_VERSION,
                    "status": "insufficient_peers",
                    "reason": "industry_peers_required",
                    "message": (
                        "Industry peer source resolved the industry label but "
                        "requires peer_codes for the constrained comparison set "
                        "(constituents are not invented)."
                    ),
                    "stock_code": code,
                    "peer_set": peer_set_explanation,
                    "rows": [],
                    "metrics": list(CANVAS_METRICS),
                    "disclaimer": VALUATION_DISCLAIMER,
                }

        estimate = self._valuation().estimate(code, peer_codes=requested)
        relative = estimate.get("relative") if isinstance(estimate.get("relative"), Mapping) else {}
        snapshot = (
            estimate.get("fundamentals_snapshot")
            if isinstance(estimate.get("fundamentals_snapshot"), Mapping)
            else {}
        )
        dcf = estimate.get("dcf") if isinstance(estimate.get("dcf"), Mapping) else {}
        peer_details = relative.get("peer_details") if isinstance(relative, Mapping) else None
        if not isinstance(peer_details, list):
            peer_details = []

        details_by_code: dict[str, Mapping[str, Any]] = {}
        for item in peer_details:
            if not isinstance(item, Mapping):
                continue
            peer_code = _normalize_code(item.get("stock_code"))
            if peer_code:
                details_by_code[peer_code.upper()] = item

        base = _normalize_currency(
            base_currency,
            fallback=default_currency_for_stock(code),
        )
        target_native_ccy = _extract_native_currency(code, fundamentals, quote)
        target_ev = None
        if isinstance(relative.get("target"), Mapping):
            target_ev = relative["target"].get("ev_ebitda")
        target_raw = {
            "pe_ratio": snapshot.get("pe_ratio"),
            "pb_ratio": snapshot.get("pb_ratio"),
            "ev_ebitda": target_ev if target_ev is not None else snapshot.get("ev_ebitda"),
            "market_cap": snapshot.get("total_mv") or snapshot.get("market_cap"),
            "current_price": snapshot.get("current_price"),
            "ebitda": snapshot.get("ebitda"),
            "net_debt": snapshot.get("net_debt"),
            "equity_value": dcf.get("equity_value") if dcf.get("status") == "ok" else None,
        }
        rows: list[dict[str, Any]] = [
            _build_row(
                stock_code=code,
                role="target",
                raw=target_raw,
                native_currency=target_native_ccy,
                base_currency=base,
                fx_convert=self._fx_convert,
            )
        ]

        for peer in requested:
            detail = details_by_code.get(peer.upper(), {})
            peer_fundamentals = self._load_fundamentals(peer)
            peer_quote = self._load_quote(peer)
            peer_ccy = _extract_native_currency(peer, peer_fundamentals, peer_quote)
            if detail:
                peer_raw = {
                    "pe_ratio": detail.get("pe_ratio"),
                    "pb_ratio": detail.get("pb_ratio"),
                    "ev_ebitda": detail.get("ev_ebitda"),
                    "market_cap": detail.get("market_cap"),
                    "current_price": _safe_float(peer_quote.get("price")),
                    "ebitda": detail.get("ebitda"),
                    "net_debt": detail.get("net_debt"),
                    "equity_value": None,
                }
            else:
                peer_raw = {
                    "pe_ratio": None,
                    "pb_ratio": None,
                    "ev_ebitda": None,
                    "market_cap": None,
                    "current_price": _safe_float(peer_quote.get("price")),
                    "ebitda": None,
                    "net_debt": None,
                    "equity_value": None,
                }
            rows.append(
                _build_row(
                    stock_code=peer,
                    role="peer",
                    raw=peer_raw,
                    native_currency=peer_ccy,
                    base_currency=base,
                    fx_convert=self._fx_convert,
                )
            )

        fx_stale = any(
            isinstance(cell, Mapping)
            and (
                cell.get("status") == "fx_stale"
                or (
                    isinstance(cell.get("fx"), Mapping)
                    and bool(cell["fx"].get("is_stale"))
                    and str(cell["fx"].get("method") or "")
                    not in {"identity", "zero"}
                )
            )
            for row in rows
            for cell in (row.get("metrics") or {}).values()
        )

        peer_set_explanation["included_codes"] = [
            row["stock_code"] for row in rows if row["role"] == "peer"
        ]
        peer_set_explanation["missing_data_codes"] = [
            row["stock_code"]
            for row in rows
            if row["role"] == "peer" and row.get("data_status") in {"missing", "partial"}
        ]

        peers_block = relative.get("peers") if isinstance(relative.get("peers"), Mapping) else {}
        medians = {
            "pe_median": peers_block.get("pe_median"),
            "pb_median": peers_block.get("pb_median"),
            "ev_ebitda_median": peers_block.get("ev_ebitda_median"),
            "count_pe": peers_block.get("count_pe"),
            "count_pb": peers_block.get("count_pb"),
            "count_ev_ebitda": peers_block.get("count_ev_ebitda"),
            "aggregation": "median_of_positive_values_from_valuation_service",
        }

        relative_summary = {
            "status": relative.get("status"),
            "implied_prices": relative.get("implied_prices") or {},
            "premium_discount": relative.get("premium_discount") or {},
            "assumptions": relative.get("assumptions") or {},
        }

        usable_multiple_rows = sum(
            1
            for row in rows
            if row["role"] == "peer"
            and any(
                isinstance(row["metrics"].get(m), Mapping)
                and row["metrics"][m].get("status") in {"ok", "fx_stale"}
                for m in MULTIPLE_METRICS
            )
        )
        if usable_multiple_rows == 0:
            status = "partial" if rows else INSUFFICIENT_FUNDAMENTALS
        elif any(row.get("data_status") != "ok" for row in rows):
            status = "partial"
        else:
            status = "ok"
        if fx_stale and status == "ok":
            status = "partial"

        return {
            "schema_version": PEER_CANVAS_SCHEMA_VERSION,
            "status": status,
            "stock_code": code,
            "base_currency": base,
            "fx_stale": fx_stale,
            "peer_set": peer_set_explanation,
            "metrics": list(CANVAS_METRICS),
            "multiple_metrics": list(MULTIPLE_METRICS),
            "currency_metrics": list(CURRENCY_METRICS),
            "rows": rows,
            "medians": medians,
            "relative_summary": relative_summary,
            "heatmap_cells": _heatmap_cells(rows),
            "valuation_status": estimate.get("status"),
            "disclaimer": estimate.get("disclaimer") or VALUATION_DISCLAIMER,
        }
