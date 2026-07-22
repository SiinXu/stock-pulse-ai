# -*- coding: utf-8 -*-
"""AlphaSift service facade and DSA runtime bridge."""

from __future__ import annotations

import importlib
import hashlib
import inspect
import json
import logging
import math
import os
import re
import subprocess
import sys
import threading
import time
from contextvars import ContextVar
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from src.auth import COOKIE_NAME, is_auth_enabled, refresh_auth_state, verify_session
from src.config import Config, DEFAULT_ALPHASIFT_INSTALL_SPEC, get_configured_llm_models
from src.security.outbound_policy import guard_outbound_urls
from src.utils.sanitize import (
    log_safe_exception,
    redact_sensitive_data,
    sanitize_sensitive_text,
)

logger = logging.getLogger(__name__)

ALPHASIFT_DSA_ADAPTER_MODULE = "alphasift.dsa_adapter"
ALPHASIFT_EXPECTED_MISSING_MODULES = frozenset({"alphasift", ALPHASIFT_DSA_ADAPTER_MODULE})
ALLOWED_ALPHASIFT_INSTALL_SPECS = frozenset({DEFAULT_ALPHASIFT_INSTALL_SPEC})
_ALPHASIFT_INSTALL_LOCK = threading.RLock()
ALPHASIFT_MANAGED_LITELLM_PROVIDERS = frozenset({"gemini", "vertex_ai", "anthropic", "openai", "deepseek"})
_ALPHASIFT_RUNTIME_ENV_LOCK = threading.RLock()
DSA_ENRICHMENT_MAX_CANDIDATES = 3
DSA_PRE_RANK_CONTEXT_MAX_CANDIDATES = 3
DSA_ALPHASIFT_LLM_CANDIDATE_MULTIPLIER = 2
DSA_ALPHASIFT_LLM_MAX_CANDIDATES = 12
DSA_ALPHASIFT_DAILY_FETCH_RETRIES = 3
DSA_ALPHASIFT_SNAPSHOT_SOURCE_PRIORITY = "sina,efinance,akshare_em,em_datacenter"
DSA_ALPHASIFT_SNAPSHOT_SOURCE_PRIORITY_WITH_TUSHARE = "tushare,sina,efinance,akshare_em,em_datacenter"
DSA_ALPHASIFT_CANDIDATE_CONTEXT_PROVIDERS = "news,fund_flow,announcement,quote"
DSA_ALPHASIFT_DATA_DIR = Path("data") / "alphasift"
DSA_ALPHASIFT_HOTSPOT_CACHE_PATH = DSA_ALPHASIFT_DATA_DIR / "hotspots.json"
DSA_ALPHASIFT_HOTSPOT_HISTORY_PATH = DSA_ALPHASIFT_DATA_DIR / "hotspot.history.jsonl"
DSA_ALPHASIFT_MIN_HOTSPOT_CACHE_COUNT = 3
DSA_ALPHASIFT_HOTSPOT_DETAIL_CACHE_TTL_SECONDS = 30 * 60
DSA_ALPHASIFT_HOTSPOT_EVENT_SUMMARY_MAX_CHARS = 90
DSA_ALPHASIFT_HOTSPOT_PREFETCH_DETAIL_COUNT = 8
DSA_ALPHASIFT_HOTSPOT_UNAVAILABLE_CODE = "eastmoney_hotspot_unavailable"
DSA_ALPHASIFT_HOTSPOT_UNAVAILABLE_MESSAGE = "热点源连接中断，暂无可用缓存。"
DSA_ALPHASIFT_HOTSPOT_REFRESH_FAILED_CODE = "alphasift_hotspot_refresh_failed"
DSA_ALPHASIFT_HOTSPOT_SOURCE_ERROR_CODE = "alphasift_hotspot_source_error"
DSA_ALPHASIFT_HOTSPOT_DIRECT_FALLBACK_FAILED_CODE = "alphasift_hotspot_direct_fallback_failed"
DSA_ALPHASIFT_HOTSPOT_DIRECT_FALLBACK_USED_CODE = "alphasift_hotspot_direct_fallback_used"
DSA_ALPHASIFT_HOTSPOT_DETAIL_PREFETCH_FAILED_CODE = "alphasift_hotspot_detail_prefetch_failed"
DSA_ALPHASIFT_HOTSPOT_DETAIL_STALE_CACHE_CODE = "alphasift_hotspot_detail_stale_cache"
DSA_ALPHASIFT_HOTSPOT_DETAIL_FALLBACK_CODE = "alphasift_hotspot_detail_fallback"
DSA_ALPHASIFT_HOTSPOT_DETAIL_SOURCE_ERROR_CODE = "alphasift_hotspot_detail_source_error"
DSA_ALPHASIFT_WARNING_CODE = "alphasift_warning"
DSA_ALPHASIFT_ERROR_CODE = "alphasift_error"
DSA_ALPHASIFT_SOURCE_ERROR_CODE = "alphasift_source_error"
DSA_ALPHASIFT_LLM_PARSE_ERROR_CODE = "alphasift_llm_parse_error"
DSA_ALPHASIFT_INTERNAL_ERROR_CODE = "alphasift_internal_error"
_ALPHASIFT_PUBLIC_LIST_DIAGNOSTIC_FIELD_CODES = {
    "errors": DSA_ALPHASIFT_ERROR_CODE,
    "exceptions": DSA_ALPHASIFT_INTERNAL_ERROR_CODE,
    "sourceerrors": DSA_ALPHASIFT_SOURCE_ERROR_CODE,
    "llmparseerrors": DSA_ALPHASIFT_LLM_PARSE_ERROR_CODE,
    "parseerrors": DSA_ALPHASIFT_LLM_PARSE_ERROR_CODE,
    "warnings": DSA_ALPHASIFT_WARNING_CODE,
    "providererrors": DSA_ALPHASIFT_SOURCE_ERROR_CODE,
    "upstreamerrors": DSA_ALPHASIFT_SOURCE_ERROR_CODE,
    "adaptererrors": DSA_ALPHASIFT_ERROR_CODE,
    "errormessages": DSA_ALPHASIFT_ERROR_CODE,
    "errormsgs": DSA_ALPHASIFT_ERROR_CODE,
    "errordetails": DSA_ALPHASIFT_ERROR_CODE,
    "errordescriptions": DSA_ALPHASIFT_ERROR_CODE,
    "lasterrors": DSA_ALPHASIFT_ERROR_CODE,
    "diagnosticerrors": DSA_ALPHASIFT_ERROR_CODE,
    "responseerrors": DSA_ALPHASIFT_ERROR_CODE,
}
_ALPHASIFT_PUBLIC_SCALAR_DIAGNOSTIC_FIELD_CODES = {
    "error": DSA_ALPHASIFT_ERROR_CODE,
    "exception": DSA_ALPHASIFT_INTERNAL_ERROR_CODE,
    "errormessage": DSA_ALPHASIFT_ERROR_CODE,
    "errormsg": DSA_ALPHASIFT_ERROR_CODE,
    "errordetail": DSA_ALPHASIFT_ERROR_CODE,
    "errordescription": DSA_ALPHASIFT_ERROR_CODE,
    "errorreason": DSA_ALPHASIFT_ERROR_CODE,
    "errortext": DSA_ALPHASIFT_ERROR_CODE,
    "errorcode": DSA_ALPHASIFT_ERROR_CODE,
    "lasterror": DSA_ALPHASIFT_ERROR_CODE,
    "lasterrormessage": DSA_ALPHASIFT_ERROR_CODE,
    "lasterrorcode": DSA_ALPHASIFT_ERROR_CODE,
    "diagnosticerror": DSA_ALPHASIFT_ERROR_CODE,
    "diagnosticerrorcode": DSA_ALPHASIFT_ERROR_CODE,
    "responseerror": DSA_ALPHASIFT_ERROR_CODE,
    "responseerrorcode": DSA_ALPHASIFT_ERROR_CODE,
    "providererror": DSA_ALPHASIFT_SOURCE_ERROR_CODE,
    "providererrorcode": DSA_ALPHASIFT_SOURCE_ERROR_CODE,
    "upstreamerror": DSA_ALPHASIFT_SOURCE_ERROR_CODE,
    "adaptererror": DSA_ALPHASIFT_ERROR_CODE,
    "rawerror": DSA_ALPHASIFT_ERROR_CODE,
    "originalerror": DSA_ALPHASIFT_ERROR_CODE,
    "innererror": DSA_ALPHASIFT_ERROR_CODE,
    "failureerror": DSA_ALPHASIFT_ERROR_CODE,
    "failureerrorcode": DSA_ALPHASIFT_ERROR_CODE,
    "sourceerror": DSA_ALPHASIFT_SOURCE_ERROR_CODE,
    "llmparseerror": DSA_ALPHASIFT_LLM_PARSE_ERROR_CODE,
    "parseerror": DSA_ALPHASIFT_LLM_PARSE_ERROR_CODE,
    "warning": DSA_ALPHASIFT_WARNING_CODE,
}
_ALPHASIFT_PUBLIC_DIAGNOSTIC_CODES = frozenset({
    DSA_ALPHASIFT_HOTSPOT_UNAVAILABLE_CODE,
    DSA_ALPHASIFT_HOTSPOT_REFRESH_FAILED_CODE,
    DSA_ALPHASIFT_HOTSPOT_SOURCE_ERROR_CODE,
    DSA_ALPHASIFT_HOTSPOT_DIRECT_FALLBACK_FAILED_CODE,
    DSA_ALPHASIFT_HOTSPOT_DIRECT_FALLBACK_USED_CODE,
    DSA_ALPHASIFT_HOTSPOT_DETAIL_PREFETCH_FAILED_CODE,
    DSA_ALPHASIFT_HOTSPOT_DETAIL_STALE_CACHE_CODE,
    DSA_ALPHASIFT_HOTSPOT_DETAIL_FALLBACK_CODE,
    DSA_ALPHASIFT_HOTSPOT_DETAIL_SOURCE_ERROR_CODE,
    DSA_ALPHASIFT_WARNING_CODE,
    DSA_ALPHASIFT_ERROR_CODE,
    DSA_ALPHASIFT_SOURCE_ERROR_CODE,
    DSA_ALPHASIFT_LLM_PARSE_ERROR_CODE,
    DSA_ALPHASIFT_INTERNAL_ERROR_CODE,
    "alphasift_hotspot_detail_failed",
    "alphasift_hotspot_topic_required",
    "alphasift_screen_rejected",
    "alphasift_invalid_input",
    "alphasift_screen_failed",
    "alphasift_install_failed",
    "alphasift_unavailable",
    "alphasift_install_spec_missing",
    "alphasift_install_spec_not_allowed",
    "alphasift_disabled",
    "alphasift_install_access_denied",
    "alphasift_invalid_result",
    "alphasift_invalid_market",
    "dsa_candidate_enrichment_failed",
    "dsa_stock_name_failed",
    "dsa_realtime_quote_missing",
    "dsa_realtime_quote_failed",
    "dsa_fundamental_context_failed",
    "dsa_search_unavailable",
    "stock_news_unavailable",
    "stock_news_failed",
})


