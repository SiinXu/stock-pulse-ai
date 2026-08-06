# -*- coding: utf-8 -*-
"""Stable Actions run-outcome codes shared by Daily Summary and Config Check (#850/#847)."""

from __future__ import annotations

from typing import Dict, Mapping, Optional, Tuple

OUTCOME_SUCCESS = "success"
OUTCOME_SKIPPED = "skipped"
OUTCOME_PARTIAL = "partial"
OUTCOME_FAILED = "failed"

CODE_SUCCESS = "success"
CODE_PARTIAL = "partial"
CODE_MISSING_LLM = "missing_llm"
CODE_MISSING_WATCHLIST = "missing_watchlist"
CODE_NON_TRADING_DAY = "non_trading_day"
CODE_DATA_SOURCE = "data_source"
CODE_TIMEOUT = "timeout"
CODE_QUOTA = "quota"
CODE_PROVIDER_DOWN = "provider_down"
CODE_UNKNOWN = "unknown"

LLM_SECRET_ENV_KEYS: Tuple[str, ...] = (
    "GEMINI_API_KEY", "GEMINI_API_KEYS",
    "LLM_ZHIPU_API_KEY", "LLM_ZHIPU_API_KEYS",
    "LLM_SILICONFLOW_API_KEY", "LLM_SILICONFLOW_API_KEYS",
    "DEEPSEEK_API_KEY", "DEEPSEEK_API_KEYS",
    "OPENAI_API_KEY", "OPENAI_API_KEYS",
    "ANTHROPIC_API_KEY", "ANTHROPIC_API_KEYS",
    "AIHUBMIX_KEY", "LITELLM_API_KEY",
    "LLM_PRIMARY_API_KEY", "LLM_PRIMARY_API_KEYS",
    "ANSPIRE_API_KEYS", "LLM_ANSPIRE_API_KEY", "LLM_ANSPIRE_API_KEYS",
    "LLM_DEEPSEEK_API_KEY", "LLM_DEEPSEEK_API_KEYS",
    "LLM_OPENAI_API_KEY", "LLM_OPENAI_API_KEYS",
    "LLM_GEMINI_API_KEY", "LLM_GEMINI_API_KEYS",
    "LLM_MOONSHOT_API_KEY", "LLM_MOONSHOT_API_KEYS",
    "LLM_DASHSCOPE_API_KEY", "LLM_DASHSCOPE_API_KEYS",
    "LLM_MINIMAX_API_KEY", "LLM_MINIMAX_API_KEYS",
    "LLM_VOLCENGINE_API_KEY", "LLM_VOLCENGINE_API_KEYS",
    "LLM_OPENROUTER_API_KEY", "LLM_OPENROUTER_API_KEYS",
    "LLM_HERMES_API_KEY",
)

RECOMMENDED_LLM_SECRET_NAMES: Tuple[str, ...] = (
    "GEMINI_API_KEY", "LLM_ZHIPU_API_KEY", "LLM_SILICONFLOW_API_KEY",
    "DEEPSEEK_API_KEY", "OPENAI_API_KEY",
)

WATCHLIST_ENV_KEYS: Tuple[str, ...] = ("STOCK_LIST", "STOCK_LIST_CONFIG")

