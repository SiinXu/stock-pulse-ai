# -*- coding: utf-8 -*-
"""Byte-stable serialization and contract tests for request_context Pydantic v2 DTOs.

Golden JSON payloads were captured from the pre-migration frozen dataclasses via
``dataclasses.asdict`` + ``json.dumps(..., sort_keys=True, separators=(",", ":"))``.
Batch 1 of Issue #549 must keep these bytes identical.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from src.schemas.request_context import AnalysisRequestContext, NotificationReplyTarget


def _json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _model_json_bytes(model: AnalysisRequestContext | NotificationReplyTarget) -> bytes:
    # mode="json" matches former asdict JSON shape (tuples -> lists).
    return _json_bytes(model.model_dump(mode="json"))


# Golden payloads captured from dataclass asdict on origin/main before migration.
_GOLDEN_FEISHU_TARGET = b'{"address":"chat-1","kind":"feishu"}'
_GOLDEN_EMPTY_CONTEXT = (
    b'{"contextual_reply_only":false,"reply_targets":[],"requester_chat_id":"",'
    b'"requester_message_id":"","requester_platform":"","requester_query":"",'
    b'"requester_user_id":"","requester_user_name":""}'
)
_GOLDEN_CONTEXT_WITH_TARGET = (
    b'{"contextual_reply_only":true,"reply_targets":[{"address":"chat-1","kind":"feishu"}],'
    b'"requester_chat_id":"c1","requester_message_id":"m1","requester_platform":"feishu",'
    b'"requester_query":"hello","requester_user_id":"u1","requester_user_name":"Ada"}'
)
_GOLDEN_FORCED_REPLY_ONLY = (
    b'{"contextual_reply_only":true,"reply_targets":[{"address":"42","kind":"telegram"}],'
    b'"requester_chat_id":"","requester_message_id":"","requester_platform":"",'
    b'"requester_query":"","requester_user_id":"","requester_user_name":""}'
)


def test_notification_reply_target_serialization_byte_identical() -> None:
    target = NotificationReplyTarget("feishu", "chat-1")
    assert _model_json_bytes(target) == _GOLDEN_FEISHU_TARGET


def test_empty_analysis_request_context_serialization_byte_identical() -> None:
    context = AnalysisRequestContext()
    assert _model_json_bytes(context) == _GOLDEN_EMPTY_CONTEXT


def test_context_with_target_serialization_byte_identical() -> None:
    context = AnalysisRequestContext(
        requester_platform="feishu",
        requester_user_id="u1",
        requester_user_name="Ada",
        requester_chat_id="c1",
        requester_message_id="m1",
        requester_query="hello",
        reply_targets=(NotificationReplyTarget("feishu", "chat-1"),),
    )
    assert _model_json_bytes(context) == _GOLDEN_CONTEXT_WITH_TARGET


def test_contextual_reply_only_forced_when_targets_present_byte_identical() -> None:
    context = AnalysisRequestContext(
        reply_targets=(NotificationReplyTarget("telegram", "42"),),
        contextual_reply_only=False,
    )
    assert context.contextual_reply_only is True
    assert _model_json_bytes(context) == _GOLDEN_FORCED_REPLY_ONLY


def test_address_is_hidden_from_repr() -> None:
    target = NotificationReplyTarget("feishu", "chat-secret")
    assert "chat-secret" not in repr(target)
    assert target.address == "chat-secret"


def test_model_validate_round_trip_preserves_json_bytes() -> None:
    original = AnalysisRequestContext(
        requester_platform="dingtalk",
        reply_targets=(
            NotificationReplyTarget(
                "dingtalk",
                "https://oapi.dingtalk.com/robot/sendBySession?session=abc",
            ),
        ),
    )
    dumped = original.model_dump(mode="json")
    restored = AnalysisRequestContext.model_validate(dumped)
    assert _model_json_bytes(restored) == _model_json_bytes(original)


def test_package_exports_remain_stable() -> None:
    from src.schemas import AnalysisRequestContext as ExportedContext
    from src.schemas import NotificationReplyTarget as ExportedTarget

    assert ExportedContext is AnalysisRequestContext
    assert ExportedTarget is NotificationReplyTarget


def test_rejects_blank_and_invalid_dingtalk_targets() -> None:
    with pytest.raises(ValueError, match="must not be blank"):
        NotificationReplyTarget("dingtalk", "   ")
    with pytest.raises(ValueError, match="official session endpoint"):
        NotificationReplyTarget(
            "dingtalk",
            "https://attacker.example/robot/sendBySession?session=secret",
        )


def test_freezes_mutable_reply_target_list() -> None:
    target = NotificationReplyTarget("feishu", "chat-1")
    mutable_targets = [target]
    context = AnalysisRequestContext(reply_targets=mutable_targets)
    mutable_targets.clear()

    assert context.reply_targets == (target,)
    assert isinstance(context.reply_targets, tuple)
    assert context.contextual_reply_only is True


def test_type_errors_match_prior_dataclass_contracts() -> None:
    with pytest.raises(TypeError, match="provenance fields must be strings"):
        AnalysisRequestContext(requester_query=[])
    with pytest.raises(TypeError, match="contextual_reply_only must be a bool"):
        AnalysisRequestContext(contextual_reply_only="yes")
    with pytest.raises(TypeError, match="address must be a string"):
        NotificationReplyTarget("feishu", 123)  # type: ignore[arg-type]
