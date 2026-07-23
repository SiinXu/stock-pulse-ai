# -*- coding: utf-8 -*-
"""
===================================
A股自选股智能分析系统 - 搜索服务模块
===================================

职责：
1. 提供统一的新闻搜索接口
2. 支持 Bocha、Tavily、Brave、SerpAPI、SearXNG 多种搜索引擎
3. 多 Key 负载均衡和故障转移
4. 搜索结果缓存和格式化
"""

import logging
import re
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import List, Dict, Any, Optional, Tuple
from itertools import cycle
from urllib.parse import parse_qsl, unquote, urlparse
import requests
from newspaper import Article, Config
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from data_provider.us_index_mapping import is_us_index_code
from src.config import (
    NEWS_STRATEGY_WINDOWS,
    normalize_news_strategy_profile,
    resolve_news_window_days,
)
from src.security.outbound_policy import safe_get, safe_post
from src.services.run_diagnostics import record_provider_run, record_provider_run_started
from src.utils.sanitize import (
    exception_chain_redaction_values,
    log_safe_exception,
    safe_before_sleep_log,
)

logger = logging.getLogger(__name__)

_SEARCH_REQUEST_FAILED = "Search request failed."
_SEARXNG_JSON_DISABLED = (
    "Search request failed (HTTP 403); the SearXNG instance may not enable JSON output "
    "(check settings.yml) or may reject this request."
)


from typing import TYPE_CHECKING as _TYPE_CHECKING

if _TYPE_CHECKING:
    from src.search_parts.anspire import AnspireSearchProvider
    from src.search_parts.bocha import BochaSearchProvider
    from src.search_parts.brave import BraveSearchProvider
    from src.search_parts.minimax import MiniMaxSearchProvider
    from src.search_parts.provider_base import (
        BaseSearchProvider,
        SearchResponse,
        SearchResult,
        _get_with_retry,
        _log_search_failure,
        _post_with_retry,
        _safe_search_exception_message,
        _stabilize_failed_search_response,
        _stable_search_failure_message,
        fetch_url_content,
    )
    from src.search_parts.searxng import SearXNGSearchProvider
    from src.search_parts.serpapi import SerpAPISearchProvider
    from src.search_parts.tavily import TavilySearchProvider


from importlib.util import find_spec as _find_spec

_SEARCH_SOURCE_MODULES = (
    "src.search_parts.provider_base",
    "src.search_parts.tavily",
    "src.search_parts.serpapi",
    "src.search_parts.bocha",
    "src.search_parts.anspire",
    "src.search_parts.minimax",
    "src.search_parts.brave",
    "src.search_parts.searxng",
)
for _search_source_module in _SEARCH_SOURCE_MODULES:
    _search_source_spec = _find_spec(_search_source_module)
    if _search_source_spec is None or _search_source_spec.loader is None:
        raise ImportError(
            f"Unable to load search source module: {_search_source_module}"
        )
    _search_source_code = _search_source_spec.loader.get_code(_search_source_module)
    if _search_source_code is None:
        raise ImportError(
            f"Search source module has no executable code: {_search_source_module}"
        )
    exec(_search_source_code, globals())
del (
    _SEARCH_SOURCE_MODULES,
    _TYPE_CHECKING,
    _find_spec,
    _search_source_code,
    _search_source_module,
    _search_source_spec,
)


