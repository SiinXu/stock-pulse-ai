# -*- coding: utf-8 -*-
"""ETF analysis semantics: instrument identity, N/A equity metrics, prompt path.

Analysis-layer contract for Issue #173. Does not own data-validation PE/PB
calibration (that remains the data-validation layer / #185). Quote/history
routing stays in data_provider; this module only projects ETF meaning for
analysis prompts and context.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from src.report_language import normalize_report_language

ETF_ANALYSIS_SCHEMA_VERSION = "etf_analysis.v1"

# Liquid A-share ETFs used for docs, fixtures, and tracking-target bootstrap.
# Values are display names of the tracked index/theme, not guaranteed provider IDs.
LIQUID_A_SHARE_ETF_TRACKING: Dict[str, str] = {
    "510050": "上证50",
    "510300": "沪深300",
    "510500": "中证500",
    "159915": "创业板指",
    "159919": "沪深300",
    "159922": "中证500",
    "512100": "中证1000",
    "512880": "证券公司",
    "512000": "证券公司",
    "512480": "半导体",
    "515030": "新能源车",
    "588000": "科创50",
    "588080": "科创50",
    "159845": "中证1000",
    "563230": "自由现金流",
}

# Equity-only metrics that must not be hard-calculated for ETFs.
ETF_INAPPLICABLE_EQUITY_METRICS: Tuple[str, ...] = (
    "pe_ratio",
    "pb_ratio",
    "roe",
    "earnings",
    "financial_report",
    "company_fundamentals",
    "chip_distribution",
    "dragon_tiger",
)

_NOT_APPLICABLE = "not_applicable"
_NOT_AVAILABLE = "not_available"

# Name tokens that often encode the tracked index/theme before the ETF suffix.
_TRACKING_NAME_MARKERS: Tuple[str, ...] = (
    "ETF",
    "交易型开放式指数证券投资基金",
    "交易型开放式指数基金",
    "指数基金",
    "联接",
)


# Mirror data_provider.symbol_normalization.ETF_PREFIXES / SearchService._A_ETF_PREFIXES.
# Kept local so analysis semantics stay available without importing the full data_provider package.
_A_SHARE_ETF_PREFIXES: Tuple[str, ...] = ("51", "52", "56", "58", "15", "16", "18")


def is_a_share_etf_code(stock_code: Optional[str]) -> bool:
    """Return whether *stock_code* matches the shared A-share ETF prefix contract."""
    raw = str(stock_code or "").strip()
    if not raw:
        return False
    try:
        from data_provider.symbol_normalization import _is_etf_code

        return bool(_is_etf_code(raw))
    except Exception:
        # Fail-open local mirror of the shared prefix rule when provider package is unavailable.
        code = raw.split(".")[0]
        if code.upper().endswith(("SH", "SZ", "SS")):
            code = code[:-2] if code[-2:].isalpha() else code
        return code.isdigit() and len(code) == 6 and code.startswith(_A_SHARE_ETF_PREFIXES)


def is_etf_instrument(
    stock_code: Optional[str],
    stock_name: Optional[str] = None,
) -> bool:
    """True when analysis should use the ETF instrument path.

    Prefers the shared A-share ETF code rule; falls back to the existing
    index/ETF news heuristic for offshore names (SPY, VOO, etc.).
    """
    if is_a_share_etf_code(stock_code):
        return True
    try:
        from src.search_service import SearchService

        return bool(SearchService.is_index_or_etf(stock_code or "", stock_name or ""))
    except Exception:
        return False


def _normalize_code(stock_code: Optional[str]) -> str:
    raw = str(stock_code or "").strip()
    if not raw:
        return ""
    try:
        from data_provider.symbol_normalization import normalize_stock_code

        return normalize_stock_code(raw)
    except Exception:
        return raw.split(".")[0].upper() if "." in raw else raw


def infer_tracking_target(
    stock_code: Optional[str],
    stock_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Infer a best-effort tracking index/theme for prompt context.

    Never invents a provider index ID. Status is ``ok`` only when the name or
    liquid bootstrap map yields a non-empty target label.
    """
    code = _normalize_code(stock_code)
    name = str(stock_name or "").strip()

    mapped = LIQUID_A_SHARE_ETF_TRACKING.get(code)
    if mapped:
        return {
            "status": "ok",
            "label": mapped,
            "source": "liquid_bootstrap",
            "confidence": "high",
        }

    if name:
        label = name
        for marker in _TRACKING_NAME_MARKERS:
            idx = label.find(marker)
            if idx > 0:
                label = label[:idx]
                break
        label = label.strip(" -_·/|（）()[]")
        # Drop common manager prefixes when still longer than the theme.
        for prefix in ("华夏", "易方达", "华泰柏瑞", "南方", "嘉实", "广发", "工银", "博时", "富国", "汇添富"):
            if label.startswith(prefix) and len(label) > len(prefix) + 1:
                label = label[len(prefix) :].strip()
                break
        if label and label not in {"ETF", "基金", name}:
            return {
                "status": "ok",
                "label": label,
                "source": "name_heuristic",
                "confidence": "medium",
            }

    return {
        "status": _NOT_AVAILABLE,
        "label": None,
        "source": "unavailable",
        "confidence": "none",
        "note": "tracking_target_not_resolved",
    }


