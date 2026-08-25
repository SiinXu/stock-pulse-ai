# -*- coding: utf-8 -*-
"""#1123 Slice A: catalog-description skill retrieval on the SkillRouter seam."""

from __future__ import annotations

import inspect
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.agent.evolution.adapters import prefer_route, rank_tools
from src.agent.evolution.guards import snapshot_soul_identity, snapshot_tool_surface_denials
from src.agent.protocols import AgentContext
from src.agent.skills.base import Skill, SkillManager
from src.agent.skills.defaults import get_default_router_skill_ids
from src.agent.skills.retrieval import (
    RETRIEVED_SKILLS_META_KEY,
    SKILL_RETRIEVAL_K_HARD_CAP,
    load_optional_skill_performance_prior,
    resolve_skill_retrieval_k,
    retrieve_skills,
)
from src.agent.skills.router import SkillRouter
from src.agent.soul import AGENT_SOUL_HASH, AGENT_SOUL_MARKER, compose_agent_soul_prompt
from src.agent.tools.execution import ToolAccessContext
from src.agent.tools.registry import ToolDefinition, ToolParameter, ToolPolicy, ToolRegistry
from src.agent.tools.surface import ToolSurface
from src.config_parts.parsers import parse_env_int


def _skill(
    name: str,
    *,
    display_name: str = "",
    description: str = "",
    instructions: str = "instructions",
    aliases: list[str] | None = None,
    default_router: bool = False,
    category: str = "trend",
    market_scopes: list[str] | None = None,
) -> Skill:
    return Skill(
        name=name,
        display_name=display_name or name,
        description=description or name,
        instructions=instructions,
        aliases=list(aliases or []),
        default_router=default_router,
        category=category,
        enabled=False,
        market_scopes=list(market_scopes or []),
    )


def _catalog_manager() -> SkillManager:
    manager = SkillManager()
    manager.register(
        _skill(
            "box_oscillation",
            display_name="箱体震荡",
            description="识别价格箱体区间，在箱底买入、箱顶减仓，适用于横盘震荡行情。",
            aliases=["箱体", "箱体震荡"],
            category="framework",
        )
    )
    manager.register(
        _skill(
            "range_box",
            display_name="区间箱体",
            description="箱体震荡区间内高抛低吸。",
            aliases=["箱体"],
            category="framework",
        )
    )
    manager.register(
        _skill(
            "bull_trend",
            display_name="默认多头趋势",
            description="默认个股分析优先策略，识别多头排列、趋势延续与回踩低吸机会。",
            default_router=True,
        )
    )
    manager.register(
        _skill(
            "shrink_pullback",
            display_name="缩量回踩",
            description="缩量回踩均线支撑后低吸。",
            default_router=True,
        )
    )
    manager.register(
        _skill(
            "unrelated_growth",
            display_name="成长质量",
            description="长期成长与质量因子，与箱体无关。",
        )
    )
    return manager


def _auto_config(k: object) -> SimpleNamespace:
    return SimpleNamespace(
        agent_skill_routing="auto",
        agent_skill_retrieval_k=k,
        agent_memory_enabled=False,
    )


def test_k1_versus_k2_changes_retrieved_set() -> None:
    catalog = _catalog_manager().list_skills()
    query = "箱体震荡"
    k1 = retrieve_skills(query, catalog, k=1)
    k2 = retrieve_skills(query, catalog, k=2)
    assert k1 == ["box_oscillation"]
    assert len(k2) == 2
    assert k2[0] == "box_oscillation"
    assert k2 != k1
    assert "range_box" in k2


def test_cjk_description_ranks_box_oscillation_above_bull_trend() -> None:
    catalog = _catalog_manager().list_skills()
    ranked = retrieve_skills("箱体震荡", catalog, k=3)
    assert "box_oscillation" in ranked
    assert ranked.index("box_oscillation") < ranked.index("bull_trend") if "bull_trend" in ranked else True
    assert ranked[0] == "box_oscillation"