class SearchService:
    """
    搜索服务
    
    功能：
    1. 管理多个搜索引擎
    2. 自动故障转移
    3. 结果聚合和格式化
    4. 数据源失败时的增强搜索（股价、走势等）
    5. 港股/美股自动使用英文搜索关键词
    """
    
    # Enhance search keyword template (A-shares Chinese)
    ENHANCED_SEARCH_KEYWORDS = [
        "{name} 股票 今日 股价",
        "{name} {code} 最新 行情 走势",
        "{name} 股票 分析 走势图",
        "{name} K线 技术分析",
        "{name} {code} 涨跌 成交量",
    ]

    # Enhance search keyword template (Hong Kong stocks/U.S. stocks English)
    ENHANCED_SEARCH_KEYWORDS_EN = [
        "{name} stock price today",
        "{name} {code} latest quote trend",
        "{name} stock analysis chart",
        "{name} technical analysis",
        "{name} {code} performance volume",
    ]
    NEWS_OVERSAMPLE_FACTOR = 2
    NEWS_OVERSAMPLE_MAX = 10
    FUTURE_TOLERANCE_DAYS = 1
    ANALYTICAL_INTEL_LOOKBACK_DAYS = 180
    ANALYTICAL_INTEL_DIMENSIONS = {"market_analysis", "earnings"}
    _CHINESE_TEXT_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
    _US_STOCK_RE = re.compile(r"^[A-Za-z]{1,5}(\.[A-Za-z])?$")
    _DIRECT_NEWS_CATEGORY = "direct_company_news"
    _SECTOR_NEWS_CATEGORY = "sector_related_news"
    _MACRO_NEWS_CATEGORY = "macro_market_news"
    _NEWS_CATEGORY_PRIORITY = {
        _DIRECT_NEWS_CATEGORY: 0,
        _SECTOR_NEWS_CATEGORY: 1,
        _MACRO_NEWS_CATEGORY: 2,
    }
    _AMBIGUOUS_EN_COMPANY_NAMES = {"apple", "meta", "square", "target", "gap"}
    _AMBIGUOUS_EN_CONFIRMING_EVENT_TERMS = (
        "earnings", "revenue", "profit", "guidance", "filing", "buyback",
        "dividend", "lawsuit", "merger", "acquisition",
    )
    _COMPANY_EVENT_TERMS = (
        "公告", "披露", "发布", "收购", "回购", "减持", "增持", "诉讼", "处罚",
        "业绩", "财报", "营收", "净利润", "分红", "董事会", "股东大会", "订单",
        "合作", "中标", "earnings", "revenue", "profit", "guidance", "filing",
        "sec", "shares", "stock", "buyback", "dividend", "lawsuit", "merger",
        "acquisition", "results", "quarterly", "annual", "announces", "launches",
    )
    _SECTOR_NEWS_TERMS = (
        "行业", "板块", "产业链", "龙头", "概念股", "赛道", "sector", "industry",
        "peers", "competitors", "supply chain", "market share",
    )
    _MACRO_NEWS_TERMS = (
        "大盘", "市场", "指数", "宏观", "央行", "利率", "通胀", "a股", "港股",
        "美股", "纳指", "标普", "market", "index", "fed", "inflation",
        "interest rate", "nasdaq", "s&p 500", "dow jones",
    )
    _OFFICIAL_SOURCE_TERMS = (
        "cninfo", "sse.com", "szse.cn", "hkexnews", "sec.gov", "nasdaq.com",
        "nyse.com", "上交所", "深交所", "港交所", "证券交易所",
    )
    _OFFICIAL_SOURCE_HOSTS = (
        "cninfo.com.cn", "sse.com", "sse.com.cn", "szse.cn", "hkexnews.hk",
        "sec.gov", "nasdaq.com", "nyse.com",
    )
    _OFFICIAL_SOURCE_LABELS = (
        "cninfo", "hkexnews", "巨潮资讯", "巨潮资讯网",
        "上交所", "深交所", "港交所", "证券交易所",
        "上海证券交易所", "深圳证券交易所", "香港交易所", "香港联合交易所",
    )
    _LOW_QUALITY_DOWNLOAD_ACTION_TERMS = (
        "下载", "安装", "下载安装", "下载安装到手机", "下载链接",
        "免费下载", "客户端下载", "应用下载", "官方app下载",
        "安装包", "apk", "download", "install", "installer",
    )
    _LOW_QUALITY_DOWNLOAD_INTENT_TERMS = (
        "安装包", "客户端下载", "应用下载", "下载安装", "下载安装到手机",
        "下载链接", "免费下载", "旧版下载", "极速版下载", "官方app下载",
    )
    _LOW_QUALITY_APP_CONTEXT_TERMS = (
        "好评", "评分", "版本", "大小", "适用年龄", "开发者", "应用",
        "ratings", "reviews", "stars", "version", "developer", "package",
    )
    _LOW_QUALITY_APP_METADATA_TERMS = (
        "版本", "大小", "适用年龄", "开发者", "应用", "应用商店",
        "安卓版", "苹果版", "官方版", "最新版", "version", "developer",
        "package", "mobile app",
    )
    _LOW_QUALITY_APP_PAGE_DETAIL_TERMS = (
        "客户端", "安卓版", "苹果版", "官方版", "最新版", "应用商店",
        "下载安装到手机", "一键下载", "旧版下载", "极速版下载",
    )
    _LOW_QUALITY_FILE_SIZE_RE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:kb|mb|gb)\b", re.IGNORECASE)
    _LOW_QUALITY_RATING_RE = re.compile(
        r"(?:\d{1,3}\s*%\s*好评|好评率|用户评分|"
        r"(?:用户)?评分\s*[:：]?\s*(?:10|[0-9])(?:\.\d{1,2})?|"
        r"\b\d(?:\.\d)?\s*(?:stars?|ratings?|reviews?)\b)",
        re.IGNORECASE,
    )
    _LOW_QUALITY_URL_RE = re.compile(
        r"(?:^|[/_.=-])(?:download|downloads|apk|ipa|exe|dmg|installer|"
        r"software|soft|game|games|app|apps|package)(?:$|[/_.?&=-])",
        re.IGNORECASE,
    )
    _BUSINESS_APP_METRIC_RE = re.compile(
        r"(?:(?:下载量|安装量|装机量|应用下载|应用安装|app下载|app安装).{0,12}"
        r"(?:增长|同比|环比|上升|增加|提升|突破|达到|达|超过|超|累计|接近|保持|创新高|下降|下滑|减少|回落|放缓|持平|承压|低迷)|"
        r"(?:增长|同比|环比|上升|增加|提升|突破|达到|达|超过|超|累计|接近|保持|创新高|下降|下滑|减少|回落|放缓|持平|承压|低迷)"
        r".{0,12}(?:下载量|安装量|装机量|应用下载|应用安装|app下载|app安装)|"
        r"\b(?:downloads?|installs?)\b.{0,16}"
        r"\b(?:grew|growth|rose|increase|increased|surged|reached|reach|reaches|"
        r"hit|hits|topped|totaled|totalled|exceeded|exceeds|surpassed|surpasses|"
        r"fell|fall|declined|decline|decreased|dropped|drop|slowed|flat|weakened)\b|"
        r"\b(?:grew|growth|rose|increase|increased|surged|reached|reach|reaches|"
        r"hit|hits|topped|totaled|totalled|exceeded|exceeds|surpassed|surpasses|"
        r"fell|fall|declined|decline|decreased|dropped|drop|slowed|flat|weakened)\b"
        r".{0,16}\b(?:downloads?|installs?)\b)",
        re.IGNORECASE,
    )
    _ADULT_SERVICE_SPAM_STRONG_TERMS = (
        "上门特殊服务", "同城约", "约炮", "援交", "楼凤", "外围女",
        "外围服务", "包夜", "大保健", "莞式", "推油",
        "成人服务", "adult service", "escort service",
        "sex service", "call girl",
    )
    _ADULT_SERVICE_SPAM_AMBIGUOUS_TERMS = (
        "全套服务", "色情",
    )
    _ADULT_SERVICE_SPAM_CONTEXT_TERMS = (
        "小姐", "上门", "预约", "同城", "按摩", "保健", "足浴", "桑拿",
        "会所", "技师", "全套", "套餐", "vip",
    )
    _ADULT_SERVICE_SPAM_CONTACT_RE = re.compile(
        r"(?:^|[^a-z0-9])(?:yue|vx|wx|qq|wechat|weixin|微信号?|微[信讯]|"
        r"电话|手机|联系电话|tel|phone)"
        r"[-_:\s：]*[a-z0-9][a-z0-9_-]{2,}(?:[^a-z0-9]|$)",
        re.IGNORECASE,
    )
    _ADULT_SERVICE_SPAM_CONTACT_CONTEXT_TERMS = (
        "小姐", "上门", "同城", "预约",
        "全套", "包夜", "大保健", "推油",
        "约炮", "援交", "成人", "色情",
    )
    _ADULT_SERVICE_REMEDIATION_TERMS = (
        "治理", "整治", "下架", "处罚", "监管", "打击", "清理",
        "封禁", "整改", "内容安全", "低俗内容", "平台风险",
    )
    _ADULT_SERVICE_SOLICITATION_TERMS = (
        "上门", "同城", "预约", "套餐", "包夜", "大保健",
        "推油", "联系", "咨询", "加微信", "加qq", "vip",
    )

    def __init__(
        self,
        bocha_keys: Optional[List[str]] = None,
        tavily_keys: Optional[List[str]] = None,
        anspire_keys: Optional[List[str]] = None,
        brave_keys: Optional[List[str]] = None,
        serpapi_keys: Optional[List[str]] = None,
        minimax_keys: Optional[List[str]] = None,
        searxng_base_urls: Optional[List[str]] = None,
        searxng_public_instances_enabled: bool = True,
        news_max_age_days: int = 3,
        news_strategy_profile: str = "short",
    ):
        """
        初始化搜索服务

        Args:
            bocha_keys: 博查搜索 API Key 列表
            tavily_keys: Tavily API Key 列表
            anspire_keys: Anspire Search API Key 列表
            brave_keys: Brave Search API Key 列表
            serpapi_keys: SerpAPI Key 列表
            minimax_keys: MiniMax API Key 列表
            searxng_base_urls: SearXNG 实例地址列表（自建无配额兜底）
            searxng_public_instances_enabled: 未配置自建实例时，是否自动使用公共 SearXNG 实例
            news_max_age_days: 新闻最大时效（天）
            news_strategy_profile: 新闻窗口策略档位（ultra_short/short/medium/long）
        """
        self._providers: List[BaseSearchProvider] = []
        self.news_max_age_days = max(1, news_max_age_days)
        raw_profile = (news_strategy_profile or "short").strip().lower()
        self.news_strategy_profile = normalize_news_strategy_profile(news_strategy_profile)
        if raw_profile != self.news_strategy_profile:
            logger.warning(
                "NEWS_STRATEGY_PROFILE '%s' 无效，已回退为 'short'",
                news_strategy_profile,
            )
        self.news_window_days = resolve_news_window_days(
            news_max_age_days=self.news_max_age_days,
            news_strategy_profile=self.news_strategy_profile,
        )
        self.news_profile_days = NEWS_STRATEGY_WINDOWS.get(
            self.news_strategy_profile,
            NEWS_STRATEGY_WINDOWS["short"],
        )

        # Initialize the search engine (sorted by priority)
        # 1. Bocha priority (Chinese search optimization, AI summary)
        if bocha_keys:
            self._providers.append(BochaSearchProvider(bocha_keys))
            logger.info(f"已配置 Bocha 搜索，共 {len(bocha_keys)} 个 API Key")

        # 2. Tavily (offers more free quota, 1000 times per month)
        if tavily_keys:
            self._providers.append(TavilySearchProvider(tavily_keys))
            logger.info(f"已配置 Tavily 搜索，共 {len(tavily_keys)} 个 API Key")

        # 3. Brave Search (privacy-first, global coverage)
        if brave_keys:
            self._providers.append(BraveSearchProvider(brave_keys))
            logger.info(f"已配置 Brave 搜索，共 {len(brave_keys)} 个 API Key")

        # 4. SerpAPI as a backup (100 requests per month)
        if serpapi_keys:
            self._providers.append(SerpAPISearchProvider(serpapi_keys))
            logger.info(f"已配置 SerpAPI 搜索，共 {len(serpapi_keys)} 个 API Key")

        # 5. MiniMax(Coding Plan Web Search, Structured result)
        if minimax_keys:
            self._providers.append(MiniMaxSearchProvider(minimax_keys))
            logger.info(f"已配置 MiniMax 搜索，共 {len(minimax_keys)} 个 API Key")

        # 6. SearXNG (prioritize self-hosted instances; automatically discover public instances if not configured)
        searxng_provider = SearXNGSearchProvider(
            searxng_base_urls,
            use_public_instances=bool(searxng_public_instances_enabled and not searxng_base_urls),
        )
        if searxng_provider.is_available:
            self._providers.append(searxng_provider)
            if searxng_base_urls:
                logger.info("已配置 SearXNG 搜索，共 %s 个自建实例", len(searxng_base_urls))
            else:
                logger.info("已启用 SearXNG 公共实例自动发现模式")

        # 7. Anspire Search (real-time intelligent search optimization)
        if anspire_keys:
            self._providers.insert(0, AnspireSearchProvider(anspire_keys))
            logger.info(f"已配置 Anspire Search 搜索，共 {len(anspire_keys)} 个 API Key")
            
        if not self._providers:
            logger.warning("未配置任何搜索能力，新闻搜索功能将不可用")

        # In-memory search result cache: {cache_key: (timestamp, SearchResponse)}
        self._cache: Dict[str, Tuple[float, 'SearchResponse']] = {}
        self._cache_lock = threading.RLock()
        self._cache_inflight: Dict[str, threading.Event] = {}
        # Default cache TTL in seconds (10 minutes)
        self._cache_ttl: int = 600
        logger.info(
            "新闻时效策略已启用: profile=%s, profile_days=%s, NEWS_MAX_AGE_DAYS=%s, effective_window=%s",
            self.news_strategy_profile,
            self.news_profile_days,
            self.news_max_age_days,
            self.news_window_days,
        )
    
    _is_foreign_stock = None

    _contains_chinese_text = None

    _is_us_stock = None

    _should_prefer_chinese_news = None

    _is_chinese_news_result = None

    _prioritize_news_language = None

    _is_better_preferred_news_response = None

    _brave_search_locale = None

    # A-share ETF code prefixes (Shanghai 51/52/56/58, Shenzhen 15/16/18)
    _A_ETF_PREFIXES = ('51', '52', '56', '58', '15', '16', '18')
    _ETF_NAME_KEYWORDS = ('ETF', 'FUND', 'TRUST', 'INDEX', 'TRACKER', 'UNIT')  # US/HK ETF name hints

    is_index_or_etf = None

    is_available = None

    _cache_key = None

    _get_cached_locked = None

    _get_cached = None

    _get_cached_or_reserve = None

    _release_cache_fill = None

    _wait_for_cached = None

    _put_cache = None

    _effective_news_window_days = None

    _provider_request_size = None

    _append_unique = None

    _stock_code_identity_terms = None

    _company_identity_terms = None

    _contains_identity_term = None

    _contains_stock_code_identity_term = None

    _contains_any_news_term = None

    _contains_any_low_quality_news_term = None

    _candidate_hostname = None

    _source_resembles_hostname = None

    _is_trusted_official_news_source = None

    _has_low_quality_news_page_signal = None

    _has_adult_service_spam_news_page_signal = None

    _score_news_relevance = None

    _rank_news_response = None

    _filter_ranked_news_for_context = None

    _news_relevance_stats = None

    _is_better_ranked_news_response = None

    _parse_relative_news_date = None

    _normalize_news_publish_date = None

    _filter_news_response = None

    _normalize_and_limit_response = None

    _limit_search_response = None

    _elapsed_ms = None

    _record_news_search_run = None

    search_stock_news = None

    search_stock_events = None

    search_comprehensive_intel = None

    format_intel_report = None

    batch_search = None

    search_stock_price_fallback = None

    search_stock_with_enhanced_fallback = None

    format_price_search_context = None


