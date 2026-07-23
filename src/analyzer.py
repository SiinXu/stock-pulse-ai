# -*- coding: utf-8 -*-
"""
===================================
A股自选股智能分析系统 - AI分析层
===================================

职责：
1. 封装 LLM 调用逻辑（通过 LiteLLM 统一调用 Gemini/Anthropic/OpenAI 等）
2. 结合技术面和消息面生成分析报告
3. 解析 LLM 响应为结构化 AnalysisResult
"""

import importlib as __importlib
import inspect as __inspect
import json
import logging
import math
import re
import time
import typing as __typing
from dataclasses import dataclass
from types import FunctionType as __FunctionType
from typing import TYPE_CHECKING as __TYPE_CHECKING
from typing import Optional, Dict, Any, List, Tuple, Callable

import litellm
from json_repair import repair_json
from litellm import Router

from src.agent.llm_adapter import (
    get_thinking_extra_body,
    resolve_fallback_litellm_wire_models,
    register_fallback_model_pricing,
)
from src.agent.provider_trace import resolved_model_provider_identity
from src.agent.skills.defaults import CORE_TRADING_SKILL_POLICY_ZH
from src.config import (
    Config,
    extra_litellm_params,
    get_api_keys_for_model,
    get_config,
    get_configured_llm_models,
    resolve_news_window_days,
)
from src.llm.hermes import (
    HERMES_CHANNEL_NAME,
    build_hermes_redaction_values,
    canonicalize_hermes_model_ref,
    filter_non_hermes_deployments,
    hermes_blocked_route_candidates,
    is_masked_secret_placeholder,
    open_hermes_no_proxy_client,
    route_deployment_origins,
    route_has_hermes,
    sanitize_hermes_error_text,
)
from src.llm.generation_params import apply_litellm_generation_params
from src.llm.errors import call_litellm_with_param_recovery
from src.llm.backend_registry import (
    LOCAL_CLI_GENERATION_BACKEND_IDS,
    LITELLM_BACKEND_ID,
    resolve_generation_backend_id,
    resolve_generation_fallback_backend_id,
)
from src.llm.backend_factory import create_generation_backend
from src.llm.generation_backend import (
    GenerationBackend,
    GenerationError,
    GenerationErrorCode,
)
from src.llm.usage import (
    attach_legacy_message_stability_audit,
    attach_message_hmacs,
    extract_usage_payload,
    normalize_litellm_usage,
    should_persist_usage_telemetry,
)
from src.llm.local_cli_backend import redact_diagnostic_text
from src.llm.provider_cache import (
    apply_prompt_cache_hints,
    build_provider_cache_route_context,
    filter_prompt_cache_telemetry,
)
from src.llm.response_content import strip_leading_think_wrapper
from src.storage import persist_llm_usage
from src.data.stock_mapping import STOCK_NAME_MAP
from src.report_language import (
    get_signal_level,
    get_no_data_text,
    get_placeholder_text,
    get_unknown_text,
    get_chip_unavailable_text,
    infer_decision_type_from_advice,
    is_chip_placeholder_value,
    localize_chip_health,
    localize_confidence_level,
    localize_operation_advice,
    localize_trend_prediction,
    normalize_report_language,
)
from src.schemas.decision_action import build_action_fields
from src.schemas.decision_scale import (
    CANONICAL_DECISION_SCALE_PROMPT_ZH,
    score_band_metadata,
)
from src.schemas.report_schema import AnalysisReportSchema
from src.market_context import detect_market, get_market_role, get_market_guidelines
from src.services.daily_market_context import format_daily_market_context_prompt_section
from src.market_phase_prompt import format_market_phase_prompt_section
from src.market_structure_prompt import format_market_structure_prompt_section

# A facade reload must recreate moved mutable constants, as the monolith did.
if "__result_processing" in globals():
    __result_processing = __importlib.reload(globals()["__result_processing"])
else:
    from src.analyzer_parts import result_processing as __result_processing

if __TYPE_CHECKING:
    from src.analyzer_parts.result_processing import (
        _localized_text,
        _safe_float,
        _sanitize_trend_analysis_for_prompt,
        apply_placeholder_fill,
        check_content_integrity,
        normalize_chip_structure_availability,
    )

logger = logging.getLogger(__name__)


def _today_has_realtime_overlay(today: Any) -> bool:
    if not isinstance(today, dict):
        return False
    data_source = today.get("data_source") or today.get("dataSource")
    if isinstance(data_source, str) and data_source.startswith("realtime:"):
        return True
    if today.get("is_partial_bar") is True or today.get("isPartialBar") is True:
        return True
    if today.get("is_estimated") is True or today.get("isEstimated") is True:
        return True
    return bool(today.get("estimated_fields") or today.get("estimatedFields"))


def _today_looks_complete_daily_bar(
    context: Dict[str, Any],
    phase_context: Dict[str, Any],
) -> bool:
    today = context.get("today")
    if (
        not isinstance(today, dict)
        or today.get("close") in (None, "")
        or _today_has_realtime_overlay(today)
    ):
        return False

    effective_date = phase_context.get("effective_daily_bar_date")
    today_date = today.get("date") or today.get("trade_date") or context.get("date")
    if effective_date and today_date and str(today_date) != str(effective_date):
        return False
    return True


