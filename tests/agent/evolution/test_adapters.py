# -*- coding: utf-8 -*-
"""Red-contract tests for gated online evolution adapters (Issue #1091)."""

from __future__ import annotations

import inspect
import logging
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from src.agent.evolution.adapters import (
    ADAPTER_INFLUENCE_META_KEY,
    calibrate_confidence,
    is_online_adapters_enabled,
    prefer_route,
    rank_tools,
    record_adapter_influence,
)
from src.agent.evolution.guards import (
    snapshot_soul_identity,
    snapshot_tool_surface_denials,
)
from src.agent.memory import AgentMemory, CalibrationResult
from src.agent.protocols import AgentContext, AgentOpinion, StageResult, StageStatus
from src.agent.soul import AGENT_SOUL_HASH
from src.agent.tools.execution import ToolAccessContext
from src.agent.tools.registry import ToolDefinition, ToolParameter, ToolPolicy, ToolRegistry
from src.agent.tools.surface import ToolSurface
from src.schemas.agent_episode import AgentEpisodeCreate

_TEST_CAPABILITY = "analysis_context:read"


def _config(*, enabled: bool = False, min_samples: int = 30) -> SimpleNamespace:
    return SimpleNamespace(
        agent_online_adapters_enabled=enabled,
        agent_online_adapters_min_samples=min_samples,
        agent_memory_enabled=True,
    )


def _memory(
    *,
    enabled: bool = True,
    samples: int = 40,
    accuracy: float = 0.5,
    avg_confidence: float = 0.9,
    min_samples: int = 30,
) -> AgentMemory:
    """Real AgentMemory.get_calibration; only the stats source is stubbed."""
    memory = AgentMemory(enabled=enabled, min_samples=min_samples)

    def _get_accuracy_stats(
        agent_name: str,
        stock_code: Optional[str],
        skill_id: Optional[str],
    ) -> Dict[str, Any]:
        return {
            "total": samples,
            "accuracy": accuracy,
            "direction_accuracy": accuracy,
            "avg_confidence": avg_confidence,
        }

    memory._get_accuracy_stats = _get_accuracy_stats  # type: ignore[method-assign]
    return memory


def _memory_with_result(result: CalibrationResult, *, enabled: bool = True) -> AgentMemory:
    """Inject a stored CalibrationResult to prove wrap uses calibration_factor."""
    memory = AgentMemory(enabled=enabled, min_samples=30)

    def _get_calibration(
        agent_name: str,
        stock_code: Optional[str] = None,
        skill_id: Optional[str] = None,
        strategy_id: Optional[str] = None,
    ) -> CalibrationResult:
        return CalibrationResult(
            agent_name=agent_name,
            total_samples=result.total_samples,
            historical_accuracy=result.historical_accuracy,
            avg_confidence=result.avg_confidence,
            calibrated=result.calibrated,
            calibration_factor=result.calibration_factor,
        )

    memory.get_calibration = _get_calibration  # type: ignore[method-assign]
    return memory


def _echo_registry(calls: List[Any]) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="echo",
            description="Echo a message.",
            parameters=[
                ToolParameter(name="message", type="string", description="Message"),
            ],
            handler=lambda message: calls.append(message) or {"message": message},
            category="data",
            policy=ToolPolicy.declared(
                read_only=True,
                side_effects=[],
                permissions=[_TEST_CAPABILITY],
            ),
        )
    )
    return registry


def test_config_defaults_are_disabled_with_thirty_samples() -> None:
    from src.config import Config

    config = Config()
    assert config.agent_online_adapters_enabled is False
    assert config.agent_online_adapters_min_samples == 30
    assert is_online_adapters_enabled(config) is False


def test_adapter_public_exports_importable() -> None:
    from src.agent.evolution.adapters import (
        ADAPTER_INFLUENCE_META_KEY as meta_key,
        is_online_adapters_enabled as enabled_fn,
        calibrate_confidence as calibrate_fn,
        rank_tools as rank_fn,
        prefer_route as route_fn,
        record_adapter_influence as record_fn,
    )

    assert meta_key == "adapter_influence"
    assert callable(enabled_fn)
    assert callable(calibrate_fn)
    assert callable(rank_fn)
    assert callable(route_fn)
    assert callable(record_fn)


