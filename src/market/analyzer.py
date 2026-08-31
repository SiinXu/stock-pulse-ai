# -*- coding: utf-8 -*-
"""
===================================
大盘复盘分析模块
===================================

职责：
1. 获取大盘指数数据（上证、深证、创业板）
2. 搜索市场新闻形成复盘情报
3. 使用大模型生成每日大盘复盘报告
"""

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from inspect import getattr_static
from typing import Optional, Dict, Any, List

import pandas as pd

from src.config import get_config
from src.report_language import normalize_report_language
from src.market_sector_analysis import (
    build_sector_analysis_payload,
    render_sector_analysis_markdown,
    render_sector_analysis_prompt_context,
)
from src.search_service import SearchService
from src.llm.backend_registry import (
    resolve_generation_backend_id,
    resolve_generation_fallback_backend_id,
)
from src.llm.generation_backend import GenerationError, GenerationErrorCode
from src.schemas.market_light import MARKET_LIGHT_REGIONS, MarketLightSnapshot
from src.services.run_diagnostics import record_llm_run, record_llm_run_started
from src.services.intelligence_service import IntelligenceService
from src.utils.sanitize import (
    exception_chain_redaction_values,
    has_matching_exception_snapshot,
    log_safe_exception,
    sanitize_diagnostic_text,
)
from src.data_provider.base import DataFetcherManager
from src.market import metrics as _market_metrics
from src.market import prompts as _market_prompts
from src.market import degradation as _market_degradation
from src.market import formatters as _market_formatters
from src.market import blocks as _market_blocks
from src.market import market_data as _market_data
from src.market import report_sections as _market_report_sections

build_market_light_scores = _market_metrics.build_market_light_scores
build_market_temperature = _market_metrics.build_market_temperature
market_light_status_from_score = _market_metrics.market_light_status_from_score
get_strategy_prompt_block = _market_prompts.get_strategy_prompt_block
build_output_template_sections = _market_prompts.build_output_template_sections
build_review_prompt = _market_prompts.build_review_prompt
generate_template_review = _market_degradation.generate_template_review
get_news_field = _market_formatters.get_news_field
format_news_catalyst_line = _market_formatters.format_news_catalyst_line
compact_news_text = _market_formatters.compact_news_text
format_optional_number = _market_formatters.format_optional_number
format_optional_pct = _market_formatters.format_optional_pct
format_signed_pct = _market_formatters.format_signed_pct
format_ranking_summary = _market_formatters.format_ranking_summary
escape_markdown_link_label = _market_formatters.escape_markdown_link_label
describe_turnover = _market_formatters.describe_turnover
build_stats_block = _market_blocks.build_stats_block
build_indices_block = _market_blocks.build_indices_block
build_sector_block = _market_blocks.build_sector_block
build_sector_analysis_block = _market_blocks.build_sector_analysis_block
build_news_block = _market_blocks.build_news_block
get_main_indices = _market_data.get_main_indices
get_market_statistics = _market_data.get_market_statistics
get_sector_rankings = _market_data.get_sector_rankings
get_concept_rankings = _market_data.get_concept_rankings
extract_report_title = _market_report_sections.extract_report_title
split_report_sections = _market_report_sections.split_report_sections
insert_after_section = _market_report_sections.insert_after_section

logger = logging.getLogger(__name__)


_ENGLISH_SECTION_PATTERNS = {
    "market_summary": r"###\s*(?:1\.\s*)?Market Summary",
    "index_commentary": r"###\s*(?:2\.\s*)?(?:Index Commentary|Major Indices)",
    "sector_highlights": r"###\s*(?:4\.\s*)?(?:Sector Highlights|Sector/Theme Highlights)",
}

_CHINESE_SECTION_PATTERNS = {
    "market_summary": r"###\s*一、(?:盘面总览|市场总结)",
    "index_commentary": r"###\s*二、(?:指数结构|指数点评|主要指数)",
    "sector_highlights": r"###\s*三、(?:板块主线|热点解读|板块表现)",
    "funds_sentiment": r"###\s*四、(?:资金与情绪|资金动向)",
    "news_catalysts": r"###\s*五、(?:消息催化|后市展望)",
}


@dataclass
class MarketIndex:
    """大盘指数数据"""
    code: str                    # Index code
    name: str                    # Index name
    current: float = 0.0         # Current level
    change: float = 0.0          # Change in points
    change_pct: float = 0.0      # Percentage change
    open: float = 0.0            # Open price level
    high: float = 0.0            # Peak value
    low: float = 0.0             # Lowest point
    prev_close: float = 0.0      # Yesterday's closing value
    volume: float = 0.0          # Volume (lots)
    amount: float = 0.0          # trading value (yuan)
    amplitude: float = 0.0       # Amplitude (%)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'code': self.code,
            'name': self.name,
            'current': self.current,
            'change': self.change,
            'change_pct': self.change_pct,
            'open': self.open,
            'high': self.high,
            'low': self.low,
            'volume': self.volume,
            'amount': self.amount,
            'amplitude': self.amplitude,
        }


