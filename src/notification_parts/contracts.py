# -*- coding: utf-8 -*-
"""Shared notification configuration and dispatch-result contracts.

This module intentionally stays lightweight: no sender imports, no SDK imports,
and no NotificationService imports. It is safe for config, diagnostics, and
runtime channel detection to share.

Dispatch result types (Issue #1081) live here so callers can depend on the
stable query shape without importing the full notification facade.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple
from urllib.parse import parse_qsl, urlsplit


@dataclass
class ChannelAttemptResult:
    """One notification channel send attempt (built-in or plugin).

    Callers that need a stable, JSON-friendly shape should use
    :meth:`as_summary` (minimal ``channel`` / ``ok`` / ``error``) or
    :meth:`as_dict` (includes retry and diagnostic fields).
    """

    channel: str
    success: bool
    error_code: Optional[str] = None
    retryable: bool = False
    latency_ms: Optional[int] = None
    diagnostics: Optional[str] = None

    def as_summary(self) -> Dict[str, Any]:
        """Return the minimal queryable per-channel shape (Issue #1081)."""

        return {
            "channel": self.channel,
            "ok": bool(self.success),
            "error": self.error_code,
        }

    def as_dict(self) -> Dict[str, Any]:
        """Return the full queryable per-channel attempt record."""

        summary = self.as_summary()
        summary.update(
            {
                "retryable": bool(self.retryable),
                "latency_ms": self.latency_ms,
                "diagnostics": self.diagnostics,
            }
        )
        return summary


@dataclass
class NotificationDispatchResult:
    """Structured multi-channel notification dispatch result.

    Separates analysis success from notification delivery outcomes:
    ``status`` may be ``sent``, ``partial_failed``, ``all_failed``,
    ``no_channel``, or ``noise_suppressed`` while ``channel_results``
    retains every attempted channel for query and diagnostics.
    """

    dispatched: bool
    success: bool
    status: str
    channel_results: List[ChannelAttemptResult] = field(default_factory=list)
    message: Optional[str] = None

    def channel_summaries(self) -> List[Dict[str, Any]]:
        """Return ``[{channel, ok, error}, ...]`` for API/bot/diagnostics callers."""

        return [item.as_summary() for item in self.channel_results]

    def as_dict(self) -> Dict[str, Any]:
        """Return a JSON-friendly dispatch record for query and logging."""

        return {
            "dispatched": bool(self.dispatched),
            "success": bool(self.success),
            "status": self.status,
            "message": self.message,
            "channels": self.channel_summaries(),
            "channel_results": [item.as_dict() for item in self.channel_results],
        }


FEISHU_WEBHOOK_ENV_GROUP: Tuple[str, ...] = ("FEISHU_WEBHOOK_URL",)
FEISHU_APP_BOT_ENV_GROUP: Tuple[str, ...] = (
    "FEISHU_APP_ID",
    "FEISHU_APP_SECRET",
    "FEISHU_CHAT_ID",
)
FEISHU_STATIC_ENV_GROUPS: Tuple[Tuple[str, ...], ...] = (
    FEISHU_WEBHOOK_ENV_GROUP,
    FEISHU_APP_BOT_ENV_GROUP,
)

_FEISHU_WEBHOOK_CONFIG_GROUP: Tuple[str, ...] = ("feishu_webhook_url",)
_FEISHU_APP_BOT_CONFIG_GROUP: Tuple[str, ...] = (
    "feishu_app_id",
    "feishu_app_secret",
    "feishu_chat_id",
)
_FEISHU_STATIC_CONFIG_GROUPS: Tuple[Tuple[str, ...], ...] = (
    _FEISHU_WEBHOOK_CONFIG_GROUP,
    _FEISHU_APP_BOT_CONFIG_GROUP,
)


def is_dingtalk_session_webhook_url(value: Any) -> bool:
    """Return whether a value is an official DingTalk session reply URL."""
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = urlsplit(value)
        port = parsed.port
        query = parse_qsl(parsed.query, keep_blank_values=True)
    except ValueError:
        return False
    return (
        parsed.scheme.lower() == "https"
        and (parsed.hostname or "").rstrip(".").lower() == "oapi.dingtalk.com"
        and port in (None, 443)
        and parsed.username is None
        and parsed.password is None
        and parsed.path == "/robot/sendBySession"
        and not parsed.fragment
        and any(key == "session" and value for key, value in query)
    )


def _has_env_group(effective_map: Mapping[str, Any], group: Tuple[str, ...]) -> bool:
    return all(str(effective_map.get(key) or "").strip() for key in group)


def is_feishu_app_bot_env_configured(effective_map: Mapping[str, Any]) -> bool:
    """Return whether Feishu App Bot active notification is configured."""
    return _has_env_group(effective_map, FEISHU_APP_BOT_ENV_GROUP)


def is_feishu_static_env_configured(effective_map: Mapping[str, Any]) -> bool:
    """Return whether any static Feishu notification route is configured."""
    return any(_has_env_group(effective_map, group) for group in FEISHU_STATIC_ENV_GROUPS)


def _has_config_group(config: Any, group: Tuple[str, ...]) -> bool:
    return all(str(getattr(config, attr, None) or "").strip() for attr in group)


def is_feishu_app_bot_configured(config: Any) -> bool:
    """Return whether a Config-like object has the App Bot notification triad."""
    return _has_config_group(config, _FEISHU_APP_BOT_CONFIG_GROUP)


def is_feishu_static_configured(config: Any) -> bool:
    """Return whether a Config-like object has any static Feishu route."""
    return any(_has_config_group(config, group) for group in _FEISHU_STATIC_CONFIG_GROUPS)
