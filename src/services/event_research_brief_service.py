# -*- coding: utf-8 -*-
"""Event-driven research briefs for key calendar events (Issue #1131)."""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Set

from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

EVENT_RESEARCH_BRIEF_REPORT_TYPE = "event_research_brief"
EVENT_RESEARCH_BRIEF_PACK_VERSION = "event_research_brief/1.0"
EVENT_RESEARCH_BRIEF_POLL_INTERVAL_SECONDS = 120
PRIMARY_EVENT_CATEGORY = "earnings"
SUPPORTED_EVENT_CATEGORIES = frozenset({PRIMARY_EVENT_CATEGORY})
DEFAULT_LOOKBACK_HOURS = 48
MAX_LOOKBACK_HOURS = 168
MAX_BRIEFS_PER_RUN = 10
MAX_UNIVERSE = 200
MAX_DETAIL_LEN = 200

_EARNINGS_TEMPLATE = {
    "metrics_to_watch": [
        {"id": "revenue_yoy", "label_en": "Revenue growth (YoY)", "label_zh": "营收同比增速",
         "why_en": "Anchors top-line momentum versus prior-year base.", "why_zh": "锚定相对去年同期的收入动能。"},
        {"id": "eps", "label_en": "EPS / net profit", "label_zh": "EPS / 净利润",
         "why_en": "Primary earnings surprise input for re-rating.", "why_zh": "业绩超预期/不及预期的核心输入。"},
        {"id": "guidance", "label_en": "Forward guidance / outlook", "label_zh": "前瞻指引 / 业绩展望",
         "why_en": "Often moves multiples more than the print itself.", "why_zh": "往往比当期业绩更能推动估值倍数变化。"},
        {"id": "margins", "label_en": "Gross / operating margin trend", "label_zh": "毛利率 / 营业利润率趋势",
         "why_en": "Separates volume-led vs quality-led beats.", "why_zh": "区分量增驱动与质量驱动的超预期。"},
    ],
    "surprise_criteria": {
        "en": "Treat as a material surprise when reported EPS or revenue differs meaningfully from stored consensus/estimate, or guidance is raised/cut. Do not invent consensus numbers.",
        "zh": "当已落库一致预期与实际 EPS/营收明确偏差，或指引上调/下调时，视为实质性超预期/不及预期。不得编造一致预期。",
    },
    "linked_hypotheses": [
        {"id": "beat_and_raise", "label_en": "Beat-and-raise → multiple expansion", "label_zh": "超预期并上调指引 → 估值扩张"},
        {"id": "miss_with_soft_guide", "label_en": "Miss + soft guide → de-rating", "label_zh": "不及预期且指引疲弱 → 估值收缩"},
        {"id": "in_line_with_quality", "label_en": "In-line with quality → limited move", "label_zh": "符合预期但质量改善 → 波动有限"},
    ],
    "post_event_checklist": [
        {"id": "verify_print", "label_en": "Verify revenue/EPS vs stored estimate", "label_zh": "核对营收/EPS 与已存预期"},
        {"id": "read_guidance", "label_en": "Record guidance direction", "label_zh": "记录指引方向"},
        {"id": "update_thesis", "label_en": "Update or retire linked hypothesis", "label_zh": "更新或废弃关联假设"},
        {"id": "check_reaction", "label_en": "Note post-print price/volume reaction", "label_zh": "记录业绩后量价反应"},
        {"id": "follow_up", "label_en": "Schedule follow-up if thesis changed", "label_zh": "论点变化则安排后续分析"},
    ],
}


@dataclass(frozen=True)
class EventResearchBriefConfigView:
    enabled: bool = False
    notify: bool = True
    persist_history: bool = True
    save_report_file: bool = True
    lookback_hours: int = DEFAULT_LOOKBACK_HOURS
    timezone_name: str = "Asia/Shanghai"
    categories: tuple = (PRIMARY_EVENT_CATEGORY,)


@dataclass
class EventResearchBriefBuildResult:
    briefs: List[Dict[str, Any]] = field(default_factory=list)
    markdown_by_code: Dict[str, str] = field(default_factory=dict)
    query_id: str = ""
    notification_status: str = "not_requested"
    notification_ok: bool = False
    skipped_reason: Optional[str] = None
    errors: List[str] = field(default_factory=list)
    history_ids: List[int] = field(default_factory=list)