def test_empty_query_and_all_zero_match_return_empty_not_full_catalog() -> None:
    catalog = _catalog_manager().list_skills()
    assert retrieve_skills("", catalog, k=2) == []
    assert retrieve_skills("   ", catalog, k=2) == []
    assert retrieve_skills("箱体震荡", [], k=2) == []
    assert retrieve_skills("箱体震荡", None, k=2) == []
    assert retrieve_skills("箱体震荡", catalog, k=0) == []
    assert retrieve_skills("箱体震荡", catalog, k=True) == []
    assert retrieve_skills("箱体震荡", catalog, k=2.0) == []
    assert retrieve_skills("箱体震荡", catalog, k="2") == []


def test_injected_all_zero_cosine_scores_return_empty_not_full_catalog(monkeypatch) -> None:
    catalog = _catalog_manager().list_skills()

    class _ZeroIndex:
        def add_many(self, documents):
            self._documents = list(documents)

        def query(self, query_text, top_k):
            del query_text
            return [(doc, 0.0) for doc in self._documents[:top_k]]

    monkeypatch.setattr("src.agent.skills.retrieval.HashingVectorIndex", _ZeroIndex)
    assert retrieve_skills("箱体震荡", catalog, k=2) == []


def test_skill_router_k1_versus_k2_on_production_select_skills() -> None:
    manager = _catalog_manager()
    ctx_one = AgentContext(query="箱体震荡")
    ctx_two = AgentContext(query="箱体震荡")
    one = SkillRouter(skill_manager=manager, config=_auto_config(1)).select_skills(ctx_one)
    two = SkillRouter(skill_manager=manager, config=_auto_config(2)).select_skills(ctx_two)
    assert one == ["box_oscillation"]
    assert two[0] == "box_oscillation"
    assert len(two) == 2
    assert one != two
    assert ctx_one.meta[RETRIEVED_SKILLS_META_KEY] == one
    assert ctx_two.meta[RETRIEVED_SKILLS_META_KEY] == two


def test_explicit_skills_requested_not_replaced_or_labeled_retrieved() -> None:
    manager = _catalog_manager()
    ctx = AgentContext(query="箱体震荡")
    ctx.meta["skills_requested"] = ["shrink_pullback"]
    selected = SkillRouter(
        skill_manager=manager,
        config=_auto_config(2),
    ).select_skills(ctx)
    assert selected == ["shrink_pullback"]
    assert RETRIEVED_SKILLS_META_KEY not in ctx.meta


def test_manual_agent_skills_not_replaced_or_labeled_retrieved() -> None:
    manager = _catalog_manager()
    ctx = AgentContext(query="箱体震荡")
    config = SimpleNamespace(
        agent_skill_routing="manual",
        agent_skill_retrieval_k=2,
        agent_skills=["unrelated_growth"],
        agent_memory_enabled=False,
    )
    selected = SkillRouter(skill_manager=manager, config=config).select_skills(ctx)
    assert selected == ["unrelated_growth"]
    assert RETRIEVED_SKILLS_META_KEY not in ctx.meta


def test_disabled_k_keeps_default_router_behavior() -> None:
    manager = _catalog_manager()
    ctx = AgentContext(query="箱体震荡")
    selected = SkillRouter(
        skill_manager=manager,
        config=_auto_config(0),
    ).select_skills(ctx)
    assert selected == get_default_router_skill_ids(manager.list_skills())
    assert RETRIEVED_SKILLS_META_KEY not in ctx.meta
    assert resolve_skill_retrieval_k(_auto_config(None)) == 0
    assert resolve_skill_retrieval_k(SimpleNamespace()) == 0


def test_empty_match_falls_back_to_default_router_set_not_full_catalog() -> None:
    manager = _catalog_manager()
    ctx = AgentContext(query="")
    selected = SkillRouter(
        skill_manager=manager,
        config=_auto_config(2),
    ).select_skills(ctx)
    expected = get_default_router_skill_ids(manager.list_skills(), max_count=2)
    assert selected == expected
    assert set(selected) <= {"bull_trend", "shrink_pullback"}
    assert "unrelated_growth" not in selected
    assert "box_oscillation" not in selected
    assert ctx.meta[RETRIEVED_SKILLS_META_KEY] == selected