def test_flag_off_and_missing_config_are_identity() -> None:
    memory = _memory(enabled=True, samples=80, accuracy=0.2, avg_confidence=0.9)
    raw = 0.8

    off_value, off_meta = calibrate_confidence(
        raw,
        memory=memory,
        agent_name="technical",
        stock_code="600519",
        min_samples=30,
        config=_config(enabled=False),
    )
    missing_value, missing_meta = calibrate_confidence(
        raw,
        memory=memory,
        agent_name="technical",
        stock_code="600519",
        min_samples=30,
        config=None,
    )
    empty_value, empty_meta = calibrate_confidence(
        raw,
        memory=memory,
        agent_name="technical",
        stock_code="600519",
        min_samples=30,
        config=SimpleNamespace(),
    )

    assert off_value == raw
    assert missing_value == raw
    assert empty_value == raw
    assert off_meta["applied"] is False
    assert off_meta["factor"] == 1.0
    assert missing_meta["applied"] is False
    assert empty_meta["applied"] is False
    assert is_online_adapters_enabled(_config(enabled=False)) is False
    assert is_online_adapters_enabled(None) is False
    assert is_online_adapters_enabled(SimpleNamespace()) is False

    assert rank_tools(["news", "quote", "risk"]) == ["news", "quote", "risk"]
    assert prefer_route("quick") == "quick"
    assert prefer_route("standard") == "standard"

    ctx = AgentContext(stock_code="600519")
    record_adapter_influence(
        ctx,
        {"confidence": {"applied": True, "factor": 0.5, "samples": 80, "reason": "applied"}},
        config=_config(enabled=False),
    )
    assert ADAPTER_INFLUENCE_META_KEY not in ctx.meta

    record_adapter_influence(ctx, {"confidence": {"applied": True}}, config=None)
    assert ADAPTER_INFLUENCE_META_KEY not in ctx.meta


def test_below_threshold_is_identity_factor() -> None:
    memory = _memory(enabled=True, samples=29, accuracy=0.1, avg_confidence=0.95)
    raw = 0.7
    adjusted, meta = calibrate_confidence(
        raw,
        memory=memory,
        agent_name="technical",
        stock_code="600519",
        min_samples=30,
        config=_config(enabled=True),
    )

    assert adjusted == raw
    assert meta["applied"] is False
    assert meta["factor"] == 1.0
    assert meta["samples"] == 29
    assert meta["reason"] == "insufficient_samples"

    ctx = AgentContext(stock_code="600519")
    record_adapter_influence(ctx, {"confidence": meta, "mode": "full"}, config=_config(enabled=True))
    influence = ctx.meta[ADAPTER_INFLUENCE_META_KEY]
    assert influence["confidence"]["applied"] is False
    assert influence["confidence"]["factor"] == 1.0
    assert influence["tool_effectiveness"] == {"applied": False, "reason": "stub_neutral"}
    assert influence["route_preference"]["applied"] is False
    assert influence["route_preference"]["reason"] == "stub_neutral"
    assert influence["route_preference"]["mode"] == "full"


def test_above_threshold_monotonic_calibration_and_clamp() -> None:
    config = _config(enabled=True)
    over_memory = _memory(enabled=True, samples=40, accuracy=0.4, avg_confidence=0.9)
    under_memory = _memory(enabled=True, samples=40, accuracy=0.8, avg_confidence=0.4)
    clamp_low = _memory(enabled=True, samples=40, accuracy=0.1, avg_confidence=1.0)
    clamp_high = _memory(enabled=True, samples=40, accuracy=1.0, avg_confidence=0.1)
    raw = 0.6

    over_value, over_meta = calibrate_confidence(
        raw,
        memory=over_memory,
        agent_name="technical",
        stock_code="600519",
        min_samples=30,
        config=config,
    )
    under_value, under_meta = calibrate_confidence(
        raw,
        memory=under_memory,
        agent_name="technical",
        stock_code="600519",
        min_samples=30,
        config=config,
    )
    low_value, low_meta = calibrate_confidence(
        raw,
        memory=clamp_low,
        agent_name="technical",
        stock_code="600519",
        min_samples=30,
        config=config,
    )
    high_value, high_meta = calibrate_confidence(
        raw,
        memory=clamp_high,
        agent_name="technical",
        stock_code="600519",
        min_samples=30,
        config=config,
    )

    assert over_meta["applied"] is True
    assert over_meta["factor"] < 1.0
    assert over_value < raw
    assert under_meta["applied"] is True
    assert under_meta["factor"] > 1.0
    assert under_value > raw
    assert low_meta["factor"] == 0.5
    assert high_meta["factor"] == 1.5
    assert 0.0 <= low_value <= 1.0
    assert 0.0 <= high_value <= 1.0
    assert high_value == pytest.approx(0.9)

    ctx = AgentContext(stock_code="600519")
    record_adapter_influence(
        ctx,
        {"confidence": over_meta, "mode": "standard", "unexpected": {"drop": True}},
        config=config,
    )
    influence = ctx.meta[ADAPTER_INFLUENCE_META_KEY]
    assert set(influence) == {"confidence", "tool_effectiveness", "route_preference"}
    assert "unexpected" not in influence
    assert influence["confidence"]["applied"] is True
    assert influence["confidence"]["factor"] < 1.0