@dataclass
class MarketOverview:
    """市场概览数据"""
    date: str                           # Date
    indices: List[MarketIndex] = field(default_factory=list)  # Major Indices
    up_count: int = 0                   # Number of rising stocks
    down_count: int = 0                 # Number of falling stocks
    flat_count: int = 0                 # Number of unchanged stocks
    limit_up_count: int = 0             # Number of limit-up stocks
    limit_down_count: int = 0           # limit-down count
    total_amount: float = 0.0           # trading value in the two markets(CNY 100 million)
    # north_flow: float = 0.0           # Net inflow of northbound funds(CNY 100 million)- deprecated, API unavailable

    # Sector rise sector
    top_sectors: List[Dict] = field(default_factory=list)     # Top 5 rising sectors
    bottom_sectors: List[Dict] = field(default_factory=list)  # Top 5 declining sectors
    top_concepts: List[Dict] = field(default_factory=list)    # Top 5 trending concepts
    bottom_concepts: List[Dict] = field(default_factory=list) # Top 5 declining concepts

# ``market_data`` anchors ``MarketIndex`` to avoid a circular import; give it
# the real class now that the dataclass exists.
_market_data.MarketIndex = MarketIndex


@dataclass
class MarketLightReviewResult:
    """Internal market-review parts built from one overview fetch."""

    overview: MarketOverview
    report: str
    market_light_snapshot: Optional[Dict[str, Any]]
    structured_payload: Dict[str, Any] = field(default_factory=dict)


