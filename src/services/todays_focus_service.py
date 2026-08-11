# -*- coding: utf-8 -*-
"""Fresh, deterministic Today's Focus aggregation (Issue #157 / T26).

"Today" is executable and market-aware:

- A-shares (cn) use Asia/Shanghai local calendar day boundaries
- Hong Kong (hk) use Asia/Hong_Kong local calendar day boundaries
- United States (us) use America/New_York local calendar day boundaries
- Unrecognized symbols fall back to the configured daily-brief timezone

Cross-market rule: each evidence row is freshened against the target symbol's
own market-local day window. A single build may therefore accept a US-morning
alert while rejecting the same absolute timestamp for a China-listed symbol
(or vice versa). Non-trading days keep the same local calendar-day window;
prior-session evidence is never rolled forward to pad the list.

Naive persisted timestamps follow the repository's UTC-naive storage
convention (``assume_utc``). Missing timestamps are excluded.

The runtime reads only managed local stores. Alert evidence uses a targeted
non-page-1 query that covers every requested target and only ``triggered``
status. Portfolio positions are loaded from the full cached-position set (no
first-page truncation) and non-finite amount / weight / change values are
rejected rather than coerced to zero. No lifetime P&L is presented as a daily
move.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Set, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.core.trading_calendar import (
    MARKET_TIMEZONE,
    MarketSessionStatus,
    classify_market_session,
)
from src.market.context import detect_market
from src.services.stock_code_utils import (
    build_daily_code_candidates,
    canonicalize_analysis_stock_code,
)
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

TODAYS_FOCUS_PACK_VERSION = "todays_focus/2.1"
DEFAULT_MAX_FOCUS_ITEMS = 5
MAX_FOCUS_ITEMS_HARD_CAP = 10
MAX_UNIVERSE_SYMBOLS = 1000
ANALYSIS_LOOKBACK_DAYS = 90
DEFAULT_TIMEZONE_NAME = "Asia/Shanghai"
FOCUS_MARKETS: Tuple[str, ...] = ("cn", "hk", "us")
MAX_DETAIL_LENGTH = 160
MAX_NAME_LENGTH = 80
MAX_DATA_NOTES = 4
MAX_DATA_NOTE_LENGTH = 160

REASON_PRIORITY: Dict[str, int] = {
    "alert_triggered": 100,
    "corporate_event": 80,
    "analysis_reversal": 70,
}
REASON_CODES = frozenset(REASON_PRIORITY)
_EVIDENCE_TYPES = {
    "alert_triggered": "alert",
    "corporate_event": "corporate_event",
    "analysis_reversal": "analysis",
}
_DIRECTIONAL_ACTIONS = frozenset({"buy", "sell", "hold"})

_REASON_TEMPLATES_EN: Dict[str, str] = {
    "alert_triggered": "Alert triggered: {detail}",
    "corporate_event": "Corporate event: {detail}",
    "analysis_reversal": "Analysis conclusion changed: {detail}",
}
_REASON_TEMPLATES_ZH: Dict[str, str] = {
    "alert_triggered": "触发告警：{detail}",
    "corporate_event": "重大事件：{detail}",
    "analysis_reversal": "分析结论变化：{detail}",
}


@dataclass(frozen=True)
class MarketDayWindow:
    """One market's local-calendar-day freshness window for a build."""

    market: str
    timezone_name: str
    local_date: date
    window_start: datetime
    window_end: datetime
    is_trading_day: Optional[bool]

    def contains(self, observed_at: datetime) -> bool:
        return self.window_start <= observed_at <= self.window_end

    def to_dict(self) -> Dict[str, Any]:
        return {
            "market": self.market,
            "timezone": self.timezone_name,
            "local_date": self.local_date.isoformat(),
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "is_trading_day": self.is_trading_day,
        }


