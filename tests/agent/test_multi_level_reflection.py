# -*- coding: utf-8 -*-
"""Tests for multi-level reflection (Issue #1094)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.agent.evolution.budget import (
    MAX_REFLECTION_LLM_CALL_BUDGET,
    LlmCallBudget,
)
from src.agent.evolution.episode_lessons import (
    InMemoryEpisodeLessonSink,
    record_reflection_lessons,
)
from src.agent.evolution.lessons import LESSON_KINDS, ReflectionLesson
from src.agent.evolution.meta_review import (
    MAX_META_EPISODES,
    run_meta_review,
    write_meta_review_report,
)
from src.agent.evolution.multilevel import (
    run_cross_run_layer,
    run_immediate_layer,
    run_trajectory_layer,
)
from src.agent.evolution.reflection import parse_reflection_output, run_reflection_loop
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

    config = SimpleNamespace(agent_step_critique_enabled=True)
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
        config=SimpleNamespace(agent_step_critique_enabled=True),
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
        agent_reflection_enabled=True,
        agent_reflection_llm_budget=0,
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


def test_trajectory_layer_rejects_corrupt_immediate_lesson_payload() -> None:
    ctx = _Ctx(run_id="run-corrupt")
    ctx.meta["step_critique_result"] = {
        "lessons": [{"kind": "invented", "severity": "high"}]
    }
    with pytest.raises(ValueError, match="kind"):
        run_trajectory_layer(
            ctx,
            config=SimpleNamespace(
                agent_reflection_enabled=True,
                agent_reflection_llm_budget=0,
                agent_reflection_in_chat=False,
            ),
        )


def test_reflection_boundaries_are_explicit_for_zero_lessons_and_revision_cap() -> None:
    config = SimpleNamespace(agent_reflection_enabled=True)
    no_lesson_calls = 0

    def unexpected_revision(_ctx, _lessons):
        nonlocal no_lesson_calls
        no_lesson_calls += 1
        raise AssertionError("zero lessons must not trigger revision")

    empty = run_reflection_loop(
        _Ctx(run_id="run-empty"),
        config=config,
        llm_complete=lambda _system, _user: json.dumps(
            {"lessons": [], "revised": False}
        ),
        revise_fn=unexpected_revision,
        budget=LlmCallBudget(total=1),
        max_revise=1,
    )

    assert empty.status == "completed"
    assert empty.terminate_reason == "ok"
    assert empty.validation_status == "valid"
    assert empty.lessons == []
    assert empty.revised is False
    assert no_lesson_calls == 0

    revision_calls = 0
    events = []

    def revise_once(_ctx, lessons):
        nonlocal revision_calls
        revision_calls += 1
        assert [lesson.kind for lesson in lessons] == ["evidence_gap"]
        return True

    revised = run_reflection_loop(
        _Ctx(run_id="run-revised"),
        config=config,
        llm_complete=lambda _system, _user: json.dumps(
            {
                "lessons": [{"kind": "evidence_gap", "severity": "medium"}],
                "revised": False,
            }
        ),
        revise_fn=revise_once,
        budget=LlmCallBudget(total=1),
        max_revise=1,
        event_sink=lambda name, payload: events.append((name, payload)),
    )

    assert revised.status == "completed"
    assert revised.revised is True
    assert revision_calls == 1
    assert [name for name, _payload in events].count("reflect_revise") == 1

    capped_calls = 0
    capped_events = []

    def exhaust_revision_cap(_ctx, _lessons):
        nonlocal capped_calls
        capped_calls += 1
        return False

    capped = run_reflection_loop(
        _Ctx(run_id="run-cap-exhausted"),
        config=config,
        llm_complete=lambda _system, _user: json.dumps(
            {
                "lessons": [{"kind": "evidence_gap", "severity": "medium"}],
                "revised": False,
            }
        ),
        revise_fn=exhaust_revision_cap,
        budget=LlmCallBudget(total=1),
        max_revise=1,
        event_sink=lambda name, payload: capped_events.append((name, payload)),
    )

    assert capped.status == "completed"
    assert capped.terminate_reason == "ok"
    assert capped.revised is False
    assert capped_calls == 1
    assert [name for name, _payload in capped_events].count("reflect_revise") == 0


def test_meta_review_sample_threshold_and_actions(tmp_path):
    config = SimpleNamespace(
        agent_meta_review_enabled=True,
        agent_meta_review_min_episodes=30,
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
    payload = report.to_dict()
    assert payload["mutates_soul"] is False
    assert payload["mutates_tool_surface"] is False
    assert payload["mutates_runtime_config"] is False
    assert any("investigate" in a or "tighten" in a or "promote" in a for a in report.recommended_actions)

    paths = write_meta_review_report(report, tmp_path)
    assert Path(paths["markdown"]).is_file()
    assert Path(paths["json"]).is_file()
    md = Path(paths["markdown"]).read_text(encoding="utf-8")
    assert "Top failure kinds" in md
    assert "Recommended actions" in md
    assert report.worst_tools[0]["count"] == 35


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


def test_reflection_budget_and_parser_reject_coercions():
    for value in (True, 1.0, -1, MAX_REFLECTION_LLM_CALL_BUDGET + 1):
        with pytest.raises((TypeError, ValueError)):
            LlmCallBudget(total=value)

    budget = LlmCallBudget(total=0)
    with pytest.raises(TypeError):
        budget.record_skip(reason=1)  # type: ignore[arg-type]
    assert budget.skips == 0
    with pytest.raises(ValueError, match="consumed"):
        LlmCallBudget(total=1, consumed=2)
    with pytest.raises(TypeError, match="skip reason"):
        LlmCallBudget(total=1, skip_reasons=[1])

    parsed = parse_reflection_output(
        json.dumps({"lessons": [], "revised": "false"})
    )
    assert parsed.validation_status == "invalid"
    assert parsed.revised is False


def test_immediate_layer_bounds_inputs_and_records_llm_failures():
    with pytest.raises(ValueError, match="observations exceeds"):
        should_trigger_step_critique([{}] * 17)

    observation = [
        {
            "step_id": "x" * 200,
            "status": "FAILED",
            "tool_calls": [
                {
                    "tool_name": "provider" + ("x" * 200),
                    "ok": False,
                    "error_code": "provider_error",
                },
                "malformed",
            ],
        }
    ]
    invalid = critique_step_observations(
        observation,
        config=SimpleNamespace(agent_step_critique_enabled=True),
        budget=LlmCallBudget(total=1),
        llm_complete=lambda _system, _user: "not-json",
    )
    assert invalid.lessons
    assert invalid.validation_status == "invalid"
    assert all(len(lesson.source_step or "") <= 64 for lesson in invalid.lessons)

    def provider_failure(_system: str, _user: str) -> str:
        raise RuntimeError("provider down")

    failed = critique_step_observations(
        observation,
        config=SimpleNamespace(agent_step_critique_enabled=True),
        budget=LlmCallBudget(total=1),
        llm_complete=provider_failure,
    )
    assert failed.lessons
    assert failed.validation_status == "error"
    assert "RuntimeError" in (failed.skip_reason or "")


def test_meta_review_is_deterministic_strict_and_path_safe(tmp_path):
    episodes = [
        {
            "run_id": "run-b",
            "mode": "single",
            "revised": True,
            "lessons": [
                {
                    "kind": "tool_failure",
                    "remedy": "retry",
                    "source_step": "step:1:quotes",
                },
                {
                    "kind": "tool_failure",
                    "remedy": "retry",
                    "source_step": "step:1:quotes",
                },
            ],
            "trajectory_summary": [{"tool": "quotes", "success": False}],
        },
        {
            "run_id": "run-a",
            "mode": "single",
            "revised": False,
            "lessons": [
                {
                    "kind": "evidence_gap",
                    "remedy": "fetch",
                    "source_step": "step:2:news",
                }
            ],
            "trajectory_summary": [{"tool": "news", "success": False}],
        },
    ]
    config = SimpleNamespace(
        agent_meta_review_enabled=True,
        agent_meta_review_min_episodes=1,
    )
    first = run_meta_review(episodes, config=config, min_kind_count=1).to_dict()
    second = run_meta_review(
        list(reversed(episodes)), config=config, min_kind_count=1
    ).to_dict()
    first.pop("generated_at")
    second.pop("generated_at")
    assert first == second
    assert next(item for item in first["worst_tools"] if item["tool"] == "quotes")[
        "count"
    ] == 1

    with pytest.raises(ValueError, match="duplicate"):
        run_meta_review([episodes[0], episodes[0]], config=config)
    with pytest.raises(ValueError, match="trajectory_summary"):
        run_meta_review(
            [{"run_id": "bad", "trajectory_summary": "not-a-list"}],
            config=config,
        )
    with pytest.raises(ValueError, match="trajectory success"):
        run_meta_review(
            [
                {
                    "run_id": "bad-success",
                    "trajectory_summary": [{"tool": "quotes", "success": "false"}],
                }
            ],
            config=config,
        )
    with pytest.raises(ValueError, match="episode meta"):
        run_meta_review([{"run_id": "bad-meta", "meta": []}], config=config)
    with pytest.raises(ValueError, match="revised"):
        run_meta_review(
            [{"run_id": "bad-revised", "revised": "false"}], config=config
        )
    with pytest.raises(ValueError, match="reflection_result"):
        run_meta_review(
            [{"run_id": "bad-reflection", "reflection_result": ""}],
            config=config,
        )
    with pytest.raises(ValueError, match="kind"):
        run_meta_review(
            [{"run_id": "bad-kind", "lessons": [{"kind": "invented"}]}],
            config=config,
        )
    with pytest.raises(ValueError, match="episode meta"):
        run_meta_review(
            [{"run_id": "bad-below-threshold", "meta": []}],
            config=SimpleNamespace(
                agent_meta_review_enabled=True,
                agent_meta_review_min_episodes=30,
            ),
        )
    with pytest.raises(ValueError, match="basename"):
        write_meta_review_report(
            run_meta_review(episodes, config=config, min_kind_count=1),
            tmp_path,
            basename="../escape",
        )

    invalid_llm = run_meta_review(
        episodes,
        config=config,
        min_kind_count=1,
        budget=LlmCallBudget(total=1),
        llm_complete=lambda _system, _user: "prose is not accepted",
    )
    assert invalid_llm.validation_status == "invalid"
    assert invalid_llm.strategy_note is None

    with pytest.raises(ValueError, match="episodes exceeds"):
        run_meta_review(
            [
                {"run_id": f"run-{index}"}
                for index in range(MAX_META_EPISODES + 1)
            ],
            config=config,
        )


def test_meta_review_cli_force_is_not_always_true(tmp_path):
    """Regression: ``force=args.force or True`` used to ignore --force semantics."""
    import importlib.util
    from pathlib import Path as _Path

    script = _Path(__file__).resolve().parents[2] / "scripts" / "run_meta_review.py"
    spec = importlib.util.spec_from_file_location("run_meta_review_cli", script)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    disabled = SimpleNamespace(
        agent_meta_review_enabled=False,
        agent_meta_review_min_episodes=30,
    )
    cfg = mod.resolve_cli_runtime(
        force=False,
        min_episodes=30,
        get_config=lambda: disabled,
    )
    assert cfg is disabled

    def config_failure():
        raise RuntimeError("config unavailable")

    with pytest.raises(RuntimeError, match="config unavailable"):
        mod.resolve_cli_runtime(
            force=False,
            min_episodes=30,
            get_config=config_failure,
        )

    episodes = [
        {"run_id": f"r{i}", "lessons": [{"kind": "tool_failure", "severity": "high"}]}
        for i in range(5)
    ]
    ep_path = tmp_path / "episodes.json"
    ep_path.write_text(json.dumps(episodes), encoding="utf-8")
    out_dir = tmp_path / "out"

    mod.resolve_cli_runtime = lambda **_kwargs: disabled
    # Without --force and with disabled config → status disabled.
    code = mod.main(
        [
            "--episodes",
            str(ep_path),
            "--output-dir",
            str(out_dir / "off"),
            "--min-episodes",
            "3",
        ]
    )
    assert code == 0
    off_payload = json.loads((out_dir / "off" / "meta_review.json").read_text())
    assert off_payload["status"] == "disabled"

    code = mod.main(
        [
            "--episodes",
            str(ep_path),
            "--output-dir",
            str(out_dir / "on"),
            "--min-episodes",
            "3",
            "--force",
        ]
    )
    assert code == 0
    on_payload = json.loads((out_dir / "on" / "meta_review.json").read_text())
    assert on_payload["status"] == "completed"

    mixed = tmp_path / "mixed.json"
    mixed.write_text(json.dumps([episodes[0], "bad"]), encoding="utf-8")
    assert mod.main(["--episodes", str(mixed), "--force"]) == 2

    oversized = tmp_path / "oversized.json"
    with oversized.open("wb") as stream:
        stream.seek(mod.MAX_EPISODE_FILE_BYTES)
        stream.write(b"x")
    assert mod.main(["--episodes", str(oversized), "--force"]) == 2
