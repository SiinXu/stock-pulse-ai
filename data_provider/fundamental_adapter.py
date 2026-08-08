# -*- coding: utf-8 -*-
"""
AkShare fundamental adapter (fail-open).

This adapter intentionally uses capability probing against multiple AkShare
endpoint candidates. It should never raise to caller; partial data is allowed.
"""

from __future__ import annotations

import logging
from src.utils.sanitize import log_safe_exception
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

_DIVIDEND_KEYWORD_MAP: Dict[str, List[str]] = {
    "per_share": [
        "每股派息",
        "每股现金红利",
        "每股分红",
        "每股派现",
        "派现(元/股)",
        "派息(元/股)",
        "税前派息(元/股)",
        "现金分红(税前)",
    ],
    "plan_text": [
        "分配方案",
        "分红方案",
        "实施方案",
        "派息方案",
        "方案",
        "预案",
        "方案说明",
    ],
    "ex_dividend_date": ["除权除息日", "除息日", "除权日", "除权除息", "除息日期"],
    "record_date": ["股权登记日", "登记日"],
    "announce_date": ["公告日期", "公告日", "实施公告日", "预案公告日"],
    "report_date": ["报告期", "报告日期", "截止日期", "统计截止日期"],
}


def _safe_float(value: Any) -> Optional[float]:
    """Best-effort float conversion."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    s = str(value).strip().replace(",", "").replace("%", "")
    if not s:
        return None
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _safe_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    try:
        parsed = pd.to_datetime(value)
    except Exception as exc:  # broad-exception: fallback_recorded - isolate provider/service failure for merge
        log_safe_exception(logger, "operation failed", exc, error_code="internal_error")
        return None
    if pd.isna(parsed):
        return None
    try:
        return parsed.to_pydatetime()
    except Exception as exc:  # broad-exception: fallback_recorded - isolate provider/service failure for merge
        log_safe_exception(logger, "operation failed", exc, error_code="internal_error")
        return None


def _normalize_code(raw: Any) -> str:
    s = _safe_str(raw).upper()
    if "." in s:
        s = s.split(".", 1)[0]
    s = re.sub(r"^(SH|SZ|BJ)", "", s)
    return s


def _pick_by_keywords(row: pd.Series, keywords: List[str]) -> Optional[Any]:
    """
    Return first non-empty row value whose column name contains any keyword.
    """
    for col in row.index:
        col_s = str(col)
        if any(k in col_s for k in keywords):
            val = row.get(col)
            if val is not None and str(val).strip() not in ("", "-", "nan", "None"):
                return val
    return None


def _parse_dividend_plan_to_per_share(plan_text: str) -> Optional[float]:
    """Parse per-share cash dividend from Chinese plan text."""
    text = _safe_str(plan_text)
    if not text:
        return None

    for pattern in (
        r"(?:每)?\s*10\s*股?\s*派(?:发)?\s*([0-9]+(?:\.[0-9]+)?)\s*元",
        r"10\s*派\s*([0-9]+(?:\.[0-9]+)?)\s*元",
    ):
        match = re.search(pattern, text)
        if match:
            parsed = _safe_float(match.group(1))
            if parsed is not None and parsed > 0:
                return parsed / 10.0

    match_per_share = re.search(r"每\s*股\s*派(?:发)?\s*([0-9]+(?:\.[0-9]+)?)\s*元", text)
    if match_per_share:
        parsed = _safe_float(match_per_share.group(1))
        if parsed is not None and parsed > 0:
            return parsed
    return None


def _extract_cash_dividend_per_share(row: pd.Series) -> Optional[float]:
    """Extract pre-tax cash dividend per share from a row."""
    plan_text = _safe_str(_pick_by_keywords(row, _DIVIDEND_KEYWORD_MAP["plan_text"]))
    # Keep pre-tax semantics; skip explicit after-tax plans unless pre-tax marker exists.
    if "税后" in plan_text and "税前" not in plan_text and "含税" not in plan_text:
        return None

    direct = _safe_float(_pick_by_keywords(row, _DIVIDEND_KEYWORD_MAP["per_share"]))
    if direct is not None and direct > 0:
        return direct
    return _parse_dividend_plan_to_per_share(plan_text)


def _filter_rows_by_code(df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    code_cols = [c for c in df.columns if any(k in str(c) for k in ("代码", "股票代码", "证券代码", "symbol", "ts_code"))]
    if not code_cols:
        return df

    target = _normalize_code(stock_code)
    for col in code_cols:
        try:
            series = df[col].astype(str).map(_normalize_code)
            filtered = df[series == target]
            if not filtered.empty:
                return filtered
        except Exception as exc:  # broad-exception: fallback_recorded - isolate provider/service failure for merge
            log_safe_exception(logger, "operation failed", exc, error_code="internal_error")
            continue
    return pd.DataFrame()


def _normalize_report_date(value: Any) -> Optional[str]:
    parsed = _safe_datetime(value)
    return parsed.date().isoformat() if parsed else None


def _build_dividend_payload(
    dividend_df: pd.DataFrame,
    stock_code: str,
    max_events: int = 5,
) -> Dict[str, Any]:
    work_df = _filter_rows_by_code(dividend_df, stock_code)
    if work_df.empty:
        return {}

    now_date = datetime.now().date()
    ttm_start_date = now_date - timedelta(days=365)
    dedupe_keys = set()
    events: List[Dict[str, Any]] = []

    for _, row in work_df.iterrows():
        if not isinstance(row, pd.Series):
            continue
        ex_dt = _safe_datetime(_pick_by_keywords(row, _DIVIDEND_KEYWORD_MAP["ex_dividend_date"]))
        record_dt = _safe_datetime(_pick_by_keywords(row, _DIVIDEND_KEYWORD_MAP["record_date"]))
        announce_dt = _safe_datetime(_pick_by_keywords(row, _DIVIDEND_KEYWORD_MAP["announce_date"]))
        event_dt = ex_dt or record_dt or announce_dt
        if event_dt is None:
            continue
        event_date = event_dt.date()
        if event_date > now_date:
            continue

        per_share = _extract_cash_dividend_per_share(row)
        if per_share is None or per_share <= 0:
            continue

        dedupe_key = (event_date.isoformat(), round(per_share, 6))
        if dedupe_key in dedupe_keys:
            continue
        dedupe_keys.add(dedupe_key)

        events.append(
            {
                "event_date": event_date.isoformat(),
                "ex_dividend_date": ex_dt.date().isoformat() if ex_dt else None,
                "record_date": record_dt.date().isoformat() if record_dt else None,
                "announcement_date": announce_dt.date().isoformat() if announce_dt else None,
                "cash_dividend_per_share": round(per_share, 6),
                "is_pre_tax": True,
            }
        )

    if not events:
        return {}

    events.sort(key=lambda item: item.get("event_date") or "", reverse=True)
    ttm_events: List[Dict[str, Any]] = []
    for item in events:
        event_dt = _safe_datetime(item.get("event_date"))
        if event_dt is None:
            continue
        event_date = event_dt.date()
        if ttm_start_date <= event_date <= now_date:
            ttm_events.append(item)

    return {
        "events": events[:max(1, max_events)],
        "ttm_event_count": len(ttm_events),
        "ttm_cash_dividend_per_share": (
            round(sum(float(item.get("cash_dividend_per_share") or 0.0) for item in ttm_events), 6)
            if ttm_events else None
        ),
        "coverage": "cash_dividend_pre_tax",
        "as_of": now_date.isoformat(),
    }


def _extract_latest_row(df: pd.DataFrame, stock_code: str) -> Optional[pd.Series]:
    """
    Select the most relevant row for the given stock.
    """
    if df is None or df.empty:
        return None

    code_cols = [c for c in df.columns if any(k in str(c) for k in ("代码", "股票代码", "证券代码", "ts_code", "symbol"))]
    target = _normalize_code(stock_code)
    if code_cols:
        for col in code_cols:
            try:
                series = df[col].astype(str).map(_normalize_code)
                matched = df[series == target]
                if not matched.empty:
                    return matched.iloc[0]
            except Exception as exc:  # broad-exception: fallback_recorded - isolate provider/service failure for merge
                log_safe_exception(logger, "operation failed", exc, error_code="internal_error")
                continue
        return None

    # Fallback: use latest row
    return df.iloc[0]


class AkshareFundamentalAdapter:
    """AkShare adapter for fundamentals, capital flow and dragon-tiger signals."""

    def _call_df_candidates(
        self,
        candidates: List[Tuple[str, Dict[str, Any]]],
    ) -> Tuple[Optional[pd.DataFrame], Optional[str], List[str]]:
        errors: List[str] = []
        try:
            import akshare as ak
        except Exception as exc:  # broad-exception: fallback_recorded - isolate provider/service failure for merge
            log_safe_exception(logger, "operation failed", exc, error_code="internal_error")
            return None, None, [f"import_akshare:{type(exc).__name__}"]

        for func_name, kwargs in candidates:
            fn = getattr(ak, func_name, None)
            if fn is None:
                continue
            try:
                df = fn(**kwargs)
                if isinstance(df, pd.Series):
                    df = df.to_frame().T
                if isinstance(df, pd.DataFrame) and not df.empty:
                    return df, func_name, errors
            except Exception as exc:  # broad-exception: fallback_recorded - isolate provider/service failure for merge
                log_safe_exception(logger, "operation failed", exc, error_code="internal_error")
                errors.append(f"{func_name}:{type(exc).__name__}")
                continue
        return None, None, errors

    def get_fundamental_bundle(self, stock_code: str) -> Dict[str, Any]:
        """
        Return normalized fundamental blocks from AkShare with partial tolerance.
        """
        result: Dict[str, Any] = {
            "status": "not_supported",
            "growth": {},
            "earnings": {},
            "institution": {},
            "source_chain": [],
            "errors": [],
        }

        # Financial indicators + multi-period statements (issue #235, A-share first).
        # Extends the existing fundamental path; never invents silent zeros.
        seed_summary: Dict[str, Any] = {}
        fin_df, fin_source, fin_errors = self._call_df_candidates([
            ("stock_financial_abstract", {"symbol": stock_code}),
            ("stock_financial_analysis_indicator", {"symbol": stock_code}),
            ("stock_financial_analysis_indicator_em", {"symbol": f"{stock_code}.SH"}),
            ("stock_financial_analysis_indicator_em", {"symbol": f"{stock_code}.SZ"}),
            ("stock_financial_analysis_indicator", {}),
        ])
        result["errors"].extend(fin_errors)
        if fin_df is not None:
            row = _extract_latest_row(fin_df, stock_code)
            if row is not None:
                revenue_yoy = _safe_float(_pick_by_keywords(row, ["营业收入同比", "营收同比", "收入同比", "同比增长"]))
                profit_yoy = _safe_float(_pick_by_keywords(row, ["净利润同比", "净利同比", "归母净利润同比"]))
                roe = _safe_float(_pick_by_keywords(row, ["净资产收益率", "ROE", "净资产收益"]))
                gross_margin = _safe_float(_pick_by_keywords(row, ["毛利率"]))
                report_date = _normalize_report_date(_pick_by_keywords(row, _DIVIDEND_KEYWORD_MAP["report_date"]))
                revenue = _safe_float(_pick_by_keywords(row, ["营业总收入", "营业收入", "营收"]))
                net_profit_parent = _safe_float(_pick_by_keywords(row, ["归母净利润", "母公司股东净利润", "净利润"]))
                operating_cash_flow = _safe_float(
                    _pick_by_keywords(row, ["经营活动产生的现金流量净额", "经营现金流", "经营活动现金流"])
                )
                result["growth"] = {
                    "revenue_yoy": revenue_yoy,
                    "net_profit_yoy": profit_yoy,
                    "roe": roe,
                    "gross_margin": gross_margin,
                }
                seed_summary = {
                    "report_date": report_date,
                    "revenue": revenue,
                    "net_profit_parent": net_profit_parent,
                    "operating_cash_flow": operating_cash_flow,
                    "roe": roe,
                    "gross_margin": gross_margin,
                }
                result["source_chain"].append(f"growth:{fin_source}")

        # Multi-period statement enrichment (additive fields on financial_report).
        try:
            report_payload, statement_sources, statement_errors = self._build_financial_report_from_statements(
                stock_code,
                seed_summary=seed_summary,
                abstract_df=fin_df,
                abstract_source=fin_source,
            )
            result["errors"].extend(statement_errors)
            if report_payload:
                result["earnings"]["financial_report"] = report_payload
                for src in statement_sources:
                    if src and src not in result["source_chain"]:
                        result["source_chain"].append(src)
                # Prefer statement-derived YoY when provider growth is empty.
                metrics = report_payload.get("metrics") if isinstance(report_payload.get("metrics"), dict) else {}
                growth = result.get("growth") if isinstance(result.get("growth"), dict) else {}
                for key in ("revenue_yoy", "net_profit_yoy", "gross_margin", "roe"):
                    if growth.get(key) is not None:
                        continue
                    metric = metrics.get(key)
                    value = metric.get("value") if isinstance(metric, dict) else None
                    if value is not None:
                        growth[key] = value
                if growth:
                    result["growth"] = growth
            elif any(v is not None for v in seed_summary.values()):
                # Fallback: keep legacy single-period summary + explicit sufficiency.
                from src.services.financial_reports_service import build_financial_report_payload

                result["earnings"]["financial_report"] = build_financial_report_payload(
                    periods=[],
                    seed_summary=seed_summary,
                    sources=[f"growth:{fin_source}"] if fin_source else [],
                    currency="CNY",
                )
        except Exception as exc:  # broad-exception: fallback_recorded - isolate failure path for continuous merge
            log_safe_exception(logger, "handler failed", exc, error_code="internal_error")
            result["errors"].append(f"financial_statements:{type(exc).__name__}")
            if any(v is not None for v in seed_summary.values()):
                result["earnings"]["financial_report"] = {
                    **seed_summary,
                    "currency": "CNY",
                    "sufficiency": {
                        "level": "partial",
                        "message": "partial fundamentals: statement enrichment failed; summary only",
                        "core_fields_present": [k for k, v in seed_summary.items() if v is not None],
                        "missing_fields": [],
                        "period_count": 0,
                        "has_multi_period_history": False,
                    },
                }

        # Earnings forecast
        forecast_df, forecast_source, forecast_errors = self._call_df_candidates([
            ("stock_yjyg_em", {"symbol": stock_code}),
            ("stock_yjyg_em", {}),
            ("stock_yjbb_em", {"symbol": stock_code}),
            ("stock_yjbb_em", {}),
        ])
        result["errors"].extend(forecast_errors)
        if forecast_df is not None:
            row = _extract_latest_row(forecast_df, stock_code)
            if row is not None:
                result["earnings"]["forecast_summary"] = _safe_str(
                    _pick_by_keywords(row, ["预告", "业绩变动", "内容", "摘要", "公告"])
                )[:200]
                result["source_chain"].append(f"earnings_forecast:{forecast_source}")

        # Earnings quick report
        quick_df, quick_source, quick_errors = self._call_df_candidates([
            ("stock_yjkb_em", {"symbol": stock_code}),
            ("stock_yjkb_em", {}),
        ])
        result["errors"].extend(quick_errors)
        if quick_df is not None:
            row = _extract_latest_row(quick_df, stock_code)
            if row is not None:
                result["earnings"]["quick_report_summary"] = _safe_str(
                    _pick_by_keywords(row, ["快报", "摘要", "公告", "说明"])
                )[:200]
                result["source_chain"].append(f"earnings_quick:{quick_source}")

        # Dividend details (cash dividend, pre-tax)
        dividend_df, dividend_source, dividend_errors = self._call_df_candidates([
            ("stock_fhps_detail_em", {"symbol": stock_code}),
            ("stock_history_dividend_detail", {"symbol": stock_code, "indicator": "分红", "date": ""}),
            ("stock_dividend_cninfo", {"symbol": stock_code}),
        ])
        result["errors"].extend(dividend_errors)
        if dividend_df is not None:
            dividend_payload = _build_dividend_payload(dividend_df, stock_code, max_events=5)
            if dividend_payload:
                result["earnings"]["dividend"] = dividend_payload
                result["source_chain"].append(f"dividend:{dividend_source}")

        # Institution / top shareholders
        inst_df, inst_source, inst_errors = self._call_df_candidates([
            ("stock_institute_hold", {}),
            ("stock_institute_recommend", {}),
        ])
        result["errors"].extend(inst_errors)
        if inst_df is not None:
            row = _extract_latest_row(inst_df, stock_code)
            if row is not None:
                inst_change = _safe_float(_pick_by_keywords(row, ["增减", "变化", "变动", "持股变化"]))
                result["institution"]["institution_holding_change"] = inst_change
                result["source_chain"].append(f"institution:{inst_source}")

        top10_df, top10_source, top10_errors = self._call_df_candidates([
            ("stock_gdfx_top_10_em", {"symbol": stock_code}),
            ("stock_gdfx_top_10_em", {}),
            ("stock_zh_a_gdhs_detail_em", {"symbol": stock_code}),
            ("stock_zh_a_gdhs_detail_em", {}),
        ])
        result["errors"].extend(top10_errors)
        if top10_df is not None:
            row = _extract_latest_row(top10_df, stock_code)
            if row is not None:
                holder_change = _safe_float(_pick_by_keywords(row, ["增减", "变化", "持股变化", "变动"]))
                result["institution"]["top10_holder_change"] = holder_change
                result["source_chain"].append(f"top10:{top10_source}")

        has_content = bool(result["growth"] or result["earnings"] or result["institution"])
        result["status"] = "partial" if has_content else "not_supported"
        return result

    def _build_financial_report_from_statements(
        self,
        stock_code: str,
        *,
        seed_summary: Optional[Dict[str, Any]] = None,
        abstract_df: Optional[pd.DataFrame] = None,
        abstract_source: Optional[str] = None,
        max_periods: int = 8,
    ) -> Tuple[Dict[str, Any], List[str], List[str]]:
        """Fetch and normalize multi-period A-share statements into financial_report.

        Prefer reusing the already-fetched financial abstract. When multi-period
        history or balance-sheet fields are missing, best-effort Eastmoney
        report-period endpoints are tried (symbol form ``SH600519``). Fail-open:
        any provider error is recorded and never raised.
        """
        from src.services.financial_reports_service import (
            build_financial_report_payload,
            extract_periods_from_wide_or_long,
            merge_period_lists,
            to_eastmoney_report_symbol,
        )

        errors: List[str] = []
        sources: List[str] = []
        statement_coverage: Dict[str, Any] = {
            "income": {"available": False, "period_count": 0, "source": None},
            "balance": {"available": False, "period_count": 0, "source": None},
            "cash_flow": {"available": False, "period_count": 0, "source": None},
            "abstract": {"available": False, "period_count": 0, "source": abstract_source},
        }

        abstract_periods: List[Dict[str, Any]] = []
        if abstract_df is not None:
            abstract_periods = extract_periods_from_wide_or_long(abstract_df, max_periods=max_periods)
            statement_coverage["abstract"] = {
                "available": bool(abstract_periods),
                "period_count": len(abstract_periods),
                "source": abstract_source,
            }
            if abstract_source and abstract_periods:
                sources.append(f"statements.abstract:{abstract_source}")

        em_symbol = to_eastmoney_report_symbol(stock_code)
        income_periods: List[Dict[str, Any]] = []
        balance_periods: List[Dict[str, Any]] = []
        cashflow_periods: List[Dict[str, Any]] = []

        has_multi = len(abstract_periods) >= 2
        has_ocf = any(p.get("operating_cash_flow") is not None for p in abstract_periods)
        has_balance = any(p.get("total_assets") is not None for p in abstract_periods)
        # Skip extra network only when abstract already provides multi-period + OCF + balance.
        need_statements = not (has_multi and has_ocf and has_balance)

        if em_symbol and need_statements:
            # Income statement (multi-period)
            income_df, income_source, income_errors = self._call_df_candidates([
                ("stock_profit_sheet_by_report_em", {"symbol": em_symbol}),
                ("stock_financial_benefit_ths", {"symbol": stock_code}),
                ("stock_financial_benefit_new_ths", {"symbol": stock_code}),
            ])
            errors.extend(income_errors)
            if income_df is not None:
                income_periods = extract_periods_from_wide_or_long(income_df, max_periods=max_periods)
                statement_coverage["income"] = {
                    "available": bool(income_periods),
                    "period_count": len(income_periods),
                    "source": income_source,
                }
                if income_source and income_periods:
                    sources.append(f"statements.income:{income_source}")

            # Balance sheet
            balance_df, balance_source, balance_errors = self._call_df_candidates([
                ("stock_balance_sheet_by_report_em", {"symbol": em_symbol}),
                ("stock_financial_debt_ths", {"symbol": stock_code}),
                ("stock_financial_debt_new_ths", {"symbol": stock_code}),
            ])
            errors.extend(balance_errors)
            if balance_df is not None:
                balance_periods = extract_periods_from_wide_or_long(balance_df, max_periods=max_periods)
                statement_coverage["balance"] = {
                    "available": bool(balance_periods),
                    "period_count": len(balance_periods),
                    "source": balance_source,
                }
                if balance_source and balance_periods:
                    sources.append(f"statements.balance:{balance_source}")

            # Cash flow
            cashflow_df, cashflow_source, cashflow_errors = self._call_df_candidates([
                ("stock_cash_flow_sheet_by_report_em", {"symbol": em_symbol}),
                ("stock_financial_cash_ths", {"symbol": stock_code}),
                ("stock_financial_cash_new_ths", {"symbol": stock_code}),
            ])
            errors.extend(cashflow_errors)
            if cashflow_df is not None:
                cashflow_periods = extract_periods_from_wide_or_long(cashflow_df, max_periods=max_periods)
                statement_coverage["cash_flow"] = {
                    "available": bool(cashflow_periods),
                    "period_count": len(cashflow_periods),
                    "source": cashflow_source,
                }
                if cashflow_source and cashflow_periods:
                    sources.append(f"statements.cash_flow:{cashflow_source}")
        elif not em_symbol:
            errors.append("statements:non_a_share_symbol_skipped")

        periods = merge_period_lists(
            income_periods,
            balance_periods,
            cashflow_periods,
            abstract_periods,
            max_periods=max_periods,
        )

        # If abstract alone had periods and statements were skipped, still mark income-like coverage.
        if periods and not statement_coverage["income"]["available"] and abstract_periods:
            statement_coverage["income"] = {
                "available": True,
                "period_count": len(abstract_periods),
                "source": abstract_source,
            }

        if not periods and not (seed_summary and any(v is not None for v in seed_summary.values())):
            # Explicit insufficient payload so consumers never see silent empty dicts
            # masquerading as zeros.
            payload = build_financial_report_payload(
                periods=[],
                statement_coverage=statement_coverage,
                sources=sources,
                currency="CNY",
                seed_summary=seed_summary or {},
            )
            return payload, sources, errors

        payload = build_financial_report_payload(
            periods=periods,
            statement_coverage=statement_coverage,
            sources=sources,
            currency="CNY",
            seed_summary=seed_summary or {},
        )
        return payload, sources, errors

    def get_capital_flow(self, stock_code: str, top_n: int = 5) -> Dict[str, Any]:
        """
        Return stock + sector capital flow.
        """
        result: Dict[str, Any] = {
            "status": "not_supported",
            "stock_flow": {},
            "sector_rankings": {"top": [], "bottom": []},
            "source_chain": [],
            "errors": [],
        }

        stock_df, stock_source, stock_errors = self._call_df_candidates([
            ("stock_individual_fund_flow", {"stock": stock_code}),
            ("stock_individual_fund_flow", {"symbol": stock_code}),
            ("stock_individual_fund_flow", {}),
            ("stock_main_fund_flow", {"symbol": stock_code}),
            ("stock_main_fund_flow", {}),
        ])
        result["errors"].extend(stock_errors)
        if stock_df is not None:
            row = _extract_latest_row(stock_df, stock_code)
            if row is not None:
                net_inflow = _safe_float(_pick_by_keywords(row, ["主力净流入", "净流入", "净额"]))
                inflow_5d = _safe_float(_pick_by_keywords(row, ["5日", "五日"]))
                inflow_10d = _safe_float(_pick_by_keywords(row, ["10日", "十日"]))
                result["stock_flow"] = {
                    "main_net_inflow": net_inflow,
                    "inflow_5d": inflow_5d,
                    "inflow_10d": inflow_10d,
                }
                result["source_chain"].append(f"capital_stock:{stock_source}")

        sector_df, sector_source, sector_errors = self._call_df_candidates([
            ("stock_sector_fund_flow_rank", {}),
            ("stock_sector_fund_flow_summary", {}),
        ])
        result["errors"].extend(sector_errors)
        if sector_df is not None:
            name_col = next((c for c in sector_df.columns if any(k in str(c) for k in ("板块", "行业", "名称", "name"))), None)
            flow_col = next((c for c in sector_df.columns if any(k in str(c) for k in ("净流入", "主力", "flow", "净额"))), None)
            if name_col and flow_col:
                work_df = sector_df[[name_col, flow_col]].copy()
                work_df[flow_col] = pd.to_numeric(work_df[flow_col], errors="coerce")
                work_df = work_df.dropna(subset=[flow_col])
                top_df = work_df.nlargest(top_n, flow_col)
                bottom_df = work_df.nsmallest(top_n, flow_col)
                result["sector_rankings"] = {
                    "top": [{"name": _safe_str(r[name_col]), "net_inflow": float(r[flow_col])} for _, r in top_df.iterrows()],
                    "bottom": [{"name": _safe_str(r[name_col]), "net_inflow": float(r[flow_col])} for _, r in bottom_df.iterrows()],
                }
                result["source_chain"].append(f"capital_sector:{sector_source}")

        has_content = bool(result["stock_flow"] or result["sector_rankings"]["top"] or result["sector_rankings"]["bottom"])
        result["status"] = "partial" if has_content else "not_supported"
        return result

    def get_dragon_tiger_flag(self, stock_code: str, lookback_days: int = 20) -> Dict[str, Any]:
        """
        Return dragon-tiger signal in lookback window.
        """
        result: Dict[str, Any] = {
            "status": "not_supported",
            "is_on_list": False,
            "recent_count": 0,
            "latest_date": None,
            "source_chain": [],
            "errors": [],
        }

        df, source, errors = self._call_df_candidates([
            ("stock_lhb_stock_statistic_em", {}),
            ("stock_lhb_detail_em", {}),
            ("stock_lhb_jgmmtj_em", {}),
        ])
        result["errors"].extend(errors)
        if df is None:
            return result

        # Try code filter
        code_cols = [c for c in df.columns if any(k in str(c) for k in ("代码", "股票代码", "证券代码"))]
        target = _normalize_code(stock_code)
        matched = pd.DataFrame()
        for col in code_cols:
            try:
                series = df[col].astype(str).map(_normalize_code)
                cur = df[series == target]
                if not cur.empty:
                    matched = cur
                    break
            except Exception as exc:  # broad-exception: fallback_recorded - isolate provider/service failure for merge
                log_safe_exception(logger, "operation failed", exc, error_code="internal_error")
                continue
        if matched.empty:
            result["source_chain"].append(f"dragon_tiger:{source}")
            result["status"] = "ok" if code_cols else "partial"
            return result

        date_col = next((c for c in matched.columns if any(k in str(c) for k in ("日期", "上榜", "交易日", "time"))), None)
        parsed_dates: List[datetime] = []
        if date_col is not None:
            for val in matched[date_col].astype(str).tolist():
                try:
                    parsed_dates.append(pd.to_datetime(val).to_pydatetime())
                except Exception as exc:  # broad-exception: fallback_recorded - isolate provider/service failure for merge
                    log_safe_exception(logger, "operation failed", exc, error_code="internal_error")
                    continue
        now = datetime.now()
        start = now - timedelta(days=max(1, lookback_days))
        recent_dates = [d for d in parsed_dates if start <= d <= now]

        result["is_on_list"] = bool(recent_dates)
        result["recent_count"] = len(recent_dates) if recent_dates else int(len(matched))
        result["latest_date"] = max(recent_dates).date().isoformat() if recent_dates else (
            max(parsed_dates).date().isoformat() if parsed_dates else None
        )
        result["status"] = "ok"
        result["source_chain"].append(f"dragon_tiger:{source}")
        return result