@dataclass(frozen=True)
class FocusTemporalPolicy:
    """Executable per-market calendar-day contract for one build."""

    fallback_timezone_name: str
    window_end: datetime
    markets: Mapping[str, MarketDayWindow]

    def window_for_code(self, code: str) -> MarketDayWindow:
        market = _resolve_focus_market(code)
        return self.markets.get(market) or self.markets["unknown"]

    def earliest_window_start(self) -> datetime:
        starts = [window.window_start for window in self.markets.values()]
        return min(starts) if starts else self.window_end

    def to_dict(self) -> Dict[str, Any]:
        ordered = sorted(
            self.markets.values(),
            key=lambda window: (
                0 if window.market in FOCUS_MARKETS else 1,
                FOCUS_MARKETS.index(window.market) if window.market in FOCUS_MARKETS else 99,
                window.market,
            ),
        )
        return {
            "semantics": "per_market_local_calendar_day",
            "cross_market_rule": "evidence_uses_target_symbol_market_timezone",
            "fallback_timezone": self.fallback_timezone_name,
            "window_end": self.window_end.isoformat(),
            "naive_timestamp_policy": "assume_utc",
            "missing_timestamp_policy": "exclude",
            "non_trading_day_policy": "same_local_day_only",
            "markets": [window.to_dict() for window in ordered],
        }


@dataclass(frozen=True)
class FocusEvidence:
    """One typed deterministic reason a symbol may enter Today's Focus."""

    code: str
    reason_code: str
    detail: str
    evidence: Mapping[str, Any]
    priority: int = 0
    name: Optional[str] = None
    weight_pct: Optional[float] = None

    def __post_init__(self) -> None:
        code = canonicalize_analysis_stock_code(str(self.code or "").strip())
        reason = str(self.reason_code or "").strip()
        if not code:
            raise ValueError("FocusEvidence.code must be a recognized market symbol")
        if reason not in REASON_CODES:
            raise ValueError(f"unsupported reason_code: {reason}")
        priority = int(self.priority) if self.priority else REASON_PRIORITY[reason]
        if not 0 <= priority <= 100:
            raise ValueError("FocusEvidence.priority must be between 0 and 100")
        weight = _finite_optional_float(self.weight_pct, field_name="FocusEvidence.weight_pct")
        if weight is not None and not 0 <= weight <= 100:
            raise ValueError("FocusEvidence.weight_pct must be finite and between 0 and 100")
        evidence = dict(self.evidence or {})
        _validate_evidence_shape(reason, evidence)
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "reason_code", reason)
        object.__setattr__(self, "priority", priority)
        object.__setattr__(self, "weight_pct", weight)
        object.__setattr__(self, "detail", _bounded_text(self.detail, MAX_DETAIL_LENGTH, fallback=reason))
        object.__setattr__(self, "name", _bounded_optional_text(self.name, MAX_NAME_LENGTH))
        object.__setattr__(self, "evidence", evidence)


@dataclass(frozen=True)
class FocusItem:
    """Selected focus row after aggregation and hard-cap truncation."""

    code: str
    reason_code: str
    reason_display: str
    priority: int
    evidence: Mapping[str, Any]
    name: Optional[str] = None
    weight_pct: Optional[float] = None
    secondary_reason_codes: Sequence[str] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name or self.code,
            "reason_code": self.reason_code,
            "reason_display": self.reason_display,
            "priority": self.priority,
            "weight_pct": self.weight_pct,
            "secondary_reason_codes": list(self.secondary_reason_codes),
            "evidence": dict(self.evidence),
        }


def format_reason_display(reason_code: str, detail: str, *, language: str = "en") -> str:
    """Format deterministic reason text without changing membership."""
    templates = _REASON_TEMPLATES_ZH if str(language or "").lower().startswith("zh") else _REASON_TEMPLATES_EN
    return (templates.get(reason_code) or "{detail}").format(detail=detail or reason_code)


def polish_reason_display_with_llm(
    selected_items: Sequence[FocusItem],
    *,
    llm_call: Optional[Callable[[str], str]] = None,
) -> List[FocusItem]:
    """Optional copy-only hook; selection identity and evidence are immutable."""
    if llm_call is None:
        return list(selected_items)
    polished: List[FocusItem] = []
    for item in selected_items:
        try:
            rewritten = _bounded_text(llm_call(item.reason_display), 240, fallback=item.reason_display)
        except Exception as exc:  # broad-exception: fallback_recorded - copy failure must not drop evidence
            log_safe_exception(
                logger,
                "Today's focus copy polish failed; keeping deterministic text",
                exc,
                error_code="todays_focus_copy_polish_failed",
                level=logging.WARNING,
            )
            rewritten = item.reason_display
        polished.append(
            FocusItem(
                code=item.code,
                reason_code=item.reason_code,
                reason_display=rewritten,
                priority=item.priority,
                evidence=item.evidence,
                name=item.name,
                weight_pct=item.weight_pct,
                secondary_reason_codes=item.secondary_reason_codes,
            )
        )
    return polished


