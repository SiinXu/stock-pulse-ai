"""Routing methods for the public notification facade."""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from src.notification import (
        ChannelDetector,
        Config,
        NotificationChannel,
        NotificationNoiseDecision,
        evaluate_notification_noise,
        get_notification_route_config,
        is_feishu_static_configured,
        log_safe_exception,
        logger,
        record_notification_noise,
        release_notification_noise,
        resolve_gotify_message_endpoint,
        resolve_ntfy_endpoint,
        split_notification_route_channels,
    )


class _RoutingMethods:
    @staticmethod
    def detect_configured_channels(config: Config) -> List[NotificationChannel]:
        """
        Detect statically configured notification channels from Config.

        This intentionally mirrors sender availability without instantiating
        sender objects, so diagnostics and runtime use the same channel truth.
        Runtime-only context channels are handled by instance methods.
        """
        channels = []

        if getattr(config, "wechat_webhook_url", None):
            channels.append(NotificationChannel.WECHAT)
        if getattr(config, "dingtalk_webhook_url", None):
            channels.append(NotificationChannel.DINGTALK)

        if is_feishu_static_configured(config):
            channels.append(NotificationChannel.FEISHU)

        if (
            getattr(config, "telegram_bot_token", None)
            and getattr(config, "telegram_chat_id", None)
        ):
            channels.append(NotificationChannel.TELEGRAM)

        if getattr(config, "email_sender", None) and getattr(config, "email_password", None):
            channels.append(NotificationChannel.EMAIL)

        if (
            getattr(config, "pushover_user_key", None)
            and getattr(config, "pushover_api_token", None)
        ):
            channels.append(NotificationChannel.PUSHOVER)

        ntfy_server_url, ntfy_topic = resolve_ntfy_endpoint(getattr(config, "ntfy_url", None))
        if ntfy_server_url and ntfy_topic:
            channels.append(NotificationChannel.NTFY)

        gotify_endpoint = resolve_gotify_message_endpoint(getattr(config, "gotify_url", None))
        if gotify_endpoint and (getattr(config, "gotify_token", None) or "").strip():
            channels.append(NotificationChannel.GOTIFY)

        if getattr(config, "pushplus_token", None):
            channels.append(NotificationChannel.PUSHPLUS)

        if getattr(config, "serverchan3_sendkey", None):
            channels.append(NotificationChannel.SERVERCHAN3)

        if getattr(config, "custom_webhook_urls", None):
            channels.append(NotificationChannel.CUSTOM)

        if (
            getattr(config, "discord_webhook_url", None)
            or (
                getattr(config, "discord_bot_token", None)
                and getattr(config, "discord_main_channel_id", None)
            )
        ):
            channels.append(NotificationChannel.DISCORD)

        if (
            getattr(config, "slack_webhook_url", None)
            or (
                getattr(config, "slack_bot_token", None)
                and getattr(config, "slack_channel_id", None)
            )
        ):
            channels.append(NotificationChannel.SLACK)

        if getattr(config, "astrbot_url", None):
            channels.append(NotificationChannel.ASTRBOT)

        return channels

    def _detect_all_channels(self) -> List[NotificationChannel]:
        """
        检测所有已配置的渠道

        Returns:
            已配置的渠道列表
        """
        return self.detect_configured_channels(self._config)

    def is_available(self) -> bool:
        """检查通知服务是否可用（至少有一个渠道或上下文渠道）"""
        return len(self._available_channels) > 0 or self._has_context_channel()

    def get_available_channels(self) -> List[NotificationChannel]:
        """获取所有已配置的渠道"""
        return self._available_channels

    def get_channels_for_route(
        self,
        route_type: Optional[str],
        channels: Optional[List[NotificationChannel]] = None,
    ) -> List[NotificationChannel]:
        """Return channels allowed for a route type.

        ``route_type=None`` keeps the legacy behavior and returns all supplied
        static channels. Empty route config also keeps all supplied channels.
        Non-empty route config that matches no enabled channel returns an empty
        list.
        """
        target_channels = list(channels if channels is not None else self._available_channels)
        if route_type is None:
            return target_channels

        route_config = get_notification_route_config(route_type)
        if route_config is None:
            logger.warning("未知通知路由类型 %s，沿用全部已配置渠道", route_type)
            return target_channels

        configured_route_channels = getattr(self._config, route_config["config_attr"], []) or []
        if not configured_route_channels:
            return target_channels

        valid_channels, invalid_channels = split_notification_route_channels(configured_route_channels)
        if invalid_channels:
            logger.warning(
                "%s 包含未知通知渠道，将忽略: %s",
                route_config["env_key"],
                ", ".join(invalid_channels),
            )

        allowed = set(valid_channels)
        return [channel for channel in target_channels if channel.value in allowed]

    def get_channel_names(self) -> str:
        """获取所有已配置渠道的名称"""
        names = [ChannelDetector.get_channel_name(ch) for ch in self._available_channels]
        if self._has_context_channel():
            names.append("钉钉会话")
        return ', '.join(names)

    def evaluate_noise_control(
        self,
        content: str,
        *,
        route_type: Optional[str] = None,
        severity: Optional[str] = None,
        dedup_key: Optional[str] = None,
        cooldown_key: Optional[str] = None,
    ) -> NotificationNoiseDecision:
        """Evaluate static-channel notification noise controls."""
        return evaluate_notification_noise(
            self._config,
            content=content,
            route_type=route_type,
            severity=severity,
            dedup_key=dedup_key,
            cooldown_key=cooldown_key,
        )

    @staticmethod
    def record_noise_control(decision: NotificationNoiseDecision) -> None:
        """Record static-channel notification noise state after a successful send."""
        record_notification_noise(decision)

    @staticmethod
    def release_noise_control(decision: NotificationNoiseDecision) -> None:
        """Release static-channel in-flight noise reservation after send failure."""
        release_notification_noise(decision)

    # ===== Context channel =====
    def _has_context_channel(self) -> bool:
        """判断是否存在基于消息上下文的临时渠道（如钉钉会话、飞书会话）"""
        return (
            self._extract_dingtalk_session_webhook() is not None
            or self._extract_feishu_reply_info() is not None
            or self._extract_telegram_context_chat_id() is not None
        )

    def _extract_telegram_context_chat_id(self) -> Optional[str]:
        """从来源消息中提取 Telegram 上下文 chat_id（用于异步回复）。"""
        if self._request_context is None:
            return None
        return self._request_context.reply_address("telegram")

    def should_broadcast_static_channels(self) -> bool:
        """Whether static notification channels should receive this dispatch."""
        return not (
            self._request_context is not None
            and self._request_context.contextual_reply_only
        )

    def _extract_dingtalk_session_webhook(self) -> Optional[str]:
        """从来源消息中提取钉钉会话 Webhook（用于 Stream 模式回复）"""
        if self._request_context is None:
            return None
        return self._request_context.reply_address("dingtalk")

    def _extract_feishu_reply_info(self) -> Optional[Dict[str, str]]:
        """
        从来源消息中提取飞书回复信息（用于 Stream 模式回复）

        Returns:
            包含 chat_id 的字典，或 None
        """
        if self._request_context is None:
            return None
        chat_id = self._request_context.reply_address("feishu")
        if not chat_id:
            return None
        return {"chat_id": chat_id}

    def send_to_context(self, content: str) -> bool:
        """
        向基于消息上下文的渠道发送消息（例如钉钉 Stream 会话）

        Args:
            content: Markdown 格式内容
        """
        return self._send_via_source_context(content)

    def _send_via_source_context(self, content: str) -> bool:
        """
        使用消息上下文（如钉钉/飞书会话）发送一份报告

        主要用于从机器人 Stream 模式触发的任务，确保结果能回到触发的会话。
        """
        success = False

        # Attempt to connect to a DingTalk session
        session_webhook = self._extract_dingtalk_session_webhook()
        if session_webhook:
            try:
                if self._send_dingtalk_session_chunked(session_webhook, content, max_bytes=20000):
                    logger.info("已通过钉钉会话（Stream）推送报告")
                    success = True
                else:
                    logger.error("钉钉会话（Stream）推送失败")
            except Exception as exc:  # broad-exception: fallback_recorded - keep other context channels running
                log_safe_exception(
                    logger,
                    "DingTalk Stream session delivery failed",
                    exc,
                    error_code="dingtalk_stream_session_delivery_failed",
                )

        # Attempt to connect to a Feishu session
        feishu_info = self._extract_feishu_reply_info()
        if feishu_info:
            try:
                if self._send_feishu_stream_reply(feishu_info["chat_id"], content):
                    logger.info("已通过飞书会话（Stream）推送报告")
                    success = True
                else:
                    logger.error("飞书会话（Stream）推送失败")
            except Exception as exc:  # broad-exception: fallback_recorded - keep other context channels running
                log_safe_exception(
                    logger,
                    "Feishu Stream session delivery failed",
                    exc,
                    error_code="feishu_stream_session_delivery_failed",
                )

        # Try Telegram conversation context (respond based on chat_id source)
        telegram_chat_id = self._extract_telegram_context_chat_id()
        if telegram_chat_id:
            try:
                if self.send_to_telegram(content, chat_id=telegram_chat_id):
                    logger.info("已通过 Telegram 上下文会话推送报告")
                    success = True
                else:
                    logger.error("Telegram 上下文会话推送失败")
            except Exception as exc:  # broad-exception: fallback_recorded - keep other context channels running
                log_safe_exception(
                    logger,
                    "Telegram context session delivery failed",
                    exc,
                    error_code="telegram_context_session_delivery_failed",
                )

        return success

    def _send_feishu_stream_reply(self, chat_id: str, content: str) -> bool:
        """
        通过飞书 Stream 模式发送消息到指定会话

        Args:
            chat_id: 飞书会话 ID
            content: 消息内容

        Returns:
            是否发送成功
        """
        try:
            from bot.platforms.feishu_stream import FeishuReplyClient, FEISHU_SDK_AVAILABLE
            if not FEISHU_SDK_AVAILABLE:
                logger.warning("飞书 SDK 不可用，无法发送 Stream 回复")
                return False

            from src.config import get_config
            config = get_config()

            app_id = getattr(config, 'feishu_app_id', None)
            app_secret = getattr(config, 'feishu_app_secret', None)

            if not app_id or not app_secret:
                logger.warning("飞书 APP_ID 或 APP_SECRET 未配置")
                return False

            # Create a reply client
            reply_client = FeishuReplyClient(app_id, app_secret)

            # Feishu text messages have length restrictions and need to be sent in batches
            max_bytes = getattr(config, 'feishu_max_bytes', 20000)
            content_bytes = len(content.encode('utf-8'))

            if content_bytes > max_bytes:
                return self._send_feishu_stream_chunked(reply_client, chat_id, content, max_bytes)

            return reply_client.send_to_chat(chat_id, content)

        except ImportError as exc:
            log_safe_exception(
                logger,
                "Feishu Stream module import failed",
                exc,
                error_code="feishu_stream_module_import_failed",
            )
            return False
        except Exception as exc:  # broad-exception: fallback_recorded - preserve the established failed-reply result
            log_safe_exception(
                logger,
                "Feishu Stream reply failed",
                exc,
                error_code="feishu_stream_reply_failed",
            )
            return False

    def _send_feishu_stream_chunked(
        self,
        reply_client,
        chat_id: str,
        content: str,
        max_bytes: int
    ) -> bool:
        """
        分批发送长消息到飞书（Stream 模式）

        Args:
            reply_client: FeishuReplyClient 实例
            chat_id: 飞书会话 ID
            content: 完整消息内容
            max_bytes: 单条消息最大字节数

        Returns:
            是否全部发送成功
        """
        import time

        def get_bytes(s: str) -> int:
            return len(s.encode('utf-8'))

        # Split by paragraphs or lines.
        if "\n---\n" in content:
            sections = content.split("\n---\n")
            separator = "\n---\n"
        elif "\n### " in content:
            parts = content.split("\n### ")
            sections = [parts[0]] + [f"### {p}" for p in parts[1:]]
            separator = "\n"
        else:
            # Split by lines.
            sections = content.split("\n")
            separator = "\n"

        chunks = []
        current_chunk = []
        current_bytes = 0
        separator_bytes = get_bytes(separator)

        for section in sections:
            section_bytes = get_bytes(section) + separator_bytes

            if current_bytes + section_bytes > max_bytes:
                if current_chunk:
                    chunks.append(separator.join(current_chunk))
                current_chunk = [section]
                current_bytes = section_bytes
            else:
                current_chunk.append(section)
                current_bytes += section_bytes

        if current_chunk:
            chunks.append(separator.join(current_chunk))

        # Send each chunk
        success = True
        for i, chunk in enumerate(chunks):
            if i > 0:
                time.sleep(0.5)  # Avoid making requests too quickly.

            if not reply_client.send_to_chat(chat_id, chunk):
                success = False
                logger.error(f"飞书 Stream 分块 {i+1}/{len(chunks)} 发送失败")

        return success
