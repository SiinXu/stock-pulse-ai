# -*- coding: utf-8 -*-
"""Event calendar service (issue #153 / T21).

Scopes events to watchlist + portfolio holdings. Defaults off via
``EVENT_CALENDAR_ENABLED`` so no extra network fetch runs unless opted in.

Impact preview reuses ``event_alerts.build_impact_context`` (read-only);
LLM text is not used to invent events.
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Set

from data_provider.base import normalize_stock_code
from src.config_parts.parsers import parse_env_bool
from src.services.event_calendar_fetcher import EventCalendarFetcher
from src.services.event_calendar_models import (
    EVENT_TYPE_TO_IMPACT_CATEGORY,
    CalendarEvent,
    normalize_certainty,
    normalize_event_types,
)
from src.services.event_alerts import build_impact_context, why_it_matters
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

ENV_EVENT_CALENDAR_ENABLED = "EVENT_CALENDAR_ENABLED"
DEFAULT_LOOKAHEAD_DAYS = 90
MAX_LOOKAHEAD_DAYS = 366
MAX_LOOKBACK_DAYS = 30
MAX_SYMBOLS = 200


def is_event_calendar_enabled(
    *,
    env: Optional[Dict[str, str]] = None,
    config: Optional[Any] = None,
) -> bool:
    """Return whether calendar fetches are allowed.

    Priority: explicit env override, then config attribute if present,
    otherwise default False (zero extra fetch).
    """
    if env is not None:
        raw_env = env.get(ENV_EVENT_CALENDAR_ENABLED)
    else:
        raw_env = os.getenv(ENV_EVENT_CALENDAR_ENABLED)
    if raw_env is not None and str(raw_env).strip() != "":
        return parse_env_bool(str(raw_env), default=False)
    if config is not None:
        return bool(getattr(config, "event_calendar_enabled", False))
    return False


def market_coverage_table() -> List[Dict[str, str]]:
    """Static coverage matrix documented for API/docs consumers."""
    return [
        {
            "market": "CN A-share",
            "earnings": "appointment + actual disclosure (akshare yysj)",
            "ex_dividend": "announced ex-date (akshare fhps)",
            "unlock": "restricted release queue (akshare)",
            "index_rebalance": "not covered (V0)",
            "macro": "not covered (V0)",
        },
        {
            "market": "HK",
            "earnings": "not covered (V0)",
            "ex_dividend": "not covered (V0)",
            "unlock": "not covered (V0)",
            "index_rebalance": "not covered (V0)",
            "macro": "not covered (V0)",
        },
        {
            "market": "US",
            "earnings": "not covered (V0)",
            "ex_dividend": "not covered (V0)",
            "unlock": "not covered (V0)",
            "index_rebalance": "not covered (V0)",
            "macro": "not covered (V0)",
        },
    ]


class EventCalendarService:
    """Assemble a watchlist/holdings-scoped event calendar."""

    def __init__(
        self,
        *,
        fetcher: Optional[EventCalendarFetcher] = None,
        portfolio_service: Optional[Any] = None,
        config: Optional[Any] = None,
        enabled_override: Optional[bool] = None,
    ) -> None:
        self._fetcher = fetcher or EventCalendarFetcher()
        self._portfolio_service = portfolio_service
        self._config = config
        self._enabled_override = enabled_override

    def get_calendar(
        self,
        *,
        symbols: Optional[Sequence[str]] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        event_types: Optional[Any] = None,
        include_impact: bool = True,
        report_language: str = "zh",
        as_of: Optional[date] = None,
    ) -> Dict[str, Any]:
        today = as_of or date.today()
        start = date_from or today
        end = date_to or (today + timedelta(days=DEFAULT_LOOKAHEAD_DAYS))
        if end < start:
            raise ValueError("date_to must be on or after date_from")
        if (end - start).days > MAX_LOOKAHEAD_DAYS + MAX_LOOKBACK_DAYS:
            raise ValueError(
                f"date range must not exceed {MAX_LOOKAHEAD_DAYS + MAX_LOOKBACK_DAYS} days"
            )
        if start < today - timedelta(days=MAX_LOOKBACK_DAYS):
            raise ValueError(
                f"date_from cannot be more than {MAX_LOOKBACK_DAYS} days before today"
            )

        types = normalize_event_types(event_types)
        enabled = (
            self._enabled_override
            if self._enabled_override is not None
            else is_event_calendar_enabled(config=self._config)
        )

        scope_symbols = self._resolve_scope_symbols(symbols)
        base: Dict[str, Any] = {
            "enabled": bool(enabled),
            "fetch_attempted": False,
            "as_of": today.isoformat(),
            "date_from": start.isoformat(),
            "date_to": end.isoformat(),
            "event_types": types,
            "symbols": sorted(scope_symbols),
            "symbol_count": len(scope_symbols),
            "event_count": 0,
            "events": [],
            "coverage": market_coverage_table(),
            "sources_attempted": [],
            "errors": [],
            "coverage_notes": [],
            "fetched_at": None,
            "impact_preview_mode": "build_impact_context" if include_impact else "off",
            "reuses_build_impact_context": bool(include_impact),
        }

        if not enabled:
            base["coverage_notes"] = [
                "EVENT_CALENDAR_ENABLED is false; no provider fetch was attempted."
            ]
            return base

        if not scope_symbols:
            base["coverage_notes"] = [
                "No watchlist or portfolio symbols in scope; nothing to fetch."
            ]
            return base

        base["fetch_attempted"] = True
        fetch_result = self._fetcher.fetch_events(
            sorted(scope_symbols),
            date_from=start,
            date_to=end,
            event_types=types,
        )
        raw_events: List[CalendarEvent] = list(fetch_result.get("events") or [])
        base["sources_attempted"] = list(fetch_result.get("sources_attempted") or [])
        base["errors"] = list(fetch_result.get("errors") or [])
        base["coverage_notes"] = list(fetch_result.get("coverage_notes") or [])
        fetched_at = fetch_result.get("fetched_at")
        if isinstance(fetched_at, datetime):
            base["fetched_at"] = fetched_at.isoformat()

        serialized: List[Dict[str, Any]] = []
        for event in raw_events:
            item = event.to_dict()
            item["certainty"] = normalize_certainty(item.get("certainty"))
            if include_impact:
                item["impact_preview"] = self._build_impact_preview(
                    event,
                    report_language=report_language,
                )
            else:
                item["impact_preview"] = None
            serialized.append(item)

        base["events"] = serialized
        base["event_count"] = len(serialized)
        return base

    def _resolve_scope_symbols(
        self,
        explicit: Optional[Sequence[str]],
    ) -> Set[str]:
        """Only watchlist / holdings symbols (intersect explicit filter if given)."""
        watchlist = self._watchlist_symbols()
        holdings = self._portfolio_symbols()
        scope = set(watchlist) | set(holdings)
        if explicit is not None:
            wanted: Set[str] = set()
            for raw in explicit:
                text = str(raw or "").strip()
                if not text:
                    continue
                wanted.add(text)
                try:
                    wanted.add(normalize_stock_code(text))
                except Exception as exc:  # broad-exception: fallback_recorded - keep raw
                    log_safe_exception(
                        logger,
                        "Event calendar explicit symbol normalize failed",
                        exc,
                        error_code="event_calendar_symbol_normalize_failed",
                        level=logging.DEBUG,
                    )
            if scope:
                scope = {
                    sym
                    for sym in scope
                    if sym in wanted
                    or self._maybe_normalize(sym) in wanted
                    or any(
                        self._maybe_normalize(w) == self._maybe_normalize(sym)
                        for w in wanted
                    )
                }
            else:
                scope = set()
        if len(scope) > MAX_SYMBOLS:
            scope = set(sorted(scope)[:MAX_SYMBOLS])
        return scope

    def _maybe_normalize(self, symbol: str) -> str:
        try:
            return normalize_stock_code(symbol)
        except Exception as exc:  # broad-exception: fallback_recorded - return raw symbol
            log_safe_exception(
                logger,
                "Event calendar symbol normalize failed",
                exc,
                error_code="event_calendar_symbol_normalize_failed",
                level=logging.DEBUG,
            )
            return str(symbol or "").strip()

    def _watchlist_symbols(self) -> Set[str]:
        config = self._config
        if config is None:
            # Prefer constructor injection; avoid bare get_config() (config-access ratchet).
            try:
                from src.application_services import get_application_services

                config = get_application_services().config
            except Exception as exc:  # broad-exception: fallback_recorded - empty watchlist
                log_safe_exception(
                    logger,
                    "Event calendar config load failed",
                    exc,
                    error_code="event_calendar_config_load_failed",
                    level=logging.DEBUG,
                )
                return set()
        refresh = getattr(config, "refresh_stock_list", None)
        if callable(refresh):
            try:
                refresh()
            except Exception as exc:  # broad-exception: fallback_recorded - continue with stale list
                log_safe_exception(
                    logger,
                    "Event calendar watchlist refresh failed",
                    exc,
                    error_code="event_calendar_watchlist_refresh_failed",
                    level=logging.DEBUG,
                )
        symbols: Set[str] = set()
        for raw in list(getattr(config, "stock_list", []) or []):
            text = str(raw or "").strip()
            if not text:
                continue
            symbols.add(text)
            try:
                symbols.add(normalize_stock_code(text))
            except Exception as exc:  # broad-exception: fallback_recorded - keep raw
                log_safe_exception(
                    logger,
                    "Event calendar watchlist symbol normalize failed",
                    exc,
                    error_code="event_calendar_symbol_normalize_failed",
                    level=logging.DEBUG,
                )
        return symbols

    def _portfolio_symbols(self) -> Set[str]:
        try:
            service = self._portfolio_service
            if service is None:
                from src.services.portfolio_service import PortfolioService

                service = PortfolioService()
            snapshot = service.get_portfolio_snapshot(
                account_id=None,
                cost_method="fifo",
                include_realtime=False,
            )
        except Exception as exc:  # broad-exception: fallback_recorded - empty holdings
            log_safe_exception(
                logger,
                "Event calendar portfolio lookup failed",
                exc,
                error_code="event_calendar_portfolio_lookup_failed",
                level=logging.DEBUG,
            )
            return set()

        symbols: Set[str] = set()
        for account in snapshot.get("accounts", []) or []:
            for position in account.get("positions", []) or []:
                pos_symbol = str(position.get("symbol") or "").strip()
                if not pos_symbol:
                    continue
                qty = position.get("quantity")
                try:
                    if qty is not None and float(qty) <= 0:
                        continue
                except (TypeError, ValueError):
                    pass
                symbols.add(pos_symbol)
                try:
                    symbols.add(normalize_stock_code(pos_symbol))
                except Exception as exc:  # broad-exception: fallback_recorded - keep raw
                    log_safe_exception(
                        logger,
                        "Event calendar portfolio symbol normalize failed",
                        exc,
                        error_code="event_calendar_symbol_normalize_failed",
                        level=logging.DEBUG,
                    )
        return symbols

    def _build_impact_preview(
        self,
        event: CalendarEvent,
        *,
        report_language: str,
    ) -> Dict[str, Any]:
        """Thin wrapper around event_alerts.build_impact_context."""
        category = EVENT_TYPE_TO_IMPACT_CATEGORY.get(event.event_type)
        what_happened = event.title
        why = why_it_matters(category, report_language=report_language) if category else ""
        event_context: Dict[str, Any] = {
            "event_category": category,
            "what_happened": what_happened,
            "why_it_matters": why or None,
            "event_categories": [category] if category else [],
            "source_name": event.source,
        }
        try:
            impact = build_impact_context(
                stock_code=event.symbol,
                event_context=event_context,
                config=self._config,
                portfolio_service=self._portfolio_service,
                analysis_records=None,
                report_language=report_language,
            )
        except Exception as exc:  # broad-exception: fallback_recorded - return explicit empty impact
            log_safe_exception(
                logger,
                "Event calendar impact preview failed",
                exc,
                error_code="event_calendar_impact_preview_failed",
                level=logging.WARNING,
            )
            return {
                "available": False,
                "what_happened": what_happened,
                "why_it_matters": None,
                "event_category": category,
                "affected": None,
                "error": "impact_preview_failed",
            }

        why_final = impact.get("why_it_matters")
        if not why_final:
            why_final = None
        available = bool(why_final or impact.get("affected"))
        return {
            "available": available,
            "what_happened": impact.get("what_happened") or what_happened,
            "why_it_matters": why_final,
            "event_category": impact.get("event_category") or category,
            "affected": impact.get("affected"),
            "related_analysis": impact.get("related_analysis"),
            "degraded": bool(impact.get("degraded")),
            "source": "event_alerts.build_impact_context",
        }
