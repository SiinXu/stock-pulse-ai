# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Project valuation estimates into report and prompt surfaces (issue #238).

Projection is **optional**: missing or empty valuation payloads yield ``None``
so callers can omit the section without empty placeholders. Existing analysis
results without a valuation block remain valid.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional


def extract_valuation_payload(source: Any) -> Optional[Mapping[str, Any]]:
    """Prefer ``dashboard.valuation``, then top-level ``valuation``."""
    if source is None:
        return None
    if isinstance(source, Mapping):
        dashboard = source.get("dashboard")
        if isinstance(dashboard, Mapping) and isinstance(dashboard.get("valuation"), Mapping):
            return dashboard.get("valuation")  # type: ignore[return-value]
        if isinstance(source.get("valuation"), Mapping):
            return source.get("valuation")  # type: ignore[return-value]
        return None
    dashboard = getattr(source, "dashboard", None)
    if isinstance(dashboard, Mapping) and isinstance(dashboard.get("valuation"), Mapping):
        return dashboard.get("valuation")  # type: ignore[return-value]
    nested = getattr(source, "valuation", None)
    if isinstance(nested, Mapping):
        return nested
    return None


def _safe_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _has_reportable_content(estimate: Mapping[str, Any]) -> bool:
    dcf = _safe_mapping(estimate.get("dcf"))
    relative = _safe_mapping(estimate.get("relative"))
    if dcf.get("status") or relative.get("status"):
        return True
    return bool(estimate.get("status") or estimate.get("schema_version"))


def project_valuation_for_report(
    estimate: Optional[Mapping[str, Any]],
    *,
    language: str = "zh",
) -> Optional[dict[str, Any]]:
    """Build a template-safe valuation projection, or ``None`` when absent."""
    if not isinstance(estimate, Mapping) or not estimate:
        return None
    if not _has_reportable_content(estimate):
        return None

    dcf = _safe_mapping(estimate.get("dcf"))
    relative = _safe_mapping(estimate.get("relative"))
    assumptions = _safe_mapping(dcf.get("assumptions"))
    sensitivity = _safe_mapping(dcf.get("sensitivity"))
    market = _safe_mapping(dcf.get("market"))
    ev_ebitda = _safe_mapping(relative.get("ev_ebitda"))
    relative_target = _safe_mapping(relative.get("target"))
    premium = _safe_mapping(relative.get("premium_discount"))
    implied = _safe_mapping(relative.get("implied_prices"))

    lang = (language or "zh").strip().lower()
    is_en = lang.startswith("en")
    is_ko = lang.startswith("ko")

    if is_en:
        status_labels = {
            "ok": "ok",
            "partial": "partial",
            "insufficient_fundamentals": "insufficient fundamentals",
            "invalid_assumptions": "invalid assumptions",
            "disabled": "disabled",
        }
    elif is_ko:
        status_labels = {
            "ok": "정상",
            "partial": "부분",
            "insufficient_fundamentals": "기본 데이터 부족",
            "invalid_assumptions": "가정 무효",
            "disabled": "비활성",
        }
    else:
        status_labels = {
            "ok": "可用",
            "partial": "部分可用",
            "insufficient_fundamentals": "基本面不足",
            "invalid_assumptions": "假设无效",
            "disabled": "未启用",
        }

    overall = str(estimate.get("status") or dcf.get("status") or relative.get("status") or "")
    dcf_status = str(dcf.get("status") or "")
    relative_status = str(relative.get("status") or "")
    sensitivity_rows = sensitivity.get("rows")
    if not isinstance(sensitivity_rows, list):
        sensitivity_rows = []

    return {
        "present": True,
        "status": overall,
        "status_label": status_labels.get(overall, overall or "—"),
        "stock_code": estimate.get("stock_code"),
        "disclaimer": estimate.get("disclaimer"),
        "dcf": {
            "status": dcf_status,
            "status_label": status_labels.get(dcf_status, dcf_status or "—"),
            "equity_value": dcf.get("equity_value"),
            "enterprise_value": dcf.get("enterprise_value"),
            "intrinsic_value_per_share": dcf.get("intrinsic_value_per_share"),
            "upside_vs_price_pct": market.get("upside_vs_price_pct"),
            "current_price": market.get("current_price"),
            "assumptions": {
                "base_fcf": assumptions.get("base_fcf"),
                "cash_flow_source": assumptions.get("cash_flow_source"),
                "growth_rate": assumptions.get("growth_rate"),
                "discount_rate": assumptions.get("discount_rate"),
                "terminal_growth_rate": assumptions.get("terminal_growth_rate"),
                "projection_years": assumptions.get("projection_years"),
                "growth_source": assumptions.get("growth_source"),
                "net_debt_assumption": assumptions.get("net_debt_assumption"),
            },
            "sensitivity": {
                "equity_value_low": sensitivity.get("equity_value_low"),
                "equity_value_mid": sensitivity.get("equity_value_mid"),
                "equity_value_high": sensitivity.get("equity_value_high"),
                "row_count": len(sensitivity_rows),
            },
            "message": dcf.get("message"),
        },
        "relative": {
            "status": relative_status,
            "status_label": status_labels.get(relative_status, relative_status or "—"),
            "pe_ratio": relative_target.get("pe_ratio"),
            "pb_ratio": relative_target.get("pb_ratio"),
            "ev_ebitda": relative_target.get("ev_ebitda") or ev_ebitda.get("target_multiple"),
            "ev_ebitda_status": ev_ebitda.get("status"),
            "ev_ebitda_peer_median": ev_ebitda.get("peer_median"),
            "implied_prices": {
                "pe_based": implied.get("pe_based"),
                "pb_based": implied.get("pb_based"),
                "ev_ebitda_equity_value": implied.get("ev_ebitda_equity_value"),
            },
            "premium_discount": {
                "pe_vs_peers_pct": premium.get("pe_vs_peers_pct"),
                "pb_vs_peers_pct": premium.get("pb_vs_peers_pct"),
                "ev_ebitda_vs_peers_pct": premium.get("ev_ebitda_vs_peers_pct"),
            },
            "message": relative.get("message"),
        },
    }


