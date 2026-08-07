# -*- coding: utf-8 -*-
"""Financial report normalization and derived-metric helpers (issue #235).

This module is pure / side-effect free: callers supply already-fetched
DataFrames or period dicts. Missing or partial inputs never become silent
zeros — sufficiency metadata is always explicit.

Formulas used by :func:`compute_statement_metrics` (document once, reuse):

- revenue_yoy / net_profit_yoy:
  ``(latest - prior_same_period) / abs(prior_same_period) * 100``
  where prior_same_period is the matching report period from ~365 days earlier
  (same month-day preferred; refused when no match). QoQ is never used as YoY.
- gross_margin: ``gross_profit / revenue * 100`` (percent)
- net_margin: ``net_profit_parent / revenue * 100`` (percent)
- ocf_to_net_profit: ``operating_cash_flow / net_profit_parent`` (ratio)
- debt_to_asset: ``total_liabilities / total_assets * 100`` (percent)
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import pandas as pd

from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

# Core fields required for a "rich" latest-period summary.
_CORE_SUMMARY_FIELDS = (
    "report_date",
    "revenue",
    "net_profit_parent",
    "operating_cash_flow",
)

_BALANCE_FIELDS = ("total_assets", "total_liabilities", "total_equity")

_FIELD_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "report_date": (
        "REPORT_DATE",
        "REPORTDATE",
        "报告期",
        "报告日期",
        "截止日期",
        "统计截止日期",
        "DATE",
    ),
    "revenue": (
        "TOTAL_OPERATE_INCOME",
        "OPERATE_INCOME",
        "营业总收入",
        "营业收入",
        "营收",
        "TOTAL_REVENUE",
        "REVENUE",
    ),
    "net_profit_parent": (
        "PARENT_NETPROFIT",
        "NETPROFIT_PARENT",
        "归母净利润",
        "母公司股东净利润",
        "归属于母公司",
        "NETPROFIT",
        "NET_PROFIT",
    ),
    "operating_cash_flow": (
        "NETCASH_OPERATE",
        "NET_CASH_FLOWS_OPERAT",
        "经营活动产生的现金流量净额",
        "经营活动现金流量净额",
        "经营现金流",
        "OPERATING_CASH_FLOW",
        "CASH_FLOW_OPERATE",
    ),
    "gross_profit": (
        "OPERATE_PROFIT",  # often operating profit; prefer gross when present
        "GROSS_PROFIT",
        "毛利",
        "营业利润",
    ),
    "total_assets": (
        "TOTAL_ASSETS",
        "总资产",
        "资产总计",
        "资产合计",
    ),
    "total_liabilities": (
        "TOTAL_LIABILITIES",
        "总负债",
        "负债合计",
        "负债总计",
    ),
    "total_equity": (
        "TOTAL_EQUITY",
        "TOTAL_PARENT_EQUITY",
        "股东权益合计",
        "所有者权益合计",
        "净资产",
    ),
    "roe": (
        "ROE",
        "净资产收益率",
        "加权净资产收益率",
        "ROE_WEIGHT",
    ),
    "gross_margin": (
        "GROSS_PROFIT_RATIO",
        "毛利率",
        "销售毛利率",
    ),
}


def safe_float(value: Any) -> Optional[float]:
    """Best-effort float conversion; never invents zero for empty inputs."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            result = float(value)
        except (TypeError, ValueError):
            return None
        if result != result:  # NaN
            return None
        return result
    text = str(value).strip().replace(",", "").replace("%", "")
    if not text or text.lower() in {"-", "nan", "none", "null", "n/a", "na", "--"}:
        return None
    # Chinese unit suffixes (万 / 亿) are left alone; callers that need scaled
    # units must pre-normalize. Raw Eastmoney numeric cells are plain numbers.
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_report_date(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        parsed = pd.to_datetime(value, errors="coerce")
    except Exception as exc:  # broad-exception: fallback_recorded - isolate provider/service failure for merge
        log_safe_exception(logger, "operation failed", exc, error_code="internal_error")
        return None
    if pd.isna(parsed):
        return None
    try:
        return parsed.date().isoformat()
    except Exception as exc:  # broad-exception: fallback_recorded - isolate provider/service failure for merge
        log_safe_exception(logger, "operation failed", exc, error_code="internal_error")
        text = safe_str(value)
        match = re.match(r"(\d{4})[-/]?(\d{2})[-/]?(\d{2})", text)
        if match:
            return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
        return None


def to_eastmoney_report_symbol(stock_code: str) -> Optional[str]:
    """Map bare A-share codes to Eastmoney report symbols (``SH600519``).

    Returns None for non A-share codes so callers can skip statement endpoints.
    """
    code = safe_str(stock_code).upper()
    if not code:
        return None
    if code.startswith(("SH", "SZ", "BJ")) and len(code) >= 8 and code[2:].isdigit():
        return code
    if "." in code:
        base, suffix = code.rsplit(".", 1)
        if base.isdigit() and suffix in {"SH", "SZ", "SS", "BJ"}:
            prefix = "SH" if suffix in {"SH", "SS"} else suffix
            return f"{prefix}{base}"
        if suffix.isdigit() and base in {"SH", "SZ", "SS", "BJ"}:
            prefix = "SH" if base in {"SH", "SS"} else base
            return f"{prefix}{suffix}"
    digits = re.sub(r"^(SH|SZ|BJ|SS)", "", code)
    if not digits.isdigit() or len(digits) not in (5, 6):
        return None
    if digits.startswith(("5", "6", "9")) and not digits.startswith(("90", "92")):
        # 5xxxxx ETFs on SH, 6xxxxx main/STAR, 9xxxxx SH B-shares
        if digits.startswith("9") and digits[1] in {"2", "20"}:
            return f"BJ{digits}"  # BSE 92xxxx
        return f"SH{digits}"
    if digits.startswith(("0", "1", "2", "3")):
        return f"SZ{digits}"
    if digits.startswith(("4", "8", "9")):
        return f"BJ{digits}"
    return None


def _column_match(columns: Iterable[Any], keywords: Sequence[str]) -> Optional[str]:
    cols = [str(c) for c in columns]
    upper_map = {c.upper(): c for c in cols}
    for key in keywords:
        key_u = key.upper()
        if key_u in upper_map:
            return upper_map[key_u]
    for key in keywords:
        key_u = key.upper()
        for col in cols:
            if key_u in col.upper():
                return col
    return None


def _pick_from_row(row: Mapping[Any, Any], field: str) -> Any:
    keywords = _FIELD_KEYWORDS.get(field, ())
    # Exact-ish keys first
    for key in keywords:
        if key in row:
            return row[key]
        for col in row.keys():
            if str(col).upper() == key.upper():
                return row[col]
    for key in keywords:
        key_u = key.upper()
        for col, val in row.items():
            if key_u in str(col).upper():
                if val is not None and safe_str(val) not in ("", "-", "nan", "None"):
                    return val
    return None


def _period_type_from_date(report_date: Optional[str]) -> str:
    if not report_date:
        return "unknown"
    try:
        month_day = report_date[5:]
    except Exception as exc:  # broad-exception: fallback_recorded - isolate provider/service failure for merge
        log_safe_exception(logger, "operation failed", exc, error_code="internal_error")
        return "unknown"
    if month_day == "12-31":
        return "annual"
    if month_day in {"03-31", "06-30", "09-30"}:
        return "quarterly" if month_day != "06-30" else "interim"
    return "unknown"


def extract_periods_from_wide_or_long(
    df: Optional[pd.DataFrame],
    *,
    max_periods: int = 8,
) -> List[Dict[str, Any]]:
    """Normalize a financial DataFrame into period dicts (newest first).

    Supports:
    - long format: one row per report period with metric columns
    - wide format: first column is metric name, remaining columns are periods
    """
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return []

    work = df.copy()
    # Drop completely empty columns
    work = work.dropna(axis=1, how="all")
    if work.empty:
        return []

    date_col = _column_match(work.columns, _FIELD_KEYWORDS["report_date"])
    if date_col is not None:
        return _extract_long_periods(work, date_col=date_col, max_periods=max_periods)

    # Wide / pivot: first column looks like metric labels, other columns are dates
    first_col = work.columns[0]
    date_like_cols = []
    for col in work.columns[1:]:
        if normalize_report_date(col) is not None:
            date_like_cols.append(col)
        else:
            # also accept YYYYMMDD header strings
            text = re.sub(r"\D", "", str(col))
            if len(text) == 8 and text.isdigit():
                date_like_cols.append(col)
    if date_like_cols:
        return _extract_wide_periods(work, metric_col=first_col, date_cols=date_like_cols, max_periods=max_periods)

    # Fallback: treat each row as a period without explicit date column
    return _extract_long_periods(work, date_col=None, max_periods=max_periods)


def _extract_long_periods(
    df: pd.DataFrame,
    *,
    date_col: Optional[str],
    max_periods: int,
) -> List[Dict[str, Any]]:
    periods: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        mapping = row.to_dict() if isinstance(row, pd.Series) else dict(row)
        report_date = normalize_report_date(mapping.get(date_col) if date_col else _pick_from_row(mapping, "report_date"))
        period = _row_to_period(mapping, report_date=report_date)
        if any(period.get(k) is not None for k in ("revenue", "net_profit_parent", "operating_cash_flow", "total_assets")):
            periods.append(period)

    periods.sort(key=lambda item: item.get("report_date") or "", reverse=True)
    return _dedupe_periods(periods)[: max(1, max_periods)]


def _extract_wide_periods(
    df: pd.DataFrame,
    *,
    metric_col: Any,
    date_cols: Sequence[Any],
    max_periods: int,
) -> List[Dict[str, Any]]:
    # Build metric_name -> {date_col: value}
    metric_map: Dict[str, Dict[Any, Any]] = {}
    for _, row in df.iterrows():
        metric_name = safe_str(row.get(metric_col))
        if not metric_name:
            continue
        metric_map[metric_name] = {col: row.get(col) for col in date_cols}

    periods: List[Dict[str, Any]] = []
    for col in date_cols:
        report_date = normalize_report_date(col)
        # Collect values for this date across metrics into a synthetic row
        synthetic: Dict[str, Any] = {"report_date": report_date}
        for metric_name, values in metric_map.items():
            synthetic[metric_name] = values.get(col)
        period = _row_to_period(synthetic, report_date=report_date)
        if any(period.get(k) is not None for k in ("revenue", "net_profit_parent", "operating_cash_flow", "total_assets", "roe")):
            periods.append(period)

    periods.sort(key=lambda item: item.get("report_date") or "", reverse=True)
    return _dedupe_periods(periods)[: max(1, max_periods)]


def _row_to_period(row: Mapping[Any, Any], *, report_date: Optional[str]) -> Dict[str, Any]:
    period: Dict[str, Any] = {
        "report_date": report_date,
        "period_type": _period_type_from_date(report_date),
        "revenue": safe_float(_pick_from_row(row, "revenue")),
        "net_profit_parent": safe_float(_pick_from_row(row, "net_profit_parent")),
        "operating_cash_flow": safe_float(_pick_from_row(row, "operating_cash_flow")),
        "gross_profit": safe_float(_pick_from_row(row, "gross_profit")),
        "total_assets": safe_float(_pick_from_row(row, "total_assets")),
        "total_liabilities": safe_float(_pick_from_row(row, "total_liabilities")),
        "total_equity": safe_float(_pick_from_row(row, "total_equity")),
        "roe": safe_float(_pick_from_row(row, "roe")),
        "gross_margin": safe_float(_pick_from_row(row, "gross_margin")),
    }
    return period


def _dedupe_periods(periods: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    result: List[Dict[str, Any]] = []
    for period in periods:
        key = period.get("report_date") or id(period)
        if key in seen:
            continue
        seen.add(key)
        result.append(period)
    return result


def merge_period_lists(*lists: Sequence[Dict[str, Any]], max_periods: int = 8) -> List[Dict[str, Any]]:
    """Merge period series by report_date, preferring non-null field values."""
    by_date: Dict[str, Dict[str, Any]] = {}
    undated: List[Dict[str, Any]] = []
    for series in lists:
        for period in series or []:
            if not isinstance(period, dict):
                continue
            report_date = period.get("report_date")
            if not report_date:
                undated.append(dict(period))
                continue
            existing = by_date.get(str(report_date))
            if existing is None:
                by_date[str(report_date)] = dict(period)
                continue
            for key, value in period.items():
                if value is None:
                    continue
                if existing.get(key) is None:
                    existing[key] = value
    merged = list(by_date.values())
    merged.sort(key=lambda item: item.get("report_date") or "", reverse=True)
    merged.extend(undated)
    return merged[: max(1, max_periods)]


def _find_prior_year_period(
    periods: Sequence[Dict[str, Any]],
    latest: Mapping[str, Any],
) -> Optional[Dict[str, Any]]:
    latest_date = normalize_report_date(latest.get("report_date"))
    if not latest_date:
        return None
    try:
        latest_dt = date.fromisoformat(latest_date)
    except ValueError:
        return None
    target_year = latest_dt.year - 1
    target = latest_dt.replace(year=target_year).isoformat()
    # Exact month-day match first
    for period in periods:
        if period is latest:
            continue
        if period.get("report_date") == target:
            return period
    # Same month-day any earlier year (prefer one year back)
    month_day = latest_date[5:]
    candidates = []
    for period in periods:
        rd = period.get("report_date")
        if not rd or rd == latest_date:
            continue
        if str(rd)[5:] == month_day:
            candidates.append(period)
    if candidates:
        candidates.sort(key=lambda item: item.get("report_date") or "", reverse=True)
        return candidates[0]
    return None


def _metric(
    value: Optional[float],
    *,
    formula: str,
    basis: str,
) -> Dict[str, Any]:
    return {
        "value": None if value is None else round(float(value), 4),
        "formula": formula,
        "basis": basis,
    }


def compute_statement_metrics(periods: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute derived metrics with explicit formulas; missing inputs stay None."""
    if not periods:
        return {}
    latest = periods[0]
    prior = _find_prior_year_period(periods, latest)

    metrics: Dict[str, Any] = {}

    def yoy(field: str) -> Optional[float]:
        if prior is None:
            return None
        cur = safe_float(latest.get(field))
        base = safe_float(prior.get(field))
        if cur is None or base is None or base == 0:
            return None
        return (cur - base) / abs(base) * 100.0

    metrics["revenue_yoy"] = _metric(
        yoy("revenue"),
        formula="(latest.revenue - prior_year_same.revenue) / abs(prior_year_same.revenue) * 100",
        basis="period_match_yoy" if prior else "unavailable",
    )
    metrics["net_profit_yoy"] = _metric(
        yoy("net_profit_parent"),
        formula=(
            "(latest.net_profit_parent - prior_year_same.net_profit_parent) "
            "/ abs(prior_year_same.net_profit_parent) * 100"
        ),
        basis="period_match_yoy" if prior else "unavailable",
    )

    revenue = safe_float(latest.get("revenue"))
    gross_profit = safe_float(latest.get("gross_profit"))
    net_profit = safe_float(latest.get("net_profit_parent"))
    ocf = safe_float(latest.get("operating_cash_flow"))
    total_assets = safe_float(latest.get("total_assets"))
    total_liabilities = safe_float(latest.get("total_liabilities"))

    gm_direct = safe_float(latest.get("gross_margin"))
    if gm_direct is not None:
        metrics["gross_margin"] = _metric(
            gm_direct,
            formula="provider_reported_gross_margin (passthrough)",
            basis="provider",
        )
    elif gross_profit is not None and revenue not in (None, 0):
        metrics["gross_margin"] = _metric(
            gross_profit / revenue * 100.0,
            formula="gross_profit / revenue * 100",
            basis="derived",
        )
    else:
        metrics["gross_margin"] = _metric(
            None,
            formula="gross_profit / revenue * 100",
            basis="unavailable",
        )

    if net_profit is not None and revenue not in (None, 0):
        metrics["net_margin"] = _metric(
            net_profit / revenue * 100.0,
            formula="net_profit_parent / revenue * 100",
            basis="derived",
        )
    else:
        metrics["net_margin"] = _metric(
            None,
            formula="net_profit_parent / revenue * 100",
            basis="unavailable",
        )

    if ocf is not None and net_profit not in (None, 0):
        metrics["ocf_to_net_profit"] = _metric(
            ocf / net_profit,
            formula="operating_cash_flow / net_profit_parent",
            basis="derived",
        )
    else:
        metrics["ocf_to_net_profit"] = _metric(
            None,
            formula="operating_cash_flow / net_profit_parent",
            basis="unavailable",
        )

    if total_liabilities is not None and total_assets not in (None, 0):
        metrics["debt_to_asset"] = _metric(
            total_liabilities / total_assets * 100.0,
            formula="total_liabilities / total_assets * 100",
            basis="derived",
        )
    else:
        metrics["debt_to_asset"] = _metric(
            None,
            formula="total_liabilities / total_assets * 100",
            basis="unavailable",
        )

    roe = safe_float(latest.get("roe"))
    metrics["roe"] = _metric(
        roe,
        formula="provider_reported_roe (passthrough; typically weighted average ROE %)",
        basis="provider" if roe is not None else "unavailable",
    )

    if prior is not None:
        metrics["comparison_period"] = {
            "latest_report_date": latest.get("report_date"),
            "prior_report_date": prior.get("report_date"),
        }
    return metrics


def assess_sufficiency(
    financial_report: Mapping[str, Any],
    *,
    periods: Optional[Sequence[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Classify fundamentals as rich / partial / insufficient (never silent zeros)."""
    periods = list(periods or financial_report.get("periods") or [])
    present: List[str] = []
    missing: List[str] = []
    for field in _CORE_SUMMARY_FIELDS:
        value = financial_report.get(field)
        if field == "report_date":
            ok = bool(normalize_report_date(value) or value)
        else:
            ok = safe_float(value) is not None
        if ok:
            present.append(field)
        else:
            missing.append(field)

    balance_present = [f for f in _BALANCE_FIELDS if safe_float(financial_report.get(f)) is not None]
    period_count = len(periods)
    has_history = period_count >= 2

    if len(present) >= 3 and has_history:
        level = "rich"
        message = None
    elif present:
        level = "partial"
        message = (
            "partial fundamentals: some statement fields are available but coverage is incomplete; "
            "do not invent missing values"
        )
    else:
        level = "insufficient"
        message = "insufficient fundamentals: no usable statement figures for this stock"

    return {
        "level": level,
        "core_fields_present": present,
        "missing_fields": missing,
        "balance_fields_present": balance_present,
        "period_count": period_count,
        "has_multi_period_history": has_history,
        "message": message,
    }


def build_financial_report_payload(
    *,
    periods: Sequence[Dict[str, Any]],
    statement_coverage: Optional[Mapping[str, Any]] = None,
    sources: Optional[Sequence[str]] = None,
    currency: str = "CNY",
    as_of: Optional[str] = None,
    seed_summary: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Assemble the additive ``earnings.financial_report`` payload.

    Existing consumers only read the summary keys (report_date / revenue /
    net_profit_parent / operating_cash_flow / roe / currency). New fields are
    strictly additive.
    """
    periods_list = [dict(p) for p in periods if isinstance(p, dict)]
    latest = periods_list[0] if periods_list else {}
    seed = dict(seed_summary or {})

    def pick(field: str) -> Any:
        if seed.get(field) is not None and seed.get(field) != "":
            return seed.get(field)
        return latest.get(field)

    report_date = normalize_report_date(pick("report_date")) or pick("report_date")
    as_of_date = as_of or date.today().isoformat()

    payload: Dict[str, Any] = {
        "report_date": report_date,
        "revenue": safe_float(pick("revenue")),
        "net_profit_parent": safe_float(pick("net_profit_parent")),
        "operating_cash_flow": safe_float(pick("operating_cash_flow")),
        "roe": safe_float(pick("roe")),
        "currency": currency,
        "total_assets": safe_float(pick("total_assets")),
        "total_liabilities": safe_float(pick("total_liabilities")),
        "total_equity": safe_float(pick("total_equity")),
        "periods": periods_list,
        "statements": dict(statement_coverage or {}),
        "metrics": compute_statement_metrics(periods_list),
        "data_recency": {
            "report_date": report_date,
            "as_of": as_of_date,
            "note": (
                "Statement figures are as of the latest reported fiscal period "
                f"({report_date or 'unknown'}); they are not real-time and may lag "
                "the current market price by months."
            ),
        },
        "sources": [s for s in (sources or []) if s],
    }
    # Drop empty balance fields from top-level to keep legacy compact when unused
    for key in _BALANCE_FIELDS:
        if payload.get(key) is None:
            payload.pop(key, None)

    payload["sufficiency"] = assess_sufficiency(payload, periods=periods_list)

    # If completely empty (no summary and no periods), still return sufficiency only.
    if not periods_list and all(
        payload.get(k) is None for k in ("report_date", "revenue", "net_profit_parent", "operating_cash_flow", "roe")
    ):
        return {
            "currency": currency,
            "periods": [],
            "statements": dict(statement_coverage or {}),
            "metrics": {},
            "sufficiency": payload["sufficiency"],
            "data_recency": payload["data_recency"],
            "sources": payload["sources"],
        }
    return payload


def format_financial_report_prompt_section(
    financial_report: Optional[Mapping[str, Any]],
    *,
    language: str = "zh",
) -> str:
    """Render a facts-only prompt section with honesty about missing data."""
    if not isinstance(financial_report, dict) or not financial_report:
        if language == "en":
            return (
                "### Financial statements (facts)\n"
                "> insufficient fundamentals: no usable statement figures; "
                "do not invent values or treat missing data as bullish/bearish.\n"
            )
        return (
            "### 财务报表（事实）\n"
            "> insufficient fundamentals：无可用财报数值；禁止编造，也不要把缺失本身解释为利好或利空。\n"
        )

    sufficiency = financial_report.get("sufficiency") if isinstance(financial_report.get("sufficiency"), dict) else {}
    level = safe_str(sufficiency.get("level") or "insufficient")
    message = safe_str(sufficiency.get("message"))
    recency = financial_report.get("data_recency") if isinstance(financial_report.get("data_recency"), dict) else {}
    metrics = financial_report.get("metrics") if isinstance(financial_report.get("metrics"), dict) else {}
    periods = financial_report.get("periods") if isinstance(financial_report.get("periods"), list) else []

    def metric_value(name: str) -> str:
        item = metrics.get(name)
        if isinstance(item, dict) and item.get("value") is not None:
            return str(item.get("value"))
        return "N/A"

    lines: List[str] = []
    if language == "en":
        lines.append("### Financial statements (facts)")
        lines.append(f"| Field | Value | Note |")
        lines.append("|------|------|------|")
        lines.append(f"| Latest report period | {financial_report.get('report_date', 'N/A')} | not real-time |")
        lines.append(f"| Revenue | {financial_report.get('revenue', 'N/A')} | statement fact |")
        lines.append(f"| Net profit (parent) | {financial_report.get('net_profit_parent', 'N/A')} | statement fact |")
        lines.append(f"| Operating cash flow | {financial_report.get('operating_cash_flow', 'N/A')} | statement fact |")
        lines.append(f"| ROE | {financial_report.get('roe', 'N/A')} | provider reported |")
        lines.append(f"| Revenue YoY % | {metric_value('revenue_yoy')} | formula in metrics.formula |")
        lines.append(f"| Net profit YoY % | {metric_value('net_profit_yoy')} | formula in metrics.formula |")
        lines.append(f"| Gross margin % | {metric_value('gross_margin')} | formula in metrics.formula |")
        lines.append(f"| Net margin % | {metric_value('net_margin')} | formula in metrics.formula |")
        lines.append(f"| OCF / net profit | {metric_value('ocf_to_net_profit')} | formula in metrics.formula |")
        lines.append(f"| Debt / assets % | {metric_value('debt_to_asset')} | formula in metrics.formula |")
        lines.append(f"| Sufficiency | {level} | {message or 'see missing_fields'} |")
        if recency.get("note"):
            lines.append(f"> Data recency: {recency.get('note')}")
        if level == "insufficient":
            lines.append(
                "> insufficient fundamentals: refuse fabricated ratios; "
                "state data is insufficient in fundamental_analysis."
            )
        elif periods and len(periods) >= 2:
            hist = ", ".join(
                f"{p.get('report_date')}: rev={p.get('revenue')} np={p.get('net_profit_parent')}"
                for p in periods[:4]
                if isinstance(p, dict)
            )
            lines.append(f"> Multi-period history (newest first): {hist}")
        lines.append(
            "> Separate facts (table above) from inference in fundamental_analysis. "
            "N/A must be described as missing, never as zero."
        )
    else:
        lines.append("### 财务报表（事实）")
        lines.append("| 指标 | 数值 | 说明 |")
        lines.append("|------|------|------|")
        lines.append(f"| 最近报告期 | {financial_report.get('report_date', 'N/A')} | 非实时 |")
        lines.append(f"| 营业收入 | {financial_report.get('revenue', 'N/A')} | 报表事实 |")
        lines.append(f"| 归母净利润 | {financial_report.get('net_profit_parent', 'N/A')} | 报表事实 |")
        lines.append(f"| 经营现金流 | {financial_report.get('operating_cash_flow', 'N/A')} | 报表事实 |")
        lines.append(f"| ROE | {financial_report.get('roe', 'N/A')} | 数据源原样 |")
        lines.append(f"| 营收同比% | {metric_value('revenue_yoy')} | 公式见 metrics.formula |")
        lines.append(f"| 净利同比% | {metric_value('net_profit_yoy')} | 公式见 metrics.formula |")
        lines.append(f"| 毛利率% | {metric_value('gross_margin')} | 公式见 metrics.formula |")
        lines.append(f"| 净利率% | {metric_value('net_margin')} | 公式见 metrics.formula |")
        lines.append(f"| 经营现金流/净利润 | {metric_value('ocf_to_net_profit')} | 公式见 metrics.formula |")
        lines.append(f"| 资产负债率% | {metric_value('debt_to_asset')} | 公式见 metrics.formula |")
        lines.append(f"| 充分性 | {level} | {message or '见 missing_fields'} |")
        if recency.get("note"):
            lines.append(f"> 数据时效：{recency.get('note')}")
        if level == "insufficient":
            lines.append(
                "> insufficient fundamentals：禁止编造比率；"
                "在 fundamental_analysis 中明确写“基本面数据不足”。"
            )
        elif periods and len(periods) >= 2:
            hist = "；".join(
                f"{p.get('report_date')}: 营收={p.get('revenue')} 净利={p.get('net_profit_parent')}"
                for p in periods[:4]
                if isinstance(p, dict)
            )
            lines.append(f"> 多期历史（新→旧）：{hist}")
        lines.append(
            "> 表格为事实层；推理写在 fundamental_analysis。"
            "N/A 必须表述为缺失，禁止当成 0。"
        )
    return "\n".join(lines) + "\n"


def flatten_metric_values(metrics: Mapping[str, Any]) -> Dict[str, Optional[float]]:
    """Extract plain float values from metrics.* for growth-block compatibility."""
    result: Dict[str, Optional[float]] = {}
    for key, item in (metrics or {}).items():
        if isinstance(item, dict) and "value" in item:
            result[key] = safe_float(item.get("value"))
        else:
            result[key] = safe_float(item)
    return result
