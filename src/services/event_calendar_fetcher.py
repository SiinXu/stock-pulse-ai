# -*- coding: utf-8 -*-
"""Independent event-calendar data fetchers (issue #153 / T21).

Intentionally **not** wired into ``data_provider`` capability tables
(``base.py`` / ``plugin_registry.py``). Fetch paths are opt-in and only
run when ``EVENT_CALENDAR_ENABLED=true``.

Coverage (see docs/event-calendar.md):
- A-share: earnings appointment (yysj), dividend/ex-rights (fhps), unlock queue
- US / HK / macro / index rebalance: not covered by default live sources in V0
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Any, Callable, Dict, List, Optional, Sequence, Set

from data_provider.base import normalize_stock_code
from src.services.event_calendar_models import CalendarEvent
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

_CN_CODE_RE = re.compile(r"^\d{6}$")
_QUARTER_ENDS = ((3, 31), (6, 30), (9, 30), (12, 31))


def _now() -> datetime:
    return datetime.now()


def _parse_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "nat", "-"}:
        return None
    text = text.replace("/", "-").replace(".", "-")
    if re.fullmatch(r"\d{8}", text):
        text = f"{text[0:4]}-{text[4:6]}-{text[6:8]}"
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _row_get(row: Any, *keys: str) -> Any:
    if row is None:
        return None
    if isinstance(row, dict):
        for key in keys:
            if key in row and row[key] is not None:
                return row[key]
        lower_map = {str(k).lower(): v for k, v in row.items()}
        for key in keys:
            if key.lower() in lower_map and lower_map[key.lower()] is not None:
                return lower_map[key.lower()]
        return None
    for key in keys:
        if hasattr(row, key):
            value = getattr(row, key)
            if value is not None:
                return value
    return None


def _is_cn_a_share(symbol: str) -> bool:
    raw = str(symbol or "").strip().upper()
    if not raw:
        return False
    digits = re.sub(r"^(SH|SZ|BJ)", "", raw)
    digits = digits.split(".")[0]
    return bool(_CN_CODE_RE.match(digits))


def _cn_digits(symbol: str) -> str:
    raw = str(symbol or "").strip().upper()
    digits = re.sub(r"^(SH|SZ|BJ)", "", raw)
    digits = digits.split(".")[0]
    return digits if _CN_CODE_RE.match(digits) else ""


def _report_period_candidates(today: date) -> List[str]:
    periods: List[str] = []
    year = today.year
    for y in (year - 1, year, year + 1):
        for month, day in _QUARTER_ENDS:
            periods.append(f"{y}{month:02d}{day:02d}")
    today_key = today.isoformat().replace("-", "")
    ranked = sorted(periods, key=lambda p: abs(int(p) - int(today_key)))
    selected: List[str] = []
    for period in ranked:
        if period not in selected:
            selected.append(period)
        if len(selected) >= 6:
            break
    return selected


def _dataframe_to_records(frame: Any) -> List[Dict[str, Any]]:
    if frame is None:
        return []
    to_dict = getattr(frame, "to_dict", None)
    if callable(to_dict):
        try:
            records = to_dict(orient="records")
            if isinstance(records, list):
                return [dict(item) for item in records if isinstance(item, dict)]
        except Exception as exc:  # broad-exception: fallback_recorded - isolate provider frame shape drift
            log_safe_exception(
                logger,
                "Event calendar frame to_dict failed",
                exc,
                error_code="event_calendar_frame_to_dict_failed",
                level=logging.DEBUG,
            )
    if isinstance(frame, list):
        return [dict(item) for item in frame if isinstance(item, dict)]
    return []


class EventCalendarFetcher:
    """Pull upcoming corporate events for a bounded symbol set."""

    def __init__(
        self,
        *,
        yysj_loader: Optional[Callable[..., Any]] = None,
        fhps_loader: Optional[Callable[..., Any]] = None,
        unlock_loader: Optional[Callable[..., Any]] = None,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self._yysj_loader = yysj_loader
        self._fhps_loader = fhps_loader
        self._unlock_loader = unlock_loader
        self._clock = clock or _now

    def fetch_events(
        self,
        symbols: Sequence[str],
        *,
        date_from: date,
        date_to: date,
        event_types: Sequence[str],
    ) -> Dict[str, Any]:
        wanted = {str(t).strip().lower() for t in event_types}
        symbol_set = self._normalize_symbol_set(symbols)
        fetched_at = self._clock()
        events: List[CalendarEvent] = []
        errors: List[str] = []
        sources_attempted: List[str] = []
        coverage_notes: List[str] = []

        cn_symbols = sorted(
            {
                _cn_digits(sym) or re.sub(r"[^0-9]", "", sym)
                for sym in symbol_set
                if _is_cn_a_share(sym)
            }
        )
        cn_symbols = [s for s in cn_symbols if _CN_CODE_RE.match(s)]
        non_cn = sorted(sym for sym in symbol_set if not _is_cn_a_share(sym))
        if non_cn:
            coverage_notes.append(
                "US/HK and other non-A-share symbols have no live calendar "
                "source in V0; they appear only when a future adapter is added."
            )

        if "earnings" in wanted and cn_symbols:
            sources_attempted.append("akshare.stock_yysj_em")
            try:
                events.extend(
                    self._fetch_cn_earnings(
                        cn_symbols,
                        date_from=date_from,
                        date_to=date_to,
                        fetched_at=fetched_at,
                    )
                )
            except Exception as exc:  # broad-exception: fallback_recorded - isolate provider fetch
                errors.append(f"earnings:{type(exc).__name__}")
                log_safe_exception(
                    logger,
                    "Event calendar earnings fetch failed",
                    exc,
                    error_code="event_calendar_earnings_fetch_failed",
                    level=logging.WARNING,
                )

        if "ex_dividend" in wanted and cn_symbols:
            sources_attempted.append("akshare.stock_fhps_em")
            try:
                events.extend(
                    self._fetch_cn_ex_dividend(
                        cn_symbols,
                        date_from=date_from,
                        date_to=date_to,
                        fetched_at=fetched_at,
                    )
                )
            except Exception as exc:  # broad-exception: fallback_recorded - isolate provider fetch
                errors.append(f"ex_dividend:{type(exc).__name__}")
                log_safe_exception(
                    logger,
                    "Event calendar ex-dividend fetch failed",
                    exc,
                    error_code="event_calendar_ex_dividend_fetch_failed",
                    level=logging.WARNING,
                )

        if "unlock" in wanted and cn_symbols:
            sources_attempted.append("akshare.stock_restricted_release_queue_em")
            try:
                events.extend(
                    self._fetch_cn_unlock(
                        cn_symbols,
                        date_from=date_from,
                        date_to=date_to,
                        fetched_at=fetched_at,
                    )
                )
            except Exception as exc:  # broad-exception: fallback_recorded - isolate provider fetch
                errors.append(f"unlock:{type(exc).__name__}")
                log_safe_exception(
                    logger,
                    "Event calendar unlock fetch failed",
                    exc,
                    error_code="event_calendar_unlock_fetch_failed",
                    level=logging.WARNING,
                )

        for kind in ("index_rebalance", "macro"):
            if kind in wanted:
                coverage_notes.append(
                    f"{kind} is modeled but has no live source in V0."
                )

        unique: Dict[str, CalendarEvent] = {}
        for event in events:
            unique.setdefault(event.event_id, event)
        ordered = sorted(
            unique.values(),
            key=lambda e: (e.event_date, e.symbol, e.event_type, e.event_id),
        )
        return {
            "events": ordered,
            "fetched_at": fetched_at,
            "sources_attempted": sources_attempted,
            "errors": errors,
            "coverage_notes": coverage_notes,
            "cn_symbol_count": len(cn_symbols),
            "non_cn_symbol_count": len(non_cn),
        }

    def _normalize_symbol_set(self, symbols: Sequence[str]) -> Set[str]:
        out: Set[str] = set()
        for raw in symbols:
            text = str(raw or "").strip()
            if not text:
                continue
            out.add(text)
            try:
                out.add(normalize_stock_code(text))
            except Exception as exc:  # broad-exception: fallback_recorded - keep raw symbol
                log_safe_exception(
                    logger,
                    "Event calendar symbol normalize failed",
                    exc,
                    error_code="event_calendar_symbol_normalize_failed",
                    level=logging.DEBUG,
                )
        return out

    def _load_yysj(self, period: str) -> Any:
        if self._yysj_loader is not None:
            return self._yysj_loader(period)
        import akshare as ak
        return ak.stock_yysj_em(symbol="沪深A股", date=period)

    def _load_fhps(self, period: str) -> Any:
        if self._fhps_loader is not None:
            return self._fhps_loader(period)
        import akshare as ak
        return ak.stock_fhps_em(date=period)

    def _load_unlock(self, code: str) -> Any:
        if self._unlock_loader is not None:
            return self._unlock_loader(code)
        import akshare as ak
        return ak.stock_restricted_release_queue_em(symbol=code)

    def _fetch_cn_earnings(
        self,
        cn_codes: Sequence[str],
        *,
        date_from: date,
        date_to: date,
        fetched_at: datetime,
    ) -> List[CalendarEvent]:
        wanted = set(cn_codes)
        events: List[CalendarEvent] = []
        for period in _report_period_candidates(date_from):
            frame = self._load_yysj(period)
            for row in _dataframe_to_records(frame):
                code = str(
                    _row_get(row, "股票代码", "code", "证券代码", "代码") or ""
                ).strip()
                if code not in wanted:
                    continue
                event_date = _parse_date(
                    _row_get(
                        row,
                        "首次预约时间",
                        "一次预约时间",
                        "实际披露时间",
                        "预约披露时间",
                        "披露时间",
                    )
                )
                if event_date is None or event_date < date_from or event_date > date_to:
                    continue
                actual = _parse_date(_row_get(row, "实际披露时间", "actual_date"))
                if actual is not None and actual == event_date:
                    certainty = "confirmed"
                else:
                    certainty = "scheduled"
                name = str(_row_get(row, "股票简称", "name", "证券简称") or code)
                title = f"{name} earnings disclosure ({period})"
                event_id = f"earnings:cn:{code}:{period}:{event_date.isoformat()}"
                events.append(
                    CalendarEvent(
                        event_id=event_id,
                        event_type="earnings",
                        event_date=event_date,
                        certainty=certainty,
                        symbol=code,
                        title=title,
                        market="CN",
                        source="akshare.stock_yysj_em",
                        fetched_at=fetched_at,
                        description=(
                            "A-share appointment/actual disclosure date from "
                            "Eastmoney via akshare. Appointment dates can change."
                        ),
                        metadata={
                            "report_period": period,
                            "raw_actual": str(_row_get(row, "实际披露时间") or ""),
                        },
                    )
                )
        return events

    def _fetch_cn_ex_dividend(
        self,
        cn_codes: Sequence[str],
        *,
        date_from: date,
        date_to: date,
        fetched_at: datetime,
    ) -> List[CalendarEvent]:
        wanted = set(cn_codes)
        events: List[CalendarEvent] = []
        for period in _report_period_candidates(date_from):
            frame = self._load_fhps(period)
            for row in _dataframe_to_records(frame):
                code = str(
                    _row_get(row, "代码", "股票代码", "code", "证券代码") or ""
                ).strip()
                if code not in wanted:
                    continue
                event_date = _parse_date(
                    _row_get(
                        row,
                        "除权除息日",
                        "股权登记日",
                        "ex_date",
                        "除息日",
                    )
                )
                if event_date is None or event_date < date_from or event_date > date_to:
                    continue
                name = str(_row_get(row, "名称", "股票简称", "name") or code)
                scheme = str(_row_get(row, "送转股份-送转总比例", "分红送转", "分配方案") or "")
                title = f"{name} ex-dividend/rights"
                if scheme and scheme.lower() not in {"nan", "none"}:
                    title = f"{title}: {scheme}"
                event_id = f"ex_dividend:cn:{code}:{period}:{event_date.isoformat()}"
                events.append(
                    CalendarEvent(
                        event_id=event_id,
                        event_type="ex_dividend",
                        event_date=event_date,
                        certainty="confirmed",
                        symbol=code,
                        title=title,
                        market="CN",
                        source="akshare.stock_fhps_em",
                        fetched_at=fetched_at,
                        description=(
                            "A-share dividend / rights schedule from Eastmoney "
                            "via akshare (ex-date treated as announced/confirmed)."
                        ),
                        metadata={"report_period": period, "scheme": scheme},
                    )
                )
        return events

    def _fetch_cn_unlock(
        self,
        cn_codes: Sequence[str],
        *,
        date_from: date,
        date_to: date,
        fetched_at: datetime,
    ) -> List[CalendarEvent]:
        events: List[CalendarEvent] = []
        for code in cn_codes:
            frame = self._load_unlock(code)
            for row in _dataframe_to_records(frame):
                event_date = _parse_date(
                    _row_get(row, "解禁时间", "解禁日期", "free_date", "date")
                )
                if event_date is None or event_date < date_from or event_date > date_to:
                    continue
                shares = _row_get(row, "解禁数量", "解禁股数", "shares")
                title = f"{code} restricted share unlock"
                if shares is not None:
                    title = f"{title} ({shares})"
                event_id = f"unlock:cn:{code}:{event_date.isoformat()}"
                events.append(
                    CalendarEvent(
                        event_id=event_id,
                        event_type="unlock",
                        event_date=event_date,
                        certainty="confirmed",
                        symbol=code,
                        title=title,
                        market="CN",
                        source="akshare.stock_restricted_release_queue_em",
                        fetched_at=fetched_at,
                        description=(
                            "A-share restricted-share release batch from "
                            "Eastmoney via akshare."
                        ),
                        metadata={"shares": shares},
                    )
                )
        return events
