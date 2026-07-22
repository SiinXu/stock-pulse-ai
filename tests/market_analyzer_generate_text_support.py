# -*- coding: utf-8 -*-
"""Shared stubs, fixtures, and helpers for analyzer text contract tests."""

import json
import sys
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# Stub heavy dependencies before project imports
for _mod in ("litellm", "google.generativeai", "google.genai", "anthropic"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

import pytest


class RotatingGenerationError(RuntimeError):
    secret = "MARKET_REVIEW_SECOND_RENDER_CANARY_987654321"

    def __init__(self):
        super().__init__()
        self.render_count = 0

    def __str__(self):
        self.render_count += 1
        return "first render" if self.render_count == 1 else self.secret


@pytest.fixture(autouse=True)
def _llm_usage_hmac_env(monkeypatch):
    monkeypatch.setenv("LLM_USAGE_HMAC_SECRET", "test-usage-hmac-secret")
    monkeypatch.setenv("LLM_USAGE_HMAC_KEY_VERSION", "test-v1")


def _assert_usage_contains(usage, expected):
    for key, value in expected.items():
        assert usage[key] == value
    assert usage["normalized_prompt_tokens"] == expected.get("prompt_tokens")
    assert usage["normalized_completion_tokens"] == expected.get("completion_tokens")
    assert usage["normalized_total_tokens"] == expected.get("total_tokens")
    assert usage["provider_usage_json"]
    assert usage["messages_hmac"] and len(usage["messages_hmac"]) == 64
    assert usage["hmac_key_version"] == "test-v1"


def _assert_no_provider_usage_hmac_only(usage):
    assert "prompt_tokens" not in usage
    assert usage["messages_hmac"] and len(usage["messages_hmac"]) == 64
    assert usage["hmac_key_version"] == "test-v1"


_OPENAI_COMPATIBILITY_PAYLOAD_FIXTURES = [
    # Repro case 1 (Issue #1279): OpenAI-compatible provider message.content is None while text is in content_blocks.
    (
        "openai/cpa-compatible",
        {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "content_blocks": [
                            {"type": "text", "text": "block "},
                            {"type": "text", "text": "response"},
                        ],
                    },
                }
            ],
            "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
        },
        "block response",
    ),
    # Repro case 2: OpenAI-compatible provider returns message.content as list-of-blocks.
    (
        "openai/list-content-provider",
        {
            "choices": [
                {
                    "message": {
                        "content": [
                            {"type": "text", "text": "list "},
                            {"type": "text", "text": "response"},
                        ],
                    },
                }
            ],
            "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
        },
        "list response",
    ),
]


__all__ = (
    "MagicMock",
    "RotatingGenerationError",
    "SimpleNamespace",
    "_OPENAI_COMPATIBILITY_PAYLOAD_FIXTURES",
    "_assert_no_provider_usage_hmac_only",
    "_assert_usage_contains",
    "_llm_usage_hmac_env",
    "contextmanager",
    "json",
    "patch",
    "pytest",
)
