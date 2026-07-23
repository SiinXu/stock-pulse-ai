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
    configured = _env_text(os.getenv("ALPHASIFT_DATA_DIR"))  # noqa: F821
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
    "_resolve_repair_constraint_args",
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
            dsa_df, dsa_source = get_dsa_daily_history(code, lookback_days=lookback_days)  # noqa: F821
            normalized = _normalize_dsa_daily_history(dsa_df)  # noqa: F821
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



_alphasift_context_part_modules = sys.modules
_alphasift_context_binding_module_name = "src.services.alphasift_service_parts.binding"
_alphasift_context_support_module_name = "src.services.alphasift_service_parts.context_support"
if _alphasift_context_binding_module_name in _alphasift_context_part_modules:
    _alphasift_context_binding_module = importlib.reload(
        _alphasift_context_part_modules[_alphasift_context_binding_module_name]
    )
else:
    _alphasift_context_binding_module = importlib.import_module(
        _alphasift_context_binding_module_name
    )
if _alphasift_context_support_module_name in _alphasift_context_part_modules:
    _alphasift_context_support_module = importlib.reload(
        _alphasift_context_part_modules[_alphasift_context_support_module_name]
    )
else:
    _alphasift_context_support_module = importlib.import_module(
        _alphasift_context_support_module_name
    )
_alphasift_context_support_names = (
    "_build_alphasift_context",
)
_alphasift_context_binding_module.bind_facade_functions(
    vars(_alphasift_context_support_module),
    globals(),
    _alphasift_context_support_names,
)
del _alphasift_context_support_names

@contextmanager
def _alphasift_litellm_headers(config: Config) -> Iterator[None]:
    header_routes = _build_alphasift_litellm_header_routes(config)  # noqa: F821
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
            matching_routes = _match_alphasift_litellm_routes(args, kwargs, routes)  # noqa: F821
            headers = next(
                (
                    dict(route.get("extra_headers") or {})
                    for route in matching_routes
                    if route.get("extra_headers")
                ),
                {},
            )
            outbound_urls = _dedupe_strings(  # noqa: F821
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
            value = _env_text(kwargs.get(key))  # noqa: F821
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


_alphasift_context_support_names = (
    "_build_alphasift_litellm_model_list",
    "_channel_litellm_model_list",
    "_build_alphasift_litellm_header_routes",
    "_match_alphasift_litellm_routes",
    "_resolve_dsa_llm_max_candidates",
    "_resolve_alphasift_llm_models",
    "_is_managed_litellm_model",
    "_normalize_dsa_llm_channels",
    "_channel_keys_for_provider",
    "_first_channel_base_url",
    "_put_provider_keys",
    "_dedupe_strings",
    "_env_text",
    "_get_dsa_fetcher_manager",
    "_get_dsa_search_service",
    "get_dsa_daily_history",
    "_normalize_dsa_daily_history",
    "_normalize_daily_date_value",
    "get_dsa_realtime_quote",
    "get_dsa_fundamental_context",
    "search_dsa_stock_news",
    "get_dsa_candidate_context",
    "_enrich_candidates_with_dsa",
    "_candidate_has_dsa_news",
    "_news_has_results",
    "_build_dsa_candidate_context",
    "_first_non_empty",
    "_compact_fundamental_context",
    "_build_dsa_analysis_summary",
    "_ensure_supported_market",
    "_normalize_candidates",
    "_normalize_candidate",
    "_extract_dsa_news_from_context",
    "_extract_dsa_analysis_summary_from_context",
    "_first_present",
    "_build_candidate_reason",
    "_to_plain",
    "_remove_non_finite_json_values",
    "_build_install_response",
    "_is_default_alphasift_install_spec",
)
_alphasift_context_binding_module.bind_facade_functions(
    vars(_alphasift_context_support_module),
    globals(),
    _alphasift_context_support_names,
)
del (
    _alphasift_context_binding_module,
    _alphasift_context_binding_module_name,
    _alphasift_context_part_modules,
    _alphasift_context_support_module,
    _alphasift_context_support_module_name,
    _alphasift_context_support_names,
)
