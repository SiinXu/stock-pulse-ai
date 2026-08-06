# -*- coding: utf-8 -*-
"""Corporate event alert evaluation and impact-context enrichment (issue #241 V0).

Evaluation reads only managed / cached data (intelligence_items, portfolio
positions without realtime refresh, analysis history). It does not call live
market data providers on the alert hot path.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from data_provider.base import normalize_stock_code
from src.utils.sanitize import log_safe_exception, sanitize_diagnostic_text

logger = logging.getLogger(__name__)

EVENT_ALERT_TYPES = frozenset({"corporate_event"})
CORPORATE_EVENT_CATEGORIES = (
    "earnings",
    "shareholder",
    "mna",
    "regulatory",
    "analyst",
)
CORPORATE_EVENT_CATEGORY_SET = frozenset(CORPORATE_EVENT_CATEGORIES)
CORPORATE_EVENT_DATA_SOURCE = "intelligence_items"
DEFAULT_LOOKBACK_HOURS = 24
MIN_LOOKBACK_HOURS = 1
MAX_LOOKBACK_HOURS = 168
DEFAULT_MIN_ITEMS = 1
MAX_MATCHED_ITEMS_IN_DIAGNOSTICS = 5

_CATEGORY_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "earnings": (
        "earnings", "eps", "revenue", "profit", "guidance",
        "财报", "业绩", "净利润", "营收", "预告", "季报", "年报", "中报",
    ),
    "shareholder": (
        "shareholder", "insider", "buyback", "repurchase", "stake",
        "持股", "股东", "增持", "减持", "回购", "大股东", "股权",
    ),
    "mna": (
        "merger", "acquisition", "acquire", "m&a", "takeover",
        "并购", "收购", "重组", "要约", "分拆",
    ),
    "regulatory": (
        "sec", "regulator", "regulatory", "investigation", "lawsuit", "sanction",
        "监管", "立案", "处罚", "调查", "诉讼", "问询", "证监会",
    ),
    "analyst": (
        "upgrade", "downgrade", "price target", "rating", "analyst",
        "上调", "下调", "目标价", "评级", "买入评级", "卖出评级", "研报",
    ),
}

_CATEGORY_WHY: Dict[str, Dict[str, str]] = {
    "earnings": {
        "zh": "业绩/财报事件可能重定价盈利预期与估值锚点。",
        "en": "Earnings events can reprice profit expectations and valuation anchors.",
    },
    "shareholder": {
        "zh": "股东结构或增减持变化可能影响供给与治理信号。",
        "en": "Shareholder structure or stake changes can signal supply and governance shifts.",
    },
    "mna": {
        "zh": "并购重组事件通常改变公司边界、协同与风险溢价。",
        "en": "M&A events often change corporate perimeter, synergies, and risk premium.",
    },
    "regulatory": {
        "zh": "监管或合规事件可能带来处罚、业务限制或情绪冲击。",
        "en": "Regulatory events may imply penalties, operating limits, or sentiment shocks.",
    },
    "analyst": {
        "zh": "分析师评级/目标价调整可能影响机构关注与短期情绪。",
        "en": "Analyst rating or target changes can move institutional attention and short-term sentiment.",
    },
}


@dataclass
class CorporateEventAlert:
    """Runtime alert for managed corporate-event intelligence matches."""

    stock_code: str
    alert_type: str = "corporate_event"
    parameters: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    target_scope: str = "single_symbol"

    def __post_init__(self) -> None:
        self.stock_code = str(self.stock_code or "").strip()
        self.alert_type = "corporate_event"
        if not isinstance(self.parameters, dict):
            self.parameters = {}
        if not isinstance(self.metadata, dict):
            self.metadata = {}
        if not self.description:
            categories = ",".join(self.parameters.get("event_categories") or list(CORPORATE_EVENT_CATEGORIES))
            self.description = f"{self.stock_code} corporate event ({categories})"


def normalize_corporate_event_parameters(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize and validate corporate_event rule parameters."""
    if not isinstance(parameters, dict):
        raise ValueError("parameters must be an object")

    raw_categories = parameters.get("event_categories")
    if raw_categories is None:
        categories = list(CORPORATE_EVENT_CATEGORIES)
    elif isinstance(raw_categories, str):
        categories = [part.strip().lower() for part in raw_categories.split(",") if part.strip()]
    elif isinstance(raw_categories, list):
        categories = []
        for item in raw_categories:
            text = str(item or "").strip().lower()
            if text:
                categories.append(text)
    else:
        raise ValueError("event_categories must be a list or comma-separated string")

    if not categories:
        raise ValueError("event_categories must not be empty")

    normalized_categories: List[str] = []
    for category in categories:
        if category not in CORPORATE_EVENT_CATEGORY_SET:
            raise ValueError(
                "event_categories only supports: " + ", ".join(CORPORATE_EVENT_CATEGORIES)
            )
        if category not in normalized_categories:
            normalized_categories.append(category)

    lookback_hours = _bounded_int(
        parameters.get("lookback_hours", DEFAULT_LOOKBACK_HOURS),
        field_name="lookback_hours",
        minimum=MIN_LOOKBACK_HOURS,
        maximum=MAX_LOOKBACK_HOURS,
        default=DEFAULT_LOOKBACK_HOURS,
    )
    min_items = _bounded_int(
        parameters.get("min_items", DEFAULT_MIN_ITEMS),
        field_name="min_items",
        minimum=1,
        maximum=50,
        default=DEFAULT_MIN_ITEMS,
    )
    return {
        "event_categories": normalized_categories,
        "lookback_hours": lookback_hours,
        "min_items": min_items,
    }