_alphasift_hotspot_part_modules = sys.modules
_alphasift_hotspot_binding_module_name = "src.services.alphasift_service_parts.binding"
_alphasift_hotspot_support_module_name = "src.services.alphasift_service_parts.hotspot_support"
if _alphasift_hotspot_binding_module_name in _alphasift_hotspot_part_modules:
    _alphasift_hotspot_binding_module = importlib.reload(
        _alphasift_hotspot_part_modules[_alphasift_hotspot_binding_module_name]
    )
else:
    _alphasift_hotspot_binding_module = importlib.import_module(
        _alphasift_hotspot_binding_module_name
    )
if _alphasift_hotspot_support_module_name in _alphasift_hotspot_part_modules:
    _alphasift_hotspot_support_module = importlib.reload(
        _alphasift_hotspot_part_modules[_alphasift_hotspot_support_module_name]
    )
else:
    _alphasift_hotspot_support_module = importlib.import_module(
        _alphasift_hotspot_support_module_name
    )
_alphasift_hotspot_support_names = (
    "_topic_log_context",
)
_alphasift_hotspot_binding_module.bind_facade_functions(
    vars(_alphasift_hotspot_support_module),
    globals(),
    _alphasift_hotspot_support_names,
)
del _alphasift_hotspot_support_names


DSA_ALPHASIFT_HOTSPOT_CONNECTIVITY_ERROR_MARKERS = (
    "remote disconnected",
    "remote end closed connection",
    "connection aborted",
    "connection reset",
    "connection refused",
    "connection timed out",
    "read timed out",
    "connecttimeout",
    "readtimeout",
    "max retries exceeded",
    "chunkedencodingerror",
    "protocolerror",
    "incompleteread",
)
_DSA_FETCHER_MANAGER_LOCK = threading.RLock()
_DSA_FETCHER_MANAGER: Any = None
_FUNDAMENTAL_BLOCKS = ("valuation", "growth", "earnings", "institution", "capital_flow", "boards")
_ALPHASIFT_LITELLM_COMPLETION_ROUTES: ContextVar[Optional[Tuple[Dict[str, Any], ...]]] = ContextVar(
    "alphasift_litellm_completion_routes",
    default=None,
)
_ALPHASIFT_LITELLM_COMPLETION_ATTR = "_alphasift_litellm_completion_bridge"
_ALPHASIFT_LITELLM_COMPLETION_LOCK = threading.Lock()


_alphasift_hotspot_support_names = (
    "_safe_float",
    "_utc_now_iso",
)
_alphasift_hotspot_binding_module.bind_facade_functions(
    vars(_alphasift_hotspot_support_module),
    globals(),
    _alphasift_hotspot_support_names,
)
del _alphasift_hotspot_support_names


def _resolve_alphasift_data_dir() -> Path:
    configured = _env_text(os.getenv("ALPHASIFT_DATA_DIR"))
    if configured:
        return Path(configured)
    return DSA_ALPHASIFT_DATA_DIR