def test_memory_disabled_is_identity_when_adapters_on() -> None:
    memory = _memory(enabled=False, samples=80, accuracy=0.1, avg_confidence=0.95)
    raw = 0.75
    adjusted, meta = calibrate_confidence(
        raw,
        memory=memory,
        agent_name="technical",
        stock_code=None,
        min_samples=30,
        config=_config(enabled=True),
    )
    assert adjusted == raw
    assert meta["applied"] is False
    assert meta["factor"] == 1.0
    assert meta["reason"] == "memory_disabled"


def test_denied_tool_stays_permission_denied_and_snapshots_unchanged() -> None:
    calls: List[Any] = []
    surface = ToolSurface(_echo_registry(calls))
    denied = ("echo",)
    denials = ("permission_denied",)
    soul_before = snapshot_soul_identity()
    tools_before = snapshot_tool_surface_denials(
        surface,
        denied_tools=denied,
        denial_codes=denials,
    )
    soul_hash_before = AGENT_SOUL_HASH

    ranked = rank_tools(["echo", "quote"], denied_names=["echo"])
    assert ranked[0] == "echo"
    assert rank_tools(["quote"], denied_names=["echo"]) == ["quote"]
    assert rank_tools(["quote", "echo"], denied_names=["echo"]) == ["quote", "echo"]

    result = surface.execute_tool(
        ranked[0],
        {"message": "should-not-run"},
        ToolAccessContext(),
    )

    assert result["error"]["code"] == "permission_denied"
    assert calls == []
    assert AGENT_SOUL_HASH == soul_hash_before
    assert snapshot_soul_identity() == soul_before
    assert tools_before == snapshot_tool_surface_denials(
        surface,
        denied_tools=denied,
        denial_codes=denials,
    )


def test_zero_accuracy_uses_agent_memory_calibration_factor_not_truthy_fallback() -> None:
    """Reviewer counterexample: historical_accuracy=0.0 must not invert the clamp.

    AgentMemory clamps 0.0 / 0.4 to factor 0.5, so raw 0.6 becomes 0.3.
    Re-deriving with ``accuracy or 0.5`` would yield 1.25 and raise confidence
    to 0.75.
    """
    memory = _memory(enabled=True, samples=40, accuracy=0.0, avg_confidence=0.4)
    raw = 0.6
    cal = memory.get_calibration("technical", stock_code="600519")
    assert cal.historical_accuracy == 0.0
    assert cal.avg_confidence == 0.4
    assert cal.calibrated is True
    assert cal.calibration_factor == pytest.approx(0.5)

    adjusted, meta = calibrate_confidence(
        raw,
        memory=memory,
        agent_name="technical",
        stock_code="600519",
        min_samples=30,
        config=_config(enabled=True),
    )

    inverted_by_truthy_fallback = raw * (0.5 / 0.4)
    memory_adjusted = memory.calibrate_confidence("technical", raw, stock_code="600519")
    assert inverted_by_truthy_fallback == pytest.approx(0.75)
    assert memory_adjusted == pytest.approx(0.3)
    assert adjusted == pytest.approx(0.3)
    assert adjusted == pytest.approx(memory_adjusted)
    assert adjusted == pytest.approx(raw * cal.calibration_factor)
    assert adjusted != pytest.approx(inverted_by_truthy_fallback)
    assert adjusted < raw
    assert meta["applied"] is True
    assert meta["factor"] == pytest.approx(0.5)
    assert meta["samples"] == 40
    assert meta["reason"] == "applied"

    ctx_a = AgentContext(stock_code="600519")
    ctx_b = AgentContext(stock_code="600519")
    record_adapter_influence(ctx_a, {"confidence": meta}, config=_config(enabled=True))
    recorded = ctx_a.meta[ADAPTER_INFLUENCE_META_KEY]["confidence"]
    assert recorded["applied"] is True
    assert recorded["factor"] == pytest.approx(0.5)
    assert ADAPTER_INFLUENCE_META_KEY not in ctx_b.meta
    record_adapter_influence(ctx_b, {"confidence": meta}, config=_config(enabled=True))
    assert ctx_a.meta is not ctx_b.meta
    assert ctx_b.meta[ADAPTER_INFLUENCE_META_KEY]["confidence"]["factor"] == pytest.approx(0.5)