def _phase_aware_quote_labels(context: Dict[str, Any]) -> Tuple[str, str]:
    """Choose Chinese quote-table labels that do not conflict with phase context."""
    phase_context = context.get("market_phase_context")
    if not isinstance(phase_context, dict):
        return "今日行情", "收盘价"

    phase = str(phase_context.get("phase") or "").strip()
    if phase in {"premarket", "non_trading"}:
        today = context.get("today")
        if _today_looks_complete_daily_bar(context, phase_context):
            return "上一完整交易日行情", "上一完整交易日收盘价"
        if _today_has_realtime_overlay(today):
            return "最新行情", "实时估算价"
        if isinstance(today, dict) and today.get("close") not in (None, ""):
            return "最新行情", "最新价"
        return "今日行情", "收盘价"

    if (
        phase in {"intraday", "lunch_break", "closing_auction"}
        and phase_context.get("is_partial_bar") is True
    ):
        return "最新行情", "盘中估算价"

    return "今日行情", "收盘价"


def _should_hide_regular_session_ohlc(context: Dict[str, Any]) -> bool:
    phase_context = context.get("market_phase_context")
    if not isinstance(phase_context, dict):
        return False

    phase = str(phase_context.get("phase") or "").strip()
    return phase in {"premarket", "non_trading"} and not _today_looks_complete_daily_bar(
        context,
        phase_context,
    )


def _legacy_market_group(stock_code: Any) -> str:
    code = str(stock_code or "").strip()
    if not code or code.lower() == "unknown":
        return "unknown"
    market = detect_market(code)
    return market if market in {"cn", "hk", "us"} else "unknown"


def _legacy_audit_marker_specs(
    context: Dict[str, Any],
    *,
    code: str,
    stock_name: str,
    report_language: str,
    news_context: Optional[str],
    analysis_context_pack_summary: Optional[str],
) -> List[Dict[str, Any]]:
    markers: List[Dict[str, Any]] = []

    def add(marker_name: str, value: Any) -> None:
        if value is None:
            return
        text = str(value).strip()
        if not text:
            return
        markers.append(
            {
                "marker_name": marker_name,
                "message_role": "user",
                "text": text,
            }
        )

    add("stock_code", code)
    add("stock_name", stock_name)
    add("analysis_date", context.get("date"))
    add("market_phase", "## Market Phase Context" if report_language in ("en", "ko") else "## 市场阶段上下文")
    add("daily_market_context", "## Daily Market Context" if report_language in ("en", "ko") else "## 大盘环境摘要")
    add("market_structure_context", "## Market Structure Context" if report_language in ("en", "ko") else "## 市场结构上下文")
    add("analysis_context_pack", analysis_context_pack_summary)
    add("quote", "## 📈 技术面数据")
    add("news_context", "## 📰 舆情情报" if news_context else None)
    return markers


class _LiteLLMStreamError(RuntimeError):
    """Internal error wrapper that records whether any text was streamed."""

    def __init__(self, message: str, *, partial_received: bool = False):
        super().__init__(message)
        self.partial_received = partial_received


