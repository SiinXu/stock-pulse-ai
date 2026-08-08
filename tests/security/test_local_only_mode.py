# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Fail-closed LOCAL_ONLY_MODE contracts and zero non-loopback analysis walk."""

from __future__ import annotations

from typing import List
from unittest.mock import patch

import pytest

from src.security.outbound_policy import (
    LOCAL_ONLY_MODE_ENV,
    OutboundPolicyError,
    clear_outbound_activity_for_tests,
    get_outbound_activity,
    is_local_only_mode,
    safe_get,
    validate_outbound_url,
)


@pytest.fixture(autouse=True)
def _clean_local_only_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(LOCAL_ONLY_MODE_ENV, raising=False)
    monkeypatch.delenv("OUTBOUND_HTTP_ALLOWLIST", raising=False)
    clear_outbound_activity_for_tests()
    yield
    clear_outbound_activity_for_tests()
    monkeypatch.delenv(LOCAL_ONLY_MODE_ENV, raising=False)


def test_local_only_mode_defaults_off() -> None:
    assert is_local_only_mode() is False


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_local_only_mode_env_truthy(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv(LOCAL_ONLY_MODE_ENV, value)
    assert is_local_only_mode() is True


@pytest.mark.parametrize(
    "url",
    [
        "https://api.openai.com/v1/models",
        "https://api.tushare.pro",
        "https://news.example.com/feed",
        "http://10.0.0.5:8080/private",
        "http://searxng.internal:8080/search",
        "http://169.254.169.254/latest/meta-data/",
    ],
)
def test_local_only_blocks_non_loopback_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    url: str,
) -> None:
    monkeypatch.setenv(LOCAL_ONLY_MODE_ENV, "true")
    monkeypatch.setenv("OUTBOUND_HTTP_ALLOWLIST", "api.openai.com,10.0.0.5:8080,searxng.internal:8080")
    with pytest.raises(OutboundPolicyError, match="local_only_mode_blocked") as exc_info:
        validate_outbound_url(url, resolve_dns=False)
    assert exc_info.value.reason == "local_only_mode_blocked"
    assert "LOCAL_ONLY_MODE" in str(exc_info.value)
    with patch("src.security.outbound_policy.requests.get") as transport:
        with pytest.raises(OutboundPolicyError, match="local_only_mode_blocked"):
            safe_get(url)
    transport.assert_not_called()


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:11434/api/tags",
        "http://localhost:11434/api/tags",
        "http://[::1]:11434/api/tags",
    ],
)
def test_local_only_allows_pure_loopback(
    monkeypatch: pytest.MonkeyPatch,
    url: str,
) -> None:
    monkeypatch.setenv(LOCAL_ONLY_MODE_ENV, "true")
    target = validate_outbound_url(url, resolve_dns=False)
    assert target.allowlisted is True
    activity = get_outbound_activity(limit=5)
    assert activity
    assert activity[0].decision == "allowed"
    assert activity[0].destination_class == "loopback"
    assert activity[0].local_only_mode is True


_ANALYSIS_EGRESS_FIXTURES: List[str] = [
    "https://api.tushare.pro",
    "https://query1.finance.yahoo.com/v8/finance/chart/AAPL",
    "https://api.openai.com/v1/chat/completions",
    "https://api.anthropic.com/v1/messages",
    "https://searx.example/search",
    "https://news.example.com/rss",
    "https://hooks.example.com/notify",
    "https://ntfy.sh/topic",
    "http://10.0.0.20:3000/webhook",
]


def test_local_only_analysis_walk_allows_zero_non_loopback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(LOCAL_ONLY_MODE_ENV, "true")
    clear_outbound_activity_for_tests()
    blocked = 0
    for url in _ANALYSIS_EGRESS_FIXTURES:
        with pytest.raises(OutboundPolicyError) as exc_info:
            validate_outbound_url(url, resolve_dns=False)
        assert exc_info.value.reason == "local_only_mode_blocked"
        blocked += 1
    validate_outbound_url("http://127.0.0.1:11434/api/generate", resolve_dns=False)
    activity = get_outbound_activity(limit=100)
    allowed_non_loopback = [
        item for item in activity
        if item.decision == "allowed" and item.destination_class != "loopback"
    ]
    blocked_items = [item for item in activity if item.decision == "blocked"]
    assert blocked == len(_ANALYSIS_EGRESS_FIXTURES)
    assert allowed_non_loopback == []
    assert len(blocked_items) >= len(_ANALYSIS_EGRESS_FIXTURES)
    assert all(item.reason == "local_only_mode_blocked" for item in blocked_items)
    assert all(item.local_only_mode for item in activity)
    for item in activity:
        for value in item.as_dict().values():
            if isinstance(value, str):
                assert "://" not in value
                assert "openai.com" not in value
                assert "tushare" not in value


def test_local_only_activity_records_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(LOCAL_ONLY_MODE_ENV, "true")
    clear_outbound_activity_for_tests()
    with pytest.raises(OutboundPolicyError):
        validate_outbound_url("https://public.example/path", resolve_dns=False)
    items = get_outbound_activity(limit=1)
    assert len(items) == 1
    assert items[0].decision == "blocked"
    assert items[0].destination_class == "public_hostname"
    assert items[0].reason == "local_only_mode_blocked"
