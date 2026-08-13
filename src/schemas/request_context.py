# -*- coding: utf-8 -*-
"""Neutral request and contextual reply contracts for application services.

Pydantic v2 service-boundary DTOs (Issue #549). Construction and validation
semantics match the former frozen dataclasses: same field names, same
TypeError/ValueError contracts, frozen instances, and reply-target forcing of
``contextual_reply_only``.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any, Literal, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from src.notification_contracts import is_dingtalk_session_webhook_url


ReplyTargetKind = Literal["dingtalk", "feishu", "telegram"]
_REPLY_TARGET_KINDS = frozenset(("dingtalk", "feishu", "telegram"))
_REQUESTER_FIELDS = (
    "requester_platform",
    "requester_user_id",
    "requester_user_name",
    "requester_chat_id",
    "requester_message_id",
    "requester_query",
)
_UNSET = object()


def _raise_frozen_instance(name: str, exc: ValidationError) -> None:
    """Map Pydantic frozen assignment errors to dataclass FrozenInstanceError."""
    if any(error.get("type") == "frozen_instance" for error in exc.errors()):
        raise FrozenInstanceError(f"cannot assign to field '{name}'") from None
    raise exc


class NotificationReplyTarget(BaseModel):
    """One ephemeral conversation target for replying to a triggering request."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: ReplyTargetKind
    address: str = Field(repr=False)

    def __init__(
        self,
        kind: Any = _UNSET,
        address: Any = _UNSET,
        **data: Any,
    ) -> None:
        # Compatibility shim only (not a general pattern): preserve former
        # dataclass positional construction NotificationReplyTarget("feishu", "chat-1").
        if kind is not _UNSET:
            if "kind" in data:
                raise TypeError("got multiple values for argument 'kind'")
            data["kind"] = kind
        if address is not _UNSET:
            if "address" in data:
                raise TypeError("got multiple values for argument 'address'")
            data["address"] = address
        super().__init__(**data)

    def __setattr__(self, name: str, value: Any) -> None:
        try:
            super().__setattr__(name, value)
        except ValidationError as exc:
            _raise_frozen_instance(name, exc)

    @model_validator(mode="before")
    @classmethod
    def _validate_types_and_values(cls, data: Any) -> Any:
        if isinstance(data, cls):
            return data
        if not isinstance(data, dict):
            return data

        kind = data.get("kind", _UNSET)
        address = data.get("address", _UNSET)

        if kind is _UNSET:
            return data
        if not isinstance(kind, str) or kind not in _REPLY_TARGET_KINDS:
            raise ValueError(f"Unsupported notification reply target: {kind}")
        if address is _UNSET:
            return data
        if not isinstance(address, str):
            raise TypeError("Notification reply target address must be a string")
        if not address.strip():
            raise ValueError("Notification reply target address must not be blank")
        if kind == "dingtalk" and not is_dingtalk_session_webhook_url(address):
            raise ValueError("DingTalk reply target must use the official session endpoint")
        return data


class AnalysisRequestContext(BaseModel):
    """Immutable requester provenance and reply targets used by the core flow."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    requester_platform: str = ""
    requester_user_id: str = ""
    requester_user_name: str = ""
    requester_chat_id: str = ""
    requester_message_id: str = ""
    requester_query: str = ""
    reply_targets: Tuple[NotificationReplyTarget, ...] = ()
    contextual_reply_only: bool = False

    def __setattr__(self, name: str, value: Any) -> None:
        try:
            super().__setattr__(name, value)
        except ValidationError as exc:
            _raise_frozen_instance(name, exc)

    @model_validator(mode="before")
    @classmethod
    def _validate_and_normalize(cls, data: Any) -> Any:
        if isinstance(data, cls):
            return data
        if not isinstance(data, dict):
            return data

        payload = dict(data)

        for name in _REQUESTER_FIELDS:
            if name in payload and not isinstance(payload[name], str):
                raise TypeError("Requester provenance fields must be strings")
        if "contextual_reply_only" in payload and not isinstance(
            payload["contextual_reply_only"], bool
        ):
            raise TypeError("contextual_reply_only must be a bool")

        if "reply_targets" in payload:
            targets = payload["reply_targets"]
            if targets is None:
                targets = ()
            if not isinstance(targets, (list, tuple)):
                raise TypeError("reply_targets must contain NotificationReplyTarget values")
            normalized: list[Any] = []
            for target in targets:
                if isinstance(target, NotificationReplyTarget):
                    normalized.append(target)
                elif isinstance(target, dict):
                    normalized.append(NotificationReplyTarget.model_validate(target))
                else:
                    raise TypeError(
                        "reply_targets must contain NotificationReplyTarget values"
                    )
            payload["reply_targets"] = tuple(normalized)
            if normalized:
                payload["contextual_reply_only"] = True

        return payload

    def reply_address(self, kind: ReplyTargetKind) -> Optional[str]:
        """Return the first address for a contextual notification channel."""
        for target in self.reply_targets:
            if target.kind == kind:
                return target.address
        return None