def resolve_event_research_brief_config(config: Any = None) -> EventResearchBriefConfigView:
    if config is None:
        try:
            from src.application_services import get_application_services
            config = get_application_services().config
        except Exception as exc:  # broad-exception: fallback_recorded
            log_safe_exception(logger, "Event research brief config load failed", exc,
                               error_code="event_research_brief_config_failed", level=logging.WARNING)
            config = None
    try:
        lookback = int(getattr(config, "event_research_brief_lookback_hours", DEFAULT_LOOKBACK_HOURS) or DEFAULT_LOOKBACK_HOURS)
    except (TypeError, ValueError):
        lookback = DEFAULT_LOOKBACK_HOURS
    lookback = max(1, min(lookback, MAX_LOOKBACK_HOURS))
    timezone_name = str(
        getattr(config, "event_research_brief_timezone", None)
        or getattr(config, "daily_brief_timezone", None)
        or "Asia/Shanghai"
    ).strip() or "Asia/Shanghai"
    raw = getattr(config, "event_research_brief_categories", None)
    cats: List[str] = []
    if isinstance(raw, str) and raw.strip():
        cats = [p.strip().lower() for p in raw.split(",") if p.strip()]
    elif isinstance(raw, (list, tuple)):
        cats = [str(p).strip().lower() for p in raw if str(p).strip()]
    cats = [c for c in (cats or [PRIMARY_EVENT_CATEGORY]) if c in SUPPORTED_EVENT_CATEGORIES] or [PRIMARY_EVENT_CATEGORY]
    return EventResearchBriefConfigView(
        enabled=bool(getattr(config, "event_research_brief_enabled", False)),
        notify=bool(getattr(config, "event_research_brief_notify", True)),
        persist_history=bool(getattr(config, "event_research_brief_persist_history", True)),
        save_report_file=bool(getattr(config, "event_research_brief_save_report_file", True)),
        lookback_hours=lookback, timezone_name=timezone_name, categories=tuple(cats),
    )


def build_earnings_event_brief(*, stock_code: str, stock_name: Optional[str] = None,
    event_context: Optional[Mapping[str, Any]] = None, trigger_id: Optional[int] = None,
    observed_at: Optional[str] = None, on_watchlist: bool = False, in_portfolio: bool = False,
    report_language: str = "zh", query_id: Optional[str] = None) -> Dict[str, Any]:
    code = str(stock_code or "").strip().upper()
    lang = "en" if str(report_language or "").lower().startswith("en") else "zh"
    ctx = dict(event_context or {})
    category = str(ctx.get("event_category") or PRIMARY_EVENT_CATEGORY).strip().lower()
    if category not in SUPPORTED_EVENT_CATEGORIES:
        category = PRIMARY_EVENT_CATEGORY
    metrics = [{"id": i["id"], "label": i["label_en"] if lang == "en" else i["label_zh"],
                "why": i["why_en"] if lang == "en" else i["why_zh"]} for i in _EARNINGS_TEMPLATE["metrics_to_watch"]]
    hypotheses = [{"id": i["id"], "label": i["label_en"] if lang == "en" else i["label_zh"]}
                  for i in _EARNINGS_TEMPLATE["linked_hypotheses"]]
    checklist = [{"id": i["id"], "label": i["label_en"] if lang == "en" else i["label_zh"], "status": "pending"}
                 for i in _EARNINGS_TEMPLATE["post_event_checklist"]]
    what = _clip(ctx.get("what_happened") or ctx.get("title") or "", MAX_DETAIL_LEN)
    why = _clip(ctx.get("why_it_matters") or "", MAX_DETAIL_LEN)
    return {
        "pack_version": EVENT_RESEARCH_BRIEF_PACK_VERSION,
        "query_id": query_id or f"event_brief_{code.lower()}_{uuid.uuid4().hex[:10]}",
        "event_type": "corporate_event", "event_category": category,
        "stock_code": code, "stock_name": str(stock_name or code),
        "trigger_id": trigger_id, "observed_at": observed_at,
        "on_watchlist": bool(on_watchlist), "in_portfolio": bool(in_portfolio),
        "phase": "pre_or_peri_event", "what_happened": what or None, "why_it_matters": why or None,
        "metrics_to_watch": metrics,
        "surprise_criteria": _EARNINGS_TEMPLATE["surprise_criteria"]["en" if lang == "en" else "zh"],
        "linked_hypotheses": hypotheses, "post_event_checklist": checklist,
        "verify_hook": {"kind": "post_event_checklist", "items": [i["id"] for i in checklist],
                        "note": "Human verification hooks; consensus is never fabricated." if lang == "en"
                        else "人工核对挂钩；不会编造一致预期。"},
        "source": "corporate_event_triggers",
        "honesty": {"fabricated_consensus": False,
                    "note": "Template only; consensus never invented." if lang == "en"
                    else "仅模板；不编造一致预期。"},
        "report_language": lang,
    }


