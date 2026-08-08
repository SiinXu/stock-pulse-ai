# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Unit tests for agent trajectory evaluation (Issue #269)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.schemas.agent_trajectory import (
    FAILURE_CLASS_ERROR,
    FAILURE_CLASS_GUARDED,
    FAILURE_CLASS_NONE,
    FAILURE_CLASS_TIMEOUT,
    PATH_ORCHESTRATOR,
    PATH_SINGLE,
)
from src.services.agent_trajectory_eval_service import (
    classify_failure,
    compute_trajectory_metrics,
    duration_to_ms,
    evaluate_agent_trajectory,
    is_agent_trajectory_eval_enabled,
    normalize_tool_arguments,
)


def _entry(
    *,
    step: int = 1,
    tool: str = "get_stock_info",
    arguments: dict | None = None,
    success: bool = True,
    duration: float = 0.1,
    cached: bool = False,
    timeout: bool | None = None,
    guarded: bool | None = None,
) -> dict:
    row = {
        "step": step,
        "tool": tool,
        "arguments": arguments if arguments is not None else {"code": "600519"},
        "success": success,
        "duration": duration,
        "result_length": 10,
        "cached": cached,
    }
    if timeout is not None:
        row["timeout"] = timeout
    if guarded is not None:
        row["guarded"] = guarded
    return row


class TestGateDefaultOff:
    def test_gate_default_false_without_config_attr(self, monkeypatch):
        monkeypatch.delenv("AGENT_TRAJECTORY_EVAL_ENABLED", raising=False)
        cfg = SimpleNamespace()  # no agent_trajectory_eval_enabled
        assert is_agent_trajectory_eval_enabled(cfg) is False

    def test_gate_respects_config_true(self, monkeypatch):
        monkeypatch.delenv("AGENT_TRAJECTORY_EVAL_ENABLED", raising=False)
        cfg = SimpleNamespace(agent_trajectory_eval_enabled=True)
        assert is_agent_trajectory_eval_enabled(cfg) is True

    def test_gate_respects_env_true(self, monkeypatch):
        monkeypatch.setenv("AGENT_TRAJECTORY_EVAL_ENABLED", "true")
        cfg = SimpleNamespace()
        assert is_agent_trajectory_eval_enabled(cfg) is True

    def test_evaluate_disabled_returns_neutral_without_computing(self, monkeypatch):
        monkeypatch.delenv("AGENT_TRAJECTORY_EVAL_ENABLED", raising=False)
        log = [
            _entry(tool="a"),
            _entry(tool="a"),  # would be redundant if computed
        ]
        result = evaluate_agent_trajectory(log, config=SimpleNamespace())
        assert result.metrics.enabled is False
        assert result.metrics.neutral is True
        assert result.metrics.sample_size == 0
        assert result.metrics.tool_selection_accuracy is None
        assert result.metrics.step_efficiency is None
        assert result.metrics.redundant_call_count == 0
        assert result.steps == []

    def test_disabled_matches_prechange_noop_contract(self, monkeypatch):
        """Gate off: evaluate is a pure no-op shape regardless of log content."""
        monkeypatch.delenv("AGENT_TRAJECTORY_EVAL_ENABLED", raising=False)
        cfg = SimpleNamespace(agent_trajectory_eval_enabled=False)
        empty = evaluate_agent_trajectory([], config=cfg)
        full = evaluate_agent_trajectory(
            [_entry(), _entry(tool="other", arguments={"x": 1})],
            config=cfg,
        )
        assert empty.metrics.to_dict() == full.metrics.to_dict()
        assert empty.steps == full.steps == []


class TestArgumentNormalization:
    def test_key_order_does_not_matter(self):
        a = normalize_tool_arguments({"b": 1, "a": 2})
        b = normalize_tool_arguments({"a": 2, "b": 1})
        assert a == b

    def test_nested_stable(self):
        a = normalize_tool_arguments({"outer": {"z": 1, "y": [2, 3]}})
        b = normalize_tool_arguments({"outer": {"y": [2, 3], "z": 1}})
        assert a == b