class _AllModelsFailedError(Exception):
    """Raised when every model in the fallback chain fails.

    This includes both LLM call errors and JSON parse errors (when a
    ``response_validator`` is provided to :meth:`GeminiAnalyzer._call_litellm`).

    The ``last_response_text`` attribute holds the raw text from the last model
    that *did* return a response (but whose JSON could not be validated), so
    callers can still attempt a best-effort text fallback.

    ``last_model`` and ``last_usage`` record the model name and token usage
    from the last attempt so callers can persist usage even on fallback.
    """

    def __init__(
        self,
        message: str,
        *,
        last_response_text: Optional[str] = None,
        last_model: Optional[str] = None,
        last_usage: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.last_response_text = last_response_text
        self.last_model = last_model
        self.last_usage = last_usage or {}


from src.utils.data_processing import normalize_report_signal_attribution
from src.utils.sanitize import (
    exception_chain_redaction_values,
    log_safe_exception,
    sanitize_diagnostic_text as sanitize_shared_diagnostic_text,
)


@dataclass
class AnalysisResult:
    """
    AI 分析结果数据类 - 决策仪表盘版

    封装 Gemini 返回的分析结果，包含决策仪表盘和详细分析
    """
    code: str
    name: str

    # ========== Core Metrics ==========
    sentiment_score: int  # Overall score 0-100 (>70 strongly bullish, >60 bullish, 40-60 range bound, <40 bearish)
    trend_prediction: str  # Trend prediction: Strongly bullish/bullish/sideways/bearish/strongly bearish
    operation_advice: str  # Trading Recommendations: Buy/Add to Position/Hold/Reduce Position/Sell/Watch
    decision_type: str = "hold"  # Decision type: buy/hold/sell (for statistics)
    confidence_level: str = "中"  # Confidence: High/Medium/Low
    report_language: str = "zh"  # Report output language: zh/en
    action: Optional[str] = None  # Recommendation taxonomy: buy/add/hold/reduce/sell/watch/avoid/alert
    action_label: Optional[str] = None  # Localized action tag suggestions

    # ========== Decision Dashboard (New) ==========
    dashboard: Optional[Dict[str, Any]] = None  # Complete decision dashboard data

    # ========== Trend Analysis ==========
    trend_analysis: str = ""  # Trend pattern analysis (support levels, resistance levels, trend lines, etc.)
    short_term_outlook: str = ""  # Short-term Outlook (1-3 days)
    medium_term_outlook: str = ""  # Mid-term outlook (1-2 weeks)

    # ========== Technical Context Analysis ==========
    technical_analysis: str = ""  # Comprehensive technical indicator analysis
    ma_analysis: str = ""  # Moving Average analysis (bullish/bearish patterns, golden cross/death cross, etc.)
    volume_analysis: str = ""  # Volume analysis (expansion/contraction and major-fund activity)
    pattern_analysis: str = ""  # Candlestick pattern analysis.

    # ========== Fundamental Analysis ==========
    fundamental_analysis: str = ""  # Comprehensive fundamental analysis
    sector_position: str = ""  # Sector status and industry trends
    company_highlights: str = ""  # Company highlights/risks

    # ========== Sentiment/News Context Analysis ==========
    news_summary: str = ""  # Recent important news/announcements summary
    market_sentiment: str = ""  # Market Sentiment Analysis
    hot_topics: str = ""  # Relevant hot topics

    # ========== Comprehensive Analysis ==========
    analysis_summary: str = ""  # Comprehensive analysis summary
    key_points: str = ""  # Key Highlights (3-5 Points)
    risk_warning: str = ""  # Risk prompt
    buy_reason: str = ""  # Buy/Sell Reason

    # ========== Metadata =========
    market_snapshot: Optional[Dict[str, Any]] = None  # Daily market snapshot (for display)
    raw_response: Optional[str] = None  # Original response (for debugging)
    search_performed: bool = False  # Did it execute a web search?
    data_sources: str = ""  # Data source explanation
    success: bool = True
    error_message: Optional[str] = None

    # ========== Price Data (Snapshot for analysis) ===========
    current_price: Optional[float] = None  # The price of the stock during the analysis.
    change_pct: Optional[float] = None     # The percentage change in price during the analysis (%).

    # ========== Model Tag (Issue #528)==========
    model_used: Optional[str] = None  # Analyze the used LLM model (full name, such as gemini/gemini-2.0-flash)

    # ========== Historical comparison(Report Engine P0)==========
    query_id: Optional[str] = None  # This analysis query_id, exclude this record when performing historical comparisons

    # ========== Fundamentals Context (Runtime only, used for notification assembly; not persisted to to_dict)==========
    fundamental_context: Optional[Dict[str, Any]] = None
    market_structure_context: Optional[Dict[str, Any]] = None

    # ========== Historical Decision Reflection (Issue #118; runtime only, not persisted to to_dict) ==========
    # Carries a DecisionReflection so the report renderer can emit its section.
    decision_reflection: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'code': self.code,
            'name': self.name,
            'sentiment_score': self.sentiment_score,
            'trend_prediction': self.trend_prediction,
            'operation_advice': self.operation_advice,
            'decision_type': self.decision_type,
            'confidence_level': self.confidence_level,
            'report_language': self.report_language,
            'action': self.action,
            'action_label': self.action_label,
            'dashboard': self.dashboard,  # Decision dashboard data
            'trend_analysis': self.trend_analysis,
            'short_term_outlook': self.short_term_outlook,
            'medium_term_outlook': self.medium_term_outlook,
            'technical_analysis': self.technical_analysis,
            'ma_analysis': self.ma_analysis,
            'volume_analysis': self.volume_analysis,
            'pattern_analysis': self.pattern_analysis,
            'fundamental_analysis': self.fundamental_analysis,
            'sector_position': self.sector_position,
            'company_highlights': self.company_highlights,
            'news_summary': self.news_summary,
            'market_sentiment': self.market_sentiment,
            'hot_topics': self.hot_topics,
            'analysis_summary': self.analysis_summary,
            'key_points': self.key_points,
            'risk_warning': self.risk_warning,
            'buy_reason': self.buy_reason,
            'market_snapshot': self.market_snapshot,
            'search_performed': self.search_performed,
            'success': self.success,
            'error_message': self.error_message,
            'current_price': self.current_price,
            'change_pct': self.change_pct,
            'model_used': self.model_used,
            'market_structure_context': self.market_structure_context,
        }

    def get_core_conclusion(self) -> str:
        """获取核心结论（一句话）"""
        if self.dashboard and 'core_conclusion' in self.dashboard:
            return self.dashboard['core_conclusion'].get('one_sentence', self.analysis_summary)
        return self.analysis_summary

    def get_position_advice(self, has_position: bool = False) -> str:
        """获取持仓建议"""
        if self.dashboard and 'core_conclusion' in self.dashboard:
            pos_advice = self.dashboard['core_conclusion'].get('position_advice', {})
            if has_position:
                return pos_advice.get('has_position', self.operation_advice)
            return pos_advice.get('no_position', self.operation_advice)
        return self.operation_advice

    def get_sniper_points(self) -> Dict[str, str]:
        """获取狙击点位"""
        if self.dashboard and 'battle_plan' in self.dashboard:
            return self.dashboard['battle_plan'].get('sniper_points', {})
        return {}

    def get_checklist(self) -> List[str]:
        """获取检查清单"""
        if self.dashboard and 'battle_plan' in self.dashboard:
            return self.dashboard['battle_plan'].get('action_checklist', [])
        return []

    def get_risk_alerts(self) -> List[str]:
        """获取风险警报"""
        if self.dashboard and 'intelligence' in self.dashboard:
            return self.dashboard['intelligence'].get('risk_alerts', [])
        return []

    def get_emoji(self) -> str:
        """根据操作建议返回对应 emoji"""
        _, emoji, _ = get_signal_level(
            self.operation_advice,
            self.sentiment_score,
            self.report_language,
        )
        return emoji

    def get_confidence_stars(self) -> str:
        """返回置信度星级"""
        star_map = {
            "高": "⭐⭐⭐",
            "high": "⭐⭐⭐",
            "中": "⭐⭐",
            "medium": "⭐⭐",
            "低": "⭐",
            "low": "⭐",
        }
        return star_map.get(str(self.confidence_level or "").strip().lower(), "⭐⭐")


