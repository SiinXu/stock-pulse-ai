# -*- coding: utf-8 -*-
"""Caller helper for the shared notification dispatch result contract."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from src.notification import ChannelAttemptResult, NotificationDispatchResult
from src.notification_parts.dispatch import (
    coerce_notification_dispatch_result,
    dispatch_channel_summaries,
    invoke_notifier_dispatch,
)


def test_invoke_uses_canonical_send_with_results_for_mixed_channels() -> None:
    class _Notifier:
        def send_with_results(self, content: str, **kwargs):
            assert content == "body"
            assert kwargs["route_type"] == "report"
            return NotificationDispatchResult(
                dispatched=True,
                success=True,
                status="partial_failed",
                channel_results=[
                    ChannelAttemptResult(
                        channel="wechat",
                        success=False,
                        error_code="exception",
                    ),
                    ChannelAttemptResult(channel="custom", success=True),
                ],
            )

        def send(self, content: str, **kwargs):
            raise AssertionError("legacy send() must not run when results exist")

    result = invoke_notifier_dispatch(
        _Notifier(),
        "body",
        route_type="report",
    )
    assert result.status == "partial_failed"
    summaries = dispatch_channel_summaries(result)
    by_channel = {item["channel"]: item for item in summaries}
    assert by_channel["wechat"] == {
        "channel": "wechat",
        "ok": False,
        "error": "exception",
    }
    assert by_channel["custom"] == {
        "channel": "custom",
        "ok": True,
        "error": None,
    }


def test_invoke_wraps_legacy_bool_send_without_inventing_channels() -> None:
    class _Notifier:
        def send(self, content: str, **kwargs):
            assert content == "legacy"
            return True

    result = invoke_notifier_dispatch(_Notifier(), "legacy")
    assert result.success is True
    assert result.status == "sent"
    assert result.channel_results == []
    assert dispatch_channel_summaries(result) == []


def test_invoke_spec_set_mock_models_canonical_all_failed_contract() -> None:
    notifier = MagicMock(spec_set=["send_with_results"])
    notifier.send_with_results.return_value = NotificationDispatchResult(
        dispatched=True,
        success=False,
        status="all_failed",
        channel_results=[
            ChannelAttemptResult(
                channel="custom",
                success=False,
                error_code="send_failed",
            ),
        ],
    )

    result = invoke_notifier_dispatch(notifier, "body", route_type="alert")

    notifier.send_with_results.assert_called_once_with("body", route_type="alert")
    assert result.status == "all_failed"
    assert dispatch_channel_summaries(result) == [
        {"channel": "custom", "ok": False, "error": "send_failed"},
    ]


def test_invoke_missing_methods_return_no_channel() -> None:
    class _EmptyNotifier:
        pass

    result = invoke_notifier_dispatch(_EmptyNotifier(), "body")
    assert result.dispatched is False
    assert result.success is False
    assert result.status == "no_channel"


def test_invoke_unrecognized_send_with_results_is_not_silent_success() -> None:
    class _Notifier:
        def send_with_results(self, content: str, **kwargs):
            return object()

        def send(self, content: str, **kwargs):
            raise AssertionError("legacy send() must not run when results exist")

    result = invoke_notifier_dispatch(_Notifier(), "body")
    assert result.dispatched is True
    assert result.success is False
    assert result.status == "all_failed"
    assert dispatch_channel_summaries(result) == []


def test_coerce_keeps_canonical_dispatch_result() -> None:
    canonical = NotificationDispatchResult(
        dispatched=True,
        success=True,
        status="sent",
        channel_results=[ChannelAttemptResult(channel="custom", success=True)],
    )
    assert coerce_notification_dispatch_result(canonical) is canonical


def test_coerce_legacy_bool_true_is_explicit_sent_boundary() -> None:
    result = coerce_notification_dispatch_result(True)
    assert isinstance(result, NotificationDispatchResult)
    assert result.success is True
    assert result.status == "sent"
    assert result.channel_results == []


def test_coerce_legacy_bool_false_is_all_failed_boundary() -> None:
    result = coerce_notification_dispatch_result(False)
    assert isinstance(result, NotificationDispatchResult)
    assert result.success is False
    assert result.status == "all_failed"


def _assert_duck_typed_result_fails_closed(value: object) -> None:
    result = coerce_notification_dispatch_result(value)
    assert isinstance(result, NotificationDispatchResult)
    assert result.success is False
    assert result.status == "all_failed"
    assert result is not value
    assert dispatch_channel_summaries(result) == []


def test_coerce_rejects_duck_typed_sent_success() -> None:
    _assert_duck_typed_result_fails_closed(
        SimpleNamespace(status="sent", success=True, dispatched=True)
    )


def test_coerce_rejects_duck_typed_partial_failed_success() -> None:
    _assert_duck_typed_result_fails_closed(
        SimpleNamespace(status="partial_failed", success=True)
    )


def test_coerce_rejects_duck_typed_all_failed_marked_success() -> None:
    _assert_duck_typed_result_fails_closed(
        SimpleNamespace(status="all_failed", success=True)
    )


def test_coerce_rejects_unknown_status_with_success_true() -> None:
    _assert_duck_typed_result_fails_closed(
        SimpleNamespace(status="ok", success=True)
    )


def test_invoke_duck_typed_send_with_results_is_not_success() -> None:
    class _Notifier:
        def send_with_results(self, content: str, **kwargs):
            return SimpleNamespace(status="sent", success=True, dispatched=True)

        def send(self, content: str, **kwargs):
            raise AssertionError("legacy send() must not run when results exist")

    result = invoke_notifier_dispatch(_Notifier(), "body")
    assert isinstance(result, NotificationDispatchResult)
    assert result.success is False
    assert result.status == "all_failed"


def test_dispatch_channel_summaries_accepts_plain_namespace_attempts() -> None:
    result = SimpleNamespace(
        channel_results=[
            SimpleNamespace(channel="email", success=True, error_code=None),
            SimpleNamespace(channel="feishu", success=False, error_code="send_failed"),
        ]
    )
    assert dispatch_channel_summaries(result) == [
        {"channel": "email", "ok": True, "error": None},
        {"channel": "feishu", "ok": False, "error": "send_failed"},
    ]
