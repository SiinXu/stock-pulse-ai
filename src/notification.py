# -*- coding: utf-8 -*-
"""
===================================
A股自选股智能分析系统 - 通知层
===================================

职责：
1. 汇总分析结果生成日报
2. 支持 Markdown 格式输出
3. 多渠道推送（自动识别）：
   - 企业微信 Webhook
   - 飞书 Webhook
   - Telegram Bot
   - 邮件 SMTP
   - Pushover（手机/桌面推送）
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple, TYPE_CHECKING
from enum import Enum

from src.agent.facade_binding import bind_facade_methods as _bind_facade_methods
from src.config import Config, get_config
from src.enums import ReportType
from src.market_phase_summary import format_public_market_status_line, format_public_phase_pack_excerpt
from src.notification_routing import (
    ROUTABLE_NOTIFICATION_CHANNELS as _ROUTABLE_NOTIFICATION_CHANNELS,
    get_notification_route_config,
    split_notification_route_channels,
)
from src.notification_contracts import is_feishu_static_configured
from src.notification_noise import (
    NotificationNoiseDecision,
    evaluate_notification_noise,
    record_notification_noise,
    release_notification_noise,
)
from src.report_language import (
    format_strategy_skill_items,
    get_localized_stock_name,
    get_report_labels,
    get_signal_level,
    get_chip_unavailable_reason,
    is_chip_structure_unavailable,
    localize_chip_health,
    localize_conflict_severity,
    localize_consensus_level,
    localize_strategy_signal,
    localize_strategy_skill,
    localize_strategy_conflict_description,
    localize_strategy_synthesis_summary,
    localize_trend_prediction,
    normalize_report_language,
    normalize_strategy_synthesis_payload,
    strategy_invalid_opinion_count,
)
from src.schemas.decision_action import (
    display_action_fields_for_result,
    display_decision_type_for_result,
    display_operation_advice_for_result,
)
from src.schemas.request_context import AnalysisRequestContext
from src.utils.sanitize import (
    log_safe_exception,
    sanitize_diagnostic_text,
    sanitize_exception_chain,
)
from src.utils.data_processing import (
    signal_attribution_has_content,
    signal_attribution_weight_items,
    normalize_model_used,
)
from src.notification_sender import (
    AstrbotSender,
    CustomWebhookSender,
    DingtalkSender,
    DiscordSender,
    EmailSender,
    FeishuSender,
    GotifySender,
    NtfySender,
    PushoverSender,
    PushplusSender,
    Serverchan3Sender,
    SlackSender,
    TelegramSender,
    WechatSender,
    WECHAT_IMAGE_MAX_BYTES,
    resolve_gotify_message_endpoint,
    resolve_ntfy_endpoint,
)
from src.plugins.notification_channels import (
    NotificationAdapterResult as _NotificationAdapterResult,
    NotificationChannelSnapshot as _NotificationChannelSnapshot,
    NotificationRequest as _NotificationRequest,
    available_notification_channel_snapshot as _available_notification_channel_snapshot,
)

logger = logging.getLogger(__name__)


def _get_notification_channel_registry():
    """Resolve the registry owned by the installed application root."""

    from src.application_services import get_application_services

    return get_application_services().notification_channel_registry


def _normalize_notification_adapter_error_code(
    value: Any,
    *,
    success: bool,
) -> Optional[str]:
    """Map plugin-provided error codes into the bounded core attempt format."""

    if success:
        return None
    candidate = sanitize_diagnostic_text(value, max_length=120)
    if (
        candidate
        and candidate.isascii()
        and candidate == candidate.lower()
        and candidate[0].isalnum()
        and all(character.isalnum() or character in "._-" for character in candidate)
    ):
        return candidate
    return "send_failed"


def _safe_float(value: Any) -> Optional[float]:
    """Best-effort float conversion; handles `"3.2%"` and `"1,234"` shapes."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    text = str(value).strip().replace(",", "")
    if text.endswith("%"):
        text = text[:-1].strip()
    if not text:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _append_strategy_synthesis_block(lines: List[str], strategy_synthesis: Any, labels: Dict[str, str], report_language: str) -> None:
    """Append the full localized strategy synthesis block when present."""
    strategy_synthesis = normalize_strategy_synthesis_payload(strategy_synthesis)
    if not strategy_synthesis:
        return
    confidence = strategy_synthesis.get("confidence")
    confidence_text = f"{confidence:.0%}" if isinstance(confidence, (int, float)) else "N/A"
    lines.extend([
        f"### 🧩 {labels['strategy_synthesis_heading']}",
        "",
        (
            f"- {labels['strategy_final_signal_label']}: "
            f"{localize_strategy_signal(strategy_synthesis.get('final_signal', 'N/A'), report_language)} | "
            f"{labels['strategy_consensus_level_label']}: "
            f"{localize_consensus_level(strategy_synthesis.get('consensus_level', 'N/A'), report_language)} | "
            f"{labels['strategy_conflict_label']}: "
            f"{localize_conflict_severity(strategy_synthesis.get('conflict_severity', 'none'), report_language)} "
            f"({strategy_synthesis.get('conflict_count', 0)}) | "
            f"{labels['strategy_confidence_label']}: {confidence_text}"
        ),
    ])
    summary = localize_strategy_synthesis_summary(strategy_synthesis, report_language)
    if summary:
        lines.append(f"- {labels['strategy_summary_label']}: {summary}")
    lines.append(
        f"- {labels['strategy_supporting_skills_label']}: "
        f"{format_strategy_skill_items(strategy_synthesis.get('supporting_skills'), report_language)}"
    )
    lines.append(
        f"- {labels['strategy_opposing_skills_label']}: "
        f"{format_strategy_skill_items(strategy_synthesis.get('opposing_skills'), report_language)}"
    )
    invalid_opinion_count = strategy_invalid_opinion_count(strategy_synthesis)
    if invalid_opinion_count:
        invalid_label = labels.get("strategy_invalid_opinions_label", "")
        if invalid_label:
            lines.append(f"- {invalid_label.format(count=invalid_opinion_count)}")
    for conflict in (strategy_synthesis.get("conflicts") or [])[:3]:
        if isinstance(conflict, dict) and conflict.get("conflict_type"):
            participants = conflict.get("participants") or []
            participant_text = "、".join(localize_strategy_skill(participant, report_language) for participant in participants)
            suffix = f"（{participant_text}）" if participant_text else ""
            lines.append(
                f"- {localize_conflict_severity(conflict.get('severity', 'medium'), report_language)}: "
                f"{localize_strategy_conflict_description(conflict.get('conflict_type'), report_language)}{suffix}"
            )
    lines.append("")