# Load method source containers without importing them through ``sys.modules``.
# This keeps direct private-module imports cycle-safe while the rebound methods
# retain the public facade globals used by legacy patch and reload seams.
from importlib.util import find_spec as _find_method_source_spec
from src.agent.facade_binding import bind_facade_methods as _bind_facade_methods

_SEARCH_METHOD_SOURCES = (
    (
        "src.search_parts.service_state",
        "_ServiceStateMethods",
        (
            "_is_foreign_stock",
            "_contains_chinese_text",
            "_is_us_stock",
            "_should_prefer_chinese_news",
            "_is_chinese_news_result",
            "_prioritize_news_language",
            "_is_better_preferred_news_response",
            "_brave_search_locale",
            "is_index_or_etf",
            "is_available",
            "_cache_key",
            "_get_cached_locked",
            "_get_cached",
            "_get_cached_or_reserve",
            "_release_cache_fill",
            "_wait_for_cached",
            "_put_cache",
            "_effective_news_window_days",
        ),
    ),
    (
        "src.search_parts.news_processing",
        "_NewsProcessingMethods",
        (
            "_provider_request_size",
            "_append_unique",
            "_stock_code_identity_terms",
            "_company_identity_terms",
            "_contains_identity_term",
            "_contains_stock_code_identity_term",
            "_contains_any_news_term",
            "_contains_any_low_quality_news_term",
            "_candidate_hostname",
            "_source_resembles_hostname",
            "_is_trusted_official_news_source",
            "_has_low_quality_news_page_signal",
            "_has_adult_service_spam_news_page_signal",
            "_score_news_relevance",
            "_rank_news_response",
            "_filter_ranked_news_for_context",
            "_news_relevance_stats",
            "_is_better_ranked_news_response",
            "_parse_relative_news_date",
            "_normalize_news_publish_date",
            "_filter_news_response",
            "_normalize_and_limit_response",
            "_limit_search_response",
            "_elapsed_ms",
            "_record_news_search_run",
        ),
    ),
    (
        "src.search_parts.orchestration",
        "_OrchestrationMethods",
        (
            "search_stock_news",
            "search_stock_events",
            "search_comprehensive_intel",
            "format_intel_report",
            "batch_search",
            "search_stock_price_fallback",
            "search_stock_with_enhanced_fallback",
            "format_price_search_context",
        ),
    ),
)