def select_focus_items(
    evidences: Sequence[FocusEvidence],
    *,
    max_items: int = DEFAULT_MAX_FOCUS_ITEMS,
    language: str = "en",
    llm_call: Optional[Callable[[str], str]] = None,
) -> List[FocusItem]:
    """Aggregate typed evidence into a stable hard-capped list; never pad."""
    cap = _normalize_max_items(max_items)
    if not evidences or cap <= 0:
        return []
    by_code: Dict[str, List[FocusEvidence]] = {}
    for raw in evidences:
        if isinstance(raw, FocusEvidence):
            by_code.setdefault(raw.code, []).append(raw)

    candidates: List[FocusItem] = []
    for code, group in by_code.items():
        ordered = sorted(
            group,
            key=lambda item: (
                -item.priority,
                -_evidence_timestamp(item.evidence),
                item.reason_code,
                item.detail,
            ),
        )
        primary = ordered[0]
        secondary: List[str] = []
        seen = {primary.reason_code}
        for extra in ordered[1:]:
            if extra.reason_code not in seen:
                seen.add(extra.reason_code)
                secondary.append(extra.reason_code)
        candidates.append(
            FocusItem(
                code=code,
                reason_code=primary.reason_code,
                reason_display=format_reason_display(primary.reason_code, primary.detail, language=language),
                priority=primary.priority,
                evidence=primary.evidence,
                name=primary.name or next((item.name for item in ordered if item.name), None),
                weight_pct=primary.weight_pct,
                secondary_reason_codes=tuple(secondary),
            )
        )
    candidates.sort(
        key=lambda item: (
            -item.priority,
            -_evidence_timestamp(item.evidence),
            item.code,
        )
    )
    return polish_reason_display_with_llm(candidates[:cap], llm_call=llm_call)


