# -*- coding: utf-8 -*-
"""Today's Focus: deterministic prioritization of watchlist + holdings (Issue #157 / T26).

Design decisions (recorded for the PR):

* **Independent module, not a daily-brief section.** Daily brief is a gated
  notification product centered on yesterday's analyses and accuracy review.
  Today's Focus is an on-demand home prioritization surface that must refresh
  without waiting for the brief schedule. Selection rules live here so brief
  (or other consumers) can later call ``select_focus_items`` without
  duplicating logic — Integration Point only; this module does not modify
  ``daily_brief_service.py``.
* **Deterministic selection only.** LLM (if ever used) may only rephrase
  ``reason_display``; it must never change the selected code set. V0 ships
  pure template reasons with no LLM calls.
* **Zero extra cost.** Aggregation reads existing stores/services only
  (alerts, portfolio snapshot without realtime, analysis history signals).
  No market-data providers, no analysis runs, no crawlers.

Focus sources (priority high → low):

1. ``alert_triggered`` — recent alert triggers for universe symbols
2. ``corporate_event`` — optional injectable event evidence (T21/calendar)
3. ``analysis_reversal`` — latest vs previous analysis action flip
4. ``high_weight_move`` — high portfolio weight + large unrealized move

Empty focus is honest: never pad to fill the hard cap.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Set

from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

TODAYS_FOCUS_PACK_VERSION = "todays_focus/1.0"
DEFAULT_MAX_FOCUS_ITEMS = 5
MAX_FOCUS_ITEMS_HARD_CAP = 10
DEFAULT_ALERT_LOOKBACK_ITEMS = 50
DEFAULT_WEIGHT_THRESHOLD_PCT = 10.0
DEFAULT_MOVE_THRESHOLD_PCT = 3.0

REASON_PRIORITY: Dict[str, int] = {
    "alert_triggered": 100,
    "corporate_event": 80,
    "analysis_reversal": 70,
    "high_weight_move": 50,
}
REASON_CODES = frozenset(REASON_PRIORITY.keys())

_REASON_TEMPLATES_EN: Dict[str, str] = {
    "alert_triggered": "Alert triggered: {detail}",
    "corporate_event": "Corporate event: {detail}",
    "analysis_reversal": "Analysis conclusion reversed: {detail}",
    "high_weight_move": "High portfolio weight with large move: {detail}",
}
_REASON_TEMPLATES_ZH: Dict[str, str] = {
    "alert_triggered": "触发告警：{detail}",
    "corporate_event": "重大事件：{detail}",
    "analysis_reversal": "分析结论反转：{detail}",
    "high_weight_move": "高权重且波动较大：{detail}",
}


@dataclass(frozen=True)
class FocusEvidence:
    """One deterministic reason a symbol may enter today's focus."""

    code: str
    reason_code: str
    detail: str
    priority: int = 0
    name: Optional[str] = None
    weight_pct: Optional[float] = None
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        code = str(self.code or "").strip().upper()
        reason = str(self.reason_code or "").strip()
        if not code:
            raise ValueError("FocusEvidence.code is required")
        if reason not in REASON_CODES:
            raise ValueError(f"unsupported reason_code: {reason}")
        priority = int(self.priority) if self.priority else REASON_PRIORITY[reason]
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "reason_code", reason)
        object.__setattr__(self, "priority", priority)
        object.__setattr__(self, "detail", str(self.detail or "").strip() or reason)


@dataclass(frozen=True)
class FocusItem:
    """Selected focus row after aggregation and hard-cap truncation."""

    code: str
    reason_code: str
    reason_display: str
    priority: int
    name: Optional[str] = None
    weight_pct: Optional[float] = None
    secondary_reason_codes: Sequence[str] = field(default_factory=tuple)
    evidence: Mapping[str, Any] = field(default_factory=dict)

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
    """Template-only reason text. Never changes selection membership."""
    templates = _REASON_TEMPLATES_ZH if str(language or "").lower().startswith("zh") else _REASON_TEMPLATES_EN
    return (templates.get(reason_code) or "{detail}").format(detail=detail or reason_code)


