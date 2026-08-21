# -*- coding: utf-8 -*-
"""Daily brief: personal morning push + historical accuracy review.

Assembles a scannable morning brief from portfolio holdings (#149), overnight
Today's Focus highlights (#149), observed earnings-event context (#1131), yesterday
analyses, watchlist context, and historical accuracy (#466). Optional quiet
mode skips notify when no material content is present. Section failures fail-open.
"""

from __future__ import annotations

import logging
import math
import threading
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Set
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.utils.sanitize import log_safe_exception, sanitize_diagnostic_text


logger = logging.getLogger(__name__)

DAILY_BRIEF_HISTORY_CODE = "DAILY_BRIEF"
DAILY_BRIEF_REPORT_TYPE = "daily_brief"
DAILY_BRIEF_PACK_VERSION = "daily_brief/1.0"

# Default honesty threshold for publishing a hit rate / accuracy percentage.
DEFAULT_MIN_SAMPLES = 10
# Cap how many analysis rows / notable outcome rows appear in the brief.
MAX_YESTERDAY_ANALYSES = 20
MAX_WATCHLIST_PREVIEW = 30
MAX_NOTABLE_OUTCOMES = 5
MAX_SKILL_BUCKETS = 5
MAX_DAILY_BRIEF_MARKDOWN_CHARS = 24_000

# Scheduler poll interval for the once-per-day gate (seconds).
DAILY_BRIEF_POLL_INTERVAL_SECONDS = 60


@dataclass(frozen=True)
class DailyBriefConfigView:
    """Resolved runtime knobs for one brief generation."""

    enabled: bool = False
    schedule_time: str = "08:30"
    timezone_name: str = "Asia/Shanghai"
    min_samples: int = DEFAULT_MIN_SAMPLES
    notify: bool = True
    persist_history: bool = True
    save_report_file: bool = True
    quiet_when_empty: bool = False


@dataclass
class DailyBriefBuildResult:
    """Structured payload + rendered markdown for one brief."""

    payload: Dict[str, Any]
    markdown: str
    query_id: str
    local_date: str
    history_id: Optional[int] = None
    notification_status: str = "not_requested"
    notification_ok: bool = False
    skipped_reason: Optional[str] = None
    errors: List[str] = field(default_factory=list)


def resolve_daily_brief_config(config: Any = None) -> DailyBriefConfigView:
    """Read config-gated daily brief knobs with safe defaults (off)."""
    if config is None:
        from src.application_services import get_application_services

        config = get_application_services().config

    schedule_time = str(
        getattr(config, "daily_brief_schedule_time", None) or "08:30"
    ).strip() or "08:30"
    try:
        _parse_hhmm(schedule_time)
    except ValueError:
        schedule_time = "08:30"

    timezone_name = str(
        getattr(config, "daily_brief_timezone", None)
        or getattr(config, "notification_timezone", None)
        or "Asia/Shanghai"
    ).strip() or "Asia/Shanghai"
    try:
        ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        timezone_name = "Asia/Shanghai"

    try:
        min_samples = int(getattr(config, "daily_brief_min_samples", DEFAULT_MIN_SAMPLES))
    except (TypeError, ValueError):
        min_samples = DEFAULT_MIN_SAMPLES
    min_samples = max(1, min(min_samples, 10_000))

    return DailyBriefConfigView(
        enabled=bool(getattr(config, "daily_brief_enabled", False)),
        schedule_time=schedule_time,
        timezone_name=timezone_name,
        min_samples=min_samples,
        notify=bool(getattr(config, "daily_brief_notify", True)),
        persist_history=bool(getattr(config, "daily_brief_persist_history", True)),
        save_report_file=bool(getattr(config, "daily_brief_save_report_file", True)),
        quiet_when_empty=bool(getattr(config, "daily_brief_quiet_when_empty", False)),
    )


def _parse_hhmm(value: str) -> time:
    parts = str(value or "").strip().split(":")
    if len(parts) != 2:
        raise ValueError("schedule time must use HH:MM")
    hour = int(parts[0])
    minute = int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("schedule time out of range")
    return time(hour=hour, minute=minute)


def _local_now(timezone_name: str, *, clock: Optional[Callable[[], datetime]] = None) -> datetime:
    clock_fn = clock or (lambda: datetime.now(timezone.utc))
    now = clock_fn()
    if now.tzinfo is None or now.utcoffset() is None:
        now = now.replace(tzinfo=timezone.utc)
    try:
        return now.astimezone(ZoneInfo(timezone_name))
    except (ZoneInfoNotFoundError, ValueError):
        return now.astimezone(ZoneInfo("Asia/Shanghai"))


def _templates_dir() -> Path:
    base = Path(__file__).resolve().parent.parent.parent
    try:
        from src.application_services import get_application_services

        configured = Path(getattr(get_application_services().config, "report_templates_dir", "templates") or "templates")
    except Exception as exc:  # broad-exception: fallback_recorded - isolate failure for sequential merge
        log_safe_exception(logger, 'operation failed', exc, error_code='internal_error', level=logging.WARNING)
        configured = Path("templates")
    if configured.is_absolute():
        return configured
    return base / configured