def test_calibration_factor_table_for_accuracy_zero_half_and_one() -> None:
    config = _config(enabled=True)
    cases = [
        # accuracy, avg_confidence, raw, expected_factor, expected_adjusted
        (0.0, 0.4, 0.6, 0.5, 0.3),
        (0.0, 0.4, 0.0, 0.5, 0.0),
        (0.0, 0.4, 1.0, 0.5, 0.5),
        (0.5, 0.5, 0.6, 1.0, 0.6),
        (0.5, 1.0, 0.6, 0.5, 0.3),
        (0.5, 0.25, 0.6, 1.5, 0.9),
        (1.0, 1.0, 0.6, 1.0, 0.6),
        (1.0, 0.4, 0.6, 1.5, 0.9),
        (1.0, 0.4, 1.0, 1.5, 1.0),
        (1.0, 0.0, 0.6, 1.0, 0.6),
    ]
    for accuracy, avg_confidence, raw, expected_factor, expected_adjusted in cases:
        memory = _memory(
            enabled=True,
            samples=40,
            accuracy=accuracy,
            avg_confidence=avg_confidence,
        )
        cal = memory.get_calibration("technical", stock_code="600519")
        assert cal.historical_accuracy == accuracy
        assert cal.calibration_factor == pytest.approx(expected_factor)
        adjusted, meta = calibrate_confidence(
            raw,
            memory=memory,
            agent_name="technical",
            stock_code="600519",
            min_samples=30,
            config=config,
        )
        assert meta["applied"] is True
        assert meta["factor"] == pytest.approx(expected_factor)
        assert adjusted == pytest.approx(expected_adjusted)
        assert 0.0 <= adjusted <= 1.0


def test_adapter_applies_stored_calibration_factor_not_rederived_ratio() -> None:
    """Wrap must use calibration_factor even when it disagrees with accuracy/avg."""
    result = CalibrationResult(
        agent_name="technical",
        total_samples=40,
        historical_accuracy=1.0,
        avg_confidence=0.4,
        calibrated=True,
        calibration_factor=0.5,
    )
    memory = _memory_with_result(result)
    raw = 0.6
    rederived = raw * min(1.5, max(0.5, 1.0 / 0.4))
    adjusted, meta = calibrate_confidence(
        raw,
        memory=memory,
        agent_name="technical",
        stock_code="600519",
        min_samples=30,
        config=_config(enabled=True),
    )
    assert rederived == pytest.approx(0.9)
    assert adjusted == pytest.approx(0.3)
    assert adjusted != pytest.approx(rederived)
    assert meta["factor"] == pytest.approx(0.5)


def test_uncalibrated_result_is_identity_even_with_non_neutral_factor() -> None:
    result = CalibrationResult(
        agent_name="technical",
        total_samples=40,
        historical_accuracy=0.0,
        avg_confidence=0.4,
        calibrated=False,
        calibration_factor=0.5,
    )
    memory = _memory_with_result(result)
    raw = 0.6
    adjusted, meta = calibrate_confidence(
        raw,
        memory=memory,
        agent_name="technical",
        stock_code="600519",
        min_samples=30,
        config=_config(enabled=True),
    )
    assert adjusted == raw
    assert meta["applied"] is False
    assert meta["factor"] == 1.0
    assert meta["samples"] == 40
    assert meta["reason"] == "insufficient_samples"


