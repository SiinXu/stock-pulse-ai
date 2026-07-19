# -*- coding: utf-8 -*-
"""Neutral request and contextual reply contracts for application services."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional, Tuple


ReplyTargetKind = Literal["dingtalk", "feishu", "telegram"]


@dataclass(frozen=True)
class NotificationReplyTarget:
    """One ephemeral conversation target for replying to a triggering request."""

    kind: ReplyTargetKind
    address: str = field(repr=False)


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

    def reply_address(self, kind: ReplyTargetKind) -> Optional[str]:
        """Return the first address for a contextual notification channel."""
        for target in self.reply_targets:
            if target.kind == kind:
                return target.address
        return None