def format_valuation_prompt_block(
    estimate: Optional[Mapping[str, Any]],
    *,
    max_chars: int = 1200,
) -> str:
    """Return a compact English prompt excerpt, or empty string when absent."""
    projection = project_valuation_for_report(estimate, language="en")
    if not projection:
        return ""

    dcf = projection["dcf"]
    relative = projection["relative"]
    assumptions = dcf.get("assumptions") or {}
    sensitivity = dcf.get("sensitivity") or {}
    lines = [
        "Valuation estimate (model research support only; not investment advice):",
        f"- overall_status: {projection.get('status')}",
        f"- stock_code: {projection.get('stock_code') or 'n/a'}",
        (
            f"- dcf_status: {dcf.get('status')}; equity_value: {dcf.get('equity_value')}; "
            f"intrinsic_value_per_share: {dcf.get('intrinsic_value_per_share')}; "
            f"upside_vs_price_pct: {dcf.get('upside_vs_price_pct')}"
        ),
        (
            f"- dcf_assumptions: growth={assumptions.get('growth_rate')}, "
            f"discount={assumptions.get('discount_rate')}, "
            f"terminal_growth={assumptions.get('terminal_growth_rate')}, "
            f"years={assumptions.get('projection_years')}, "
            f"cash_flow_source={assumptions.get('cash_flow_source')}, "
            f"growth_source={assumptions.get('growth_source')}"
        ),
        (
            f"- dcf_sensitivity_equity_range: "
            f"low={sensitivity.get('equity_value_low')}, "
            f"mid={sensitivity.get('equity_value_mid')}, "
            f"high={sensitivity.get('equity_value_high')}"
        ),
        (
            f"- relative_status: {relative.get('status')}; "
            f"pe={relative.get('pe_ratio')}; pb={relative.get('pb_ratio')}; "
            f"ev_ebitda={relative.get('ev_ebitda')} "
            f"(ev_ebitda_status={relative.get('ev_ebitda_status')})"
        ),
        (
            f"- relative_implied: pe_based={relative.get('implied_prices', {}).get('pe_based')}, "
            f"pb_based={relative.get('implied_prices', {}).get('pb_based')}, "
            f"ev_ebitda_equity={relative.get('implied_prices', {}).get('ev_ebitda_equity_value')}"
        ),
    ]
    disclaimer = projection.get("disclaimer")
    if disclaimer:
        lines.append(f"- disclaimer: {disclaimer}")
    text = "\n".join(lines)
    if max_chars > 0 and len(text) > max_chars:
        return text[: max_chars - 1].rstrip() + "…"
    return text