def test_strict_k_validation_and_hard_cap() -> None:
    assert resolve_skill_retrieval_k(_auto_config(2)) == 2
    assert resolve_skill_retrieval_k(_auto_config(0)) == 0
    assert resolve_skill_retrieval_k(_auto_config(-1)) == 0
    assert resolve_skill_retrieval_k(_auto_config(99)) == SKILL_RETRIEVAL_K_HARD_CAP
    assert resolve_skill_retrieval_k(_auto_config(True)) == 0
    assert resolve_skill_retrieval_k(_auto_config(False)) == 0
    assert resolve_skill_retrieval_k(_auto_config(2.0)) == 0
    assert resolve_skill_retrieval_k(_auto_config("2")) == 0
    assert parse_env_int(
        "2",
        0,
        field_name="AGENT_SKILL_RETRIEVAL_K",
        minimum=0,
        maximum=SKILL_RETRIEVAL_K_HARD_CAP,
    ) == 2
    assert parse_env_int(
        "99",
        0,
        field_name="AGENT_SKILL_RETRIEVAL_K",
        minimum=0,
        maximum=SKILL_RETRIEVAL_K_HARD_CAP,
    ) == SKILL_RETRIEVAL_K_HARD_CAP
    assert parse_env_int(
        "nope",
        0,
        field_name="AGENT_SKILL_RETRIEVAL_K",
        minimum=0,
        maximum=SKILL_RETRIEVAL_K_HARD_CAP,
    ) == 0
    assert parse_env_int(
        "-3",
        0,
        field_name="AGENT_SKILL_RETRIEVAL_K",
        minimum=0,
        maximum=SKILL_RETRIEVAL_K_HARD_CAP,
    ) == 0


def test_config_default_is_disabled() -> None:
    from src.config import Config

    assert Config().agent_skill_retrieval_k == 0


def test_optional_prior_requires_injected_memory_and_finite_samples() -> None:
    catalog = _catalog_manager().list_skills()
    assert load_optional_skill_performance_prior(catalog) == {}
    assert load_optional_skill_performance_prior(catalog, memory=None) == {}

    class _Memory:
        enabled = True

        def get_skill_performance(self, skill_id: str):
            if skill_id == "box_oscillation":
                return {"sufficient_samples": True, "win_rate": 0.9}
            if skill_id == "range_box":
                return {"sufficient_samples": True, "win_rate": float("nan")}
            if skill_id == "bull_trend":
                return {"sufficient_samples": True, "win_rate": True}
            if skill_id == "shrink_pullback":
                return {"sufficient_samples": False, "win_rate": 0.99}
            return {"available": False}

    prior = load_optional_skill_performance_prior(catalog, memory=_Memory())
    assert prior == {"box_oscillation": pytest.approx(1.4)}
    ranked = retrieve_skills(
        "箱体震荡",
        catalog,
        k=2,
        performance_prior={"box_oscillation": 1.4, "range_box": math.inf},
    )
    assert ranked[0] == "box_oscillation"


def test_skill_router_does_not_construct_memory_without_injection() -> None:
    manager = _catalog_manager()
    source = inspect.getsource(SkillRouter._select_retrieved_skills)
    assert "AgentMemory(" not in source
    selected = SkillRouter(
        skill_manager=manager,
        config=_auto_config(1),
    ).select_skills(AgentContext(query="箱体震荡"))
    assert selected == ["box_oscillation"]


def test_instructions_use_retrieved_subset_not_all() -> None:
    manager = _catalog_manager()
    manager.activate(["all"])
    dumped_all = manager.get_skill_instructions()
    assert "成长质量" in dumped_all
    ctx = AgentContext(query="箱体震荡")
    selected = SkillRouter(
        skill_manager=manager,
        config=_auto_config(1),
    ).select_skills(ctx)
    subset = manager.get_skill_instructions(selected)
    assert "箱体震荡" in subset
    assert "成长质量" not in subset
    assert dumped_all != subset


def test_factory_keeps_activation_dump_without_empty_context_retrieval(monkeypatch) -> None:
    from src.agent.runtime_assembly import resolve_skill_prompt_state

    manager = _catalog_manager()
    monkeypatch.setattr(
        "src.agent.runtime_assembly.get_skill_manager",
        lambda config=None: manager,
    )
    enabled = SimpleNamespace(
        agent_skills=["all"],
        agent_skill_dir=None,
        agent_skill_routing="auto",
        agent_skill_retrieval_k=2,
        agent_memory_enabled=False,
    )
    state = resolve_skill_prompt_state(enabled)
    assert "成长质量" in state.skill_instructions
    assert "箱体震荡" in state.skill_instructions