if TYPE_CHECKING:
    from src.analyzer import AnalysisResult


# Preserve the legacy module namespace and provide the global lookup surface
# used by descriptors rebound from the private source containers.
_NOTIFICATION_COMPAT_EXPORTS = (
    time,
    datetime,
    Config,
    ReportType,
    format_public_market_status_line,
    format_public_phase_pack_excerpt,
    get_notification_route_config,
    split_notification_route_channels,
    is_feishu_static_configured,
    NotificationNoiseDecision,
    evaluate_notification_noise,
    record_notification_noise,
    release_notification_noise,
    get_chip_unavailable_reason,
    is_chip_structure_unavailable,
    localize_chip_health,
    localize_trend_prediction,
    display_decision_type_for_result,
    log_safe_exception,
    sanitize_diagnostic_text,
    sanitize_exception_chain,
    signal_attribution_has_content,
    signal_attribution_weight_items,
    normalize_model_used,
    WECHAT_IMAGE_MAX_BYTES,
    resolve_gotify_message_endpoint,
    resolve_ntfy_endpoint,
)


class NotificationChannel(Enum):
    """通知渠道类型"""
    WECHAT = "wechat"      # WeCom
    DINGTALK = "dingtalk"
    FEISHU = "feishu"      # Feishu
    TELEGRAM = "telegram"  # Telegram
    EMAIL = "email"        # Email
    PUSHOVER = "pushover"  # Pushover (mobile/desktop push)
    NTFY = "ntfy"          # ntfy
    GOTIFY = "gotify"      # Gotify
    PUSHPLUS = "pushplus"  # PushPlus (domestic push service)
    SERVERCHAN3 = "serverchan3"  # ServerChan3 (mobile push service)
    CUSTOM = "custom"      # Custom Webhook
    DISCORD = "discord"    # Discord Bot (Bot)
    SLACK = "slack"        # Slack
    ASTRBOT = "astrbot"
    UNKNOWN = "unknown"    # Unknown.


@dataclass
class ChannelAttemptResult:
    """One static notification channel send attempt."""

    channel: str
    success: bool
    error_code: Optional[str] = None
    retryable: bool = False
    latency_ms: Optional[int] = None
    diagnostics: Optional[str] = None