class TodaysFocusService:
    """Assemble fresh evidence using bounded read-only repository contracts."""

    def __init__(
        self,
        *,
        config_provider: Optional[Callable[[], Any]] = None,
        alert_repository: Any = None,
        portfolio_repository: Any = None,
        signal_changes_batch_loader: Optional[Callable[..., Mapping[str, Sequence[Mapping[str, Any]]]]] = None,
        event_evidence_loader: Optional[Callable[[Sequence[str]], Sequence[FocusEvidence]]] = None,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self._config_provider = config_provider
        self._alert_repository = alert_repository
        self._portfolio_repository = portfolio_repository
        self._signal_changes_batch_loader = signal_changes_batch_loader
        self._event_evidence_loader = event_evidence_loader
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def build_focus(
        self,
        *,
        max_items: int = DEFAULT_MAX_FOCUS_ITEMS,
        language: Optional[str] = None,
        account_id: Optional[int] = None,
        llm_call: Optional[Callable[[str], str]] = None,
        evidences: Optional[Sequence[FocusEvidence]] = None,
        universe: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        """Build a strict-JSON-safe focus payload without provider calls or writes."""
        cap = _normalize_max_items(max_items)
        config = self._config()
        lang = language or str(getattr(config, "report_language", None) or "en")
        now = _aware_utc(self._clock())
        if now is None:
            raise ValueError("clock must return a valid datetime")
        temporal_policy = _resolve_temporal_policy(now, config)
        degraded_sources: List[str] = []
        source_calls = {
            "alert_repository_calls": 0,
            "portfolio_repository_calls": 0,
            "analysis_history_repository_calls": 0,
            "event_repository_calls": 0,
        }
        sources_used: List[str] = []
        universe_sources: List[str] = []
        universe_truncated = False
        data_notes: List[str] = []
        excluded_non_finite_positions = 0
        universe_count = 0

        if evidences is not None:
            fresh_evidences = [item for item in evidences if self._is_fresh_evidence(item, temporal_policy)]
            selected = select_focus_items(fresh_evidences, max_items=cap, language=lang, llm_call=llm_call)
            sources_used = sorted({str(item.evidence.get("type")) for item in fresh_evidences})
            universe_count = len({item.code for item in fresh_evidences})
            universe_sources.append("injected_evidences")
        else:
            positions: List[Mapping[str, Any]] = []
            if universe is None:
                source_calls["portfolio_repository_calls"] = 1
                positions, portfolio_failed, excluded_non_finite_positions, position_notes = (
                    self._load_cached_positions(account_id=account_id)
                )
                universe_sources.append("portfolio_position_cache")
                data_notes.extend(position_notes)
                if portfolio_failed:
                    degraded_sources.append("portfolio_position_cache")
            codes, universe_truncated = self._resolve_universe(
                config,
                positions=positions,
                universe=universe,
            )
            universe_count = len(codes)
            universe_sources.append("request" if universe is not None else "watchlist_config")
            collected: List[FocusEvidence] = []

            if codes:
                source_calls["alert_repository_calls"] = 1
                alert_items, alert_failed = self._collect_alert_evidence(codes, temporal_policy)
                if alert_failed:
                    degraded_sources.append("alerts")
                elif alert_items:
                    sources_used.append("alerts")
                    collected.extend(alert_items)

                if self._event_evidence_loader is not None:
                    source_calls["event_repository_calls"] = 1
                    event_items, event_failed = self._collect_event_evidence(codes, temporal_policy)
                    if event_failed:
                        degraded_sources.append("corporate_events")
                    elif event_items:
                        sources_used.append("corporate_events")
                        collected.extend(event_items)

                source_calls["analysis_history_repository_calls"] = 1
                reversal_items, history_failed = self._collect_reversal_evidence(codes, temporal_policy)
                if history_failed:
                    degraded_sources.append("analysis_history")
                elif reversal_items:
                    sources_used.append("analysis_history")
                    collected.extend(reversal_items)
            selected = select_focus_items(collected, max_items=cap, language=lang, llm_call=llm_call)

        degraded_sources = sorted(set(degraded_sources))
        status = "degraded" if degraded_sources else ("ok" if selected else "empty")
        empty_reason = None
        empty_message = None
        if not selected:
            if degraded_sources:
                empty_reason = "source_unavailable"
                empty_message = (
                    "One or more local sources were unavailable; focus is not reported as a normal empty list."
                )
            elif excluded_non_finite_positions > 0 and universe_count == 0:
                empty_reason = "insufficient_finite_data"
                empty_message = (
                    "Position amount/weight/change values were non-finite or missing; "
                    "no trustworthy focus conclusion is available."
                )
            else:
                empty_reason = "no_fresh_deterministic_signals"
                empty_message = (
                    "No fresh deterministic alert, event, or analysis-change evidence is available "
                    "for each symbol's market-local today."
                )
        return {
            "pack_version": TODAYS_FOCUS_PACK_VERSION,
            "generated_at": now.isoformat(),
            "status": status,
            "max_items": cap,
            "item_count": len(selected),
            "items": [item.to_dict() for item in selected],
            "empty_reason": empty_reason,
            "empty_message": empty_message,
            "sources_used": sorted(set(sources_used)),
            "degraded_sources": degraded_sources,
            "temporal_policy": temporal_policy.to_dict(),
            "universe_contract": {
                "symbol_count": universe_count,
                "hard_cap": MAX_UNIVERSE_SYMBOLS,
                "truncated": universe_truncated,
                "sources": sorted(set(universe_sources)),
                "excluded_non_finite_positions": excluded_non_finite_positions,
                "data_notes": data_notes[:MAX_DATA_NOTES],
            },
            "cost_contract": {
                **source_calls,
                "database_writes": 0,
                "provider_calls": 0,
                "analysis_runs_triggered": 0,
                "zero_extra_fetch": True,
                "read_only": True,
            },
            "presentation_boundary": {
                "alerts_owned_by": "signal_center",
                "focus_shows": "prioritized_symbols_with_evidence_links",
                "duplicate_alert_ui": False,
            },
        }

    def _config(self) -> Any:
        if self._config_provider is not None:
            return self._config_provider()
        try:
            from src.application_services import get_application_services

            return get_application_services().config
        except Exception as exc:  # broad-exception: fallback_recorded - configuration is optional
            log_safe_exception(
                logger,
                "Today's focus configuration load failed",
                exc,
                error_code="todays_focus_config_failed",
                level=logging.WARNING,
            )
            return None

    def _resolve_universe(
        self,
        config: Any,
        *,
        positions: Sequence[Mapping[str, Any]],
        universe: Optional[Sequence[str]],
    ) -> tuple[Set[str], bool]:
        raw_codes: List[Any] = []
        if universe is not None:
            raw_codes.extend(universe)
        else:
            raw = getattr(config, "stock_list", None) or [] if config is not None else []
            if isinstance(raw, str):
                try:
                    from src.utils.stock_list import split_stock_list

                    raw = split_stock_list(raw)
                except Exception as exc:  # broad-exception: fallback_recorded - malformed watchlist is isolated
                    log_safe_exception(
                        logger,
                        "Today's focus watchlist parse failed",
                        exc,
                        error_code="todays_focus_watchlist_parse_failed",
                        level=logging.DEBUG,
                    )
                    raw = []
            raw_codes.extend(raw)
            raw_codes.extend(position.get("symbol") for position in positions)

        ordered: List[str] = []
        seen: Set[str] = set()
        for raw in raw_codes:
            canonical = canonicalize_analysis_stock_code(str(raw or "").strip())
            if not canonical or canonical in seen:
                continue
            seen.add(canonical)
            ordered.append(canonical)
        truncated = len(ordered) > MAX_UNIVERSE_SYMBOLS
        return set(ordered[:MAX_UNIVERSE_SYMBOLS]), truncated

    def _load_cached_positions(
        self,
        *,
        account_id: Optional[int],
    ) -> tuple[List[Mapping[str, Any]], bool, int, List[str]]:
        """Load the full cached-position set (no first-page truncation)."""
        repository = self._portfolio_repository
        if repository is None:
            try:
                from src.repositories.portfolio_repo import PortfolioRepository

                repository = PortfolioRepository()
            except Exception as exc:  # broad-exception: fallback_recorded - portfolio is optional
                log_safe_exception(
                    logger,
                    "Today's focus portfolio repository unavailable",
                    exc,
                    error_code="todays_focus_portfolio_unavailable",
                    level=logging.WARNING,
                )
                return [], True, 0, []
        try:
            # Full-set contract: no page/offset truncation.
            rows = repository.list_cached_positions(account_id=account_id, cost_method="fifo")
        except Exception as exc:  # broad-exception: fallback_recorded - surface degraded source
            log_safe_exception(
                logger,
                "Today's focus cached position read failed",
                exc,
                error_code="todays_focus_portfolio_read_failed",
                level=logging.WARNING,
            )
            return [], True, 0, []

        accepted: List[Mapping[str, Any]] = []
        excluded = 0
        for row in rows or []:
            if not isinstance(row, Mapping):
                excluded += 1
                continue
            if not _position_financials_are_finite(row):
                excluded += 1
                continue
            accepted.append(row)

        notes: List[str] = []
        if excluded:
            notes.append(
                _bounded_text(
                    (
                        f"Excluded {excluded} cached position row(s) with non-finite "
                        "amount, weight, or change values; zeros were not substituted."
                    ),
                    MAX_DATA_NOTE_LENGTH,
                    fallback="excluded non-finite positions",
                )
            )
        return accepted, False, excluded, notes

    def _collect_alert_evidence(
        self,
        universe: Set[str],
        policy: FocusTemporalPolicy,
    ) -> tuple[List[FocusEvidence], bool]:
        repository = self._alert_repository
        if repository is None:
            try:
                from src.repositories.alert_repo import AlertRepository

                repository = AlertRepository()
            except Exception as exc:  # broad-exception: fallback_recorded - alerts are optional
                log_safe_exception(
                    logger,
                    "Today's focus alert repository unavailable",
                    exc,
                    error_code="todays_focus_alerts_unavailable",
                    level=logging.WARNING,
                )
                return [], True
        target_aliases = sorted({
            alias
            for code in universe
            for alias in build_daily_code_candidates(code)
        })
        try:
            # Full-coverage contract: never use list_triggers(page=1).
            rows = repository.list_recent_triggered_for_targets(
                targets=target_aliases,
                triggered_since=policy.earliest_window_start(),
                per_target_limit=1,
            )
        except Exception as exc:  # broad-exception: fallback_recorded - surface degraded source
            log_safe_exception(
                logger,
                "Today's focus alert read failed",
                exc,
                error_code="todays_focus_alerts_read_failed",
                level=logging.WARNING,
            )
            return [], True

        output: List[FocusEvidence] = []
        for row in rows or []:
            status = str(_row_value(row, "status") or "").strip().lower()
            target = canonicalize_analysis_stock_code(str(_row_value(row, "target") or ""))
            observed_at = _aware_utc(_row_value(row, "triggered_at"))
            trigger_id = _positive_int(_row_value(row, "id"))
            if (
                status != "triggered"
                or target not in universe
                or observed_at is None
                or trigger_id is None
                or not _within_policy(observed_at, policy, code=target)
            ):
                continue
            if not _alert_row_financials_are_finite(row):
                continue
            rule_id = _positive_int(_row_value(row, "rule_id"))
            evidence: Dict[str, Any] = {
                "type": "alert",
                "trigger_id": trigger_id,
                "rule_id": rule_id,
                "observed_at": observed_at.isoformat(),
                "status": "triggered",
            }
            source = _bounded_optional_text(_row_value(row, "data_source"), 64)
            if source:
                evidence["source"] = source
            output.append(
                FocusEvidence(
                    code=target,
                    reason_code="alert_triggered",
                    detail=_bounded_text(_row_value(row, "reason"), MAX_DETAIL_LENGTH, fallback="triggered"),
                    evidence=evidence,
                )
            )
        return output, False

    def _collect_event_evidence(
        self,
        universe: Set[str],
        policy: FocusTemporalPolicy,
    ) -> tuple[List[FocusEvidence], bool]:
        if self._event_evidence_loader is None:
            return [], False
        try:
            rows = self._event_evidence_loader(sorted(universe))
        except Exception as exc:  # broad-exception: fallback_recorded - surface degraded source
            log_safe_exception(
                logger,
                "Today's focus event evidence read failed",
                exc,
                error_code="todays_focus_events_read_failed",
                level=logging.WARNING,
            )
            return [], True
        return [
            row
            for row in (rows or [])
            if isinstance(row, FocusEvidence)
            and row.reason_code == "corporate_event"
            and row.code in universe
            and self._is_fresh_evidence(row, policy)
        ], False

    def _collect_reversal_evidence(
        self,
        universe: Set[str],
        policy: FocusTemporalPolicy,
    ) -> tuple[List[FocusEvidence], bool]:
        loader = self._signal_changes_batch_loader
        if loader is None:
            try:
                from src.services.history_comparison_service import get_signal_changes_batch

                loader = get_signal_changes_batch
            except Exception as exc:  # broad-exception: fallback_recorded - history is optional
                log_safe_exception(
                    logger,
                    "Today's focus analysis history unavailable",
                    exc,
                    error_code="todays_focus_history_unavailable",
                    level=logging.WARNING,
                )
                return [], True
        try:
            history_by_code = loader(
                sorted(universe),
                limit=2,
                created_at_from=policy.earliest_window_start() - timedelta(days=ANALYSIS_LOOKBACK_DAYS),
            )
        except Exception as exc:  # broad-exception: fallback_recorded - one batch call, no retry
            log_safe_exception(
                logger,
                "Today's focus analysis history read failed",
                exc,
                error_code="todays_focus_history_read_failed",
                level=logging.WARNING,
            )
            return [], True
        if not isinstance(history_by_code, Mapping):
            return [], True

        output: List[FocusEvidence] = []
        for code in sorted(universe):
            rows = history_by_code.get(code)
            if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)) or len(rows) < 2:
                continue
            latest = rows[0] if isinstance(rows[0], Mapping) else {}
            previous = rows[1] if isinstance(rows[1], Mapping) else {}
            latest_action = _normalize_action(latest)
            previous_action = _normalize_action(previous)
            latest_observed = _aware_utc(latest.get("created_at"))
            previous_observed = _aware_utc(previous.get("created_at"))
            record_id = _positive_int(latest.get("record_id"))
            if (
                latest_observed is None
                or previous_observed is None
                or record_id is None
                or not _within_policy(latest_observed, policy, code=code)
                or not _is_directional_flip(previous_action, latest_action)
            ):
                continue
            evidence = {
                "type": "analysis",
                "record_id": record_id,
                "query_id": _bounded_optional_text(latest.get("query_id"), 128),
                "observed_at": latest_observed.isoformat(),
                "previous_observed_at": previous_observed.isoformat(),
                "previous_action": previous_action,
                "latest_action": latest_action,
            }
            output.append(
                FocusEvidence(
                    code=code,
                    reason_code="analysis_reversal",
                    detail=f"{previous_action} → {latest_action}",
                    evidence=evidence,
                )
            )
        return output, False

    @staticmethod
    def _is_fresh_evidence(item: FocusEvidence, policy: FocusTemporalPolicy) -> bool:
        if not isinstance(item, FocusEvidence):
            return False
        observed_at = _aware_utc(item.evidence.get("observed_at"))
        return observed_at is not None and _within_policy(observed_at, policy, code=item.code)