def _make_base_agent(
    memory: AgentMemory,
    *,
    agent_name: str = "technical",
    config: Any = None,
):
    from src.agent.agents.base_agent import BaseAgent

    class DummyAgent(BaseAgent):
        def system_prompt(self, ctx):
            return "system"

        def build_user_message(self, ctx):
            return "user"

        def post_process(self, ctx, raw_text):
            return AgentOpinion(
                agent_name=self.agent_name,
                signal="buy",
                confidence=0.6,
                reasoning=raw_text,
            )

    DummyAgent.agent_name = agent_name
    with patch("src.agent.agents.base_agent.AgentMemory.from_config", return_value=memory):
        return DummyAgent(
            tool_registry=MagicMock(),
            llm_adapter=MagicMock(),
            config=config,
        )


def _loop_result() -> Any:
    return SimpleNamespace(
        success=True,
        content='{"signal":"buy","confidence":0.6,"reasoning":"ok"}',
        total_tokens=12,
        tool_calls_log=[],
        models_used=["test/model"],
    )


def _patch_live_adapter_config(config: Any):
    return patch(
        "src.application_services.get_application_services",
        return_value=SimpleNamespace(config=config),
    )


def _run_agent(agent: Any, ctx: AgentContext, *, adapters_enabled: bool) -> Any:
    agent.config = _config(enabled=adapters_enabled)
    with patch(
        "src.agent.agents.base_agent.run_agent_loop",
        return_value=_loop_result(),
    ):
        return agent.run(ctx)


def test_base_agent_flag_off_keeps_ungated_memory_multiply() -> None:
    memory = _memory(enabled=True, samples=40, accuracy=0.0, avg_confidence=0.4)
    agent = _make_base_agent(memory)
    ctx = AgentContext(query="test", stock_code="600519")
    opinion = AgentOpinion(agent_name="technical", signal="buy", confidence=0.6, reasoning="ok")
    result = StageResult(stage_name="technical", status=StageStatus.RUNNING)

    with _patch_live_adapter_config(_config(enabled=False)):
        with patch(
            "src.agent.agents.base_agent.calibrate_confidence",
            wraps=calibrate_confidence,
        ) as spy:
            agent._apply_memory_calibration(ctx, opinion, result)

    spy.assert_not_called()
    assert opinion.confidence == pytest.approx(0.3)
    assert result.meta["memory_calibration"]["factor"] == pytest.approx(0.5)
    assert ADAPTER_INFLUENCE_META_KEY not in ctx.meta


def test_base_agent_flag_off_keeps_ungated_multiply_on_run_path() -> None:
    memory = _memory(enabled=True, samples=40, accuracy=0.0, avg_confidence=0.4)
    agent = _make_base_agent(memory)
    ctx = AgentContext(query="test", stock_code="600519")

    with patch(
        "src.agent.agents.base_agent.calibrate_confidence",
        wraps=calibrate_confidence,
    ) as spy:
        result = _run_agent(agent, ctx, adapters_enabled=False)

    spy.assert_not_called()
    assert result.success
    assert result.opinion is not None
    assert result.opinion.confidence == pytest.approx(0.3)
    assert ctx.opinions[0].confidence == pytest.approx(0.3)
    assert result.meta["memory_calibration"]["factor"] == pytest.approx(0.5)
    assert result.meta["memory_calibration"]["samples"] == 40
    assert ADAPTER_INFLUENCE_META_KEY not in ctx.meta