for (
    _search_method_source_module,
    _search_method_container_name,
    _expected_search_method_names,
) in _SEARCH_METHOD_SOURCES:
    _search_method_source_spec = _find_method_source_spec(
        _search_method_source_module
    )
    if (
        _search_method_source_spec is None
        or _search_method_source_spec.loader is None
    ):
        raise ImportError(
            f"Unable to load search method source module: "
            f"{_search_method_source_module}"
        )
    _search_method_source_code = _search_method_source_spec.loader.get_code(
        _search_method_source_module
    )
    if _search_method_source_code is None:
        raise ImportError(
            f"Search method source module has no executable code: "
            f"{_search_method_source_module}"
        )
    _search_method_namespace = dict(globals())
    _search_method_namespace.update(
        {
            "__name__": _search_method_source_module,
            "__package__": _search_method_source_spec.parent,
            "__loader__": _search_method_source_spec.loader,
            "__spec__": _search_method_source_spec,
            "__file__": _search_method_source_spec.origin,
            "__cached__": _search_method_source_spec.cached,
            "_SEARCH_FACADE_LOADING": True,
        }
    )
    exec(_search_method_source_code, _search_method_namespace)
    _search_method_container = _search_method_namespace[
        _search_method_container_name
    ]
    _bound_search_method_names = _bind_facade_methods(
        SearchService,
        _search_method_container,
        globals(),
    )
    if _bound_search_method_names != _expected_search_method_names:
        raise ImportError(
            f"Unexpected methods in search source module "
            f"{_search_method_source_module}: {_bound_search_method_names!r}"
        )