def test_retrieval_respects_select_skills_max_count() -> None:
    manager = _catalog_manager()
    router = SkillRouter(skill_manager=manager, config=_auto_config(8))
    one = router.select_skills(AgentContext(query="箱体震荡"), max_count=1)
    two = router.select_skills(AgentContext(query="箱体震荡"), max_count=2)
    none = router.select_skills(AgentContext(query="箱体震荡"), max_count=0)
    assert one == ["box_oscillation"]
    assert len(two) == 2
    assert two[0] == "box_oscillation"
    assert none == []


def test_context_skills_requested_and_manual_all_stay_on_skill_router() -> None:
    manager = _catalog_manager()
    exact_ctx = AgentContext(query="箱体震荡")
    exact_ctx.meta["skills_requested"] = ["shrink_pullback", "bull_trend"]
    exact = SkillRouter(skill_manager=manager, config=_auto_config(2)).select_skills(exact_ctx)
    assert exact == ["shrink_pullback", "bull_trend"]
    assert RETRIEVED_SKILLS_META_KEY not in exact_ctx.meta

    all_ctx = AgentContext(query="箱体震荡")
    all_ctx.meta["skills_requested"] = ["all"]
    selected_all = SkillRouter(
        skill_manager=manager,
        config=_auto_config(2),
    ).select_skills(all_ctx)
    assert selected_all == ["all"]
    assert RETRIEVED_SKILLS_META_KEY not in all_ctx.meta

    manual_ctx = AgentContext(query="箱体震荡")
    manual = SkillRouter(
        skill_manager=manager,
        config=SimpleNamespace(
            agent_skill_routing="manual",
            agent_skill_retrieval_k=2,
            agent_skills=["all"],
            agent_memory_enabled=False,
        ),
    ).select_skills(manual_ctx)
    assert manual == get_default_router_skill_ids(manager.list_skills())
    assert RETRIEVED_SKILLS_META_KEY not in manual_ctx.meta


def test_explicit_selection_flag_skips_router_retrieval() -> None:
    manager = _catalog_manager()
    ctx = AgentContext(query="箱体震荡")
    selected = SkillRouter(
        skill_manager=manager,
        config=_auto_config(2),
        explicit_selection=True,
    ).select_skills(ctx)
    assert selected == get_default_router_skill_ids(manager.list_skills())
    assert RETRIEVED_SKILLS_META_KEY not in ctx.meta


def test_equal_scores_break_ties_by_skill_id() -> None:
    skills = [
        _skill("zeta_box", description="identical box range text"),
        _skill("alpha_box", description="identical box range text"),
    ]
    ranked = retrieve_skills("identical box range text", skills, k=2)
    assert ranked == ["alpha_box", "zeta_box"]


def test_native_implicit_uses_real_query_and_does_not_mutate_owner() -> None:
    from src.agent.skills.router import skill_instructions_for_native_task

    manager = _catalog_manager()
    manager.activate(["all"])
    owner = SimpleNamespace(
        skill_instructions="FACTORY_DUMP 成长质量",
        skill_manager=manager,
        config=_auto_config(1),
        explicit_skill_selection=False,
    )
    matched = skill_instructions_for_native_task(owner, "箱体震荡")
    empty = skill_instructions_for_native_task(owner, "")
    assert "箱体震荡" in matched
    assert "成长质量" not in matched
    assert "成长质量" not in empty
    assert owner.skill_instructions == "FACTORY_DUMP 成长质量"


