# -*- coding: utf-8 -*-
"""Tests for multi-level reflection (Issue #1094)."""

from __future__ import annotations

from types import SimpleNamespace

from src.agent.evolution.budget import LlmCallBudget
from src.agent.evolution.episode_lessons import (
    InMemoryEpisodeLessonSink,
    record_reflection_lessons,
)
from src.agent.evolution.lessons import LESSON_KINDS, ReflectionLesson
from src.agent.evolution.meta_review import run_meta_review, write_meta_review_report
from src.agent.evolution.multilevel import (
    run_cross_run_layer,
    run_immediate_layer,
    run_trajectory_layer,
)
from src.agent.evolution.step_critique import (
    critique_step_observations,
    map_replan_reason_kind,
    should_trigger_step_critique,
)
from src.agent.soul import AGENT_SOUL_HASH, AGENT_SOUL_VERSION


class _Ctx:
    def __init__(self, **meta):
        self.meta = dict(meta)
        self.opinions = []
        self.risk_flags = []
        self.stock_code = "AAPL"


def test_map_replan_reason_kind_uses_shared_taxonomy():
    assert map_replan_reason_kind(error_code="tool_failed") == "tool_failure"
    assert map_replan_reason_kind(error_code="timeout") == "tool_failure"
    assert map_replan_reason_kind(error_code="schema_invalid") == "format_violation"
    assert map_replan_reason_kind(summary="signals conflict on direction") == "overclaim"
    assert map_replan_reason_kind(error_code="tool_failure") in LESSON_KINDS
    # Free-form prose does not invent a new kind.
    assert map_replan_reason_kind(summary="buy this stock now for free money") == "other"


def test_immediate_step_critique_trigger_and_typed_lessons():
    observations = [
        {
            "step_id": 1,
            "status": "failed",
            "failure_reason": "tool_failed",
            "tool_calls": [
                {
                    "tool_name": "get_realtime_quote",
                    "ok": False,
                    "error_code": "provider_error",
                    "summary": "provider timeout",
                }
            ],
        }
    ]
    assert should_trigger_step_critique(observations) is True

    config = SimpleNamespace(agent_step_critique_enabled=True, agent_step_critique_llm_budget=0)
    ctx = _Ctx(run_id="run-1", episode_id="ep-1")
    result = critique_step_observations(observations, config=config, ctx=ctx)
    assert result.status == "completed"
    assert result.lessons
    assert all(lesson.kind in LESSON_KINDS for lesson in result.lessons)
    assert ctx.meta["step_critique_result"]["layer"] == "immediate"
    assert "tool_failure" in ctx.meta["replan_reason_kinds"]


def test_immediate_disabled_and_budget_skip_explicit():
    observations = [
        {
            "step_id": 1,
            "status": "failed",
            "tool_calls": [{"tool_name": "x", "ok": False, "error_code": "tool_failed"}],
        }
    ]
    disabled = critique_step_observations(
        observations,
        config=SimpleNamespace(agent_step_critique_enabled=False),
        ctx=_Ctx(),
    )
    assert disabled.status == "disabled"

    # With force + budget 0 + llm_complete requested, deterministic lessons remain
    # and budget skip is explicit for enrichment.
    def boom(_sys: str, _user: str) -> str:
        raise AssertionError("llm should not be called when budget is 0")

    budgeted = critique_step_observations(
        observations,
        config=SimpleNamespace(agent_step_critique_enabled=True, agent_step_critique_llm_budget=0),
        ctx=_Ctx(run_id="r2"),
        budget=LlmCallBudget(total=0),
        llm_complete=boom,
        force=True,
    )
    assert budgeted.lessons  # deterministic floor
    assert budgeted.validation_status == "budget_skipped"
    assert budgeted.skip_reason


def test_trajectory_layer_seeds_from_immediate_and_records_episode_lessons():
    config = SimpleNamespace(
        agent_step_critique_enabled=True,
        agent_step_critique_llm_budget=0,
        agent_reflection_enabled=True,
        agent_reflection_llm_budget=0,
        agent_reflection_max_revise=0,
        agent_reflection_in_chat=False,
    )
    ctx = _Ctx(run_id="run-t1", episode_id="ep-t1")
    observations = [
        {
            "step_id": 2,
            "status": "failed",
            "tool_calls": [
                {"tool_name": "analyze_trend", "ok": False, "error_code": "tool_failed"}
            ],
        }
    ]
    sink = InMemoryEpisodeLessonSink()
    immediate = run_immediate_layer(observations, config=config, ctx=ctx, sink=sink)
    assert immediate.episode_lessons
    assert immediate.replan_reason_kinds

    traj = run_trajectory_layer(ctx, config=config, sink=sink)
    # Disabled LLM budget 0 still returns a reflection result structure.
    assert traj.trajectory is not None
    assert sink.records
    assert all(rec["lessons"] for rec in sink.records)