_alphasift_hotspot_support_names = (
    "_alphasift_hotspot_cache_path",
    "_alphasift_hotspot_history_path",
    "_alphasift_hotspot_detail_cache_dir",
    "_alphasift_hotspot_detail_cache_path",
    "_parse_cache_datetime",
    "_load_alphasift_hotspot_detail_cache",
    "_write_alphasift_hotspot_detail_cache",
    "_ensure_hotspot_detail_compat_fields",
    "_extract_nested_hotspot_leader_stocks",
    "_load_alphasift_hotspot_cache",
    "_normalize_alphasift_hotspot_cache_payload",
    "_hotspot_route_has_external_event",
    "_has_configured_hotspot_news_source",
    "_build_hotspot_event_routes_from_search",
    "_summarize_hotspot_news_event",
    "_summarize_hotspot_news_event_locally",
    "_strip_hotspot_news_noise",
    "_extract_hotspot_catalyst_phrase",
    "_extract_hotspot_impact_phrases",
    "_first_meaningful_hotspot_sentence",
    "_compact_hotspot_news_text",
    "_normalize_inline_text",
    "_truncate_text",
    "_summarize_hotspot_news_event_with_llm",
    "_extract_litellm_message_content",
    "_clean_hotspot_llm_summary",
    "_extract_date_text",
    "_hotspot_rows_are_thin",
    "_snake_to_camel",
    "_enrich_hotspot_rows_from_provider",
    "_write_alphasift_hotspot_cache",
    "_hotspot_topic_from_row",
    "_attach_cached_hotspot_details",
    "_empty_alphasift_hotspot_payload",
    "_is_known_eastmoney_hotspot_connectivity_error",
    "_should_return_eastmoney_hotspot_unavailable",
    "_has_degraded_eastmoney_hotspot_failure",
)
_alphasift_hotspot_binding_module.bind_facade_functions(
    vars(_alphasift_hotspot_support_module),
    globals(),
    _alphasift_hotspot_support_names,
)
del _alphasift_hotspot_support_names


class AlphaSiftStrategyResponse(BaseModel):
    id: str
    name: str = ""
    title: str = ""
    description: str = ""
    category: str = ""
    tag: str = ""
    tags: List[str] = Field(default_factory=list)
    market_scope: List[str] = Field(default_factory=list)
    market: str = ""


class AlphaSiftService:
    """Coordinate AlphaSift calls with DSA-owned runtime capabilities."""


_alphasift_part_modules = sys.modules
_alphasift_binding_module_name = "src.services.alphasift_service_parts.binding"
_alphasift_service_module_name = "src.services.alphasift_service_parts.service"
if _alphasift_binding_module_name in _alphasift_part_modules:
    _alphasift_binding_module = importlib.reload(
        _alphasift_part_modules[_alphasift_binding_module_name]
    )
else:
    _alphasift_binding_module = importlib.import_module(
        _alphasift_binding_module_name
    )
if _alphasift_service_module_name in _alphasift_part_modules:
    _alphasift_service_module = importlib.reload(
        _alphasift_part_modules[_alphasift_service_module_name]
    )
else:
    _alphasift_service_module = importlib.import_module(
        _alphasift_service_module_name
    )
_alphasift_service_source_class = _alphasift_service_module.AlphaSiftService
_alphasift_service_method_names = _alphasift_binding_module.bind_facade_class_methods(
    AlphaSiftService,
    _alphasift_service_source_class,
    globals(),
)
del (
    _alphasift_binding_module,
    _alphasift_binding_module_name,
    _alphasift_part_modules,
    _alphasift_service_method_names,
    _alphasift_service_module,
    _alphasift_service_module_name,
    _alphasift_service_source_class,
)


_alphasift_hotspot_support_names = (
    "_normalize_alphasift_hotspot_detail",
    "_list_text_values",
    "_public_diagnostic_codes",
    "_public_diagnostic_code",
    "_normalize_diagnostic_field_name",
    "_classify_hotspot_source_errors",
    "_sanitize_public_alphasift_diagnostics",
    "_list_dict_values",
    "_hotspot_timeline_to_route",
    "_merge_provider_hotspot_route_fallback",
    "_has_meaningful_hotspot_route",
    "_build_alphasift_hotspot_summary_text",
)
_alphasift_hotspot_binding_module.bind_facade_functions(
    vars(_alphasift_hotspot_support_module),
    globals(),
    _alphasift_hotspot_support_names,
)
del (
    _alphasift_hotspot_binding_module,
    _alphasift_hotspot_binding_module_name,
    _alphasift_hotspot_part_modules,
    _alphasift_hotspot_support_module,
    _alphasift_hotspot_support_module_name,
    _alphasift_hotspot_support_names,
)


_alphasift_runtime_part_modules = sys.modules
_alphasift_runtime_binding_module_name = "src.services.alphasift_service_parts.binding"
_alphasift_runtime_support_module_name = "src.services.alphasift_service_parts.runtime_support"
if _alphasift_runtime_binding_module_name in _alphasift_runtime_part_modules:
    _alphasift_runtime_binding_module = importlib.reload(
        _alphasift_runtime_part_modules[_alphasift_runtime_binding_module_name]
    )
else:
    _alphasift_runtime_binding_module = importlib.import_module(
        _alphasift_runtime_binding_module_name
    )
if _alphasift_runtime_support_module_name in _alphasift_runtime_part_modules:
    _alphasift_runtime_support_module = importlib.reload(
        _alphasift_runtime_part_modules[_alphasift_runtime_support_module_name]
    )
else:
    _alphasift_runtime_support_module = importlib.import_module(
        _alphasift_runtime_support_module_name
    )
_alphasift_runtime_support_names = (
    "_install_alphasift",
    "_validate_install_spec",
    "_ensure_alphasift_enabled",
    "_ensure_alphasift_ready",
    "_ensure_alphasift_available_for_use",
    "_is_missing_alphasift_module",
    "_include_alphasift_diagnostic_suffix",
    "_get_alphasift_status_snapshot",
    "_get_alphasift_source_health_snapshot",
    "_ensure_alphasift_install_access",
    "_is_alphasift_available",
    "_is_adapter_available",
    "_import_alphasift",
    "_import_alphasift_hotspot",
    "_prepare_alphasift_runtime_env",
    "_get_dsa_adapter",
    "_get_adapter_callable",
    "_call_alphasift_status",
    "_is_expected_alphasift_missing",
    "_purge_alphasift_modules",
    "_alphasift_unavailable_exception",
    "_log_unexpected_alphasift_exception",
    "_extract_alphasift_diagnostics",
    "_list_strategies",
    "_normalize_strategy",
    "_strategy_model",
    "_ensure_supported_strategy",
    "_call_alphasift_screen",
)
_alphasift_runtime_binding_module.bind_facade_functions(
    vars(_alphasift_runtime_support_module),
    globals(),
    _alphasift_runtime_support_names,
)
del _alphasift_runtime_support_names


@contextmanager
def _alphasift_runtime_env(config: Config, *, max_results: Optional[int] = None) -> Iterator[None]:
    updates = _build_alphasift_runtime_env(config, max_results=max_results)  # noqa: F821
    if not updates:
        yield
        return

    sentinel = object()
    with _ALPHASIFT_RUNTIME_ENV_LOCK:
        previous = {key: os.environ.get(key, sentinel) for key in updates}
        os.environ.update(updates)
        try:
            yield
        finally:
            for key, value in previous.items():
                if value is sentinel:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value  # type: ignore[assignment]


@contextmanager
def _alphasift_dsa_daily_history_provider() -> Iterator[None]:
    try:
        daily_module = importlib.import_module("alphasift.daily")
    except Exception:
        yield
        return

    original_fetch = getattr(daily_module, "fetch_daily_history", None)
    if not callable(original_fetch):
        yield
        return

    def fetch_daily_history_with_dsa(
        code: str,
        *,
        lookback_days: int = 120,
        source: str = "akshare",
        retries: int = 2,
    ) -> Any:
        try:
            dsa_df, dsa_source = get_dsa_daily_history(code, lookback_days=lookback_days)
            normalized = _normalize_dsa_daily_history(dsa_df)
            if normalized is not None and not normalized.empty:
                normalized.attrs["source"] = f"dsa:{dsa_source}"
                return normalized
        except Exception as exc:
            log_safe_exception(
                logger,
                "AlphaSift StockPulse daily history fetch failed; falling back to AlphaSift source",
                exc,
                error_code="alphasift_daily_history_fallback",
                level=logging.WARNING,
                context={"code": code, "source": source},
            )
        return original_fetch(code, lookback_days=lookback_days, source=source, retries=retries)

    with _ALPHASIFT_RUNTIME_ENV_LOCK:
        setattr(daily_module, "fetch_daily_history", fetch_daily_history_with_dsa)
        try:
            yield
        finally:
            setattr(daily_module, "fetch_daily_history", original_fetch)


