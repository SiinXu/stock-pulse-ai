# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Cross-runtime replay conformance for the Single RUN path (RF-06a / AR-RF-08).

Every ``mode=single_run`` manifest fixture is driven through BOTH runtimes over
the *same* strict ``ReplayLLMAdapter`` transcript and the deterministic replay
tool registry, and the two runtimes are asserted to honor one shared Contract:

* **Equivalent** (normal / partial / modelref / fallback / toolscope /
  malformed): identical terminal verdict, dashboard, LLM-call count and tool
  call sequence + arguments — the PydanticAI runtime drives the real model
  bridge (RF-05), never a shortcut.
* **Intentional difference** (timeout / cancelrace): terminal *classification*
  equivalence only. The experimental runtime fences timeout/cancel after the
  current step's tools while native fences before, so tool logs may differ.
  Recorded in ``docs/architecture/ADR-001-agent-runtime.md`` D5; neither
  runtime ever fakes success and the dashboard stays absent on both. The native
  side is read from the frozen ``expected`` baseline (already gated by the
  compatibility suite) rather than re-run, so these fixtures' real per-step
  sleeps are exercised once, not twice; the experimental side reaches the same
  non-success terminal via each fixture's bounded budget versus its
  fixed-margin over-budget sleep — a deterministic outcome, not a concurrency
  race on ordering.
* **Unsupported**: CHAT / RESEARCH (and every orchestrator mode) return a
  stable ``unsupported_capability`` — the first-phase matrix is Single RUN only
  and no other mode is implemented to satisfy a fixture count.

The 36 native replay fixtures are read-only; nothing here re-freezes or relaxes
them. When PydanticAI is absent this module skips (native gate); in the
installed matrix (``STOCKPULSE_REQUIRE_PYDANTIC_AI=1``) a missing dependency is
a hard failure, not a skip.
"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from tests.litellm_stub import ensure_litellm_stub

ensure_litellm_stub()

from unittest.mock import patch

from src.agent import factory as factory_module
from src.agent import llm_adapter as llm_adapter_module
from src.agent.runtime.contract import ExecutionContext, ExecutionMode, ExecutionState
from src.agent.runtime.lifecycle import classify_terminal_state
from src.agent.runtime.tool_session import BoundToolSession
from tests.agent_runtime_replay import (
    ReplayLLMAdapter,
    build_replay_tool_registry,
    load_case,
    load_manifest,
    make_case_config,
    run_case,
)

from tests.agent.runtime._pydantic_ai_dependency import require_pydantic_ai

require_pydantic_ai()

from src.agent.runtime.pydantic_ai_adapter import PydanticAIRuntimeAdapter

# ---------------------------------------------------------------------------
# First-phase support matrix, derived from the manifest (never hand-listed):
# only mode=single_run fixtures are double-run; timeout/cancelrace are the
# ADR-001 D5 intentional-difference set; every other mode is unsupported.
# ---------------------------------------------------------------------------

_MANIFEST = load_manifest()
_SINGLE_RUN = [c for c in _MANIFEST["cases"] if c["mode"] == "single_run"]
_INTENTIONAL_DIFF_PROFILES = {"timeout", "cancelrace"}

_EQUIVALENT = [c for c in _SINGLE_RUN if c["profile"] not in _INTENTIONAL_DIFF_PROFILES]
_TERMINAL_ONLY = [c for c in _SINGLE_RUN if c["profile"] in _INTENTIONAL_DIFF_PROFILES]

_EQUIVALENT_IDS = [c["id"] for c in _EQUIVALENT]
_TERMINAL_ONLY_IDS = [c["id"] for c in _TERMINAL_ONLY]

_NON_SUCCESS_TERMINALS = frozenset(
    {ExecutionState.FAILED, ExecutionState.CANCELLED, ExecutionState.TIMED_OUT}
)

# Audit label for the experimental runtime's tool session; mirrors
# PydanticAIRuntimeAdapter.name so the conformance session is not mislabelled
# as the native runtime.
_EXPERIMENTAL_RUNTIME = "pydantic_ai_experimental"