def test_meta_review_sample_threshold_and_actions(tmp_path):
    config = SimpleNamespace(
        agent_meta_review_enabled=True,
        agent_meta_review_min_episodes=30,
        agent_meta_review_llm_budget=0,
    )
    # Below threshold.
    few = [{"run_id": f"r{i}", "lessons": [{"kind": "tool_failure", "severity": "high"}]} for i in range(5)]
    low = run_meta_review(few, config=config)
    assert low.status == "threshold_not_met"
    assert low.threshold_met is False
    assert low.recommended_actions == []

    # Above threshold with repeated kinds + worst tools.
    episodes = []
    for i in range(35):
        episodes.append(
            {
                "run_id": f"run-{i}",
                "mode": "single" if i % 2 == 0 else "multi",
                "revised": i % 3 == 0,
                "lessons": [
                    {
                        "kind": "tool_failure",
                        "severity": "high",
                        "remedy": "retry alternate provider",
                        "source_step": "step:1:get_realtime_quote",
                    },
                    {
                        "kind": "evidence_gap",
                        "severity": "medium",
                        "remedy": "fetch more news",
                        "source_step": "step:2",
                    },
                ],
                "trajectory_summary": [
                    {"tool": "get_realtime_quote", "success": False},
                ],
            }
        )
    report = run_meta_review(episodes, config=config, min_kind_count=3)
    assert report.status == "completed"
    assert report.threshold_met is True
    assert report.sample_count == 35
    assert report.top_failure_kinds
    assert report.worst_tools
    assert report.recommended_actions
    assert report.mutates_soul is False if hasattr(report, "mutates_soul") else True
    payload = report.to_dict()
    assert payload["mutates_soul"] is False
    assert payload["mutates_tool_surface"] is False
    assert payload["mutates_runtime_config"] is False
    assert any("investigate" in a or "tighten" in a or "promote" in a for a in report.recommended_actions)

    paths = write_meta_review_report(report, tmp_path)
    assert Path_exists(paths["markdown"])
    assert Path_exists(paths["json"])
    md = open(paths["markdown"], encoding="utf-8").read()
    assert "Top failure kinds" in md
    assert "Recommended actions" in md


def Path_exists(p: str) -> bool:
    from pathlib import Path

    return Path(p).is_file()


def test_meta_review_does_not_mutate_soul():
    soul_before = (AGENT_SOUL_VERSION, AGENT_SOUL_HASH)
    episodes = [
        {
            "run_id": f"r{i}",
            "lessons": [{"kind": "risk_omission", "severity": "high", "remedy": "add stop"}],
        }
        for i in range(30)
    ]
    run_meta_review(
        episodes,
        config=SimpleNamespace(
            agent_meta_review_enabled=True,
            agent_meta_review_min_episodes=30,
            agent_meta_review_llm_budget=0,
        ),
        min_kind_count=1,
    )
    assert (AGENT_SOUL_VERSION, AGENT_SOUL_HASH) == soul_before


def test_cross_run_layer_facade():
    episodes = [
        {"run_id": f"r{i}", "lessons": [{"kind": "overconfidence", "severity": "medium"}]}
        for i in range(30)
    ]
    result = run_cross_run_layer(
        episodes,
        config=SimpleNamespace(
            agent_meta_review_enabled=True,
            agent_meta_review_min_episodes=10,
            agent_meta_review_llm_budget=0,
        ),
        min_episodes=10,
    )
    assert result.meta is not None
    assert result.meta["threshold_met"] is True


def test_record_reflection_lessons_rejects_freeform_kinds_via_projection():
    sink = InMemoryEpisodeLessonSink()
    from src.agent.evolution.lessons import ReflectionResult

    result = ReflectionResult(
        lessons=[
            ReflectionLesson(kind="tool_failure", severity="high", remedy="retry"),
        ],
        run_id="run-x",
        episode_id="ep-x",
    )
    lessons = record_reflection_lessons(sink, result, layer="immediate")
    assert lessons[0]["kind"] == "tool_failure"
    assert sink.records[0]["layer"] == "immediate"