def populate_decision_action_fields(
    result: AnalysisResult,
    *,
    explicit_action: Any = None,
    report_type: Any = None,
    use_existing_action: bool = True,
    align_with_score: bool = True,
) -> AnalysisResult:
    """Populate optional decision action fields without changing legacy advice."""

    action_source = explicit_action
    if action_source is None and use_existing_action:
        action_source = getattr(result, "action", None)

    fields = build_action_fields(
        operation_advice=getattr(result, "operation_advice", None),
        explicit_action=action_source,
        report_type=report_type,
        report_language=getattr(result, "report_language", "zh"),
        sentiment_score=getattr(result, "sentiment_score", None),
        guardrail_reason=getattr(result, "guardrail_reason", None),
        align_with_score=align_with_score,
    )
    result.action = fields["action"]
    result.action_label = fields["action_label"]
    return result


def __clone_facade_function(
    function: __FunctionType,
    *,
    qualname: str,
    resolve_annotations: bool = False,
) -> __FunctionType:
    """Clone a function with the legacy analyzer facade as its globals."""

    rebound = __FunctionType(
        function.__code__,
        globals(),
        function.__name__,
        function.__defaults__,
        function.__closure__,
    )
    rebound.__kwdefaults__ = (
        dict(function.__kwdefaults__) if function.__kwdefaults__ else None
    )
    annotations = dict(function.__annotations__)
    if resolve_annotations:
        if any(
            __contains_forward_reference(annotation)
            for annotation in annotations.values()
        ):
            resolved = __typing.get_type_hints(
                function,
                globalns=globals(),
                localns=globals(),
                include_extras=True,
            )
            for annotation_name, annotation in annotations.items():
                if annotation is None:
                    resolved[annotation_name] = None
            annotations = resolved
        else:
            annotations = __inspect.get_annotations(
                function,
                globals=globals(),
                locals=globals(),
                eval_str=True,
            )
    rebound.__annotations__ = annotations
    rebound.__dict__.update(function.__dict__)
    rebound.__doc__ = function.__doc__
    rebound.__module__ = __name__
    rebound.__qualname__ = qualname
    if hasattr(function, "__type_params__"):
        rebound.__type_params__ = function.__type_params__
    return rebound


def __contains_forward_reference(annotation: Any) -> bool:
    """Return whether an annotation contains a deferred facade-owned type."""

    if isinstance(annotation, __typing.ForwardRef):
        return True
    return any(
        __contains_forward_reference(argument)
        for argument in __typing.get_args(annotation)
    )


def __clone_analyzer_descriptor(descriptor: Any) -> Any:
    """Clone an analyzer descriptor with facade globals and annotations."""

    descriptor_type = None
    function = descriptor
    if isinstance(descriptor, staticmethod):
        descriptor_type = staticmethod
        function = descriptor.__func__
    elif isinstance(descriptor, classmethod):
        descriptor_type = classmethod
        function = descriptor.__func__

    rebound = __clone_facade_function(
        function,
        qualname=function.__qualname__,
        resolve_annotations=True,
    )
    return descriptor_type(rebound) if descriptor_type is not None else rebound


if "__analyzer_method_modules" in globals():
    __analyzer_method_modules = tuple(
        __importlib.reload(module)
        for module in globals()["__analyzer_method_modules"]
    )
else:
    from src.analyzer_parts import analysis as __analysis_methods
    from src.analyzer_parts import generation as __generation_methods
    from src.analyzer_parts import response as __response_methods

    __analyzer_method_modules = (
        __generation_methods,
        __analysis_methods,
        __response_methods,
    )


