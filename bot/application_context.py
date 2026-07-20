# -*- coding: utf-8 -*-
"""Map Bot boundary messages into neutral application request contracts."""

from __future__ import annotations

from typing import Any, Dict, Optional

from bot.models import BotMessage
from src.notification_contracts import is_dingtalk_session_webhook_url
from src.schemas.request_context import AnalysisRequestContext, NotificationReplyTarget


def _string_value(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "value"):
        value = value.value
    return str(value)


def _dingtalk_session_webhook_candidate(raw_data: Dict[str, Any]) -> Any:
    candidate = (
        raw_data.get("_session_webhook")
        or raw_data.get("sessionWebhook")
        or raw_data.get("session_webhook")
        or raw_data.get("session_webhook_url")
    )
    if not candidate and isinstance(raw_data.get("headers"), dict):
        candidate = raw_data["headers"].get("sessionWebhook")
    return candidate


def _telegram_chat_id(message: BotMessage, raw_data: Dict[str, Any]) -> Optional[str]:
    raw_message = raw_data.get("message")
    raw_chat = raw_message.get("chat") if isinstance(raw_message, dict) else None
    nested_chat_id = raw_chat.get("id") if isinstance(raw_chat, dict) else None
    for candidate in (message.chat_id, raw_data.get("chat_id"), nested_chat_id):
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
        if candidate is not None and not isinstance(candidate, str):
            candidate_text = str(candidate).strip()
            if candidate_text:
                return candidate_text
    return None


def to_analysis_request_context(message: BotMessage) -> AnalysisRequestContext:
    """Snapshot the core-relevant fields from a mutable boundary message."""
    raw_data = message.raw_data if isinstance(message.raw_data, dict) else {}
    platform = _string_value(message.platform).lower()
    reply_targets = []
    dingtalk_candidate = _dingtalk_session_webhook_candidate(raw_data)
    feishu_chat_id = _string_value(message.chat_id).strip()
    telegram_chat_id = None

    if platform == "dingtalk":
        if is_dingtalk_session_webhook_url(dingtalk_candidate):
            reply_targets.append(NotificationReplyTarget("dingtalk", dingtalk_candidate))

    if platform == "feishu" and feishu_chat_id:
        reply_targets.append(NotificationReplyTarget("feishu", feishu_chat_id))

    if platform == "telegram":
        telegram_chat_id = _telegram_chat_id(message, raw_data)
        if telegram_chat_id:
            reply_targets.append(NotificationReplyTarget("telegram", telegram_chat_id))

    return AnalysisRequestContext(
        requester_platform=platform,
        requester_user_id=_string_value(message.user_id),
        requester_user_name=_string_value(message.user_name),
        requester_chat_id=_string_value(message.chat_id),
        requester_message_id=_string_value(message.message_id),
        requester_query=_string_value(message.content),
        reply_targets=tuple(reply_targets),
        # Preserve reply-only intent even when an untrusted address is rejected.
        contextual_reply_only=(
            bool(dingtalk_candidate)
            or (platform == "feishu" and bool(message.chat_id))
            or telegram_chat_id is not None
        ),
    )
