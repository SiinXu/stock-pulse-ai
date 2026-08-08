# -*- coding: utf-8 -*-
"""Tests for the optional agent planning pre-step (Issue #199)."""

from __future__ import annotations

import json
import os
import unittest
from types import SimpleNamespace
from typing import Any, List, Optional
from unittest.mock import patch

from src.agent.planning.config import load_planning_settings
from src.agent.planning.engine import PlanningEngine, prepare_run_with_planning
from src.agent.planning.types import validate_plan_payload
from src.agent.tools.registry import (
    ToolDefinition,
    ToolParameter,
    ToolPolicy,
    ToolRegistry,
)


def _tool_registry(*names: str) -> ToolRegistry:
    registry = ToolRegistry()
    for name in names:
        registry.register(
            ToolDefinition(
                name=name,
                description=f"tool {name}",
                parameters=[
                    ToolParameter(
                        name="stock_code",
                        type="string",
                        description="Stock code",
                    )
                ],
                handler=lambda stock_code, _n=name: {"tool": _n, "stock_code": stock_code},
                policy=ToolPolicy.declared(
                    read_only=True,
                    permissions=["market_data:read"],
                ),
            )
        )
    return registry


class TestPlanningConfigDefaultOff(unittest.TestCase):
    def test_default_disabled(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AGENT_PLANNING_ENABLED", None)
            settings = load_planning_settings()
        self.assertFalse(settings.enabled)
        self.assertEqual(settings.strategy, "auto")
        self.assertEqual(settings.max_plan_steps, 8)
        self.assertEqual(settings.max_replans, 1)


class TestPlanStructureValidation(unittest.TestCase):
    def test_valid_plan(self):
        plan = validate_plan_payload(
            {
                "goal": "Analyze 600519",
                "max_steps": 4,
                "steps": [
                    {
                        "id": 1,
                        "goal": "Quotes",
                        "expected_tools": ["get_realtime_quote", "unknown_tool"],
                        "success_criteria": "quote returned",
                    }
                ],
            },
            available_tools=["get_realtime_quote"],
            max_steps=4,
        )
        self.assertEqual(plan.step_count, 1)
        self.assertEqual(plan.expected_tool_names, ("get_realtime_quote",))

    def test_rejects_too_many_steps(self):
        with self.assertRaises(ValueError):
            validate_plan_payload(
                {
                    "goal": "x",
                    "steps": [
                        {
                            "id": i,
                            "goal": f"s{i}",
                            "expected_tools": [],
                            "success_criteria": "ok",
                        }
                        for i in range(1, 6)
                    ],
                },
                available_tools=[],
                max_steps=3,
            )

    def test_rejects_missing_success_criteria(self):
        with self.assertRaises(ValueError):
            validate_plan_payload(
                {
                    "goal": "x",
                    "steps": [{"id": 1, "goal": "a", "expected_tools": []}],
                },
                available_tools=[],
                max_steps=3,
            )


class TestPlanningEngineTemplate(unittest.TestCase):
    def test_template_plan_applied(self):
        from src.agent.planning.config import PlanningSettings

        engine = PlanningEngine(
            PlanningSettings(
                enabled=True,
                strategy="template",
                max_plan_steps=8,
                max_replans=1,
            )
        )
        tools = [
            "get_realtime_quote",
            "get_daily_history",
            "analyze_trend",
            "get_chip_distribution",
            "search_stock_news",
        ]
        outcome = engine.plan(
            "Analyze 600519",
            available_tools=tools,
            context={"stock_code": "600519"},
        )
        self.assertTrue(outcome.enabled)
        self.assertTrue(outcome.applied)
        self.assertIsNotNone(outcome.plan)
        assert outcome.plan is not None
        self.assertGreaterEqual(outcome.plan.step_count, 2)
        self.assertIn("get_realtime_quote", outcome.plan.expected_tool_names)

    def test_max_plan_steps_cap(self):
        from src.agent.planning.config import PlanningSettings

        engine = PlanningEngine(
            PlanningSettings(
                enabled=True,
                strategy="template",
                max_plan_steps=2,
                max_replans=0,
            )
        )
        outcome = engine.plan(
            "Analyze",
            available_tools=[
                "get_realtime_quote",
                "get_daily_history",
                "analyze_trend",
                "search_stock_news",
            ],
        )
        self.assertTrue(outcome.applied)
        assert outcome.plan is not None
        self.assertLessEqual(outcome.plan.step_count, 2)


class TestPlanningFallback(unittest.TestCase):
    def test_llm_failure_degrades_to_direct_after_replans(self):
        from src.agent.planning.config import PlanningSettings

        class BoomAdapter:
            def call_completion(self, *args, **kwargs):
                raise RuntimeError("planner unavailable")

        engine = PlanningEngine(
            PlanningSettings(
                enabled=True,
                strategy="llm",
                max_plan_steps=4,
                max_replans=0,
            ),
            llm_adapter=BoomAdapter(),
        )
        # max_replans=0 and strategy llm: first failure may switch to template
        # because engine tries template on llm failure when attempts remain.
        # With max_attempts=1, only one try — should fallback without apply if
        # only llm path is taken and fails without remaining attempts.
        outcome = engine.plan("task", available_tools=["get_realtime_quote"])
        # Engine may still apply template on the same attempt chain when llm fails
        # mid-loop; with max_replans=0, attempt 0 fails llm then continues if
        # attempt+1 < max_attempts is false... so applied should be False.
        self.assertTrue(outcome.enabled)
        self.assertFalse(outcome.applied)
        self.assertIsNotNone(outcome.fallback_reason)

    def test_llm_failure_with_replan_uses_template(self):
        from src.agent.planning.config import PlanningSettings

        class BoomAdapter:
            def call_completion(self, *args, **kwargs):
                raise RuntimeError("planner unavailable")

        engine = PlanningEngine(
            PlanningSettings(
                enabled=True,
                strategy="llm",
                max_plan_steps=4,
                max_replans=1,
            ),
            llm_adapter=BoomAdapter(),
        )
        outcome = engine.plan(
            "Analyze 600519",
            available_tools=["get_realtime_quote", "get_daily_history"],
            context={"stock_code": "600519"},
        )
        self.assertTrue(outcome.applied)
        self.assertEqual(outcome.strategy, "template")


class TestPrepareRunWithPlanning(unittest.TestCase):
    def test_disabled_preserves_task_and_context_identity(self):
        ctx = {"stock_code": "600519"}
        with patch.dict(os.environ, {"AGENT_PLANNING_ENABLED": "false"}):
            task, context, meta = prepare_run_with_planning(
                task="Analyze 600519",
                context=ctx,
                available_tools=["get_realtime_quote"],
            )
        self.assertIs(context, ctx)
        self.assertEqual(task, "Analyze 600519")
        self.assertFalse(meta["enabled"])
        self.assertFalse(meta["applied"])
        self.assertNotIn("Execution Plan", task)

    def test_enabled_injects_plan_section(self):
        ctx = {"stock_code": "600519"}
        with patch.dict(
            os.environ,
            {
                "AGENT_PLANNING_ENABLED": "true",
                "AGENT_PLANNING_STRATEGY": "template",
            },
        ):
            task, context, meta = prepare_run_with_planning(
                task="Analyze 600519",
                context=ctx,
                available_tools=[
                    "get_realtime_quote",
                    "get_daily_history",
                    "analyze_trend",
                ],
            )
        self.assertTrue(meta["applied"])
        self.assertIn("Execution Plan", task)
        self.assertIsNot(context, ctx)
        assert context is not None
        self.assertIn("agent_execution_plan", context)
        self.assertEqual(context["agent_execution_plan"]["version"], "agent-plan-v1")


class TestExecutorPlanningHook(unittest.TestCase):
    """Enable/disable parity through AgentExecutor.run without network."""

    def _build_executor(self, *, tools: Optional[List[str]] = None):
        from src.agent.executor import AgentExecutor
        from src.agent.llm_adapter import LLMResponse

        names = tools or [
            "get_realtime_quote",
            "get_daily_history",
            "analyze_trend",
            "search_stock_news",
        ]
        registry = _tool_registry(*names)

        class StubAdapter:
            def __init__(self):
                self.calls = 0
                self.messages_seen: List[Any] = []
                self.primary_model = "stub-model"
                self._config = SimpleNamespace()

            def call_with_tools(self, messages, tools=None, **kwargs):
                self.calls += 1
                self.messages_seen.append(messages)
                # Final answer without tools so the loop ends quickly.
                dashboard = {
                    "decision": {"action": "hold", "confidence": 0.5},
                    "summary": "stub",
                }
                return LLMResponse(
                    content=json.dumps(dashboard, ensure_ascii=False),
                    tool_calls=[],
                    usage={"total_tokens": 100},
                    provider="stub",
                    model="stub-model",
                )

            def call_completion(self, messages, tools=None, **kwargs):
                return self.call_with_tools(messages, tools=tools, **kwargs)

        adapter = StubAdapter()
        executor = AgentExecutor(
            registry,
            adapter,
            max_steps=3,
            timeout_seconds=5.0,
        )
        return executor, adapter

    def test_default_off_run_has_inert_planning_meta(self):
        executor, adapter = self._build_executor()
        with patch.dict(os.environ, {"AGENT_PLANNING_ENABLED": "false"}):
            result = executor.run("Analyze 600519", context={"stock_code": "600519"})
        self.assertIsNotNone(result.planning)
        assert result.planning is not None
        self.assertFalse(result.planning.get("enabled"))
        self.assertFalse(result.planning.get("applied"))
        # User message should not include planning section.
        user_msgs = [
            m.get("content", "")
            for m in result.messages
            if m.get("role") == "user"
        ]
        self.assertTrue(user_msgs)
        self.assertNotIn("Execution Plan", user_msgs[0])
        self.assertGreaterEqual(adapter.calls, 1)

    def test_enabled_run_attaches_plan_and_injects_prompt(self):
        executor, adapter = self._build_executor()
        with patch.dict(
            os.environ,
            {
                "AGENT_PLANNING_ENABLED": "true",
                "AGENT_PLANNING_STRATEGY": "template",
            },
        ):
            result = executor.run("Analyze 600519", context={"stock_code": "600519"})
        self.assertIsNotNone(result.planning)
        assert result.planning is not None
        self.assertTrue(result.planning.get("enabled"))
        self.assertTrue(result.planning.get("applied"))
        self.assertIn("plan", result.planning)
        user_msgs = [
            m.get("content", "")
            for m in result.messages
            if m.get("role") == "user"
        ]
        self.assertTrue(any("Execution Plan" in (msg or "") for msg in user_msgs))
        self.assertGreaterEqual(adapter.calls, 1)

    def test_enable_vs_disable_comparison_evidence(self):
        """Same input: planning on injects plan; off does not. Token/step fields recorded."""
        executor_off, adapter_off = self._build_executor()
        executor_on, adapter_on = self._build_executor()
        task = "Analyze 600519 for short-term risk"
        ctx = {"stock_code": "600519"}

        with patch.dict(os.environ, {"AGENT_PLANNING_ENABLED": "false"}):
            off = executor_off.run(task, context=dict(ctx))
        with patch.dict(
            os.environ,
            {
                "AGENT_PLANNING_ENABLED": "true",
                "AGENT_PLANNING_STRATEGY": "template",
            },
        ):
            on = executor_on.run(task, context=dict(ctx))

        off_user = next(m["content"] for m in off.messages if m.get("role") == "user")
        on_user = next(m["content"] for m in on.messages if m.get("role") == "user")

        comparison = {
            "input": task,
            "disabled": {
                "planning_applied": bool(off.planning and off.planning.get("applied")),
                "total_steps": off.total_steps,
                "total_tokens": off.total_tokens,
                "tool_calls": len(off.tool_calls_log),
                "user_message_chars": len(off_user or ""),
                "has_execution_plan_section": "Execution Plan" in (off_user or ""),
            },
            "enabled": {
                "planning_applied": bool(on.planning and on.planning.get("applied")),
                "total_steps": on.total_steps,
                "total_tokens": on.total_tokens,
                "tool_calls": len(on.tool_calls_log),
                "user_message_chars": len(on_user or ""),
                "has_execution_plan_section": "Execution Plan" in (on_user or ""),
                "plan_step_count": (on.planning or {}).get("step_count"),
                "expected_tools": (on.planning or {}).get("expected_tools"),
            },
        }
        # Persistable evidence for the PR (also asserted below).
        self.assertFalse(comparison["disabled"]["planning_applied"])
        self.assertFalse(comparison["disabled"]["has_execution_plan_section"])
        self.assertTrue(comparison["enabled"]["planning_applied"])
        self.assertTrue(comparison["enabled"]["has_execution_plan_section"])
        self.assertGreater(
            comparison["enabled"]["user_message_chars"],
            comparison["disabled"]["user_message_chars"],
        )
        # Stub loop does not call tools; step/token counts remain comparable budgets.
        self.assertIsInstance(comparison["disabled"]["total_steps"], int)
        self.assertIsInstance(comparison["enabled"]["total_steps"], int)
        # Evidence object is JSON-serializable for PR paste.
        json.dumps(comparison)


class TestDisabledPathParityWithDirectBuild(unittest.TestCase):
    def test_disabled_prepare_matches_original_task_bytes(self):
        task = "Analyze 600519"
        ctx = {"stock_code": "600519", "report_language": "zh"}
        with patch.dict(os.environ, {"AGENT_PLANNING_ENABLED": "false"}):
            out_task, out_ctx, meta = prepare_run_with_planning(
                task=task,
                context=ctx,
                available_tools=["get_realtime_quote"],
            )
        self.assertEqual(out_task, task)
        self.assertIs(out_ctx, ctx)
        self.assertEqual(
            json.dumps(meta, sort_keys=True),
            json.dumps(
                {
                    "enabled": False,
                    "applied": False,
                    "strategy": "none",
                    "replan_attempts": 0,
                    "planning_tokens": 0,
                    "planning_model": "",
                    "schema_version": "agent-plan-v1",
                },
                sort_keys=True,
            ),
        )


if __name__ == "__main__":
    unittest.main()
