# -*- coding: utf-8 -*-
"""AR-01 agent-runtime characterization compatibility gate.

Two layers of protection for any future runtime replacement (e.g. an
external-engine adapter behind the same factory entrypoints):

1. Replay characterization: every fixture in
   ``tests/fixtures/agent_runtime/manifest.json`` is replayed through the
   real production runtime (factory, executor/orchestrator, runner, tool
   registry, parsers, risk override) with a strict transcript-serving LLM
   adapter, and the observation must equal the frozen ``expected`` block.
   Re-freeze intentionally changed behaviour with
   ``python -m tests.agent_runtime_replay record``.

2. Factory contract freezes: entrypoint-level invariants that fixtures
   cannot express (caching, config non-mutation, legacy alias, stage
   input contracts).
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.agent import factory as factory_module
from src.agent import llm_adapter as llm_adapter_module
from src.config import AGENT_MAX_STEPS_DEFAULT
from tests.agent_runtime_replay import (
    BASE_CONFIG_FIELDS,
    FIXTURES_DIR,
    ReplayLLMAdapter,
    build_replay_tool_registry,
    load_case,
    load_manifest,
    observe_case,
)

MANIFEST = load_manifest()
CASE_ENTRIES = MANIFEST["cases"]
CASE_IDS = [entry["id"] for entry in CASE_ENTRIES]


# ---------------------------------------------------------------------------
# Manifest integrity
# ---------------------------------------------------------------------------

def test_manifest_ids_unique_and_files_exist():
    assert len(CASE_IDS) == len(set(CASE_IDS))
    for entry in CASE_ENTRIES:
        path = FIXTURES_DIR / entry["file"]
        assert path.is_file(), f"missing fixture file: {entry['file']}"
        case = load_case(entry["file"])
        assert case["id"] == entry["id"]
        assert case["expected"], f"fixture {entry['id']} has no frozen expected block"
        assert case["transcript"], f"fixture {entry['id']} has an empty transcript"
        assert "task" in case["input"] or "message" in case["input"]


def test_manifest_has_no_orphan_fixture_files():
    listed = {entry["file"] for entry in CASE_ENTRIES}
    on_disk = {
        str(path.relative_to(FIXTURES_DIR)).replace("\\", "/")
        for path in FIXTURES_DIR.rglob("*.json")
        if path.name != "manifest.json"
    }
    assert on_disk == listed


def test_manifest_covers_plan_matrix():
    """Freeze the AR-01 dataset shape: 24 financial + 12 contract cases."""
    financial = [entry for entry in CASE_ENTRIES if entry["kind"] == "financial"]
    contract = [entry for entry in CASE_ENTRIES if entry["kind"] == "contract"]
    assert len(financial) == 24
    assert len(contract) == 12

    markets = {}
    for entry in financial:
        markets[entry["market"]] = markets.get(entry["market"], 0) + 1
    assert markets == {"A": 8, "HK": 8, "US": 8}

    financial_modes = {entry["mode"] for entry in financial}
    assert {"single_run", "single_chat", "quick", "standard", "full", "specialist"} <= financial_modes
    assert any(entry["profile"] == "partial" for entry in financial)

    profiles = {}
    for entry in contract:
        profiles[entry["profile"]] = profiles.get(entry["profile"], 0) + 1
    assert profiles == {
        "modelref": 2,
        "fallback": 2,
        "toolscope": 2,
        "timeout": 2,
        "cancelrace": 2,
        "malformed": 2,
    }

    assert MANIFEST["notes"]["provider_trace_differences"].strip()
    assert all(entry["license"] == "synthetic-fixture" for entry in CASE_ENTRIES)


# ---------------------------------------------------------------------------
# Replay characterization
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("entry", CASE_ENTRIES, ids=CASE_IDS)
def test_replay_case_matches_frozen_expected(entry):
    case = load_case(entry["file"])
    observed = observe_case(case)
    assert observed == case["expected"], (
        f"Runtime behaviour drifted for case '{entry['id']}'. If the change is "
        "intentional, re-freeze with: python -m tests.agent_runtime_replay record"
    )


# ---------------------------------------------------------------------------
# Factory contract freezes
# ---------------------------------------------------------------------------

_ROUTING_FIELDS = (
    "agent_litellm_model",
    "litellm_model",
    "litellm_fallback_models",
    "llm_model_list",
)


def _build_with_replay_doubles(config):
    adapter = ReplayLLMAdapter([], config=config)
    registry = build_replay_tool_registry()
    with patch.object(
        llm_adapter_module, "LLMToolAdapter", new=lambda cfg: adapter
    ), patch.object(factory_module, "get_tool_registry", new=lambda: registry):
        return factory_module.build_agent_executor(config), registry


def test_factory_does_not_mutate_model_routing_fields():
    config = SimpleNamespace(**BASE_CONFIG_FIELDS)
    snapshot = {name: getattr(config, name) for name in _ROUTING_FIELDS}
    _build_with_replay_doubles(config)
    for name in _ROUTING_FIELDS:
        assert getattr(config, name) == snapshot[name], f"factory mutated {name}"


def test_factory_invalid_numeric_config_falls_back_without_mutation():
    fields = dict(BASE_CONFIG_FIELDS)
    fields["agent_max_steps"] = "not-a-number"
    fields["agent_orchestrator_timeout_s"] = object()
    config = SimpleNamespace(**fields)
    raw_timeout = config.agent_orchestrator_timeout_s

    executor, _registry = _build_with_replay_doubles(config)

    assert executor.max_steps == AGENT_MAX_STEPS_DEFAULT
    assert executor.timeout_seconds == 0
    # Coercion must be side-effect free: source config keeps the raw values.
    assert config.agent_max_steps == "not-a-number"
    assert config.agent_orchestrator_timeout_s is raw_timeout


def test_tool_registry_is_cached_and_shared_across_builds():
    original = factory_module._TOOL_REGISTRY
    try:
        factory_module._TOOL_REGISTRY = None
        first = factory_module.get_tool_registry()
        second = factory_module.get_tool_registry()
        assert first is second

        config = SimpleNamespace(**BASE_CONFIG_FIELDS)
        adapter = ReplayLLMAdapter([], config=config)
        with patch.object(llm_adapter_module, "LLMToolAdapter", new=lambda cfg: adapter):
            executor_a = factory_module.build_agent_executor(config)
            executor_b = factory_module.build_agent_executor(config)
        assert executor_a.tool_registry is first
        assert executor_b.tool_registry is first
    finally:
        factory_module._TOOL_REGISTRY = original


def test_skill_manager_prototype_is_cloned_per_request_and_invalidated_on_dir_change(tmp_path):
    original_prototype = factory_module._SKILL_MANAGER_PROTOTYPE
    original_dir = factory_module._SKILL_MANAGER_CUSTOM_DIR
    try:
        factory_module._SKILL_MANAGER_PROTOTYPE = None
        factory_module._SKILL_MANAGER_CUSTOM_DIR = factory_module._SENTINEL

        config = SimpleNamespace(agent_skill_dir=None)
        clone_a = factory_module.get_skill_manager(config)
        prototype_a = factory_module._SKILL_MANAGER_PROTOTYPE
        clone_b = factory_module.get_skill_manager(config)

        assert prototype_a is not None
        # Per-request clones: activation state cannot bleed between requests.
        assert clone_a is not clone_b
        assert clone_a is not prototype_a
        # Same directory: prototype is reused, not rebuilt.
        assert factory_module._SKILL_MANAGER_PROTOTYPE is prototype_a

        config_changed = SimpleNamespace(agent_skill_dir=str(tmp_path))
        factory_module.get_skill_manager(config_changed)
        assert factory_module._SKILL_MANAGER_PROTOTYPE is not prototype_a
        assert factory_module._SKILL_MANAGER_CUSTOM_DIR == str(tmp_path)
    finally:
        factory_module._SKILL_MANAGER_PROTOTYPE = original_prototype
        factory_module._SKILL_MANAGER_CUSTOM_DIR = original_dir


def test_build_executor_legacy_alias_is_preserved():
    assert factory_module.build_executor is factory_module.build_agent_executor


def test_risk_agent_input_contract_is_intel_only():
    """AR contract: equivalence-migration Risk input stays Risk(Intel).

    The RiskAgent user message may embed the intel opinion but must not embed
    the technical opinion; feeding Technical into Risk is reserved for a
    versioned AR-07 enhancement.
    """
    from src.agent.agents.risk_agent import RiskAgent
    from src.agent.protocols import AgentContext

    agent = RiskAgent(
        tool_registry=build_replay_tool_registry(),
        llm_adapter=MagicMock(name="unused_adapter"),
    )
    ctx = AgentContext(stock_code="600519", stock_name="贵州茅台")
    ctx.set_data("technical_opinion", {"marker": "TECHNICAL_OPINION_SENTINEL"})
    ctx.set_data("intel_opinion", {"marker": "INTEL_OPINION_SENTINEL"})

    message = agent.build_user_message(ctx)

    assert "INTEL_OPINION_SENTINEL" in message
    assert "TECHNICAL_OPINION_SENTINEL" not in message
