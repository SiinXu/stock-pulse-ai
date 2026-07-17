# -*- coding: utf-8 -*-
"""Tests for the experimental PydanticAI runtime adapter (AR-PY-04, 方案 B).

Two contracts are asserted:

- **Optional-dependency contract**: when ``pydantic-ai-slim`` is absent, the
  availability probe reports False and using the runtime raises one explicit
  ``PydanticAIRuntimeUnavailableError`` — never a silent fallback. Native is
  unaffected (this module never touches the default path).
- **POC functional contract**: driven by a deterministic fake PydanticAI
  ``Model`` (no network), a Single Agent run terminates via the shared
  ``classify_terminal_state`` and maps PydanticAI output into a StockPulse
  ``AgentResult``.
"""

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from tests.litellm_stub import ensure_litellm_stub

ensure_litellm_stub()

from src.agent.runtime.contract import ExecutionContext, ExecutionMode, ExecutionState
from src.agent.runtime.pydantic_ai_adapter import (
    PydanticAIRuntimeAdapter,
    PydanticAIRuntimeUnavailableError,
    _to_stockpulse_messages,
    is_pydantic_ai_available,
)

pydantic_ai = pytest.importorskip("pydantic_ai")


def _fake_model(output_text: str):
    from pydantic_ai.messages import ModelResponse, TextPart
    from pydantic_ai.models import Model
    from pydantic_ai.usage import RequestUsage

    class _FakeModel(Model):
        def __init__(self):
            self.calls = []

        @property
        def model_name(self) -> str:
            return "fake-model"

        @property
        def system(self) -> str:
            return "stockpulse"

        async def request(self, messages, model_settings, model_request_parameters):
            self.calls.append(list(messages))
            return ModelResponse(
                parts=[TextPart(content=output_text)],
                usage=RequestUsage(input_tokens=4, output_tokens=6),
                model_name=self.model_name,
            )

    return _FakeModel()


def _run_context(prompt: str) -> ExecutionContext:
    return ExecutionContext(mode=ExecutionMode.RUN, prompt=prompt)


# ---------------------------------------------------------------------------
# Optional-dependency contract
# ---------------------------------------------------------------------------


def test_availability_probe_true_when_installed():
    assert is_pydantic_ai_available() is True


def test_availability_probe_false_when_absent():
    with patch("importlib.util.find_spec", return_value=None):
        assert is_pydantic_ai_available() is False


def test_execute_raises_explicit_error_when_dependency_absent():
    adapter = PydanticAIRuntimeAdapter(model=_fake_model('{"signal": "buy"}'))
    # Simulate the dependency being uninstalled: a None entry in sys.modules
    # makes ``import pydantic_ai`` raise ImportError.
    with patch.dict(sys.modules, {"pydantic_ai": None}):
        with pytest.raises(PydanticAIRuntimeUnavailableError):
            adapter.execute(_run_context("Analyze 600519"))


def test_constructor_requires_model_or_adapter():
    with pytest.raises(ValueError):
        PydanticAIRuntimeAdapter()


# ---------------------------------------------------------------------------
# POC functional contract
# ---------------------------------------------------------------------------


def test_run_maps_dashboard_output_to_succeeded():
    adapter = PydanticAIRuntimeAdapter(model=_fake_model('{"signal": "buy", "confidence": 0.8}'))
    handle = adapter.execute(_run_context("Analyze 600519"))

    assert handle.state is ExecutionState.SUCCEEDED
    assert handle.is_terminal is True
    result = handle.result
    assert result.success is True
    assert result.dashboard == {"signal": "buy", "confidence": 0.8}
    assert result.total_tokens == 10
    assert result.model == "fake-model"


def test_run_without_dashboard_json_fails_closed():
    adapter = PydanticAIRuntimeAdapter(model=_fake_model("no json here"))
    handle = adapter.execute(_run_context("Analyze 600519"))

    assert handle.state is ExecutionState.FAILED
    assert handle.result.success is False
    assert handle.result.dashboard is None
    assert "dashboard" in (handle.result.error or "").lower()


def test_non_run_mode_is_not_implemented():
    adapter = PydanticAIRuntimeAdapter(model=_fake_model('{"signal": "buy"}'))
    with pytest.raises(NotImplementedError):
        adapter.execute(
            ExecutionContext(mode=ExecutionMode.CHAT, prompt="hi", session_id="s-1")
        )


def test_name_is_experimental_and_non_default():
    adapter = PydanticAIRuntimeAdapter(model=_fake_model("{}"))
    assert adapter.name == "pydantic_ai_experimental"


# ---------------------------------------------------------------------------
# Message conversion (deterministic, no model)
# ---------------------------------------------------------------------------


def test_message_conversion_maps_text_parts_only():
    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        SystemPromptPart,
        TextPart,
        UserPromptPart,
    )

    history = [
        ModelRequest(parts=[SystemPromptPart(content="sys"), UserPromptPart(content="hello")]),
        ModelResponse(parts=[TextPart(content="hi back")], model_name="fake"),
    ]
    assert _to_stockpulse_messages(history) == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi back"},
    ]