def make_corporate_event_payload(
    *,
    parent_key: str,
    data: Dict[str, Any],
    effective_target: Optional[str] = None,
    display_target: Optional[str] = None,
) -> Any:
    """Build a RuntimeAlertPayload for a corporate_event symbol target."""
    from src.services.portfolio_alerts import RuntimeAlertPayload

    symbol = str(effective_target or data.get("target") or "").strip()
    display = str(display_target or symbol)
    rule = CorporateEventAlert(
        stock_code=symbol,
        parameters=dict(data.get("parameters") or {}),
        metadata={
            "persisted_rule_id": data.get("id"),
            "target_scope": data.get("target_scope"),
            "parent_target": data.get("target"),
            "effective_target": symbol,
            "display_target": display,
        },
        description=data.get("name") or f"{symbol} corporate_event",
        target_scope=str(data.get("target_scope") or "single_symbol"),
    )
    return RuntimeAlertPayload(
        key=f"{parent_key}|{symbol}" if effective_target else parent_key,
        rule=rule,
        effective_target=symbol,
        display_target=display,
    )


def classify_corporate_event_text(text: str) -> List[str]:
    """Return matching event categories for free-form title/summary text."""
    haystack = str(text or "").strip().lower()
    if not haystack:
        return []
    matched: List[str] = []
    for category in CORPORATE_EVENT_CATEGORIES:
        for keyword in _CATEGORY_KEYWORDS[category]:
            if keyword.lower() in haystack:
                matched.append(category)
                break
    return matched


