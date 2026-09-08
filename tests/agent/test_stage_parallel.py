"""Opt-in Technical ∥ Intel wave contracts (issue #1290 slice 1)."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from tests.litellm_stub import ensure_litellm_stub


ensure_litellm_stub()

from src.agent.orchestrator import AgentOrchestrator
from src.agent.orchestrator_parts.stage_parallel import WAVE_MAX_WORKERS
from src.agent.protocols import (
    AgentContext,
    AgentOpinion,
    StageFailureReason,
    StageResult,
    StageStatus,
)
from src.agent.tools.registry import ToolRegistry
from src.analysis_context_pack.snapshot import (
    SnapshotMutationError,
    seal_analysis_context_snapshot,
)
from src.config import Config
from src.core.config_registry import get_field_definition
from src.schemas.analysis_context_pack import (
    AnalysisContextBlock,
    AnalysisContextItem,
    AnalysisContextPack,
    AnalysisSubject,
    ContextFieldStatus,
)


def _completed(name: str) -> StageResult:
    result = StageResult(stage_name=name, status=StageStatus.COMPLETED)
    result.meta.update({"raw_text": "ok", "models_used": ["test/model"], "tool_calls_log": []})
    return result


def _failed(
    name: str,
    *,
    reason: StageFailureReason = StageFailureReason.STAGE_FAILURE,
    error: str = "stage failed",
) -> StageResult:
    result = StageResult(
        stage_name=name,
        status=StageStatus.FAILED,
        error=error,
        failure_reason=reason,
    )
    result.meta.update({"raw_text": "", "models_used": ["test/model"], "tool_calls_log": []})
    return result


class _Stage:
    max_steps = 1

    def __init__(self, agent_name: str, run_callback) -> None:
        self.agent_name = agent_name
        self._run_callback = run_callback

    def run(self, ctx: AgentContext, **kwargs) -> StageResult:
        return self._run_callback(ctx, **kwargs)


def _orchestrator(*, enabled: bool, mode: str = "standard", **config_extra) -> AgentOrchestrator:
    config = SimpleNamespace(
        agent_stage_parallel_enabled=enabled,
        agent_orchestrator_timeout_s=0,
        agent_risk_override=True,
        **config_extra,
    )
    orch = AgentOrchestrator(
        tool_registry=ToolRegistry(),
        llm_adapter=MagicMock(),
        config=config,
        mode=mode,
    )
    return orch


def _pack() -> AnalysisContextPack:
    return AnalysisContextPack(
        subject=AnalysisSubject(code="600519", stock_name="贵州茅台", market="cn"),
        blocks={
            "quote": AnalysisContextBlock(
                status=ContextFieldStatus.AVAILABLE,
                source="akshare_em",
                timestamp="2026-05-24T09:30:00+08:00",
                items={
                    "price": AnalysisContextItem(
                        status=ContextFieldStatus.AVAILABLE,
                        value=1880.0,
                        source="akshare_em",
                        timestamp="2026-05-24T09:30:00+08:00",
                    )
                },
            )
        },
        created_at=datetime(2026, 5, 24, 1, 30, tzinfo=timezone.utc),
    )


def test_flag_defaults_off_and_is_registered() -> None:
    assert Config().agent_stage_parallel_enabled is False
    field = get_field_definition("AGENT_STAGE_PARALLEL_ENABLED")
    assert field["default_value"] == "false"
    assert field["data_type"] == "boolean"
    assert field["help_key"] == "settings.agent.AGENT_STAGE_PARALLEL_ENABLED"


def test_default_off_serial_intel_sees_technical_same_thread() -> None:
    threads: list[int] = []
    intel_seen: list[list[str]] = []
    captured: dict[str, object] = {}

    def technical_run(ctx: AgentContext, **_kwargs) -> StageResult:
        threads.append(threading.get_ident())
        ctx.add_opinion(AgentOpinion(
            agent_name="technical", signal="buy", confidence=0.8, reasoning="trend",
        ))
        return _completed("technical")

    def intel_run(ctx: AgentContext, **_kwargs) -> StageResult:
        threads.append(threading.get_ident())
        intel_seen.append([item.agent_name for item in ctx.opinions])
        ctx.add_opinion(AgentOpinion(
            agent_name="intel", signal="hold", confidence=0.6, reasoning="news",
        ))
        ctx.set_data("intel_opinion", {"signal": "hold"})
        return _completed("intel")

    def decision_run(ctx: AgentContext, **_kwargs) -> StageResult:
        captured["opinions"] = [item.agent_name for item in ctx.opinions]
        captured["meta"] = dict(ctx.meta)
        return _completed("decision")

    orch = _orchestrator(enabled=False)
    technical = _Stage("technical", technical_run)
    intel = _Stage("intel", intel_run)
    decision = _Stage("decision", decision_run)
    with patch.object(orch, "_build_agent_chain", return_value=[technical, intel, decision]):
        result = orch._execute_pipeline(AgentContext(query="test", stock_code="600519"), parse_dashboard=False)

    assert result.success
    assert intel_seen == [["technical"]]
    assert threads[0] == threads[1]
    assert captured["opinions"] == ["technical", "intel"]
    assert "stage_parallel" not in captured["meta"]


def test_wave_merges_declaration_order_when_intel_finishes_first() -> None:
    started = threading.Barrier(2, timeout=5)
    intel_finished = threading.Event()
    threads: dict[str, int] = {}
    events: list[dict] = []
    captured: dict[str, object] = {}
    created_workers: list[int] = []
    real_pool = ThreadPoolExecutor

    class _SpyPool(real_pool):
        def __init__(self, *args, **kwargs):
            created_workers.append(int(kwargs.get("max_workers", args[0] if args else 0)))
            super().__init__(*args, **kwargs)

    def technical_run(ctx: AgentContext, **_kwargs) -> StageResult:
        started.wait()
        assert intel_finished.wait(timeout=5)
        threads["technical"] = threading.get_ident()
        ctx.add_opinion(AgentOpinion(
            agent_name="technical", signal="buy", confidence=0.8, reasoning="trend",
        ))
        ctx.set_data("technical_note", "from-technical")
        return _completed("technical")

    def intel_run(ctx: AgentContext, **_kwargs) -> StageResult:
        started.wait()
        threads["intel"] = threading.get_ident()
        ctx.add_opinion(AgentOpinion(
            agent_name="intel", signal="hold", confidence=0.6, reasoning="news",
        ))
        ctx.set_data("intel_opinion", {"signal": "hold"})
        ctx.set_data("technical_note", "from-intel")
        intel_finished.set()
        return _completed("intel")

    def decision_run(ctx: AgentContext, **_kwargs) -> StageResult:
        captured["opinions"] = [item.agent_name for item in ctx.opinions]
        captured["intel_opinion"] = ctx.get_data("intel_opinion")
        captured["technical_note"] = ctx.get_data("technical_note")
        captured["stage_parallel"] = ctx.meta.get("stage_parallel")
        return _completed("decision")

    orch = _orchestrator(enabled=True)
    technical = _Stage("technical", technical_run)
    intel = _Stage("intel", intel_run)
    decision = _Stage("decision", decision_run)
    with patch(
        "src.agent.orchestrator_parts.stage_parallel.ThreadPoolExecutor",
        _SpyPool,
    ), patch.object(orch, "_build_agent_chain", return_value=[technical, intel, decision]):
        result = orch._execute_pipeline(
            AgentContext(query="test", stock_code="600519"),
            parse_dashboard=False,
            progress_callback=events.append,
        )

    assert result.success
    assert captured["opinions"] == ["technical", "intel"]
    assert captured["intel_opinion"] == {"signal": "hold"}
    assert captured["technical_note"] == "from-technical"
    assert captured["stage_parallel"]["max_workers"] == WAVE_MAX_WORKERS
    assert created_workers == [WAVE_MAX_WORKERS]
    assert threads["technical"] != threads["intel"]
    starts = [item.get("stage") for item in events if item.get("type") == "stage_start"]
    dones = [item.get("stage") for item in events if item.get("type") == "stage_done"]
    assert starts[:2] == ["technical", "intel"]
    assert dones[:2] == ["technical", "intel"]


def test_intel_isolate_keeps_technical_and_runs_decision() -> None:
    captured: dict[str, object] = {}

    def technical_run(ctx: AgentContext, **_kwargs) -> StageResult:
        ctx.add_opinion(AgentOpinion(
            agent_name="technical", signal="buy", confidence=0.8, reasoning="trend",
        ))
        return _completed("technical")

    def intel_run(ctx: AgentContext, **_kwargs) -> StageResult:
        ctx.add_opinion(AgentOpinion(
            agent_name="intel", signal="hold", confidence=0.6, reasoning="news",
        ))
        ctx.set_data("intel_opinion", {"signal": "hold"})
        return _failed("intel")

    def decision_run(ctx: AgentContext, **_kwargs) -> StageResult:
        captured["opinions"] = [item.agent_name for item in ctx.opinions]
        captured["intel_opinion"] = ctx.get_data("intel_opinion")
        captured["degraded"] = list(ctx.meta.get("degraded_stages") or [])
        return _completed("decision")

    orch = _orchestrator(enabled=True)
    technical = _Stage("technical", technical_run)
    intel = _Stage("intel", intel_run)
    decision = _Stage("decision", decision_run)
    with patch.object(orch, "_build_agent_chain", return_value=[technical, intel, decision]):
        result = orch._execute_pipeline(AgentContext(query="test", stock_code="600519"), parse_dashboard=False)

    assert result.success
    assert captured["opinions"] == ["technical"]
    assert captured["intel_opinion"] is None
    assert any(item.get("stage_name") == "intel" for item in captured["degraded"])
    assert decision._run_callback  # decision path executed


def test_technical_failure_cancels_intel_and_does_not_commit_intel_only() -> None:
    intel_started = threading.Event()
    captured_ctx = AgentContext(query="test", stock_code="600519")

    def technical_run(ctx: AgentContext, **_kwargs) -> StageResult:
        assert intel_started.wait(timeout=5)
        return _failed("technical")

    def intel_run(ctx: AgentContext, cancelled_check=None, **_kwargs) -> StageResult:
        intel_started.set()
        deadline = time.time() + 1.0
        while time.time() < deadline:
            if cancelled_check is not None and cancelled_check():
                break
            time.sleep(0.01)
        ctx.add_opinion(AgentOpinion(
            agent_name="intel", signal="hold", confidence=0.6, reasoning="should-not-commit",
        ))
        ctx.set_data("intel_opinion", {"signal": "hold"})
        return _completed("intel")

    decision = _Stage("decision", lambda ctx, **_kwargs: _completed("decision"))
    orch = _orchestrator(enabled=True)
    technical = _Stage("technical", technical_run)
    intel = _Stage("intel", intel_run)
    with patch.object(orch, "_build_agent_chain", return_value=[technical, intel, decision]):
        result = orch._execute_pipeline(captured_ctx, parse_dashboard=False)

    opinion_names = [item.agent_name for item in captured_ctx.opinions]
    assert captured_ctx.get_data("intel_opinion") is None
    assert opinion_names != ["intel"]
    assert "intel" not in opinion_names
    assert result.cancelled or (not result.success)


def test_intel_timeout_isolates_and_keeps_technical() -> None:
    captured: dict[str, object] = {}

    def technical_run(ctx: AgentContext, **_kwargs) -> StageResult:
        ctx.add_opinion(AgentOpinion(
            agent_name="technical", signal="buy", confidence=0.8, reasoning="trend",
        ))
        return _completed("technical")

    def intel_run(ctx: AgentContext, **_kwargs) -> StageResult:
        time.sleep(0.2)
        ctx.set_data("intel_opinion", {"signal": "hold"})
        return _completed("intel")

    def decision_run(ctx: AgentContext, **_kwargs) -> StageResult:
        captured["opinions"] = [item.agent_name for item in ctx.opinions]
        captured["intel_opinion"] = ctx.get_data("intel_opinion")
        return _completed("decision")

    orch = _orchestrator(enabled=True, agent_intel_agent_timeout_s=0.05)
    technical = _Stage("technical", technical_run)
    intel = _Stage("intel", intel_run)
    decision = _Stage("decision", decision_run)
    with patch.object(orch, "_build_agent_chain", return_value=[technical, intel, decision]):
        result = orch._execute_pipeline(AgentContext(query="test", stock_code="600519"), parse_dashboard=False)

    assert result.success
    assert captured["opinions"] == ["technical"]
    assert captured["intel_opinion"] is None


def test_full_mode_risk_reads_merged_intel_opinion_after_wave() -> None:
    captured: dict[str, object] = {}

    def technical_run(ctx: AgentContext, **_kwargs) -> StageResult:
        ctx.add_opinion(AgentOpinion(
            agent_name="technical", signal="buy", confidence=0.8, reasoning="trend",
        ))
        return _completed("technical")

    def intel_run(ctx: AgentContext, **_kwargs) -> StageResult:
        ctx.add_opinion(AgentOpinion(
            agent_name="intel", signal="hold", confidence=0.6, reasoning="news",
        ))
        ctx.set_data("intel_opinion", {"signal": "hold", "risk_alerts": ["gap"]})
        return _completed("intel")

    def risk_run(ctx: AgentContext, **_kwargs) -> StageResult:
        captured["intel_opinion"] = ctx.get_data("intel_opinion")
        captured["opinions"] = [item.agent_name for item in ctx.opinions]
        return _completed("risk")

    def decision_run(ctx: AgentContext, **_kwargs) -> StageResult:
        return _completed("decision")

    orch = _orchestrator(enabled=True, mode="full")
    stages = [
        _Stage("technical", technical_run),
        _Stage("intel", intel_run),
        _Stage("risk", risk_run),
        _Stage("decision", decision_run),
    ]
    with patch.object(orch, "_build_agent_chain", return_value=stages):
        result = orch._execute_pipeline(AgentContext(query="test", stock_code="600519"), parse_dashboard=False)

    assert result.success
    assert captured["opinions"] == ["technical", "intel"]
    assert captured["intel_opinion"]["signal"] == "hold"


def test_wave_preserves_sealed_snapshot_and_rejects_isolated_market_writes() -> None:
    snapshot = seal_analysis_context_snapshot(
        _pack(),
        {"realtime_quote": {"price": 1880.0}, "news_context": "headline-a"},
        snapshot_id="snap-wave",
        snapshot_revision=1,
    )
    ctx = AgentContext(query="test", stock_code="600519")
    ctx.seal_input_snapshot(snapshot)
    fingerprint = ctx.input_snapshot.fingerprint() if ctx.input_snapshot else None
    mutations: list[str] = []

    def technical_run(isolated: AgentContext, **_kwargs) -> StageResult:
        with pytest.raises(SnapshotMutationError):
            isolated.set_data("realtime_quote", {"price": 1.0})
        mutations.append("technical")
        isolated.add_opinion(AgentOpinion(
            agent_name="technical", signal="buy", confidence=0.8, reasoning="trend",
        ))
        return _completed("technical")

    def intel_run(isolated: AgentContext, **_kwargs) -> StageResult:
        with pytest.raises(SnapshotMutationError):
            isolated.set_data("realtime_quote", {"price": 2.0})
        mutations.append("intel")
        isolated.add_opinion(AgentOpinion(
            agent_name="intel", signal="hold", confidence=0.6, reasoning="news",
        ))
        isolated.set_data("intel_opinion", {"signal": "hold"})
        return _completed("intel")

    def decision_run(final_ctx: AgentContext, **_kwargs) -> StageResult:
        return _completed("decision")

    orch = _orchestrator(enabled=True)
    stages = [
        _Stage("technical", technical_run),
        _Stage("intel", intel_run),
        _Stage("decision", decision_run),
    ]
    with patch.object(orch, "_build_agent_chain", return_value=stages):
        result = orch._execute_pipeline(ctx, parse_dashboard=False)

    assert result.success
    assert mutations == ["technical", "intel"] or set(mutations) == {"technical", "intel"}
    assert ctx.input_snapshot is not None
    assert ctx.input_snapshot.fingerprint() == fingerprint
    assert ctx.get_data("realtime_quote")["price"] == 1880.0
    sealed_keys = getattr(ctx.data, "_sealed_keys", frozenset())
    assert "realtime_quote" in sealed_keys
    with pytest.raises(SnapshotMutationError):
        ctx.data.clear()


def test_quick_mode_does_not_open_wave_when_flag_on() -> None:
    intel_calls = {"count": 0}

    def technical_run(ctx: AgentContext, **_kwargs) -> StageResult:
        ctx.add_opinion(AgentOpinion(
            agent_name="technical", signal="buy", confidence=0.8, reasoning="trend",
        ))
        return _completed("technical")

    def intel_run(ctx: AgentContext, **_kwargs) -> StageResult:
        intel_calls["count"] += 1
        return _completed("intel")

    def decision_run(ctx: AgentContext, **_kwargs) -> StageResult:
        return _completed("decision")

    orch = _orchestrator(enabled=True, mode="quick")
    technical = _Stage("technical", technical_run)
    decision = _Stage("decision", decision_run)
    ctx = AgentContext(query="test", stock_code="600519")
    with patch.object(orch, "_build_agent_chain", return_value=[technical, decision]):
        result = orch._execute_pipeline(ctx, parse_dashboard=False)

    assert result.success
    assert intel_calls["count"] == 0
    assert "stage_parallel" not in ctx.meta
    assert orch.mode == "quick"
    assert [agent.agent_name for agent in AgentOrchestrator(
        tool_registry=ToolRegistry(),
        llm_adapter=MagicMock(),
        config=SimpleNamespace(agent_stage_parallel_enabled=True, agent_orchestrator_timeout_s=0),
        mode="quick",
    )._build_agent_chain(AgentContext(query="q"))] == ["technical", "decision"]


def test_wave_worker_cap_is_two() -> None:
    created_workers: list[int] = []
    thread_ids: set[int] = set()
    real_pool = ThreadPoolExecutor

    class _SpyPool(real_pool):
        def __init__(self, *args, **kwargs):
            created_workers.append(int(kwargs.get("max_workers", args[0] if args else 0)))
            super().__init__(*args, **kwargs)

    def technical_run(ctx: AgentContext, **_kwargs) -> StageResult:
        thread_ids.add(threading.get_ident())
        time.sleep(0.05)
        ctx.add_opinion(AgentOpinion(
            agent_name="technical", signal="buy", confidence=0.8, reasoning="trend",
        ))
        return _completed("technical")

    def intel_run(ctx: AgentContext, **_kwargs) -> StageResult:
        thread_ids.add(threading.get_ident())
        time.sleep(0.05)
        ctx.add_opinion(AgentOpinion(
            agent_name="intel", signal="hold", confidence=0.6, reasoning="news",
        ))
        ctx.set_data("intel_opinion", {"signal": "hold"})
        return _completed("intel")

    orch = _orchestrator(enabled=True)
    stages = [
        _Stage("technical", technical_run),
        _Stage("intel", intel_run),
        _Stage("decision", lambda ctx, **_kwargs: _completed("decision")),
    ]
    with patch(
        "src.agent.orchestrator_parts.stage_parallel.ThreadPoolExecutor",
        _SpyPool,
    ), patch.object(orch, "_build_agent_chain", return_value=stages):
        result = orch._execute_pipeline(AgentContext(query="test", stock_code="600519"), parse_dashboard=False)

    assert result.success
    assert created_workers
    assert max(created_workers) <= WAVE_MAX_WORKERS
    assert created_workers == [WAVE_MAX_WORKERS]
    assert len(thread_ids) == 2


def test_intel_hard_budget_does_not_isolate() -> None:
    decision_calls = {"count": 0}

    def technical_run(ctx: AgentContext, **_kwargs) -> StageResult:
        ctx.add_opinion(AgentOpinion(
            agent_name="technical", signal="buy", confidence=0.8, reasoning="trend",
        ))
        return _completed("technical")

    def intel_run(ctx: AgentContext, **_kwargs) -> StageResult:
        return _failed("intel", reason=StageFailureReason.BUDGET_TOOLS, error="tool budget")

    def decision_run(ctx: AgentContext, **_kwargs) -> StageResult:
        decision_calls["count"] += 1
        return _completed("decision")

    orch = _orchestrator(enabled=True)
    stages = [
        _Stage("technical", technical_run),
        _Stage("intel", intel_run),
        _Stage("decision", decision_run),
    ]
    ctx = AgentContext(query="test", stock_code="600519")
    with patch.object(orch, "_build_agent_chain", return_value=stages):
        result = orch._execute_pipeline(ctx, parse_dashboard=False)

    assert not result.success
    assert result.failure_reason == StageFailureReason.BUDGET_TOOLS.value
    assert decision_calls["count"] == 0
    assert [item.agent_name for item in ctx.opinions] == ["technical"]