def test_base_agent_missing_config_keeps_ungated_memory_multiply() -> None:
    memory = _memory(enabled=True, samples=40, accuracy=0.0, avg_confidence=0.4)
    agent = _make_base_agent(memory)
    ctx = AgentContext(query="test", stock_code="600519")
    opinion = AgentOpinion(agent_name="technical", signal="buy", confidence=0.6, reasoning="ok")
    result = StageResult(stage_name="technical", status=StageStatus.RUNNING)

    with patch(
        "src.application_services.get_application_services",
        side_effect=RuntimeError("config missing"),
    ):
        with patch("src.agent.agents.base_agent.log_safe_exception") as safe_log:
            agent._apply_memory_calibration(ctx, opinion, result)

    assert opinion.confidence == pytest.approx(0.3)
    assert result.meta["memory_calibration"]["factor"] == pytest.approx(0.5)
    assert ADAPTER_INFLUENCE_META_KEY not in ctx.meta
    safe_log.assert_called_once()
    assert safe_log.call_args.args[1] == (
        "Online adapter config lookup failed; keeping ungated memory calibration"
    )
    assert isinstance(safe_log.call_args.args[2], RuntimeError)
    assert safe_log.call_args.kwargs["error_code"] == "agent_online_adapter_config_unavailable"
    assert safe_log.call_args.kwargs["level"] == logging.WARNING
    assert safe_log.call_args.kwargs["context"] == {"agent": agent.agent_name}

    missing_attr_ctx = AgentContext(query="test", stock_code="600519")
    missing_attr_opinion = AgentOpinion(
        agent_name="technical", signal="buy", confidence=0.6, reasoning="ok"
    )
    missing_attr_result = StageResult(stage_name="technical", status=StageStatus.RUNNING)
    with _patch_live_adapter_config(SimpleNamespace()):
        with patch("src.agent.agents.base_agent.log_safe_exception") as missing_attr_log:
            agent._apply_memory_calibration(
                missing_attr_ctx, missing_attr_opinion, missing_attr_result
            )
    missing_attr_log.assert_not_called()
    assert missing_attr_opinion.confidence == pytest.approx(0.3)
    assert ADAPTER_INFLUENCE_META_KEY not in missing_attr_ctx.meta


def test_base_agent_injected_config_skips_composition_root_lookup() -> None:
    memory = _memory(enabled=True, samples=40, accuracy=0.0, avg_confidence=0.4)
    gated_agent = _make_base_agent(memory, config=_config(enabled=True))
    gated_ctx = AgentContext(query="test", stock_code="600519")
    gated_opinion = AgentOpinion(
        agent_name="technical", signal="buy", confidence=0.6, reasoning="ok"
    )
    gated_result = StageResult(stage_name="technical", status=StageStatus.RUNNING)

    with patch(
        "src.application_services.get_application_services",
        side_effect=AssertionError("injected config must not look up composition root"),
    ) as get_services:
        with patch("src.agent.agents.base_agent.log_safe_exception") as safe_log:
            gated_agent._apply_memory_calibration(gated_ctx, gated_opinion, gated_result)

    get_services.assert_not_called()
    safe_log.assert_not_called()
    assert gated_opinion.confidence == pytest.approx(0.3)
    assert "memory_calibration" not in gated_result.meta
    assert gated_ctx.meta[ADAPTER_INFLUENCE_META_KEY]["confidence"]["applied"] is True

    ungated_agent = _make_base_agent(memory, config=_config(enabled=False))
    ungated_ctx = AgentContext(query="test", stock_code="600519")
    ungated_opinion = AgentOpinion(
        agent_name="technical", signal="buy", confidence=0.6, reasoning="ok"
    )
    ungated_result = StageResult(stage_name="technical", status=StageStatus.RUNNING)
    with patch(
        "src.application_services.get_application_services",
        side_effect=AssertionError("injected config must not look up composition root"),
    ) as ungated_services:
        with patch("src.agent.agents.base_agent.log_safe_exception") as ungated_log:
            ungated_agent._apply_memory_calibration(
                ungated_ctx, ungated_opinion, ungated_result
            )
    ungated_services.assert_not_called()
    ungated_log.assert_not_called()
    assert ungated_opinion.confidence == pytest.approx(0.3)
    assert ungated_result.meta["memory_calibration"]["factor"] == pytest.approx(0.5)
    assert ADAPTER_INFLUENCE_META_KEY not in ungated_ctx.meta