class TestAllSuccessTrajectory:
    def test_all_success_unique_tools(self):
        log = [
            _entry(step=1, tool="get_stock_info", arguments={"code": "A"}, duration=0.1),
            _entry(step=2, tool="get_daily_history", arguments={"code": "A"}, duration=0.2),
            _entry(step=3, tool="analyze_trend", arguments={"code": "A"}, duration=0.3),
        ]
        result = compute_trajectory_metrics([log], path_label=PATH_SINGLE)
        m = result.metrics
        assert m.sample_size == 3
        assert m.tool_selection_accuracy == pytest.approx(1.0)
        assert m.redundant_call_count == 0
        assert m.retry_count == 0
        assert m.step_efficiency == pytest.approx(1.0)
        assert m.total_duration_ms == 100 + 200 + 300
        assert m.neutral is False
        assert m.path_label == PATH_SINGLE
        assert all(s.failure_class == FAILURE_CLASS_NONE for s in result.steps)


class TestFailureRetry:
    def test_failure_then_success_is_retry_not_redundant(self):
        log = [
            _entry(
                step=1,
                tool="get_realtime_quote",
                arguments={"code": "600519"},
                success=False,
                duration=0.05,
            ),
            _entry(
                step=2,
                tool="get_realtime_quote",
                arguments={"code": "600519"},
                success=True,
                duration=0.08,
            ),
        ]
        result = compute_trajectory_metrics([log])
        m = result.metrics
        assert m.sample_size == 2
        assert m.retry_count == 1
        assert m.redundant_call_count == 0
        assert m.tool_selection_accuracy == pytest.approx(0.5)
        assert result.steps[0].is_retry is False
        assert result.steps[0].failure_class == FAILURE_CLASS_ERROR
        assert result.steps[1].is_retry is True
        assert result.steps[1].is_redundant is False

    def test_timeout_classified(self):
        entry = _entry(success=False, timeout=True)
        assert classify_failure(entry) == FAILURE_CLASS_TIMEOUT
        result = compute_trajectory_metrics([[entry]])
        assert result.steps[0].failure_class == FAILURE_CLASS_TIMEOUT

    def test_guarded_classified(self):
        entry = _entry(success=False, guarded=True)
        assert classify_failure(entry) == FAILURE_CLASS_GUARDED


class TestCachedHit:
    def test_cached_success_counts_normally(self):
        log = [
            _entry(tool="get_daily_history", arguments={"code": "X"}, cached=True, duration=0.01),
            _entry(tool="analyze_trend", arguments={"code": "X"}, cached=False, duration=0.2),
        ]
        result = compute_trajectory_metrics([log])
        assert result.metrics.sample_size == 2
        assert result.metrics.tool_selection_accuracy == pytest.approx(1.0)
        assert result.steps[0].cached is True
        assert result.metrics.redundant_call_count == 0

    def test_reissued_identical_cached_call_is_redundant(self):
        log = [
            _entry(tool="get_stock_info", arguments={"code": "X"}, cached=False),
            _entry(tool="get_stock_info", arguments={"code": "X"}, cached=True),
        ]
        result = compute_trajectory_metrics([log])
        assert result.metrics.redundant_call_count == 1
        assert result.steps[1].is_redundant is True
        assert result.metrics.step_efficiency == pytest.approx(0.5)


class TestEmptyAndSingleStep:
    def test_empty_trajectory_neutral(self):
        result = compute_trajectory_metrics([[]])
        m = result.metrics
        assert m.sample_size == 0
        assert m.tool_selection_accuracy is None
        assert m.step_efficiency is None
        assert m.neutral is True
        assert m.total_duration_ms == 0

    def test_no_runs_neutral(self):
        result = compute_trajectory_metrics([])
        assert result.metrics.sample_size == 0
        assert result.metrics.tool_selection_accuracy is None
        assert result.run_count == 0

    def test_single_step(self):
        result = compute_trajectory_metrics([[_entry(duration=1.5)]])
        m = result.metrics
        assert m.sample_size == 1
        assert m.tool_selection_accuracy == pytest.approx(1.0)
        assert m.step_efficiency == pytest.approx(1.0)
        assert m.redundant_call_count == 0
        assert m.retry_count == 0
        assert m.total_duration_ms == 1500