@dataclass
class NotificationDispatchResult:
    """Structured result for notification dispatch diagnostics."""

    dispatched: bool
    success: bool
    status: str
    channel_results: List[ChannelAttemptResult] = field(default_factory=list)
    message: Optional[str] = None


class ChannelDetector:
    """
    渠道检测器 - 简化版

    根据配置直接判断渠道类型（不再需要 URL 解析）
    """

    @staticmethod
    def get_channel_name(channel: NotificationChannel) -> str:
        """获取渠道中文名称"""
        names = {
            NotificationChannel.WECHAT: "企业微信",
            NotificationChannel.FEISHU: "飞书",
            NotificationChannel.DINGTALK: "钉钉",
            NotificationChannel.TELEGRAM: "Telegram",
            NotificationChannel.EMAIL: "邮件",
            NotificationChannel.PUSHOVER: "Pushover",
            NotificationChannel.NTFY: "ntfy",
            NotificationChannel.GOTIFY: "Gotify",
            NotificationChannel.PUSHPLUS: "PushPlus",
            NotificationChannel.SERVERCHAN3: "Server酱3",
            NotificationChannel.CUSTOM: "自定义Webhook",
            NotificationChannel.DISCORD: "Discord机器人",
            NotificationChannel.SLACK: "Slack",
            NotificationChannel.ASTRBOT: "ASTRBOT机器人",
            NotificationChannel.UNKNOWN: "未知渠道",
        }
        return names.get(channel, "未知渠道")