def _normalize_max_items(max_items: int) -> int:
    try:
        value = int(max_items)
    except (TypeError, ValueError):
        value = DEFAULT_MAX_FOCUS_ITEMS
    if value < 0:
        return 0
    return min(value, MAX_FOCUS_ITEMS_HARD_CAP)


def _resolve_focus_market(code: str) -> str:
    """Map a symbol to a focus market key (cn/hk/us or unknown)."""
    market = str(detect_market(code) or "").strip().lower()
    if market in FOCUS_MARKETS:
        return market
    if market in MARKET_TIMEZONE:
        return market
    return "unknown"


def _resolve_timezone_name(name: str, *, fallback: str = DEFAULT_TIMEZONE_NAME) -> tuple[str, ZoneInfo]:
    cleaned = str(name or "").strip() or fallback
    try:
        return cleaned, ZoneInfo(cleaned)
    except (ZoneInfoNotFoundError, ValueError):
        return fallback, ZoneInfo(fallback)


def _build_market_day_window(
    *,
    market: str,
    timezone_name: str,
    now_utc: datetime,
) -> MarketDayWindow:
    resolved_name, local_zone = _resolve_timezone_name(timezone_name)
    local_now = now_utc.astimezone(local_zone)
    local_date = local_now.date()
    local_start = datetime.combine(local_date, time.min, tzinfo=local_zone)
    is_trading_day: Optional[bool] = None
    if market in FOCUS_MARKETS or market in MARKET_TIMEZONE:
        session = classify_market_session(market, local_date)
        if session == MarketSessionStatus.OPEN:
            is_trading_day = True
        elif session == MarketSessionStatus.CLOSED:
            is_trading_day = False
    return MarketDayWindow(
        market=market,
        timezone_name=resolved_name,
        local_date=local_date,
        window_start=local_start.astimezone(timezone.utc),
        window_end=now_utc,
        is_trading_day=is_trading_day,
    )