def _run_case_pydantic(case):
    """Drive one fixture through the PydanticAI runtime over its replay transcript.

    Uses the SAME strict ReplayLLMAdapter and deterministic tool registry as the
    native path, seeds the resolved single-run prompt via the executor (RF-05
    prompt authority), and fences tools by the execution deadline so the
    timeout/cancel fixtures terminate deterministically.

    Returns ``(handle, replay_adapter, executed_tools)``.
    """
    config = make_case_config(case)
    executed_tools = []
    registry = build_replay_tool_registry(executed_tools)
    replay = ReplayLLMAdapter(case["transcript"], config=config)

    with patch.object(
        llm_adapter_module, "LLMToolAdapter", new=lambda cfg: replay
    ), patch.object(factory_module, "get_tool_registry", new=lambda: registry):
        executor = factory_module.build_agent_executor(config)
        timeout = getattr(executor, "timeout_seconds", None) or None
        # Tool-fence deadline for the session (bounds slow tools in the
        # timeout/cancel fixtures); distinct from the model-call deadline the
        # adapter derives from context.timeout_seconds below — one fences tools,
        # the other fences LLM round-trips.
        deadline = time.monotonic() + float(timeout) if timeout else None
        session = BoundToolSession(
            registry,
            execution_id=f"conformance-{case['id']}",
            allowed_tools=registry.list_names(),
            backend=_EXPERIMENTAL_RUNTIME,
            principal=_EXPERIMENTAL_RUNTIME,
            # Pass-through access policy reproduces the native run loop's
            # replay-frozen tool dispatch byte-for-byte so the equivalence
            # comparison is apples-to-apples; the strict fail-closed gate is
            # exercised by test_tool_session.py and test_pydantic_ai_real_bridge.py.
            enforce_access_policy=False,
            deadline_monotonic=deadline,
        )
        adapter = PydanticAIRuntimeAdapter(
            llm_adapter=replay, executor=executor, tool_session=session
        )
        payload = case["input"]
        handle = adapter.execute(
            ExecutionContext(
                mode=ExecutionMode.RUN,
                prompt=payload["task"],
                request_context=payload.get("context") or {},
                timeout_seconds=timeout,
            )
        )
    return handle, replay, executed_tools


# ---------------------------------------------------------------------------
# Support-matrix integrity (the three-category report)
# ---------------------------------------------------------------------------


def test_support_matrix_partitions_single_run_fixtures():
    # First phase: 4 financial + 7 contract single_run fixtures, split into
    # 8 equivalent + 3 intentional-difference. Guards against silently
    # dropping a fixture from the double-run.
    assert len(_SINGLE_RUN) == 11
    assert len(_EQUIVALENT) == 8
    assert len(_TERMINAL_ONLY) == 3
    assert {c["profile"] for c in _TERMINAL_ONLY} == {"timeout", "cancelrace"}


# ---------------------------------------------------------------------------
# Equivalent single-run fixtures: full contract equivalence
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case_entry", _EQUIVALENT, ids=_EQUIVALENT_IDS)
def test_single_run_is_contract_equivalent(case_entry):
    case = load_case(case_entry["file"])

    native_result, native_adapter, native_tools, _ = run_case(case)
    handle, pyd_replay, pyd_tools = _run_case_pydantic(case)
    pyd_result = handle.result

    # Terminal verdict: both agree on success, and neither fakes it.
    assert pyd_result.success == native_result.success
    native_terminal = classify_terminal_state(
        success=bool(native_result.success),
        cancelled=bool(native_result.cancelled),
        timed_out=bool(native_result.timed_out),
    )
    assert handle.state is native_terminal
    # Dashboard and derived signal are identical.
    assert pyd_result.dashboard == native_result.dashboard
    # Same number of LLM round-trips, both transcripts fully consumed.
    assert pyd_replay.consumed == native_adapter.consumed
    assert pyd_replay.remaining == 0 and native_adapter.remaining == 0
    # Same tool call sequence and arguments through the fail-closed session.
    assert pyd_tools == native_tools


# ---------------------------------------------------------------------------
# Timeout / cancelrace: terminal-classification equivalence only (ADR-001 D5)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case_entry", _TERMINAL_ONLY, ids=_TERMINAL_ONLY_IDS)
def test_timeout_cancel_is_terminal_equivalent(case_entry):
    case = load_case(case_entry["file"])

    # Native verdict is the frozen AR-01 baseline (already gated by the
    # compatibility suite); read it rather than re-running the fixture's real
    # per-step sleeps a second time. Only the experimental side executes here.
    native_expected = case["expected"]
    handle, _pyd_replay, _pyd_tools = _run_case_pydantic(case)
    pyd_result = handle.result

    # Native fences timeout/cancel before the step's tools; the experimental
    # runtime after (ADR-001 D5), so tool logs may differ. What must hold: the
    # frozen native verdict is non-success with no dashboard, and the
    # experimental runtime reaches the same non-success terminal, never faking
    # success.
    assert native_expected["success"] is False
    assert native_expected["dashboard"] is None
    assert pyd_result.success is False
    assert handle.state in _NON_SUCCESS_TERMINALS
    assert pyd_result.dashboard is None


# ---------------------------------------------------------------------------
# Unsupported capability: only Single RUN is implemented in this phase
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", [ExecutionMode.CHAT, ExecutionMode.RESEARCH])
def test_non_run_modes_are_unsupported(mode):
    adapter = PydanticAIRuntimeAdapter(llm_adapter=object())
    kwargs = {"mode": mode, "prompt": "x"}
    if mode is ExecutionMode.CHAT:
        kwargs["session_id"] = "s-1"
    with pytest.raises(NotImplementedError) as excinfo:
        adapter.execute(ExecutionContext(**kwargs))
    assert "unsupported_capability" in str(excinfo.value)