class GeminiAnalyzer:
    """
    Gemini AI 分析器

    职责：
    1. 调用 Google Gemini API 进行股票分析
    2. 结合预先搜索的新闻和技术面数据生成分析报告
    3. 解析 AI 返回的 JSON 格式结果

    使用方式：
        analyzer = GeminiAnalyzer()
        result = analyzer.analyze(context, news_context)
    """

    # ========================================
    # System prompt - Decision Dashboard v2.0
    # ========================================
    # Output format upgrade: from simple signal to decision dashboard
    # Core Modules: Core Conclusion + Data Insights + Sentiment Intelligence + Operational Plan
    # ========================================

    LEGACY_DEFAULT_SYSTEM_PROMPT = """你是一位专注于趋势交易的{market_placeholder}投资分析师，负责生成专业的【决策仪表盘】分析报告。

{guidelines_placeholder}

""" + CORE_TRADING_SKILL_POLICY_ZH + """

""" + CANONICAL_DECISION_SCALE_PROMPT_ZH + """

## 输出格式：决策仪表盘 JSON

请严格按照以下 JSON 格式输出，这是一个完整的【决策仪表盘】：

```json
{
    "stock_name": "股票中文名称",
    "sentiment_score": 0-100整数,
    "trend_prediction": "强烈看多/看多/震荡/看空/强烈看空",
    "operation_advice": "买入/加仓/持有/减仓/卖出/观望",
    "decision_type": "buy/hold/sell",
    "action": "buy/add/hold/reduce/sell/watch/avoid/alert",
    "guardrail_reason": "当分数区间与最终 action 不一致时填写降级/升级原因，否则留空",
    "confidence_level": "高/中/低",

    "dashboard": {
        "core_conclusion": {
            "one_sentence": "一句话核心结论（30字以内，直接告诉用户做什么）",
            "signal_type": "🟢买入信号/🟡持有观望/🔴卖出信号/⚠️风险警告",
            "time_sensitivity": "立即行动/今日内/本周内/不急",
            "position_advice": {
                "no_position": "空仓者建议：具体操作指引",
                "has_position": "持仓者建议：具体操作指引"
            }
        },

        "data_perspective": {
            "trend_status": {
                "ma_alignment": "均线排列状态描述",
                "is_bullish": true/false,
                "trend_score": 0-100
            },
            "price_position": {
                "current_price": 当前价格数值,
                "ma5": MA5数值,
                "ma10": MA10数值,
                "ma20": MA20数值,
                "bias_ma5": 乖离率百分比数值,
                "bias_status": "安全/警戒/危险",
                "support_level": 支撑位价格,
                "resistance_level": 压力位价格
            },
            "volume_analysis": {
                "volume_ratio": 量比数值,
                "volume_status": "放量/缩量/平量",
                "turnover_rate": 换手率百分比,
                "volume_meaning": "量能含义解读（如：缩量回调表示抛压减轻）"
            },
            "chip_structure": {
                "profit_ratio": 获利比例,
                "avg_cost": 平均成本,
                "concentration": 筹码集中度,
                "chip_health": "健康/一般/警惕"
            }
        },

        "intelligence": {
            "latest_news": "【最新消息】近期重要新闻摘要",
            "risk_alerts": ["风险点1：具体描述", "风险点2：具体描述"],
            "positive_catalysts": ["利好1：具体描述", "利好2：具体描述"],
            "earnings_outlook": "业绩预期分析（基于年报预告、业绩快报等）",
            "sentiment_summary": "舆情情绪一句话总结"
        },

        "battle_plan": {
            "sniper_points": {
                "ideal_buy": "理想买入点：XX元（在MA5附近）",
                "secondary_buy": "次优买入点：XX元（在MA10附近）",
                "stop_loss": "止损位：XX元（跌破MA20或X%）",
                "take_profit": "目标位：XX元（前高/整数关口）"
            },
            "position_strategy": {
                "suggested_position": "建议仓位：X成",
                "entry_plan": "分批建仓策略描述",
                "risk_control": "风控策略描述"
            },
            "action_checklist": [
                "✅/⚠️/❌ 检查项1：多头排列",
                "✅/⚠️/❌ 检查项2：乖离率合理（强势趋势可放宽）",
                "✅/⚠️/❌ 检查项3：量能配合",
                "✅/⚠️/❌ 检查项4：无重大利空",
                "✅/⚠️/❌ 检查项5：筹码健康",
                "✅/⚠️/❌ 检查项6：PE估值合理"
            ]
        },

        "phase_decision": {
            "phase_context": {"phase": "premarket/intraday/lunch_break/closing_auction/postmarket/non_trading/unknown"},
            "action_window": "盘前计划/盘中跟踪/午间确认/收盘前风控/盘后复盘/非交易日观察",
            "immediate_action": "立即行动/等待确认/观察/止损止盈预警/禁止追高/无盘中动作",
            "watch_conditions": ["观察条件1", "观察条件2"],
            "next_check_time": "下一次检查点或市场本地时间",
            "confidence_reason": "置信度理由，说明阶段和数据质量限制",
            "data_limitations": ["阶段或数据质量限制1", "阶段或数据质量限制2"]
        },

        "signal_attribution": {
            "technical_indicators": 技术指标贡献度(0-100),
            "news_sentiment": 新闻舆情贡献度(0-100),
            "fundamentals": 基本面贡献度(0-100),
            "market_conditions": 市场环境贡献度(0-100),
            "strongest_bullish_signal": "最强看多信号名称",
            "strongest_bearish_signal": "最强看空信号名称"
        }
    },

    "analysis_summary": "100字综合分析摘要",
    "key_points": "3-5个核心看点，逗号分隔",
    "risk_warning": "风险提示",
    "buy_reason": "操作理由，引用交易理念",

    "trend_analysis": "走势形态分析",
    "short_term_outlook": "短期1-3日展望",
    "medium_term_outlook": "中期1-2周展望",
    "technical_analysis": "技术面综合分析",
    "ma_analysis": "均线系统分析",
    "volume_analysis": "量能分析",
    "pattern_analysis": "K线形态分析",
    "fundamental_analysis": "基本面分析",
    "sector_position": "板块行业分析",
    "company_highlights": "公司亮点/风险",
    "news_summary": "新闻摘要",
    "market_sentiment": "市场情绪",
    "hot_topics": "相关热点",

    "search_performed": true/false,
    "data_sources": "数据来源说明"
}
```

## 评分标准

### 强烈买入（80-100分）：
- ✅ 多头排列：MA5 > MA10 > MA20
- ✅ 低乖离率：<2%，最佳买点
- ✅ 缩量回调或放量突破
- ✅ 筹码集中健康
- ✅ 消息面有利好催化

### 买入（60-79分）：
- ✅ 多头排列或弱势多头
- ✅ 乖离率 <5%
- ✅ 量能正常
- ⚪ 允许一项次要条件不满足

### 观望（40-59分）：
- ⚠️ 乖离率 >5%（追高风险）
- ⚠️ 均线缠绕趋势不明
- ⚠️ 有风险事件

### 减仓（20-39分）：
- ⚠️ 趋势走弱或跌破关键均线
- ⚠️ 资金/量能转弱，风险明显高于收益
- ⚠️ 以降低仓位和保护收益为主

### 卖出（0-19分）：
- ❌ 空头排列或趋势显著恶化
- ❌ 跌破关键支撑/止损位
- ❌ 放量下跌或重大利空

## 决策仪表盘核心原则

1. **核心结论先行**：一句话说清该买该卖
2. **分持仓建议**：空仓者和持仓者给不同建议
3. **精确狙击点**：必须给出具体价格，不说模糊的话
4. **检查清单可视化**：用 ✅⚠️❌ 明确显示每项检查结果
5. **风险优先级**：舆情中的风险点要醒目标出

## 可操作性与稳定性约束

- 不得仅因为单日涨跌或评分跨线就在“买入/卖出”之间剧烈切换。
- 操作建议必须同时参考价格位置（支撑/压力位）、量能/筹码、主力资金流向和风险事件。
- 股价位于支撑与压力之间、资金流不明确时，优先输出“持有/震荡/观望/洗盘观察”等可执行的中性建议；`decision_type` 仍保持 `hold`。
- 只有在接近支撑确认或有效突破压力，且资金流/量价配合时，才能给出买入；接近压力且资金流出时不得追买。
- 只有在跌破关键支撑、主力资金持续流出或风险显著放大时，才能给出卖出/减仓。
- 必须输出 `dashboard.phase_decision` 七字段；盘中/午休/临近收盘要给出当前动作、观察条件和下一次检查点。
- 建议输出可选展示字段 `dashboard.signal_attribution` 六字段；解释推荐理由的构成，包括技术指标、新闻舆情、基本面、市场环境的贡献度，以及最强看多/看空信号。
- 盘前、非交易日或未知阶段不得伪造今日盘中走势；quote/daily_bars/technical 存在 stale、fallback、missing、fetch_failed、partial 或 estimated 时，`confidence_level` 不得为高。"""

    SYSTEM_PROMPT = """你是一位{market_placeholder}投资分析师，负责生成专业的【决策仪表盘】分析报告。

{guidelines_placeholder}

{default_skill_policy_section}
{skills_section}

""" + CANONICAL_DECISION_SCALE_PROMPT_ZH + """

## 输出格式：决策仪表盘 JSON

请严格按照以下 JSON 格式输出，这是一个完整的【决策仪表盘】：

```json
{
    "stock_name": "股票中文名称",
    "sentiment_score": 0-100整数,
    "trend_prediction": "强烈看多/看多/震荡/看空/强烈看空",
    "operation_advice": "买入/加仓/持有/减仓/卖出/观望",
    "decision_type": "buy/hold/sell",
    "action": "buy/add/hold/reduce/sell/watch/avoid/alert",
    "guardrail_reason": "当分数区间与最终 action 不一致时填写降级/升级原因，否则留空",
    "confidence_level": "高/中/低",

    "dashboard": {
        "core_conclusion": {
            "one_sentence": "一句话核心结论（30字以内，直接告诉用户做什么）",
            "signal_type": "🟢买入信号/🟡持有观望/🔴卖出信号/⚠️风险警告",
            "time_sensitivity": "立即行动/今日内/本周内/不急",
            "position_advice": {
                "no_position": "空仓者建议：具体操作指引",
                "has_position": "持仓者建议：具体操作指引"
            }
        },

        "data_perspective": {
            "trend_status": {
                "ma_alignment": "均线排列状态描述",
                "is_bullish": true/false,
                "trend_score": 0-100
            },
            "price_position": {
                "current_price": 当前价格数值,
                "ma5": MA5数值,
                "ma10": MA10数值,
                "ma20": MA20数值,
                "bias_ma5": 乖离率百分比数值,
                "bias_status": "安全/警戒/危险",
                "support_level": 支撑位价格,
                "resistance_level": 压力位价格
            },
            "volume_analysis": {
                "volume_ratio": 量比数值,
                "volume_status": "放量/缩量/平量",
                "turnover_rate": 换手率百分比,
                "volume_meaning": "量能含义解读（如：缩量回调表示抛压减轻）"
            },
            "chip_structure": {
                "profit_ratio": 获利比例,
                "avg_cost": 平均成本,
                "concentration": 筹码集中度,
                "chip_health": "健康/一般/警惕"
            }
        },

        "intelligence": {
            "latest_news": "【最新消息】近期重要新闻摘要",
            "risk_alerts": ["风险点1：具体描述", "风险点2：具体描述"],
            "positive_catalysts": ["利好1：具体描述", "利好2：具体描述"],
            "earnings_outlook": "业绩预期分析（基于年报预告、业绩快报等）",
            "sentiment_summary": "舆情情绪一句话总结"
        },

        "battle_plan": {
            "sniper_points": {
                "ideal_buy": "理想入场位：XX元（满足主要技能触发条件）",
                "secondary_buy": "次优入场位：XX元（更保守或确认后执行）",
                "stop_loss": "止损位：XX元（失效条件或X%风险）",
                "take_profit": "目标位：XX元（按阻力位/风险回报比制定）"
            },
            "position_strategy": {
                "suggested_position": "建议仓位：X成",
                "entry_plan": "分批建仓策略描述",
                "risk_control": "风控策略描述"
            },
            "action_checklist": [
                "✅/⚠️/❌ 检查项1：当前结构是否满足激活技能条件",
                "✅/⚠️/❌ 检查项2：入场位置与风险回报是否合理",
                "✅/⚠️/❌ 检查项3：量价/波动/筹码是否支持判断",
                "✅/⚠️/❌ 检查项4：无重大利空",
                "✅/⚠️/❌ 检查项5：仓位与止损计划明确",
                "✅/⚠️/❌ 检查项6：估值/业绩/催化与结论匹配"
            ]
        },

        "phase_decision": {
            "phase_context": {"phase": "premarket/intraday/lunch_break/closing_auction/postmarket/non_trading/unknown"},
            "action_window": "盘前计划/盘中跟踪/午间确认/收盘前风控/盘后复盘/非交易日观察",
            "immediate_action": "立即行动/等待确认/观察/止损止盈预警/禁止追高/无盘中动作",
            "watch_conditions": ["观察条件1", "观察条件2"],
            "next_check_time": "下一次检查点或市场本地时间",
            "confidence_reason": "置信度理由，说明阶段和数据质量限制",
            "data_limitations": ["阶段或数据质量限制1", "阶段或数据质量限制2"]
        },

        "signal_attribution": {
            "technical_indicators": 技术指标贡献度(0-100),
            "news_sentiment": 新闻舆情贡献度(0-100),
            "fundamentals": 基本面贡献度(0-100),
            "market_conditions": 市场环境贡献度(0-100),
            "strongest_bullish_signal": "最强看多信号名称",
            "strongest_bearish_signal": "最强看空信号名称"
        }
    },

    "analysis_summary": "100字综合分析摘要",
    "key_points": "3-5个核心看点，逗号分隔",
    "risk_warning": "风险提示",
    "buy_reason": "操作理由，引用激活技能或风险框架",

    "trend_analysis": "走势形态分析",
    "short_term_outlook": "短期1-3日展望",
    "medium_term_outlook": "中期1-2周展望",
    "technical_analysis": "技术面综合分析",
    "ma_analysis": "均线系统分析",
    "volume_analysis": "量能分析",
    "pattern_analysis": "K线形态分析",
    "fundamental_analysis": "基本面分析",
    "sector_position": "板块行业分析",
    "company_highlights": "公司亮点/风险",
    "news_summary": "新闻摘要",
    "market_sentiment": "市场情绪",
    "hot_topics": "相关热点",

    "search_performed": true/false,
    "data_sources": "数据来源说明"
}
```

## 评分标准

### 强烈买入（80-100分）：
- ✅ 多个激活技能同时支持积极结论
- ✅ 上行空间、触发条件与风险回报清晰
- ✅ 关键风险已排查，仓位与止损计划明确
- ✅ 重要数据和情报结论彼此一致

### 买入（60-79分）：
- ✅ 主信号偏积极，但仍有少量待确认项
- ✅ 允许存在可控风险或次优入场点
- ✅ 需要在报告中明确补充观察条件

### 观望（40-59分）：
- ⚠️ 信号分歧较大，或缺乏足够确认
- ⚠️ 风险与机会大致均衡
- ⚠️ 更适合等待触发条件或回避不确定性

### 减仓（20-39分）：
- ⚠️ 主要结论转弱，风险明显高于收益
- ⚠️ 触发了部分失效条件，现有仓位需要降低暴露
- ⚠️ 更适合保护收益而不是进攻

### 卖出（0-19分）：
- ❌ 触发了止损/失效条件或重大利空
- ❌ 趋势或风险显著恶化
- ❌ 现有仓位应优先退出

## 决策仪表盘核心原则

1. **核心结论先行**：一句话说清该买该卖
2. **分持仓建议**：空仓者和持仓者给不同建议
3. **精确狙击点**：必须给出具体价格，不说模糊的话
4. **检查清单可视化**：用 ✅⚠️❌ 明确显示每项检查结果
5. **风险优先级**：舆情中的风险点要醒目标出

## 可操作性与稳定性约束

- 不得仅因为单日涨跌或评分跨线就在“买入/卖出”之间剧烈切换。
- 操作建议必须同时参考价格位置（支撑/压力位）、量能/筹码、主力资金流向和风险事件。
- 股价位于支撑与压力之间、资金流不明确时，优先输出“持有/震荡/观望/洗盘观察”等可执行的中性建议；`decision_type` 仍保持 `hold`。
- 只有在接近支撑确认或有效突破压力，且资金流/量价配合时，才能给出买入；接近压力且资金流出时不得追买。
- 只有在跌破关键支撑、主力资金持续流出或风险显著放大时，才能给出卖出/减仓。
- 必须输出 `dashboard.phase_decision` 七字段；盘中/午休/临近收盘要给出当前动作、观察条件和下一次检查点。
- 建议输出可选展示字段 `dashboard.signal_attribution` 六字段；解释推荐理由的构成，包括技术指标、新闻舆情、基本面、市场环境的贡献度，以及最强看多/看空信号。
- 盘前、非交易日或未知阶段不得伪造今日盘中走势；quote/daily_bars/technical 存在 stale、fallback、missing、fetch_failed、partial 或 estimated 时，`confidence_level` 不得为高。"""

    TEXT_SYSTEM_PROMPT = """你是一位专业的股票分析助手。

- 回答必须基于用户提供的数据与上下文
- 若信息不足，要明确指出不确定性
- 不要编造价格、财报或新闻事实
"""

    for _method_module in globals()["__analyzer_method_modules"]:
        for _method_name, _method_descriptor in vars(
            _method_module.GeminiAnalyzer
        ).items():
            _method_function = (
                _method_descriptor.__func__
                if isinstance(_method_descriptor, (staticmethod, classmethod))
                else _method_descriptor
            )
            if isinstance(_method_function, globals()["__FunctionType"]):
                locals()[_method_name] = globals()[
                    "__clone_analyzer_descriptor"
                ](_method_descriptor)

    del _method_module, _method_name, _method_descriptor, _method_function