def _resolve_temporal_policy(now_utc: datetime, config: Any) -> FocusTemporalPolicy:
    fallback_name = str(
        getattr(config, "daily_brief_timezone", None)
        or getattr(config, "notification_timezone", None)
        or DEFAULT_TIMEZONE_NAME
    ).strip() or DEFAULT_TIMEZONE_NAME
    fallback_name, _ = _resolve_timezone_name(fallback_name)

    markets: Dict[str, MarketDayWindow] = {}
    for market in FOCUS_MARKETS:
        markets[market] = _build_market_day_window(
            market=market,
            timezone_name=MARKET_TIMEZONE[market],
            now_utc=now_utc,
        )
    markets["unknown"] = _build_market_day_window(
        market="unknown",
        timezone_name=fallback_name,
        now_utc=now_utc,
    )
    return FocusTemporalPolicy(
        fallback_timezone_name=fallback_name,
        window_end=now_utc,
        markets=markets,
    )


def _within_policy(
    observed_at: datetime,
    policy: FocusTemporalPolicy,
    *,
    code: str,
) -> bool:
    return policy.window_for_code(code).contains(observed_at)


def _aware_utc(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text_value = value.strip()
        if not text_value:
            return None
        try:
            parsed = datetime.fromisoformat(text_value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _validate_evidence_shape(reason_code: str, evidence: Mapping[str, Any]) -> None:
    if evidence.get("type") != _EVIDENCE_TYPES[reason_code]:
        raise ValueError("evidence type does not match reason_code")
    if _aware_utc(evidence.get("observed_at")) is None:
        raise ValueError("evidence.observed_at must be a valid datetime")
    if reason_code == "alert_triggered":
        if _positive_int(evidence.get("trigger_id")) is None or evidence.get("status") != "triggered":
            raise ValueError("alert evidence requires a positive trigger_id and triggered status")
    elif reason_code == "analysis_reversal":
        if _positive_int(evidence.get("record_id")) is None:
            raise ValueError("analysis evidence requires a positive record_id")
        previous_action = evidence.get("previous_action")
        latest_action = evidence.get("latest_action")
        if previous_action not in _DIRECTIONAL_ACTIONS:
            raise ValueError("analysis evidence previous_action is invalid")
        if latest_action not in _DIRECTIONAL_ACTIONS:
            raise ValueError("analysis evidence latest_action is invalid")
        if previous_action == latest_action:
            raise ValueError("analysis evidence actions must differ")
        previous_observed = _aware_utc(evidence.get("previous_observed_at"))
        observed = _aware_utc(evidence.get("observed_at"))
        if previous_observed is None:
            raise ValueError("analysis evidence requires previous_observed_at")
        if observed is not None and previous_observed > observed:
            raise ValueError("analysis evidence previous timestamp cannot be newer")
    elif reason_code == "corporate_event":
        event_id = _bounded_optional_text(evidence.get("event_id"), 128)
        href = _bounded_optional_text(evidence.get("href"), 512)
        if not event_id or not href or not href.startswith("/") or href.startswith("//"):
            raise ValueError("corporate event evidence requires a safe event_id and relative href")


def _normalize_action(row: Mapping[str, Any]) -> str:
    value = str(row.get("action") or "").strip().lower()
    return value if value in _DIRECTIONAL_ACTIONS else ""


def _is_directional_flip(previous: str, latest: str) -> bool:
    return previous in _DIRECTIONAL_ACTIONS and latest in _DIRECTIONAL_ACTIONS and previous != latest


def _evidence_timestamp(evidence: Mapping[str, Any]) -> float:
    observed_at = _aware_utc(evidence.get("observed_at"))
    return observed_at.timestamp() if observed_at is not None else 0.0


def _positive_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if parsed > 0 else None


def _row_value(row: Any, key: str) -> Any:
    if isinstance(row, Mapping):
        return row.get(key)
    return getattr(row, key, None)


def _bounded_text(value: Any, limit: int, *, fallback: str) -> str:
    text_value = str(value or "").strip()
    return (text_value or fallback)[:limit]


def _bounded_optional_text(value: Any, limit: int) -> Optional[str]:
    if value is None:
        return None
    text_value = str(value).strip()
    return text_value[:limit] if text_value else None


def _finite_optional_float(value: Any, *, field_name: str) -> Optional[float]:
    """Parse optional financial numbers; reject non-finite values explicitly."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be finite")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field_name} must be finite") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be finite")
    return number


def _is_present_non_finite(value: Any) -> bool:
    """True when a value is provided but cannot be treated as a finite number."""
    if value is None:
        return False
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        return not math.isfinite(float(value))
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return False
        try:
            return not math.isfinite(float(text))
        except (TypeError, ValueError, OverflowError):
            return True
    try:
        return not math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return True


_POSITION_FINANCIAL_FIELDS = (
    "quantity",
    "market_value_base",
    "market_value",
    "last_price",
    "weight_pct",
    "weight",
    "unrealized_pnl",
    "unrealized_pnl_pct",
    "change_pct",
    "day_change_pct",
    "pct_change",
)

_ALERT_FINANCIAL_FIELDS = (
    "price",
    "threshold",
    "change_pct",
    "day_change_pct",
    "pct_change",
    "value",
    "market_value",
    "weight_pct",
)


def _position_financials_are_finite(row: Mapping[str, Any]) -> bool:
    for field_name in _POSITION_FINANCIAL_FIELDS:
        if field_name in row and _is_present_non_finite(row.get(field_name)):
            return False
    quantity = row.get("quantity")
    if quantity is not None:
        try:
            qty = float(quantity)
        except (TypeError, ValueError, OverflowError):
            return False
        if not math.isfinite(qty) or qty <= 0:
            return False
    return True


def _alert_row_financials_are_finite(row: Any) -> bool:
    for field_name in _ALERT_FINANCIAL_FIELDS:
        value = _row_value(row, field_name)
        if value is not None and _is_present_non_finite(value):
            return False
    return True
