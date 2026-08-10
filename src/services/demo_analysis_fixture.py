# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Offline demo analysis fixture for zero-config first success (#796).

The payload is intentionally static: fixed symbols, fixed narrative, and an
explicit sample marker so clients can never present it as a live analysis.
No network, LLM, or paid data path is used.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Mapping

DEMO_ANALYSIS_SCHEMA_VERSION = 1
DEMO_QUERY_ID = "demo-sample-analysis-v1"
DEMO_STOCK_CODE = "600519"
DEMO_STOCK_NAME_ZH = "贵州茅台（示例）"
DEMO_STOCK_NAME_EN = "Kweichow Moutai (sample)"
DEMO_STOCK_NAME_KO = "구이저우 마오타이(예시)"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _copy_for_language(report_language: str) -> Mapping[str, str]:
    lang = str(report_language or "zh").strip().lower()
    if lang.startswith("en"):
        return {
            "stock_name": DEMO_STOCK_NAME_EN,
            "analysis_summary": (
                "SAMPLE DATA — This is a built-in offline demonstration, not a live market analysis. "
                "The narrative uses fixed fixture text so you can explore the report layout without "
                "API keys or a local model."
            ),
            "operation_advice": (
                "SAMPLE DATA — Try a real run after applying a local Ollama profile or a cloud key. "
                "Do not treat this sample as investment advice."
            ),
            "action_label": "Watch (sample)",
            "trend_prediction": "Sample trend narrative only — not live.",
            "sample_banner": "Sample data — not a live analysis",
            "sample_disclaimer": (
                "This demo analysis is offline fixture content. Prices, scores, and advice are "
                "illustrative and must not be used for trading decisions."
            ),
        }
    if lang.startswith("ko"):
        return {
            "stock_name": DEMO_STOCK_NAME_KO,
            "analysis_summary": (
                "【예시 데이터】내장된 오프라인 데모이며 실시간 시세나 실제 AI 분석이 아닙니다. "
                "API 키나 로컬 모델 없이 보고서 화면을 살펴볼 수 있도록 고정된 문구를 사용합니다."
            ),
            "operation_advice": (
                "【예시 데이터】로컬 Ollama 또는 클라우드 키를 설정한 뒤 실제 분석을 실행하세요. "
                "이 예시를 투자 조언으로 사용하지 마세요."
            ),
            "action_label": "관망(예시)",
            "trend_prediction": "예시 추세 설명 — 실시간이 아닙니다.",
            "sentiment_label": "중립",
            "sample_banner": "예시 데이터 — 실시간 분석 아님",
            "sample_disclaimer": (
                "이 데모는 고정된 오프라인 예시입니다. 가격, 점수 및 의견은 화면 설명용이며 "
                "거래 결정에 사용해서는 안 됩니다."
            ),
        }
    return {
        "stock_name": DEMO_STOCK_NAME_ZH,
        "analysis_summary": (
            "【示例数据】这是内置的离线演示分析，不是实时行情或真实 AI 结论。"
            "固定文案仅用于在无 API Key、无本地模型时体验报告界面。"
        ),
        "operation_advice": (
            "【示例数据】配置本地 Ollama 或云端 Key 后，再运行真实分析。"
            "请勿将本示例当作投资建议。"
        ),
        "action_label": "观望（示例）",
        "trend_prediction": "示例趋势说明 — 非实时。",
        "sentiment_label": "中性",
        "sample_banner": "示例数据 — 非实时分析",
        "sample_disclaimer": (
            "本演示分析为离线固定样例。价格、评分与操作建议仅用于界面演示，"
            "不得用于交易决策。"
        ),
    }


def build_demo_analysis(*, report_language: str = "zh") -> Dict[str, Any]:
    """Return a JSON-serializable offline demo analysis payload.

    Always sets ``is_sample=True`` and bilingual sample banners so UI layers can
    render an unmistakable sample marker.
    """
    lang = str(report_language or "zh").strip().lower() or "zh"
    if lang not in {"zh", "en", "ko"}:
        raise ValueError("report_language must be one of: zh, en, ko")
    copy = _copy_for_language(lang)
    created_at = _utc_now_iso()
    report = {
        "meta": {
            "query_id": DEMO_QUERY_ID,
            "stock_code": DEMO_STOCK_CODE,
            "stock_name": copy["stock_name"],
            "report_type": "brief",
            "report_language": lang,
            "created_at": created_at,
            "current_price": None,
            "change_pct": None,
            "model_used": "demo-fixture/offline",
        },
        "summary": {
            "analysis_summary": copy["analysis_summary"],
            "operation_advice": copy["operation_advice"],
            "action": "watch",
            "action_label": copy["action_label"],
            "trend_prediction": copy["trend_prediction"],
            "sentiment_score": 50,
            "sentiment_label": copy.get("sentiment_label", "Neutral"),
        },
        "strategy": {
            "ideal_buy": None,
            "secondary_buy": None,
            "stop_loss": None,
            "take_profit": None,
        },
        "details": {
            "news": [],
            "technical": [],
        },
    }
    return {
        "schema_version": DEMO_ANALYSIS_SCHEMA_VERSION,
        "is_sample": True,
        "sample_banner": copy["sample_banner"],
        "sample_disclaimer": copy["sample_disclaimer"],
        "query_id": DEMO_QUERY_ID,
        "stock_code": DEMO_STOCK_CODE,
        "stock_name": copy["stock_name"],
        "created_at": created_at,
        "report": report,
    }


__all__ = [
    "DEMO_ANALYSIS_SCHEMA_VERSION",
    "DEMO_QUERY_ID",
    "DEMO_STOCK_CODE",
    "build_demo_analysis",
]
