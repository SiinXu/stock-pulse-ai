# -*- coding: utf-8 -*-
"""Event-triggered deep analysis with debounce and budget caps (issues #129, #152).

All gates default off. Analysis is only enqueued when:
1. EVENT_TRIGGERED_ANALYSIS_ENABLED=true (master switch)
2. The rule explicitly opts in via notification_policy.auto_analysis=true
3. Per-symbol debounce and process-local budget caps allow the run

Uses AnalysisSubmissionService / task queue; never runs analysis inline on the
alert hot path.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from data_provider.base import normalize_stock_code
from src.utils.sanitize import log_safe_exception, sanitize_diagnostic_text

logger = logging.getLogger(__name__)

EVENT_TRIGGER_ELIGIBLE_ALERT_TYPES = frozenset(
    {
        "corporate_event",
        "volume_spike",
        "price_change_percent",
    }
)

DEFAULT_COOLDOWN_MINUTES = 180
DEFAULT_MAX_PER_HOUR = 5
DEFAULT_MAX_PER_DAY = 20
DEFAULT_PIPELINE = "standard"
PIPELINE_TO_REPORT_TYPE = {
    "standard": "detailed",
    "detailed": "detailed",
    "simple": "simple",
    "full": "detailed",
}
MAX_COOLDOWN_MINUTES = 7 * 24 * 60
MAX_BUDGET_PER_WINDOW = 10_000


@dataclass
class EventTriggerBudgetState:
    """Process-local counters for debounce and budget enforcement."""

    lock: threading.Lock = field(default_factory=threading.Lock)
    last_submitted_at: Dict[str, float] = field(default_factory=dict)
    hourly: List[float] = field(default_factory=list)
    daily: List[float] = field(default_factory=list)


_GLOBAL_STATE = EventTriggerBudgetState()


@dataclass(frozen=True)
class EventTriggerDecision:
    """Result of an auto-analysis attempt after a real alert trigger."""

    status: str
    submitted: bool = False
    stock_code: Optional[str] = None
    pipeline: Optional[str] = None
    report_type: Optional[str] = None
    reason: Optional[str] = None
    task_ids: Tuple[str, ...] = ()
    cooldown_minutes: Optional[int] = None
    max_per_hour: Optional[int] = None
    max_per_day: Optional[int] = None

    def to_public_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "status": self.status,
            "submitted": bool(self.submitted),
        }
        if self.stock_code:
            payload["stock_code"] = self.stock_code
        if self.pipeline:
            payload["pipeline"] = self.pipeline
        if self.report_type:
            payload["report_type"] = self.report_type
        if self.reason:
            payload["reason"] = sanitize_diagnostic_text(self.reason) or self.reason[:200]
        if self.task_ids:
            payload["task_ids"] = list(self.task_ids)[:10]
        if self.cooldown_minutes is not None:
            payload["cooldown_minutes"] = int(self.cooldown_minutes)
        if self.max_per_hour is not None:
            payload["max_per_hour"] = int(self.max_per_hour)
        if self.max_per_day is not None:
            payload["max_per_day"] = int(self.max_per_day)
        return payload


def is_event_triggered_analysis_enabled(config: Any) -> bool:
    return bool(getattr(config, "event_triggered_analysis_enabled", False))


def resolve_event_trigger_pipeline(config: Any, notification_policy: Optional[Dict[str, Any]] = None) -> str:
    policy = notification_policy if isinstance(notification_policy, dict) else {}
    raw = policy.get("pipeline") or policy.get("report_type")
    if raw in (None, ""):
        raw = getattr(config, "event_trigger_default_pipeline", None) or DEFAULT_PIPELINE
    text = str(raw or DEFAULT_PIPELINE).strip().lower()
    if text not in PIPELINE_TO_REPORT_TYPE:
        return DEFAULT_PIPELINE
    return text


def pipeline_to_report_type(pipeline: str) -> str:
    return PIPELINE_TO_REPORT_TYPE.get(str(pipeline or "").strip().lower(), "detailed")


def rule_auto_analysis_enabled(notification_policy: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(notification_policy, dict):
        return False
    value = notification_policy.get("auto_analysis")
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def normalize_budget_int(value: Any, *, default: int, minimum: int = 0, maximum: int = MAX_BUDGET_PER_WINDOW) -> int:
    if value in (None, ""):
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


def normalize_cooldown_minutes(value: Any) -> int:
    return normalize_budget_int(
        value,
        default=DEFAULT_COOLDOWN_MINUTES,
        minimum=0,
        maximum=MAX_COOLDOWN_MINUTES,
    )


def build_suggested_action(
    *,
    stock_code: str,
    alert_type: str,
    event_context: Optional[Dict[str, Any]] = None,
    impact_context: Optional[Dict[str, Any]] = None,
    auto_analysis: Optional[Dict[str, Any]] = None,
    report_language: str = "zh",
) -> Dict[str, Any]:
    """Build a privacy-bounded suggested next action with deep links."""
    symbol = ""
    try:
        symbol = normalize_stock_code(stock_code) if stock_code else ""
    except Exception as exc:  # broad-exception: fallback_recorded - isolate failure for sequential merge
        log_safe_exception(logger, "suggested action symbol normalize failed", exc, error_code="internal_error", level=logging.DEBUG)
        symbol = str(stock_code or "").strip()

    lang_en = str(report_language or "").lower().startswith("en")
    affected = {}
    if isinstance(impact_context, dict) and isinstance(impact_context.get("affected"), dict):
        affected = impact_context["affected"]
    in_portfolio = bool(affected.get("in_portfolio"))
    in_watchlist = bool(affected.get("in_watchlist"))

    if str(alert_type or "") == "corporate_event":
        action_code = "review_thesis"
        label = "Review investment thesis" if lang_en else "复核投资论点"
        rationale = (
            "Corporate event may reprice the thesis; review holdings context and consider a deeper analysis."
            if lang_en
            else "企业事件可能重定价投资论点；请结合持仓/自选相关性复核，并按需触发深度分析。"
        )
    elif str(alert_type or "") in {"volume_spike", "price_change_percent"}:
        action_code = "review_abnormal_move"
        label = "Review abnormal move" if lang_en else "复核异动"
        rationale = (
            "Price/volume anomaly detected; confirm catalyst and risk before acting."
            if lang_en
            else "价格/成交量异动已触发；请确认催化剂与风险后再行动。"
        )
    else:
        action_code = "review_alert"
        label = "Review alert" if lang_en else "查看告警"
        rationale = (
            "Alert fired; open the stock detail and related event history."
            if lang_en
            else "告警已触发；请打开个股详情与相关事件历史。"
        )

    deep_links: Dict[str, str] = {
        "event_alerts": "/event-alerts",
        "signals_rules": "/signals?tab=rules",
    }
    if symbol:
        deep_links["stock_detail"] = f"/stocks/{symbol}"
        deep_links["analysis"] = f"/research/analysis?stock={symbol}"

    source_url = None
    if isinstance(event_context, dict):
        source_url = event_context.get("source_url")
    if source_url:
        deep_links["source"] = str(source_url)[:2048]

    relevance_bits: List[str] = []
    if in_portfolio:
        relevance_bits.append("portfolio" if lang_en else "持仓")
    if in_watchlist:
        relevance_bits.append("watchlist" if lang_en else "自选")

    payload: Dict[str, Any] = {
        "action_code": action_code,
        "label": label,
        "rationale": rationale,
        "deep_links": deep_links,
        "relevance": relevance_bits,
    }
    if isinstance(auto_analysis, dict) and auto_analysis:
        payload["auto_analysis"] = auto_analysis
    return payload


def format_suggested_action_excerpt(
    suggested_action: Any,
    *,
    report_language: str = "zh",
) -> str:
    if not isinstance(suggested_action, dict) or not suggested_action:
        return ""
    lang_en = str(report_language or "").lower().startswith("en")
    lines = ["**Suggested action**" if lang_en else "**建议动作**"]
    label = suggested_action.get("label")
    if label:
        lines.append(f"- {label}")
    rationale = suggested_action.get("rationale")
    if rationale:
        lines.append(f"- {str(rationale)[:160]}")
    deep_links = suggested_action.get("deep_links") if isinstance(suggested_action.get("deep_links"), dict) else {}
    analysis_link = deep_links.get("analysis") or deep_links.get("stock_detail")
    if analysis_link:
        lines.append(f"- link: {analysis_link}" if lang_en else f"- 链接：{analysis_link}")
    auto = suggested_action.get("auto_analysis") if isinstance(suggested_action.get("auto_analysis"), dict) else None
    if auto:
        status = auto.get("status") or "unknown"
        lines.append(
            f"- auto analysis: {status}"
            if lang_en
            else f"- 自动分析：{status}"
        )
    return "\n".join(lines)


class EventTriggeredAnalysisService:
    """Debounced, budget-capped enqueue of deep analysis after alert triggers."""

    def __init__(
        self,
        *,
        state: Optional[EventTriggerBudgetState] = None,
        submission_service: Optional[Any] = None,
        now_provider: Optional[Callable[[], float]] = None,
        security_audit_factory: Optional[Callable[[], Any]] = None,
    ) -> None:
        self.state = state or _GLOBAL_STATE
        self.submission_service = submission_service
        self.now_provider = now_provider or time.time
        self.security_audit_factory = security_audit_factory

    def maybe_submit(
        self,
        *,
        config: Any,
        stock_code: str,
        alert_type: str,
        rule_id: Optional[int] = None,
        notification_policy: Optional[Dict[str, Any]] = None,
        trigger_reason: Optional[str] = None,
    ) -> EventTriggerDecision:
        alert_type_norm = str(alert_type or "").strip().lower()
        cooldown_minutes = normalize_cooldown_minutes(
            getattr(config, "event_trigger_cooldown_minutes", DEFAULT_COOLDOWN_MINUTES)
        )
        max_per_hour = normalize_budget_int(
            getattr(config, "event_trigger_max_per_hour", DEFAULT_MAX_PER_HOUR),
            default=DEFAULT_MAX_PER_HOUR,
            minimum=0,
        )
        max_per_day = normalize_budget_int(
            getattr(config, "event_trigger_max_per_day", DEFAULT_MAX_PER_DAY),
            default=DEFAULT_MAX_PER_DAY,
            minimum=0,
        )
        pipeline = resolve_event_trigger_pipeline(config, notification_policy)
        report_type = pipeline_to_report_type(pipeline)

        try:
            symbol = normalize_stock_code(stock_code) if stock_code else ""
        except Exception as exc:  # broad-exception: fallback_recorded - isolate failure for sequential merge
            log_safe_exception(logger, "event trigger symbol normalize failed", exc, error_code="internal_error", level=logging.DEBUG)
            symbol = str(stock_code or "").strip()

        if not is_event_triggered_analysis_enabled(config):
            return EventTriggerDecision(
                status="disabled",
                stock_code=symbol or None,
                pipeline=pipeline,
                report_type=report_type,
                reason="EVENT_TRIGGERED_ANALYSIS_ENABLED is false",
                cooldown_minutes=cooldown_minutes,
                max_per_hour=max_per_hour,
                max_per_day=max_per_day,
            )

        if not rule_auto_analysis_enabled(notification_policy):
            return EventTriggerDecision(
                status="rule_opt_in_required",
                stock_code=symbol or None,
                pipeline=pipeline,
                report_type=report_type,
                reason="notification_policy.auto_analysis is not true",
                cooldown_minutes=cooldown_minutes,
                max_per_hour=max_per_hour,
                max_per_day=max_per_day,
            )

        if alert_type_norm not in EVENT_TRIGGER_ELIGIBLE_ALERT_TYPES:
            return EventTriggerDecision(
                status="ineligible_alert_type",
                stock_code=symbol or None,
                pipeline=pipeline,
                report_type=report_type,
                reason=f"alert_type {alert_type_norm or '<empty>'} cannot auto-trigger analysis",
                cooldown_minutes=cooldown_minutes,
                max_per_hour=max_per_hour,
                max_per_day=max_per_day,
            )

        if not symbol:
            return EventTriggerDecision(
                status="invalid_target",
                pipeline=pipeline,
                report_type=report_type,
                reason="stock_code missing",
                cooldown_minutes=cooldown_minutes,
                max_per_hour=max_per_hour,
                max_per_day=max_per_day,
            )

        debounce_key = f"{rule_id or 0}:{symbol}:{alert_type_norm}"
        now = float(self.now_provider())
        with self.state.lock:
            self._prune_windows(now)
            last = self.state.last_submitted_at.get(debounce_key)
            if cooldown_minutes > 0 and last is not None and (now - last) < cooldown_minutes * 60:
                return EventTriggerDecision(
                    status="debounced",
                    stock_code=symbol,
                    pipeline=pipeline,
                    report_type=report_type,
                    reason=f"cooldown active ({cooldown_minutes}m)",
                    cooldown_minutes=cooldown_minutes,
                    max_per_hour=max_per_hour,
                    max_per_day=max_per_day,
                )
            if max_per_hour > 0 and len(self.state.hourly) >= max_per_hour:
                return EventTriggerDecision(
                    status="budget_exceeded",
                    stock_code=symbol,
                    pipeline=pipeline,
                    report_type=report_type,
                    reason=f"hourly budget {max_per_hour} reached",
                    cooldown_minutes=cooldown_minutes,
                    max_per_hour=max_per_hour,
                    max_per_day=max_per_day,
                )
            if max_per_day > 0 and len(self.state.daily) >= max_per_day:
                return EventTriggerDecision(
                    status="budget_exceeded",
                    stock_code=symbol,
                    pipeline=pipeline,
                    report_type=report_type,
                    reason=f"daily budget {max_per_day} reached",
                    cooldown_minutes=cooldown_minutes,
                    max_per_hour=max_per_hour,
                    max_per_day=max_per_day,
                )
            self.state.last_submitted_at[debounce_key] = now
            self.state.hourly.append(now)
            self.state.daily.append(now)

        try:
            task_ids = self._enqueue(
                stock_code=symbol,
                report_type=report_type,
                trigger_reason=trigger_reason,
                alert_type=alert_type_norm,
                rule_id=rule_id,
            )
        except Exception as exc:  # broad-exception: fallback_recorded - isolate failure for sequential merge
            log_safe_exception(
                logger,
                "Event-triggered analysis enqueue failed",
                exc,
                error_code="event_triggered_analysis_enqueue_failed",
                level=logging.WARNING,
                context={"stock_code": symbol, "alert_type": alert_type_norm},
            )
            with self.state.lock:
                self.state.last_submitted_at.pop(debounce_key, None)
                if self.state.hourly and abs(self.state.hourly[-1] - now) < 1e-6:
                    self.state.hourly.pop()
                if self.state.daily and abs(self.state.daily[-1] - now) < 1e-6:
                    self.state.daily.pop()
            return EventTriggerDecision(
                status="failed",
                stock_code=symbol,
                pipeline=pipeline,
                report_type=report_type,
                reason=sanitize_diagnostic_text(str(exc) or "enqueue failed") or "enqueue failed",
                cooldown_minutes=cooldown_minutes,
                max_per_hour=max_per_hour,
                max_per_day=max_per_day,
            )

        if not task_ids:
            return EventTriggerDecision(
                status="duplicate_or_empty",
                stock_code=symbol,
                pipeline=pipeline,
                report_type=report_type,
                reason="no new analysis task accepted (duplicate or empty)",
                cooldown_minutes=cooldown_minutes,
                max_per_hour=max_per_hour,
                max_per_day=max_per_day,
            )

        return EventTriggerDecision(
            status="submitted",
            submitted=True,
            stock_code=symbol,
            pipeline=pipeline,
            report_type=report_type,
            reason="analysis task accepted",
            task_ids=tuple(task_ids),
            cooldown_minutes=cooldown_minutes,
            max_per_hour=max_per_hour,
            max_per_day=max_per_day,
        )

    def _enqueue(
        self,
        *,
        stock_code: str,
        report_type: str,
        trigger_reason: Optional[str],
        alert_type: str,
        rule_id: Optional[int],
    ) -> List[str]:
        from src.services.analysis_submission_service import (
            AnalysisSubmissionService,
            build_submission_command,
        )
        from src.services.security_audit_service import SecurityAuditService

        service = self.submission_service or AnalysisSubmissionService()
        if self.security_audit_factory is not None:
            audit = self.security_audit_factory()
        else:
            audit = SecurityAuditService()

        query = trigger_reason or f"event-triggered analysis ({alert_type})"
        if rule_id:
            query = f"{query} [rule_id={rule_id}]"
        command = build_submission_command(
            stock_codes=[stock_code],
            report_type=report_type,
            analysis_phase="auto",
            force_refresh=False,
            notify=True,
            original_query=query[:500],
            selection_source="event_trigger",
        )
        result = service.submit(command, security_audit=audit)
        task_ids: List[str] = []
        for task in result.accepted_tasks:
            task_id = getattr(task, "task_id", None) or getattr(task, "id", None)
            if task_id is not None:
                task_ids.append(str(task_id))
        return task_ids

    def _prune_windows(self, now: float) -> None:
        hour_cut = now - 3600.0
        day_cut = now - 86400.0
        self.state.hourly = [ts for ts in self.state.hourly if ts >= hour_cut]
        self.state.daily = [ts for ts in self.state.daily if ts >= day_cut]
        stale = [key for key, ts in self.state.last_submitted_at.items() if ts < now - 7 * 86400]
        for key in stale:
            self.state.last_submitted_at.pop(key, None)


def reset_event_trigger_budget_state_for_tests() -> None:
    """Clear process-local budget state (tests only)."""
    with _GLOBAL_STATE.lock:
        _GLOBAL_STATE.last_submitted_at.clear()
        _GLOBAL_STATE.hourly.clear()
        _GLOBAL_STATE.daily.clear()
