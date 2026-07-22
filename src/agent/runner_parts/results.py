# -*- coding: utf-8 -*-
"""Terminal result builders rebound through the legacy runner facade."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from src.agent.protocols import StageFailureReason

if TYPE_CHECKING:
    from src.agent.runner import RunLoopResult


def _remaining_timeout_seconds(
    start_time: float,
    max_wall_clock_seconds: Optional[float],
) -> Optional[float]:
    """Return remaining wall-clock budget in seconds, or None when disabled."""
    if max_wall_clock_seconds is None or max_wall_clock_seconds <= 0:
        return None
    return max(0.0, float(max_wall_clock_seconds) - (time.time() - start_time))


def _build_timeout_result(
    *,
    start_time: float,
    max_wall_clock_seconds: float,
    step: int,
    tool_calls_log: List[Dict[str, Any]],
    total_tokens: int,
    provider_used: str,
    models_used: List[str],
    messages: List[Dict[str, Any]],
) -> RunLoopResult:
    elapsed = time.time() - start_time
    return RunLoopResult(
        success=False,
        content="",
        tool_calls_log=tool_calls_log,
        total_steps=step,
        total_tokens=total_tokens,
        provider=provider_used,
        models_used=models_used,
        error=f"Agent timed out after {elapsed:.2f}s (limit: {max_wall_clock_seconds:.2f}s)",
        failure_reason=StageFailureReason.TIMEOUT,
        messages=messages,
        timed_out=True,
    )


def _build_cancelled_result(
    *,
    step: int,
    tool_calls_log: List[Dict[str, Any]],
    total_tokens: int,
    provider_used: str,
    models_used: List[str],
    messages: List[Dict[str, Any]],
) -> RunLoopResult:
    """Build the typed terminal result for cooperative cancellation."""
    return RunLoopResult(
        success=False,
        content="",
        tool_calls_log=tool_calls_log,
        total_steps=step,
        total_tokens=total_tokens,
        provider=provider_used,
        models_used=models_used,
        error="Agent execution cancelled",
        messages=messages,
        cancelled=True,
    )


def _build_budget_guard_result(
    *,
    start_time: float,
    step: int,
    tool_calls_log: List[Dict[str, Any]],
    total_tokens: int,
    provider_used: str,
    models_used: List[str],
    messages: List[Dict[str, Any]],
    remaining_timeout_s: float,
    min_step_budget_s: float,
) -> RunLoopResult:
    return RunLoopResult(
        success=False,
        content="",
        tool_calls_log=tool_calls_log,
        total_steps=step,
        total_tokens=total_tokens,
        provider=provider_used,
        models_used=models_used,
        error=(
            "Agent step skipped due to insufficient budget: "
            f"{remaining_timeout_s:.2f}s remaining, minimum {min_step_budget_s:.1f}s required"
        ),
        failure_reason=StageFailureReason.BUDGET_SKIP,
        messages=messages,
    )


def _build_tool_loop_result(
    *,
    step: int,
    tool_name: str,
    repeat_limit: int,
    tool_calls_log: List[Dict[str, Any]],
    total_tokens: int,
    provider_used: str,
    models_used: List[str],
    messages: List[Dict[str, Any]],
) -> RunLoopResult:
    """Build the typed terminal result for an identical tool-call loop."""
    return RunLoopResult(
        success=False,
        content="",
        tool_calls_log=tool_calls_log,
        total_steps=step,
        total_tokens=total_tokens,
        provider=provider_used,
        models_used=models_used,
        error=(
            f"Agent stopped because tool '{tool_name}' exceeded the "
            f"identical-call limit ({repeat_limit})"
        ),
        failure_reason=StageFailureReason.LOOP_DETECTED,
        messages=messages,
    )