class NotificationService(
    AstrbotSender,
    CustomWebhookSender,
    DingtalkSender,
    DiscordSender,
    EmailSender,
    FeishuSender,
    GotifySender,
    NtfySender,
    PushoverSender,
    PushplusSender,
    Serverchan3Sender,
    SlackSender,
    TelegramSender,
    WechatSender
):
    """
    通知服务

    职责：
    1. 生成 Markdown 格式的分析日报
    2. 向所有已配置的渠道推送消息（多渠道并发）
    3. 支持本地保存日报

    支持的渠道：
    - 企业微信 Webhook
    - 飞书 Webhook
    - Telegram Bot
    - 邮件 SMTP
    - Pushover（手机/桌面推送）

    注意：所有已配置的渠道都会收到推送
    """

    def __init__(self, request_context: Optional[AnalysisRequestContext] = None):
        """Initialize configured channels and an optional contextual reply route."""
        config = get_config()
        self._config = config
        self._request_context = request_context
        self._context_channels: List[str] = []
        self._notification_channel_registry = _get_notification_channel_registry()

        # Markdown Convert to image(Issue #289)
        self._markdown_to_image_channels = set(
            getattr(config, 'markdown_to_image_channels', []) or []
        )
        self._markdown_to_image_max_chars = getattr(
            config, 'markdown_to_image_max_chars', 15000
        )

        # Only analyze the result summary (Issue #262): true only pushes summaries, without individual stock details
        self._report_summary_only = getattr(config, 'report_summary_only', False)
        self._report_show_llm_model = getattr(config, 'report_show_llm_model', True)
        self._history_compare_cache: Dict[Tuple[int, str, Tuple[Tuple[str, str], ...]], Dict[str, List[Dict[str, Any]]]] = {}

        # Initialize all channels
        AstrbotSender.__init__(self, config)
        CustomWebhookSender.__init__(self, config)
        DiscordSender.__init__(self, config)
        EmailSender.__init__(self, config)
        FeishuSender.__init__(self, config)
        GotifySender.__init__(self, config)
        NtfySender.__init__(self, config)
        PushoverSender.__init__(self, config)
        PushplusSender.__init__(self, config)
        Serverchan3Sender.__init__(self, config)
        SlackSender.__init__(self, config)
        TelegramSender.__init__(self, config)
        WechatSender.__init__(self, config)
        DingtalkSender.__init__(self, config)

        # Detect all configured channels
        self._available_channels = self._detect_all_channels()
        plugin_channels = self._notification_channel_registry.snapshot()
        if self._extract_dingtalk_session_webhook() is not None:
            self._context_channels.append("钉钉会话")
        if self._extract_feishu_reply_info() is not None:
            self._context_channels.append("飞书会话")

        if (
            not self._available_channels
            and not self._context_channels
            and not plugin_channels
        ):
            logger.warning("未配置有效的通知渠道，将不发送推送通知")
        else:
            channel_names = [ChannelDetector.get_channel_name(ch) for ch in self._available_channels]
            channel_names.extend(self._context_channels)
            channel_names.extend(channel.display_name for channel in plugin_channels)
            logger.info(f"已配置 {len(channel_names)} 个通知渠道：{', '.join(channel_names)}")

    # Reserve the legacy class namespace order. Facade binding replaces each
    # method placeholder in place after the class has been created.
    _normalize_report_type = None
    _get_report_language = None
    _get_labels = None
    _get_display_name = None
    _get_history_compare_context = None
    generate_aggregate_report = None
    _collect_models_used = None
    _public_phase_pack_excerpt = None
    _public_market_status_line = None
    _append_market_status_line = None
    _should_show_llm_model = None
    detect_configured_channels = None
    _detect_all_channels = None
    is_available = None
    get_available_channels = None
    get_channels_for_route = None
    get_channel_names = None
    evaluate_noise_control = None
    record_noise_control = None
    release_noise_control = None
    _has_context_channel = None
    _extract_telegram_context_chat_id = None
    should_broadcast_static_channels = None
    _extract_dingtalk_session_webhook = None
    _extract_feishu_reply_info = None
    send_to_context = None
    _send_via_source_context = None
    _send_feishu_stream_reply = None
    _send_feishu_stream_chunked = None
    generate_daily_report = None
    _escape_md = None
    _clean_sniper_value = None
    _phase_decision_list = None
    _phase_decision_has_content = None
    _append_phase_decision_block = None
    _get_display_operation_advice = None
    _count_display_decisions = None
    _get_signal_level = None
    generate_dashboard_report = None
    generate_wechat_dashboard = None
    generate_wechat_summary = None
    generate_brief_report = None
    generate_single_stock_report = None

    # Display name mapping for realtime data sources
    _SOURCE_DISPLAY_NAMES = {
        "tencent": {"zh": "腾讯财经", "en": "Tencent Finance"},
        "akshare_em": {"zh": "东方财富", "en": "Eastmoney"},
        "akshare_sina": {"zh": "新浪财经", "en": "Sina Finance"},
        "akshare_qq": {"zh": "腾讯财经", "en": "Tencent Finance"},
        "efinance": {"zh": "东方财富(efinance)", "en": "Eastmoney (efinance)"},
        "tushare": {"zh": "Tushare Pro", "en": "Tushare Pro"},
        "sina": {"zh": "新浪财经", "en": "Sina Finance"},
        "stooq": {"zh": "Stooq", "en": "Stooq"},
        "longbridge": {"zh": "长桥", "en": "Longbridge"},
        "fallback": {"zh": "降级兜底", "en": "Fallback"},
    }
    _get_source_display_name = None
    _append_market_snapshot = None
    _CURRENCY_SUFFIX = {
        "USD": "美元",
        "HKD": "港元",
        "CNY": "元",
        "RMB": "元",
        "CNH": "元",
        "TWD": "新台币",  # Taiwan stocks (TWSE/TPEx) are priced in New Taiwan Dollars to avoid confusion with A-shares "yuan" (Renminbi)
    }
    _format_amount_cn = None
    _format_percent = None
    _format_per_share = None
    _format_text = None
    _get_fundamental_blocks = None
    _append_fundamental_blocks = None
    _append_financial_summary = None
    _append_shareholder_return = None
    _format_net_shares = None
    _append_institutional_flow = None
    _append_related_boards = None
    _should_use_image_for_channel = None
    _sanitize_notification_diagnostics = None
    _send_to_static_channel = None
    send_with_results = None
    send = None
    save_report_to_file = None
    save_and_send_feishu_file = None


# Bind after the facade class exists so every moved method keeps the legacy
# module globals, descriptor metadata, patch seams, and method order.
from src.notification_parts import dispatch as _notification_dispatch  # noqa: E402
from src.notification_parts import rendering as _notification_rendering  # noqa: E402
from src.notification_parts import report_setup as _notification_report_setup  # noqa: E402
from src.notification_parts import routing as _notification_routing  # noqa: E402

_ReportSetupMethods = _notification_report_setup._ReportSetupMethods
_RoutingMethods = _notification_routing._RoutingMethods
_RenderingMethods = _notification_rendering._RenderingMethods
_DispatchMethods = _notification_dispatch._DispatchMethods

_REPORT_SETUP_METHOD_NAMES = _bind_facade_methods(
    NotificationService, _ReportSetupMethods, globals()
)
_ROUTING_METHOD_NAMES = _bind_facade_methods(
    NotificationService, _RoutingMethods, globals()
)
_RENDERING_METHOD_NAMES = _bind_facade_methods(
    NotificationService, _RenderingMethods, globals()
)
_DISPATCH_METHOD_NAMES = _bind_facade_methods(
    NotificationService, _DispatchMethods, globals()
)