def test_base_agent_flag_on_applies_adapter_once_without_double_multiply() -> None:
    memory = _memory(enabled=True, samples=40, accuracy=0.0, avg_confidence=0.4)
    agent = _make_base_agent(memory)
    ctx = AgentContext(query="test", stock_code="600519")
    opinion = AgentOpinion(agent_name="technical", signal="buy", confidence=0.6, reasoning="ok")
    result = StageResult(stage_name="technical", status=StageStatus.RUNNING)
    raw = 0.6
    double_multiplied = raw * 0.5 * 0.5
    inverted = raw * (0.5 / 0.4)

    with _patch_live_adapter_config(_config(enabled=True)):
        with patch(
            "src.agent.agents.base_agent.calibrate_confidence",
            wraps=calibrate_confidence,
        ) as calibrate_spy:
            with patch(
                "src.agent.evolution.adapters.rank_tools",
                wraps=rank_tools,
            ) as rank_spy:
                with patch(
                    "src.agent.evolution.adapters.prefer_route",
                    wraps=prefer_route,
                ) as route_spy:
                    agent._apply_memory_calibration(ctx, opinion, result)

    assert calibrate_spy.call_count == 1
    rank_spy.assert_not_called()
    route_spy.assert_not_called()
    assert opinion.confidence == pytest.approx(0.3)
    assert opinion.confidence != pytest.approx(double_multiplied)
    assert opinion.confidence != pytest.approx(inverted)
    assert "memory_calibration" not in result.meta
    influence = ctx.meta[ADAPTER_INFLUENCE_META_KEY]
    assert influence["confidence"]["applied"] is True
    assert influence["confidence"]["factor"] == pytest.approx(0.5)
    assert influence["confidence"]["samples"] == 40
    assert influence["tool_effectiveness"] == {"applied": False, "reason": "stub_neutral"}
    assert influence["route_preference"]["applied"] is False
    assert set(influence) == {"confidence", "tool_effectiveness", "route_preference"}


def test_base_agent_flag_on_zero_accuracy_clamps_down_on_run_path() -> None:
    memory = _memory(enabled=True, samples=40, accuracy=0.0, avg_confidence=0.4)
    agent = _make_base_agent(memory)
    ctx = AgentContext(query="test", stock_code="600519")
    other_ctx = AgentContext(query="test", stock_code="600519")
    raw = 0.6
    double_multiplied = raw * 0.5 * 0.5
    inverted = raw * (0.5 / 0.4)

    result = _run_agent(agent, ctx, adapters_enabled=True)

    assert result.success
    assert result.opinion is not None
    assert result.opinion.confidence == pytest.approx(0.3)
    assert result.opinion.confidence != pytest.approx(double_multiplied)
    assert result.opinion.confidence != pytest.approx(inverted)
    assert ctx.opinions[0].confidence == pytest.approx(0.3)
    assert "memory_calibration" not in result.meta
    recorded = ctx.meta[ADAPTER_INFLUENCE_META_KEY]["confidence"]
    assert recorded["applied"] is True
    assert recorded["factor"] == pytest.approx(0.5)
    assert recorded["reason"] == "applied"
    assert ADAPTER_INFLUENCE_META_KEY not in other_ctx.meta
    assert ctx.meta is not other_ctx.meta


def test_base_agent_flag_on_memory_disabled_is_identity_on_run_path() -> None:
    memory = _memory(enabled=False, samples=80, accuracy=0.1, avg_confidence=0.95)
    agent = _make_base_agent(memory)
    ctx = AgentContext(query="test", stock_code="600519")

    result = _run_agent(agent, ctx, adapters_enabled=True)

    assert result.success
    assert result.opinion is not None
    assert result.opinion.confidence == pytest.approx(0.6)
    assert ctx.opinions[0].confidence == pytest.approx(0.6)
    assert "memory_calibration" not in result.meta
    influence = ctx.meta[ADAPTER_INFLUENCE_META_KEY]["confidence"]
    assert influence["applied"] is False
    assert influence["factor"] == 1.0
    assert influence["reason"] == "memory_disabled"


def test_base_agent_flag_on_below_threshold_is_identity_on_run_path() -> None:
    memory = _memory(enabled=True, samples=29, accuracy=0.0, avg_confidence=0.4)
    agent = _make_base_agent(memory)
    ctx = AgentContext(query="test", stock_code="600519")

    result = _run_agent(agent, ctx, adapters_enabled=True)

    assert result.success
    assert result.opinion is not None
    assert result.opinion.confidence == pytest.approx(0.6)
    assert ctx.opinions[0].confidence == pytest.approx(0.6)
    assert "memory_calibration" not in result.meta
    influence = ctx.meta[ADAPTER_INFLUENCE_META_KEY]["confidence"]
    assert influence["applied"] is False
    assert influence["factor"] == 1.0
    assert influence["samples"] == 29
    assert influence["reason"] == "insufficient_samples"


