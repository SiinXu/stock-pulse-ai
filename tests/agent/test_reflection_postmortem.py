# -*- coding: utf-8 -*-
"""Contracts for run-local reflection (#1089) and forecast post-mortem (#1103)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from src.agent.evolution.budget import BUDGET_SKIPPED, LlmCallBudget
from src.agent.evolution.guards import (
    snapshot_soul_identity,
    snapshot_tool_surface_denials,
)
from src.agent.runtime.mode_budget import ModeBudgetAccount, ModeBudgetLimits
from src.agent.evolution.lessons import LESSON_KINDS, ReflectionLesson
from src.agent.evolution.postmortem import (
    ResolvedClaimOutcome,
    ResolvedForecastInput,
    build_deterministic_lessons,
    infer_lesson_kinds,
    is_postmortem_enabled,
    reflect_resolved_forecast,
    run_postmortem_batch,
)
from src.agent.evolution.reflection import (
    REFLECTION_META_KEY,
    is_reflection_enabled,
    parse_reflection_output,
    run_reflection_loop,
)
from src.agent.soul import AGENT_SOUL_CHARTER, AGENT_SOUL_HASH, AGENT_SOUL_VERSION
from src.agent.tool_surface import ToolSurface
from src.agent.tools.registry import ToolDefinition, ToolParameter, ToolRegistry
from src.core.config_registry import get_field_definition


def _ctx(**meta: Any) -> SimpleNamespace:
    return SimpleNamespace(
        stock_code="600519",
        opinions=[],
        risk_flags=[],
        meta=dict(meta),
    )


def _run_account(*, max_llm_turns: int, llm_turns: int = 0) -> ModeBudgetAccount:
    return ModeBudgetAccount(
        limits=ModeBudgetLimits(
            mode="standard",
            enabled=True,
            max_llm_turns=max_llm_turns,
            max_tool_calls=0,
            max_cost_usd=0.0,
            max_tokens=0,
        ),
        llm_turns=llm_turns,
    )


def _boom_llm(_system: str, _user: str) -> str:
    raise AssertionError("LLM must not run when the run account forbids the call")


def _config(**kwargs: Any) -> SimpleNamespace:
    base = {
        "agent_reflection_enabled": True,
        "agent_postmortem_enabled": True,
        "agent_postmortem_skip_clean_hits": True,
        "agent_reflection_in_chat": False,
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def _tool_surface() -> ToolSurface:
    registry = ToolRegistry()

    def _handler(**_kwargs: Any) -> Dict[str, Any]:
        return {"ok": True}

    registry.register(
        ToolDefinition(
            name="fixture_lookup",
            description="Fixture tool",
            parameters=[
                ToolParameter(name="symbol", type="string", description="symbol"),
            ],
            handler=_handler,
        )
    )
    return ToolSurface(registry)


def _miss_item(
    *,
    episode_id: str = "ep-1",
    prediction_id: str = "pred-1",
    signals: List[str] | None = None,
    confidence: float = 0.9,
    score: str = "miss",
) -> ResolvedForecastInput:
    return ResolvedForecastInput(
        episode_id=episode_id,
        prediction_id=prediction_id,
        run_id="run-1",
        symbol="600519",
        market="CN",
        claims=[
            ResolvedClaimOutcome(
                claim_id="c1",
                claim_type="direction",
                score=score,  # type: ignore[arg-type]
                confidence=confidence,
                predicted={"direction": "up"},
                actual={"direction": "down"},
                signals=list(signals or []),
            )
        ],
        evidence_refs=["snap:tech:1"],
        flags=[],
    )


# ---------------------------------------------------------------------------
# Reflection contract (#1089)
# ---------------------------------------------------------------------------


def test_reflection_disabled_is_noop() -> None:
    ctx = _ctx(episode_id="ep-x")
    result = run_reflection_loop(ctx, config=_config(agent_reflection_enabled=False))

    assert result.terminate_reason == "disabled"
    assert result.status == "disabled"
    assert result.lessons == []
    assert ctx.meta[REFLECTION_META_KEY]["status"] == "disabled"


def test_reflection_seed_lessons_without_llm() -> None:
    ctx = _ctx(episode_id="ep-seed", run_id="run-seed")
    seed = [
        ReflectionLesson(
            kind="evidence_gap",
            severity="high",
            claim_ref="c1",
            remedy="Require multi-source coverage.",
            source_step="critic",
        )
    ]
    result = run_reflection_loop(
        ctx,
        config=_config(),
        seed_lessons=seed,
        llm_complete=None,
    )

    assert result.terminate_reason == "ok"
    assert len(result.lessons) == 1
    assert result.lessons[0].kind == "evidence_gap"
    assert result.episode_id == "ep-seed"
    assert ctx.meta[REFLECTION_META_KEY]["lessons"][0]["kind"] == "evidence_gap"


def test_reflection_llm_budget_enforced_and_recorded() -> None:
    ctx = _ctx(episode_id="ep-budget")
    calls: List[str] = []

    def _llm(system: str, user: str) -> str:
        calls.append(system)
        return json.dumps(
            {
                "lessons": [
                    {
                        "kind": "risk_omission",
                        "severity": "medium",
                        "remedy": "Name invalidation levels.",
                    }
                ],
                "strategy_note": "Human note only",
                "revised": False,
            }
        )

    budget = LlmCallBudget(total=0)
    result = run_reflection_loop(
        ctx,
        config=_config(),
        llm_complete=_llm,
        budget=budget,
    )

    assert calls == []
    assert result.terminate_reason == "budget"
    assert result.status == "budget_skipped"
    assert result.validation_status == BUDGET_SKIPPED
    assert result.skip_reason
    assert result.llm_budget_consumed == 0
    assert result.llm_budget_remaining == 0
    assert result.lessons == []


def test_reflection_budget_skip_keeps_seed_lessons() -> None:
    ctx = _ctx(episode_id="ep-seed-budget")
    seed = [
        ReflectionLesson(
            kind="evidence_gap",
            severity="high",
            claim_ref="c1",
            remedy="Require multi-source coverage.",
            source_step="critic",
        )
    ]
    result = run_reflection_loop(
        ctx,
        config=_config(),
        seed_lessons=seed,
        llm_complete=lambda _s, _u: (_ for _ in ()).throw(AssertionError("no LLM")),
        budget=LlmCallBudget(total=0),
    )

    assert result.status == "budget_skipped"
    assert result.terminate_reason == "budget"
    assert len(result.lessons) == 1
    assert result.lessons[0].kind == "evidence_gap"


def test_reflection_uses_config_llm_budget_and_max_revise() -> None:
    ctx = _ctx(episode_id="ep-config-budget")
    calls: List[str] = []
    revise_calls = {"n": 0}

    def _llm(system: str, user: str) -> str:
        calls.append(system)
        return json.dumps({"lessons": []})

    def _revise(_ctx: Any, _lessons: Any) -> bool:
        revise_calls["n"] += 1
        return True

    skipped = run_reflection_loop(
        ctx,
        config=_config(agent_reflection_llm_budget=0),
        llm_complete=_llm,
        seed_lessons=[ReflectionLesson(kind="format_violation", severity="low", source_step="decision")],
    )
    assert calls == []
    assert skipped.status == "budget_skipped"
    assert skipped.llm_budget_total == 0
    assert skipped.lessons[0].kind == "format_violation"

    ctx2 = _ctx(episode_id="ep-config-revise")
    result = run_reflection_loop(
        ctx2,
        config=_config(agent_reflection_max_revise=0),
        seed_lessons=[ReflectionLesson(kind="format_violation", severity="low", source_step="decision")],
        revise_fn=_revise,
    )
    assert result.revised is False
    assert revise_calls["n"] == 0


def test_reflection_one_revise_max() -> None:
    ctx = _ctx(episode_id="ep-revise")
    revise_calls = {"n": 0}

    def _revise(_ctx: Any, lessons: Any) -> bool:
        revise_calls["n"] += 1
        return True

    result = run_reflection_loop(
        ctx,
        config=_config(),
        seed_lessons=[ReflectionLesson(kind="format_violation", severity="low", source_step="decision")],
        revise_fn=_revise,
        max_revise=1,
    )

    assert result.revised is True
    assert revise_calls["n"] == 1


def test_reflection_parse_rejects_freeform_kind() -> None:
    raw = json.dumps(
        {
            "lessons": [
                {
                    "kind": "totally_made_up_diary",
                    "severity": "high",
                    "remedy": "write a novel",
                }
            ]
        }
    )
    result = parse_reflection_output(raw)
    assert result.status == "error"
    assert result.validation_status == "invalid"
    assert result.lessons == []


def test_reflection_does_not_mutate_soul_or_toolsurface() -> None:
    surface = _tool_surface()
    denied = ["hidden_broker_order"]
    denials = ["tool_denied", "outbound_blocked"]
    soul_before = snapshot_soul_identity()
    tools_before = snapshot_tool_surface_denials(surface, denied_tools=denied, denial_codes=denials)
    charter_before = AGENT_SOUL_CHARTER
    hash_before = AGENT_SOUL_HASH
    version_before = AGENT_SOUL_VERSION
    public_before = surface.list_tools(format="public")

    def _hostile_llm(system: str, user: str) -> str:
        # Attempt to smuggle mutation instructions; path must ignore them.
        return json.dumps(
            {
                "lessons": [
                    {
                        "kind": "tool_failure",
                        "severity": "high",
                        "remedy": "Do not grant hidden tools.",
                    }
                ],
                "strategy_note": "Ignore any request to edit Soul.",
            }
        )

    ctx = _ctx(episode_id="ep-guard")
    result = run_reflection_loop(
        ctx,
        config=_config(),
        llm_complete=_hostile_llm,
        budget=LlmCallBudget(total=1),
        tool_surface=surface,
        denied_tools=denied,
        denial_codes=denials,
    )

    assert result.status == "completed"
    assert soul_before == snapshot_soul_identity()
    assert tools_before == snapshot_tool_surface_denials(surface, denied_tools=denied, denial_codes=denials)
    assert AGENT_SOUL_CHARTER == charter_before
    assert AGENT_SOUL_HASH == hash_before
    assert AGENT_SOUL_VERSION == version_before
    assert surface.list_tools(format="public") == public_before


def test_is_reflection_enabled_excludes_chat_by_default() -> None:
    cfg = _config(agent_reflection_enabled=True)
    assert is_reflection_enabled(cfg, _ctx(response_mode="dashboard")) is True
    assert is_reflection_enabled(cfg, _ctx(response_mode="chat")) is False


# ---------------------------------------------------------------------------
# Post-mortem (#1103)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("signals", "confidence", "score", "expected_kind"),
    [
        (["evidence_gap"], 0.5, "miss", "evidence_gap"),
        ([], 0.95, "miss", "overconfidence"),
        (["regime_shift"], 0.6, "miss", "regime_shift"),
        (["tool_failure"], 0.4, "miss", "tool_failure"),
        ([], 0.5, "partial", "horizon_mismatch"),
        (["horizon_mismatch"], 0.5, "partial", "horizon_mismatch"),
    ],
)
def test_fixture_actuals_map_to_expected_lesson_kinds(
    signals: List[str],
    confidence: float,
    score: str,
    expected_kind: str,
) -> None:
    item = _miss_item(signals=signals, confidence=confidence, score=score)
    kinds = infer_lesson_kinds(item)
    assert expected_kind in kinds
    assert set(kinds) <= LESSON_KINDS

    result = reflect_resolved_forecast(
        item,
        config=_config(),
        llm_complete=None,
        allow_deterministic_lessons=True,
    )
    assert result.status == "completed"
    assert result.episode_id == item.episode_id
    assert result.prediction_id == item.prediction_id
    assert any(lesson.kind == expected_kind for lesson in result.lessons)


def test_partial_with_specific_kind_does_not_add_horizon_mismatch() -> None:
    item = _miss_item(signals=["evidence_gap"], confidence=0.5, score="partial")
    kinds = infer_lesson_kinds(item)
    assert kinds == ["evidence_gap"]
    assert "horizon_mismatch" not in kinds


def test_deterministic_lessons_use_source_claim_ref() -> None:
    item = ResolvedForecastInput(
        episode_id="ep-multi",
        prediction_id="pred-multi",
        claims=[
            ResolvedClaimOutcome(
                claim_id="hit-claim",
                claim_type="direction",
                score="hit",
                confidence=0.6,
                predicted={"direction": "up"},
                actual={"direction": "up"},
            ),
            ResolvedClaimOutcome(
                claim_id="miss-claim",
                claim_type="direction",
                score="miss",
                confidence=0.9,
                predicted={"direction": "up"},
                actual={"direction": "down"},
                signals=["overconfidence"],
            ),
        ],
    )
    lessons = build_deterministic_lessons(item)
    assert lessons
    assert all(lesson.claim_ref == "miss-claim" for lesson in lessons)
    assert any(lesson.kind == "overconfidence" for lesson in lessons)


def test_postmortem_misses_generate_lessons_without_user_trigger() -> None:
    item = _miss_item(signals=["evidence_gap"], confidence=0.7)
    result = reflect_resolved_forecast(
        item,
        config=_config(),
        llm_complete=None,
    )
    assert result.lessons
    assert result.episode_id == "ep-1"
    assert all(lesson.kind in LESSON_KINDS for lesson in result.lessons)


def test_postmortem_batch_llm_budget_hard_cap() -> None:
    items = [_miss_item(episode_id=f"ep-{i}", prediction_id=f"pred-{i}", signals=["evidence_gap"]) for i in range(5)]
    calls: List[str] = []

    def _llm(system: str, user: str) -> str:
        calls.append(user)
        return json.dumps(
            {
                "lessons": [
                    {
                        "kind": "evidence_gap",
                        "severity": "high",
                        "claim_ref": "c1",
                        "remedy": "Need volume confirmation.",
                        "source_step": "postmortem",
                    }
                ]
            }
        )

    batch = run_postmortem_batch(
        items,
        config=_config(),
        llm_complete=_llm,
        budget=LlmCallBudget(total=2),
    )

    assert len(calls) == 2
    assert batch.llm_budget_total == 2
    assert batch.llm_budget_consumed == 2
    assert batch.llm_budget_remaining == 0
    assert batch.budget_skips >= 3

    completed = [r for r in batch.results if r.status == "completed"]
    skipped = [r for r in batch.results if r.status == "budget_skipped"]
    assert len(completed) == 2
    assert len(skipped) == 3
    for item in skipped:
        assert item.validation_status == BUDGET_SKIPPED
        assert item.skip_reason
        assert item.terminate_reason == "budget"
        # Episode linkage remains even when LLM is skipped.
        assert item.episode_id.startswith("ep-")
        assert item.prediction_id.startswith("pred-")


def test_postmortem_batch_uses_config_llm_budget() -> None:
    items = [_miss_item(episode_id=f"ep-{i}", prediction_id=f"pred-{i}", signals=["evidence_gap"]) for i in range(5)]
    calls: List[str] = []

    def _llm(system: str, user: str) -> str:
        calls.append(user)
        return json.dumps(
            {
                "lessons": [
                    {
                        "kind": "evidence_gap",
                        "severity": "high",
                        "claim_ref": "c1",
                        "remedy": "Need volume confirmation.",
                        "source_step": "postmortem",
                    }
                ]
            }
        )

    batch = run_postmortem_batch(
        items,
        config=_config(agent_reflection_llm_budget=99, agent_postmortem_llm_budget=2),
        llm_complete=_llm,
    )

    assert len(calls) == 2
    assert batch.llm_budget_total == 2
    assert batch.llm_budget_consumed == 2
    assert batch.budget_skips >= 3


def test_postmortem_llm_error_keeps_deterministic_lessons() -> None:
    item = _miss_item(signals=["evidence_gap"], confidence=0.7)

    invalid = reflect_resolved_forecast(
        item,
        config=_config(),
        llm_complete=lambda _s, _u: "not-json",
        budget=LlmCallBudget(total=1),
    )
    assert invalid.status == "error"
    assert any(lesson.kind == "evidence_gap" for lesson in invalid.lessons)

    def _boom(_system: str, _user: str) -> str:
        raise RuntimeError("transport")

    failed = reflect_resolved_forecast(
        item,
        config=_config(),
        llm_complete=_boom,
        budget=LlmCallBudget(total=1),
    )
    assert failed.status == "error"
    assert any(lesson.kind == "evidence_gap" for lesson in failed.lessons)


def test_postmortem_skips_clean_hits_under_cost_policy() -> None:
    item = ResolvedForecastInput(
        episode_id="ep-hit",
        prediction_id="pred-hit",
        claims=[
            ResolvedClaimOutcome(
                claim_id="c1",
                claim_type="direction",
                score="hit",
                confidence=0.7,
                predicted={"direction": "up"},
                actual={"direction": "up"},
            )
        ],
    )
    result = reflect_resolved_forecast(
        item,
        config=_config(),
        llm_complete=lambda s, u: (_ for _ in ()).throw(AssertionError("no LLM")),
        cost_mode="tight",
    )
    assert result.status == "skipped_hit"
    assert result.lessons == []
    assert result.llm_budget_consumed == 0


def test_postmortem_data_unavailable_never_fabricates_hit() -> None:
    item = ResolvedForecastInput(
        episode_id="ep-na",
        prediction_id="pred-na",
        claims=[
            ResolvedClaimOutcome(
                claim_id="c1",
                claim_type="direction",
                score="data_unavailable",
                predicted={"direction": "up"},
                actual={},
            )
        ],
    )
    result = reflect_resolved_forecast(
        item,
        config=_config(),
        llm_complete=lambda s, u: json.dumps({"lessons": []}),
    )
    assert result.status == "data_unavailable"
    assert result.lessons == []
    assert result.validation_status == "data_unavailable"
    # Must not score as a hit when actuals are unavailable.
    assert result.status != "completed" or not result.lessons


def test_postmortem_does_not_mutate_soul_or_toolsurface() -> None:
    surface = _tool_surface()
    denied = ["secret_tool"]
    denials = ["capability_denied"]
    soul_before = snapshot_soul_identity()
    tools_before = snapshot_tool_surface_denials(surface, denied_tools=denied, denial_codes=denials)
    public_before = list(surface.list_tools(format="public"))

    item = _miss_item(signals=["overconfidence"], confidence=0.99)
    result = reflect_resolved_forecast(
        item,
        config=_config(),
        llm_complete=lambda s, u: json.dumps(
            {
                "lessons": [
                    {
                        "kind": "overconfidence",
                        "severity": "high",
                        "claim_ref": "c1",
                        "remedy": "Require confirmation.",
                        "source_step": "postmortem",
                    }
                ],
                "strategy_note": "Not a Soul edit",
            }
        ),
        budget=LlmCallBudget(total=1),
        tool_surface=surface,
        denied_tools=denied,
        denial_codes=denials,
    )

    assert result.status == "completed"
    assert result.lessons[0].kind == "overconfidence"
    assert soul_before == snapshot_soul_identity()
    assert tools_before == snapshot_tool_surface_denials(surface, denied_tools=denied, denial_codes=denials)
    assert surface.list_tools(format="public") == public_before
    assert AGENT_SOUL_HASH.startswith("sha256:")


def test_postmortem_episode_bundle_traceability() -> None:
    items = [
        _miss_item(episode_id="ep-a", prediction_id="pred-a", signals=["regime_shift"]),
        _miss_item(episode_id="ep-b", prediction_id="pred-b", signals=["tool_failure"]),
    ]
    batch = run_postmortem_batch(
        items,
        config=_config(),
        llm_complete=None,
    )
    assert len(batch.bundles) == 2
    by_episode = {bundle.episode_id: bundle for bundle in batch.bundles}
    assert by_episode["ep-a"].prediction_id == "pred-a"
    assert by_episode["ep-a"].result.lessons
    assert by_episode["ep-b"].result.lessons[0].kind == "tool_failure"


def test_postmortem_disabled() -> None:
    assert is_postmortem_enabled(_config(agent_postmortem_enabled=False)) is False
    result = reflect_resolved_forecast(
        _miss_item(),
        config=_config(agent_postmortem_enabled=False),
    )
    assert result.status == "disabled"
    assert result.lessons == []


def test_config_registry_fields_present() -> None:
    for key in (
        "AGENT_REFLECTION_ENABLED",
        "AGENT_REFLECTION_LLM_BUDGET",
        "AGENT_REFLECTION_MAX_REVISE",
        "AGENT_POSTMORTEM_ENABLED",
        "AGENT_POSTMORTEM_LLM_BUDGET",
        "AGENT_POSTMORTEM_SKIP_CLEAN_HITS",
    ):
        field = get_field_definition(key)
        assert field is not None, key
        assert field["category"] == "agent"


# ---------------------------------------------------------------------------
# Run-account mode budget (#1121 Task 2)
# ---------------------------------------------------------------------------


def test_reflection_skips_when_run_account_already_at_max_llm_turns() -> None:
    account = _run_account(max_llm_turns=3, llm_turns=3)
    ctx = _ctx(episode_id="ep-run-cap", mode_budget_account=account)
    soul_before = snapshot_soul_identity()
    hash_before = AGENT_SOUL_HASH

    result = run_reflection_loop(
        ctx,
        config=_config(),
        llm_complete=_boom_llm,
        budget=LlmCallBudget(total=1),
    )

    assert result.status == "budget_skipped"
    assert result.terminate_reason == "budget"
    assert result.validation_status == BUDGET_SKIPPED
    assert result.skip_reason
    assert ctx.meta[REFLECTION_META_KEY]["status"] == "budget_skipped"
    assert account.llm_turns == 3
    snap = account.snapshot()
    assert snap["used"]["llm_turns"] <= snap["limits"]["max_llm_turns"]
    assert snapshot_soul_identity() == soul_before
    assert AGENT_SOUL_HASH == hash_before


def test_reflection_skips_when_run_account_already_breached() -> None:
    account = _run_account(max_llm_turns=2, llm_turns=2)
    breach = account.record_llm_turn()
    assert breach is not None
    assert breach.reason == "budget_turns"
    turns_after_breach = account.llm_turns
    ctx = _ctx(episode_id="ep-run-breach", mode_budget_account=account)
    soul_before = snapshot_soul_identity()

    result = run_reflection_loop(
        ctx,
        config=_config(),
        llm_complete=_boom_llm,
        budget=LlmCallBudget(total=1),
    )

    assert result.status == "budget_skipped"
    assert result.terminate_reason == "budget"
    assert result.validation_status == BUDGET_SKIPPED
    assert result.skip_reason
    assert account.llm_turns == turns_after_breach
    assert account.breach is not None
    assert account.breach.reason == "budget_turns"
    snap = account.snapshot()
    assert snap["breach"]["reason"] == "budget_turns"
    assert snapshot_soul_identity() == soul_before
    assert AGENT_SOUL_HASH == soul_before.content_hash


def test_reflection_records_last_remaining_run_account_turn() -> None:
    """End-of-run reflection does not reserve a Decision turn."""
    account = _run_account(max_llm_turns=2, llm_turns=1)
    ctx = _ctx(episode_id="ep-run-last", mode_budget_account=account)
    calls: List[str] = []

    def _llm(system: str, user: str) -> str:
        calls.append(system)
        return json.dumps({"lessons": [], "revised": False})

    result = run_reflection_loop(
        ctx,
        config=_config(),
        llm_complete=_llm,
        budget=LlmCallBudget(total=1),
    )

    assert result.status == "completed"
    assert len(calls) == 1
    assert account.llm_turns == 2
    assert account.breach is None


def test_reflection_records_one_run_account_turn_when_room_remains() -> None:
    account = _run_account(max_llm_turns=4, llm_turns=1)
    ctx = _ctx(episode_id="ep-run-room", mode_budget_account=account)
    calls: List[str] = []

    def _llm(system: str, user: str) -> str:
        calls.append(system)
        return json.dumps({"lessons": [], "revised": False})

    result = run_reflection_loop(
        ctx,
        config=_config(),
        llm_complete=_llm,
        budget=LlmCallBudget(total=1),
    )

    assert result.status == "completed"
    assert len(calls) == 1
    assert account.llm_turns == 2
    assert account.breach is None


def test_postmortem_skips_llm_when_run_account_at_max_llm_turns() -> None:
    account = _run_account(max_llm_turns=2, llm_turns=2)
    ctx = _ctx(mode_budget_account=account)
    soul_before = snapshot_soul_identity()

    result = reflect_resolved_forecast(
        _miss_item(signals=["evidence_gap"]),
        config=_config(),
        llm_complete=_boom_llm,
        budget=LlmCallBudget(total=1),
        ctx=ctx,
    )

    assert result.status == "budget_skipped"
    assert result.terminate_reason == "budget"
    assert result.validation_status == BUDGET_SKIPPED
    assert result.skip_reason
    assert account.llm_turns == 2
    assert any(lesson.kind == "evidence_gap" for lesson in result.lessons)
    assert snapshot_soul_identity() == soul_before
    assert AGENT_SOUL_HASH == soul_before.content_hash


def test_postmortem_batch_records_run_account_turns_then_skips() -> None:
    account = _run_account(max_llm_turns=1, llm_turns=0)
    ctx = _ctx(mode_budget_account=account)
    items = [
        _miss_item(episode_id=f"ep-{i}", prediction_id=f"pred-{i}", signals=["evidence_gap"])
        for i in range(3)
    ]
    calls: List[str] = []

    def _llm(system: str, user: str) -> str:
        calls.append(user)
        return json.dumps(
            {
                "lessons": [
                    {
                        "kind": "evidence_gap",
                        "severity": "high",
                        "claim_ref": "c1",
                        "remedy": "Need volume confirmation.",
                        "source_step": "postmortem",
                    }
                ]
            }
        )

    batch = run_postmortem_batch(
        items,
        config=_config(),
        llm_complete=_llm,
        budget=LlmCallBudget(total=8),
        ctx=ctx,
    )

    assert len(calls) == 1
    assert account.llm_turns == 1
    assert account.breach is None
    completed = [row for row in batch.results if row.status == "completed"]
    skipped = [row for row in batch.results if row.status == "budget_skipped"]
    assert len(completed) == 1
    assert len(skipped) == 2
    for row in skipped:
        assert row.validation_status == BUDGET_SKIPPED
        assert row.skip_reason
        assert row.terminate_reason == "budget"