_CAUSE_COPY: Dict[str, Dict[str, str]] = {
    CODE_SUCCESS: {
        "zh": "运行成功。报告已生成（如已配置通知渠道，报告推送逻辑与现网一致）。",
        "en": "Run succeeded. Reports were generated (report push behavior is unchanged when channels are configured).",
        "action_zh": "在 Actions Artifacts 中下载 analysis-reports，或查看已配置的通知渠道。",
        "action_en": "Download the analysis-reports artifact or check configured notification channels.",
    },
    CODE_PARTIAL: {
        "zh": "部分股票成功，部分失败或跳过。",
        "en": "Some symbols succeeded; others failed or were skipped.",
        "action_zh": "下载 logs Artifact 查看失败股票原因；可先跑 Config Check 确认 Key 与自选。",
        "action_en": "Download the logs artifact for failed symbols; run Config Check to verify keys and watchlist.",
    },
    CODE_MISSING_LLM: {
        "zh": "未检测到可用模型 Key（GEMINI / LLM_ZHIPU / LLM_SILICONFLOW 等）。",
        "en": "No usable model API key detected (GEMINI / LLM_ZHIPU / LLM_SILICONFLOW, etc.).",
        "action_zh": "到 Settings → Secrets and variables → Actions 添加至少一种推荐 Key（如 GEMINI_API_KEY、LLM_ZHIPU_API_KEY 或 LLM_SILICONFLOW_API_KEY），建议先跑 Config Check。",
        "action_en": "Add at least one recommended key under Settings → Secrets and variables → Actions (e.g. GEMINI_API_KEY, LLM_ZHIPU_API_KEY, or LLM_SILICONFLOW_API_KEY). Prefer Config Check first.",
    },
    CODE_MISSING_WATCHLIST: {
        "zh": "未配置自选 STOCK_LIST（或 STOCK_LIST_CONFIG）。",
        "en": "Watchlist STOCK_LIST (or STOCK_LIST_CONFIG) is not configured.",
        "action_zh": "在 Actions Variables/Secrets 中设置 STOCK_LIST（逗号分隔代码，如 600519,hk00700,AAPL）。",
        "action_en": "Set STOCK_LIST in Actions Variables/Secrets (comma-separated codes, e.g. 600519,hk00700,AAPL).",
    },
    CODE_NON_TRADING_DAY: {
        "zh": "非交易日已跳过分析；可用手动触发时勾选 force_run 强制执行。",
        "en": "Skipped because relevant markets are closed; use workflow force_run to override.",
        "action_zh": "若需休市日仍跑：Actions → StockPulse Daily Analysis → Run workflow → 勾选 force_run。",
        "action_en": "To run on a closed day: Actions → StockPulse Daily Analysis → Run workflow → enable force_run.",
    },
    CODE_DATA_SOURCE: {
        "zh": "行情或数据源暂时不可用。",
        "en": "Market data source temporarily unavailable.",
        "action_zh": "下载 logs Artifact 查看具体源；可稍后重试，或检查 TUSHARE_TOKEN / TICKFLOW_API_KEY 等可选增强源。",
        "action_en": "Download the logs artifact for the provider; retry later, or check optional TUSHARE_TOKEN / TICKFLOW_API_KEY.",
    },
    CODE_TIMEOUT: {
        "zh": "分析超时（达到 ANALYSIS_TIMEOUT_MINUTES）。",
        "en": "Analysis timed out (hit ANALYSIS_TIMEOUT_MINUTES).",
        "action_zh": "减少 STOCK_LIST 数量，或提高仓库 Variable ANALYSIS_TIMEOUT_MINUTES 后重试。",
        "action_en": "Reduce STOCK_LIST size or raise repository Variable ANALYSIS_TIMEOUT_MINUTES, then retry.",
    },
    CODE_QUOTA: {
        "zh": "模型或数据源配额/限流可能已触发。",
        "en": "Model or data-source quota / rate limit may have been hit.",
        "action_zh": "检查对应厂商控制台配额与账单；可换备用 Key、降低并发 MAX_WORKERS，或错峰重试。",
        "action_en": "Check the provider console quota/billing; rotate a backup key, lower MAX_WORKERS, or retry off-peak.",
    },
    CODE_PROVIDER_DOWN: {
        "zh": "上游提供商暂时不可用。",
        "en": "Upstream provider temporarily unavailable.",
        "action_zh": "查看 logs Artifact 中的 provider 名称；稍后重试或切换 GENERATION_FALLBACK_BACKEND / 备用 LLM Key。",
        "action_en": "Inspect the provider name in the logs artifact; retry later or switch GENERATION_FALLBACK_BACKEND / a backup LLM key.",
    },
    CODE_UNKNOWN: {
        "zh": "运行失败；原因未自动归类。",
        "en": "Run failed; cause was not auto-classified.",
        "action_zh": "下载 logs Artifact 查看 traceback，或先跑 Config Check；仍不明可开 Issue。",
        "action_en": "Download the logs artifact for the traceback, or run Config Check first; open an Issue if still unclear.",
    },
}


def get_cause_copy(code: str) -> Mapping[str, str]:
    normalized = (code or "").strip().lower() or CODE_UNKNOWN
    return _CAUSE_COPY.get(normalized, _CAUSE_COPY[CODE_UNKNOWN])


def format_cause_headline(code: str, *, language: str = "zh") -> str:
    copy = get_cause_copy(code)
    key = "zh" if language.lower().startswith("zh") else "en"
    return str(copy.get(key) or copy["zh"])


def format_cause_action(code: str, *, language: str = "zh") -> str:
    copy = get_cause_copy(code)
    if language.lower().startswith("zh"):
        return str(copy.get("action_zh") or copy.get("action_en") or "")
    return str(copy.get("action_en") or copy.get("action_zh") or "")


def format_bilingual_cause_block(code: str) -> str:
    copy = get_cause_copy(code)
    return "\n".join([
        f"**原因 / Cause (`{code}`)**",
        f"- 中文：{copy['zh']}",
        f"- English: {copy['en']}",
        f"- 下一步 / Next：{copy['action_zh']}",
        f"- Next step: {copy['action_en']}",
    ])


def env_value_present(raw: Optional[str]) -> bool:
    return bool((raw or "").strip())


def has_any_llm_secret(environ: Mapping[str, str]) -> bool:
    try:
        from src.services.actions_config_check import discover_llm_key_names
        if discover_llm_key_names(environ):
            return True
    except Exception:  # broad-exception: cleanup - optional Config Check import when #847 is absent
        pass
    for key in LLM_SECRET_ENV_KEYS:
        if env_value_present(environ.get(key)):
            return True
    if env_value_present(environ.get("LITELLM_CONFIG_YAML")) and env_value_present(environ.get("LITELLM_MODEL")):
        return True
    return False


def has_watchlist_configured(environ: Mapping[str, str]) -> bool:
    return any(env_value_present(environ.get(k)) for k in WATCHLIST_ENV_KEYS)


def list_missing_recommended_llm_keys(environ: Mapping[str, str]) -> Tuple[str, ...]:
    return tuple(n for n in RECOMMENDED_LLM_SECRET_NAMES if not env_value_present(environ.get(n)))