def test_base_agent_gated_run_leaves_soul_and_denied_tools_unchanged() -> None:
    memory = _memory(enabled=True, samples=40, accuracy=0.0, avg_confidence=0.4)
    agent = _make_base_agent(memory)
    ctx = AgentContext(query="test", stock_code="600519")

    calls: List[Any] = []
    surface = ToolSurface(_echo_registry(calls))
    denied = ("echo",)
    denials = ("permission_denied",)
    soul_before = snapshot_soul_identity()
    soul_hash_before = AGENT_SOUL_HASH
    tools_before = snapshot_tool_surface_denials(
        surface,
        denied_tools=denied,
        denial_codes=denials,
    )

    result = _run_agent(agent, ctx, adapters_enabled=True)

    ranked = rank_tools(["echo", "quote"], denied_names=["echo"])
    tool_result = surface.execute_tool(
        ranked[0],
        {"message": "should-not-run"},
        ToolAccessContext(),
    )

    assert result.success
    assert result.opinion is not None
    assert result.opinion.confidence == pytest.approx(0.3)
    assert tool_result["error"]["code"] == "permission_denied"
    assert calls == []
    assert AGENT_SOUL_HASH == soul_hash_before
    assert snapshot_soul_identity() == soul_before
    assert tools_before == snapshot_tool_surface_denials(
        surface,
        denied_tools=denied,
        denial_codes=denials,
    )


def test_specialised_agents_do_not_override_memory_calibration() -> None:
    from src.agent.agents.base_agent import BaseAgent
    from src.agent.agents.decision_agent import DecisionAgent
    from src.agent.agents.intel_agent import IntelAgent
    from src.agent.agents.portfolio_agent import PortfolioAgent
    from src.agent.agents.risk_agent import RiskAgent
    from src.agent.agents.technical_agent import TechnicalAgent
    from src.agent.bull_bear_debate import BoundedBullBearDebateAgent
    from src.agent.critic import BoundedCriticAgent
    from src.agent.skills.skill_agent import SkillAgent

    for cls in (
        DecisionAgent,
        IntelAgent,
        PortfolioAgent,
        RiskAgent,
        TechnicalAgent,
        SkillAgent,
        BoundedCriticAgent,
        BoundedBullBearDebateAgent,
    ):
        assert cls._apply_memory_calibration is BaseAgent._apply_memory_calibration


def test_base_agent_does_not_hook_tool_route_overlay_or_events() -> None:
    """Supplemental source scan. Functional BaseAgent.run tests are the proof."""
    import src.agent.agents.base_agent as base_agent_mod
    from src.agent.agents.base_agent import BaseAgent

    module_source = inspect.getsource(base_agent_mod)
    hook_source = inspect.getsource(BaseAgent._apply_memory_calibration)
    gated_source = inspect.getsource(BaseAgent._apply_gated_online_calibration)
    assert "src.agent.evolution.adapters" in module_source
    assert "calibrate_confidence" in gated_source
    assert "record_adapter_influence" in gated_source
    assert "rank_tools" not in module_source
    assert "prefer_route" not in module_source
    assert "outcome_ingest" not in module_source
    assert "apply_forecast_outcome_calibration" not in module_source
    assert "EvolutionEvent" not in module_source
    assert "agent_evolution_events" not in module_source
    assert "calibration.calibration_factor" in inspect.getsource(
        BaseAgent._apply_ungated_memory_calibration
    )
    assert "adapters.calibrate_confidence" not in hook_source


def test_episode_schema_has_no_adapter_field_and_tests_do_not_update_episodes() -> None:
    field_names = set(AgentEpisodeCreate.model_fields)
    assert all("adapter" not in name.lower() for name in field_names)
    assert ADAPTER_INFLUENCE_META_KEY not in field_names
    ctx = AgentContext(stock_code="600519")
    record_adapter_influence(
        ctx,
        {"confidence": {"applied": True, "factor": 0.8, "samples": 40, "reason": "applied"}},
        config=_config(enabled=True),
    )
    assert ADAPTER_INFLUENCE_META_KEY in ctx.meta
    repo = MagicMock(name="agent_episode_repo")
    repo.update.assert_not_called()
    repo.save.assert_not_called()