def test_explicit_factory_dump_is_verbatim_identity_native_and_multi(monkeypatch) -> None:
    from unittest.mock import MagicMock

    from src.agent.orchestrator import AgentOrchestrator
    from src.agent.runtime_assembly import resolve_skill_prompt_state
    from src.agent.skills.router import (
        skill_instructions_for_native_task,
        skill_instructions_for_run,
    )

    manager = _catalog_manager()
    monkeypatch.setattr(
        "src.agent.runtime_assembly.get_skill_manager",
        lambda config=None: manager,
    )
    all_state = resolve_skill_prompt_state(
        SimpleNamespace(
            agent_skills=["all"],
            agent_skill_dir=None,
            agent_skill_routing="auto",
            agent_skill_retrieval_k=2,
            agent_memory_enabled=False,
        )
    )
    ids_state = resolve_skill_prompt_state(
        SimpleNamespace(
            agent_skills=["box_oscillation"],
            agent_skill_dir=None,
            agent_skill_routing="auto",
            agent_skill_retrieval_k=2,
            agent_memory_enabled=False,
        )
    )
    assert all_state.explicit_skill_selection is True
    assert ids_state.explicit_skill_selection is True
    dump_all = all_state.skill_instructions
    dump_ids = ids_state.skill_instructions
    assert "成长质量" in dump_all
    assert "箱体震荡" in dump_ids
    assert "成长质量" not in dump_ids

    ctx = AgentContext(query="箱体震荡")
    for dump, manager_for_owner in ((dump_all, all_state.skill_manager), (dump_ids, ids_state.skill_manager)):
        owner = SimpleNamespace(
            skill_instructions=dump,
            skill_manager=manager_for_owner,
            config=_auto_config(2),
            explicit_skill_selection=True,
        )
        assert skill_instructions_for_native_task(owner, "箱体震荡") is dump
        assert skill_instructions_for_run(owner, ctx) is dump
        orch = AgentOrchestrator(
            tool_registry=MagicMock(),
            llm_adapter=MagicMock(),
            skill_instructions=dump,
            skill_manager=manager_for_owner,
            config=_auto_config(2),
            mode="quick",
            explicit_skill_selection=True,
        )
        chain = orch._build_agent_chain(ctx)
        assert orch.skill_instructions is dump
        assert chain[0].skill_instructions is dump
        assert RETRIEVED_SKILLS_META_KEY not in ctx.meta


def test_context_request_beats_explicit_factory_selection_native_and_multi() -> None:
    from unittest.mock import MagicMock

    from src.agent.orchestrator import AgentOrchestrator
    from src.agent.skills.router import (
        skill_instructions_for_native_task,
        skill_instructions_for_run,
    )

    manager = _catalog_manager()
    manager.activate(["all"])
    factory_dump = manager.get_skill_instructions(["box_oscillation"])
    assert "箱体震荡" in factory_dump
    assert "缩量回踩" not in factory_dump
    owner = SimpleNamespace(
        skill_instructions=factory_dump,
        skill_manager=manager,
        config=_auto_config(2),
        explicit_skill_selection=True,
    )
    ctx = AgentContext(query="箱体震荡")
    ctx.meta["skills_requested"] = ["shrink_pullback"]
    rendered = skill_instructions_for_run(owner, ctx)
    native = skill_instructions_for_native_task(
        owner,
        "箱体震荡",
        {"skills_requested": ["shrink_pullback"]},
    )
    assert rendered is not factory_dump
    assert native is not factory_dump
    assert "缩量回踩" in rendered
    assert "缩量回踩" in native
    assert "箱体震荡" not in rendered
    assert RETRIEVED_SKILLS_META_KEY not in ctx.meta

    orch = AgentOrchestrator(
        tool_registry=MagicMock(),
        llm_adapter=MagicMock(),
        skill_instructions=factory_dump,
        skill_manager=manager,
        config=_auto_config(2),
        mode="quick",
        explicit_skill_selection=True,
    )
    chain = orch._build_agent_chain(ctx)
    assert orch.skill_instructions is factory_dump
    assert chain[0].skill_instructions is not factory_dump
    assert "缩量回踩" in chain[0].skill_instructions
    assert RETRIEVED_SKILLS_META_KEY not in ctx.meta


def test_retrieval_construction_failure_keeps_factory_dump(monkeypatch) -> None:
    from src.agent.skills.router import skill_instructions_for_native_task

    fallback = "PRE_RESOLVED_DUMP"
    owner = SimpleNamespace(
        skill_instructions=fallback,
        skill_manager=None,
        config=_auto_config(1),
        explicit_skill_selection=False,
    )

    def _boom(config=None):
        raise RuntimeError("catalog unavailable")

    monkeypatch.setattr("src.agent.factory.get_skill_manager", _boom)
    assert skill_instructions_for_native_task(owner, "箱体震荡") is fallback