def polish_reason_display_with_llm(
    selected_items: Sequence[FocusItem],
    *,
    llm_call: Optional[Callable[[str], str]] = None,
) -> List[FocusItem]:
    """Optional reason polish hook; cannot change selection membership."""
    if llm_call is None:
        return list(selected_items)
    polished: List[FocusItem] = []
    for item in selected_items:
        try:
            rewritten = str(llm_call(item.reason_display) or "").strip()
        except Exception as exc:  # broad-exception: fallback_recorded - polish must not drop selection
            log_safe_exception(
                logger,
                "Today's focus LLM polish failed; keeping template reason",
                exc,
                error_code="todays_focus_llm_polish_failed",
                level=logging.WARNING,
            )
            polished.append(item)
            continue
        if not rewritten:
            polished.append(item)
            continue
        polished.append(
            FocusItem(
                code=item.code,
                reason_code=item.reason_code,
                reason_display=rewritten,
                priority=item.priority,
                name=item.name,
                weight_pct=item.weight_pct,
                secondary_reason_codes=item.secondary_reason_codes,
                evidence=item.evidence,
            )
        )
    if [i.code for i in polished] != [i.code for i in selected_items]:
        logger.error("Today's focus LLM polish attempted to change selection; ignoring polish")
        return list(selected_items)
    return polished


def select_focus_items(
    evidences: Sequence[FocusEvidence],
    *,
    max_items: int = DEFAULT_MAX_FOCUS_ITEMS,
    language: str = "en",
    llm_call: Optional[Callable[[str], str]] = None,
) -> List[FocusItem]:
    """Aggregate evidence into a hard-capped focus list. Never pads."""
    cap = _normalize_max_items(max_items)
    if not evidences or cap <= 0:
        return []

    by_code: Dict[str, List[FocusEvidence]] = {}
    for raw in evidences:
        if isinstance(raw, FocusEvidence):
            by_code.setdefault(raw.code, []).append(raw)

    candidates: List[FocusItem] = []
    for code, group in by_code.items():
        ordered = sorted(group, key=lambda e: (-e.priority, e.reason_code, e.detail, e.code))
        primary = ordered[0]
        secondary = []
        seen = {primary.reason_code}
        for extra in ordered[1:]:
            if extra.reason_code not in seen:
                seen.add(extra.reason_code)
                secondary.append(extra.reason_code)
        weight = primary.weight_pct
        if weight is None:
            for item in ordered:
                if item.weight_pct is not None:
                    weight = item.weight_pct
                    break
        name = primary.name
        if not name:
            for item in ordered:
                if item.name:
                    name = item.name
                    break
        candidates.append(
            FocusItem(
                code=code,
                reason_code=primary.reason_code,
                reason_display=format_reason_display(primary.reason_code, primary.detail, language=language),
                priority=primary.priority,
                name=name,
                weight_pct=weight,
                secondary_reason_codes=tuple(secondary),
                evidence=dict(primary.evidence),
            )
        )

    candidates.sort(
        key=lambda item: (-item.priority, -(item.weight_pct if item.weight_pct is not None else -1.0), item.code)
    )
    return polish_reason_display_with_llm(candidates[:cap], llm_call=llm_call)


def _normalize_max_items(max_items: int) -> int:
    try:
        value = int(max_items)
    except (TypeError, ValueError):
        value = DEFAULT_MAX_FOCUS_ITEMS
    if value < 0:
        return 0
    return min(value, MAX_FOCUS_ITEMS_HARD_CAP)


