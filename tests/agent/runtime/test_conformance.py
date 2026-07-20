# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Cross-runtime contract conformance (AR-PY-05 seam).

Drives the same logical scenario through both the permanent Native runtime
and the experimental PydanticAI runtime with deterministic fakes (no
network) and asserts they honor one shared Contract: a terminal
``ExecutionHandle`` classified through ``classify_terminal_state``, a
StockPulse ``AgentResult`` payload, and — critically — no pseudo-success on
failure. This is the contract-parity half of AR-PY-05; the full replay
fixture double-run lands once the adapter covers the chat/pipeline paths.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from tests.litellm_stub import ensure_litellm_stub

ensure_litellm_stub()

from src.agent.executor import AgentResult
from src.agent.runtime.contract import ExecutionContext, ExecutionMode, ExecutionState
from src.agent.runtime.native_adapter import NativeRuntimeAdapter

from tests.agent.runtime._pydantic_ai_dependency import require_pydantic_ai

require_pydantic_ai()

from src.agent.runtime.pydantic_ai_adapter import PydanticAIRuntimeAdapter


class _FakeExecutor:
    def __init__(self, result):
        self._result = result

    def run(self, task, context=None):
        return self._result


def _fake_model(output_text: str):
    from pydantic_ai.messages import ModelResponse, TextPart
    from pydantic_ai.models import Model
    from pydantic_ai.usage import RequestUsage

    class _FakeModel(Model):
        @property
        def model_name(self) -> str:
            return "conformance-fake"

        @property
        def system(self) -> str:
            return "stockpulse"

        async def request(self, messages, model_settings, model_request_parameters):
            return ModelResponse(
                parts=[TextPart(content=output_text)],
                usage=RequestUsage(input_tokens=1, output_tokens=1),
                model_name=self.model_name,
            )

    return _FakeModel()


_DASHBOARD = {"signal": "buy", "confidence": 0.7}
_DASHBOARD_JSON = '{"signal": "buy", "confidence": 0.7}'


def _native_runtime(*, success: bool):
    result = (
        AgentResult(success=True, content=_DASHBOARD_JSON, dashboard=_DASHBOARD)
        if success
        else AgentResult(success=False, content="", dashboard=None, error="boom")
    )
    return NativeRuntimeAdapter(executor=_FakeExecutor(result))


def _pydantic_ai_runtime(*, success: bool):
    text = _DASHBOARD_JSON if success else "not json"
    return PydanticAIRuntimeAdapter(model=_fake_model(text))


_RUNTIME_BUILDERS = {
    "native": _native_runtime,
    "pydantic_ai": _pydantic_ai_runtime,
}


def _run(builder, *, success: bool):
    adapter = builder(success=success)
    return adapter.execute(ExecutionContext(mode=ExecutionMode.RUN, prompt="Analyze 600519"))


@pytest.mark.parametrize("builder", list(_RUNTIME_BUILDERS.values()), ids=list(_RUNTIME_BUILDERS))
def test_success_path_is_contract_equivalent(builder):
    handle = _run(builder, success=True)
    assert handle.state is ExecutionState.SUCCEEDED
    assert handle.is_terminal is True
    assert handle.result.success is True
    assert handle.result.dashboard == _DASHBOARD
    assert handle.error is None


@pytest.mark.parametrize("builder", list(_RUNTIME_BUILDERS.values()), ids=list(_RUNTIME_BUILDERS))
def test_failure_never_masquerades_as_success(builder):
    handle = _run(builder, success=False)
    # Both runtimes fail closed: terminal is FAILED, never a pseudo-success.
    assert handle.state is ExecutionState.FAILED
    assert handle.is_terminal is True
    assert handle.result.success is False
    assert handle.result.dashboard is None


def test_both_runtimes_produce_the_same_result_type():
    native = _run(_native_runtime, success=True)
    pai = _run(_pydantic_ai_runtime, success=True)
    assert type(native.result) is type(pai.result) is AgentResult