class EventResearchBriefService:
    def __init__(self, *, alert_repository: Any = None, portfolio_repository: Any = None,
                 notifier: Any = None, config_provider: Optional[Callable[[], Any]] = None,
                 clock: Optional[Callable[[], datetime]] = None) -> None:
        self._alert_repository = alert_repository
        self._portfolio_repository = portfolio_repository
        self._notifier = notifier
        self._config_provider = config_provider
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._run_lock = threading.Lock()
        self._seen_trigger_ids: Set[int] = set()

    def _config(self) -> Any:
        if self._config_provider is not None:
            return self._config_provider()
        from src.application_services import get_application_services
        return get_application_services().config

    @property
    def alert_repository(self) -> Any:
        if self._alert_repository is None:
            from src.repositories.alert_repo import AlertRepository
            self._alert_repository = AlertRepository()
        return self._alert_repository

    @property
    def portfolio_repository(self) -> Any:
        if self._portfolio_repository is None:
            try:
                from src.repositories.portfolio_repo import PortfolioRepository
                self._portfolio_repository = PortfolioRepository()
            except Exception as exc:  # broad-exception: fallback_recorded
                log_safe_exception(logger, "portfolio unavailable", exc,
                                   error_code="event_research_brief_portfolio_unavailable", level=logging.WARNING)
                self._portfolio_repository = False
        return self._portfolio_repository if self._portfolio_repository is not False else None

    @property
    def notifier(self) -> Any:
        if self._notifier is None:
            from src.notification import NotificationService
            self._notifier = NotificationService()
        return self._notifier

    def build_briefs_for_universe(self, *, codes: Optional[Sequence[str]] = None, config: Any = None,
                                  lookback_hours: Optional[int] = None,
                                  max_briefs: int = MAX_BRIEFS_PER_RUN) -> List[Dict[str, Any]]:
        runtime = config if config is not None else self._config()
        view = resolve_event_research_brief_config(runtime)
        hours = max(1, min(int(lookback_hours if lookback_hours is not None else view.lookback_hours), MAX_LOOKBACK_HOURS))
        lang = str(getattr(runtime, "report_language", "zh") or "zh")
        universe = self._resolve_universe(runtime, codes=codes)
        if not universe:
            return []
        portfolio_codes = self._portfolio_codes()
        watchlist_codes = self._watchlist_codes(runtime)
        since = self._clock() - timedelta(hours=hours)
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)
        try:
            from src.services.stock_code_utils import build_daily_code_candidates
            aliases = sorted({a for c in universe for a in build_daily_code_candidates(c)})
        except Exception as exc:  # broad-exception: fallback_recorded
            log_safe_exception(logger, "alias expansion failed", exc,
                               error_code="event_research_brief_alias_failed", level=logging.WARNING)
            aliases = sorted(universe)
        try:
            rows = self.alert_repository.list_recent_triggered_for_targets(
                targets=aliases, triggered_since=since, per_target_limit=2)
        except Exception as exc:  # broad-exception: fallback_recorded
            log_safe_exception(logger, "trigger load failed", exc,
                               error_code="event_research_brief_triggers_failed", level=logging.WARNING)
            return []
        ranked, seen = [], set()
        for row in rows or []:
            brief = self._brief_from_row(row, lang=lang, watchlist_codes=watchlist_codes,
                                         portfolio_codes=portfolio_codes, allowed=set(view.categories))
            if not brief:
                continue
            code = brief["stock_code"]
            if code in seen:
                continue
            seen.add(code)
            pri = 0 if brief.get("in_portfolio") else 1 if brief.get("on_watchlist") else 2
            ranked.append((pri, brief))
        out = [b for _, b in sorted(ranked, key=lambda x: (x[0], x[1]["stock_code"]))]
        return out[: max(1, min(int(max_briefs), MAX_BRIEFS_PER_RUN))]

    def render_markdown(self, brief: Mapping[str, Any]) -> str:
        try:
            from jinja2 import Environment, FileSystemLoader, select_autoescape
            td = _templates_dir()
            if (td / "event_research_brief.j2").exists():
                env = Environment(loader=FileSystemLoader(str(td)),
                                  autoescape=select_autoescape(enabled_extensions=()),
                                  trim_blocks=True, lstrip_blocks=True)
                labels = self._labels(str(brief.get("report_language") or "zh"))
                return str(env.get_template("event_research_brief.j2").render(brief=brief, labels=labels)).strip() + "\n"
        except Exception as exc:  # broad-exception: fallback_recorded
            log_safe_exception(logger, "template render failed", exc,
                               error_code="event_research_brief_template_failed", level=logging.WARNING)
        return self._fallback_markdown(brief)

    def maybe_run(self, *, force: bool = False) -> Optional[EventResearchBriefBuildResult]:
        if not resolve_event_research_brief_config(self._config()).enabled and not force:
            return None
        return self.run(force=force)

    def run(self, *, force: bool = False) -> EventResearchBriefBuildResult:
        with self._run_lock:
            config = self._config()
            view = resolve_event_research_brief_config(config)
            if not view.enabled and not force:
                return EventResearchBriefBuildResult(skipped_reason="disabled")
            qid = f"event_research_brief_{self._clock().strftime('%Y%m%d')}_{uuid.uuid4().hex[:10]}"
            briefs = self.build_briefs_for_universe(config=config)
            fresh = [b for b in briefs if not (isinstance(b.get("trigger_id"), int) and b["trigger_id"] in self._seen_trigger_ids)]
            if not fresh:
                return EventResearchBriefBuildResult(query_id=qid, skipped_reason="no_fresh_events")
            result = EventResearchBriefBuildResult(query_id=qid, briefs=fresh)
            parts = []
            for brief in fresh:
                md = self.render_markdown(brief)
                code = brief["stock_code"]
                result.markdown_by_code[code] = md
                parts.append(md)
                if isinstance(brief.get("trigger_id"), int):
                    self._seen_trigger_ids.add(brief["trigger_id"])
                if view.persist_history and md:
                    hid = self._persist(md, brief, f"{qid}_{code.lower()}")
                    if hid:
                        result.history_ids.append(hid)
                    else:
                        result.errors.append(f"persist_failed:{code}")
                if view.save_report_file and md:
                    try:
                        self.notifier.save_report_to_file(md, f"event_research_brief_{code}_{self._clock().strftime('%Y%m%d')}.md")
                    except Exception as exc:  # broad-exception: fallback_recorded
                        log_safe_exception(logger, "save failed", exc,
                                           error_code="event_research_brief_save_failed", level=logging.WARNING)
                        result.errors.append(f"save_failed:{code}")
            combined = "\n---\n".join(parts).strip()
            if view.notify and combined:
                result.notification_status, result.notification_ok = self._send(combined)
            elif not view.notify:
                result.notification_status = "not_requested"
            return result

    def _brief_from_row(self, row, *, lang, watchlist_codes, portfolio_codes, allowed):
        try:
            from src.services.stock_code_utils import canonicalize_analysis_stock_code
            code = canonicalize_analysis_stock_code(str(getattr(row, "target", None) or "").strip())
        except Exception:
            code = str(getattr(row, "target", None) or "").strip().upper() or None
        if not code:
            return None
        diagnostics = getattr(row, "diagnostics", None) or {}
        if not isinstance(diagnostics, Mapping):
            diagnostics = {}
        ctx = diagnostics.get("event_context") if isinstance(diagnostics.get("event_context"), Mapping) else {}
        if not isinstance(ctx, Mapping):
            ctx = {}
        category = str(ctx.get("event_category") or (ctx.get("event_categories") or [None])[0] or "").strip().lower()
        cats = [str(c).strip().lower() for c in (ctx.get("event_categories") or []) if str(c).strip()]
        if category and category not in cats:
            cats = [category] + cats
        if not any(c in allowed for c in (cats or [category])):
            msg = str(getattr(row, "message", None) or "")
            if PRIMARY_EVENT_CATEGORY not in allowed or not _looks_like_earnings(msg):
                return None
            category = PRIMARY_EVENT_CATEGORY
            ctx = dict(ctx)
            ctx.setdefault("event_category", category)
            ctx.setdefault("what_happened", msg)
        observed = getattr(row, "triggered_at", None)
        observed_at = None
        if isinstance(observed, datetime):
            if observed.tzinfo is None:
                observed = observed.replace(tzinfo=timezone.utc)
            observed_at = observed.isoformat()
        try:
            tid = int(getattr(row, "id")) if getattr(row, "id", None) is not None else None
        except (TypeError, ValueError):
            tid = None
        return build_earnings_event_brief(
            stock_code=code, stock_name=code, event_context=ctx, trigger_id=tid,
            observed_at=observed_at, on_watchlist=code in watchlist_codes,
            in_portfolio=code in portfolio_codes, report_language=lang)

    def _resolve_universe(self, config, *, codes):
        raw = list(codes) if codes is not None else list(self._watchlist_codes(config)) + list(self._portfolio_codes())
        out = set()
        for item in raw:
            c = str(item or "").strip().upper()
            if c:
                out.add(c)
            if len(out) >= MAX_UNIVERSE:
                break
        return out

    def _watchlist_codes(self, config) -> Set[str]:
        raw = getattr(config, "stock_list", None) or []
        if isinstance(raw, str):
            try:
                from src.utils.stock_list import split_stock_list
                raw = split_stock_list(raw)
            except Exception:
                raw = []
        return {str(c).strip().upper() for c in raw if str(c or "").strip()}

    def _portfolio_codes(self) -> Set[str]:
        repo = self.portfolio_repository
        if repo is None:
            return set()
        try:
            rows = repo.list_cached_positions(account_id=None, cost_method="fifo")
        except Exception as exc:  # broad-exception: fallback_recorded
            log_safe_exception(logger, "portfolio read failed", exc,
                               error_code="event_research_brief_portfolio_read_failed", level=logging.WARNING)
            return set()
        return {str(r.get("symbol") or "").strip().upper()
                for r in (rows or []) if isinstance(r, Mapping) and r.get("symbol")}

    def _persist(self, markdown, brief, query_id) -> int:
        try:
            from src.analyzer import AnalysisResult
            from src.storage import DatabaseManager
            lang = str(brief.get("report_language") or "zh")
            code = str(brief.get("stock_code") or "EVENT_BRIEF")
            result = AnalysisResult(
                code=code,
                name=f"Event brief · {code}" if lang == "en" else f"事件研究简报 · {code}",
                sentiment_score=50,
                trend_prediction="Event research brief" if lang == "en" else "事件研究简报",
                operation_advice="View event brief" if lang == "en" else "查看事件简报",
                analysis_summary=_clip(brief.get("what_happened") or brief.get("surprise_criteria"), 400),
                report_language=lang, news_summary=markdown, raw_response=markdown,
                data_sources="event_research_brief",
            )
            return int(DatabaseManager.get_instance().save_analysis_history(
                result=result, query_id=query_id, report_type=EVENT_RESEARCH_BRIEF_REPORT_TYPE,
                news_content=markdown,
                context_snapshot={
                    "report_kind": EVENT_RESEARCH_BRIEF_REPORT_TYPE,
                    "pack_version": EVENT_RESEARCH_BRIEF_PACK_VERSION,
                    "event_category": brief.get("event_category"),
                    "trigger_id": brief.get("trigger_id"),
                    "verify_hook": brief.get("verify_hook"),
                },
                save_snapshot=True,
            ) or 0)
        except Exception as exc:  # broad-exception: fallback_recorded
            log_safe_exception(logger, "history persist failed", exc,
                               error_code="event_research_brief_history_failed", level=logging.WARNING)
            return 0

    def _send(self, markdown: str):
        try:
            if not self.notifier.is_available():
                return "not_configured", False
            ok = bool(self.notifier.send(markdown, email_send_to_all=True, route_type="report"))
            return ("ok" if ok else "degraded"), ok
        except Exception as exc:  # broad-exception: fallback_recorded
            log_safe_exception(logger, "notify failed", exc,
                               error_code="event_research_brief_notification_failed", level=logging.WARNING)
            return "failed", False

    @staticmethod
    def _labels(lang: str) -> Dict[str, str]:
        if str(lang or "").lower().startswith("en"):
            return {"title": "Event Research Brief", "metrics_heading": "Metrics to watch",
                    "surprise_heading": "What counts as a surprise", "hypotheses_heading": "Linked hypotheses",
                    "checklist_heading": "Post-event verification checklist", "context_heading": "Event context",
                    "portfolio_flag": "in portfolio", "watchlist_flag": "on watchlist",
                    "disclaimer": "Research only. Consensus is never fabricated."}
        return {"title": "事件研究简报", "metrics_heading": "关注指标", "surprise_heading": "何谓超预期/不及预期",
                "hypotheses_heading": "关联假设", "checklist_heading": "事后核对清单", "context_heading": "事件上下文",
                "portfolio_flag": "持仓", "watchlist_flag": "自选",
                "disclaimer": "仅供研究参考。不会编造一致预期。"}

    def _fallback_markdown(self, brief: Mapping[str, Any]) -> str:
        labels = self._labels(str(brief.get("report_language") or "zh"))
        code = brief.get("stock_code") or ""
        lines = [f"# {labels['title']} · {brief.get('stock_name') or code} ({code})", "",
                 f"## {labels['context_heading']}"]
        if brief.get("what_happened"):
            lines.append(str(brief["what_happened"]))
        lines += ["", f"## {labels['metrics_heading']}"]
        for m in brief.get("metrics_to_watch") or []:
            lines.append(f"- **{m.get('label')}**: {m.get('why')}")
        lines += ["", f"## {labels['surprise_heading']}", str(brief.get("surprise_criteria") or "")]
        lines += ["", f"## {labels['checklist_heading']}"]
        for item in brief.get("post_event_checklist") or []:
            lines.append(f"- [ ] {item.get('label')}")
        lines += ["", f"*{labels['disclaimer']}*", ""]
        return "\n".join(lines)