_alphasift_runtime_support_names = (
    "_resolve_alphasift_snapshot_source_priority",
    "_build_alphasift_runtime_env",
    "_resolve_hotspot_provider",
)
_alphasift_runtime_binding_module.bind_facade_functions(
    vars(_alphasift_runtime_support_module),
    globals(),
    _alphasift_runtime_support_names,
)
del (
    _alphasift_runtime_binding_module,
    _alphasift_runtime_binding_module_name,
    _alphasift_runtime_part_modules,
    _alphasift_runtime_support_module,
    _alphasift_runtime_support_module_name,
    _alphasift_runtime_support_names,
)


class DsaEastMoneyHotspotProvider:
    """Minimal EastMoney board provider for AlphaSift hotspot scoring."""

    _BASE_URL = "https://push2.eastmoney.com/api/qt/clist/get"
    _HTTP_TIMEOUT_SECONDS = 8
    _COMMON_PARAMS = {
        "pn": "1",
        "po": "1",
        "np": "1",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": "2",
        "invt": "2",
        "fid": "f12",
        "fields": "f2,f3,f4,f12,f13,f14,f104,f105,f128,f136,f140,f141,f207",
    }
    _BROAD_BOARD_KEYWORDS = (
        "融资融券",
        "深股通",
        "沪股通",
        "创业板",
        "昨日",
        "机构重仓",
        "富时罗素",
        "MSCI",
        "标普",
        "上证",
        "深证",
        "中证",
        "HS300",
        "证金",
        "QFII",
        "基金",
        "转融券",
        "预增",
        "预盈",
        "亏损",
        "低价",
        "小盘股",
        "中盘股",
        "百元股",
        "破发",
        "破增发",
        "趋势股",
        "广东板块",
        "江苏板块",
        "浙江板块",
        "上海板块",
        "深圳特区",
        "央国企",
        "国企改革",
        "专精特新",
        "其他",
        "Ⅱ",
        "Ⅲ",
    )
    _CHANGE_EVENT_LABELS = {
        4: "快速拉升",
        8: "快速回落",
        16: "大幅上涨",
        32: "大幅下跌",
        64: "有大笔买入",
        128: "有大笔卖出",
        8193: "火箭发射",
        8194: "高台跳水",
        8201: "大笔买入",
        8202: "大笔卖出",
        8203: "封涨停板",
        8204: "打开涨停板",
        8207: "有打开跌停板",
        8208: "封跌停板",
        8209: "向上缺口",
        8210: "向下缺口",
        8211: "60日新高",
        8212: "60日新低",
        8213: "60日大幅上涨",
        8214: "60日大幅下跌",
        8215: "竞价上涨",
        8216: "竞价下跌",
        8217: "高开",
        8218: "低开",
        8219: "放量",
        8220: "缩量",
        8221: "向上突破",
        8222: "向下破位",
    }
    _METAL_TOPIC_GROUPS = {
        "钼": "小金属",
        "钨": "小金属",
        "钴": "小金属",
        "镍": "小金属",
        "锑": "小金属",
        "铟": "小金属",
        "锗": "小金属",
        "铅锌": "工业金属",
        "铜": "工业金属",
        "铝": "工业金属",
        "锡": "工业金属",
        "黄金": "贵金属",
        "白银": "贵金属",
        "贵金属": "贵金属",
    }


_alphasift_part_modules = sys.modules
_alphasift_binding_module_name = "src.services.alphasift_service_parts.binding"
_alphasift_provider_module_name = "src.services.alphasift_service_parts.hotspot_provider"
if _alphasift_binding_module_name in _alphasift_part_modules:
    _alphasift_binding_module = importlib.reload(
        _alphasift_part_modules[_alphasift_binding_module_name]
    )
else:
    _alphasift_binding_module = importlib.import_module(
        _alphasift_binding_module_name
    )
if _alphasift_provider_module_name in _alphasift_part_modules:
    _alphasift_provider_module = importlib.reload(
        _alphasift_part_modules[_alphasift_provider_module_name]
    )
else:
    _alphasift_provider_module = importlib.import_module(
        _alphasift_provider_module_name
    )
_alphasift_provider_source_class = _alphasift_provider_module.DsaEastMoneyHotspotProvider
_alphasift_provider_method_names = _alphasift_binding_module.bind_facade_class_methods(
    DsaEastMoneyHotspotProvider,
    _alphasift_provider_source_class,
    globals(),
)
del (
    _alphasift_binding_module,
    _alphasift_binding_module_name,
    _alphasift_part_modules,
    _alphasift_provider_method_names,
    _alphasift_provider_module,
    _alphasift_provider_module_name,
    _alphasift_provider_source_class,
)



def _build_alphasift_context(config: Config, *, max_results: Optional[int] = None) -> Dict[str, Any]:
    # context.llm.model/fallback/model_list And LiteLLM Route semantics remain consistent,
    # See https://docs.litellm.ai/docs/proxy/configs#the-model_list-key
    channels = _normalize_dsa_llm_channels(config)
    litellm_model, fallback_models = _resolve_alphasift_llm_models(config)
    return {
        "llm": {
            "model": litellm_model,
            "fallback_models": fallback_models,
            "temperature": config.llm_temperature,
            "channels": channels,
            "model_list": _build_alphasift_litellm_model_list(config, channels),
            "litellm_config_path": config.litellm_config_path or "",
            "candidate_context_enabled": False,
            "candidate_multiplier": DSA_ALPHASIFT_LLM_CANDIDATE_MULTIPLIER,
            "max_candidates": _resolve_dsa_llm_max_candidates(max_results),
        },
        "dsa": {
            "contract_version": "1",
            "mode": "pre_rank_light",
            "max_candidates": DSA_PRE_RANK_CONTEXT_MAX_CANDIDATES,
            "include_news": False,
            "news_max_results": 0,
            "capabilities": [
                "candidate_context",
                "daily_history",
                "realtime_quote",
                "fundamental_context",
            ],
            "get_candidate_context": get_dsa_candidate_context,
            "get_daily_history": get_dsa_daily_history,
            "get_realtime_quote": get_dsa_realtime_quote,
            "get_fundamental_context": get_dsa_fundamental_context,
        },
    }