def evaluate_corporate_event_alert(
    rule: CorporateEventAlert,
    *,
    items: Optional[Sequence[Any]] = None,
    intelligence_repo: Optional[Any] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Evaluate a corporate_event rule against managed intelligence items."""
    parameters = normalize_corporate_event_parameters(rule.parameters or {})
    stock_code = normalize_stock_code(rule.stock_code) if rule.stock_code else ""
    if not stock_code:
        return _result(
            rule,
            triggered=False,
            record_status="skipped",
            status="not_triggered",
            observed_value=None,
            message="No stock code available for corporate event evaluation",
            parameters=parameters,
        )

    try:
        loaded_items = list(items) if items is not None else _load_intelligence_items(
            stock_code=stock_code,
            lookback_hours=int(parameters["lookback_hours"]),
            intelligence_repo=intelligence_repo,
            now=now,
        )
    except Exception as exc:
        return _result(
            rule,
            triggered=False,
            record_status="failed",
            status="evaluation_error",
            observed_value=None,
            message=sanitize_diagnostic_text(str(exc) or "intelligence lookup failed")
            or "intelligence lookup failed",
            parameters=parameters,
        )

    if not loaded_items:
        return _result(
            rule,
            triggered=False,
            record_status="skipped",
            status="not_triggered",
            observed_value=0,
            message=f"No managed intelligence items in last {parameters['lookback_hours']}h for {stock_code}",
            parameters=parameters,
            data_timestamp=None,
        )

    wanted = set(parameters["event_categories"])
    matches: List[Dict[str, Any]] = []
    for item in loaded_items:
        title = str(getattr(item, "title", None) or (item.get("title") if isinstance(item, dict) else "") or "")
        summary = str(
            getattr(item, "summary", None) or (item.get("summary") if isinstance(item, dict) else "") or ""
        )
        categories = [c for c in classify_corporate_event_text(f"{title}\n{summary}") if c in wanted]
        if not categories:
            continue
        published_at = _item_datetime(item, "published_at") or _item_datetime(item, "fetched_at")
        matches.append(
            {
                "item_id": getattr(item, "id", None) if not isinstance(item, dict) else item.get("id"),
                "title": sanitize_diagnostic_text(title) or title[:200],
                "summary": sanitize_diagnostic_text(summary[:300]) if summary else None,
                "url": _safe_url(item),
                "source_name": str(
                    getattr(item, "source_name", None)
                    or (item.get("source_name") if isinstance(item, dict) else "")
                    or getattr(item, "source", None)
                    or (item.get("source") if isinstance(item, dict) else "")
                    or ""
                )[:100]
                or None,
                "categories": categories,
                "published_at": published_at.isoformat() if published_at else None,
            }
        )

    match_count = len(matches)
    primary = matches[0] if matches else None
    data_timestamp = _parse_iso(primary.get("published_at")) if primary else None
    min_items = int(parameters["min_items"])
    if match_count >= min_items and primary is not None:
        category = primary["categories"][0]
        message = (
            f"{stock_code} corporate event ({category}): "
            f"{primary.get('title') or 'managed intelligence match'}"
        )
        event_context = {
            "what_happened": primary.get("title") or message,
            "why_it_matters": why_it_matters(category, report_language="zh"),
            "event_category": category,
            "event_categories": list(primary.get("categories") or []),
            "matched_count": match_count,
            "source_item_id": primary.get("item_id"),
            "source_name": primary.get("source_name"),
            "source_url": primary.get("url"),
            "matched_items": matches[:MAX_MATCHED_ITEMS_IN_DIAGNOSTICS],
        }
        return _result(
            rule,
            triggered=True,
            record_status="triggered",
            status="triggered",
            observed_value=float(match_count),
            message=message,
            parameters=parameters,
            data_timestamp=data_timestamp,
            diagnostics={"event_context": event_context},
        )

    return _result(
        rule,
        triggered=False,
        record_status=None,
        status="not_triggered",
        observed_value=float(match_count),
        message=(
            f"{stock_code} corporate event: {match_count} matching items "
            f"(need {min_items}) in last {parameters['lookback_hours']}h"
        ),
        parameters=parameters,
        data_timestamp=data_timestamp,
        diagnostics={"matched_count": match_count} if match_count else None,
    )


def why_it_matters(category: str, *, report_language: str = "zh") -> str:
    lang = "en" if str(report_language or "").lower().startswith("en") else "zh"
    mapping = _CATEGORY_WHY.get(str(category or "").strip().lower()) or {}
    return mapping.get(lang) or mapping.get("zh") or mapping.get("en") or ""


def build_impact_context(
    *,
    stock_code: str,
    event_context: Optional[Dict[str, Any]] = None,
    config: Optional[Any] = None,
    portfolio_service: Optional[Any] = None,
    analysis_records: Optional[Sequence[Any]] = None,
    report_language: str = "zh",
) -> Dict[str, Any]:
    """Assemble holdings/watchlist impact context from managed data only."""
    symbol = ""
    try:
        symbol = normalize_stock_code(stock_code) if stock_code else ""
    except Exception:
        symbol = str(stock_code or "").strip()

    in_watchlist = False
    watchlist_error: Optional[str] = None
    if config is not None and symbol:
        try:
            symbols = _watchlist_symbols(config)
            in_watchlist = symbol in symbols or str(stock_code).strip() in symbols
        except Exception as exc:
            watchlist_error = sanitize_diagnostic_text(str(exc) or "watchlist lookup failed")
            log_safe_exception(
                logger,
                "Alert impact watchlist lookup failed",
                exc,
                error_code="alert_impact_watchlist_lookup_failed",
                level=logging.DEBUG,
            )

    holding = _portfolio_holding_context(
        symbol=symbol or str(stock_code or "").strip(),
        portfolio_service=portfolio_service,
    )
    related_analysis = _related_analysis_excerpt(analysis_records, report_language=report_language)

    category = None
    what_happened = None
    why = None
    if isinstance(event_context, dict):
        category = event_context.get("event_category")
        what_happened = event_context.get("what_happened")
        why = event_context.get("why_it_matters")
    if not why and category:
        why = why_it_matters(str(category), report_language=report_language)
    if not why and related_analysis:
        why = related_analysis

    affected: Dict[str, Any] = {
        "symbol": symbol or str(stock_code or "").strip() or None,
        "in_watchlist": bool(in_watchlist),
        "in_portfolio": bool(holding.get("in_portfolio")),
        "portfolio_accounts": holding.get("portfolio_accounts") or [],
        "quantity": holding.get("quantity"),
        "weight_pct": holding.get("weight_pct"),
        "market_value_base": holding.get("market_value_base"),
    }
    if watchlist_error:
        affected["watchlist_error"] = watchlist_error
    if holding.get("error"):
        affected["portfolio_error"] = holding.get("error")

    payload: Dict[str, Any] = {
        "degraded": bool(watchlist_error or holding.get("error")),
        "what_happened": what_happened,
        "why_it_matters": why,
        "event_category": category,
        "affected": affected,
        "related_analysis": related_analysis,
    }
    if isinstance(event_context, dict):
        for key in ("matched_count", "source_item_id", "source_name", "source_url", "event_categories"):
            if key in event_context and event_context.get(key) is not None:
                payload[key] = event_context.get(key)
    return payload


def format_impact_context_excerpt(
    impact_context: Any,
    *,
    report_language: str = "zh",
) -> str:
    """Render a low-sensitivity public excerpt for alert notifications."""
    if not isinstance(impact_context, dict) or not impact_context:
        return ""
    lang_en = str(report_language or "").lower().startswith("en")
    lines: List[str] = []
    header = "Impact context" if lang_en else "影响上下文"
    lines.append(f"**{header}**")

    what = impact_context.get("what_happened")
    if what:
        label = "What happened" if lang_en else "发生了什么"
        lines.append(f"- {label}: {_clip(str(what), 160)}")

    why = impact_context.get("why_it_matters")
    if why:
        label = "Why it matters" if lang_en else "为何重要"
        lines.append(f"- {label}: {_clip(str(why), 160)}")

    category = impact_context.get("event_category")
    if category:
        label = "Event type" if lang_en else "事件类型"
        lines.append(f"- {label}: {category}")

    affected = impact_context.get("affected") if isinstance(impact_context.get("affected"), dict) else {}
    bits: List[str] = []
    if affected.get("in_portfolio"):
        weight = affected.get("weight_pct")
        if weight is not None:
            bits.append(
                (f"holding weight ~{float(weight):.1f}%" if lang_en else f"持仓权重约 {float(weight):.1f}%")
            )
        else:
            bits.append("in holdings" if lang_en else "在持仓中")
    if affected.get("in_watchlist"):
        bits.append("on watchlist" if lang_en else "在自选中")
    if not bits:
        bits.append("not in holdings/watchlist" if lang_en else "不在持仓/自选中")
    label = "Affected" if lang_en else "影响范围"
    lines.append(f"- {label}: {', '.join(bits)}")

    related = impact_context.get("related_analysis")
    if related:
        label = "Related analysis" if lang_en else "相关分析"
        lines.append(f"- {label}: {_clip(str(related), 120)}")

    if impact_context.get("degraded"):
        lines.append(
            "- note: partial context (managed data incomplete)"
            if lang_en
            else "- 说明：上下文部分降级（托管数据不完整）"
        )
    return "\n".join(lines)


def _load_intelligence_items(
    *,
    stock_code: str,
    lookback_hours: int,
    intelligence_repo: Optional[Any],
    now: Optional[datetime],
) -> List[Any]:
    repo = intelligence_repo
    if repo is None:
        from src.repositories.intelligence_repo import IntelligenceRepository
        from src.storage import DatabaseManager

        repo = IntelligenceRepository(DatabaseManager.get_instance())

    lookback_days = max(1, int((max(1, lookback_hours) + 23) // 24))
    rows, _total = repo.list_items(
        scope_type="symbol",
        scope_value=stock_code,
        days=lookback_days,
        page=1,
        page_size=50,
    )
    cutoff = (now or datetime.now()) - timedelta(hours=max(1, int(lookback_hours)))
    filtered: List[Any] = []
    for row in rows:
        stamp = _item_datetime(row, "published_at") or _item_datetime(row, "fetched_at")
        if stamp is None or stamp >= cutoff:
            filtered.append(row)
    return filtered


def _watchlist_symbols(config: Any) -> Set[str]:
    refresh = getattr(config, "refresh_stock_list", None)
    if callable(refresh):
        try:
            refresh()
        except Exception as exc:
            log_safe_exception(
                logger,
                "Alert impact watchlist refresh failed",
                exc,
                error_code="alert_impact_watchlist_refresh_failed",
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
        except Exception:
            continue
    return symbols


def _portfolio_holding_context(
    *,
    symbol: str,
    portfolio_service: Optional[Any],
) -> Dict[str, Any]:
    if not symbol:
        return {"in_portfolio": False}
    try:
        service = portfolio_service
        if service is None:
            from src.services.portfolio_service import PortfolioService

            service = PortfolioService()
        snapshot = service.get_portfolio_snapshot(
            account_id=None,
            cost_method="fifo",
            include_realtime=False,
        )
    except Exception as exc:
        log_safe_exception(
            logger,
            "Alert impact portfolio lookup failed",
            exc,
            error_code="alert_impact_portfolio_lookup_failed",
            level=logging.DEBUG,
        )
        return {
            "in_portfolio": False,
            "error": sanitize_diagnostic_text(str(exc) or "portfolio lookup failed"),
        }

    accounts: List[str] = []
    total_qty = 0.0
    total_mv = 0.0
    total_equity = 0.0
    for account in snapshot.get("accounts", []) or []:
        account_id = account.get("id") or account.get("account_id") or account.get("name")
        equity = _safe_float(account.get("total_equity") or account.get("equity"))
        if equity is not None:
            total_equity += max(0.0, equity)
        for position in account.get("positions", []) or []:
            pos_symbol = str(position.get("symbol") or "").strip()
            try:
                pos_norm = normalize_stock_code(pos_symbol) if pos_symbol else ""
            except Exception:
                pos_norm = pos_symbol
            if pos_norm != symbol and pos_symbol != symbol:
                continue
            qty = _safe_float(position.get("quantity")) or 0.0
            if qty <= 0:
                continue
            total_qty += qty
            mv = _safe_float(position.get("market_value_base") or position.get("market_value"))
            if mv is not None:
                total_mv += mv
            if account_id is not None:
                accounts.append(str(account_id))
    weight_pct = None
    if total_mv > 0 and total_equity > 0:
        weight_pct = round(100.0 * total_mv / total_equity, 2)
    return {
        "in_portfolio": total_qty > 0,
        "portfolio_accounts": sorted(set(accounts)),
        "quantity": total_qty if total_qty > 0 else None,
        "weight_pct": weight_pct,
        "market_value_base": total_mv if total_mv > 0 else None,
    }


def _related_analysis_excerpt(
    analysis_records: Optional[Sequence[Any]],
    *,
    report_language: str,
) -> Optional[str]:
    if not analysis_records:
        return None
    _ = report_language
    record = analysis_records[0]
    for attr in ("summary", "query", "code", "report_type"):
        value = getattr(record, attr, None) if not isinstance(record, dict) else record.get(attr)
        if value:
            text = sanitize_diagnostic_text(str(value)) or str(value)
            return _clip(text, 120)
    return None


def _result(
    rule: CorporateEventAlert,
    *,
    triggered: bool,
    record_status: Optional[str],
    status: str,
    observed_value: Any,
    message: str,
    parameters: Dict[str, Any],
    data_timestamp: Optional[datetime] = None,
    diagnostics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload = {
        "rule_id": int((rule.metadata or {}).get("persisted_rule_id", 0) or 0),
        "status": status,
        "record_status": record_status,
        "triggered": bool(triggered),
        "observed_value": observed_value,
        "threshold": float(parameters.get("min_items") or DEFAULT_MIN_ITEMS),
        "data_source": CORPORATE_EVENT_DATA_SOURCE,
        "data_timestamp": data_timestamp,
        "reason": message,
        "message": message,
        "alert_type": "corporate_event",
    }
    if diagnostics:
        payload["diagnostics"] = diagnostics
    return payload


def _bounded_int(
    value: Any,
    *,
    field_name: str,
    minimum: int,
    maximum: int,
    default: int,
) -> int:
    if value is None or value == "":
        return default
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid {field_name}: {value}") from exc
    if number < minimum or number > maximum:
        raise ValueError(f"{field_name} must be between {minimum} and {maximum}")
    return number


def _item_datetime(item: Any, field_name: str) -> Optional[datetime]:
    raw = getattr(item, field_name, None) if not isinstance(item, dict) else item.get(field_name)
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.replace(tzinfo=None) if raw.tzinfo is not None else raw
    if hasattr(raw, "to_pydatetime"):
        try:
            parsed = raw.to_pydatetime()
            return parsed.replace(tzinfo=None) if parsed.tzinfo is not None else parsed
        except Exception:
            return None
    return _parse_iso(raw)


def _parse_iso(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo is not None else value
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=None) if parsed.tzinfo is not None else parsed
    except ValueError:
        return None


def _safe_url(item: Any) -> Optional[str]:
    raw = getattr(item, "url", None) if not isinstance(item, dict) else item.get("url")
    text = str(raw or "").strip()
    if not text:
        return None
    cleaned = re.sub(r"([?&])(token|key|secret|password|access_token)=[^&]*", r"\1\2=***", text, flags=re.I)
    return cleaned[:500]


def _safe_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clip(text: str, limit: int) -> str:
    value = str(text or "").strip()
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)].rstrip() + "…"