def test_build_skill_agents_uses_active_set_when_factory_explicit() -> None:
    from unittest.mock import MagicMock

    from src.agent.orchestrator import AgentOrchestrator

    manager = _catalog_manager()
    manager.activate(["box_oscillation"])
    orch = AgentOrchestrator(
        tool_registry=MagicMock(),
        llm_adapter=MagicMock(),
        skill_instructions="FACTORY_BOX",
        skill_manager=manager,
        config=_auto_config(2),
        mode="specialist",
        explicit_skill_selection=True,
    )
    ctx = AgentContext(query="缩量回踩均线支撑")
    agents = orch._build_skill_agents(ctx)
    assert [agent.skill_id for agent in agents] == ["box_oscillation"]
    assert RETRIEVED_SKILLS_META_KEY not in ctx.meta


def test_build_skill_agents_all_uses_active_catalog_and_skill_cap() -> None:
    from unittest.mock import MagicMock

    from src.agent.orchestrator import AgentOrchestrator

    manager = _catalog_manager()
    manager.activate(["all"])
    orch = AgentOrchestrator(
        tool_registry=MagicMock(),
        llm_adapter=MagicMock(),
        skill_instructions="FACTORY_ALL",
        skill_manager=manager,
        config=_auto_config(2),
        mode="specialist",
        explicit_skill_selection=True,
    )
    ctx = AgentContext(query="箱体震荡")
    agents = orch._build_skill_agents(ctx)
    active_ids = [skill.name for skill in manager.list_active_skills()]
    assert [agent.skill_id for agent in agents] == active_ids[:3]
    assert len(agents) == 3
    assert RETRIEVED_SKILLS_META_KEY not in ctx.meta


def test_build_skill_agents_context_request_overrides_explicit_active() -> None:
    from unittest.mock import MagicMock

    from src.agent.orchestrator import AgentOrchestrator

    manager = _catalog_manager()
    manager.activate(["box_oscillation"])
    orch = AgentOrchestrator(
        tool_registry=MagicMock(),
        llm_adapter=MagicMock(),
        skill_instructions="FACTORY_BOX",
        skill_manager=manager,
        config=_auto_config(2),
        mode="specialist",
        explicit_skill_selection=True,
    )
    ctx = AgentContext(query="箱体震荡")
    ctx.meta["skills_requested"] = ["shrink_pullback"]
    agents = orch._build_skill_agents(ctx)
    assert [agent.skill_id for agent in agents] == ["shrink_pullback"]
    assert RETRIEVED_SKILLS_META_KEY not in ctx.meta


def test_pipeline_does_not_mutate_shared_skill_instructions() -> None:
    from unittest.mock import MagicMock

    from src.agent.orchestrator import AgentOrchestrator

    manager = _catalog_manager()
    manager.activate(["all"])
    orch = AgentOrchestrator(
        tool_registry=MagicMock(),
        llm_adapter=MagicMock(),
        skill_instructions="FACTORY_DUMP 成长质量",
        skill_manager=manager,
        config=_auto_config(1),
        mode="quick",
    )
    ctx = AgentContext(query="箱体震荡")
    chain = orch._build_agent_chain(ctx)
    assert orch.skill_instructions == "FACTORY_DUMP 成长质量"
    assert "箱体震荡" in chain[0].skill_instructions
    assert "成长质量" not in chain[0].skill_instructions
    import src.agent.orchestrator_parts.pipeline as pipeline_mod

    assert "self.skill_instructions =" not in inspect.getsource(pipeline_mod)