@contextmanager
def _alphasift_litellm_headers(config: Config) -> Iterator[None]:
    header_routes = _build_alphasift_litellm_header_routes(config)
    if not header_routes:
        yield
        return

    try:
        litellm_module = importlib.import_module("litellm")
    except Exception:
        yield
        return

    completion = getattr(litellm_module, "completion", None)
    if not callable(completion):
        yield
        return

    bridge_completion = getattr(completion, _ALPHASIFT_LITELLM_COMPLETION_ATTR, None)
    if bridge_completion:
        token = _ALPHASIFT_LITELLM_COMPLETION_ROUTES.set(
            tuple(route.copy() for route in header_routes),
        )
        try:
            yield
        finally:
            _ALPHASIFT_LITELLM_COMPLETION_ROUTES.reset(token)
        return

    original_completion = completion

    def completion_with_dsa_headers(*args: Any, **kwargs: Any) -> Any:
        routes = _ALPHASIFT_LITELLM_COMPLETION_ROUTES.get()
        outbound_urls: List[str] = []
        if routes:
            matching_routes = _match_alphasift_litellm_routes(args, kwargs, routes)
            headers = next(
                (
                    dict(route.get("extra_headers") or {})
                    for route in matching_routes
                    if route.get("extra_headers")
                ),
                {},
            )
            outbound_urls = _dedupe_strings(
                [route.get("api_base") for route in matching_routes]
            )
            if headers:
                existing_headers = kwargs.get("extra_headers")
                if isinstance(existing_headers, dict):
                    merged_headers = dict(headers)
                    merged_headers.update(existing_headers)
                    kwargs = dict(kwargs)
                    kwargs["extra_headers"] = merged_headers
                elif existing_headers in (None, ""):
                    kwargs = dict(kwargs)
                    kwargs["extra_headers"] = dict(headers)
        for key in ("api_base", "base_url", "azure_endpoint"):
            value = _env_text(kwargs.get(key))
            if value and value not in outbound_urls:
                outbound_urls.append(value)
        with guard_outbound_urls(outbound_urls, strict_dns=True):
            return original_completion(*args, **kwargs)

    setattr(completion_with_dsa_headers, _ALPHASIFT_LITELLM_COMPLETION_ATTR, True)
    setattr(completion_with_dsa_headers, "_alphasift_litellm_completion_original", original_completion)
    completion_with_dsa_headers.__name__ = "completion_with_dsa_headers"

    if completion is not completion_with_dsa_headers:
        with _ALPHASIFT_LITELLM_COMPLETION_LOCK:
            if not getattr(getattr(litellm_module, "completion", None), _ALPHASIFT_LITELLM_COMPLETION_ATTR, False):
                setattr(litellm_module, "completion", completion_with_dsa_headers)

    token = _ALPHASIFT_LITELLM_COMPLETION_ROUTES.set(
        tuple(route.copy() for route in header_routes),
    )
    try:
        yield
    finally:
        _ALPHASIFT_LITELLM_COMPLETION_ROUTES.reset(token)


