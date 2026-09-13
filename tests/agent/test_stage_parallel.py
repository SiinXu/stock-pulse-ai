"""Opt-in Technical ∥ Intel wave contracts (issue #1290 slice 1)."""

from __future__ import annotations

import inspect
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from tests.litellm_stub import ensure_litellm_stub


ensure_litellm_stub()

from src.agent.llm_adapter import LLMResponse
from src.agent.orchestrator import AgentOrchestrator
from src.agent.orchestrator_parts.stage_parallel import WAVE_MAX_WORKERS, maybe_run_technical_intel_wave
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
from src.services.analysis_stage_checkpoint import (
    AnalysisStageCheckpointStore,
    META_SESSION_KEY,
    agent_stage_name,
    create_checkpoint_session,
)
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


def _checkpoint_config(tmp_path: Path, **overrides) -> SimpleNamespace:
    base = {
        "analysis_checkpoint_enabled": True,
        "analysis_checkpoint_dir": str(tmp_path / "ckpts"),
        "analysis_checkpoint_ttl_hours": 24,
        "analysis_checkpoint_force_full": False,
        "repro_mode_enabled": False,
        "repro_record_config": True,
        "repro_seed": None,
        "llm_temperature": 0.7,
        "litellm_model": "test-model",
        "agent_litellm_model": "test-agent-model",
        "agent_generation_backend": "litellm",
        "generation_backend": "litellm",
        "agent_mode": True,
        "agent_arch": "multi",
        "agent_orchestrator_mode": "standard",
        "agent_critic_enabled": False,
        "agent_red_team_enabled": False,
        "agent_multi_strategy_deliberation": False,
        "agent_investment_committee_mode": False,
        "agent_risk_override": True,
        "risk_gate_profile": "balanced",
        "report_type": "detailed",
        "report_language": "zh",
        "report_mode": "standard",
        "agent_skills": [],
        "agent_planning_enabled": False,
        "agent_memory_enabled": False,
        "decision_memory_enabled": False,
        "report_integrity_enabled": True,
        "agent_observability_enabled": True,
        "backtest_engine_version": "v1",
        "agent_stage_parallel_enabled": True,
        "agent_orchestrator_timeout_s": 0,
        "agent_mode_budget_enabled": False,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _checkpoint_session(tmp_path: Path, *, query_id: str, config: SimpleNamespace):
    store = AnalysisStageCheckpointStore(tmp_path / "ckpts", ttl_hours=24)
    return create_checkpoint_session(
        config,
        query_id=query_id,
        stock_code="600519",
        store=store,
    )


def _assert_cancel_probe_precedes_wave_commit() -> None:
    source = inspect.getsource(maybe_run_technical_intel_wave)
    after_join = source.split("technical_ok = technical_result.status", 1)[1]
    cancel_pos = after_join.find("cancelled_check")
    commit_pos = after_join.find("_commit_stage_context")
    merge_pos = after_join.find("_merge_intel_first_wins")
    checkpoint_pos = after_join.find("_save_wave_checkpoint")
    assert 0 <= cancel_pos < commit_pos
    assert cancel_pos < merge_pos
    assert cancel_pos < checkpoint_pos


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


def test_user_cancel_in_flight_does_not_commit_or_checkpoint(tmp_path: Path) -> None:
    started = threading.Barrier(2, timeout=5)
    cancelled = threading.Event()
    decision_calls = {"count": 0}
    events: list[dict] = []
    config = _checkpoint_config(tmp_path)
    session = _checkpoint_session(tmp_path, query_id="n1-in-flight-cancel", config=config)

    def technical_run(ctx: AgentContext, cancelled_check=None, **_kwargs) -> StageResult:
        started.wait()
        cancelled.set()
        deadline = time.time() + 2.0
        while time.time() < deadline:
            if cancelled_check is not None and cancelled_check():
                return _failed("technical")
            time.sleep(0.01)
        ctx.add_opinion(AgentOpinion(
            agent_name="technical", signal="buy", confidence=0.8, reasoning="trend",
        ))
        return _completed("technical")

    def intel_run(ctx: AgentContext, cancelled_check=None, **_kwargs) -> StageResult:
        started.wait()
        deadline = time.time() + 2.0
        while time.time() < deadline:
            if cancelled_check is not None and cancelled_check():
                ctx.set_data("intel_opinion", {"signal": "should-not-commit"})
                return _failed("intel")
            time.sleep(0.01)
        ctx.add_opinion(AgentOpinion(
            agent_name="intel", signal="hold", confidence=0.6, reasoning="news",
        ))
        ctx.set_data("intel_opinion", {"signal": "hold"})
        return _completed("intel")

    def decision_run(ctx: AgentContext, **_kwargs) -> StageResult:
        decision_calls["count"] += 1
        return _completed("decision")

    orch = _orchestrator(enabled=True, agent_mode_budget_enabled=False)
    ctx = AgentContext(query="test", stock_code="600519")
    ctx.meta[META_SESSION_KEY] = session
    stages = [
        _Stage("technical", technical_run),
        _Stage("intel", intel_run),
        _Stage("decision", decision_run),
    ]
    with patch.object(orch, "_build_agent_chain", return_value=stages):
        result = orch._execute_pipeline(
            ctx,
            parse_dashboard=False,
            progress_callback=events.append,
            cancelled_check=cancelled.is_set,
        )

    dones = [item.get("stage") for item in events if item.get("type") == "stage_done"]
    assert result.cancelled
    assert result.success is False
    assert ctx.get_data("intel_opinion") is None
    assert "intel" not in [item.agent_name for item in ctx.opinions]
    assert agent_stage_name("technical_intel") not in session.completed_stages
    assert agent_stage_name("intel") not in session.completed_stages
    assert decision_calls["count"] == 0
    assert dones[:2] == ["technical", "intel"]


def test_cancel_after_successful_join_outranks_commit(tmp_path: Path) -> None:
    started = threading.Barrier(2, timeout=5)
    cancelled = {"flag": False}
    decision_calls = {"count": 0}
    events: list[dict] = []
    config = _checkpoint_config(tmp_path)
    session = _checkpoint_session(tmp_path, query_id="n2-cancel-after-join", config=config)

    def cancelled_check() -> bool:
        return cancelled["flag"]

    def technical_run(ctx: AgentContext, **_kwargs) -> StageResult:
        started.wait()
        time.sleep(0.05)
        ctx.add_opinion(AgentOpinion(
            agent_name="technical", signal="buy", confidence=0.8, reasoning="trend",
        ))
        cancelled["flag"] = True
        return _completed("technical")

    def intel_run(ctx: AgentContext, **_kwargs) -> StageResult:
        started.wait()
        ctx.add_opinion(AgentOpinion(
            agent_name="intel", signal="hold", confidence=0.6, reasoning="news",
        ))
        ctx.set_data("intel_opinion", {"signal": "hold"})
        return _completed("intel")

    def decision_run(ctx: AgentContext, **_kwargs) -> StageResult:
        decision_calls["count"] += 1
        return _completed("decision")

    _assert_cancel_probe_precedes_wave_commit()
    orch = _orchestrator(enabled=True)
    ctx = AgentContext(query="test", stock_code="600519")
    ctx.meta[META_SESSION_KEY] = session
    stages = [
        _Stage("technical", technical_run),
        _Stage("intel", intel_run),
        _Stage("decision", decision_run),
    ]
    with patch.object(orch, "_build_agent_chain", return_value=stages):
        result = orch._execute_pipeline(
            ctx,
            parse_dashboard=False,
            progress_callback=events.append,
            cancelled_check=cancelled_check,
        )

    dones = [item.get("stage") for item in events if item.get("type") == "stage_done"]
    assert result.cancelled
    assert result.success is False
    assert ctx.get_data("intel_opinion") is None
    assert "intel" not in [item.agent_name for item in ctx.opinions]
    assert "technical" not in [item.agent_name for item in ctx.opinions]
    assert agent_stage_name("technical_intel") not in session.completed_stages
    assert agent_stage_name("intel") not in session.completed_stages
    assert decision_calls["count"] == 0
    assert dones[:2] == ["technical", "intel"]


def test_flag_on_wave_writes_technical_intel_checkpoint(tmp_path: Path) -> None:
    config = _checkpoint_config(tmp_path)
    session = _checkpoint_session(tmp_path, query_id="n3-wave-checkpoint", config=config)

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
        return _completed("intel")

    orch = _orchestrator(enabled=True, agent_mode_budget_enabled=False)
    ctx = AgentContext(query="test", stock_code="600519")
    ctx.meta[META_SESSION_KEY] = session
    stages = [
        _Stage("technical", technical_run),
        _Stage("intel", intel_run),
        _Stage("decision", lambda ctx, **_kwargs: _completed("decision")),
    ]
    with patch.object(orch, "_build_agent_chain", return_value=stages):
        result = orch._execute_pipeline(ctx, parse_dashboard=False)

    assert result.success
    assert agent_stage_name("technical_intel") in session.completed_stages
    assert agent_stage_name("technical") not in session.completed_stages
    assert agent_stage_name("intel") not in session.completed_stages


def test_resume_from_technical_intel_skips_wave_and_runs_decision(tmp_path: Path) -> None:
    config = _checkpoint_config(tmp_path)
    query_id = "n4-wave-resume"
    first_session = _checkpoint_session(tmp_path, query_id=query_id, config=config)
    first_calls: list[str] = []

    def technical_run(ctx: AgentContext, **_kwargs) -> StageResult:
        first_calls.append("technical")
        ctx.add_opinion(AgentOpinion(
            agent_name="technical", signal="buy", confidence=0.8, reasoning="trend",
        ))
        return _completed("technical")

    def intel_run(ctx: AgentContext, **_kwargs) -> StageResult:
        first_calls.append("intel")
        ctx.add_opinion(AgentOpinion(
            agent_name="intel", signal="hold", confidence=0.6, reasoning="news",
        ))
        ctx.set_data("intel_opinion", {"signal": "hold"})
        return _completed("intel")

    def interrupting_decision(ctx: AgentContext, **_kwargs) -> StageResult:
        first_calls.append("decision")
        raise KeyboardInterrupt("stop after wave checkpoint")

    orch = _orchestrator(enabled=True, agent_mode_budget_enabled=False)
    first_ctx = AgentContext(query="test", stock_code="600519")
    first_ctx.meta[META_SESSION_KEY] = first_session
    with patch.object(
        orch,
        "_build_agent_chain",
        return_value=[
            _Stage("technical", technical_run),
            _Stage("intel", intel_run),
            _Stage("decision", interrupting_decision),
        ],
    ), pytest.raises(KeyboardInterrupt):
        orch._execute_pipeline(first_ctx, parse_dashboard=False)

    assert "technical" in first_calls and "intel" in first_calls
    assert agent_stage_name("technical_intel") in first_session.completed_stages
    assert agent_stage_name("decision") not in first_session.completed_stages

    resumed_session = _checkpoint_session(tmp_path, query_id=query_id, config=config)
    resume_calls: list[str] = []
    captured: dict[str, object] = {}
    created_workers: list[int] = []
    real_pool = ThreadPoolExecutor

    class _SpyPool(real_pool):
        def __init__(self, *args, **kwargs):
            created_workers.append(int(kwargs.get("max_workers", args[0] if args else 0)))
            super().__init__(*args, **kwargs)

    def resume_technical(ctx: AgentContext, **_kwargs) -> StageResult:
        resume_calls.append("technical")
        return _completed("technical")

    def resume_intel(ctx: AgentContext, **_kwargs) -> StageResult:
        resume_calls.append("intel")
        return _completed("intel")

    def resume_decision(ctx: AgentContext, **_kwargs) -> StageResult:
        resume_calls.append("decision")
        captured["opinions"] = [item.agent_name for item in ctx.opinions]
        captured["intel_opinion"] = ctx.get_data("intel_opinion")
        return _completed("decision")

    resume_orch = _orchestrator(enabled=True, agent_mode_budget_enabled=False)
    resume_ctx = AgentContext(query="test", stock_code="600519")
    resume_ctx.meta[META_SESSION_KEY] = resumed_session
    with patch(
        "src.agent.orchestrator_parts.stage_parallel.ThreadPoolExecutor",
        _SpyPool,
    ), patch.object(
        resume_orch,
        "_build_agent_chain",
        return_value=[
            _Stage("technical", resume_technical),
            _Stage("intel", resume_intel),
            _Stage("decision", resume_decision),
        ],
    ):
        result = resume_orch._execute_pipeline(resume_ctx, parse_dashboard=False)

    assert result.success
    assert resume_calls == ["decision"]
    assert captured["opinions"] == ["technical", "intel"]
    assert captured["intel_opinion"] == {"signal": "hold"}
    assert created_workers == []


def test_intel_isolate_resume_runs_intel_serially(tmp_path: Path) -> None:
    config = _checkpoint_config(tmp_path)
    query_id = "n5-intel-isolate-resume"
    first_session = _checkpoint_session(tmp_path, query_id=query_id, config=config)

    def technical_run(ctx: AgentContext, **_kwargs) -> StageResult:
        ctx.add_opinion(AgentOpinion(
            agent_name="technical", signal="buy", confidence=0.8, reasoning="trend",
        ))
        return _completed("technical")

    def failing_intel(ctx: AgentContext, **_kwargs) -> StageResult:
        return _failed("intel")

    def interrupting_decision(ctx: AgentContext, **_kwargs) -> StageResult:
        raise KeyboardInterrupt("stop after technical checkpoint")

    orch = _orchestrator(enabled=True, agent_mode_budget_enabled=False)
    first_ctx = AgentContext(query="test", stock_code="600519")
    first_ctx.meta[META_SESSION_KEY] = first_session
    with patch.object(
        orch,
        "_build_agent_chain",
        return_value=[
            _Stage("technical", technical_run),
            _Stage("intel", failing_intel),
            _Stage("decision", interrupting_decision),
        ],
    ), pytest.raises(KeyboardInterrupt):
        orch._execute_pipeline(first_ctx, parse_dashboard=False)

    assert agent_stage_name("technical") in first_session.completed_stages
    assert agent_stage_name("technical_intel") not in first_session.completed_stages
    assert agent_stage_name("intel") not in first_session.completed_stages

    resumed_session = _checkpoint_session(tmp_path, query_id=query_id, config=config)
    resume_calls: list[str] = []
    threads: dict[str, int] = {}
    created_workers: list[int] = []
    real_pool = ThreadPoolExecutor

    class _SpyPool(real_pool):
        def __init__(self, *args, **kwargs):
            created_workers.append(int(kwargs.get("max_workers", args[0] if args else 0)))
            super().__init__(*args, **kwargs)

    def resume_technical(ctx: AgentContext, **_kwargs) -> StageResult:
        resume_calls.append("technical")
        return _completed("technical")

    def resume_intel(ctx: AgentContext, **_kwargs) -> StageResult:
        resume_calls.append("intel")
        threads["intel"] = threading.get_ident()
        ctx.add_opinion(AgentOpinion(
            agent_name="intel", signal="hold", confidence=0.6, reasoning="news",
        ))
        ctx.set_data("intel_opinion", {"signal": "hold"})
        return _completed("intel")

    def resume_decision(ctx: AgentContext, **_kwargs) -> StageResult:
        resume_calls.append("decision")
        threads["decision"] = threading.get_ident()
        return _completed("decision")

    resume_orch = _orchestrator(enabled=True, agent_mode_budget_enabled=False)
    resume_ctx = AgentContext(query="test", stock_code="600519")
    resume_ctx.meta[META_SESSION_KEY] = resumed_session
    with patch(
        "src.agent.orchestrator_parts.stage_parallel.ThreadPoolExecutor",
        _SpyPool,
    ), patch.object(
        resume_orch,
        "_build_agent_chain",
        return_value=[
            _Stage("technical", resume_technical),
            _Stage("intel", resume_intel),
            _Stage("decision", resume_decision),
        ],
    ):
        result = resume_orch._execute_pipeline(resume_ctx, parse_dashboard=False)

    assert result.success
    assert resume_calls == ["intel", "decision"]
    assert created_workers == []
    assert threads["intel"] == threads["decision"]


def test_real_technical_and_intel_agents_merge_declaration_order() -> None:
    from src.agent.agents.intel_agent import IntelAgent
    from src.agent.agents.technical_agent import TechnicalAgent

    technical_json = {
        "signal": "buy",
        "confidence": 0.8,
        "reasoning": "trend is constructive",
        "key_levels": {"support": 10.0, "resistance": 12.0, "stop_loss": 9.5},
        "trend_score": 70,
        "ma_alignment": "bullish",
        "volume_status": "normal",
        "pattern": "none",
    }
    intel_json = {
        "signal": "hold",
        "confidence": 0.6,
        "reasoning": "news is mixed",
        "risk_alerts": [],
        "positive_catalysts": ["product launch"],
        "sentiment_label": "neutral",
        "capital_flow_signal": "neutral",
        "key_news": [],
    }
    decision_json = {
        "stock_name": "Test Stock",
        "sentiment_score": 72,
        "trend_prediction": "up",
        "operation_advice": "buy",
        "decision_type": "buy",
        "confidence_level": "Medium",
        "analysis_summary": "technical leads, intel is mixed",
        "dashboard": {
            "phase_decision": {
                "phase_context": "regular",
                "action_window": "now",
                "immediate_action": "watch",
                "watch_conditions": [],
                "next_check_time": "next session",
                "confidence_reason": "test fixture",
                "data_limitations": [],
            },
            "core_conclusion": {
                "one_sentence": "test decision",
                "signal_type": "buy",
                "position_advice": {
                    "no_position": "watch",
                    "has_position": "hold",
                },
            },
        },
    }

    def _scripted_call(messages, tools=None, **_kwargs):
        blob = " ".join(
            str(item.get("content", ""))
            for item in messages
            if isinstance(item, dict)
        )
        if "Technical Analysis Agent" in blob:
            time.sleep(0.05)
            return LLMResponse(
                content=json.dumps(technical_json),
                provider="scripted",
                model="scripted-model",
            )
        if "Intelligence & Sentiment Agent" in blob:
            return LLMResponse(
                content=json.dumps(intel_json),
                provider="scripted",
                model="scripted-model",
            )
        return LLMResponse(
            content=json.dumps(decision_json),
            provider="scripted",
            model="scripted-model",
        )

    adapter = MagicMock()
    adapter.call_with_tools.side_effect = _scripted_call
    adapter.model = "scripted-model"
    snapshot = seal_analysis_context_snapshot(
        _pack(),
        {"realtime_quote": {"price": 1880.0}, "news_context": "headline-a"},
        snapshot_id="snap-real-wave",
        snapshot_revision=1,
    )
    ctx = AgentContext(query="test", stock_code="600519")
    ctx.seal_input_snapshot(snapshot)
    fingerprint = ctx.input_snapshot.fingerprint() if ctx.input_snapshot else None

    orch = AgentOrchestrator(
        tool_registry=ToolRegistry(),
        llm_adapter=adapter,
        config=SimpleNamespace(
            agent_stage_parallel_enabled=True,
            agent_orchestrator_timeout_s=0,
            agent_risk_override=True,
            agent_mode_budget_enabled=False,
            agent_critic_enabled=False,
            agent_red_team_enabled=False,
            agent_memory_enabled=False,
        ),
        mode="standard",
    )
    preview = orch._build_agent_chain(AgentContext(query="preview", stock_code="600519"))
    assert isinstance(preview[0], TechnicalAgent)
    assert isinstance(preview[1], IntelAgent)

    result = orch._execute_pipeline(ctx, parse_dashboard=False)

    assert result.success
    assert [item.agent_name for item in ctx.opinions][:2] == ["technical", "intel"]
    assert ctx.get_data("intel_opinion")["signal"] == "hold"
    assert ctx.input_snapshot is not None
    assert ctx.input_snapshot.fingerprint() == fingerprint
    assert ctx.get_data("realtime_quote")["price"] == 1880.0
    sealed_keys = getattr(ctx.data, "_sealed_keys", frozenset())
    assert "realtime_quote" in sealed_keys


def test_technical_failure_is_not_rewritten_as_cancelled_without_user_cancel() -> None:
    intel_started = threading.Event()
    ctx = AgentContext(query="test", stock_code="600519")

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

    orch = _orchestrator(enabled=True)
    stages = [
        _Stage("technical", technical_run),
        _Stage("intel", intel_run),
        _Stage("decision", lambda ctx, **_kwargs: _completed("decision")),
    ]
    with patch.object(orch, "_build_agent_chain", return_value=stages):
        result = orch._execute_pipeline(
            ctx,
            parse_dashboard=False,
            cancelled_check=lambda: False,
        )

    assert result.success is False
    assert result.cancelled is False
    assert ctx.get_data("intel_opinion") is None
    assert "intel" not in [item.agent_name for item in ctx.opinions]