class MarketAnalyzer:
    """
    大盘复盘分析器
    
    功能：
    1. 获取大盘指数实时行情
    2. 获取市场涨跌统计
    3. 获取板块涨跌榜
    4. 搜索市场新闻
    5. 生成大盘复盘报告
    """

    def __init__(
        self,
        search_service: Optional[SearchService] = None,
        analyzer=None,
        region: str = "cn",
        config: Optional[Any] = None,
    ):
        """
        初始化大盘分析器

        Args:
            search_service: 搜索服务实例
            analyzer: AI分析器实例（用于调用LLM）
            region: 市场区域 cn=A股 hk=港股 us=美股 jp=日本 kr=韩国
            config: 本次复盘使用的配置；未传时读取全局配置
        """
        self.config = config or get_config()
        self.search_service = search_service
        self.analyzer = analyzer
        self.data_manager = DataFetcherManager()
        self.region = region if region in ("cn", "us", "hk", "jp", "kr") else "cn"
        from src.core.market_profile import get_profile
        from src.core.market_strategy import get_market_strategy_blueprint
        self.profile = get_profile(self.region)
        self.strategy = get_market_strategy_blueprint(self.region)

    def _log_context(self) -> str:
        return f"component=market_review region={self.region}"

    def _generation_log_redaction_values(self, error: Any = None) -> set[str]:
        """Return exact generation secrets without depending on analyzer internals."""
        analyzer = getattr(self, "analyzer", None)
        if analyzer is None:
            return exception_chain_redaction_values(error)
        static_method = getattr_static(
            analyzer,
            "get_generation_log_redaction_values",
            None,
        )
        if static_method is None:
            return exception_chain_redaction_values(error)
        method = getattr(analyzer, "get_generation_log_redaction_values", None)
        if not callable(method):
            return exception_chain_redaction_values(error)
        try:
            model = str(getattr(self.config, "litellm_model", "") or "")
            values = method(model, fallback_error=error)
            static_values = values if isinstance(values, set) else set(values or ())
        except Exception:  # broad-exception: optional_metadata - optional redaction lookup falls back safely
            return exception_chain_redaction_values(error)
        if has_matching_exception_snapshot(error, static_values):
            return static_values
        exception_values = exception_chain_redaction_values(error)
        exception_values.update(static_values)
        return exception_values

    def _sanitize_generation_diagnostic(
        self,
        error: Any,
        *,
        redaction_values: Optional[set[str]] = None,
    ) -> str:
        """Sanitize an analyzer failure before persistence or user diagnostics."""
        if redaction_values is None:
            redaction_values = self._generation_log_redaction_values(error)
        if isinstance(error, GenerationError):
            error_code = (
                error.error_code.value
                if isinstance(error.error_code, GenerationErrorCode)
                else GenerationErrorCode.UNKNOWN_BACKEND_ERROR.value
            )
            return f"GenerationError: {error_code}"
        if has_matching_exception_snapshot(error, redaction_values):
            return sanitize_diagnostic_text(
                error,
                max_length=500,
                redaction_values=redaction_values,
            )
        analyzer = getattr(self, "analyzer", None)
        static_method = (
            getattr_static(analyzer, "sanitize_generation_diagnostic", None)
            if analyzer is not None
            else None
        )
        method = (
            getattr(analyzer, "sanitize_generation_diagnostic", None)
            if static_method is not None
            else None
        )
        if callable(method):
            try:
                model = str(getattr(self.config, "litellm_model", "") or "")
                return sanitize_diagnostic_text(
                    method(error, model=model),
                    max_length=500,
                    redaction_values=redaction_values,
                )
            except Exception:  # broad-exception: optional_metadata - optional sanitizer falls back safely
                pass
        return sanitize_diagnostic_text(
            error,
            max_length=500,
            redaction_values=redaction_values,
        )

    def _get_output_language(self) -> str:
        """Return the truthful report language (zh/en/ko) for payload and directives."""
        return normalize_report_language(
            getattr(getattr(self, "config", None), "report_language", "zh")
        )

    def _get_review_language(self) -> str:
        # Structural/template language. Korean reuses the English scaffolding;
        # the Korean output directive is applied in the prompt builder.
        language = self._get_output_language()
        return "en" if language == "ko" else language

    def _get_template_review_language(self) -> str:
        return self._get_review_language()

    def _get_market_scope_name(self, review_language: str | None = None) -> str:
        review_language = review_language or self._get_review_language()
        if self.region == "us":
            return "US market" if review_language == "en" else "美股市场"
        if self.region == "hk":
            return "Hong Kong market" if review_language == "en" else "港股市场"
        if self.region == "jp":
            return "Japan market" if review_language == "en" else "日本市场"
        if self.region == "kr":
            return "Korea market" if review_language == "en" else "韩国市场"
        if review_language == "en":
            return "A-share market"
        return "A股市场"

    def _get_turnover_unit_label(self) -> str:
        """Return the turnover unit label for the current market/language."""
        if self.region == "us":
            return "USD bn" if self._get_review_language() == "en" else "十亿美元"
        if self.region == "hk":
            return "HKD bn" if self._get_review_language() == "en" else "十亿港元"
        if self.region == "jp":
            return "JPY bn" if self._get_review_language() == "en" else "十亿日元"
        if self.region == "kr":
            return "KRW bn" if self._get_review_language() == "en" else "十亿韩元"
        return "CNY 100m" if self._get_review_language() == "en" else "亿"

    def _format_turnover_value(self, amount_raw: float) -> str:
        """Format raw turnover according to market-specific units."""
        if amount_raw == 0.0:
            return "N/A"
        if self.region in ("us", "hk", "jp", "kr"):
            return f"{amount_raw / 1e9:.2f}"
        if amount_raw > 1e6:
            return f"{amount_raw / 1e8:.0f}"
        return f"{amount_raw:.0f}"

    def _get_index_change_arrow(self, change_pct: float) -> str:
        if change_pct == 0:
            return "⚪"
        color_scheme = getattr(getattr(self, "config", None), "market_review_color_scheme", "green_up")
        if color_scheme == "red_up":
            return "🔴" if change_pct > 0 else "🟢"
        return "🟢" if change_pct > 0 else "🔴"

    def _get_review_title(self, date: str) -> str:
        if self._get_review_language() == "en":
            market_names = {
                "us": "US Market Recap",
                "hk": "HK Market Recap",
                "jp": "Japan Market Recap",
                "kr": "Korea Market Recap",
            }
            market_name = market_names.get(self.region, "A-share Market Recap")
            return f"## {date} {market_name}"
        return f"## {date} 大盘复盘"

    def _get_index_hint(self) -> str:
        if self._get_review_language() == "en":
            if self.region == "us":
                return "Analyze the key moves in the S&P 500, Nasdaq, Dow, and other major indices."
            if self.region == "hk":
                return "Analyze the key moves in the HSI, Hang Seng Tech, HSCEI, and other major indices."
            if self.region == "jp":
                return "Analyze the key moves in the Nikkei 225, TOPIX, and other major Japanese indices."
            if self.region == "kr":
                return "Analyze the key moves in the KOSPI, KOSDAQ, and other major Korean indices."
            return "Analyze the price action in the SSE, SZSE, ChiNext, and other major indices."
        return self.profile.prompt_index_hint

    def _get_strategy_prompt_block(self) -> str:
        return get_strategy_prompt_block(
            self.region,
            self._get_review_language(),
            default_strategy_block=self.strategy.to_prompt_block(),
        )

    def _get_strategy_markdown_block(self, review_language: str | None = None) -> str:
        review_language = review_language or self._get_review_language()
        if self.region == "hk" and review_language == "en":
            return """### 6. Strategy Framework
- **Trend Regime**: Classify the market as momentum, range, or risk-off based on HSI/HSTECH/HSCEI alignment.
- **Capital Flows**: Track southbound flow direction and macro narrative for risk appetite signals.
- **Sector Themes**: Focus on tech/internet platform persistence and financials/property policy sensitivity.
"""
        if self.region == "jp" and review_language == "en":
            return """### 6. Strategy Framework
- **Trend Regime**: Classify Japan equities as advancing, range-bound, or defensive based on Nikkei 225/TOPIX alignment.
- **Macro & FX**: Track yen, rates, and global risk appetite for exporter and financial-sector implications.
- **Theme Signals**: Focus on semiconductor, automation, auto-chain, financial, and domestic-demand rotation.
"""
        if self.region == "kr" and review_language == "en":
            return """### 6. Strategy Framework
- **Trend Regime**: Classify Korea equities as advancing, range-bound, or defensive based on KOSPI/KOSDAQ alignment.
- **Technology Cycle**: Track semiconductor, AI hardware, and global technology read-through for market risk appetite.
- **Theme Signals**: Focus on battery, auto, internet-platform, and KOSDAQ growth-stock rotation.
"""
        if self.region == "us" and review_language == "zh":
            return """### 六、策略框架
- **趋势结构**：判断市场在进攻、震荡与防守中的状态是否一致。
- **资金与情绪**：结合波动率、宽度和主题轮动评估风险偏好。
- **主题主线**：识别可延续和可放大的行业主线与防守线索。
"""
        if not (self.region == "cn" and review_language == "en"):
            return self.strategy.to_markdown_block()
        return """### 6. Strategy Framework
- **Trend Structure**: Determine whether the market is in an uptrend, range, or defensive phase.
- **Liquidity & Sentiment**: Track breadth, turnover expansion, and whether leaders are diverging.
- **Leading Themes**: Focus on sectors with catalysts and sustained leadership while avoiding broadening weakness.
"""

    def _get_market_mood_text(self, mood_key: str, review_language: str | None = None) -> str:
        review_language = review_language or self._get_review_language()
        if review_language == "en":
            mapping = {
                "strong_up": "strong gains",
                "mild_up": "moderate gains",
                "mild_down": "mild losses",
                "strong_down": "clear weakness",
                "range": "range-bound trading",
            }
        else:
            mapping = {
                "strong_up": "强势上涨",
                "mild_up": "小幅上涨",
                "mild_down": "小幅下跌",
                "strong_down": "明显下跌",
                "range": "震荡整理",
            }
        return mapping[mood_key]

    def get_market_overview(self) -> MarketOverview:
        """
        获取市场概览数据
        
        Returns:
            MarketOverview: 市场概览数据对象
        """
        today = datetime.now().strftime('%Y-%m-%d')
        overview = MarketOverview(date=today)

        # 1. Get quote data for key indices (switch between regions: A-shares/U.S. stocks).
        overview.indices = self._get_main_indices()

        # 2. Get rise and fall statistics (A-shares have them, no equivalent data for U.S. stocks, etc.)
        if self.profile.has_market_stats:
            self._get_market_statistics(overview)

        # 3. Get sector rise-fall rankings (A-shares have, U.S. stocks currently unavailable)
        if self.profile.has_sector_rankings:
            self._get_sector_rankings(overview)
            self._get_concept_rankings(overview)

        # 4. Get Northbound Funds (optional)
        # self._get_north_flow(overview)

        return overview


    def _get_main_indices(self) -> List[MarketIndex]:
        return get_main_indices(self)

    def _get_market_statistics(self, overview: MarketOverview):
        return get_market_statistics(self, overview)

    def _get_sector_rankings(self, overview: MarketOverview):
        return get_sector_rankings(self, overview)

    def _get_concept_rankings(self, overview: MarketOverview):
        return get_concept_rankings(self, overview)

    # def _get_north_flow(self, overview: MarketOverview):
    #     """获取北向资金流入"""
    #     try:
    #         logger.info("[大盘] 获取北向资金...")
    #
    #         # Get Northbound Funds Data
    #         df = ak.stock_hsgt_north_net_flow_in_em(symbol="北上")
    #
    #         if df is not None and not df.empty:
    #             # Get latest data point
    #             latest = df.iloc[-1]
    #             if '当日净流入' in df.columns:
    #                 overview.north_flow = float(latest['当日净流入']) / 1e8  # Convert to CNY 100 million of yuan
    #             elif '净流入' in df.columns:
    #                 overview.north_flow = float(latest['净流入']) / 1e8
    #
    #             logger.info(f"[大盘] 北向资金净流入: {overview.north_flow:.2f}亿")
    #
    #     except Exception as e:
    #         logger.warning(f"[大盘] 获取北向资金失败: {e}")

    def search_market_news(self) -> List[Dict]:
        """
        搜索市场新闻
        
        Returns:
            新闻列表
        """
        if not self.search_service:
            logger.warning(
                "[大盘] %s action=search_market_news status=skipped reason=no_search_service",
                self._log_context(),
            )
            return []

        all_news = []

        # Use different news search terms based on region.
        search_queries = self.profile.news_queries
        review_language = self._get_review_language()
        market_names = {
            "cn": "大盘" if review_language == "zh" else "A-share market",
            "us": "美股市场" if review_language == "zh" else "US market",
            "hk": "港股市场" if review_language == "zh" else "HK market",
            "jp": "日本股市" if review_language == "zh" else "Japan stock market",
            "kr": "韩国股市" if review_language == "zh" else "Korea stock market",
        }

        try:
            logger.info("[大盘] %s action=search_market_news status=start", self._log_context())

            # Set search context name based on region to avoid interpreting US stock searches as A-shares context
            market_name = market_names.get(self.region, "大盘")
            for query in search_queries:
                response = self.search_service.search_stock_news(
                    stock_code="market",
                    stock_name=market_name,
                    max_results=3,
                    focus_keywords=query.split()
                )
                if response and response.results:
                    all_news.extend(response.results)
                    logger.info(
                        "[大盘] %s action=search_market_news status=query_success count=%d",
                        self._log_context(),
                        len(response.results),
                    )

            logger.info(
                "[大盘] %s action=search_market_news status=success count=%d",
                self._log_context(),
                len(all_news),
            )

        except Exception as e:  # broad-exception: fallback_recorded - news failure is logged before fallback
            log_safe_exception(
                logger,
                "Market review news search failed",
                e,
                error_code="market_review_news_search_failed",
                level=logging.ERROR,
                context={"region": self.region},
            )

        return all_news

    def generate_market_review(self, overview: MarketOverview, news: List) -> str:
        """
        使用大模型生成大盘复盘报告
        
        Args:
            overview: 市场概览数据
            news: 市场新闻列表 (SearchResult 对象列表)
            
        Returns:
            大盘复盘报告文本
        """
        backend_error = self._get_analyzer_generation_backend_config_error()
        if backend_error is not None:
            redaction_values = self._generation_log_redaction_values(backend_error)
            log_safe_exception(
                logger,
                "Market review generation backend unavailable",
                backend_error,
                error_code="market_review_generation_backend_unavailable",
                level=logging.ERROR,
                context={"region": self.region},
                redaction_values=redaction_values,
            )
            safe_backend_error = self._sanitize_generation_diagnostic(
                backend_error,
                redaction_values=redaction_values,
            )
            record_llm_run(
                success=False,
                provider="litellm",
                model=getattr(self.config, "litellm_model", None),
                call_type="market_review",
                error_type=type(backend_error).__name__,
                error_message=safe_backend_error,
            )
            raise backend_error

        if not self.analyzer or not self.analyzer.is_available():
            logger.warning(
                "[大盘] %s action=generate_review status=fallback_template reason=no_analyzer",
                self._log_context(),
            )
            return self._generate_template_review(overview, news)

        # Construct Prompt
        prompt = self._build_review_prompt(overview, news)

        logger.info("[大盘] %s action=generate_review status=start", self._log_context())
        # Use the public generate_text() entry point - never access private analyzer attributes.
        llm_started_at = time.perf_counter()
        try:
            record_llm_run_started(
                provider="litellm",
                model=getattr(self.config, "litellm_model", None),
                call_type="market_review",
            )
            review = self.analyzer.generate_text(prompt, max_tokens=8192, temperature=0.7)
        except Exception as exc:  # broad-exception: fallback_recorded - generation failure is recorded then raised
            safe_error = self._sanitize_generation_diagnostic(exc)
            record_llm_run(
                success=False,
                provider="litellm",
                model=getattr(self.config, "litellm_model", None),
                call_type="market_review",
                duration_ms=int((time.perf_counter() - llm_started_at) * 1000),
                error_type=type(exc).__name__,
                error_message=safe_error,
            )
            raise

        record_llm_run(
            success=bool(review),
            provider="litellm",
            model=getattr(self.config, "litellm_model", None),
            call_type="market_review",
            duration_ms=int((time.perf_counter() - llm_started_at) * 1000),
            error_type=None if review else "EmptyResponse",
            error_message=None if review else "empty market review response",
        )

        if review:
            logger.info(
                "[大盘] %s action=generate_review status=success length=%d",
                self._log_context(),
                len(review),
            )
            # Inject structured data tables into LLM prose sections
            return self._inject_data_into_review(review, overview, news)

        logger.warning(
            "[大盘] %s action=generate_review status=fallback_template reason=empty_llm_response",
            self._log_context(),
        )
        return self._generate_template_review(overview, news)

    def _get_analyzer_generation_backend_config_error(self) -> Optional[GenerationError]:
        """Return analyzer backend config errors without relying on dynamic mock attributes."""
        if self.analyzer is None:
            try:
                resolve_generation_backend_id(self.config)
                resolve_generation_fallback_backend_id(self.config)
            except GenerationError as exc:
                return exc
            return None
        missing = object()
        if getattr_static(self.analyzer, "get_generation_backend_config_error", missing) is missing:
            return None
        method = getattr(self.analyzer, "get_generation_backend_config_error", None)
        if not callable(method):
            return None
        error = method()
        return error if isinstance(error, GenerationError) else None

    def build_sector_analysis(self, overview: MarketOverview) -> Dict[str, Any]:
        """Build additive sector analysis from existing session ranking data."""
        return build_sector_analysis_payload(
            as_of=overview.date,
            indices=overview.indices,
            top_sectors=overview.top_sectors,
            bottom_sectors=overview.bottom_sectors,
            top_concepts=overview.top_concepts,
            bottom_concepts=overview.bottom_concepts,
            rankings_supported=bool(self.profile.has_sector_rankings),
        )

    def build_market_review_payload(
        self,
        overview: MarketOverview,
        news: List,
        report: str,
        market_light_snapshot: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Build the structured market-review contract consumed by API, Web, and notifications."""
        language = self._get_output_language()
        sections = self._split_report_sections(report)
        title = self._extract_report_title(report) or self._get_review_title(overview.date).lstrip("# ").strip()
        light = (
            market_light_snapshot or self.build_market_light_snapshot(overview)
            if self._supports_market_light()
            else None
        )
        breadth_dimensions = None
        if isinstance(light, dict):
            dimensions = light.get("dimensions")
            if isinstance(dimensions, dict):
                breadth_dimensions = dimensions.get("breadth")

        breadth_supported = bool(self.profile.has_market_stats)
        if breadth_supported and isinstance(breadth_dimensions, dict) and "available" in breadth_dimensions:
            breadth_supported = bool(breadth_dimensions.get("available"))

        has_breadth_data = False
        if breadth_supported:
            if isinstance(breadth_dimensions, dict) and "available" in breadth_dimensions:
                has_breadth_data = bool(breadth_dimensions.get("available"))
            else:
                breadth_available = overview.up_count + overview.down_count + overview.flat_count > 0
                limit_available = overview.limit_up_count + overview.limit_down_count > 0
                has_breadth_data = bool(breadth_available or limit_available)

        payload = {
            "version": 1,
            "kind": "market_review",
            "region": self.region,
            "language": language,
            "title": title,
            "generated_at": datetime.now().isoformat(),
            "date": overview.date,
            "market_scope": self._get_market_scope_name(language),
            "indices": [idx.to_dict() for idx in overview.indices],
            "sectors": {
                "top": list(overview.top_sectors or []),
                "bottom": list(overview.bottom_sectors or []),
            },
            "concepts": {
                "top": list(overview.top_concepts or []),
                "bottom": list(overview.bottom_concepts or []),
            },
            "sector_analysis": self.build_sector_analysis(overview),
            "news": [self._normalize_news_item(item) for item in (news or [])[:8]],
            "sections": sections,
            "markdown_report": report,
        }

        if light is not None:
            payload["market_light"] = light

        if has_breadth_data:
            payload["breadth"] = {
                "up_count": overview.up_count,
                "down_count": overview.down_count,
                "flat_count": overview.flat_count,
                "limit_up_count": overview.limit_up_count,
                "limit_down_count": overview.limit_down_count,
                "total_amount": overview.total_amount,
                "turnover_unit": self._get_turnover_unit_label(),
            }

        return payload

    def _supports_market_light(self) -> bool:
        return self.region in MARKET_LIGHT_REGIONS

    @staticmethod
    def _extract_report_title(report):
        return extract_report_title(report)

    @classmethod
    def _split_report_sections(cls, report):
        return split_report_sections(report)

    @classmethod
    def _normalize_news_item(cls, item: Any) -> Dict[str, str]:
        return {
            "title": cls._compact_news_text(cls._get_news_field(item, "title"), limit=120),
            "snippet": cls._compact_news_text(cls._get_news_field(item, "snippet"), limit=260),
            "source": cls._compact_news_text(cls._get_news_field(item, "source"), limit=80),
            "published_date": cls._compact_news_text(cls._get_news_field(item, "published_date"), limit=40),
            "url": cls._compact_news_text(cls._get_news_field(item, "url"), limit=240),
        }

    def _inject_data_into_review(
        self,
        review: str,
        overview: MarketOverview,
        news: Optional[List] = None,
    ) -> str:
        """Inject structured data tables into the corresponding LLM prose sections."""
        # Build data blocks
        stats_block = self._build_stats_block(overview)
        indices_block = self._build_indices_block(overview)
        sector_block = self._build_sector_block(overview)
        patterns = (
            _ENGLISH_SECTION_PATTERNS
            if self._get_review_language() == "en"
            else _CHINESE_SECTION_PATTERNS
        )

        if stats_block:
            review = self._insert_after_section(
                review,
                patterns["market_summary"],
                stats_block,
            )

        if indices_block:
            review = self._insert_after_section(
                review,
                patterns["index_commentary"],
                indices_block,
            )

        if sector_block:
            original_review = review
            review = self._insert_after_section(
                review,
                patterns["sector_highlights"],
                sector_block,
            )
            if review == original_review and sector_block not in review:
                fallback_heading = (
                    "### 4. Sector Highlights"
                    if self._get_review_language() == "en"
                    else "### 三、板块主线"
                )
                review = f"{review.rstrip()}\n\n{fallback_heading}\n{sector_block}\n"

        return review

    @staticmethod
    def _insert_after_section(text, heading_pattern, block):
        return insert_after_section(text, heading_pattern, block)

    def _build_stats_block(self, overview: MarketOverview) -> str:
        return build_stats_block(self, overview)

    def build_market_light_snapshot(self, overview: MarketOverview) -> Dict[str, Any]:
        """Build a deterministic market-light snapshot from structured breadth data."""
        scores = self._build_market_light_scores(overview)
        score = int(scores["score"])
        temperature_label = str(scores["temperature_label"])
        status = market_light_status_from_score(score)

        if self._get_review_language() == "en":
            label_map = {
                "green": "risk-on",
                "yellow": "balanced",
                "red": "risk-off",
            }
            guidance_map = {
                "green": "Risk appetite is acceptable; focus on leading themes and position discipline.",
                "yellow": "Signals are mixed; keep position sizing moderate and wait for confirmation.",
                "red": "Risk is elevated; prioritize drawdown control and avoid chasing weak rebounds.",
            }
            reasons = self._build_market_light_reasons_en(overview, score)
        else:
            label_map = {
                "green": "可进攻",
                "yellow": "需观察",
                "red": "偏防守",
            }
            guidance_map = {
                "green": "风险偏好尚可，关注主线延续与仓位纪律。",
                "yellow": "信号分化，控制仓位并等待量价确认。",
                "red": "风险偏高，优先控制回撤，避免追高弱反弹。",
            }
            reasons = self._build_market_light_reasons_zh(overview, score)

        snapshot = MarketLightSnapshot(
            region=self.region,
            trade_date=overview.date,
            status=status,
            label=label_map[status],
            score=score,
            temperature_label=temperature_label,
            reasons=reasons,
            guidance=guidance_map[status],
            dimensions=scores["dimensions"],
            data_quality=str(scores["data_quality"]),
        )
        return snapshot.model_dump()

    def _build_market_light_reasons_zh(self, overview: MarketOverview, score: int) -> List[str]:
        participation = overview.up_count + overview.down_count
        up_ratio = overview.up_count / participation if participation else None
        reasons: List[str] = []
        if up_ratio is not None:
            if up_ratio >= 0.6:
                reasons.append(f"上涨家数占比 {up_ratio:.0%}，赚钱效应扩散")
            elif up_ratio <= 0.4:
                reasons.append(f"上涨家数占比 {up_ratio:.0%}，亏钱效应较强")
            else:
                reasons.append(f"上涨家数占比 {up_ratio:.0%}，市场分化")
        index_changes = [idx.change_pct for idx in overview.indices if idx.change_pct is not None]
        if index_changes:
            avg_change = sum(index_changes) / len(index_changes)
            reasons.append(f"主要指数平均涨跌幅 {avg_change:+.2f}%")
        if overview.limit_up_count or overview.limit_down_count:
            reasons.append(f"涨跌停差 {overview.limit_up_count - overview.limit_down_count:+d}")
        if not reasons and overview.total_amount:
            reasons.append(f"成交额 {overview.total_amount:.0f} 亿，{self._describe_turnover(overview.total_amount)}")
        if not reasons:
            reasons.append("结构化涨跌数据有限，按可用行情综合判断")
        return reasons[:4]

    def _build_market_light_reasons_en(self, overview: MarketOverview, score: int) -> List[str]:
        participation = overview.up_count + overview.down_count
        up_ratio = overview.up_count / participation if participation else None
        reasons: List[str] = []
        if up_ratio is not None:
            if up_ratio >= 0.6:
                reasons.append(f"advancers ratio {up_ratio:.0%}, breadth is expanding")
            elif up_ratio <= 0.4:
                reasons.append(f"advancers ratio {up_ratio:.0%}, downside pressure dominates")
            else:
                reasons.append(f"advancers ratio {up_ratio:.0%}, breadth is mixed")
        index_changes = [idx.change_pct for idx in overview.indices if idx.change_pct is not None]
        if index_changes:
            avg_change = sum(index_changes) / len(index_changes)
            reasons.append(f"average major-index change {avg_change:+.2f}%")
        if overview.limit_up_count or overview.limit_down_count:
            reasons.append(f"limit-up/down spread {overview.limit_up_count - overview.limit_down_count:+d}")
        if not reasons and overview.total_amount:
            reasons.append(f"turnover {overview.total_amount:.0f} ({self._get_turnover_unit_label()})")
        if not reasons:
            reasons.append("limited structured breadth data; using available market inputs")
        return reasons[:4]

    def _build_indices_block(self, overview: MarketOverview) -> str:
        return build_indices_block(self, overview)

    def _build_sector_block(self, overview: MarketOverview) -> str:
        return build_sector_block(self, overview)

    def _build_sector_analysis_block(self, overview: MarketOverview) -> str:
        return build_sector_analysis_block(
            self, overview, renderer=render_sector_analysis_markdown
        )

    def _build_news_block(self, news: List) -> str:
        return build_news_block(self, news)

    @staticmethod
    def _get_news_field(item: Any, field: str) -> str:
        return get_news_field(item, field)

    @classmethod
    def _format_news_catalyst_line(cls, idx: int, item: Any, *, language: str = "zh") -> str:
        return format_news_catalyst_line(cls, idx, item, language=language)

    @staticmethod
    def _compact_news_text(value: str, *, limit: int) -> str:
        return compact_news_text(value, limit=limit)

    @staticmethod
    def _format_optional_number(value: float) -> str:
        return format_optional_number(value)

    @staticmethod
    def _format_optional_pct(value: float) -> str:
        return format_optional_pct(value)

    @staticmethod
    def _format_signed_pct(value: Any) -> str:
        return format_signed_pct(value)

    @classmethod
    def _format_ranking_summary(cls, rows: List[Dict], limit: int = 3) -> str:
        return format_ranking_summary(cls, rows, limit)

    @staticmethod
    def _escape_markdown_link_label(value: str) -> str:
        return escape_markdown_link_label(value)

    @staticmethod
    def _describe_turnover(total_amount: float) -> str:
        return describe_turnover(total_amount)

    def _build_market_light_scores(self, overview: MarketOverview) -> Dict[str, Any]:
        """Build the canonical Market Light scores used by reports and alerts."""
        return build_market_light_scores(
            overview,
            has_market_stats=self.profile.has_market_stats,
            review_language=self._get_review_language(),
        )

    def _build_market_temperature(self, overview: MarketOverview) -> tuple[int, str]:
        scores = self._build_market_light_scores(overview)
        score = int(scores["score"])
        label = str(scores["temperature_label"])
        return score, label

    def _build_output_template_sections(self, review_language: str) -> str:
        """Build LLM output sections according to market data capabilities."""
        return build_output_template_sections(
            review_language,
            has_market_stats=self.profile.has_market_stats,
            has_sector_rankings=self.profile.has_sector_rankings,
        )

    def _build_review_prompt(self, overview: MarketOverview, news: List) -> str:
        """构建复盘报告 Prompt"""
        review_language = self._get_review_language()

        indices_text = ""
        for idx in overview.indices:
            direction = "↑" if idx.change_pct > 0 else "↓" if idx.change_pct < 0 else "-"
            indices_text += f"- {idx.name}: {idx.current:.2f} ({direction}{abs(idx.change_pct):.2f}%)\n"

        news_text = ""
        for i, n in enumerate(news[:6], 1):
            title = self._compact_news_text(self._get_news_field(n, "title"), limit=90)
            snippet = self._compact_news_text(self._get_news_field(n, "snippet"), limit=220)
            source = self._compact_news_text(self._get_news_field(n, "source"), limit=60)
            published_date = self._compact_news_text(self._get_news_field(n, "published_date"), limit=30)
            url = self._compact_news_text(self._get_news_field(n, "url"), limit=180)
            meta_parts = [part for part in (source, published_date) if part]
            meta = f" ({' / '.join(meta_parts)})" if meta_parts else ""
            url_line = f"\n   URL: {url}" if url else ""
            news_text += f"{i}. {title}{meta}\n   {snippet or '-'}{url_line}\n"

        return build_review_prompt(
            review_language=review_language,
            output_language=self._get_output_language(),
            region=self.region,
            date=overview.date,
            has_market_stats=self.profile.has_market_stats,
            has_sector_rankings=self.profile.has_sector_rankings,
            indices_text=indices_text,
            news_text=news_text,
            top_sectors_text=self._format_ranking_summary(overview.top_sectors),
            bottom_sectors_text=self._format_ranking_summary(overview.bottom_sectors),
            top_concepts_text=self._format_ranking_summary(overview.top_concepts),
            bottom_concepts_text=self._format_ranking_summary(overview.bottom_concepts),
            sector_analysis_context=render_sector_analysis_prompt_context(
                self.build_sector_analysis(overview),
                language=review_language,
            ),
            turnover_unit_label=self._get_turnover_unit_label(),
            up_count=overview.up_count,
            down_count=overview.down_count,
            flat_count=overview.flat_count,
            limit_up_count=overview.limit_up_count,
            limit_down_count=overview.limit_down_count,
            total_amount=overview.total_amount,
            market_scope_name_en=self._get_market_scope_name("en"),
            market_scope_name_zh=self._get_market_scope_name("zh"),
            review_title=self._get_review_title(overview.date).removeprefix("## ").strip(),
            index_hint=self._get_index_hint(),
            strategy_prompt_block=self._get_strategy_prompt_block(),
            output_template_sections=self._build_output_template_sections(review_language),
        )

    def _generate_template_review(self, overview: MarketOverview, news: List) -> str:
        """使用模板生成复盘报告（无大模型时的备选方案）"""
        return generate_template_review(
            self,
            overview,
            news,
            datetime_cls=datetime,
        )

    def _run_daily_review_parts(self) -> MarketLightReviewResult:
        """Run market review once and keep report/snapshot on the same overview."""
        logger.info("========== 开始大盘复盘分析 ==========")

        # 1. Get market overview
        overview = self.get_market_overview()

        # 2. Search market news
        news = self.search_market_news()
        news = self._merge_persisted_market_intelligence(news)

        # 3. Generate a review report.
        report = self.generate_market_review(overview, news)
        snapshot = self.build_market_light_snapshot(overview) if self._supports_market_light() else None
        structured_payload = self.build_market_review_payload(
            overview,
            news,
            report,
            snapshot,
        )

        logger.info("========== 大盘复盘分析完成 ==========")

        return MarketLightReviewResult(
            overview=overview,
            report=report,
            market_light_snapshot=snapshot,
            structured_payload=structured_payload,
        )

    def _merge_persisted_market_intelligence(self, news: List) -> List:
        """Merge local persisted market intelligence and search news with bounded prompt/payload slot preservation."""
        search_news = list(news or [])
        merged_local = []
        seen_urls = {
            self._get_news_field(item, "url")
            for item in search_news
            if self._get_news_field(item, "url")
        }
        try:
            service = IntelligenceService(config=self.config)
            service.refresh_auto_sources()
            payload = service.list_items(
                scope_type="market",
                market=self.region,
                published_days=max(1, int(self.config.get_effective_news_window_days() or 1)),
                page=1,
                page_size=6,
            )
            for item in payload.get("items", []):
                if not isinstance(item, dict):
                    continue
                url = str(item.get("url") or "")
                if url and url in seen_urls:
                    continue
                seen_urls.add(url)
                merged_local.append({
                    "title": item.get("title") or "未命名资讯",
                    "snippet": item.get("summary") or "",
                    "source": item.get("source") or item.get("source_name") or "local-intel",
                    "published_date": item.get("published_at") or "",
                    "url": "" if url.startswith("no-url:intel:") else url,
                })
        except Exception as exc:  # broad-exception: fallback_recorded - local intelligence failure is logged
            log_safe_exception(
                logger,
                "Market review local intelligence load failed",
                exc,
                error_code="market_review_local_intelligence_load_failed",
                level=logging.DEBUG,
                context={"region": self.region},
            )
        merged_news = []
        merged_local_index = 0
        merged_search_index = 0
        while merged_local_index < len(merged_local) or merged_search_index < len(search_news):
            if merged_local_index < len(merged_local):
                merged_news.append(merged_local[merged_local_index])
                merged_local_index += 1
            if merged_search_index < len(search_news):
                merged_news.append(search_news[merged_search_index])
                merged_search_index += 1
        return merged_news

    def run_daily_review(self) -> str:
        """
        执行每日大盘复盘流程

        Returns:
            复盘报告文本
        """
        return self.run_daily_review_with_snapshot().report

    def run_daily_review_with_snapshot(self) -> MarketLightReviewResult:
        """Run daily review and return the report plus its structured Market Light snapshot."""
        return self._run_daily_review_parts()


# Test entry point
if __name__ == "__main__":
    import sys
    sys.path.insert(0, '.')

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
    )

    analyzer = MarketAnalyzer()

    # Test get market overview
    overview = analyzer.get_market_overview()
    print(f"\n=== 市场概览 ===")
    print(f"日期: {overview.date}")
    print(f"指数数量: {len(overview.indices)}")
    for idx in overview.indices:
        print(f"  {idx.name}: {idx.current:.2f} ({idx.change_pct:+.2f}%)")
    print(f"上涨: {overview.up_count} | 下跌: {overview.down_count}")
    print(f"成交额: {overview.total_amount:.0f}亿")

    # Test generating template reports.
    report = analyzer._generate_template_review(overview, [])
    print(f"\n=== 复盘报告 ===")
    print(report)
