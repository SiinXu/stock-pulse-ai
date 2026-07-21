# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Leak-scan for the experimental runtime's failure surface (RF-06b / RF-06).

RF-06's verification list requires a "secret / prompt / reasoning / complete tool
Result / Raw anomaly leakage scan". This is the offline, deterministic slice of that
requirement for the experimental PydanticAI runtime: it proves the adapter's
user-facing failure surface routes through StockPulse's ``sanitize_agent_
diagnostic`` — redacting API keys, credentialed URLs and bearer tokens and
bounding length — instead of surfacing a raw provider payload.

The realistic failure path is a provider error: the in-process
``LLMToolAdapter`` collapses upstream failures into ``provider="error"`` with a
public message, and the model bridge maps that to a sanitized terminal error
(``pydantic_ai_adapter.py`` ``_ProviderBridgeError``). Here a fake adapter
plants secrets in that error content to assert the redaction is real, not
assumed. Benchmark latency/cost and desktop packaging leak scans need a real
provider and build machines and are out of this offline slice.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from tests.litellm_stub import ensure_litellm_stub

ensure_litellm_stub()

from src.agent.llm_adapter import LLMResponse
from src.agent.runtime.contract import ExecutionContext, ExecutionMode, ExecutionState

from tests.agent.runtime._pydantic_ai_dependency import require_pydantic_ai

require_pydantic_ai()

from src.agent.runtime.pydantic_ai_adapter import PydanticAIRuntimeAdapter

# Planted secrets — none of these substrings may survive into a user-facing
# terminal error. Values are synthetic and match the shapes StockPulse's
# sanitizer redacts (token-like key, credentialed URL, bearer header).
_LEAKED_API_KEY = "sk-LEAKED0000key1111secret2222deadbeef"
_LEAKED_URL = "https://user:pw@internal.provider.local/v1/chat"
_LEAKED_BEARER = "Bearer abcdef0123456789abcdef0123456789"
_ALL_SECRETS = (_LEAKED_API_KEY, "internal.provider.local", "abcdef0123456789")


class _LeakingProviderAdapter:
    """Fake in-process adapter that returns a provider error carrying secrets."""

    def __init__(self, *, repeat: int = 1):
        self.primary_model = "leak-model"
        self._repeat = repeat

    def call_with_tools(self, messages, tools, provider=None, timeout=None):
        payload = (
            f"upstream request to {_LEAKED_URL} failed: authorization={_LEAKED_BEARER} "
            f"apikey={_LEAKED_API_KEY} raw_provider_body="
        ) * self._repeat
        return LLMResponse(content=payload, provider="error")


def _run(adapter):
    return adapter.execute(
        ExecutionContext(mode=ExecutionMode.RUN, prompt="Analyze 600519")
    )


def test_provider_error_surface_redacts_secrets():
    adapter = PydanticAIRuntimeAdapter(llm_adapter=_LeakingProviderAdapter())
    handle = _run(adapter)

    assert handle.state is ExecutionState.FAILED
    assert handle.result.success is False
    error = handle.result.error or ""
    # The terminal error is non-empty (a sanitized diagnostic, not swallowed)
    # but none of the planted secrets survive.
    assert error
    for secret in _ALL_SECRETS:
        assert secret not in error, f"leaked secret in terminal error: {secret!r}"
    # No dashboard is fabricated on failure.
    assert handle.result.dashboard is None


def test_provider_error_surface_is_length_bounded():
    # A large raw payload must not be surfaced verbatim; sanitize bounds it.
    adapter = PydanticAIRuntimeAdapter(llm_adapter=_LeakingProviderAdapter(repeat=200))
    handle = _run(adapter)

    assert handle.state is ExecutionState.FAILED
    error = handle.result.error or ""
    assert len(error) <= 300
    for secret in _ALL_SECRETS:
        assert secret not in error