class NotificationBuilder:
    """
    通知消息构建器

    提供便捷的消息构建方法
    """

    @staticmethod
    def build_simple_alert(
        title: str,
        content: str,
        alert_type: str = "info"
    ) -> str:
        """
        构建简单的提醒消息

        Args:
            title: 标题
            content: 内容
            alert_type: 类型（info, warning, error, success）
        """
        emoji_map = {
            "info": "ℹ️",
            "warning": "⚠️",
            "error": "❌",
            "success": "✅",
        }
        emoji = emoji_map.get(alert_type, "📢")

        return f"{emoji} **{title}**\n\n{content}"

    @staticmethod
    def build_stock_summary(results: List[AnalysisResult]) -> str:
        """
        构建股票摘要（简短版）

        适用于快速通知
        """
        report_language = normalize_report_language(
            next((getattr(result, "report_language", None) for result in results if getattr(result, "report_language", None)), None)
        )
        labels = get_report_labels(report_language)
        lines = [f"📊 **{labels['summary_heading']}**", ""]

        for r in sorted(results, key=lambda x: x.sentiment_score, reverse=True):
            display_action = display_action_fields_for_result(
                r,
                report_language=report_language,
            )["action"]
            signal_action = {
                "buy": "buy",
                "add": "buy",
                "hold": "hold",
                "reduce": "reduce",
                "sell": "sell",
                "watch": "watch",
                "avoid": "hold",
                "alert": "sell",
            }.get(display_action)
            display_advice = display_operation_advice_for_result(
                r,
                report_language=report_language,
            )
            signal_text, emoji, _ = get_signal_level(
                signal_action or display_advice,
                r.sentiment_score,
                report_language,
            )
            name = get_localized_stock_name(r.name, r.code, report_language)
            lines.append(
                f"{emoji} {name}({r.code}): {display_advice} | "
                f"{labels['score_label']} {r.sentiment_score}"
            )

        return "\n".join(lines)


# Convenient function
def get_notification_service() -> NotificationService:
    """获取通知服务实例"""
    return NotificationService()


def send_daily_report(results: List[AnalysisResult]) -> bool:
    """
    发送每日报告的快捷方式

    自动识别渠道并推送
    """
    service = get_notification_service()

    # Generate a report.
    report = service.generate_daily_report(results)

    # Save locally
    service.save_report_to_file(report)

    # Push to configured channels (automatically identified)
    return service.send(report)


if __name__ == "__main__":
    # Test code
    logging.basicConfig(level=logging.DEBUG)
    from src.analyzer import AnalysisResult

    # Simulate analysis results
    test_results = [
        AnalysisResult(
            code='600519',
            name='贵州茅台',
            sentiment_score=75,
            trend_prediction='看多',
            analysis_summary='技术面强势，消息面利好',
            operation_advice='买入',
            technical_analysis='放量突破 MA20，MACD 金叉',
            news_summary='公司发布分红公告，业绩超预期',
        ),
        AnalysisResult(
            code='000001',
            name='平安银行',
            sentiment_score=45,
            trend_prediction='震荡',
            analysis_summary='横盘整理，等待方向',
            operation_advice='持有',
            technical_analysis='均线粘合，成交量萎缩',
            news_summary='近期无重大消息',
        ),
        AnalysisResult(
            code='300750',
            name='宁德时代',
            sentiment_score=35,
            trend_prediction='看空',
            analysis_summary='技术面走弱，注意风险',
            operation_advice='卖出',
            technical_analysis='跌破 MA10 支撑，量能不足',
            news_summary='行业竞争加剧，毛利率承压',
        ),
    ]

    service = NotificationService()

    # Displays detected channels
    print("=== 通知渠道检测 ===")
    print(f"当前渠道: {service.get_channel_names()}")
    print(f"渠道列表: {service.get_available_channels()}")
    print(f"服务可用: {service.is_available()}")

    # Generate daily reports
    print("\n=== 生成日报测试 ===")
    report = service.generate_daily_report(test_results)
    print(report)

    # Save to file
    print("\n=== 保存日报 ===")
    filepath = service.save_report_to_file(report)
    print(f"保存成功: {filepath}")

    # Push test
    if service.is_available():
        print(f"\n=== 推送测试（{service.get_channel_names()}）===")
        success = service.send(report)
        print(f"推送结果: {'成功' if success else '失败'}")
    else:
        print("\n通知渠道未配置，跳过推送测试")
