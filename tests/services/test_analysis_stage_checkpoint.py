# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Stage checkpoint resume consistency and reproducibility controls."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.agent.protocols import AgentContext, AgentOpinion, StageResult, StageStatus
from src.services.analysis_stage_checkpoint import (
    AnalysisStageCheckpointStore,
    activate_checkpoint_session,
    agent_stage_name,
    apply_repro_mode,
    build_agent_input_fingerprint,
    build_compatibility_fingerprint,
    build_repro_snapshot,
    capture_agent_stage_payload,
    create_checkpoint_session,
    current_checkpoint_session,
    restore_agent_context_from_session,
    resolve_repro_generation_params,
    reset_checkpoint_session,
    serialize_agent_opinion,
    META_SESSION_KEY,
)


def _config(**overrides):
    base = {
        "analysis_checkpoint_enabled": True,
        "analysis_checkpoint_dir": None,
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
        "agent_orchestrator_mode": "full",
        "agent_critic_enabled": False,
        "agent_multi_strategy_deliberation": False,
        "agent_investment_committee_mode": False,
        "agent_risk_override": True,
        "risk_gate_profile": "balanced",
        "report_type": "detailed",
        "report_language": "zh",
        "report_mode": "standard",
        "agent_skills": ["bull_trend"],
        "agent_planning_enabled": False,
        "agent_memory_enabled": False,
        "decision_memory_enabled": False,
        "report_integrity_enabled": True,
        "agent_observability_enabled": True,
        "backtest_engine_version": "v1",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _opinion(name: str, signal: str, confidence: float = 0.8) -> AgentOpinion:
    return AgentOpinion(
        agent_name=name,
        signal=signal,
        confidence=confidence,
        reasoning=f"{name} reasoning for {signal}",
        key_levels={"support": 10.0, "resistance": 12.0},
        raw_data={"source": "test"},
        timestamp=1.0,
    )


def test_interrupt_resume_exact_replay_matches_full_run(tmp_path: Path) -> None:
    """Interrupted multi-agent run resumes from checkpoint with identical opinions."""
    store = AnalysisStageCheckpointStore(tmp_path / "ckpts", ttl_hours=24)
    config = _config(analysis_checkpoint_dir=str(tmp_path / "ckpts"))
    query_id = "task-resume-1"
    stock = "600519"

    # Full run path: complete technical + intel + risk + decision.
    full_session = create_checkpoint_session(
        config,
        query_id=query_id + "-full",
        stock_code=stock,
        report_type="detailed",
        analysis_phase="auto",
        store=store,
    )
    full_ctx = AgentContext(query="analysis", stock_code=stock)
    full_ctx.meta["_checkpoint_agent_input_fingerprint"] = build_agent_input_fingerprint(full_ctx)
    for stage, signal in (
        ("technical", "buy"),
        ("intel", "hold"),
        ("risk", "hold"),
        ("decision", "buy"),
    ):
        full_ctx.add_opinion(_opinion(stage, signal))
        full_session.save_stage(
            agent_stage_name(stage),
            capture_agent_stage_payload(full_ctx, stage_name=stage),
        )
    full_signals = [(o.agent_name, o.signal, o.confidence, o.reasoning) for o in full_ctx.opinions]
    full_session.complete()  # terminal success clears durable state for that query

    # Interrupted run: save technical+intel, then "crash" (keep checkpoint).
    interrupted = create_checkpoint_session(
        config,
        query_id=query_id,
        stock_code=stock,
        report_type="detailed",
        analysis_phase="auto",
        store=store,
    )
    mid_ctx = AgentContext(query="analysis", stock_code=stock)
    mid_ctx.meta["_checkpoint_agent_input_fingerprint"] = build_agent_input_fingerprint(mid_ctx)
    for stage, signal in (("technical", "buy"), ("intel", "hold")):
        mid_ctx.add_opinion(_opinion(stage, signal))
        interrupted.save_stage(
            agent_stage_name(stage),
            capture_agent_stage_payload(mid_ctx, stage_name=stage),
        )
    interrupted.fail_keep()
    assert interrupted.is_stage_complete(agent_stage_name("technical"))
    assert interrupted.is_stage_complete(agent_stage_name("intel"))
    assert not interrupted.is_stage_complete(agent_stage_name("decision"))

    # Resume with same fingerprint: restore completed stages, then finish remaining.
    resumed = create_checkpoint_session(
        config,
        query_id=query_id,
        stock_code=stock,
        report_type="detailed",
        analysis_phase="auto",
        store=store,
    )
    assert resumed.consistency == "exact_replay"
    assert resumed.annotation["resumed"] is True
    resume_ctx = AgentContext(query="analysis", stock_code=stock)
    restored = restore_agent_context_from_session(resumed, resume_ctx)
    assert set(restored) == {"technical", "intel"}
    # Remaining stages produce the same opinions as the full run.
    for stage, signal in (("risk", "hold"), ("decision", "buy")):
        resume_ctx.add_opinion(_opinion(stage, signal))
        resumed.save_stage(
            agent_stage_name(stage),
            capture_agent_stage_payload(resume_ctx, stage_name=stage),
        )

    resume_signals = [
        (o.agent_name, o.signal, o.confidence, o.reasoning) for o in resume_ctx.opinions
    ]
    assert resume_signals == full_signals
    assert resumed.annotation["consistency"] == "exact_replay"
    assert resumed.annotation["resumed"] is True


def test_fingerprint_mismatch_forces_full_rerun_without_silent_divergence(
    tmp_path: Path,
) -> None:
    store = AnalysisStageCheckpointStore(tmp_path / "ckpts", ttl_hours=24)
    config_a = _config(
        analysis_checkpoint_dir=str(tmp_path / "ckpts"),
        llm_temperature=0.7,
        litellm_model="model-a",
    )
    session = create_checkpoint_session(
        config_a,
        query_id="task-mismatch",
        stock_code="AAPL",
        report_type="detailed",
        store=store,
    )
    ctx = AgentContext(query="q", stock_code="AAPL")
    ctx.add_opinion(_opinion("technical", "buy"))
    session.save_stage(
        agent_stage_name("technical"),
        capture_agent_stage_payload(ctx, stage_name="technical"),
    )

    config_b = _config(
        analysis_checkpoint_dir=str(tmp_path / "ckpts"),
        llm_temperature=0.2,
        litellm_model="model-b",
    )
    resumed = create_checkpoint_session(
        config_b,
        query_id="task-mismatch",
        stock_code="AAPL",
        report_type="detailed",
        store=store,
    )
    assert resumed.consistency == "full_rerun_incompatible"
    assert resumed.completed_stages == ()
    assert resumed.annotation["note"] == "compatibility_fingerprint_mismatch"


def test_force_full_ignores_existing_checkpoint(tmp_path: Path) -> None:
    store = AnalysisStageCheckpointStore(tmp_path / "ckpts", ttl_hours=24)
    config = _config(analysis_checkpoint_dir=str(tmp_path / "ckpts"))
    session = create_checkpoint_session(
        config,
        query_id="task-force",
        stock_code="00700",
        store=store,
    )
    ctx = AgentContext(query="q", stock_code="00700")
    ctx.add_opinion(_opinion("technical", "sell"))
    session.save_stage(
        agent_stage_name("technical"),
        capture_agent_stage_payload(ctx, stage_name="technical"),
    )

    forced = create_checkpoint_session(
        config,
        query_id="task-force",
        stock_code="00700",
        force_full=True,
        store=store,
    )
    assert forced.consistency == "full_rerun_forced"
    assert forced.completed_stages == ()
    assert forced.force_full is True


def test_disabled_checkpoint_has_no_resume_side_effects(tmp_path: Path) -> None:
    store = AnalysisStageCheckpointStore(tmp_path / "ckpts", ttl_hours=24)
    config = _config(
        analysis_checkpoint_enabled=False,
        analysis_checkpoint_dir=str(tmp_path / "ckpts"),
    )
    session = create_checkpoint_session(
        config,
        query_id="task-off",
        stock_code="600519",
        store=store,
    )
    assert session.enabled is False
    assert session.consistency == "checkpoint_disabled"
    session.save_stage(agent_stage_name("technical"), {"opinions": []})
    assert session.completed_stages == ()
    disabled_root = tmp_path / "disabled-root"
    create_checkpoint_session(
        _config(
            analysis_checkpoint_enabled=False,
            analysis_checkpoint_dir=str(disabled_root),
        ),
        query_id="disabled-no-store",
        stock_code="600519",
    )
    assert not disabled_root.exists()
    inactive_root = tmp_path / "inactive-single-agent"
    inactive = create_checkpoint_session(
        _config(analysis_checkpoint_dir=str(inactive_root)),
        query_id="single-agent",
        stock_code="600519",
        active=False,
    )
    assert inactive.enabled is False
    assert not inactive_root.exists()


def test_repro_mode_pins_seed_and_temperature() -> None:
    config = _config(repro_mode_enabled=True, repro_seed=42, llm_temperature=0.9)
    status = apply_repro_mode(config)
    assert status["enabled"] is True
    assert status["seed"] == 42
    assert status["temperature_pinned"] is True
    assert status["scope"] == "request"
    assert config.llm_temperature == 0.9
    assert resolve_repro_generation_params(config, 0.9) == (0.0, 42)


def test_record_config_false_hides_snapshot_without_disabling_checkpoint(tmp_path: Path) -> None:
    session = create_checkpoint_session(
        _config(
            analysis_checkpoint_dir=str(tmp_path / "ckpts"),
            repro_record_config=False,
        ),
        query_id="no-audit-snapshot",
        stock_code="AAPL",
    )
    metadata = session.metadata_for_snapshot()
    assert session.enabled is True
    assert session.compatibility_fingerprint
    assert metadata["run_configuration"] == {}


def test_repro_snapshot_and_fingerprint_are_stable() -> None:
    config = _config(repro_mode_enabled=True, repro_seed=7)
    snap1 = build_repro_snapshot(config, skills=["bull_trend"], seed=7)
    snap2 = build_repro_snapshot(config, skills=["bull_trend"], seed=7)
    assert snap1["fingerprint"] == snap2["fingerprint"]
    assert "limitations" in snap1
    assert snap1["models"]["litellm_model"] == "test-model"
    fp1 = build_compatibility_fingerprint(
        stock_code="600519",
        repro_snapshot=snap1,
        report_type="detailed",
        analysis_phase="auto",
    )
    fp2 = build_compatibility_fingerprint(
        stock_code="600519",
        repro_snapshot=snap2,
        report_type="detailed",
        analysis_phase="auto",
    )
    assert fp1 == fp2
    changed = build_repro_snapshot(
        _config(repro_mode_enabled=True, repro_seed=7, agent_tool_timeout_s=9),
        skills=["bull_trend"],
        seed=7,
    )
    baseline_with_timeout = build_repro_snapshot(
        _config(repro_mode_enabled=True, repro_seed=7, agent_tool_timeout_s=8),
        skills=["bull_trend"],
        seed=7,
    )
    assert changed["fingerprint"] != baseline_with_timeout["fingerprint"]


def test_opinion_roundtrip_preserves_conclusion_fields() -> None:
    original = _opinion("decision", "buy", confidence=0.91)
    payload = serialize_agent_opinion(original)
    from src.services.analysis_stage_checkpoint import deserialize_agent_opinion

    restored = deserialize_agent_opinion(payload)
    assert restored.agent_name == original.agent_name
    assert restored.signal == original.signal
    assert restored.confidence == original.confidence
    assert restored.reasoning == original.reasoning


def test_ttl_cleanup_removes_old_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = AnalysisStageCheckpointStore(tmp_path / "ckpts", ttl_hours=1)
    store.ensure_root()
    run_dir = store._run_dir("old", "600519")
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text("{}", encoding="utf-8")
    old_mtime = 1_000_000.0
    monkeypatch.setattr(
        "src.services.analysis_stage_checkpoint.time.time",
        lambda: old_mtime + 10_000,
    )
    import os

    os.utime(run_dir, (old_mtime, old_mtime))
    removed = store.cleanup_expired()
    assert removed == 1
    assert not run_dir.exists()


class _ReplayStage:
    def __init__(self, name: str, calls: list[str], *, interrupt: bool = False) -> None:
        self.agent_name = name
        self.calls = calls
        self.interrupt = interrupt
        self.tool_names: list[str] = []

    def run(self, ctx: AgentContext, **_kwargs) -> StageResult:
        self.calls.append(self.agent_name)
        if self.interrupt:
            raise KeyboardInterrupt("simulated process interrupt")
        signal = "buy" if self.agent_name in {"technical", "decision"} else "hold"
        ctx.add_opinion(_opinion(self.agent_name, signal))
        ctx.set_data(f"{self.agent_name}_result", {"signal": signal})
        if self.agent_name == "decision":
            ctx.set_data("final_response_text", "deterministic final response")
        return StageResult(
            stage_name=self.agent_name,
            status=StageStatus.COMPLETED,
        )


def _run_real_orchestrator(session, stages: list[_ReplayStage]) -> AgentContext:
    from src.agent.orchestrator import AgentOrchestrator

    config = _config(
        agent_orchestrator_timeout_s=0,
        agent_mode_budget_enabled=False,
    )
    orchestrator = AgentOrchestrator(
        tool_registry=MagicMock(),
        llm_adapter=MagicMock(),
        config=config,
        mode="standard",
    )
    ctx = AgentContext(query="Analyze 600519", stock_code="600519")
    ctx.set_data("market_input", {"close": 10.0, "as_of": "2026-08-13"})
    ctx.meta[META_SESSION_KEY] = session
    with patch.object(orchestrator, "_build_agent_chain", return_value=stages):
        result = orchestrator._execute_pipeline(ctx, parse_dashboard=False)
    assert result.success is True
    return ctx


def test_real_orchestrator_interrupt_resume_skips_completed_stage_and_restores_final_state(
    tmp_path: Path,
) -> None:
    store = AnalysisStageCheckpointStore(tmp_path / "ckpts", ttl_hours=24)
    config = _config(analysis_checkpoint_dir=str(tmp_path / "ckpts"))

    full_session = create_checkpoint_session(
        config,
        query_id="full-run",
        stock_code="600519",
        store=store,
    )
    full_calls: list[str] = []
    full_ctx = _run_real_orchestrator(
        full_session,
        [_ReplayStage(name, full_calls) for name in ("technical", "intel", "decision")],
    )
    assert full_calls == ["technical", "intel", "decision"]

    interrupted_session = create_checkpoint_session(
        config,
        query_id="resume-run",
        stock_code="600519",
        store=store,
    )
    interrupted_calls: list[str] = []
    from src.agent.orchestrator import AgentOrchestrator

    interrupted_orchestrator = AgentOrchestrator(
        tool_registry=MagicMock(),
        llm_adapter=MagicMock(),
        config=_config(agent_orchestrator_timeout_s=0, agent_mode_budget_enabled=False),
        mode="standard",
    )
    interrupted_ctx = AgentContext(query="Analyze 600519", stock_code="600519")
    interrupted_ctx.set_data("market_input", {"close": 10.0, "as_of": "2026-08-13"})
    interrupted_ctx.meta[META_SESSION_KEY] = interrupted_session
    interrupted_stages = [
        _ReplayStage("technical", interrupted_calls),
        _ReplayStage("intel", interrupted_calls, interrupt=True),
        _ReplayStage("decision", interrupted_calls),
    ]
    with patch.object(
        interrupted_orchestrator,
        "_build_agent_chain",
        return_value=interrupted_stages,
    ), pytest.raises(KeyboardInterrupt):
        interrupted_orchestrator._execute_pipeline(interrupted_ctx, parse_dashboard=False)
    assert interrupted_calls == ["technical", "intel"]

    resumed_session = create_checkpoint_session(
        config,
        query_id="resume-run",
        stock_code="600519",
        store=store,
    )
    resumed_calls: list[str] = []
    resumed_ctx = _run_real_orchestrator(
        resumed_session,
        [_ReplayStage(name, resumed_calls) for name in ("technical", "intel", "decision")],
    )
    assert resumed_calls == ["intel", "decision"]
    assert [serialize_agent_opinion(item) for item in resumed_ctx.opinions] == [
        serialize_agent_opinion(item) for item in full_ctx.opinions
    ]
    assert resumed_ctx.data == full_ctx.data

    completed_resume = create_checkpoint_session(
        config,
        query_id="full-run",
        stock_code="600519",
        store=store,
    )
    replay_calls: list[str] = []
    replay_ctx = _run_real_orchestrator(
        completed_resume,
        [_ReplayStage(name, replay_calls) for name in ("technical", "intel", "decision")],
    )
    assert replay_calls == []
    assert replay_ctx.data == full_ctx.data


def test_changed_agent_input_forces_full_rerun(tmp_path: Path) -> None:
    store = AnalysisStageCheckpointStore(tmp_path / "ckpts", ttl_hours=24)
    config = _config(analysis_checkpoint_dir=str(tmp_path / "ckpts"))
    session = create_checkpoint_session(
        config,
        query_id="changed-input",
        stock_code="AAPL",
        store=store,
    )
    original = AgentContext(query="Analyze AAPL", stock_code="AAPL")
    original.set_data("market_input", {"close": 100.0})
    original.meta["_checkpoint_agent_input_fingerprint"] = build_agent_input_fingerprint(original)
    original.add_opinion(_opinion("technical", "buy"))
    session.save_stage(
        agent_stage_name("technical"),
        capture_agent_stage_payload(original, stage_name="technical"),
    )

    resumed = create_checkpoint_session(
        config,
        query_id="changed-input",
        stock_code="AAPL",
        store=store,
    )
    changed = AgentContext(query="Analyze AAPL", stock_code="AAPL")
    changed.set_data("market_input", {"close": 101.0})
    assert restore_agent_context_from_session(resumed, changed) == []
    assert resumed.consistency == "full_rerun_corrupt_checkpoint"
    assert resumed.annotation["note"] == "agent_input_fingerprint_mismatch"


def test_run_key_sanitization_does_not_alias_distinct_ids(tmp_path: Path) -> None:
    store = AnalysisStageCheckpointStore(tmp_path / "ckpts")
    assert store._run_dir("task/a", "AAPL") != store._run_dir("task_a", "AAPL")


def test_concurrent_store_instances_merge_completed_stage_manifest(tmp_path: Path) -> None:
    root = tmp_path / "ckpts"
    config = _config(analysis_checkpoint_dir=str(root))
    first = create_checkpoint_session(
        config,
        query_id="concurrent",
        stock_code="MSFT",
        store=AnalysisStageCheckpointStore(root),
    )
    second = create_checkpoint_session(
        config,
        query_id="concurrent",
        stock_code="MSFT",
        store=AnalysisStageCheckpointStore(root),
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(
            pool.map(
                lambda pair: pair[0].save_stage(pair[1], {"context": {}}),
                (
                    (first, agent_stage_name("technical")),
                    (second, agent_stage_name("intel")),
                ),
            )
        )
    manifest = AnalysisStageCheckpointStore(root).load_manifest("concurrent", "MSFT")
    assert manifest is not None
    assert set(manifest.completed_stages) == {
        agent_stage_name("technical"),
        agent_stage_name("intel"),
    }


def test_stale_incompatible_session_cannot_overwrite_persisted_stage(
    tmp_path: Path,
) -> None:
    root = tmp_path / "ckpts"
    config = _config(analysis_checkpoint_dir=str(root))
    store = AnalysisStageCheckpointStore(root)
    current = create_checkpoint_session(
        config,
        query_id="shared-run",
        stock_code="MSFT",
        store=store,
    )
    stage = agent_stage_name("technical")
    current.save_stage(stage, {"owner": "current"})

    stale = create_checkpoint_session(
        config,
        query_id="shared-run",
        stock_code="MSFT",
        store=AnalysisStageCheckpointStore(root),
    )
    stale.compatibility_fingerprint = "stale-incompatible-fingerprint"
    assert stale.manifest is not None
    stale.manifest.compatibility_fingerprint = stale.compatibility_fingerprint
    stale.save_stage(stage, {"owner": "stale"})

    persisted = store.load_stage("shared-run", "MSFT", stage)
    assert stale.enabled is False
    assert persisted is not None
    assert persisted.payload == {"owner": "current"}


def test_corrupt_manifest_is_replaced_with_fail_closed_full_rerun(tmp_path: Path) -> None:
    store = AnalysisStageCheckpointStore(tmp_path / "ckpts")
    config = _config(analysis_checkpoint_dir=str(tmp_path / "ckpts"))
    store.ensure_root()
    run_dir = store._run_dir("corrupt", "AAPL")
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text("{", encoding="utf-8")

    session = create_checkpoint_session(
        config,
        query_id="corrupt",
        stock_code="AAPL",
        store=store,
    )
    assert session.consistency == "full_rerun_corrupt_checkpoint"
    assert session.completed_stages == ()


def test_checkpoint_context_is_request_scoped_across_threads(tmp_path: Path) -> None:
    config = _config(analysis_checkpoint_enabled=False)
    sessions = [
        create_checkpoint_session(
            config,
            query_id=f"thread-{index}",
            stock_code=stock,
            store=AnalysisStageCheckpointStore(tmp_path / "ckpts"),
        )
        for index, stock in enumerate(("AAPL", "MSFT"))
    ]

    def _observe(session):
        token = activate_checkpoint_session(session)
        try:
            return current_checkpoint_session().stock_code
        finally:
            reset_checkpoint_session(token)

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert set(pool.map(_observe, sessions)) == {"AAPL", "MSFT"}
    assert current_checkpoint_session() is None


@patch("src.config.setup_env")
@patch("src.config.Config._parse_litellm_yaml", return_value=[])
@patch("src.config.Config._parse_stock_email_groups", return_value=[])
def test_checkpoint_and_repro_config_load_from_environment(
    _mock_groups,
    _mock_litellm,
    _mock_setup_env,
    tmp_path: Path,
) -> None:
    from src.config import Config

    with patch.dict(
        os.environ,
        {
            "STOCK_LIST": "600519",
            "ANALYSIS_CHECKPOINT_ENABLED": "false",
            "ANALYSIS_CHECKPOINT_DIR": str(tmp_path / "custom"),
            "ANALYSIS_CHECKPOINT_TTL_HOURS": "0",
            "ANALYSIS_CHECKPOINT_FORCE_FULL": "true",
            "REPRO_MODE_ENABLED": "true",
            "REPRO_RECORD_CONFIG": "false",
            "REPRO_SEED": "31",
        },
        clear=True,
    ):
        config = Config._load_from_env()

    assert config.analysis_checkpoint_enabled is False
    assert config.analysis_checkpoint_dir == str(tmp_path / "custom")
    assert config.analysis_checkpoint_ttl_hours == 0
    assert config.analysis_checkpoint_force_full is True
    assert config.repro_mode_enabled is True
    assert config.repro_record_config is False
    assert config.repro_seed == 31
