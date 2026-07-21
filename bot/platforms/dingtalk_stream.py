# -*- coding: utf-8 -*-
"""
===================================
DingTalk Stream mode adapter
===================================

Use DingTalk official Stream SDK to access the robot, without public IP and Webhook configuration.

Advantages:
- No public IP or domain name required
- No Webhook URL configuration needed
- Receive messages via long-lived WebSocket connection
- Simpler integration method

Dependent:
pip install dingtalk-stream

DingTalk Stream SDK:
https://github.com/open-dingtalk/dingtalk-stream-sdk-python
"""

import logging
import inspect
import threading
from datetime import datetime
from typing import Optional, Callable, Any

from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)
DINGTALK_STREAM_PUBLIC_ERROR = "message_processing_failed"

# Attempt to import DingTalk Stream SDK
try:
    import dingtalk_stream
    from dingtalk_stream import AckMessage

    DINGTALK_STREAM_AVAILABLE = True
except ImportError:
    DINGTALK_STREAM_AVAILABLE = False
    logger.warning(
        "[DingTalk Stream] dingtalk-stream SDK is not installed; stream mode is unavailable"
    )
    logger.warning("[DingTalk Stream] Install it with: pip install dingtalk-stream")

from bot.models import BotMessage, BotResponse, ChatType


class DingtalkStreamHandler:
    """
    DingTalk Stream mode message processor

    Convert Stream SDK callbacks to a unified BotMessage format
    Will invoke the command dispatcher to handle.
    """

    def __init__(self, on_message: Callable[[BotMessage], Any]):
        """
        Args:
            on_message: message handler callback function, receives BotMessage returns BotResponse
        """
        self._on_message = on_message
        self._logger = logger

    def _log_incoming_message(self, message: BotMessage) -> None:
        content = message.raw_content or message.content or ""
        self._logger.info(
            "[DingTalk Stream] Incoming message: chat_type=%s content_length=%d",
            getattr(message.chat_type, "value", message.chat_type),
            len(content),
        )

    if DINGTALK_STREAM_AVAILABLE:
        class _ChatbotHandler(dingtalk_stream.ChatbotHandler):
            """Internal message processor"""

            def __init__(self, parent: 'DingtalkStreamHandler'):
                super().__init__()
                self._parent = parent
                self.logger = logger

            async def process(self, callback: dingtalk_stream.CallbackMessage):
                """Process received messages"""
                try:
                    # Parse message
                    incoming = dingtalk_stream.ChatbotMessage.from_dict(callback.data)

                    # Convert to Unified Format
                    bot_message = self._parent._parse_stream_message(incoming, callback.data)

                    if bot_message:
                        self._parent._log_incoming_message(bot_message)
                        # Call the message processing callback
                        response = self._parent._on_message(bot_message)
                        if inspect.isawaitable(response):
                            response = await response

                        # Send reply
                        if response and response.text:
                            # Construct @user prefix (in group chat scenarios, @username must be included in the text)
                            if response.at_user and incoming.sender_nick:
                                if response.markdown:
                                    self.reply_markdown(
                                        title="股票分析助手",
                                        text=f"@{incoming.sender_nick} " + response.text,
                                        incoming_message=incoming
                                    )
                                else:
                                    self.reply_text(response.text, incoming)

                    return AckMessage.STATUS_OK, 'OK'

                except Exception as exc:
                    log_safe_exception(
                        self.logger,
                        "[DingTalk Stream] Message processing failed",
                        exc,
                        error_code="bot_dingtalk_stream_message_failed",
                    )
                    return AckMessage.STATUS_SYSTEM_EXCEPTION, DINGTALK_STREAM_PUBLIC_ERROR

        def create_handler(self) -> '_ChatbotHandler':
            """Create processor instances required for SDK"""
            return self._ChatbotHandler(self)

    def _parse_stream_message(self, incoming: Any, raw_data: dict) -> Optional[BotMessage]:
        """
        Parse Stream messages into a unified format

        Args:
            incoming: ChatbotMessage object
            raw_data: raw callback data
        """
        try:
            raw_data = dict(raw_data or {})

            # Get message content
            raw_content = incoming.text.content if incoming.text else ''

            # Extracts command (excluding @robot)
            content = self._extract_command(raw_content)

            # Session type
            conversation_type = getattr(incoming, 'conversation_type', None)
            if conversation_type == '1':
                chat_type = ChatType.PRIVATE
            elif conversation_type == '2':
                chat_type = ChatType.GROUP
            else:
                chat_type = ChatType.UNKNOWN

            # Whether @ed the robot (messages received in Stream mode are usually @the robot)
            mentioned = True

            # Extracts sessionWebhook for asynchronous push notifications
            session_webhook = (
                    getattr(incoming, 'session_webhook', None)
                    or raw_data.get('sessionWebhook')
                    or raw_data.get('session_webhook')
            )
            if session_webhook:
                raw_data['_session_webhook'] = session_webhook

            return BotMessage(
                platform='dingtalk',
                message_id=getattr(incoming, 'msg_id', '') or '',
                user_id=getattr(incoming, 'sender_id', '') or '',
                user_name=getattr(incoming, 'sender_nick', '') or '',
                chat_id=getattr(incoming, 'conversation_id', '') or '',
                chat_type=chat_type,
                content=content,
                raw_content=raw_content,
                mentioned=mentioned,
                mentions=[],
                timestamp=datetime.now(),
                raw_data=raw_data,
            )

        except Exception as exc:
            log_safe_exception(
                logger,
                "[DingTalk Stream] Message parsing failed",
                exc,
                error_code="bot_dingtalk_stream_parse_failed",
            )
            return None

    def _extract_command(self, text: str) -> str:
        """Extracts command content (excluding @robot)"""
        import re
        text = re.sub(r'^@[\S]+\s*', '', text.strip())
        return text.strip()