def _build_alphasift_litellm_model_list(config: Config, channels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    explicit_model_list = _to_plain(config.llm_model_list or [])
    if isinstance(explicit_model_list, list) and explicit_model_list:
        return explicit_model_list
    return _channel_litellm_model_list(channels)


def _channel_litellm_model_list(channels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    model_list_builder = getattr(Config, "_channels_to_model_list", None)
    if callable(model_list_builder):
        return _to_plain(model_list_builder(channels))

    model_list: List[Dict[str, Any]] = []
    for channel in channels:
        headers = dict(channel.get("extra_headers") or {})
        base_url = _env_text(channel.get("base_url"))
        for model_name in channel.get("models") or []:
            for api_key in channel.get("api_keys") or []:
                litellm_params: Dict[str, Any] = {"model": model_name}
                if api_key:
                    litellm_params["api_key"] = api_key
                if base_url:
                    litellm_params["api_base"] = base_url
                if headers:
                    litellm_params["extra_headers"] = dict(headers)
                model_list.append({"model_name": model_name, "litellm_params": litellm_params})
    return model_list


def _build_alphasift_litellm_header_routes(config: Config) -> List[Dict[str, Any]]:
    channels = _normalize_dsa_llm_channels(config)
    model_list = _build_alphasift_litellm_model_list(config, channels)
    routes: List[Dict[str, Any]] = []
    for entry in model_list:
        if not isinstance(entry, dict):
            continue
        params = entry.get("litellm_params") or {}
        if not isinstance(params, dict):
            continue
        headers = params.get("extra_headers")
        if not isinstance(headers, dict):
            headers = {}
        api_base = _env_text(params.get("api_base") or params.get("base_url"))
        if not headers and not api_base:
            continue
        model_names = _dedupe_strings([
            entry.get("model_name"),
            params.get("model"),
        ])
        if not model_names:
            continue
        routes.append(
            {
                "models": model_names,
                "api_key": _env_text(params.get("api_key")),
                "api_base": api_base,
                "extra_headers": dict(headers),
            }
        )
    legacy_base_url = _env_text(config.openai_base_url)
    primary_model, fallback_models = _resolve_alphasift_llm_models(config)
    legacy_models = _dedupe_strings([primary_model, *fallback_models])
    if legacy_base_url and legacy_models and not any(
        route.get("api_base") == legacy_base_url
        and set(route.get("models") or []).intersection(legacy_models)
        for route in routes
    ):
        routes.append(
            {
                "models": legacy_models,
                "api_key": "",
                "api_base": legacy_base_url,
                "extra_headers": {},
            }
        )
    return routes


def _match_alphasift_litellm_routes(
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
    routes: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    model = _env_text(kwargs.get("model"))
    if not model and args:
        model = _env_text(args[0])
    if not model:
        return []

    api_key = _env_text(kwargs.get("api_key"))
    api_base = _env_text(kwargs.get("api_base") or kwargs.get("base_url"))
    matches: List[Dict[str, Any]] = []
    for route in routes:
        if model not in set(route.get("models") or []):
            continue
        route_api_key = _env_text(route.get("api_key"))
        if route_api_key and api_key and route_api_key != api_key:
            continue
        route_api_base = _env_text(route.get("api_base"))
        if route_api_base and api_base and route_api_base != api_base:
            continue
        matches.append(route)
    return matches


def _resolve_dsa_llm_max_candidates(max_results: Optional[int]) -> int:
    requested = max_results if isinstance(max_results, int) and max_results > 0 else DSA_ENRICHMENT_MAX_CANDIDATES
    return min(
        DSA_ALPHASIFT_LLM_MAX_CANDIDATES,
        max(requested, requested * DSA_ALPHASIFT_LLM_CANDIDATE_MULTIPLIER),
    )


def _resolve_alphasift_llm_models(config: Config) -> Tuple[str, List[str]]:
    primary = _env_text(config.litellm_model)
    configured_models = get_configured_llm_models(config.llm_model_list or [])
    configured_model_set = set(configured_models)

    if configured_models and (
        not primary or (primary not in configured_model_set and _is_managed_litellm_model(primary))
    ):
        primary = configured_models[0]

    raw_fallbacks = _dedupe_strings(config.litellm_fallback_models or [])
    if not configured_models:
        return primary, [model for model in raw_fallbacks if model != primary]

    fallback_models: List[str] = []
    seen = {primary} if primary else set()

    for model in raw_fallbacks:
        if model in seen:
            continue
        if model in configured_model_set or not _is_managed_litellm_model(model):
            fallback_models.append(model)
            seen.add(model)

    for model in configured_models:
        if model and model not in seen:
            fallback_models.append(model)
            seen.add(model)

    return primary, fallback_models


def _is_managed_litellm_model(model: str) -> bool:
    text = _env_text(model)
    if not text:
        return False
    provider = text.split("/", 1)[0].lower() if "/" in text else "openai"
    return provider in ALPHASIFT_MANAGED_LITELLM_PROVIDERS


def _normalize_dsa_llm_channels(config: Config) -> List[Dict[str, Any]]:
    channels: List[Dict[str, Any]] = []
    for index, raw in enumerate(config.llm_channels or []):
        if not isinstance(raw, dict):
            continue
        name = _env_text(raw.get("name")) or f"channel{index + 1}"
        api_keys = _dedupe_strings(raw.get("api_keys") if isinstance(raw.get("api_keys"), list) else [])
        models = _dedupe_strings(raw.get("models") if isinstance(raw.get("models"), list) else [])
        channel = {
            "name": name,
            "protocol": _env_text(raw.get("protocol")),
            "base_url": _env_text(raw.get("base_url")),
            "api_keys": api_keys,
            "models": models,
            "extra_headers": raw.get("extra_headers") if isinstance(raw.get("extra_headers"), dict) else {},
            "enabled": bool(raw.get("enabled", True)),
        }
        if channel["enabled"] and (api_keys or models or channel["base_url"] or channel["extra_headers"]):
            channels.append(channel)
    return channels


def _channel_keys_for_provider(channels: List[Dict[str, Any]], providers: set[str]) -> List[str]:
    keys: List[str] = []
    for channel in channels:
        protocol = _env_text(channel.get("protocol")).lower()
        models = channel.get("models") or []
        model_providers = {
            str(model).split("/", 1)[0].lower()
            for model in models
            if isinstance(model, str) and "/" in model
        }
        if protocol in providers or model_providers.intersection(providers):
            keys.extend(channel.get("api_keys") or [])
    return keys


def _first_channel_base_url(channels: List[Dict[str, Any]], providers: set[str]) -> str:
    for channel in channels:
        protocol = _env_text(channel.get("protocol")).lower()
        base_url = _env_text(channel.get("base_url"))
        if base_url and protocol in providers:
            return base_url
    return ""


def _put_provider_keys(env: Dict[str, str], provider: str, keys: List[str]) -> None:
    if not keys:
        return
    env[f"{provider}_API_KEYS"] = ",".join(keys)
    env[f"{provider}_API_KEY"] = keys[0]


def _dedupe_strings(values: Any) -> List[str]:
    result: List[str] = []
    seen: set[str] = set()
    if not isinstance(values, list):
        return result
    for value in values:
        text = _env_text(value)
        if not text or text in seen:
            continue
        result.append(text)
        seen.add(text)
    return result


def _env_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and not math.isfinite(value):
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "null"}:
        return ""
    return text


def _get_dsa_fetcher_manager() -> Any:
    global _DSA_FETCHER_MANAGER
    if _DSA_FETCHER_MANAGER is None:
        with _DSA_FETCHER_MANAGER_LOCK:
            if _DSA_FETCHER_MANAGER is None:
                from data_provider import DataFetcherManager

                _DSA_FETCHER_MANAGER = DataFetcherManager()
    return _DSA_FETCHER_MANAGER


def _get_dsa_search_service() -> Any:
    from src.search_service import get_search_service

    return get_search_service()


def get_dsa_daily_history(stock_code: str, *, lookback_days: int = 120) -> Tuple[Any, str]:
    from src.services.history_loader import load_history_df

    normalized_code = _env_text(stock_code).zfill(6)
    days = max(int(lookback_days or 0), 30)
    return load_history_df(normalized_code, days=days)


def _normalize_dsa_daily_history(raw_df: Any) -> Any:
    if raw_df is None:
        return None

    import pandas as pd

    df = pd.DataFrame(raw_df).copy()
    if df.empty:
        return df

    aliases = {
        "date": ("date", "trade_date", "datetime", "日期"),
        "open": ("open", "开盘"),
        "high": ("high", "最高"),
        "low": ("low", "最低"),
        "close": ("close", "收盘", "price"),
        "volume": ("volume", "vol", "成交量"),
        "amount": ("amount", "成交额"),
    }
    normalized = pd.DataFrame(index=df.index)
    for target, candidates in aliases.items():
        source_column = next((column for column in candidates if column in df.columns), None)
        if source_column is not None:
            normalized[target] = df[source_column]

    if "close" not in normalized.columns:
        return pd.DataFrame()
    for column in ("open", "high", "low"):
        if column not in normalized.columns:
            normalized[column] = normalized["close"]
    if "volume" not in normalized.columns:
        normalized["volume"] = 0

    if "date" in normalized.columns:
        normalized["date"] = normalized["date"].map(_normalize_daily_date_value)

    for column in ("open", "high", "low", "close", "volume", "amount"):
        if column in normalized.columns:
            normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    normalized = normalized.dropna(subset=["close"])
    return normalized.reset_index(drop=True)


def _normalize_daily_date_value(value: Any) -> str:
    text = _env_text(value)
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text


def get_dsa_realtime_quote(stock_code: str) -> Dict[str, Any]:
    manager = _get_dsa_fetcher_manager()
    quote = manager.get_realtime_quote(stock_code, log_final_failure=False)
    if quote is None:
        return {}
    if hasattr(quote, "to_dict") and callable(quote.to_dict):
        return _remove_non_finite_json_values(quote.to_dict())
    payload = _to_plain(quote)
    return _remove_non_finite_json_values(payload if isinstance(payload, dict) else {})


def get_dsa_fundamental_context(stock_code: str) -> Dict[str, Any]:
    manager = _get_dsa_fetcher_manager()
    context = manager.get_fundamental_context(stock_code, budget_seconds=4.0)
    return _compact_fundamental_context(_remove_non_finite_json_values(_to_plain(context)))


def search_dsa_stock_news(stock_code: str, stock_name: str = "", max_results: int = 3) -> Dict[str, Any]:
    service = _get_dsa_search_service()
    if not getattr(service, "is_available", False):
        return {
            "success": False,
            "error": "dsa_search_unavailable",
            "results": [],
        }

    response = service.search_stock_news(stock_code, stock_name or stock_code, max_results=max_results)
    results = []
    for item in getattr(response, "results", []) or []:
        results.append(
            {
                "title": getattr(item, "title", ""),
                "snippet": getattr(item, "snippet", ""),
                "url": getattr(item, "url", ""),
                "source": getattr(item, "source", ""),
                "published_date": getattr(item, "published_date", None),
            }
        )
    success = bool(getattr(response, "success", False))
    return _remove_non_finite_json_values({
        "query": getattr(response, "query", ""),
        "provider": getattr(response, "provider", ""),
        "success": success,
        "error": None if success else "stock_news_unavailable",
        "results": results,
    })


def get_dsa_candidate_context(
    stock_code: str,
    stock_name: str = "",
    *,
    include_news: bool = False,
    include_fundamentals: bool = True,
    mode: str = "pre_rank_light",
) -> Dict[str, Any]:
    candidate = {"code": stock_code, "name": stock_name, "raw": {}}
    context = _build_dsa_candidate_context(
        candidate,
        include_news=include_news,
        include_fundamentals=include_fundamentals,
        profile=mode or "pre_rank_light",
    )
    return context.get("dsa_context", {})


def _enrich_candidates_with_dsa(candidates: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    enriched_count = 0
    warnings: List[str] = []
    limit = min(len(candidates), DSA_ENRICHMENT_MAX_CANDIDATES)

    for index, candidate in enumerate(candidates):
        if index >= limit:
            continue
        existing_context = candidate.get("dsa_context")
        if (
            isinstance(existing_context, dict)
            and existing_context.get("enriched")
            and _candidate_has_dsa_news(candidate)
        ):
            enriched_count += 1
            existing_warnings = existing_context.get("warnings") or []
            if isinstance(existing_warnings, list):
                warnings.extend(str(item) for item in existing_warnings if item)
            elif existing_warnings:
                warnings.append(str(existing_warnings))
            continue
        try:
            enriched = _build_dsa_candidate_context(
                candidate,
                include_news=True,
                include_fundamentals=True,
                profile="post_rank_full",
            )
            candidate.update(enriched)
            if enriched.get("dsa_context", {}).get("enriched"):
                enriched_count += 1
            warnings.extend(enriched.get("dsa_context", {}).get("warnings") or [])
        except Exception as exc:  # noqa: BLE001 - enrichment must not block screening.
            code = candidate.get("code") or f"rank-{candidate.get('rank', index + 1)}"
            warnings.append("dsa_candidate_enrichment_failed")
            log_safe_exception(
                logger,
                "StockPulse enrichment failed for AlphaSift candidate",
                exc,
                error_code="dsa_candidate_enrichment_failed",
                level=logging.WARNING,
                context={"code": code},
            )
            candidate["dsa_context"] = {
                "enriched": False,
                "warnings": ["dsa_candidate_enrichment_failed"],
            }

    return candidates, {
        "enabled": True,
        "max_candidates": DSA_ENRICHMENT_MAX_CANDIDATES,
        "requested_count": limit,
        "enriched_count": enriched_count,
        "warnings": _dedupe_strings(warnings),
    }


def _candidate_has_dsa_news(candidate: Dict[str, Any]) -> bool:
    news_items = candidate.get("dsa_news")
    if isinstance(news_items, list) and any(isinstance(item, dict) for item in news_items):
        return True
    context = candidate.get("dsa_context")
    if not isinstance(context, dict):
        return False
    return _news_has_results(context.get("news"))


def _news_has_results(news: Any) -> bool:
    if isinstance(news, dict):
        results = news.get("results")
        return isinstance(results, list) and any(isinstance(item, dict) for item in results)
    if isinstance(news, list):
        return any(isinstance(item, dict) for item in news)
    return False


def _build_dsa_candidate_context(
    candidate: Dict[str, Any],
    *,
    include_news: bool = True,
    include_fundamentals: bool = True,
    profile: str = "post_rank_full",
) -> Dict[str, Any]:
    code = _env_text(candidate.get("code"))
    name = _env_text(candidate.get("name"))
    warnings: List[str] = []
    if not code:
        return {
            "dsa_context": {
                "enriched": False,
                "warnings": ["missing candidate code"],
            }
        }

    existing_context = candidate.get("dsa_context")
    if not isinstance(existing_context, dict):
        existing_context = {}

    quote = existing_context.get("quote") if isinstance(existing_context.get("quote"), dict) else {}
    fundamentals = (
        existing_context.get("fundamentals")
        if isinstance(existing_context.get("fundamentals"), dict)
        else {}
    )
    existing_news = existing_context.get("news") if isinstance(existing_context.get("news"), dict) else {}
    news: Dict[str, Any] = dict(existing_news) if existing_news else {"success": False, "results": []}
    existing_warnings = existing_context.get("warnings") or []
    if isinstance(existing_warnings, list):
        warnings.extend(str(item) for item in existing_warnings if item)
    elif existing_warnings:
        warnings.append(str(existing_warnings))

    try:
        manager = _get_dsa_fetcher_manager()
        resolved_name = manager.get_stock_name(code, allow_realtime=False)
        if resolved_name and (not name or name == code):
            name = resolved_name
            candidate["name"] = resolved_name
    except Exception as exc:  # noqa: BLE001
        warnings.append("dsa_stock_name_failed")
        log_safe_exception(
            logger,
            "StockPulse stock name lookup failed during AlphaSift enrichment",
            exc,
            error_code="dsa_stock_name_failed",
            level=logging.WARNING,
        )

    if not quote:
        try:
            quote = get_dsa_realtime_quote(code)
            if not quote:
                warnings.append("dsa_realtime_quote_missing")
        except Exception as exc:  # noqa: BLE001
            warnings.append("dsa_realtime_quote_failed")
            log_safe_exception(
                logger,
                "StockPulse realtime quote failed during AlphaSift enrichment",
                exc,
                error_code="dsa_realtime_quote_failed",
                level=logging.WARNING,
            )
            quote = {}

    if quote:
        candidate["price"] = _first_non_empty(candidate.get("price"), quote.get("price"))
        candidate["change_pct"] = _first_non_empty(candidate.get("change_pct"), quote.get("change_pct"))
        candidate["amount"] = _first_non_empty(candidate.get("amount"), quote.get("amount"))
        if not candidate.get("name") and quote.get("name"):
            candidate["name"] = quote.get("name")

    if include_fundamentals and not fundamentals:
        try:
            fundamentals = get_dsa_fundamental_context(code)
        except Exception as exc:  # noqa: BLE001
            warnings.append("dsa_fundamental_context_failed")
            log_safe_exception(
                logger,
                "StockPulse fundamental context failed during AlphaSift enrichment",
                exc,
                error_code="dsa_fundamental_context_failed",
                level=logging.WARNING,
            )
            fundamentals = {}

    if include_news:
        if not _news_has_results(news):
            try:
                news = search_dsa_stock_news(code, _env_text(candidate.get("name")) or name or code, max_results=3)
                if not news.get("success"):
                    warnings.append(news.get("error") or "stock_news_unavailable")
            except Exception as exc:  # noqa: BLE001
                warnings.append("stock_news_failed")
                log_safe_exception(
                    logger,
                    "StockPulse stock news failed during AlphaSift enrichment",
                    exc,
                    error_code="stock_news_failed",
                    level=logging.WARNING,
                )
                news = {"success": False, "error": "stock_news_failed", "results": []}
    elif not _news_has_results(news):
        news = {
            "success": False,
            "skipped": True,
            "reason": "pre_rank_light_context",
            "results": [],
        }

    summary = _build_dsa_analysis_summary(candidate, quote, fundamentals, news)
    context = {
        "enriched": bool(quote or fundamentals or news.get("results")),
        "profile": profile,
        "news_included": bool(include_news),
        "quote": quote,
        "fundamentals": fundamentals,
        "news": news,
        "warnings": _dedupe_strings(warnings),
    }
    return {
        "dsa_context": context,
        "dsa_news": news.get("results") or [],
        "dsa_analysis_summary": summary,
    }


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _compact_fundamental_context(context: Any) -> Dict[str, Any]:
    if not isinstance(context, dict):
        return {}
    compact: Dict[str, Any] = {
        "market": context.get("market"),
        "status": context.get("status"),
        "coverage": context.get("coverage") if isinstance(context.get("coverage"), dict) else {},
    }
    for block in _FUNDAMENTAL_BLOCKS:
        payload = context.get(block)
        if isinstance(payload, dict):
            compact[block] = {
                "status": payload.get("status"),
                "data": payload.get("data") if isinstance(payload.get("data"), dict) else {},
            }
    errors = context.get("errors")
    if isinstance(errors, list) and errors:
        compact["errors"] = [str(item) for item in errors[:3]]
    return compact


def _build_dsa_analysis_summary(
    candidate: Dict[str, Any],
    quote: Dict[str, Any],
    fundamentals: Dict[str, Any],
    news: Dict[str, Any],
) -> str:
    parts: List[str] = []
    price = _first_non_empty(quote.get("price"), candidate.get("price"))
    change_pct = _first_non_empty(quote.get("change_pct"), candidate.get("change_pct"))
    if price is not None:
        text = f"StockPulse 行情：现价 {price}"
        if change_pct is not None:
            text += f"，涨跌幅 {change_pct}%"
        parts.append(text)

    coverage = fundamentals.get("coverage") if isinstance(fundamentals, dict) else {}
    if isinstance(coverage, dict) and coverage:
        available_blocks = [key for key, value in coverage.items() if str(value).lower() in {"available", "partial"}]
        if available_blocks:
            parts.append(f"StockPulse 基本面覆盖：{', '.join(available_blocks[:4])}")

    news_results = news.get("results") if isinstance(news, dict) else []
    if isinstance(news_results, list) and news_results:
        titles = [str(item.get("title") or "").strip() for item in news_results if isinstance(item, dict)]
        titles = [title for title in titles if title]
        if titles:
            parts.append(f"StockPulse 新闻：{'；'.join(titles[:2])}")

    if not parts:
        return ""
    return "；".join(parts)


def _ensure_supported_market(market: str) -> None:
    status = _call_alphasift_status()  # noqa: F821
    supported_markets = status.get("supported_markets") or status.get("markets") or status.get("market")
    if not supported_markets:
        return

    normalized: List[Any]
    if isinstance(supported_markets, str):
        normalized = [supported_markets]
    elif isinstance(supported_markets, (list, tuple, set)):
        normalized = list(supported_markets)
    else:
        normalized = []

    if market not in normalized:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "alphasift_invalid_market",
                "message": (
                    f"市场 {market} 不在 AlphaSift 适配层支持范围内"
                    f"（支持市场：{', '.join(map(str, normalized)) or '未知'}）。"
                ),
            },
        )


def _normalize_candidates(raw: Any) -> List[Dict[str, Any]]:
    data = _to_plain(raw)
    items = data
    if isinstance(data, dict):
        for key in ("candidates", "picks", "items", "results", "stocks"):
            if isinstance(data.get(key), list):
                items = data[key]
                break
    if not isinstance(items, list):
        return []
    return [_normalize_candidate(item, index + 1) for index, item in enumerate(items)]


def _normalize_candidate(raw: Any, rank: int) -> Dict[str, Any]:
    item = _remove_non_finite_json_values(_to_plain(raw))
    if not isinstance(item, dict):
        item = {"code": str(item)}
    source = item.get("raw") if isinstance(item.get("raw"), dict) else item
    dsa_context = item.get("dsa_context") or source.get("dsa_context") or {}
    dsa_news = item.get("dsa_news") or source.get("dsa_news") or _extract_dsa_news_from_context(dsa_context)
    dsa_analysis_summary = (
        item.get("dsa_analysis_summary")
        or source.get("dsa_analysis_summary")
        or _extract_dsa_analysis_summary_from_context(dsa_context)
    )
    return {
        "rank": item.get("rank") or source.get("rank") or rank,
        "code": item.get("code") or source.get("code") or item.get("symbol") or source.get("symbol") or item.get("stock_code") or source.get("stock_code") or "",
        "name": item.get("name") or source.get("name") or item.get("stock_name") or source.get("stock_name") or "",
        "score": _first_present(item, source, "score", "final_score"),
        "screen_score": _first_present(item, source, "screen_score"),
        "reason": item.get("reason") or source.get("reason") or source.get("ranking_reason") or source.get("risk_summary") or item.get("summary") or _build_candidate_reason(source),
        "risk_level": item.get("risk_level") or source.get("risk_level") or "",
        "risk_flags": item.get("risk_flags") or source.get("risk_flags") or [],
        "llm_score": _first_present(item, source, "llm_score"),
        "llm_confidence": _first_present(item, source, "llm_confidence"),
        "llm_sector": item.get("llm_sector") or source.get("llm_sector") or "",
        "llm_theme": item.get("llm_theme") or source.get("llm_theme") or "",
        "llm_tags": item.get("llm_tags") or source.get("llm_tags") or [],
        "llm_thesis": item.get("llm_thesis") or source.get("llm_thesis") or "",
        "llm_catalysts": item.get("llm_catalysts") or source.get("llm_catalysts") or [],
        "llm_risks": item.get("llm_risks") or source.get("llm_risks") or [],
        "llm_watch_items": item.get("llm_watch_items") or source.get("llm_watch_items") or [],
        "llm_invalidators": item.get("llm_invalidators") or source.get("llm_invalidators") or [],
        "llm_style_fit": item.get("llm_style_fit") or source.get("llm_style_fit") or "",
        "price": _first_present(item, source, "price"),
        "change_pct": _first_present(item, source, "change_pct"),
        "amount": _first_present(item, source, "amount"),
        "industry": item.get("industry") or source.get("industry") or "",
        "factor_scores": item.get("factor_scores") or source.get("factor_scores") or {},
        "dsa_context": dsa_context,
        "dsa_news": dsa_news,
        "dsa_analysis_summary": dsa_analysis_summary,
        "post_analysis_summaries": item.get("post_analysis_summaries") or source.get("post_analysis_summaries") or {},
        "post_analysis_tags": item.get("post_analysis_tags") or source.get("post_analysis_tags") or [],
        "raw": source,
    }


def _extract_dsa_news_from_context(context: Any) -> List[Dict[str, Any]]:
    if not isinstance(context, dict):
        return []
    news = context.get("news")
    if isinstance(news, dict):
        results = news.get("results")
    elif isinstance(news, list):
        results = news
    else:
        results = None
    if not isinstance(results, list):
        return []
    return [item for item in results if isinstance(item, dict)]


def _extract_dsa_analysis_summary_from_context(context: Any) -> str:
    if not isinstance(context, dict):
        return ""
    for key in ("dsa_analysis_summary", "analysis_summary", "summary"):
        value = context.get(key)
        if isinstance(value, str) and value.strip():
            return value
    news = context.get("news")
    if isinstance(news, dict):
        for key in ("analysis_summary", "summary"):
            value = news.get(key)
            if isinstance(value, str) and value.strip():
                return value
    news_items = _extract_dsa_news_from_context(context)
    if not news_items:
        return ""
    quote = context.get("quote") if isinstance(context.get("quote"), dict) else {}
    fundamentals = context.get("fundamentals") if isinstance(context.get("fundamentals"), dict) else {}
    return _build_dsa_analysis_summary({}, quote, fundamentals, {"results": news_items})


def _first_present(primary: Dict[str, Any], source: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if primary.get(key) is not None:
            return primary.get(key)
        if source.get(key) is not None:
            return source.get(key)
    return None


def _build_candidate_reason(item: Dict[str, Any]) -> str:
    summaries = item.get("post_analysis_summaries")
    if isinstance(summaries, dict):
        summary = next((str(value) for value in summaries.values() if value), "")
        if summary:
            return summary

    factors = item.get("factor_scores")
    parts: List[str] = []
    if isinstance(factors, dict) and factors:
        top_factors = sorted(
            ((key, value) for key, value in factors.items() if isinstance(value, (int, float))),
            key=lambda pair: pair[1],
            reverse=True,
        )[:3]
        if top_factors:
            factor_text = "、".join(f"{key} {value:.1f}" for key, value in top_factors)
            parts.append(f"主要因子：{factor_text}")
    if item.get("industry"):
        parts.append(f"行业：{item['industry']}")
    if item.get("risk_level"):
        parts.append(f"风险等级：{item['risk_level']}")
    return "；".join(parts)


def _to_plain(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict") and callable(value.dict):
        return value.dict()
    if isinstance(value, list):
        return [_to_plain(item) for item in value]
    return value


def _remove_non_finite_json_values(value: Any) -> Any:
    if isinstance(value, list):
        return [_remove_non_finite_json_values(item) for item in value]
    if isinstance(value, tuple):
        return [_remove_non_finite_json_values(item) for item in value]
    if isinstance(value, dict):
        return {key: _remove_non_finite_json_values(item) for key, item in value.items()}
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value


def _build_install_response(already_installed: bool, install_spec_is_default: bool) -> Dict[str, Any]:
    return {
        "installed": True,
        "already_installed": already_installed,
        "install_spec_is_default": install_spec_is_default,
    }


def _is_default_alphasift_install_spec(install_spec: str) -> bool:
    return (install_spec or "").strip() == DEFAULT_ALPHASIFT_INSTALL_SPEC