class TestRedundancyBoundary:
    def test_same_tool_different_args_not_redundant(self):
        log = [
            _entry(tool="get_stock_info", arguments={"code": "600519"}),
            _entry(tool="get_stock_info", arguments={"code": "000001"}),
        ]
        result = compute_trajectory_metrics([log])
        assert result.metrics.redundant_call_count == 0
        assert result.metrics.retry_count == 0
        assert all(not s.is_redundant for s in result.steps)

    def test_same_tool_same_args_is_redundant(self):
        log = [
            _entry(tool="get_stock_info", arguments={"code": "600519"}),
            _entry(tool="get_stock_info", arguments={"code": "600519"}),
            _entry(tool="get_stock_info", arguments={"code": "600519"}),
        ]
        result = compute_trajectory_metrics([log])
        assert result.metrics.redundant_call_count == 2
        assert result.metrics.retry_count == 0
        assert result.steps[0].is_redundant is False
        assert result.steps[1].is_redundant is True
        assert result.steps[2].is_redundant is True
        assert result.metrics.step_efficiency == pytest.approx(1.0 / 3.0)

    def test_key_order_variant_still_redundant(self):
        log = [
            _entry(tool="search", arguments={"q": "a", "limit": 5}),
            _entry(tool="search", arguments={"limit": 5, "q": "a"}),
        ]
        result = compute_trajectory_metrics([log])
        assert result.metrics.redundant_call_count == 1


class TestPathComparability:
    def test_single_and_orchestrator_share_formulas(self):
        log = [
            _entry(tool="t1", arguments={"x": 1}),
            _entry(tool="t1", arguments={"x": 1}),
            _entry(tool="t2", arguments={"x": 1}, success=False),
            _entry(tool="t2", arguments={"x": 1}, success=True),
        ]
        single = compute_trajectory_metrics([log], path_label=PATH_SINGLE)
        orch = compute_trajectory_metrics([log], path_label=PATH_ORCHESTRATOR)
        assert single.metrics.tool_selection_accuracy == orch.metrics.tool_selection_accuracy
        assert single.metrics.redundant_call_count == orch.metrics.redundant_call_count
        assert single.metrics.retry_count == orch.metrics.retry_count
        assert single.metrics.step_efficiency == orch.metrics.step_efficiency
        assert single.metrics.total_duration_ms == orch.metrics.total_duration_ms
        assert single.metrics.sample_size == orch.metrics.sample_size
        assert single.metrics.path_label == PATH_SINGLE
        assert orch.metrics.path_label == PATH_ORCHESTRATOR

    def test_multi_run_aggregation(self):
        run_a = [_entry(tool="a", arguments={"k": 1}, duration=0.1)]
        run_b = [
            _entry(tool="b", arguments={"k": 2}, duration=0.2),
            _entry(tool="b", arguments={"k": 2}, duration=0.2),  # redundant within run_b
        ]
        result = compute_trajectory_metrics([run_a, run_b], path_label=PATH_ORCHESTRATOR)
        assert result.run_count == 2
        assert result.metrics.sample_size == 3
        assert result.metrics.redundant_call_count == 1
        assert result.metrics.total_duration_ms == 100 + 200 + 200


class TestDurationAndForce:
    def test_duration_to_ms_invalid(self):
        assert duration_to_ms(None) is None
        assert duration_to_ms("bad") is None
        assert duration_to_ms(-1.0) == 0

    def test_force_bypasses_gate(self, monkeypatch):
        monkeypatch.delenv("AGENT_TRAJECTORY_EVAL_ENABLED", raising=False)
        log = [_entry(), _entry()]  # second redundant
        result = evaluate_agent_trajectory(
            log,
            config=SimpleNamespace(agent_trajectory_eval_enabled=False),
            force=True,
        )
        assert result.metrics.enabled is True
        assert result.metrics.sample_size == 2
        assert result.metrics.redundant_call_count == 1