def build_event_research_brief_background_tasks(config, *, config_provider, service=None):
    if not resolve_event_research_brief_config(config).enabled:
        return []
    svc = service or EventResearchBriefService(config_provider=config_provider)

    def task():
        try:
            result = svc.maybe_run(force=False)
        except Exception as exc:  # broad-exception: fallback_recorded
            log_safe_exception(logger, "scheduled run failed", exc,
                               error_code="event_research_brief_scheduled_run_failed", level=logging.WARNING)
            return
        if result is None or result.skipped_reason:
            return
        logger.info("[EventResearchBrief] complete count=%s notify=%s", len(result.briefs), result.notification_status)

    return [{"task": task, "interval_seconds": EVENT_RESEARCH_BRIEF_POLL_INTERVAL_SECONDS,
             "run_immediately": True, "name": "event_research_brief"}]


def _templates_dir() -> Path:
    base = Path(__file__).resolve().parent.parent.parent
    try:
        from src.application_services import get_application_services
        configured = Path(getattr(get_application_services().config, "report_templates_dir", "templates") or "templates")
    except Exception:
        configured = Path("templates")
    return configured if configured.is_absolute() else base / configured


def _looks_like_earnings(text: str) -> bool:
    t = str(text or "").lower()
    return any(k in t for k in ("earnings", "eps", "revenue", "guidance", "财报", "业绩", "净利润", "营收", "季报", "年报", "中报", "预告"))


def _clip(value: Any, max_len: int) -> str:
    text = str(value or "").strip()
    return text if len(text) <= max_len else text[: max(0, max_len - 1)].rstrip() + "…"