# Convenient function
def get_analyzer() -> GeminiAnalyzer:
    """获取 LLM 分析器实例"""
    return GeminiAnalyzer()


_CHIP_KEYS: tuple = __result_processing._CHIP_KEYS
_RISK_WARNING_PLACEHOLDER_TEXTS = __result_processing._RISK_WARNING_PLACEHOLDER_TEXTS
_STRUCTURAL_RISK_PHRASE_HINTS = __result_processing._STRUCTURAL_RISK_PHRASE_HINTS
_CAPITAL_FLOW_UNAVAILABLE_STATUS = __result_processing._CAPITAL_FLOW_UNAVAILABLE_STATUS
_BULLISH_TREND_HINTS: Tuple[str, ...] = __result_processing._BULLISH_TREND_HINTS
_WEAK_BULLISH_TREND_HINTS: Tuple[str, ...] = (
    __result_processing._WEAK_BULLISH_TREND_HINTS
)
_BEARISH_TREND_HINTS: Tuple[str, ...] = __result_processing._BEARISH_TREND_HINTS
_WEAK_BEARISH_TREND_HINTS: Tuple[str, ...] = (
    __result_processing._WEAK_BEARISH_TREND_HINTS
)
_NEGATION_TOKENS: Tuple[str, ...] = __result_processing._NEGATION_TOKENS
_NEGATION_BREAK_CHARS: Tuple[str, ...] = __result_processing._NEGATION_BREAK_CHARS
_NEGATION_LOOKBACK_CHARS = __result_processing._NEGATION_LOOKBACK_CHARS
_NEGATION_MAX_GAP_CHARS = __result_processing._NEGATION_MAX_GAP_CHARS
_NEGATION_SCOPE_BREAK_TOKENS: Tuple[str, ...] = (
    __result_processing._NEGATION_SCOPE_BREAK_TOKENS
)
_SINGLE_CHAR_NEGATION_GAP_PREFIXES: Tuple[str, ...] = (
    __result_processing._SINGLE_CHAR_NEGATION_GAP_PREFIXES
)
_PRICE_POS_KEYS = __result_processing._PRICE_POS_KEYS

