# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Stage checkpoint resume consistency and reproducibility controls."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.agent.protocols import AgentContext, AgentOpinion, StageResult, StageStatus
from src.services.analysis_stage_checkpoint import (
    AnalysisStageCheckpointStore,
    agent_stage_name,
    apply_repro_mode,
    build_compatibility_fingerprint,
    build_repro_snapshot,
    capture_agent_stage_payload,
    create_checkpoint_session,
    restore_agent_context_from_session,
    serialize_agent_opinion,
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
    full_ctx = AgentContext(query="full", stock_code=stock)
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
    mid_ctx = AgentContext(query="mid", stock_code=stock)
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
    resume_ctx = AgentContext(query="resume", stock_code=stock)
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


def test_repro_mode_pins_seed_and_temperature() -> None:
    config = _config(repro_mode_enabled=True, repro_seed=42, llm_temperature=0.9)
    status = apply_repro_mode(config)
    assert status["enabled"] is True
    assert status["seed_applied"] is True
    assert status["seed"] == 42
    assert status["temperature_pinned"] is True
    assert config.llm_temperature == 0.0


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