del (
    _SEARCH_METHOD_SOURCES,
    _bind_facade_methods,
    _bound_search_method_names,
    _expected_search_method_names,
    _find_method_source_spec,
    _search_method_container,
    _search_method_container_name,
    _search_method_namespace,
    _search_method_source_code,
    _search_method_source_module,
    _search_method_source_spec,
)


# === Convenience Functions ===
_search_service: Optional[SearchService] = None
_search_service_lock = threading.Lock()


def get_search_service() -> SearchService:
    """获取搜索服务单例"""
    global _search_service
    
    if _search_service is None:
        with _search_service_lock:
            if _search_service is None:
                from src.config import get_config
                config = get_config()
                
                _search_service = SearchService(
                    bocha_keys=config.bocha_api_keys,
                    tavily_keys=config.tavily_api_keys,
                    anspire_keys=config.anspire_api_keys,
                    brave_keys=config.brave_api_keys,
                    serpapi_keys=config.serpapi_keys,
                    minimax_keys=config.minimax_api_keys,
                    searxng_base_urls=config.searxng_base_urls,
                    searxng_public_instances_enabled=config.searxng_public_instances_enabled,
                    news_max_age_days=config.news_max_age_days,
                    news_strategy_profile=getattr(config, "news_strategy_profile", "short"),
                )
    
    return _search_service


def reset_search_service() -> None:
    """重置搜索服务（用于测试）"""
    global _search_service
    with _search_service_lock:
        _search_service = None


if __name__ == "__main__":
    # Testing search service
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s'
    )
    
    # Manual testing (requires API Key configuration)
    service = get_search_service()
    
    if service.is_available:
        print("=== 测试股票新闻搜索 ===")
        response = service.search_stock_news("300389", "艾比森")
        print(f"搜索状态: {'成功' if response.success else '失败'}")
        print(f"搜索引擎: {response.provider}")
        print(f"结果数量: {len(response.results)}")
        print(f"耗时: {response.search_time:.2f}s")
        print("\n" + response.to_context())
    else:
        print("未配置搜索能力，跳过测试")