for __name_to_bind, __value_to_bind in vars(__result_processing).items():
    if (
        isinstance(__value_to_bind, __FunctionType)
        and __value_to_bind.__module__ == __result_processing.__name__
    ):
        globals()[__name_to_bind] = __clone_facade_function(
            __value_to_bind,
            qualname=__value_to_bind.__name__,
        )


if __name__ == "__main__":
    # Test code
    logging.basicConfig(level=logging.DEBUG)
    
    # Simulate context data
    test_context = {
        'code': '600519',
        'date': '2026-01-09',
        'today': {
            'open': 1800.0,
            'high': 1850.0,
            'low': 1780.0,
            'close': 1820.0,
            'volume': 10000000,
            'amount': 18200000000,
            'pct_chg': 1.5,
            'ma5': 1810.0,
            'ma10': 1800.0,
            'ma20': 1790.0,
            'volume_ratio': 1.2,
        },
        'ma_status': '多头排列 📈',
        'volume_change_ratio': 1.3,
        'price_change_ratio': 1.5,
    }
    
    analyzer = GeminiAnalyzer()
    
    if analyzer.is_available():
        print("=== AI 分析测试 ===")
        result = analyzer.analyze(test_context)
        print(f"分析结果: {result.to_dict()}")
    else:
        print("Gemini API 未配置，跳过测试")