def _safe_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return number


def compute_premium_discount(
    price: Any = None,
    iopv: Any = None,
    nav: Any = None,
) -> Dict[str, Any]:
    """Premium/discount vs IOPV (preferred) or NAV when both sides are numeric."""
    px = _safe_float(price)
    ref = _safe_float(iopv)
    ref_kind = "iopv"
    if ref is None or ref <= 0:
        ref = _safe_float(nav)
        ref_kind = "nav"
    if px is None or ref is None or ref <= 0:
        return {
            "status": _NOT_AVAILABLE,
            "premium_discount_pct": None,
            "reference": None,
            "reference_kind": None,
            "note": "premium_requires_price_and_iopv_or_nav",
        }
    pct = round((px - ref) / ref * 100.0, 4)
    return {
        "status": "ok",
        "premium_discount_pct": pct,
        "reference": ref,
        "reference_kind": ref_kind,
        "note": None,
    }


def infer_holdings_exposure(
    stock_code: Optional[str],
    stock_name: Optional[str] = None,
    tracking: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Coarse holdings-exposure theme for ETF analysis (not full look-through).

    Full constituent lists are out of the public provider contract for most
    free paths; analysis must treat missing constituents as not_available.
    """
    tracking = tracking or {}
    label = str(tracking.get("label") or "").strip()
    name = str(stock_name or "").strip()
    text = f"{label} {name}".upper()

    broad_markers = (
        "沪深300",
        "上证50",
        "中证500",
        "中证1000",
        "创业板",
        "科创50",
        "中证全指",
        "A500",
        "HS300",
        "CSI300",
        "CSI500",
        "CSI1000",
    )
    sector_markers = (
        "证券",
        "银行",
        "半导体",
        "芯片",
        "新能源",
        "军工",
        "医药",
        "消费",
        "白酒",
        "煤炭",
        "有色",
        "地产",
        "科技",
        "人工智能",
        "AI",
        "自由现金流",
    )

    if any(marker.upper() in text or marker in f"{label}{name}" for marker in broad_markers):
        exposure_class = "broad_index"
    elif any(marker.upper() in text or marker in f"{label}{name}" for marker in sector_markers):
        exposure_class = "sector_theme"
    elif label:
        exposure_class = "theme_unknown"
    else:
        exposure_class = "unknown"

    return {
        "status": "ok" if label or name else _NOT_AVAILABLE,
        "exposure_class": exposure_class,
        "theme_label": label or None,
        "constituents": [],
        "constituents_status": _NOT_AVAILABLE,
        "note": "full_holdings_lookthrough_not_in_public_provider_contract",
    }


def equity_metrics_applicability() -> Dict[str, str]:
    """Map of equity metrics that are not applicable to ETF analysis."""
    return {metric: _NOT_APPLICABLE for metric in ETF_INAPPLICABLE_EQUITY_METRICS}


def build_etf_analysis_context(
    stock_code: Optional[str],
    stock_name: Optional[str] = None,
    *,
    realtime: Optional[Mapping[str, Any]] = None,
    is_index_etf: Optional[bool] = None,
) -> Dict[str, Any]:
    """Build the structured ETF analysis projection for pipeline context.

    Non-ETF symbols return ``status=not_applicable`` so callers can attach the
    block unconditionally without branching report schemas.
    """
    code = _normalize_code(stock_code)
    name = str(stock_name or "").strip()
    realtime = realtime if isinstance(realtime, Mapping) else {}

    etf = is_etf_instrument(code or stock_code, name)
    if is_index_etf is True:
        etf = True
    if not etf:
        return {
            "schema_version": ETF_ANALYSIS_SCHEMA_VERSION,
            "status": _NOT_APPLICABLE,
            "instrument_type": "equity",
            "is_etf": False,
            "code": code or str(stock_code or "").strip(),
            "name": name or None,
        }

    a_share = is_a_share_etf_code(code or stock_code)
    tracking = infer_tracking_target(code or stock_code, name)
    premium = compute_premium_discount(
        price=realtime.get("price"),
        iopv=realtime.get("iopv") or realtime.get("IOPV"),
        nav=realtime.get("nav") or realtime.get("unit_nav") or realtime.get("净值"),
    )
    holdings = infer_holdings_exposure(code or stock_code, name, tracking)
    missing: List[str] = []
    if tracking.get("status") != "ok":
        missing.append("tracking_target")
    if premium.get("status") != "ok":
        missing.append("premium_discount")
    if holdings.get("constituents_status") != "ok":
        missing.append("holdings_constituents")

    return {
        "schema_version": ETF_ANALYSIS_SCHEMA_VERSION,
        "status": "ok",
        "instrument_type": "etf",
        "is_etf": True,
        "is_a_share_etf": a_share,
        "code": code or str(stock_code or "").strip(),
        "name": name or None,
        "tracking_target": tracking,
        "premium_discount": premium,
        "holdings_exposure": holdings,
        "equity_metrics": equity_metrics_applicability(),
        "analysis_focus": [
            "tracking_index_or_theme",
            "premium_discount_to_iopv_or_nav",
            "liquidity_and_turnover",
            "holdings_theme_exposure",
            "index_constituent_news_not_issuer_ops",
        ],
        "data_quality": {
            "missing_fields": missing,
        },
        "report_structure": "shared_with_equity_dashboard",
    }


def format_etf_metric_display(
    metric: str,
    value: Any,
    *,
    is_etf: bool,
    language: str = "zh",
) -> str:
    """Render a metric cell: explicit not_applicable for equity-only fields on ETFs."""
    language = normalize_report_language(language)
    if is_etf and metric in ETF_INAPPLICABLE_EQUITY_METRICS:
        if language == "en":
            return "not_applicable (ETF)"
        if language == "ko":
            return "해당 없음 (ETF)"
        return "不适用（ETF）"
    if value is None or value == "":
        return "N/A"
    return str(value)


def format_etf_analysis_prompt_section(
    context: Any,
    report_language: str = "zh",
) -> str:
    """Render the ETF-specific analysis section for the shared report prompt."""
    if not isinstance(context, Mapping):
        return ""
    if context.get("schema_version") != ETF_ANALYSIS_SCHEMA_VERSION:
        return ""
    if not context.get("is_etf") or context.get("status") == _NOT_APPLICABLE:
        return ""

    language = normalize_report_language(report_language)
    tracking = context.get("tracking_target") if isinstance(context.get("tracking_target"), Mapping) else {}
    premium = context.get("premium_discount") if isinstance(context.get("premium_discount"), Mapping) else {}
    holdings = context.get("holdings_exposure") if isinstance(context.get("holdings_exposure"), Mapping) else {}
    missing = []
    data_quality = context.get("data_quality")
    if isinstance(data_quality, Mapping):
        raw_missing = data_quality.get("missing_fields")
        if isinstance(raw_missing, Sequence) and not isinstance(raw_missing, (str, bytes)):
            missing = [str(item) for item in raw_missing if str(item).strip()]

    tracking_label = tracking.get("label") or (
        "unavailable" if language == "en" else ("없음" if language == "ko" else "不可用")
    )
    tracking_status = tracking.get("status") or _NOT_AVAILABLE
    premium_status = premium.get("status") or _NOT_AVAILABLE
    premium_pct = premium.get("premium_discount_pct")
    premium_text = (
        f"{premium_pct}%"
        if premium_status == "ok" and premium_pct is not None
        else ("not_available" if language == "en" else ("불가" if language == "ko" else "不可用"))
    )
    exposure_class = holdings.get("exposure_class") or "unknown"
    theme_label = holdings.get("theme_label") or tracking_label

    if language == "en":
        lines = [
            "",
            "## ETF Analysis Path",
            f"- Instrument type: **ETF** (`{context.get('code', '')}`)",
            f"- Tracking target: {tracking_label} (status={tracking_status})",
            f"- Premium/discount vs IOPV/NAV: {premium_text} (status={premium_status})",
            f"- Holdings exposure class: {exposure_class}; theme={theme_label}",
            f"- Full holdings look-through: {holdings.get('constituents_status', _NOT_AVAILABLE)}",
            "- Equity-only metrics (PE/PB/ROE/earnings/financial report/company fundamentals/"
            "chip distribution/Dragon Tiger list): **not_applicable** — do not invent or hard-calculate.",
            "- Focus: index/theme path, tracking quality, premium/discount, liquidity, and "
            "constituent-basket news. Do not treat fund-manager lawsuits or issuer ops as ETF risk.",
            "- Report structure: keep the same decision-dashboard JSON schema as single-stock reports.",
        ]
        if missing:
            lines.append(f"- Missing evidence: {', '.join(missing)}")
        return "\n".join(lines) + "\n"

    if language == "ko":
        lines = [
            "",
            "## ETF 분석 경로",
            f"- 상품 유형: **ETF** (`{context.get('code', '')}`)",
            f"- 추적 대상: {tracking_label} (status={tracking_status})",
            f"- IOPV/NAV 대비 괴리율: {premium_text} (status={premium_status})",
            f"- 보유 노출 유형: {exposure_class}; theme={theme_label}",
            f"- 전체 보유 종목 관통: {holdings.get('constituents_status', _NOT_AVAILABLE)}",
            "- 주식 전용 지표(PE/PB/ROE/실적/재무제표/회사 펀더멘털/칩 분포 등): "
            "**해당 없음(not_applicable)** — 추정·강제 계산 금지.",
            "- 초점: 지수/테마 경로, 추적 품질, 괴리율, 유동성, 구성 종목 바스켓 뉴스. "
            "운용사 소송·발행사 경영 이슈를 ETF 리스크로 쓰지 말 것.",
            "- 보고서 구조: 개별 주식과 동일한 decision-dashboard JSON 스키마 유지.",
        ]
        if missing:
            lines.append(f"- 결측 증거: {', '.join(missing)}")
        return "\n".join(lines) + "\n"

    lines = [
        "",
        "## ETF 专属分析路径",
        f"- 品种类型：**ETF**（`{context.get('code', '')}`）",
        f"- 跟踪标的：{tracking_label}（status={tracking_status}）",
        f"- 相对 IOPV/净值溢价率：{premium_text}（status={premium_status}）",
        f"- 持仓暴露类型：{exposure_class}；主题={theme_label}",
        f"- 完整持仓穿透：{holdings.get('constituents_status', _NOT_AVAILABLE)}",
        "- 个股专属指标（PE/PB/ROE/财报/公司基本面/筹码分布/龙虎榜）："
        "**不适用（not_applicable）**，禁止编造或硬算。",
        "- 分析焦点：跟踪指数/主题、跟踪质量、溢价折价、流动性、成分篮子新闻；"
        "不得将基金管理人诉讼或发行方经营风险当作 ETF 本身利空。",
        "- 报告结构：与个股共用同一决策仪表盘 JSON 结构，不另起报告模板。",
    ]
    if missing:
        lines.append(f"- 缺失证据：{', '.join(missing)}")
    return "\n".join(lines) + "\n"


def format_etf_focus_points(report_language: str = "zh") -> str:
    """ETF-specific '重点关注' bullets that replace equity-centric questions."""
    language = normalize_report_language(report_language)
    if language == "en":
        return """
### Focus points (ETF path — must answer explicitly):
1. What index/theme does this ETF track, and is current price action aligned with that basket?
2. Is premium/discount vs IOPV/NAV available? If available, is the gap extreme enough to matter for entry?
3. Are liquidity and turnover healthy enough for the intended size?
4. What sector/theme exposure does the holdings basket imply (even without full constituents)?
5. Any material news on the tracked index/theme or major constituents? Ignore fund-manager issuer noise.
"""
    if language == "ko":
        return """
### 중점 확인 (ETF 경로 — 반드시 명시 답변):
1. 이 ETF가 추적하는 지수/테마는 무엇이며, 현재 가격 움직임이 해당 바스켓과 정렬되는가?
2. IOPV/NAV 대비 괴리율을 사용할 수 있는가? 사용 가능하다면 진입에 유의미할 정도로 큰가?
3. 유동성과 회전율이 의도한 규모에 충분한가?
4. 보유 바스켓이 함의하는 섹터/테마 노출은 무엇인가(전체 구성 종목이 없어도)?
5. 추적 지수/테마 또는 주요 구성 종목에 중대 뉴스가 있는가? 운용사 발행사 잡음은 무시.
"""
    return """
### 重点关注（ETF 路径 — 必须明确回答）：
1. ❓ 该 ETF 跟踪的指数/主题是什么？当前价格走势是否与该篮子一致？
2. ❓ 相对 IOPV/净值的溢价折价是否可得？若可得，是否大到影响进出场？
3. ❓ 流动性与换手是否足以支撑拟交易规模？
4. ❓ 持仓篮子隐含的行业/主题暴露是什么（即使没有完整成分列表）？
5. ❓ 跟踪指数/主题或主要成分是否有重大消息？忽略基金管理人/发行方噪声。
"""
