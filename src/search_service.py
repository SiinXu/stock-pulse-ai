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
    
    @staticmethod
    def _is_foreign_stock(stock_code: str) -> bool:
        """判断是否为港股或美股"""
        code = stock_code.strip()
        # U.S. stocks: 1-5 uppercase letters, may contain periods (e.g., BRK.B)
        if SearchService._US_STOCK_RE.match(code):
            return True
        # Hong Kong stocks: With hk prefix or 5-digit numbers only
        lower = code.lower()
        if lower.startswith('hk'):
            return True
        if code.isdigit() and len(code) == 5:
            return True
        return False

    @classmethod
    def _contains_chinese_text(cls, value: Optional[str]) -> bool:
        """Return True when the input contains CJK characters."""
        return bool(value and cls._CHINESE_TEXT_RE.search(value))

    @classmethod
    def _is_us_stock(cls, stock_code: str) -> bool:
        """判断是否为美股/美股指数代码。"""
        code = (stock_code or "").strip().upper()
        return bool(cls._US_STOCK_RE.match(code) or is_us_index_code(code))

    @classmethod
    def _should_prefer_chinese_news(
        cls,
        stock_code: str,
        stock_name: str,
        focus_keywords: Optional[List[str]] = None,
    ) -> bool:
        """A 股或中文名称/关键词场景下优先中文资讯。

        Only returns True when there is a positive Chinese signal:
        Chinese characters in keywords/stock_name, or a 6-digit A-stock code.
        Avoids false positives for non-foreign but English contexts like
        ``stock_code="market", stock_name="US market"``.
        """
        if any(cls._contains_chinese_text(keyword) for keyword in (focus_keywords or [])):
            return True
        if cls._contains_chinese_text(stock_name):
            return True
        # Positive A-stock identification: 6-digit numeric codes (e.g. 600519)
        code = (stock_code or "").strip()
        return code.isdigit() and len(code) == 6

    @classmethod
    def _is_chinese_news_result(cls, item: SearchResult) -> bool:
        """Heuristic check for Chinese-language news items."""
        return cls._contains_chinese_text(" ".join(filter(None, [item.title, item.snippet, item.source])))

    @classmethod
    def _prioritize_news_language(
        cls,
        response: SearchResponse,
        *,
        prefer_chinese: bool,
    ) -> Tuple[SearchResponse, int]:
        """Reorder results by preferred language and return preferred-result count."""
        if not prefer_chinese or not response.success or not response.results:
            return response, 0

        chinese_results: List[SearchResult] = []
        other_results: List[SearchResult] = []
        for item in response.results:
            if cls._is_chinese_news_result(item):
                chinese_results.append(item)
            else:
                other_results.append(item)

        return (
            SearchResponse(
                query=response.query,
                results=chinese_results + other_results,
                provider=response.provider,
                success=response.success,
                error_message=response.error_message,
                search_time=response.search_time,
            ),
            len(chinese_results),
        )

    @classmethod
    def _is_better_preferred_news_response(
        cls,
        candidate: SearchResponse,
        *,
        candidate_preferred_count: int,
        best_response: Optional[SearchResponse],
        best_preferred_count: int,
    ) -> bool:
        """Prefer responses with more Chinese items, then more total items."""
        if best_response is None:
            return True
        if candidate_preferred_count != best_preferred_count:
            return candidate_preferred_count > best_preferred_count
        return len(candidate.results) > len(best_response.results)

    @classmethod
    def _brave_search_locale(
        cls,
        stock_code: str,
        *,
        prefer_chinese: bool,
    ) -> Dict[str, str]:
        """Resolve Brave locale hints without forcing US bias onto non-US symbols."""
        if prefer_chinese:
            return {"search_lang": "zh-hans", "country": "CN"}
        if cls._is_us_stock(stock_code):
            return {"search_lang": "en", "country": "US"}
        return {}

    # A-share ETF code prefixes (Shanghai 51/52/56/58, Shenzhen 15/16/18)
    _A_ETF_PREFIXES = ('51', '52', '56', '58', '15', '16', '18')
    _ETF_NAME_KEYWORDS = ('ETF', 'FUND', 'TRUST', 'INDEX', 'TRACKER', 'UNIT')  # US/HK ETF name hints

    @staticmethod
    def is_index_or_etf(stock_code: str, stock_name: str) -> bool:
        """
        Judge if symbol is index-tracking ETF or market index.
        For such symbols, analysis focuses on index movement only, not issuer company risks.
        """
        code = (stock_code or '').strip().split('.')[0]
        if not code:
            return False
        # A-share ETF
        if code.isdigit() and len(code) == 6 and code.startswith(SearchService._A_ETF_PREFIXES):
            return True
        # US index (SPX, DJI, IXIC etc.)
        if is_us_index_code(code):
            return True
        # US/HK ETF: foreign symbol + name contains fund-like keywords
        if SearchService._is_foreign_stock(code):
            name_upper = (stock_name or '').upper()
            return any(kw in name_upper for kw in SearchService._ETF_NAME_KEYWORDS)
        return False

    @property
    def is_available(self) -> bool:
        """检查是否有可用的搜索引擎"""
        return any(p.is_available for p in self._providers)

    def _cache_key(self, query: str, max_results: int, days: int) -> str:
        """Build a cache key from query parameters."""
        return f"{query}|{max_results}|{days}"

    def _get_cached_locked(self, key: str) -> Optional['SearchResponse']:
        entry = self._cache.get(key)
        if entry is None:
            return None
        ts, response = entry
        if time.time() - ts > self._cache_ttl:
            self._cache.pop(key, None)
            return None
        logger.debug(f"Search cache hit: {key[:60]}...")
        return response

    def _get_cached(self, key: str) -> Optional['SearchResponse']:
        """Return cached SearchResponse if still valid, else None."""
        with self._cache_lock:
            return self._get_cached_locked(key)

    def _get_cached_or_reserve(
        self,
        key: str,
    ) -> Tuple[Optional['SearchResponse'], bool, Optional[threading.Event]]:
        with self._cache_lock:
            cached = self._get_cached_locked(key)
            if cached is not None:
                return cached, False, None

            event = self._cache_inflight.get(key)
            if event is None:
                event = threading.Event()
                self._cache_inflight[key] = event
                return None, True, event
            return None, False, event

    def _release_cache_fill(self, key: str, event: threading.Event) -> None:
        with self._cache_lock:
            current = self._cache_inflight.get(key)
            if current is event:
                self._cache_inflight.pop(key, None)
                event.set()

    def _wait_for_cached(self, key: str, event: threading.Event) -> Optional['SearchResponse']:
        event.wait(timeout=max(1.0, min(float(self._cache_ttl), 30.0)))
        return self._get_cached(key)

    def _put_cache(self, key: str, response: 'SearchResponse') -> None:
        """Store a successful SearchResponse in cache."""
        with self._cache_lock:
            # Hard cap: evict oldest entries when cache exceeds limit
            _MAX_CACHE_SIZE = 500
            if len(self._cache) >= _MAX_CACHE_SIZE:
                now = time.time()
                # First pass: remove expired entries
                expired = [k for k, (ts, _) in self._cache.items() if now - ts > self._cache_ttl]
                for k in expired:
                    self._cache.pop(k, None)
                # Second pass: if still over limit, evict oldest entries (FIFO)
                if len(self._cache) >= _MAX_CACHE_SIZE:
                    excess = len(self._cache) - _MAX_CACHE_SIZE + 1
                    oldest = sorted(self._cache.keys(), key=lambda k: self._cache[k][0])[:excess]
                    for k in oldest:
                        self._cache.pop(k, None)
            self._cache[key] = (time.time(), response)

    def _effective_news_window_days(self) -> int:
        """Resolve effective news window from strategy profile and global max-age."""
        return resolve_news_window_days(
            news_max_age_days=self.news_max_age_days,
            news_strategy_profile=self.news_strategy_profile,
        )

    @classmethod
    def _provider_request_size(cls, max_results: int) -> int:
        """Apply light overfetch before time filtering to avoid sparse outputs."""
        target = max(1, int(max_results))
        return max(target, min(target * cls.NEWS_OVERSAMPLE_FACTOR, cls.NEWS_OVERSAMPLE_MAX))

    @staticmethod
    def _append_unique(values: List[str], value: Optional[str]) -> None:
        cleaned = (value or "").strip()
        if cleaned and cleaned not in values:
            values.append(cleaned)

    @classmethod
    def _stock_code_identity_terms(cls, stock_code: str) -> List[str]:
        """Return code/ticker variants that should count as strong identity hits."""
        raw = (stock_code or "").strip()
        if not raw:
            return []

        terms: List[str] = []
        upper = raw.upper()
        code_for_variants = upper
        if "." in upper:
            base, suffix = upper.rsplit(".", 1)
            if suffix == "HK" and base.isdigit() and 1 <= len(base) <= 5:
                code_for_variants = f"HK{base.zfill(5)}"
            elif suffix in {"SH", "SZ", "SS", "BJ"} and base.isdigit() and len(base) == 6:
                code_for_variants = base
            elif suffix == "US" and re.fullmatch(r"[A-Z]{1,5}", base):
                code_for_variants = base

        is_us_ticker = bool(cls._US_STOCK_RE.match(code_for_variants))
        if not is_us_ticker:
            cls._append_unique(terms, raw)
            cls._append_unique(terms, upper)
            if code_for_variants != upper:
                cls._append_unique(terms, code_for_variants)

        lower = code_for_variants.lower()
        hk_digits = ""
        if lower.startswith("hk"):
            hk_digits = re.sub(r"\D", "", code_for_variants)
        elif code_for_variants.isdigit() and len(code_for_variants) == 5:
            hk_digits = code_for_variants

        if hk_digits:
            padded = hk_digits.zfill(5)
            short = str(int(hk_digits)) if hk_digits.isdigit() else hk_digits.lstrip("0")
            cls._append_unique(terms, padded)
            cls._append_unique(terms, f"HK{padded}")
            cls._append_unique(terms, f"{padded}.HK")
            cls._append_unique(terms, f"{short}.HK")
            cls._append_unique(terms, f"HKEX:{short}")
            return terms

        if code_for_variants.isdigit() and len(code_for_variants) == 6:
            suffix = ".SH" if code_for_variants.startswith(("5", "6", "9")) else ".SZ"
            cls._append_unique(terms, f"{code_for_variants}{suffix}")
            return terms

        if cls._US_STOCK_RE.match(code_for_variants):
            cls._append_unique(terms, f"${code_for_variants}")
            cls._append_unique(terms, f"NASDAQ:{code_for_variants}")
            cls._append_unique(terms, f"NYSE:{code_for_variants}")
            if len(code_for_variants) > 1:
                cls._append_unique(terms, code_for_variants)
            return terms

        return terms

    @classmethod
    def _company_identity_terms(cls, stock_name: str) -> List[str]:
        """Return conservative company-name variants for relevance matching."""
        raw = (stock_name or "").strip()
        if not raw:
            return []

        terms: List[str] = []
        cls._append_unique(terms, raw)

        without_market_suffix = re.sub(r"[-－（(].*$", "", raw).strip()
        cls._append_unique(terms, without_market_suffix)

        if cls._contains_chinese_text(raw):
            cleaned = re.sub(
                r"(股份有限公司|有限责任公司|有限公司|控股集团|控股|集团|股份|公司)$",
                "",
                without_market_suffix,
            ).strip()
            if len(cleaned) >= 4:
                cls._append_unique(terms, cleaned)
        else:
            cleaned = re.sub(
                r"\b(incorporated|inc|corporation|corp|company|co|plc|ltd|limited|holdings?)\.?$",
                "",
                without_market_suffix,
                flags=re.IGNORECASE,
            ).strip()
            if len(cleaned) >= 3:
                cls._append_unique(terms, cleaned)

        return terms

    @classmethod
    def _contains_identity_term(cls, text: str, term: str) -> bool:
        if not text or not term:
            return False

        if cls._contains_chinese_text(term):
            start = 0
            while True:
                index = text.find(term, start)
                if index < 0:
                    return False
                next_char = text[index + len(term):index + len(term) + 1]
                if next_char not in {"镇", "村", "县"}:
                    return True
                start = index + len(term)

        lower_text = text.lower()
        lower_term = term.lower()
        if lower_term.startswith("$"):
            return lower_term in lower_text

        pattern = r"(?<![A-Za-z0-9])" + re.escape(lower_term) + r"(?![A-Za-z0-9])"
        return bool(re.search(pattern, lower_text))

    @classmethod
    def _contains_stock_code_identity_term(cls, text: str, term: str) -> bool:
        if not text or not term:
            return False

        if cls._US_STOCK_RE.match(term) and term.upper() == term and not term.startswith("$"):
            ticker_pattern = f"(?:{re.escape(term)}|{re.escape(term.lower())})"
            pattern = (
                r"(?<![A-Za-z0-9$:.])"
                + ticker_pattern
                + r"(?=$|[^A-Za-z0-9.]|\.(?:US|us|O|o|N|n|NYSE|nyse|NASDAQ|nasdaq|AMEX|amex)\b)"
            )
            return bool(re.search(pattern, text))

        return cls._contains_identity_term(text, term)

    @classmethod
    def _contains_any_news_term(cls, text: str, terms: Tuple[str, ...]) -> bool:
        lower = (text or "").lower()
        return any(term.lower() in lower for term in terms)

    @classmethod
    def _contains_any_low_quality_news_term(cls, text: str, terms: Tuple[str, ...]) -> bool:
        lower = (text or "").lower()
        if not lower:
            return False

        for term in terms:
            normalized_term = term.lower()
            if not normalized_term:
                continue
            if normalized_term.isascii() and re.search(r"[a-z0-9]", normalized_term):
                pattern = r"(?<![A-Za-z0-9])" + re.escape(normalized_term) + r"(?![A-Za-z0-9])"
                if re.search(pattern, lower):
                    return True
                continue
            if normalized_term in lower:
                return True
        return False

    @staticmethod
    def _candidate_hostname(value: Any) -> str:
        raw = str(value or "").strip().lower()
        if not raw or re.search(r"\s", raw):
            return ""

        parse_value = (
            raw
            if re.match(r"^[a-z][a-z0-9+.-]*://", raw) or raw.startswith("//")
            else f"//{raw}"
        )
        return (urlparse(parse_value).hostname or "").rstrip(".")

    @staticmethod
    def _source_resembles_hostname(value: Any) -> bool:
        raw = str(value or "").strip().lower()
        if not raw or re.search(r"\s", raw):
            return False
        if re.match(r"^[a-z][a-z0-9+.-]*://", raw) or raw.startswith("//"):
            return True
        return bool(re.search(r"\.[a-z0-9-]{2,}(?::\d+)?/?$", raw))

    @classmethod
    def _is_trusted_official_news_source(cls, item: SearchResult) -> bool:
        """Only trust official exemptions from trusted hosts; fallback to labels only when URL host is absent."""
        url_host = cls._candidate_hostname(item.url)
        source_label = str(item.source or "").strip().lower()
        source_host = (
            cls._candidate_hostname(item.source)
            if cls._source_resembles_hostname(item.source)
            else ""
        )

        if url_host:
            # Use the hostname when a URL is present, avoid misleading official approvals with source label/host.
            return any(
                url_host == official_host or url_host.endswith(f".{official_host}")
                for official_host in cls._OFFICIAL_SOURCE_HOSTS
            )

        if source_host:
            return any(
                source_host == official_host or source_host.endswith(f".{official_host}")
                for official_host in cls._OFFICIAL_SOURCE_HOSTS
            )

        return source_label in cls._OFFICIAL_SOURCE_LABELS

    @classmethod
    def _has_low_quality_news_page_signal(cls, item: SearchResult) -> bool:
        """Detect app/download/listing pages without relying on a domain blocklist."""
        content_text = " ".join(filter(None, [item.title, item.snippet])).lower()
        parsed_url = urlparse(item.url or "")
        url_surface = unquote(
            " ".join(filter(None, [parsed_url.netloc, parsed_url.path, parsed_url.query]))
        ).lower()

        has_app_context = cls._contains_any_low_quality_news_term(
            content_text,
            cls._LOW_QUALITY_APP_CONTEXT_TERMS,
        )
        has_app_metadata = cls._contains_any_low_quality_news_term(
            content_text,
            cls._LOW_QUALITY_APP_METADATA_TERMS,
        )
        has_download_action = cls._contains_any_low_quality_news_term(
            content_text,
            cls._LOW_QUALITY_DOWNLOAD_ACTION_TERMS,
        )
        has_download_intent = cls._contains_any_low_quality_news_term(
            content_text,
            cls._LOW_QUALITY_DOWNLOAD_INTENT_TERMS,
        )
        has_app_page_detail = cls._contains_any_low_quality_news_term(
            content_text,
            cls._LOW_QUALITY_APP_PAGE_DETAIL_TERMS,
        )
        has_file_size = bool(cls._LOW_QUALITY_FILE_SIZE_RE.search(content_text))
        has_rating = bool(cls._LOW_QUALITY_RATING_RE.search(content_text))
        has_url_signal = bool(cls._LOW_QUALITY_URL_RE.search(url_surface))
        has_business_app_metric = bool(cls._BUSINESS_APP_METRIC_RE.search(content_text))
        has_app_listing_detail = (
            has_file_size
            or has_rating
            or cls._contains_any_low_quality_news_term(
                content_text,
                (
                    "版本", "适用年龄", "开发者", "应用商店", "安卓版",
                    "苹果版", "官方版", "最新版", "version", "developer",
                    "package",
                ),
            )
        )
        has_strong_app_page_evidence = (
            has_app_listing_detail
            and (
                has_url_signal
                or has_download_intent
                or (has_download_action and has_app_metadata)
            )
        )
        has_business_app_metric_only = (
            has_business_app_metric
            and not has_strong_app_page_evidence
        )
        has_app_listing_context = (
            not has_business_app_metric_only
            and has_app_context
            and has_app_metadata
            and (has_download_action or has_download_intent)
            and (has_file_size or has_rating)
        )
        has_content_download_page = (
            not has_business_app_metric_only
            and (
                (has_download_intent and (has_app_page_detail or has_file_size or has_rating))
                or (has_download_action and (has_app_metadata or has_file_size))
            )
        )
        has_url_backed_download_page = (
            not has_business_app_metric_only
            and has_url_signal
            and (
                has_file_size
                or has_download_intent
                or (has_download_action and has_app_metadata)
                or (has_app_metadata and has_rating)
            )
        )

        return (
            has_content_download_page
            or has_app_listing_context
            or has_url_backed_download_page
        )

    @classmethod
    def _has_adult_service_spam_news_page_signal(cls, item: SearchResult) -> bool:
        """Detect adult-service spam by content signals instead of domain names."""
        combined_text = " ".join(
            filter(None, [item.title, item.snippet, item.source, item.url])
        ).lower()

        if cls._contains_any_news_term(
            combined_text,
            cls._ADULT_SERVICE_SPAM_STRONG_TERMS,
        ):
            return True
        has_contact_signal = bool(cls._ADULT_SERVICE_SPAM_CONTACT_RE.search(combined_text))
        has_remediation_context = cls._contains_any_news_term(
            combined_text,
            cls._ADULT_SERVICE_REMEDIATION_TERMS,
        )
        if has_remediation_context and not has_contact_signal:
            return False

        if (
            "外围" in combined_text
            and cls._contains_any_news_term(
                combined_text,
                ("上门", "同城", "约炮", "援交", "包夜", "大保健", "推油", "小姐", "技师"),
            )
        ):
            return True

        context_hits = sum(
            1
            for term in cls._ADULT_SERVICE_SPAM_CONTEXT_TERMS
            if term.lower() in combined_text
        )
        has_service_anchor = cls._contains_any_news_term(
            combined_text,
            ("小姐", "按摩", "足浴", "桑拿", "会所", "技师"),
        )
        has_adult_specific_anchor = cls._contains_any_news_term(
            combined_text,
            (
                "小姐", "约炮", "援交", "楼凤", "外围", "包夜",
                "大保健", "莞式", "推油", "成人", "色情",
            ),
        )
        if has_contact_signal:
            return has_adult_specific_anchor and cls._contains_any_news_term(
                combined_text,
                cls._ADULT_SERVICE_SPAM_CONTACT_CONTEXT_TERMS,
            )
        has_solicitation_signal = cls._contains_any_news_term(
            combined_text,
            cls._ADULT_SERVICE_SOLICITATION_TERMS,
        )
        has_ambiguous_adult_phrase = cls._contains_any_news_term(
            combined_text,
            cls._ADULT_SERVICE_SPAM_AMBIGUOUS_TERMS,
        )
        if has_ambiguous_adult_phrase:
            return has_service_anchor and has_solicitation_signal

        return (
            has_adult_specific_anchor
            and has_service_anchor
            and has_solicitation_signal
            and context_hits >= 3
        )

    @classmethod
    def _score_news_relevance(
        cls,
        item: SearchResult,
        *,
        stock_code: str,
        stock_name: str,
    ) -> SearchResult:
        """Attach conservative, explainable relevance metadata to one news item."""
        title = item.title or ""
        snippet = item.snippet or ""
        url = item.url or ""
        source = item.source or ""
        full_text = " ".join([title, snippet, url, source])

        score = 0
        direct_signal = 0
        reasons: List[str] = []
        has_stock_code_signal = False
        has_unambiguous_company_signal = False
        has_ambiguous_company_signal = False

        def add_reason(reason: str) -> None:
            if reason not in reasons and len(reasons) < 5:
                reasons.append(reason)

        for term in cls._stock_code_identity_terms(stock_code):
            if cls._contains_stock_code_identity_term(title, term):
                score += 55
                direct_signal += 55
                has_stock_code_signal = True
                add_reason(f"标题命中股票代码 {term}")
                break
        else:
            for term in cls._stock_code_identity_terms(stock_code):
                if cls._contains_stock_code_identity_term(snippet, term):
                    score += 34
                    direct_signal += 34
                    has_stock_code_signal = True
                    add_reason(f"摘要命中股票代码 {term}")
                    break
            else:
                for term in cls._stock_code_identity_terms(stock_code):
                    if cls._contains_stock_code_identity_term(url, term):
                        score += 18
                        direct_signal += 18
                        has_stock_code_signal = True
                        add_reason(f"链接命中股票代码 {term}")
                        break

        for term in cls._company_identity_terms(stock_name):
            ambiguous_en = (
                not cls._contains_chinese_text(term)
                and term.lower() in cls._AMBIGUOUS_EN_COMPANY_NAMES
            )
            title_score = 26 if ambiguous_en else 45
            snippet_score = 16 if ambiguous_en else 28
            if cls._contains_identity_term(title, term):
                score += title_score
                direct_signal += title_score
                if ambiguous_en:
                    has_ambiguous_company_signal = True
                else:
                    has_unambiguous_company_signal = True
                add_reason(f"标题命中公司名 {term}")
                break
            if cls._contains_identity_term(snippet, term):
                score += snippet_score
                direct_signal += snippet_score
                if ambiguous_en:
                    has_ambiguous_company_signal = True
                else:
                    has_unambiguous_company_signal = True
                add_reason(f"摘要命中公司名 {term}")
                break

        has_company_event = cls._contains_any_news_term(full_text, cls._COMPANY_EVENT_TERMS)
        if has_company_event and direct_signal > 0:
            score += 12
            ambiguous_name_only = (
                has_ambiguous_company_signal
                and not has_stock_code_signal
                and not has_unambiguous_company_signal
            )
            has_confirming_event = cls._contains_any_news_term(
                full_text,
                cls._AMBIGUOUS_EN_CONFIRMING_EVENT_TERMS,
            )
            if not ambiguous_name_only or has_confirming_event:
                direct_signal += 12
            add_reason("命中公告/财报/交易等公司事件词")

        if cls._is_trusted_official_news_source(item):
            score += 8
            add_reason("来源接近公告或交易所渠道")

        has_sector_signal = cls._contains_any_news_term(full_text, cls._SECTOR_NEWS_TERMS)
        has_macro_signal = cls._contains_any_news_term(full_text, cls._MACRO_NEWS_TERMS)

        if direct_signal >= 38:
            category = cls._DIRECT_NEWS_CATEGORY
        elif has_macro_signal and not direct_signal:
            category = cls._MACRO_NEWS_CATEGORY
            score = max(0, score - 12)
            add_reason("未命中目标公司身份，归为宏观/市场新闻")
        else:
            category = cls._SECTOR_NEWS_CATEGORY
            if has_sector_signal:
                score += 6
                add_reason("仅命中行业或板块背景")
            else:
                add_reason("未命中股票代码或公司全称，降级为背景新闻")

        score = max(0, min(100, score))
        return SearchResult(
            title=item.title,
            snippet=item.snippet,
            url=item.url,
            source=item.source,
            published_date=item.published_date,
            relevance_score=score,
            relevance_category=category,
            relevance_reasons=reasons,
        )

    @classmethod
    def _rank_news_response(
        cls,
        response: SearchResponse,
        *,
        stock_code: str,
        stock_name: str,
        prefer_chinese: bool,
        max_results: int,
        log_scope: str,
    ) -> SearchResponse:
        """Score and sort news so direct company items are not crowded out."""
        if not response.success or not response.results:
            return response

        scored_results = [
            cls._score_news_relevance(item, stock_code=stock_code, stock_name=stock_name)
            for item in response.results
        ]

        indexed_results = list(enumerate(scored_results))

        def sort_key(entry: Tuple[int, SearchResult]) -> Tuple[int, int, int, int]:
            index, result = entry
            category = result.relevance_category or cls._SECTOR_NEWS_CATEGORY
            category_rank = cls._NEWS_CATEGORY_PRIORITY.get(category, 9)
            language_rank = 0 if prefer_chinese and cls._is_chinese_news_result(result) else 1
            if not prefer_chinese:
                language_rank = 0
            score = result.relevance_score or 0
            return (category_rank, language_rank, -score, index)

        ranked_results = [result for _, result in sorted(indexed_results, key=sort_key)]
        limited_results = ranked_results[:max_results]
        category_counts = {
            cls._DIRECT_NEWS_CATEGORY: 0,
            cls._SECTOR_NEWS_CATEGORY: 0,
            cls._MACRO_NEWS_CATEGORY: 0,
        }
        for result in limited_results:
            if result.relevance_category in category_counts:
                category_counts[result.relevance_category] += 1
        if limited_results:
            top = limited_results[0]
            logger.info(
                "[新闻相关度] %s: direct=%s, sector=%s, macro=%s, top_score=%s, top_category=%s, reasons=%s",
                log_scope,
                category_counts[cls._DIRECT_NEWS_CATEGORY],
                category_counts[cls._SECTOR_NEWS_CATEGORY],
                category_counts[cls._MACRO_NEWS_CATEGORY],
                top.relevance_score,
                top.relevance_category,
                "；".join(top.relevance_reasons or []),
            )

        return SearchResponse(
            query=response.query,
            results=limited_results,
            provider=response.provider,
            success=response.success,
            error_message=response.error_message,
            search_time=response.search_time,
        )

    @classmethod
    def _filter_ranked_news_for_context(
        cls,
        response: SearchResponse,
        *,
        log_scope: str,
    ) -> SearchResponse:
        """Drop obvious non-news pages and zero-relevance fillers from ranked results."""
        if not response.success or not response.results:
            return response

        candidates: List[SearchResult] = []
        dropped_low_quality = 0
        dropped_adult_spam = 0
        dropped_zero_relevance = 0

        for item in response.results:
            is_official_source = cls._is_trusted_official_news_source(item)
            if (
                not is_official_source
                and cls._has_low_quality_news_page_signal(item)
            ):
                dropped_low_quality += 1
                continue
            if (
                not is_official_source
                and cls._has_adult_service_spam_news_page_signal(item)
            ):
                dropped_adult_spam += 1
                continue
            candidates.append(item)

        meaningful_candidates = [
            item
            for item in candidates
            if item.relevance_category == cls._DIRECT_NEWS_CATEGORY
            or (item.relevance_score or 0) > 0
        ]
        if meaningful_candidates:
            dropped_zero_relevance = len(candidates) - len(meaningful_candidates)
            filtered_results = meaningful_candidates
        else:
            filtered_results = candidates

        if dropped_low_quality or dropped_adult_spam or dropped_zero_relevance:
            logger.info(
                "[新闻准入] %s: provider=%s, total=%s, kept=%s, "
                "drop_low_quality=%s, drop_adult_spam=%s, drop_zero_relevance=%s",
                log_scope,
                response.provider,
                len(response.results),
                len(filtered_results),
                dropped_low_quality,
                dropped_adult_spam,
                dropped_zero_relevance,
            )

        return SearchResponse(
            query=response.query,
            results=filtered_results,
            provider=response.provider,
            success=response.success,
            error_message=response.error_message,
            search_time=response.search_time,
        )

    @classmethod
    def _news_relevance_stats(
        cls,
        response: SearchResponse,
        *,
        prefer_chinese: bool,
    ) -> Dict[str, int]:
        results = response.results if response and response.results else []
        return {
            "direct_count": sum(
                1 for item in results if item.relevance_category == cls._DIRECT_NEWS_CATEGORY
            ),
            "preferred_direct_count": sum(
                1
                for item in results
                if (
                    prefer_chinese
                    and item.relevance_category == cls._DIRECT_NEWS_CATEGORY
                    and cls._is_chinese_news_result(item)
                )
            ),
            "preferred_count": sum(
                1 for item in results if prefer_chinese and cls._is_chinese_news_result(item)
            ),
            "max_score": max((item.relevance_score or 0 for item in results), default=0),
            "result_count": len(results),
        }

    @classmethod
    def _is_better_ranked_news_response(
        cls,
        candidate: SearchResponse,
        *,
        candidate_stats: Dict[str, int],
        best_response: Optional[SearchResponse],
        best_stats: Optional[Dict[str, int]],
        prefer_chinese: bool,
    ) -> bool:
        if best_response is None or best_stats is None:
            return True
        if candidate_stats["direct_count"] != best_stats["direct_count"]:
            return candidate_stats["direct_count"] > best_stats["direct_count"]
        if (
            prefer_chinese
            and candidate_stats["preferred_direct_count"] != best_stats["preferred_direct_count"]
        ):
            return candidate_stats["preferred_direct_count"] > best_stats["preferred_direct_count"]
        if prefer_chinese and candidate_stats["preferred_count"] != best_stats["preferred_count"]:
            return candidate_stats["preferred_count"] > best_stats["preferred_count"]
        if candidate_stats["max_score"] != best_stats["max_score"]:
            return candidate_stats["max_score"] > best_stats["max_score"]
        return candidate_stats["result_count"] > best_stats["result_count"]

    @staticmethod
    def _parse_relative_news_date(text: str, now: datetime) -> Optional[date]:
        """Parse common Chinese/English relative-time strings."""
        raw = (text or "").strip()
        if not raw:
            return None

        lower = raw.lower()
        if raw in {"今天", "今日", "刚刚"} or lower in {"today", "just now", "now"}:
            return now.date()
        if raw == "昨天" or lower == "yesterday":
            return (now - timedelta(days=1)).date()
        if raw == "前天":
            return (now - timedelta(days=2)).date()

        zh = re.match(r"^\s*(\d+)\s*(分钟|小时|天|周|个月|月|年)\s*前\s*$", raw)
        if zh:
            amount = int(zh.group(1))
            unit = zh.group(2)
            if unit == "分钟":
                return (now - timedelta(minutes=amount)).date()
            if unit == "小时":
                return (now - timedelta(hours=amount)).date()
            if unit == "天":
                return (now - timedelta(days=amount)).date()
            if unit == "周":
                return (now - timedelta(weeks=amount)).date()
            if unit in {"个月", "月"}:
                return (now - timedelta(days=amount * 30)).date()
            if unit == "年":
                return (now - timedelta(days=amount * 365)).date()

        en = re.match(
            r"^\s*(\d+)\s*(minute|minutes|min|mins|hour|hours|day|days|week|weeks|month|months|year|years)\s*ago\s*$",
            lower,
        )
        if en:
            amount = int(en.group(1))
            unit = en.group(2)
            if unit in {"minute", "minutes", "min", "mins"}:
                return (now - timedelta(minutes=amount)).date()
            if unit in {"hour", "hours"}:
                return (now - timedelta(hours=amount)).date()
            if unit in {"day", "days"}:
                return (now - timedelta(days=amount)).date()
            if unit in {"week", "weeks"}:
                return (now - timedelta(weeks=amount)).date()
            if unit in {"month", "months"}:
                return (now - timedelta(days=amount * 30)).date()
            if unit in {"year", "years"}:
                return (now - timedelta(days=amount * 365)).date()

        return None

    @classmethod
    def _normalize_news_publish_date(cls, value: Any) -> Optional[date]:
        """Normalize provider date value into a date object."""
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is not None:
                local_tz = datetime.now().astimezone().tzinfo or timezone.utc
                return value.astimezone(local_tz).date()
            return value.date()
        if isinstance(value, date):
            return value

        text = str(value).strip()
        if not text:
            return None
        now = datetime.now()
        local_tz = now.astimezone().tzinfo or timezone.utc

        relative_date = cls._parse_relative_news_date(text, now)
        if relative_date:
            return relative_date

        # Unix timestamp fallback
        if text.isdigit() and len(text) in (10, 13):
            try:
                ts = int(text[:10]) if len(text) == 13 else int(text)
                # Provider timestamps are typically UTC epoch seconds.
                # Normalize to local date to keep window checks aligned with local "today".
                return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(local_tz).date()
            except (OSError, OverflowError, ValueError):
                pass

        iso_candidate = text.replace("Z", "+00:00")
        try:
            parsed_iso = datetime.fromisoformat(iso_candidate)
            if parsed_iso.tzinfo is not None:
                return parsed_iso.astimezone(local_tz).date()
            return parsed_iso.date()
        except ValueError:
            pass

        normalized = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", text, flags=re.IGNORECASE)

        try:
            parsed_rfc = parsedate_to_datetime(normalized)
            if parsed_rfc:
                if parsed_rfc.tzinfo is not None:
                    return parsed_rfc.astimezone(local_tz).date()
                return parsed_rfc.date()
        except (TypeError, ValueError):
            pass

        zh_match = re.search(r"(\d{4})\s*[年/\-.]\s*(\d{1,2})\s*[月/\-.]\s*(\d{1,2})\s*日?", text)
        if zh_match:
            try:
                return date(int(zh_match.group(1)), int(zh_match.group(2)), int(zh_match.group(3)))
            except ValueError:
                pass

        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d %H:%M",
            "%Y/%m/%d",
            "%Y.%m.%d %H:%M:%S",
            "%Y.%m.%d %H:%M",
            "%Y.%m.%d",
            "%Y%m%d",
            "%b %d, %Y",
            "%B %d, %Y",
            "%d %b %Y",
            "%d %B %Y",
            "%a, %d %b %Y %H:%M:%S %z",
        ):
            try:
                parsed_dt = datetime.strptime(normalized, fmt)
                if parsed_dt.tzinfo is not None:
                    return parsed_dt.astimezone(local_tz).date()
                return parsed_dt.date()
            except ValueError:
                continue

        return None

    def _filter_news_response(
        self,
        response: SearchResponse,
        *,
        search_days: int,
        max_results: int,
        log_scope: str,
        keep_unknown: bool = False,
    ) -> SearchResponse:
        """Hard-filter results by published_date recency and normalize date strings."""
        if not response.success or not response.results:
            return response

        today = datetime.now().date()
        earliest = today - timedelta(days=max(0, int(search_days) - 1))
        latest = today + timedelta(days=self.FUTURE_TOLERANCE_DAYS)

        filtered: List[SearchResult] = []
        dropped_unknown = 0
        dropped_old = 0
        dropped_future = 0

        for item in response.results:
            published = self._normalize_news_publish_date(item.published_date)
            if published is None:
                if keep_unknown:
                    filtered.append(
                        SearchResult(
                            title=item.title,
                            snippet=item.snippet,
                            url=item.url,
                            source=item.source,
                            published_date=item.published_date,
                            relevance_score=item.relevance_score,
                            relevance_category=item.relevance_category,
                            relevance_reasons=item.relevance_reasons,
                        )
                    )
                    if len(filtered) >= max_results:
                        break
                    continue
                dropped_unknown += 1
                continue
            if published < earliest:
                dropped_old += 1
                continue
            if published > latest:
                dropped_future += 1
                continue

            filtered.append(
                SearchResult(
                    title=item.title,
                    snippet=item.snippet,
                    url=item.url,
                    source=item.source,
                    published_date=published.isoformat(),
                    relevance_score=item.relevance_score,
                    relevance_category=item.relevance_category,
                    relevance_reasons=item.relevance_reasons,
                )
            )
            if len(filtered) >= max_results:
                break

        if dropped_unknown or dropped_old or dropped_future:
            logger.info(
                "[新闻过滤] %s: provider=%s, total=%s, kept=%s, drop_unknown=%s, drop_old=%s, drop_future=%s, window=[%s,%s]",
                log_scope,
                response.provider,
                len(response.results),
                len(filtered),
                dropped_unknown,
                dropped_old,
                dropped_future,
                earliest.isoformat(),
                latest.isoformat(),
            )

        return SearchResponse(
            query=response.query,
            results=filtered,
            provider=response.provider,
            success=response.success,
            error_message=response.error_message,
            search_time=response.search_time,
        )

    def _normalize_and_limit_response(
        self,
        response: SearchResponse,
        *,
        max_results: int,
    ) -> SearchResponse:
        """Normalize parseable dates without enforcing freshness filtering."""
        if not response.success or not response.results:
            return response

        normalized_results: List[SearchResult] = []
        for item in response.results[:max_results]:
            normalized_date = self._normalize_news_publish_date(item.published_date)
            normalized_results.append(
                SearchResult(
                    title=item.title,
                    snippet=item.snippet,
                    url=item.url,
                    source=item.source,
                    published_date=(
                        normalized_date.isoformat() if normalized_date is not None else item.published_date
                    ),
                    relevance_score=item.relevance_score,
                    relevance_category=item.relevance_category,
                    relevance_reasons=item.relevance_reasons,
                )
            )

        return SearchResponse(
            query=response.query,
            results=normalized_results,
            provider=response.provider,
            success=response.success,
            error_message=response.error_message,
            search_time=response.search_time,
        )

    @staticmethod
    def _limit_search_response(
        response: SearchResponse,
        *,
        max_results: int,
    ) -> SearchResponse:
        """Trim response results without changing the rest of the metadata."""
        if not response.success or not response.results:
            return response

        limited_results = response.results[:max_results]
        if len(limited_results) == len(response.results):
            return response

        return SearchResponse(
            query=response.query,
            results=limited_results,
            provider=response.provider,
            success=response.success,
            error_message=response.error_message,
            search_time=response.search_time,
        )

    @staticmethod
    def _elapsed_ms(started_at: float) -> int:
        return max(0, int((time.monotonic() - started_at) * 1000))

    @staticmethod
    def _record_news_search_run(
        *,
        provider: str,
        operation: str,
        success: bool,
        latency_ms: Optional[int] = None,
        record_count: Optional[int] = None,
        cache_hit: Optional[bool] = None,
        error_type: Optional[str] = None,
        error_message: Optional[Any] = None,
    ) -> None:
        record_provider_run(
            data_type="news_search",
            provider=provider,
            operation=operation,
            success=success,
            latency_ms=latency_ms,
            error_type=error_type,
            error_message=error_message,
            cache_hit=cache_hit,
            record_count=record_count,
        )

    def search_stock_news(
        self,
        stock_code: str,
        stock_name: str,
        max_results: int = 5,
        focus_keywords: Optional[List[str]] = None
    ) -> SearchResponse:
        """
        搜索股票相关新闻
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            max_results: 最大返回结果数
            focus_keywords: 重点关注的关键词列表
            
        Returns:
            SearchResponse 对象
        """
        # Strategy window priority: ultra_short/short/medium/long = 1/3/7/30 Day,
        # Will unify the constraint imposed by NEWS_MAX_AGE_DAYS.
        search_days = self._effective_news_window_days()
        provider_max_results = self._provider_request_size(max_results)
        prefer_chinese = self._should_prefer_chinese_news(
            stock_code,
            stock_name,
            focus_keywords=focus_keywords,
        )

        # Build search query (optimize search effect)
        is_foreign = self._is_foreign_stock(stock_code)
        if focus_keywords:
            # If keywords are provided, use them directly as queries.
            query = " ".join(focus_keywords)
        elif prefer_chinese:
            query = f"{stock_name} {stock_code} 股票 最新消息"
        elif is_foreign:
            # Use English search keywords for Hong Kong/U.S. stocks
            query = f"{stock_name} {stock_code} stock latest news"
        else:
            # Default main query: Stock Name + Core Keywords
            query = f"{stock_name} {stock_code} 股票 最新消息"

        logger.info(
            (
                "搜索股票新闻: %s(%s), query='%s', 时间范围: 近%s天 "
                "(profile=%s, NEWS_MAX_AGE_DAYS=%s, prefer_chinese=%s), 目标条数=%s, provider请求条数=%s"
            ),
            stock_name,
            stock_code,
            query,
            search_days,
            self.news_strategy_profile,
            self.news_max_age_days,
            prefer_chinese,
            max_results,
            provider_max_results,
        )

        cache_key = self._cache_key(
            (
                f"{query}|target={stock_code}:{stock_name}|"
                f"news_pref={'zh' if prefer_chinese else 'default'}"
            ),
            max_results,
            search_days,
        )
        cached, cache_owner, cache_event = self._get_cached_or_reserve(cache_key)
        if cached is not None:
            cached = _stabilize_failed_search_response(cached)
            logger.info(f"使用缓存搜索结果: {stock_name}({stock_code})")
            self._record_news_search_run(
                provider=cached.provider or "SearchCache",
                operation="search_stock_news_cache",
                success=bool(cached.success),
                latency_ms=0,
                record_count=len(cached.results or []),
                cache_hit=True,
                error_message=cached.error_message,
            )
            return cached

        if not cache_owner and cache_event is not None:
            cached = self._wait_for_cached(cache_key, cache_event)
            if cached is not None:
                cached = _stabilize_failed_search_response(cached)
                logger.info(f"使用并发填充后的缓存搜索结果: {stock_name}({stock_code})")
                self._record_news_search_run(
                    provider=cached.provider or "SearchCache",
                    operation="search_stock_news_cache_wait",
                    success=bool(cached.success),
                    latency_ms=0,
                    record_count=len(cached.results or []),
                    cache_hit=True,
                    error_message=cached.error_message,
                )
                return cached
            cached, cache_owner, cache_event = self._get_cached_or_reserve(cache_key)
            if cached is not None:
                cached = _stabilize_failed_search_response(cached)
                logger.info(f"使用等待后命中的缓存搜索结果: {stock_name}({stock_code})")
                self._record_news_search_run(
                    provider=cached.provider or "SearchCache",
                    operation="search_stock_news_cache_retry",
                    success=bool(cached.success),
                    latency_ms=0,
                    record_count=len(cached.results or []),
                    cache_hit=True,
                    error_message=cached.error_message,
                )
                return cached

        try:
            # Try each search engine sequentially (if empty after filtering, try the next engine)
            had_provider_success = False
            best_ranked_response: Optional[SearchResponse] = None
            best_ranked_stats: Optional[Dict[str, int]] = None
            for provider in self._providers:
                if not provider.is_available:
                    continue

                search_kwargs: Dict[str, Any] = {}
                if isinstance(provider, TavilySearchProvider):
                    search_kwargs["topic"] = "news"
                elif isinstance(provider, BraveSearchProvider):
                    search_kwargs.update(
                        self._brave_search_locale(
                            stock_code,
                            prefer_chinese=prefer_chinese,
                        )
                    )

                started_at = time.monotonic()
                try:
                    record_provider_run_started(
                        data_type="news_search",
                        provider=provider.name,
                        operation="search_stock_news",
                    )
                    response = provider.search(query, provider_max_results, days=search_days, **search_kwargs)
                    response = _stabilize_failed_search_response(response)
                except Exception as exc:
                    self._record_news_search_run(
                        provider=provider.name,
                        operation="search_stock_news",
                        success=False,
                        latency_ms=self._elapsed_ms(started_at),
                        error_type=type(exc).__name__,
                        error_message=_SEARCH_REQUEST_FAILED,
                    )
                    raise
                filtered_response = self._filter_news_response(
                    response,
                    search_days=search_days,
                    max_results=provider_max_results,
                    log_scope=f"{stock_code}:{provider.name}:stock_news",
                )
                had_provider_success = had_provider_success or bool(response.success)

                if filtered_response.success and filtered_response.results:
                    language_response, _preferred_count = self._prioritize_news_language(
                        filtered_response,
                        prefer_chinese=prefer_chinese,
                    )
                    ranked_response = self._rank_news_response(
                        language_response,
                        stock_code=stock_code,
                        stock_name=stock_name,
                        prefer_chinese=prefer_chinese,
                        max_results=provider_max_results,
                        log_scope=f"{stock_code}:{provider.name}:stock_news",
                    )
                    admitted_response = self._filter_ranked_news_for_context(
                        ranked_response,
                        log_scope=f"{stock_code}:{provider.name}:stock_news",
                    )
                    limited_response = self._limit_search_response(
                        admitted_response,
                        max_results=max_results,
                    )
                    admitted_count = len(limited_response.results or [])
                    self._record_news_search_run(
                        provider=provider.name,
                        operation="search_stock_news",
                        success=bool(limited_response.success and limited_response.results),
                        latency_ms=self._elapsed_ms(started_at),
                        record_count=admitted_count,
                        error_type=None if admitted_count else "NoUsableNews",
                        error_message=None if admitted_count else (
                            response.error_message or "过滤后无有效新闻"
                        ),
                    )
                    if not admitted_count:
                        logger.info(
                            "%s 搜索成功但准入过滤后无有效新闻，继续尝试下一引擎",
                            provider.name,
                        )
                        continue

                    stats = self._news_relevance_stats(
                        limited_response,
                        prefer_chinese=prefer_chinese,
                    )
                    if self._is_better_ranked_news_response(
                        limited_response,
                        candidate_stats=stats,
                        best_response=best_ranked_response,
                        best_stats=best_ranked_stats,
                        prefer_chinese=prefer_chinese,
                    ):
                        best_ranked_response = limited_response
                        best_ranked_stats = stats

                    if stats["direct_count"] > 0 and (
                        not prefer_chinese or stats["preferred_direct_count"] > 0
                    ):
                        logger.info(
                            "%s 搜索成功，识别到 %s 条直接个股新闻，优先返回",
                            provider.name,
                            stats["direct_count"],
                        )
                        self._put_cache(cache_key, limited_response)
                        return limited_response

                    if prefer_chinese and stats["direct_count"] > 0:
                        logger.info(
                            "%s 搜索成功，识别到 %s 条直接个股新闻但缺少中文直接命中，继续尝试下一引擎",
                            provider.name,
                            stats["direct_count"],
                        )
                        continue

                    if prefer_chinese and stats["preferred_count"] >= max_results:
                        logger.info(
                            "%s 搜索成功，中文结果已满足目标条数但缺少直接个股命中，继续尝试下一引擎",
                            provider.name,
                        )
                        continue

                    if prefer_chinese and stats["preferred_count"] > 0:
                        logger.info(
                            "%s 搜索成功，识别到 %s/%s 条中文新闻但缺少直接个股命中，继续尝试下一引擎",
                            provider.name,
                            stats["preferred_count"],
                            len(limited_response.results),
                        )
                    else:
                        logger.info(
                            "%s 搜索成功但未识别直接个股新闻，继续尝试下一引擎",
                            provider.name,
                        )
                else:
                    filtered_count = len(filtered_response.results or []) if filtered_response.success else 0
                    self._record_news_search_run(
                        provider=provider.name,
                        operation="search_stock_news",
                        success=bool(filtered_response.success and filtered_response.results),
                        latency_ms=self._elapsed_ms(started_at),
                        record_count=filtered_count,
                        error_type=None if filtered_count else "NoUsableNews",
                        error_message=None if filtered_count else (
                            response.error_message or "过滤后无有效新闻"
                        ),
                    )
                    if response.success and not filtered_response.results:
                        logger.info(
                            "%s 搜索成功但过滤后无有效新闻，继续尝试下一引擎",
                            provider.name,
                        )
                    else:
                        _log_search_failure(
                            provider=provider.name,
                            error_code="stock_news_provider_failed",
                        )

            if best_ranked_response is not None:
                self._put_cache(cache_key, best_ranked_response)
                return best_ranked_response

            if had_provider_success:
                return SearchResponse(
                    query=query,
                    results=[],
                    provider="Filtered",
                    success=True,
                    error_message=None,
                )
            
            # All engines failed
            return SearchResponse(
                query=query,
                results=[],
                provider="None",
                success=False,
                error_message="所有搜索引擎都不可用或搜索失败"
            )
        finally:
            if cache_owner and cache_event is not None:
                self._release_cache_fill(cache_key, cache_event)
    
    def search_stock_events(
        self,
        stock_code: str,
        stock_name: str,
        event_types: Optional[List[str]] = None
    ) -> SearchResponse:
        """
        搜索股票特定事件（年报预告、减持等）
        
        专门针对交易决策相关的重要事件进行搜索
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            event_types: 事件类型列表
            
        Returns:
            SearchResponse 对象
        """
        if event_types is None:
            if self._is_foreign_stock(stock_code):
                event_types = ["earnings report", "insider selling", "quarterly results"]
            else:
                event_types = ["年报预告", "减持公告", "业绩快报"]
        
        # Build targeted query
        event_query = " OR ".join(event_types)
        query = f"{stock_name} ({event_query})"
        
        logger.info(f"搜索股票事件: {stock_name}({stock_code}) - {event_types}")
        
        # Try various search engines sequentially
        for provider in self._providers:
            if not provider.is_available:
                continue
            
            response = provider.search(query, max_results=5)
            
            if response.success:
                return response
        
        return SearchResponse(
            query=query,
            results=[],
            provider="None",
            success=False,
            error_message="事件搜索失败"
        )
    
    def search_comprehensive_intel(
        self,
        stock_code: str,
        stock_name: str,
        max_searches: int = 3
    ) -> Dict[str, SearchResponse]:
        """
        多维度情报搜索（同时使用多个引擎、多个维度）
        
        搜索维度：
        1. 最新消息 - 近期新闻动态
        2. 风险排查 - 减持、处罚、利空
        3. 业绩预期 - 年报预告、业绩快报
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            max_searches: 最大搜索次数
            
        Returns:
            {维度名称: SearchResponse} 字典
        """
        results = {}
        search_count = 0

        is_foreign = self._is_foreign_stock(stock_code)
        is_index_etf = self.is_index_or_etf(stock_code, stock_name)

        if is_foreign:
            search_dimensions = [
                {
                    'name': 'latest_news',
                    'query': f"{stock_name} {stock_code} latest news events",
                    'desc': '最新消息',
                    'tavily_topic': 'news',
                    'strict_freshness': True,
                },
                {
                    'name': 'market_analysis',
                    'query': f"{stock_name} analyst rating target price report",
                    'desc': '机构分析',
                    'tavily_topic': None,
                    'strict_freshness': False,
                },
                {
                    'name': 'risk_check',
                    'query': (
                        f"{stock_name} {stock_code} index performance outlook tracking error"
                        if is_index_etf else f"{stock_name} risk insider selling lawsuit litigation"
                    ),
                    'desc': '风险排查',
                    'tavily_topic': None if is_index_etf else 'news',
                    'strict_freshness': not is_index_etf,
                },
                {
                    'name': 'earnings',
                    'query': (
                        f"{stock_name} {stock_code} index performance composition outlook"
                        if is_index_etf else f"{stock_name} earnings revenue profit growth forecast"
                    ),
                    'desc': '业绩预期',
                    'tavily_topic': None,
                    'strict_freshness': False,
                },
                {
                    'name': 'industry',
                    'query': (
                        f"{stock_name} {stock_code} index sector allocation holdings"
                        if is_index_etf else f"{stock_name} industry competitors market share outlook"
                    ),
                    'desc': '行业分析',
                    'tavily_topic': None,
                    'strict_freshness': False,
                },
            ]
        else:
            search_dimensions = [
                {
                    'name': 'latest_news',
                    'query': f"{stock_name} {stock_code} 最新 新闻 重大 事件",
                    'desc': '最新消息',
                    'tavily_topic': 'news',
                    'strict_freshness': True,
                },
                {
                    'name': 'market_analysis',
                    'query': f"{stock_name} 研报 目标价 评级 深度分析",
                    'desc': '机构分析',
                    'tavily_topic': None,
                    'strict_freshness': False,
                },
                {
                    'name': 'risk_check',
                    'query': (
                        f"{stock_name} 指数走势 跟踪误差 净值 表现"
                        if is_index_etf else f"{stock_name} 减持 处罚 违规 诉讼 利空 风险"
                    ),
                    'desc': '风险排查',
                    'tavily_topic': None if is_index_etf else 'news',
                    'strict_freshness': not is_index_etf,
                },
                {
                    'name': 'announcements',
                    'query': (
                        f"{stock_name} {stock_code} 公告 指数调整 成分变化"
                        if is_index_etf else f"{stock_name} {stock_code} 公司公告 重要公告 上交所 深交所 cninfo"
                    ),
                    'desc': '公司公告',
                    'tavily_topic': 'news',
                    'strict_freshness': True,
                },
                {
                    'name': 'earnings',
                    'query': (
                        f"{stock_name} 指数成分 净值 跟踪表现"
                        if is_index_etf else f"{stock_name} 业绩预告 财报 营收 净利润 同比增长"
                    ),
                    'desc': '业绩预期',
                    'tavily_topic': None,
                    'strict_freshness': False,
                },
                {
                    'name': 'industry',
                    'query': (
                        f"{stock_name} 指数成分股 行业配置 权重"
                        if is_index_etf else f"{stock_name} 所在行业 竞争对手 市场份额 行业前景"
                    ),
                    'desc': '行业分析',
                    'tavily_topic': None,
                    'strict_freshness': False,
                },
            ]
        
        search_days = self._effective_news_window_days()
        target_per_dimension = 3
        provider_max_results = self._provider_request_size(target_per_dimension)

        logger.info(
            (
                "开始多维度情报搜索: %s(%s), 时间范围: 近%s天 "
                "(profile=%s, NEWS_MAX_AGE_DAYS=%s), 目标条数=%s, provider请求条数=%s"
            ),
            stock_name,
            stock_code,
            search_days,
            self.news_strategy_profile,
            self.news_max_age_days,
            target_per_dimension,
            provider_max_results,
        )
        
        # Rotate between different search engines
        provider_index = 0
        
        for dim in search_dimensions:
            if search_count >= max_searches:
                break
            
            # Select search engine (rotate usage).
            available_providers = [p for p in self._providers if p.is_available]
            if not available_providers:
                break
            
            provider = available_providers[provider_index % len(available_providers)]
            provider_index += 1
            
            request_days = (
                self.ANALYTICAL_INTEL_LOOKBACK_DAYS
                if dim['name'] in self.ANALYTICAL_INTEL_DIMENSIONS
                else search_days
            )

            logger.info(
                "[情报搜索] %s: 使用 %s，请求窗口: 近%s天",
                dim['desc'],
                provider.name,
                request_days,
            )

            if isinstance(provider, TavilySearchProvider) and dim.get('tavily_topic'):
                response = provider.search(
                    dim['query'],
                    max_results=provider_max_results,
                    days=request_days,
                    topic=dim['tavily_topic'],
                )
            else:
                response = provider.search(
                    dim['query'],
                    max_results=provider_max_results,
                    days=request_days,
                )
            response = _stabilize_failed_search_response(response)
            if dim['strict_freshness']:
                filtered_response = self._filter_news_response(
                    response,
                    search_days=search_days,
                    max_results=provider_max_results,
                    log_scope=f"{stock_code}:{provider.name}:{dim['name']}",
                )
            elif dim['name'] in self.ANALYTICAL_INTEL_DIMENSIONS:
                filtered_response = self._filter_news_response(
                    response,
                    search_days=self.ANALYTICAL_INTEL_LOOKBACK_DAYS,
                    max_results=provider_max_results,
                    keep_unknown=True,
                    log_scope=f"{stock_code}:{provider.name}:{dim['name']}",
                )
            else:
                filtered_response = self._normalize_and_limit_response(
                    response,
                    max_results=provider_max_results,
                )
            filtered_response = self._rank_news_response(
                filtered_response,
                stock_code=stock_code,
                stock_name=stock_name,
                prefer_chinese=self._should_prefer_chinese_news(stock_code, stock_name),
                max_results=provider_max_results,
                log_scope=f"{stock_code}:{provider.name}:{dim['name']}:rank",
            )
            filtered_response = self._filter_ranked_news_for_context(
                filtered_response,
                log_scope=f"{stock_code}:{provider.name}:{dim['name']}:admission",
            )
            filtered_response = self._limit_search_response(
                filtered_response,
                max_results=target_per_dimension,
            )
            results[dim['name']] = filtered_response
            search_count += 1
            
            if response.success:
                logger.info(
                    "[情报搜索] %s: 原始=%s条, 过滤后=%s条",
                    dim['desc'],
                    len(response.results),
                    len(filtered_response.results),
                )
            else:
                filtered_response.error_message = response.error_message
                _log_search_failure(
                    provider=provider.name,
                    error_code="search_dimension_failed",
                )
            
            # Avoid excessive requests due to short delays
            time.sleep(0.5)
        
        return results
    
    def format_intel_report(self, intel_results: Dict[str, SearchResponse], stock_name: str) -> str:
        """
        格式化情报搜索结果为报告
        
        Args:
            intel_results: 多维度搜索结果
            stock_name: 股票名称
            
        Returns:
            格式化的情报报告文本
        """
        lines = [f"【{stock_name} 情报搜索结果】"]
        
        # Dimension display order
        display_order = ['latest_news', 'announcements', 'market_analysis', 'risk_check', 'earnings', 'industry']

        dim_labels = {
            'latest_news': '📰 最新消息',
            'announcements': '📋 公司公告',
            'market_analysis': '📈 机构分析',
            'risk_check': '⚠️ 风险排查',
            'earnings': '📊 业绩预期',
            'industry': '🏭 行业分析',
        }

        for dim_name in display_order:
            if dim_name not in intel_results:
                continue
                
            resp = intel_results[dim_name]
            
            # Get dimension description
            dim_desc = dim_labels.get(dim_name, dim_name)
            
            lines.append(f"\n{dim_desc} (来源: {resp.provider}):")
            if resp.success and resp.results:
                # Increase display count
                for i, r in enumerate(resp.results[:4], 1):
                    date_str = f" [{r.published_date}]" if r.published_date else ""
                    lines.append(f"  {i}. {r.title}{date_str}")
                    # If the summary is too short, the information may be insufficient.
                    snippet = r.snippet[:150] if len(r.snippet) > 20 else r.snippet
                    lines.append(f"     {snippet}...")
                    if r.relevance_category or r.relevance_reasons:
                        relevance_parts = []
                        if r.relevance_category:
                            relevance_parts.append(r.relevance_category)
                        if r.relevance_score is not None:
                            relevance_parts.append(f"score={r.relevance_score}")
                        if r.relevance_reasons:
                            relevance_parts.append(f"依据: {'；'.join(r.relevance_reasons[:3])}")
                        lines.append(f"     关联度: {'; '.join(relevance_parts)}")
            else:
                lines.append("  未找到相关信息")
        
        return "\n".join(lines)
    
    def batch_search(
        self,
        stocks: List[Dict[str, str]],
        max_results_per_stock: int = 3,
        delay_between: float = 1.0
    ) -> Dict[str, SearchResponse]:
        """
        Batch search news for multiple stocks.
        
        Args:
            stocks: List of stocks
            max_results_per_stock: Max results per stock
            delay_between: Delay between searches (seconds)
            
        Returns:
            Dict of results
        """
        results = {}
        
        for i, stock in enumerate(stocks):
            if i > 0:
                time.sleep(delay_between)
            
            code = stock.get('code', '')
            name = stock.get('name', '')
            
            response = self.search_stock_news(code, name, max_results_per_stock)
            results[code] = response
        
        return results

    def search_stock_price_fallback(
        self,
        stock_code: str,
        stock_name: str,
        max_attempts: int = 3,
        max_results: int = 5
    ) -> SearchResponse:
        """
        Enhance search when data sources fail.
        
        When all data sources (efinance, akshare, tushare, baostock, etc.) fail to get
        stock data, use search engines to find stock trends and price info as supplemental data for AI analysis.
        
        Strategy:
        1. Search using multiple keyword templates
        2. Try all available search engines for each keyword
        3. Aggregate and deduplicate results
        
        Args:
            stock_code: Stock Code
            stock_name: Stock Name
            max_attempts: Max search attempts (using different keywords)
            max_results: Max results to return
            
        Returns:
            SearchResponse object with aggregated results
        """

        if not self.is_available:
            return SearchResponse(
                query=f"{stock_name} 股价走势",
                results=[],
                provider="None",
                success=False,
                error_message="未配置搜索能力"
            )
        
        logger.info(f"[增强搜索] 数据源失败，启动增强搜索: {stock_name}({stock_code})")
        
        all_results = []
        seen_urls = set()
        successful_providers = []
        
        # Use multiple keyword templates to search
        is_foreign = self._is_foreign_stock(stock_code)
        keywords = self.ENHANCED_SEARCH_KEYWORDS_EN if is_foreign else self.ENHANCED_SEARCH_KEYWORDS
        for i, keyword_template in enumerate(keywords[:max_attempts]):
            query = keyword_template.format(name=stock_name, code=stock_code)
            
            logger.info(f"[增强搜索] 第 {i+1}/{max_attempts} 次搜索: {query}")
            
            # Try various search engines sequentially
            for provider in self._providers:
                if not provider.is_available:
                    continue
                
                try:
                    response = provider.search(query, max_results=3)
                    
                    if response.success and response.results:
                        # Deduplicate and add results
                        for result in response.results:
                            if result.url not in seen_urls:
                                seen_urls.add(result.url)
                                all_results.append(result)
                                
                        if provider.name not in successful_providers:
                            successful_providers.append(provider.name)
                        
                        logger.info(f"[增强搜索] {provider.name} 返回 {len(response.results)} 条结果")
                        break  # Continue with the next keyword after a successful search
                    else:
                        logger.debug(f"[增强搜索] {provider.name} 无结果或失败")
                        
                except Exception as exc:
                    log_safe_exception(
                        logger,
                        "Enhanced search provider request failed",
                        exc,
                        error_code="enhanced_search_provider_request_failed",
                        level=logging.WARNING,
                        context={"provider": provider.name},
                        exception_redaction_values=exception_chain_redaction_values(exc),
                    )
                    continue
            
            # Avoid excessive requests due to short delays
            if i < max_attempts - 1:
                time.sleep(0.5)
        
        # Summary results
        if all_results:
            # Truncate top max_results items
            final_results = all_results[:max_results]
            provider_str = ", ".join(successful_providers) if successful_providers else "None"
            
            logger.info(f"[增强搜索] 完成，共获取 {len(final_results)} 条结果（来源: {provider_str}）")
            
            return SearchResponse(
                query=f"{stock_name}({stock_code}) 股价走势",
                results=final_results,
                provider=provider_str,
                success=True,
            )
        else:
            logger.warning(f"[增强搜索] 所有搜索均未返回结果")
            return SearchResponse(
                query=f"{stock_name}({stock_code}) 股价走势",
                results=[],
                provider="None",
                success=False,
                error_message="增强搜索未找到相关信息"
            )

    def search_stock_with_enhanced_fallback(
        self,
        stock_code: str,
        stock_name: str,
        include_news: bool = True,
        include_price: bool = False,
        max_results: int = 5
    ) -> Dict[str, SearchResponse]:
        """
        综合搜索接口（支持新闻和股价信息）
        
        当 include_price=True 时，会同时搜索新闻和股价信息。
        主要用于数据源完全失败时的兜底方案。
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            include_news: 是否搜索新闻
            include_price: 是否搜索股价/走势信息
            max_results: 每类搜索的最大结果数
            
        Returns:
            {'news': SearchResponse, 'price': SearchResponse} 字典
        """
        results = {}
        
        if include_news:
            results['news'] = self.search_stock_news(
                stock_code, 
                stock_name, 
                max_results=max_results
            )
        
        if include_price:
            results['price'] = self.search_stock_price_fallback(
                stock_code,
                stock_name,
                max_attempts=3,
                max_results=max_results
            )
        
        return results

    def format_price_search_context(self, response: SearchResponse) -> str:
        """
        将股价搜索结果格式化为 AI 分析上下文
        
        Args:
            response: 搜索响应对象
            
        Returns:
            格式化的文本，可直接用于 AI 分析
        """
        if not response.success or not response.results:
            return "【股价走势搜索】未找到相关信息，请以其他渠道数据为准。"
        
        lines = [
            f"【股价走势搜索结果】（来源: {response.provider}）",
            "⚠️ 注意：以下信息来自网络搜索，仅供参考，可能存在延迟或不准确。",
            ""
        ]
        
        for i, result in enumerate(response.results, 1):
            date_str = f" [{result.published_date}]" if result.published_date else ""
            lines.append(f"{i}. 【{result.source}】{result.title}{date_str}")
            lines.append(f"   {result.snippet[:200]}...")
            lines.append("")
        
        return "\n".join(lines)


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