class DailyBriefService:
    """Build, render, persist, and optionally notify a daily brief."""

    def __init__(
        self,
        *,
        analysis_repo: Any = None,
        decision_outcome_service: Any = None,
        decision_signal_repo: Any = None,
        backtest_service: Any = None,
        skill_performance_service: Any = None,
        portfolio_repository: Any = None,
        todays_focus_service: Any = None,
        event_research_brief_service: Any = None,
        notifier: Any = None,
        config_provider: Optional[Callable[[], Any]] = None,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self._analysis_repo = analysis_repo
        self._decision_outcome_service = decision_outcome_service
        self._decision_signal_repo = decision_signal_repo
        self._backtest_service = backtest_service
        self._skill_performance_service = skill_performance_service
        self._portfolio_repository = portfolio_repository
        self._todays_focus_service = todays_focus_service
        self._event_research_brief_service = event_research_brief_service
        self._notifier = notifier
        self._config_provider = config_provider
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._run_lock = threading.Lock()
        self._last_run_local_date: Optional[str] = None

    # ------------------------------------------------------------------
    # Lazy deps (read-only consumers of existing stores)
    # ------------------------------------------------------------------

    def _config(self) -> Any:
        if self._config_provider is not None:
            return self._config_provider()
        from src.application_services import get_application_services

        return get_application_services().config

    @property
    def analysis_repo(self) -> Any:
        if self._analysis_repo is None:
            from src.repositories.analysis_repo import AnalysisRepository

            self._analysis_repo = AnalysisRepository()
        return self._analysis_repo

    @property
    def decision_outcome_service(self) -> Any:
        if self._decision_outcome_service is None:
            from src.services.decision_signal_outcome_service import (
                DecisionSignalOutcomeService,
            )

            self._decision_outcome_service = DecisionSignalOutcomeService()
        return self._decision_outcome_service

    @property
    def decision_signal_repo(self) -> Any:
        if self._decision_signal_repo is None:
            from src.repositories.decision_signal_repo import DecisionSignalRepository

            self._decision_signal_repo = DecisionSignalRepository()
        return self._decision_signal_repo

    @property
    def backtest_service(self) -> Any:
        if self._backtest_service is None:
            from src.services.backtest_service import BacktestService

            self._backtest_service = BacktestService()
        return self._backtest_service

    @property
    def skill_performance_service(self) -> Any:
        if self._skill_performance_service is None:
            from src.services.skill_opinion_performance_service import (
                SkillOpinionPerformanceService,
            )

            self._skill_performance_service = SkillOpinionPerformanceService()
        return self._skill_performance_service

    @property
    def notifier(self) -> Any:
        if self._notifier is None:
            from src.notification import NotificationService

            self._notifier = NotificationService()
        return self._notifier

    @property
    def portfolio_repository(self) -> Any:
        if self._portfolio_repository is None:
            try:
                from src.repositories.portfolio_repo import PortfolioRepository
                self._portfolio_repository = PortfolioRepository()
            except Exception as exc:  # broad-exception: fallback_recorded - optional portfolio source
                log_safe_exception(logger, "Daily brief portfolio repository unavailable", exc,
                                   error_code="daily_brief_portfolio_unavailable", level=logging.WARNING)
                self._portfolio_repository = False
        return self._portfolio_repository if self._portfolio_repository is not False else None

    @property
    def todays_focus_service(self) -> Any:
        if self._todays_focus_service is None:
            from src.services.todays_focus_service import TodaysFocusService
            self._todays_focus_service = TodaysFocusService(
                config_provider=self._config_provider or (lambda: self._config()),
                clock=self._clock,
            )
        return self._todays_focus_service

    @property
    def event_research_brief_service(self) -> Any:
        if self._event_research_brief_service is None:
            from src.services.event_research_brief_service import EventResearchBriefService
            self._event_research_brief_service = EventResearchBriefService(
                config_provider=self._config_provider or (lambda: self._config()),
                clock=self._clock,
            )
        return self._event_research_brief_service

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    def should_run_now(
        self,
        *,
        config: Any = None,
        force: bool = False,
    ) -> bool:
        """Return True when the config gate and once-per-day schedule allow a run."""
        view = resolve_daily_brief_config(config if config is not None else self._config())
        if not view.enabled and not force:
            return False
        if force:
            return True
        local_now = _local_now(view.timezone_name, clock=self._clock)
        schedule = _parse_hhmm(view.schedule_time)
        if local_now.timetz().replace(tzinfo=None) < schedule:
            return False
        local_date = local_now.date().isoformat()
        if self._last_run_local_date == local_date:
            return False
        if self._history_exists_for_local_date(local_date, timezone_name=view.timezone_name):
            self._last_run_local_date = local_date
            return False
        return True

    def maybe_run(self, *, force: bool = False) -> Optional[DailyBriefBuildResult]:
        """Scheduler tick: run at most once per local day when enabled."""
        config = self._config()
        view = resolve_daily_brief_config(config)
        if not view.enabled and not force:
            return None
        if not self.should_run_now(config=config, force=force):
            return None
        return self.run(force=force)

    def run(
        self,
        *,
        force: bool = False,
        notify: Optional[bool] = None,
        persist_history: Optional[bool] = None,
        save_report_file: Optional[bool] = None,
    ) -> DailyBriefBuildResult:
        """Generate the brief, optionally persist and notify.

        One notification channel failure never aborts persistence or the
        returned payload (notification status is recorded only).
        """
        with self._run_lock:
            config = self._config()
            view = resolve_daily_brief_config(config)
            if not view.enabled and not force:
                return DailyBriefBuildResult(
                    payload={},
                    markdown="",
                    query_id="",
                    local_date="",
                    skipped_reason="disabled",
                )

            local_now = _local_now(view.timezone_name, clock=self._clock)
            local_date = local_now.date().isoformat()
            query_id = f"daily_brief_{local_date}_{uuid.uuid4().hex[:12]}"

            payload = self.build_payload(
                config=config,
                view=view,
                local_now=local_now,
                query_id=query_id,
            )
            markdown = self.render_markdown(payload)
            result = DailyBriefBuildResult(
                payload=payload,
                markdown=markdown,
                query_id=query_id,
                local_date=local_date,
            )

            do_persist = view.persist_history if persist_history is None else bool(persist_history)
            do_save_file = view.save_report_file if save_report_file is None else bool(save_report_file)
            do_notify = view.notify if notify is None else bool(notify)
            material = bool((payload.get("materiality") or {}).get("has_material_content"))
            if do_notify and view.quiet_when_empty and not material:
                do_notify = False
                result.notification_status = "quiet_skipped"
                result.skipped_reason = result.skipped_reason or "quiet_when_empty"

            if do_save_file and markdown:
                try:
                    filename = f"daily_brief_{local_date.replace('-', '')}.md"
                    self.notifier.save_report_to_file(markdown, filename)
                except Exception as exc:  # broad-exception: fallback_recorded - isolate failure for sequential merge
                    log_safe_exception(
                        logger,
                        "Daily brief report file save failed; continuing",
                        exc,
                        error_code="daily_brief_save_report_failed",
                        level=logging.WARNING,
                    )
                    result.errors.append("save_report_failed")

            if do_persist and markdown:
                history_id = self._persist_history(
                    markdown=markdown,
                    payload=payload,
                    query_id=query_id,
                    local_date=local_date,
                    config=config,
                )
                result.history_id = history_id or None
                if not history_id:
                    result.errors.append("persist_history_failed")

            if do_notify and markdown:
                result.notification_status, result.notification_ok = self._send_notification(
                    markdown
                )
            elif result.notification_status == "quiet_skipped":
                pass
            elif not do_notify:
                result.notification_status = "not_requested"

            self._last_run_local_date = local_date
            logger.info(
                "[DailyBrief] generated query_id=%s local_date=%s accuracy_status=%s notify=%s",
                query_id,
                local_date,
                (payload.get("accuracy") or {}).get("status"),
                result.notification_status,
            )
            return result

    def build_payload(
        self,
        *,
        config: Any = None,
        view: Optional[DailyBriefConfigView] = None,
        local_now: Optional[datetime] = None,
        query_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Assemble the structured brief without side effects."""
        runtime = config if config is not None else self._config()
        resolved = view or resolve_daily_brief_config(runtime)
        now_local = local_now or _local_now(resolved.timezone_name, clock=self._clock)
        local_date = now_local.date()
        yesterday = local_date - timedelta(days=1)
        report_language = str(getattr(runtime, "report_language", "zh") or "zh")

        watchlist = self._watchlist_codes(runtime)
        portfolio = self._build_portfolio_section()
        portfolio_codes = {
            str(item.get("code") or "").upper()
            for item in (portfolio.get("holdings") or [])
            if item.get("code")
        }
        yesterday_analyses = self._load_yesterday_analyses(
            yesterday=yesterday,
            timezone_name=resolved.timezone_name,
            watchlist=watchlist,
            portfolio_codes=portfolio_codes,
        )
        watchlist_context = self._build_watchlist_context(
            watchlist=watchlist,
            recent_analyses=yesterday_analyses,
            portfolio_codes=portfolio_codes,
        )
        overnight = self._build_overnight_section(runtime=runtime, report_language=report_language)
        event_briefs = self._build_event_foresight_section(
            runtime=runtime, watchlist=watchlist, portfolio_codes=portfolio_codes,
        )
        accuracy = self._build_accuracy_section(min_samples=resolved.min_samples)
        materiality = self._assess_materiality(
            portfolio=portfolio, overnight=overnight, event_briefs=event_briefs,
            yesterday_analyses=yesterday_analyses,
        )
        return {
            "pack_version": DAILY_BRIEF_PACK_VERSION,
            "query_id": query_id or f"daily_brief_{local_date.isoformat()}",
            "report_date": local_date.isoformat(),
            "report_timestamp": now_local.isoformat(),
            "timezone": resolved.timezone_name,
            "report_language": report_language,
            "yesterday_date": yesterday.isoformat(),
            "portfolio": portfolio,
            "overnight_highlights": overnight,
            "event_foresight": event_briefs,
            "yesterday_analyses": yesterday_analyses,
            "watchlist": watchlist_context,
            "accuracy": accuracy,
            "materiality": materiality,
            "honesty": {
                "min_samples": resolved.min_samples,
                "fabricated_metrics": False,
                "note": accuracy.get("honesty_note"),
            },
        }

    def render_markdown(self, payload: Mapping[str, Any]) -> str:
        """Render ``templates/daily_brief.j2``; fall back to a plain-text body."""
        try:
            from jinja2 import Environment, FileSystemLoader, select_autoescape
        except ImportError:
            return _bounded_markdown(
                self._fallback_markdown(payload),
                MAX_DAILY_BRIEF_MARKDOWN_CHARS,
            )

        templates_dir = _templates_dir()
        template_path = templates_dir / "daily_brief.j2"
        if not template_path.exists():
            logger.warning("Daily brief template missing: %s", template_path)
            return _bounded_markdown(
                self._fallback_markdown(payload),
                MAX_DAILY_BRIEF_MARKDOWN_CHARS,
            )

        try:
            env = Environment(
                loader=FileSystemLoader(str(templates_dir)),
                autoescape=select_autoescape(enabled_extensions=()),
                trim_blocks=True,
                lstrip_blocks=True,
            )
            template = env.get_template("daily_brief.j2")
            labels = self._labels(str(payload.get("report_language") or "zh"))
            rendered = str(template.render(brief=payload, labels=labels)).strip() + "\n"
            return _bounded_markdown(rendered, MAX_DAILY_BRIEF_MARKDOWN_CHARS)
        except Exception as exc:  # broad-exception: fallback_recorded - isolate failure for sequential merge
            log_safe_exception(
                logger,
                "Daily brief template render failed; using fallback markdown",
                exc,
                error_code="daily_brief_template_render_failed",
                level=logging.WARNING,
            )
            return _bounded_markdown(
                self._fallback_markdown(payload),
                MAX_DAILY_BRIEF_MARKDOWN_CHARS,
            )

    # ------------------------------------------------------------------
    # Sections
    # ------------------------------------------------------------------

    def _watchlist_codes(self, config: Any) -> List[str]:
        raw = getattr(config, "stock_list", None) or []
        if isinstance(raw, str):
            from src.utils.stock_list import split_stock_list

            raw = split_stock_list(raw)
        codes: List[str] = []
        seen = set()
        for item in raw:
            code = str(item or "").strip().upper()
            if not code or code in seen:
                continue
            seen.add(code)
            codes.append(code)
            if len(codes) >= MAX_WATCHLIST_PREVIEW * 2:
                break
        return codes

    def _load_yesterday_analyses(self, *, yesterday: date, timezone_name: str, watchlist: Sequence[str], portfolio_codes: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
        try:
            rows = self.analysis_repo.get_list(code=None, days=3, limit=200)
        except Exception as exc:  # broad-exception: fallback_recorded - section remains explicitly unavailable
            log_safe_exception(logger, "Daily brief yesterday analysis load failed", exc, error_code="daily_brief_yesterday_load_failed", level=logging.WARNING)
            return []
        watch_set = {c.upper() for c in watchlist}
        hold_set = {c.upper() for c in (portfolio_codes or set()) if c}
        items: List[Dict[str, Any]] = []
        for row in rows:
            report_type = str(getattr(row, "report_type", None) or "").strip().lower()
            code = str(getattr(row, "code", None) or "").strip().upper()
            if not code or code in {DAILY_BRIEF_HISTORY_CODE, "MARKET", "EVENT_BRIEF"} or report_type in {DAILY_BRIEF_REPORT_TYPE, "market_review", "event_research_brief"}:
                continue
            created = getattr(row, "created_at", None)
            if not isinstance(created, datetime):
                continue
            if self._to_local_date(created, timezone_name) != yesterday:
                continue
            items.append({
                "code": code, "name": str(getattr(row, "stock_name", None) or code),
                "operation_advice": getattr(row, "operation_advice", None),
                "sentiment_score": _finite_float(
                    getattr(row, "sentiment_score", None), minimum=0, maximum=100
                ),
                "trend_prediction": getattr(row, "trend_prediction", None),
                "analysis_summary": _clip(getattr(row, "analysis_summary", None), 120),
                "report_type": report_type or None, "created_at": created.isoformat(),
                "on_watchlist": code in watch_set if watch_set else False,
                "in_portfolio": code in hold_set if hold_set else False,
                "query_id": getattr(row, "query_id", None),
            })
        items.sort(key=lambda item: (not item["in_portfolio"], not item["on_watchlist"], item.get("created_at") or ""))
        return items[:MAX_YESTERDAY_ANALYSES]

    def _build_watchlist_context(self, *, watchlist: Sequence[str], recent_analyses: Sequence[Mapping[str, Any]], portfolio_codes: Optional[Set[str]] = None) -> Dict[str, Any]:
        recent_codes = {str(item.get("code") or "").upper() for item in recent_analyses if item.get("code")}
        hold_set = {c.upper() for c in (portfolio_codes or set()) if c}
        entries = [{"code": code, "had_yesterday_analysis": code in recent_codes, "in_portfolio": code in hold_set} for code in list(watchlist)[:MAX_WATCHLIST_PREVIEW]]
        entries.sort(key=lambda e: (not e["in_portfolio"], e["code"]))
        covered = sum(1 for e in entries if e["had_yesterday_analysis"])
        return {"codes": list(watchlist)[:MAX_WATCHLIST_PREVIEW], "total": len(watchlist), "previewed": len(entries),
                "with_yesterday_analysis": covered, "without_yesterday_analysis": max(0, len(entries) - covered),
                "entries": entries, "empty": len(watchlist) == 0}

    def _build_portfolio_section(self) -> Dict[str, Any]:
        repo = self.portfolio_repository
        if repo is None:
            return {"status": "unavailable", "holdings": [], "total": 0, "empty": True, "message": "Portfolio position cache unavailable."}
        try:
            rows = repo.list_cached_positions(account_id=None, cost_method="fifo")
        except Exception as exc:  # broad-exception: fallback_recorded - section remains explicitly unavailable
            log_safe_exception(logger, "Daily brief portfolio load failed", exc, error_code="daily_brief_portfolio_load_failed", level=logging.WARNING)
            return {"status": "unavailable", "holdings": [], "total": 0, "empty": True, "message": "Portfolio position cache read failed."}
        holdings: List[Dict[str, Any]] = []
        seen: Set[str] = set()
        for row in rows or []:
            if not isinstance(row, Mapping):
                continue
            symbol = str(row.get("symbol") or "").strip().upper()
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            # Cached positions may use a different valuation currency per
            # account. The daily brief only needs membership, so do not expose,
            # aggregate, or rank unnormalised quantities/market values.
            holdings.append({
                "code": symbol,
                "market": str(row.get("market") or "").strip().lower() or None,
            })
            if len(holdings) >= MAX_WATCHLIST_PREVIEW:
                break
        holdings.sort(key=lambda item: (item["code"], item.get("market") or ""))
        return {"status": "ok", "holdings": holdings, "total": len(holdings), "empty": len(holdings) == 0, "message": None}

    def _build_overnight_section(self, *, runtime: Any, report_language: str) -> Dict[str, Any]:
        try:
            focus = self.todays_focus_service.build_focus(max_items=8, language=report_language)
        except Exception as exc:  # broad-exception: fallback_recorded - section remains explicitly unavailable
            log_safe_exception(logger, "Daily brief overnight focus load failed", exc, error_code="daily_brief_overnight_failed", level=logging.WARNING)
            return {"status": "unavailable", "items": [], "item_count": 0, "empty": True, "message": "Overnight highlights unavailable.", "sources_used": [], "degraded_sources": ["todays_focus"]}
        items = []
        for raw in focus.get("items") or []:
            if isinstance(raw, Mapping):
                items.append({"code": raw.get("code"), "name": raw.get("name") or raw.get("code"),
                              "reason_code": raw.get("reason_code"), "reason_display": raw.get("reason_display"),
                              "secondary_reason_codes": list(raw.get("secondary_reason_codes") or [])})
        return {"status": str(focus.get("status") or "empty"), "items": items, "item_count": len(items), "empty": len(items) == 0,
                "message": focus.get("empty_message"), "sources_used": list(focus.get("sources_used") or []),
                "degraded_sources": list(focus.get("degraded_sources") or [])}

    def _build_event_foresight_section(self, *, runtime: Any, watchlist: Sequence[str], portfolio_codes: Set[str]) -> Dict[str, Any]:
        """Build recent-event context under the compatibility payload key."""
        universe = list(dict.fromkeys([*portfolio_codes, *list(watchlist)]))
        try:
            briefs = self.event_research_brief_service.build_briefs_for_universe(codes=universe or None, config=runtime, max_briefs=5)
        except Exception as exc:  # broad-exception: fallback_recorded - section remains explicitly unavailable
            log_safe_exception(logger, "Daily brief recent-event context load failed", exc, error_code="daily_brief_event_foresight_failed", level=logging.WARNING)
            return {"status": "unavailable", "briefs": [], "count": 0, "empty": True, "message": "Recent event context unavailable."}
        compact = []
        for brief in briefs or []:
            if not isinstance(brief, Mapping):
                continue
            compact.append({
                "stock_code": brief.get("stock_code"), "stock_name": brief.get("stock_name"),
                "event_category": brief.get("event_category"), "what_happened": brief.get("what_happened"),
                "why_it_matters": brief.get("why_it_matters"), "on_watchlist": brief.get("on_watchlist"),
                "in_portfolio": brief.get("in_portfolio"),
                "metrics_to_watch": list(brief.get("metrics_to_watch") or [])[:4],
                "surprise_criteria": brief.get("surprise_criteria"),
                "post_event_checklist": list(brief.get("post_event_checklist") or [])[:5],
                "verify_hook": brief.get("verify_hook"), "trigger_id": brief.get("trigger_id"),
                "observed_at": brief.get("observed_at"),
            })
        return {"status": "ok" if compact else "empty", "briefs": compact, "count": len(compact), "empty": len(compact) == 0,
                "message": None if compact else "No recent earnings-class events in universe."}

    @staticmethod
    def _assess_materiality(*, portfolio, overnight, event_briefs, yesterday_analyses) -> Dict[str, Any]:
        reasons = []
        if overnight.get("item_count"):
            reasons.append("overnight_highlights")
        if event_briefs.get("count"):
            reasons.append("event_foresight")
        if yesterday_analyses:
            reasons.append("yesterday_analyses")
        holdings = list(portfolio.get("holdings") or [])
        if holdings and any(i.get("in_portfolio") for i in yesterday_analyses):
            reasons.append("portfolio_analysis")
        return {"has_material_content": bool(reasons), "reasons": reasons, "portfolio_only": bool(holdings) and not reasons}

    def _build_accuracy_section(self, *, min_samples: int) -> Dict[str, Any]:
        """Aggregate accuracy from existing stores with explicit insufficiency."""
        signals = self._decision_signal_accuracy(min_samples=min_samples)
        backtest = self._backtest_accuracy(min_samples=min_samples)
        skills = self._skill_outcome_accuracy(min_samples=min_samples)

        source_statuses = [
            signals.get("status"),
            backtest.get("status"),
            skills.get("status"),
        ]
        if any(status == "ok" for status in source_statuses):
            overall_status = "ok"
            honesty_note = (
                "Accuracy figures below come only from completed evaluations "
                "already stored by the decision-signal, backtest, and skill-outcome "
                "pipelines. No new evaluation was run for this brief."
            )
        elif all(status == "unavailable" for status in source_statuses):
            overall_status = "unavailable"
            honesty_note = (
                "Historical accuracy stores could not be read. No accuracy "
                "percentages are shown."
            )
        else:
            overall_status = "insufficient_history"
            honesty_note = (
                "Insufficient completed evaluation history to publish a reliable "
                f"hit rate (minimum sample size: {min_samples}). "
                "No accuracy percentages have been fabricated."
            )

        return {
            "status": overall_status,
            "min_samples": min_samples,
            "honesty_note": honesty_note,
            "decision_signals": signals,
            "backtest": backtest,
            "skill_outcomes": skills,
        }

    def _decision_signal_accuracy(self, *, min_samples: int) -> Dict[str, Any]:
        try:
            try:
                from src.services.decision_signal_outcome_service import (
                    DECISION_SIGNAL_OUTCOME_ENGINE_VERSION,
                )
            except ImportError:
                DECISION_SIGNAL_OUTCOME_ENGINE_VERSION = None

            rows = self.decision_outcome_service.repo.list_stats_rows(
                engine_version=DECISION_SIGNAL_OUTCOME_ENGINE_VERSION,
                horizons=None,
                statuses=None,
            )
            completed = [
                row
                for row in rows
                if getattr(row, "eval_status", None) == "completed"
                and getattr(row, "outcome", None) in {"hit", "miss", "neutral"}
            ]
            aggregate = self.decision_outcome_service.aggregate_outcome_rows(completed)
            hit = _non_negative_int(aggregate.get("hit"))
            miss = _non_negative_int(aggregate.get("miss"))
            completed_count = _non_negative_int(aggregate.get("completed"))
            if hit is None or miss is None or completed_count is None:
                raise ValueError("invalid decision-signal aggregate counts")
            decided = hit + miss
            notable_hits, notable_misses = self._notable_signal_outcomes(completed)

            if decided < min_samples:
                return {
                    "status": "insufficient_data",
                    "sample_size": decided,
                    "completed": completed_count,
                    "hit": hit,
                    "miss": miss,
                    "hit_rate_pct": None,
                    "avg_return_pct": None,
                    "notable_hits": notable_hits,
                    "notable_misses": notable_misses,
                    "message": (
                        f"Only {decided} decided signal outcome(s); "
                        f"need at least {min_samples} before publishing a hit rate."
                    ),
                }
            return {
                "status": "ok",
                "sample_size": decided,
                "completed": completed_count,
                "hit": hit,
                "miss": miss,
                "hit_rate_pct": round(hit / decided * 100, 1),
                "avg_return_pct": _finite_float(
                    aggregate.get("avg_stock_return_pct")
                ),
                "notable_hits": notable_hits,
                "notable_misses": notable_misses,
                "message": None,
            }
        except Exception as exc:  # broad-exception: fallback_recorded - isolate failure for sequential merge
            log_safe_exception(
                logger,
                "Daily brief decision-signal accuracy read failed",
                exc,
                error_code="daily_brief_signal_accuracy_failed",
                level=logging.WARNING,
            )
            return {
                "status": "unavailable",
                "sample_size": 0,
                "completed": 0,
                "hit": 0,
                "miss": 0,
                "hit_rate_pct": None,
                "avg_return_pct": None,
                "notable_hits": [],
                "notable_misses": [],
                "message": "Decision-signal outcome store unavailable.",
            }

    def _notable_signal_outcomes(
        self,
        completed: Sequence[Any],
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        hits = [row for row in completed if getattr(row, "outcome", None) == "hit"]
        misses = [row for row in completed if getattr(row, "outcome", None) == "miss"]

        def _abs_return(row: Any) -> float:
            value = _finite_float(getattr(row, "stock_return_pct", None))
            return abs(value) if value is not None else -1.0

        hits_sorted = sorted(hits, key=_abs_return, reverse=True)[:MAX_NOTABLE_OUTCOMES]
        misses_sorted = sorted(misses, key=_abs_return, reverse=True)[:MAX_NOTABLE_OUTCOMES]
        signal_ids = {
            int(getattr(row, "signal_id"))
            for row in list(hits_sorted) + list(misses_sorted)
            if getattr(row, "signal_id", None) is not None
        }
        signal_map: Dict[int, Any] = {}
        for signal_id in signal_ids:
            try:
                signal = self.decision_signal_repo.get(signal_id)
            except Exception as exc:  # broad-exception: fallback_recorded - isolate failure for sequential merge
                log_safe_exception(logger, 'operation failed', exc, error_code='internal_error', level=logging.WARNING)
                signal = None
            if signal is not None:
                signal_map[signal_id] = signal

        def _serialize(row: Any) -> Dict[str, Any]:
            signal = signal_map.get(int(getattr(row, "signal_id", 0) or 0))
            anchor = getattr(row, "anchor_date", None)
            return_value = _finite_float(getattr(row, "stock_return_pct", None))
            return {
                "signal_id": getattr(row, "signal_id", None),
                "stock_code": getattr(signal, "stock_code", None),
                "stock_name": getattr(signal, "stock_name", None),
                "action": getattr(row, "action", None) or getattr(signal, "action", None),
                "horizon": getattr(row, "horizon", None),
                "return_pct": round(return_value, 2) if return_value is not None else None,
                "anchor_date": (
                    anchor.isoformat()
                    if hasattr(anchor, "isoformat")
                    else (str(anchor) if anchor else None)
                ),
            }

        return (
            [_serialize(row) for row in hits_sorted],
            [_serialize(row) for row in misses_sorted],
        )

    def _backtest_accuracy(self, *, min_samples: int) -> Dict[str, Any]:
        try:
            summary = self.backtest_service.get_summary(scope="overall", code=None)
        except Exception as exc:  # broad-exception: fallback_recorded - isolate failure for sequential merge
            log_safe_exception(
                logger,
                "Daily brief backtest accuracy read failed",
                exc,
                error_code="daily_brief_backtest_accuracy_failed",
                level=logging.WARNING,
            )
            return {
                "status": "unavailable",
                "completed_count": 0,
                "direction_accuracy_pct": None,
                "win_rate_pct": None,
                "message": "Backtest summary store unavailable.",
            }

        if not summary:
            return {
                "status": "insufficient_data",
                "completed_count": 0,
                "direction_accuracy_pct": None,
                "win_rate_pct": None,
                "message": (
                    "No overall backtest summary is stored yet. "
                    "Run backtests before expecting direction accuracy here."
                ),
            }

        completed = _non_negative_int(summary.get("completed_count"))
        if completed is None:
            return {
                "status": "unavailable",
                "completed_count": 0,
                "direction_accuracy_pct": None,
                "win_rate_pct": None,
                "message": "Backtest summary contains invalid numeric data; metrics were withheld.",
            }
        if completed < min_samples:
            return {
                "status": "insufficient_data",
                "completed_count": completed,
                "direction_accuracy_pct": None,
                "win_rate_pct": None,
                "message": (
                    f"Only {completed} completed backtest evaluation(s); "
                    f"need at least {min_samples} before publishing direction accuracy."
                ),
            }
        direction_accuracy = _finite_float(
            summary.get("direction_accuracy_pct"), minimum=0, maximum=100
        )
        win_rate = _finite_float(summary.get("win_rate_pct"), minimum=0, maximum=100)
        avg_return = _finite_float(summary.get("avg_stock_return_pct"))
        if direction_accuracy is None or win_rate is None:
            return {
                "status": "unavailable",
                "completed_count": completed,
                "direction_accuracy_pct": None,
                "win_rate_pct": None,
                "avg_stock_return_pct": None,
                "message": "Backtest summary contains invalid numeric data; metrics were withheld.",
            }
        return {
            "status": "ok",
            "completed_count": completed,
            "direction_accuracy_pct": direction_accuracy,
            "win_rate_pct": win_rate,
            "avg_stock_return_pct": avg_return,
            "eval_window_days": summary.get("eval_window_days"),
            "engine_version": summary.get("engine_version"),
            "message": None,
        }

    def _skill_outcome_accuracy(self, *, min_samples: int) -> Dict[str, Any]:
        """Consume the merged skill-opinion **performance** read API only."""
        try:
            stats = self.skill_performance_service.get_stats()
        except Exception as exc:  # broad-exception: fallback_recorded - isolate failure for sequential merge
            log_safe_exception(
                logger,
                "Daily brief skill-outcome accuracy read failed",
                exc,
                error_code="daily_brief_skill_accuracy_failed",
                level=logging.WARNING,
            )
            return {
                "status": "unavailable",
                "sufficient_buckets": 0,
                "buckets": [],
                "message": "Skill-opinion performance store unavailable.",
            }

        buckets = list(stats.get("buckets") or [])
        # Policy sample size is owned by SkillOpinionPerformanceService; we only
        # surface buckets already marked sample_sufficient / with hit_rate_pct.
        sufficient = []
        invalid_sufficient = False
        for bucket in buckets:
            if not bucket.get("sample_sufficient"):
                continue
            hit_rate = _finite_float(bucket.get("hit_rate_pct"), minimum=0, maximum=100)
            miss_rate = _finite_float(bucket.get("miss_rate_pct"), minimum=0, maximum=100)
            evaluated = _non_negative_int(bucket.get("evaluated"))
            if hit_rate is None or miss_rate is None or evaluated is None:
                invalid_sufficient = True
                continue
            sufficient.append({
                "skill_id": bucket.get("skill_id"),
                "horizon": bucket.get("horizon"),
                "evaluated": evaluated,
                "hit_rate_pct": hit_rate,
                "miss_rate_pct": miss_rate,
                "sample_status": bucket.get("sample_status"),
            })
        # Secondary honesty gate: treat very small service thresholds carefully.
        if not sufficient:
            evaluated_total = sum(
                value
                for value in (_non_negative_int(b.get("evaluated")) for b in buckets)
                if value is not None
            )
            if invalid_sufficient:
                return {
                    "status": "unavailable",
                    "sufficient_buckets": 0,
                    "buckets": [],
                    "evaluated_total": evaluated_total,
                    "message": "Skill performance contains invalid numeric data; metrics were withheld.",
                }
            return {
                "status": "insufficient_data",
                "sufficient_buckets": 0,
                "buckets": [],
                "evaluated_total": evaluated_total,
                "message": (
                    "No skill-opinion performance bucket has a sufficient sample "
                    "to publish a hit rate yet."
                ),
            }
        return {
            "status": "ok",
            "sufficient_buckets": len(sufficient),
            "buckets": sufficient[:MAX_SKILL_BUCKETS],
            "message": None,
        }

    # ------------------------------------------------------------------
    # Persistence / notification
    # ------------------------------------------------------------------

    def _history_exists_for_local_date(
        self,
        local_date: str,
        *,
        timezone_name: str,
    ) -> bool:
        try:
            rows = self.analysis_repo.get_list(
                code=DAILY_BRIEF_HISTORY_CODE,
                days=3,
                limit=20,
            )
        except Exception as exc:  # broad-exception: fallback_recorded - isolate failure for sequential merge
            log_safe_exception(logger, 'operation failed', exc, error_code='internal_error', level=logging.WARNING)
            return False
        target = date.fromisoformat(local_date)
        for row in rows:
            report_type = str(getattr(row, "report_type", None) or "").strip().lower()
            if report_type and report_type != DAILY_BRIEF_REPORT_TYPE:
                continue
            created = getattr(row, "created_at", None)
            if not isinstance(created, datetime):
                continue
            if self._to_local_date(created, timezone_name) == target:
                return True
        return False

    def _persist_history(
        self,
        *,
        markdown: str,
        payload: Mapping[str, Any],
        query_id: str,
        local_date: str,
        config: Any,
    ) -> int:
        try:
            from src.analyzer import AnalysisResult
            from src.storage import DatabaseManager

            report_language = str(payload.get("report_language") or "zh")
            accuracy = payload.get("accuracy") or {}
            summary = str(accuracy.get("honesty_note") or "Daily brief")
            if report_language == "en":
                stock_name = "Daily Brief"
                operation_advice = "View brief"
                trend_prediction = "Daily brief"
            else:
                stock_name = "每日简报"
                operation_advice = "查看简报"
                trend_prediction = "每日简报"

            result = AnalysisResult(
                code=DAILY_BRIEF_HISTORY_CODE,
                name=stock_name,
                sentiment_score=50,
                trend_prediction=trend_prediction,
                operation_advice=operation_advice,
                analysis_summary=_clip(summary, 400),
                report_language=report_language,
                news_summary=markdown,
                raw_response=markdown,
                data_sources="daily_brief",
            )
            context_snapshot = {
                "report_kind": DAILY_BRIEF_REPORT_TYPE,
                "pack_version": DAILY_BRIEF_PACK_VERSION,
                "report_date": local_date,
                "timezone": payload.get("timezone"),
                "accuracy_status": accuracy.get("status"),
                "daily_brief_payload": {
                    "yesterday_count": len(payload.get("yesterday_analyses") or []),
                    "watchlist_total": (payload.get("watchlist") or {}).get("total"),
                    "portfolio_total": (payload.get("portfolio") or {}).get("total"),
                    "overnight_count": (payload.get("overnight_highlights") or {}).get("item_count"),
                    "event_foresight_count": (payload.get("event_foresight") or {}).get("count"),
                    "material": (payload.get("materiality") or {}).get("has_material_content"),
                    "accuracy_status": accuracy.get("status"),
                    "min_samples": accuracy.get("min_samples"),
                },
            }
            db = DatabaseManager.get_instance()
            return int(
                db.save_analysis_history(
                    result=result,
                    query_id=query_id,
                    report_type=DAILY_BRIEF_REPORT_TYPE,
                    news_content=markdown,
                    context_snapshot=context_snapshot,
                    save_snapshot=True,
                )
                or 0
            )
        except Exception as exc:  # broad-exception: fallback_recorded - isolate failure for sequential merge
            log_safe_exception(
                logger,
                "Daily brief history persistence failed; notifications may still proceed",
                exc,
                error_code="daily_brief_history_persistence_failed",
                level=logging.WARNING,
                context={"query_id": query_id},
            )
            return 0

    def _send_notification(self, markdown: str) -> tuple[str, bool]:
        try:
            dispatch = self.notifier.send_with_results(
                markdown,
                email_send_to_all=True,
                route_type="report",
            )
            status = str(getattr(dispatch, "status", "all_failed") or "all_failed")
            success = bool(getattr(dispatch, "success", False))
            from src.notification_parts.dispatch import dispatch_channel_summaries

            channels = dispatch_channel_summaries(dispatch)
            if status == "partial_failed" and success:
                logger.warning(
                    "[DailyBrief] notification partial_failed channels=%s",
                    sanitize_diagnostic_text(channels),
                )
                return "degraded", True
            if status == "sent" and success:
                return "ok", True
            if status == "no_channel":
                return "not_configured", False
            return "degraded", False
        except Exception as exc:  # broad-exception: fallback_recorded - isolate failure for sequential merge
            log_safe_exception(
                logger,
                "Daily brief notification dispatch failed; brief generation continues",
                exc,
                error_code="daily_brief_notification_failed",
                level=logging.WARNING,
            )
            return "failed", False

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_local_date(value: datetime, timezone_name: str) -> date:
        if value.tzinfo is None or value.utcoffset() is None:
            # Storage convention is UTC-naive.
            value = value.replace(tzinfo=timezone.utc)
        try:
            return value.astimezone(ZoneInfo(timezone_name)).date()
        except (ZoneInfoNotFoundError, ValueError):
            return value.astimezone(timezone.utc).date()

    @staticmethod
    def _labels(report_language: str) -> Dict[str, str]:
        if str(report_language or "").lower().startswith("en"):
            return {
                "title": "Daily Brief", "portfolio_heading": "Holdings", "portfolio_empty": "No cached portfolio holdings.",
                "portfolio_unavailable": "Portfolio cache unavailable", "overnight_heading": "Overnight highlights",
                "overnight_empty": "No fresh overnight alerts, events, or analysis changes.",
                "overnight_unavailable": "Overnight highlights unavailable", "event_heading": "Recent earnings event context",
                "event_empty": "No recent earnings-class events on holdings/watchlist.", "event_unavailable": "Recent event context unavailable",
                "metrics_label": "Watch", "checklist_label": "Post-event check", "yesterday_heading": "Yesterday's analyses",
                "yesterday_empty": "No analyses were stored for yesterday.", "watchlist_heading": "Today's watchlist",
                "watchlist_empty": "Watchlist is empty — configure STOCK_LIST to personalize this section.",
                "watchlist_covered": "with yesterday analysis", "watchlist_missing": "no yesterday analysis",
                "accuracy_heading": "Historical accuracy review", "accuracy_insufficient": "Insufficient history",
                "accuracy_unavailable": "Accuracy stores unavailable", "signals_heading": "Decision-signal outcomes",
                "backtest_heading": "Backtest summary", "skills_heading": "Skill-opinion performance",
                "hit_rate": "Hit rate", "direction_accuracy": "Direction accuracy", "win_rate": "Win rate",
                "samples": "Samples", "notable_hits": "Notable correct calls", "notable_misses": "Notable misses",
                "none": "None", "in_portfolio": "holding",
                "disclaimer": "Research input only — not investment advice. Accuracy numbers are never invented when history is thin.",
            }
        return {
            "title": "每日简报", "portfolio_heading": "持仓要点", "portfolio_empty": "暂无缓存持仓。",
            "portfolio_unavailable": "持仓缓存不可用", "overnight_heading": "隔夜要点",
            "overnight_empty": "暂无新鲜的隔夜告警、事件或分析变化。", "overnight_unavailable": "隔夜要点不可用",
            "event_heading": "近期财报事件复盘", "event_empty": "自选/持仓近期无财报类事件。",
            "event_unavailable": "近期事件上下文不可用", "metrics_label": "关注", "checklist_label": "事后核对",
            "yesterday_heading": "昨日分析回顾", "yesterday_empty": "昨日暂无已存储的分析记录。",
            "watchlist_heading": "今日关注列表", "watchlist_empty": "关注列表为空 — 请配置 STOCK_LIST 以个性化本节。",
            "watchlist_covered": "昨日已有分析", "watchlist_missing": "昨日无分析",
            "accuracy_heading": "历史准确率复盘", "accuracy_insufficient": "历史样本不足",
            "accuracy_unavailable": "准确率数据源不可用", "signals_heading": "决策信号结果",
            "backtest_heading": "回测汇总", "skills_heading": "技能观点表现", "hit_rate": "命中率",
            "direction_accuracy": "方向准确率", "win_rate": "胜率", "samples": "样本数",
            "notable_hits": "值得一提的正确判断", "notable_misses": "值得一提的失误", "none": "无",
            "in_portfolio": "持仓",
            "disclaimer": "仅供研究参考，不构成投资建议。在历史样本不足时，本简报不会编造准确率数字。",
        }

    def _fallback_markdown(self, payload: Mapping[str, Any]) -> str:
        labels = self._labels(str(payload.get("report_language") or "zh"))
        lines = [f"# {labels['title']} · {payload.get('report_date') or ''}", "", f"## {labels['portfolio_heading']}"]
        portfolio = payload.get("portfolio") or {}
        if portfolio.get("status") == "unavailable":
            lines.append(labels["portfolio_unavailable"])
        elif portfolio.get("empty"):
            lines.append(labels["portfolio_empty"])
        else:
            for item in portfolio.get("holdings") or []:
                lines.append(f"- `{item.get('code')}`")
        lines += ["", f"## {labels['overnight_heading']}"]
        overnight = payload.get("overnight_highlights") or {}
        if overnight.get("empty") or overnight.get("status") == "unavailable":
            lines.append(labels["overnight_empty"] if overnight.get("empty") else labels["overnight_unavailable"])
        else:
            for item in overnight.get("items") or []:
                lines.append(f"- **{item.get('name') or item.get('code')}** ({item.get('code')}): {item.get('reason_display') or item.get('reason_code')}")
        lines += ["", f"## {labels['event_heading']}"]
        events = payload.get("event_foresight") or {}
        if events.get("empty") or events.get("status") == "unavailable":
            lines.append(labels["event_empty"] if events.get("empty") else labels["event_unavailable"])
        else:
            for b in events.get("briefs") or []:
                lines.append(f"- **{b.get('stock_name') or b.get('stock_code')}** ({b.get('stock_code')}) · {b.get('event_category')}")
        accuracy = payload.get("accuracy") or {}
        lines += ["", f"## {labels['accuracy_heading']}", str(accuracy.get("honesty_note") or labels["accuracy_insufficient"]), "", f"## {labels['yesterday_heading']}"]
        analyses = list(payload.get("yesterday_analyses") or [])
        if not analyses:
            lines.append(labels["yesterday_empty"])
        else:
            for item in analyses:
                hold = f" · {labels['in_portfolio']}" if item.get("in_portfolio") else ""
                lines.append(f"- **{item.get('name') or item.get('code')}** ({item.get('code')}) {item.get('operation_advice') or ''}{hold}")
        lines += ["", f"## {labels['watchlist_heading']}"]
        watchlist = payload.get("watchlist") or {}
        lines.append(labels["watchlist_empty"] if watchlist.get("empty") else (", ".join(watchlist.get("codes") or []) or labels["none"]))
        lines += ["", f"*{labels['disclaimer']}*", ""]
        return "\n".join(lines)


def build_daily_brief_background_tasks(config: Any, *, config_provider: Callable[[], Any], service: Optional[DailyBriefService] = None) -> List[Dict[str, Any]]:
    view = resolve_daily_brief_config(config)
    if not view.enabled:
        return []
    brief_service = service or DailyBriefService(config_provider=config_provider)

    def daily_brief_task() -> None:
        try:
            result = brief_service.maybe_run(force=False)
        except Exception as exc:  # broad-exception: fallback_recorded - scheduler isolates brief failure
            log_safe_exception(logger, "Daily brief scheduled run failed; other notifications continue", exc,
                               error_code="daily_brief_scheduled_run_failed", level=logging.WARNING)
            return
        if result is None:
            return
        if result.skipped_reason and result.notification_status != "quiet_skipped":
            logger.debug("[DailyBrief] skipped reason=%s", result.skipped_reason)
            return
        logger.info("[DailyBrief] scheduled run complete query_id=%s notify=%s", result.query_id, result.notification_status)

    return [{"task": daily_brief_task, "interval_seconds": DAILY_BRIEF_POLL_INTERVAL_SECONDS, "run_immediately": True, "name": "daily_brief"}]


def _clip(value: Any, max_len: int) -> str:
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max(0, max_len - 1)].rstrip() + "…"


def _finite_float(
    value: Any,
    *,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number):
        return None
    if minimum is not None and number < minimum:
        return None
    if maximum is not None and number > maximum:
        return None
    return number


def _non_negative_int(value: Any) -> Optional[int]:
    number = _finite_float(value, minimum=0)
    if number is None or not number.is_integer():
        return None
    return int(number)


def _bounded_markdown(markdown: str, max_chars: int) -> str:
    text = str(markdown or "")
    if len(text) <= max_chars:
        return text
    marker = "\n\n*[Content truncated to the report length budget.]*\n"
    boundary = max(0, max_chars - len(marker))
    cut = text.rfind("\n", 0, boundary)
    if cut <= 0:
        cut = boundary
    return text[:cut].rstrip() + marker
