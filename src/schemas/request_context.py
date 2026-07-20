# -*- coding: utf-8 -*-
"""Neutral request and contextual reply contracts for application services."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional, Tuple

from src.notification_contracts import is_dingtalk_session_webhook_url


ReplyTargetKind = Literal["dingtalk", "feishu", "telegram"]
_REPLY_TARGET_KINDS = frozenset(("dingtalk", "feishu", "telegram"))


@dataclass(frozen=True)
class NotificationReplyTarget:
    """One ephemeral conversation target for replying to a triggering request."""

    kind: ReplyTargetKind
    address: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.kind, str) or self.kind not in _REPLY_TARGET_KINDS:
            raise ValueError(f"Unsupported notification reply target: {self.kind}")
        if not isinstance(self.address, str):
            raise TypeError("Notification reply target address must be a string")
        if not self.address.strip():
            raise ValueError("Notification reply target address must not be blank")
        if self.kind == "dingtalk" and not is_dingtalk_session_webhook_url(self.address):
            raise ValueError("DingTalk reply target must use the official session endpoint")


@dataclass(frozen=True)
class AnalysisRequestContext:
    """Immutable requester provenance and reply targets used by the core flow."""

    requester_platform: str = ""
    requester_user_id: str = ""
    requester_user_name: str = ""
    requester_chat_id: str = ""
    requester_message_id: str = ""
    requester_query: str = ""
    reply_targets: Tuple[NotificationReplyTarget, ...] = ()
    contextual_reply_only: bool = False

    def __post_init__(self) -> None:
        requester_fields = (
            "requester_platform",
            "requester_user_id",
            "requester_user_name",
            "requester_chat_id",
            "requester_message_id",
            "requester_query",
        )
        if any(not isinstance(getattr(self, name), str) for name in requester_fields):
            raise TypeError("Requester provenance fields must be strings")
        if not isinstance(self.contextual_reply_only, bool):
            raise TypeError("contextual_reply_only must be a bool")
        targets = tuple(self.reply_targets)
        if any(not isinstance(target, NotificationReplyTarget) for target in targets):
            raise TypeError("reply_targets must contain NotificationReplyTarget values")
        object.__setattr__(self, "reply_targets", targets)
        if targets:
            object.__setattr__(self, "contextual_reply_only", True)

    def reply_address(self, kind: ReplyTargetKind) -> Optional[str]:
        """Return the first address for a contextual notification channel."""
        for target in self.reply_targets:
            if target.kind == kind:
                return target.address
        return None