class DingtalkStreamClient:
    """
    DingTalk Stream mode client

    Encapsulate the dingtalk-stream SDK, providing a simple startup interface.

    Usage:
        client = DingtalkStreamClient()
        client.start() # blocking execution

        # Or run in the background
        client.start_background()
    """

    def __init__(
            self,
            client_id: Optional[str] = None,
            client_secret: Optional[str] = None
    ):
        """
        Args:
            client_id: Apply AppKey(Read configuration if not passed in)
            client_secret: Apply AppSecret(No Pass, Read from Configuration)
        """
        if not DINGTALK_STREAM_AVAILABLE:
            raise ImportError(
                "dingtalk-stream SDK 未安装。\n"
                "请运行: pip install dingtalk-stream"
            )

        from src.config import get_config
        config = get_config()

        self._client_id = client_id or getattr(config, 'dingtalk_app_key', None)
        self._client_secret = client_secret or getattr(config, 'dingtalk_app_secret', None)

        if not self._client_id or not self._client_secret:
            raise ValueError(
                "钉钉 Stream 模式需要配置 DINGTALK_APP_KEY 和 DINGTALK_APP_SECRET"
            )

        self._client: Optional[dingtalk_stream.DingTalkStreamClient] = None
        self._background_thread: Optional[threading.Thread] = None
        self._running = False

    def _create_message_handler(self) -> Callable[[BotMessage], Any]:
        """Create message processing function"""

        async def handle_message(message: BotMessage) -> BotResponse:
            from bot.dispatcher import get_dispatcher
            dispatcher = get_dispatcher()
            return await dispatcher.dispatch_async(message)

        return handle_message

    def start(self) -> None:
        """
        Start Stream client (blocking)

        This method will block the current thread until the client stops.
        """
        logger.info("[DingTalk Stream] Starting client")

        # Create credentials
        credential = dingtalk_stream.Credential(
            self._client_id,
            self._client_secret
        )

        # Create a client
        self._client = dingtalk_stream.DingTalkStreamClient(credential)

        # Register message processor
        handler = DingtalkStreamHandler(self._create_message_handler())
        self._client.register_callback_handler(
            dingtalk_stream.chatbot.ChatbotMessage.TOPIC,
            handler.create_handler()
        )

        self._running = True
        logger.info("[DingTalk Stream] Client started and waiting for messages")

        # Block execution
        self._client.start_forever()

    def start_background(self) -> None:
        """
        Start Stream client (non-blocking) in a background thread.

        Suitable for scenarios where it runs concurrently with other services (such as WebUI).
        """
        if self._background_thread and self._background_thread.is_alive():
            logger.warning("[DingTalk Stream] Client is already running")
            return

        self._running = True
        self._background_thread = threading.Thread(
            target=self._run_in_background,
            daemon=True,
            name="DingtalkStreamClient"
        )
        self._background_thread.start()
        logger.info("[DingTalk Stream] Background client started")

    def _run_in_background(self) -> None:
        """Run in the background (handle exceptions and reconnect)."""
        import time

        while self._running:
            try:
                self.start()
            except Exception as exc:
                log_safe_exception(
                    logger,
                    "[DingTalk Stream] Client run failed",
                    exc,
                    error_code="bot_dingtalk_stream_run_failed",
                )
                if self._running:
                    logger.info("[DingTalk Stream] Reconnecting in 5 seconds")
                    time.sleep(5)

    def stop(self) -> None:
        """Stop client"""
        self._running = False
        logger.info("[DingTalk Stream] Client stopped")

    @property
    def is_running(self) -> bool:
        """Return whether the stream client is running."""
        return self._running


# Global client instance
_stream_client: Optional[DingtalkStreamClient] = None


def get_dingtalk_stream_client() -> Optional[DingtalkStreamClient]:
    """Get the global Stream client instance"""
    global _stream_client

    if _stream_client is None and DINGTALK_STREAM_AVAILABLE:
        try:
            _stream_client = DingtalkStreamClient()
        except (ImportError, ValueError) as exc:
            log_safe_exception(
                logger,
                "[DingTalk Stream] Client creation failed",
                exc,
                error_code="bot_dingtalk_stream_client_create_failed",
                level=logging.WARNING,
            )
            return None

    return _stream_client


def start_dingtalk_stream_background() -> bool:
    """
    Start DingTalk Stream client in the background.

    Returns:
        Did it start successfully?
    """
    client = get_dingtalk_stream_client()
    if client:
        client.start_background()
        return True
    return False