class TodaysFocusService:
    """Assemble today's focus from existing managed data only."""

    def __init__(
        self,
        *,
        config_provider: Optional[Callable[[], Any]] = None,
        alert_service: Any = None,
        portfolio_service: Any = None,
        signal_changes_loader: Optional[Callable[[str, int], Sequence[Mapping[str, Any]]]] = None,
        event_evidence_loader: Optional[Callable[[Sequence[str]], Sequence[FocusEvidence]]] = None,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self._config_provider = config_provider
        self._alert_service = alert_service
        self._portfolio_service = portfolio_service
        self._signal_changes_loader = signal_changes_loader
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
        """Build the focus payload. Never triggers analysis or provider fetches."""
        cap = _normalize_max_items(max_items)
        config = self._config()
        lang = language or str(getattr(config, "report_language", None) or "en")
        now = self._clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        sources_used: List[str] = []
        provider_calls = 0
        analysis_runs_triggered = 0

        if evidences is not None:
            selected = select_focus_items(evidences, max_items=cap, language=lang, llm_call=llm_call)
            sources_used.append("injected_evidences")
        else:
            codes = self._resolve_universe(config, account_id=account_id, universe=universe)
            collected: List[FocusEvidence] = []
            alert_items = self._collect_alert_evidence(codes)
            if alert_items:
                sources_used.append("alerts")
                collected.extend(alert_items)
            event_items = self._collect_event_evidence(codes)
            if event_items:
                sources_used.append("corporate_events")
                collected.extend(event_items)
            reversal_items = self._collect_reversal_evidence(codes)
            if reversal_items:
                sources_used.append("analysis_history")
                collected.extend(reversal_items)
            weight_items = self._collect_high_weight_evidence(account_id=account_id)
            if weight_items:
                sources_used.append("portfolio_snapshot")
                collected.extend(weight_items)
            selected = select_focus_items(collected, max_items=cap, language=lang, llm_call=llm_call)

        return {
            "pack_version": TODAYS_FOCUS_PACK_VERSION,
            "generated_at": now.isoformat(),
            "status": "ok" if selected else "empty",
            "max_items": cap,
            "item_count": len(selected),
            "items": [item.to_dict() for item in selected],
            "empty_reason": None if selected else "no_deterministic_signals",
            "empty_message": None if selected else (
                "No symbols need special attention today based on alerts, events, reversals, or high-weight moves."
            ),
            "sources_used": sources_used,
            "cost_contract": {
                "provider_calls": provider_calls,
                "analysis_runs_triggered": analysis_runs_triggered,
                "zero_extra_fetch": provider_calls == 0 and analysis_runs_triggered == 0,
            },
            "presentation_boundary": {
                "alerts_owned_by": "notifications_or_alerts_hub",
                "focus_shows": "prioritized_symbols_with_why_selected",
                "duplicate_alert_ui": False,
            },
        }

    def _config(self) -> Any:
        if self._config_provider is not None:
            return self._config_provider()
        try:
            from src.application_services import get_application_services
            return get_application_services().config
        except Exception as exc:  # broad-exception: fallback_recorded - isolate config access
            log_safe_exception(logger, "Today's focus config load failed", exc, error_code="todays_focus_config_failed", level=logging.WARNING)
            return None

    def _resolve_universe(self, config: Any, *, account_id: Optional[int], universe: Optional[Sequence[str]]) -> Set[str]:
        if universe is not None:
            return {str(c).strip().upper() for c in universe if str(c).strip()}
        codes: Set[str] = set()
        raw = getattr(config, "stock_list", None) or [] if config is not None else []
        if isinstance(raw, str):
            try:
                from src.utils.stock_list import split_stock_list
                raw = split_stock_list(raw)
            except Exception as exc:  # broad-exception: fallback_recorded - isolate parse failure
                log_safe_exception(logger, "Today's focus watchlist parse failed", exc, error_code="todays_focus_watchlist_parse_failed", level=logging.DEBUG)
                raw = []
        for item in raw:
            code = str(item or "").strip().upper()
            if code:
                codes.add(code)
        for pos in self._portfolio_positions(account_id=account_id):
            symbol = str(pos.get("symbol") or "").strip().upper()
            if symbol:
                codes.add(symbol)
        return codes

    def _portfolio_positions(self, *, account_id: Optional[int]) -> List[Mapping[str, Any]]:
        service = self._portfolio_service
        if service is None:
            try:
                from src.services.portfolio_service import PortfolioService
                service = PortfolioService()
            except Exception as exc:  # broad-exception: fallback_recorded - portfolio optional
                log_safe_exception(logger, "Today's focus portfolio service unavailable", exc, error_code="todays_focus_portfolio_unavailable", level=logging.DEBUG)
                return []
        try:
            snapshot = service.get_portfolio_snapshot(account_id=account_id, include_realtime=False)
        except Exception as exc:  # broad-exception: fallback_recorded - empty positions on failure
            log_safe_exception(logger, "Today's focus portfolio snapshot failed", exc, error_code="todays_focus_portfolio_snapshot_failed", level=logging.WARNING)
            return []
        positions: List[Mapping[str, Any]] = []
        if isinstance(snapshot, Mapping):
            for account in snapshot.get("accounts") or []:
                if isinstance(account, Mapping):
                    for pos in account.get("positions") or []:
                        if isinstance(pos, Mapping):
                            positions.append(pos)
            for pos in snapshot.get("positions") or []:
                if isinstance(pos, Mapping):
                    positions.append(pos)
        return positions

    def _collect_alert_evidence(self, universe: Set[str]) -> List[FocusEvidence]:
        if not universe:
            return []
        service = self._alert_service
        if service is None:
            try:
                from src.services.alert_service import AlertService
                service = AlertService()
            except Exception as exc:  # broad-exception: fallback_recorded - alerts optional
                log_safe_exception(logger, "Today's focus alert service unavailable", exc, error_code="todays_focus_alerts_unavailable", level=logging.DEBUG)
                return []
        try:
            payload = service.list_triggers(page=1, page_size=DEFAULT_ALERT_LOOKBACK_ITEMS)
        except Exception as exc:  # broad-exception: fallback_recorded - isolate alert read
            log_safe_exception(logger, "Today's focus alert list failed", exc, error_code="todays_focus_alerts_list_failed", level=logging.WARNING)
            return []
        items = payload.get("items") if isinstance(payload, Mapping) else None
        if not isinstance(items, list):
            return []
        out: List[FocusEvidence] = []
        for row in items:
            if not isinstance(row, Mapping):
                continue
            target = str(row.get("target") or "").strip().upper()
            if not target or target not in universe:
                continue
            reason = str(row.get("reason") or row.get("status") or "triggered").strip()
            out.append(FocusEvidence(
                code=target,
                reason_code="alert_triggered",
                detail=reason[:160],
                evidence={"trigger_id": row.get("id"), "rule_id": row.get("rule_id"), "triggered_at": row.get("triggered_at"), "status": row.get("status")},
            ))
        return out

    def _collect_event_evidence(self, universe: Set[str]) -> List[FocusEvidence]:
        if not universe or self._event_evidence_loader is None:
            return []
        try:
            rows = self._event_evidence_loader(sorted(universe))
        except Exception as exc:  # broad-exception: fallback_recorded - events optional
            log_safe_exception(logger, "Today's focus event evidence load failed", exc, error_code="todays_focus_events_failed", level=logging.WARNING)
            return []
        return [row for row in (rows or []) if isinstance(row, FocusEvidence) and row.code in universe]

    def _collect_reversal_evidence(self, universe: Set[str]) -> List[FocusEvidence]:
        if not universe:
            return []
        loader = self._signal_changes_loader
        if loader is None:
            try:
                from src.services.history_comparison_service import get_signal_changes

                def _default_loader(code: str, limit: int = 2) -> Sequence[Mapping[str, Any]]:
                    return get_signal_changes(code, limit=limit)

                loader = _default_loader
            except Exception as exc:  # broad-exception: fallback_recorded - history optional
                log_safe_exception(logger, "Today's focus signal history unavailable", exc, error_code="todays_focus_history_unavailable", level=logging.DEBUG)
                return []
        out: List[FocusEvidence] = []
        for code in sorted(universe):
            try:
                rows = list(loader(code, 2) or [])
            except TypeError:
                try:
                    rows = list(loader(code) or [])  # type: ignore[call-arg, misc]
                except Exception as exc:  # broad-exception: fallback_recorded - per-symbol isolation
                    log_safe_exception(logger, "Today's focus signal load failed", exc, error_code="todays_focus_signal_load_failed", level=logging.DEBUG, context={"code": code})
                    continue
            except Exception as exc:  # broad-exception: fallback_recorded - per-symbol isolation
                log_safe_exception(logger, "Today's focus signal load failed", exc, error_code="todays_focus_signal_load_failed", level=logging.DEBUG, context={"code": code})
                continue
            if len(rows) < 2:
                continue
            latest = rows[0] if isinstance(rows[0], Mapping) else {}
            previous = rows[1] if isinstance(rows[1], Mapping) else {}
            latest_action = _normalize_action(latest)
            previous_action = _normalize_action(previous)
            if not latest_action or not previous_action or latest_action == previous_action:
                continue
            if not _is_directional_flip(previous_action, latest_action):
                continue
            out.append(FocusEvidence(
                code=code,
                reason_code="analysis_reversal",
                detail=f"{previous_action} → {latest_action}",
                evidence={
                    "previous_action": previous_action,
                    "latest_action": latest_action,
                    "latest_query_id": latest.get("query_id"),
                    "previous_query_id": previous.get("query_id"),
                },
            ))
        return out

    def _collect_high_weight_evidence(self, *, account_id: Optional[int]) -> List[FocusEvidence]:
        positions = self._portfolio_positions(account_id=account_id)
        if not positions:
            return []
        total_mv = 0.0
        cleaned: List[Dict[str, Any]] = []
        for pos in positions:
            symbol = str(pos.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            try:
                mv = float(pos.get("market_value_base") or 0.0)
            except (TypeError, ValueError):
                mv = 0.0
            if mv <= 0:
                continue
            try:
                move = pos.get("unrealized_pnl_pct")
                move_pct = float(move) if move is not None else None
            except (TypeError, ValueError):
                move_pct = None
            cleaned.append({"symbol": symbol, "market_value_base": mv, "unrealized_pnl_pct": move_pct, "name": pos.get("name") or pos.get("stock_name")})
            total_mv += mv
        if total_mv <= 0:
            return []
        out: List[FocusEvidence] = []
        for pos in cleaned:
            weight_pct = (float(pos["market_value_base"]) / total_mv) * 100.0
            move_pct = pos.get("unrealized_pnl_pct")
            if weight_pct < DEFAULT_WEIGHT_THRESHOLD_PCT:
                continue
            if move_pct is None or abs(float(move_pct)) < DEFAULT_MOVE_THRESHOLD_PCT:
                continue
            move_val = float(move_pct)
            out.append(FocusEvidence(
                code=pos["symbol"],
                name=str(pos["name"]) if pos.get("name") else None,
                reason_code="high_weight_move",
                detail=f"weight {weight_pct:.1f}%, unrealized {move_val:+.1f}%",
                weight_pct=round(weight_pct, 4),
                evidence={
                    "weight_pct": round(weight_pct, 4),
                    "unrealized_pnl_pct": round(move_val, 4),
                    "weight_threshold_pct": DEFAULT_WEIGHT_THRESHOLD_PCT,
                    "move_threshold_pct": DEFAULT_MOVE_THRESHOLD_PCT,
                },
            ))
        return out


def _normalize_action(row: Mapping[str, Any]) -> str:
    for key in ("action", "operation_advice", "action_label"):
        raw = row.get(key)
        if raw is None:
            continue
        text = str(raw).strip().lower()
        if not text:
            continue
        if text in {"buy", "买入", "加仓", "accumulate", "long"}:
            return "buy"
        if text in {"sell", "卖出", "减仓", "reduce", "short"}:
            return "sell"
        if text in {"hold", "持有", "观望", "neutral"}:
            return "hold"
        return text.split()[0][:32]
    return ""


def _is_directional_flip(previous: str, latest: str) -> bool:
    if previous == latest:
        return False
    directional = {"buy", "sell"}
    if previous in directional and latest in directional and previous != latest:
        return True
    if previous == "hold" and latest in directional:
        return True
    if previous in directional and latest == "hold":
        return True
    return previous != latest