def test_concurrent_pipeline_runs_do_not_cross_contaminate_instructions() -> None:
    import threading
    from unittest.mock import MagicMock

    from src.agent.orchestrator import AgentOrchestrator

    manager = _catalog_manager()
    manager.activate(["all"])
    orch = AgentOrchestrator(
        tool_registry=MagicMock(),
        llm_adapter=MagicMock(),
        skill_instructions="FACTORY_DUMP 成长质量",
        skill_manager=manager,
        config=_auto_config(1),
        mode="quick",
    )
    results: dict[str, str] = {}

    def _run(label: str, query: str) -> None:
        chain = orch._build_agent_chain(AgentContext(query=query))
        results[label] = chain[0].skill_instructions

    first = threading.Thread(target=_run, args=("box", "箱体震荡"))
    second = threading.Thread(target=_run, args=("shrink", "缩量回踩均线支撑"))
    first.start()
    second.start()
    first.join()
    second.join()
    assert orch.skill_instructions == "FACTORY_DUMP 成长质量"
    assert "箱体震荡" in results["box"]
    assert "成长质量" not in results["box"]
    assert "成长质量" not in results["shrink"]
    assert results["box"] != results["shrink"] or "缩量回踩" in results["shrink"]


def test_soul_suffix_still_present_after_retrieved_instructions() -> None:
    manager = _catalog_manager()
    selected = SkillRouter(
        skill_manager=manager,
        config=_auto_config(1),
    ).select_skills(AgentContext(query="箱体震荡"))
    composed = compose_agent_soul_prompt(manager.get_skill_instructions(selected))
    assert AGENT_SOUL_MARKER in composed
    assert AGENT_SOUL_HASH


def test_no_new_tables_and_no_tool_rank_fork() -> None:
    import src.agent.skills.retrieval as retrieval_mod
    import src.agent.skills.router as router_mod

    retrieval_src = inspect.getsource(retrieval_mod)
    router_src = inspect.getsource(router_mod)
    for source in (retrieval_src, router_src):
        assert "CREATE TABLE" not in source
        assert "EvolutionEvent" not in source
        assert "rank_tools" not in source
        assert "prefer_route" not in source
        assert "AgentMemory(" not in source
    assert rank_tools(["quote", "echo"]) == ["quote", "echo"]
    assert prefer_route("standard") == "standard"


def test_denied_tool_still_not_invocable_after_skill_retrieval() -> None:
    calls: list[object] = []
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="echo",
            description="Echo a message.",
            parameters=[ToolParameter(name="message", type="string", description="Message")],
            handler=lambda message: calls.append(message) or {"message": message},
            category="data",
            policy=ToolPolicy.declared(
                read_only=True,
                side_effects=[],
                permissions=["analysis_context:read"],
            ),
        )
    )
    surface = ToolSurface(registry)
    denied = ("echo",)
    denials = ("permission_denied",)
    soul_before = snapshot_soul_identity()
    tools_before = snapshot_tool_surface_denials(
        surface,
        denied_tools=denied,
        denial_codes=denials,
    )
    retrieve_skills("箱体震荡", _catalog_manager().list_skills(), k=2)
    ranked = rank_tools(["echo", "quote"], denied_names=["echo"])
    result = surface.execute_tool(
        ranked[0],
        {"message": "should-not-run"},
        ToolAccessContext(),
    )
    assert result["error"]["code"] == "permission_denied"
    assert calls == []
    assert snapshot_soul_identity() == soul_before
    assert tools_before == snapshot_tool_surface_denials(
        surface,
        denied_tools=denied,
        denial_codes=denials,
    )
    assert AGENT_SOUL_HASH


def test_skill_router_has_no_raw_exception_object_log_violations() -> None:
    """Counterexample: unannotated skill_catalog taint flagged the scope-exclusion log."""
    from tests.test_exception_log_callsite_guard import find_exception_log_violations

    path = "src/agent/skills/router.py"
    source = Path(path).read_text(encoding="utf-8")
    assert find_exception_log_violations(path, source) == []


def test_retrieval_scope_exclusion_falls_back_to_default_router_set() -> None:
    manager = SkillManager()
    manager.register(
        _skill(
            "us_box",
            display_name="US box",
            description="箱体震荡",
            market_scopes=["us/equity"],
        )
    )
    manager.register(
        _skill("bull_trend", description="默认多头趋势", default_router=True)
    )
    ctx = AgentContext(query="箱体震荡", stock_code="600519")
    selected = SkillRouter(
        skill_manager=manager,
        config=_auto_config(2),
    ).select_skills(ctx)
    expected = get_default_router_skill_ids(manager.list_skills(), max_count=2)
    assert "us_box" not in selected
    assert selected == expected
    assert ctx.meta[RETRIEVED_SKILLS_META_KEY] == selected
