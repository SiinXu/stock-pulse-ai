# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Deterministic contract tests for the rules-first AgentRouter (#1120 slice 1)."""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

from src.agent.orchestrator import VALID_MODES
from src.agent.runtime import agent_router as router_module
from src.agent.runtime.agent_router import (
    CHAT_PATHS,
    INTENT_CATEGORIES,
    REASON_DEFAULT_STANDARD,
    REASON_EXPLICIT_OVERRIDE,
    REASON_FLOOR_COMPARE,
    REASON_FLOOR_MULTI_SYMBOL,
    REASON_FLOOR_NEED_NEWS,
    REASON_FLOOR_NEED_RISK,
    REASON_INCONSISTENT_FACTS,
    REASON_INVALID_ENTRY_KIND,
    REASON_INVALID_FLAG,
    REASON_INVALID_INTENT,
    REASON_INVALID_MISS_RATE,
    REASON_INVALID_OVERRIDE,
    REASON_INVALID_REQUEST,
    REASON_INVALID_SYMBOL_COUNT,
    REASON_QUICK_ELIGIBLE,
    REASON_UNKNOWN_FIELD,
    ROUTER_MODES,
    AgentRouter,
    AgentRouterDecision,
    AgentRouterRequest,
    normalize_router_mode,
    route,
)
from src.agent.runtime.mode_budget import BUDGET_MODES
from scripts.check_import_layers import module_name_for_path, package_of_module, top_level_import_modules

ROOT = Path(__file__).resolve().parents[3]
ROUTER_PATH = ROOT / "src/agent/runtime/agent_router.py"
ALLOWED_IMPORTS = frozenset(
    {
        "__future__",
        "math",
        "dataclasses",
        "types",
        "typing",
        "src.agent.runtime.mode_budget",
    }
)
BANNED_IMPORT_PREFIXES = (
    "src.agent.evolution",
    "src.agent.orchestrator",
    "src.agent.factory",
    "src.agent.runtime.native_adapter",
    "src.api",
    "src.bot",
    "src.repositories",
    "src.config",
    "src.schemas",
)


def _facts(**overrides):
    payload = {
        "intent_category": "analysis",
        "symbol_count": 1,
        "need_news": False,
        "need_risk": False,
        "entry_kind": "run",
    }
    payload.update(overrides)
    return payload


def _dumped(decision: AgentRouterDecision) -> str:
    return str(decision.to_dict())


def test_router_modes_match_orchestrator_and_budget_vocabulary():
    assert ROUTER_MODES == VALID_MODES
    assert set(ROUTER_MODES) == set(BUDGET_MODES) - {"chat"}
    assert "chat" not in ROUTER_MODES
    assert CHAT_PATHS == ("incremental_tool", "full_repipeline")


def test_normalize_router_mode_reuses_aliases_but_does_not_fail_open():
    assert normalize_router_mode("QUICK") == "quick"
    assert normalize_router_mode(" strategy ") == "specialist"
    assert normalize_router_mode("skill") == "specialist"
    assert normalize_router_mode("") is None
    assert normalize_router_mode("   ") is None
    assert normalize_router_mode("nonsense") is None
    assert normalize_router_mode("chat") is None
    assert normalize_router_mode("standard") == "standard"


def test_default_dashboard_run_is_standard_full_repipeline():
    decision = route(_facts())
    assert decision.accepted is True
    assert decision.mode == "standard"
    assert decision.chat_path == "full_repipeline"
    assert decision.reason_code == REASON_DEFAULT_STANDARD
    assert decision.error is None
    assert decision.explain["mode_floor"] == "none"
    assert decision.explain["miss_rate_applied"] is False


def test_never_defaults_to_always_full():
    decision = route(_facts(intent_category="technical"))
    assert decision.mode == "standard"
    assert decision.mode != "full"


def test_quick_eligible_simple_single_symbol_without_news_or_risk():
    decision = route(_facts(intent_category="simple"))
    assert decision.mode == "quick"
    assert decision.reason_code == REASON_QUICK_ELIGIBLE
    assert decision.chat_path == "full_repipeline"
    assert decision.explain["quick_eligible"] is True


def test_need_news_flag_requires_at_least_standard_not_quick():
    decision = route(_facts(intent_category="technical", need_news=True))
    assert decision.mode == "standard"
    assert decision.reason_code == REASON_FLOOR_NEED_NEWS
    assert decision.explain["quick_eligible"] is False
    assert decision.explain["mode_floor"] == "standard"


def test_news_intent_itself_is_at_least_standard():
    decision = route(_facts(intent_category="news", need_news=True))
    assert decision.accepted is True
    assert decision.mode == "standard"
    assert decision.reason_code == REASON_FLOOR_NEED_NEWS
    assert decision.explain["mode_floor"] == "standard"


def test_risk_intent_itself_requires_full():
    decision = route(_facts(intent_category="risk", need_risk=True))
    assert decision.accepted is True
    assert decision.mode == "full"
    assert decision.reason_code == REASON_FLOOR_NEED_RISK
    assert decision.explain["mode_floor"] == "full"


def test_risk_intent_with_need_risk_false_does_not_route_standard():
    decision = route(_facts(intent_category="risk", need_risk=False))
    assert decision.accepted is False
    assert decision.reason_code == REASON_INCONSISTENT_FACTS
    assert decision.mode is None
    assert decision.mode != "standard"
    assert decision.chat_path is None


def test_news_intent_with_need_news_false_does_not_route_below_standard():
    decision = route(_facts(intent_category="news", need_news=False))
    assert decision.accepted is False
    assert decision.reason_code == REASON_INCONSISTENT_FACTS
    assert decision.mode is None
    assert decision.mode not in {"quick", "standard"}
    assert decision.chat_path is None


@pytest.mark.parametrize(
    "payload, reason",
    [
        (_facts(need_risk=True), REASON_FLOOR_NEED_RISK),
        (_facts(intent_category="compare"), REASON_FLOOR_COMPARE),
        (_facts(symbol_count=2), REASON_FLOOR_MULTI_SYMBOL),
        (_facts(intent_category="risk", need_risk=True, symbol_count=3), REASON_FLOOR_NEED_RISK),
    ],
)
def test_risk_compare_and_multi_symbol_require_at_least_full(payload, reason):
    decision = route(payload)
    assert decision.accepted is True
    assert decision.mode == "full"
    assert decision.reason_code == reason
    assert decision.explain["mode_floor"] == "full"


@pytest.mark.parametrize(
    "payload, error_field",
    [
        (_facts(intent_category="risk", need_risk=False), "need_risk"),
        (_facts(intent_category="news", need_news=False), "need_news"),
        (_facts(intent_category="simple", need_news=True), "need_news"),
        (_facts(intent_category="simple", need_risk=True), "need_risk"),
        (_facts(intent_category="simple", symbol_count=2), "symbol_count"),
    ],
)
def test_intent_flag_contradictions_fail_closed(payload, error_field):
    decision = route(payload)
    assert decision.accepted is False
    assert decision.reason_code == REASON_INCONSISTENT_FACTS
    assert decision.mode is None
    assert decision.chat_path is None
    assert decision.explain["error_field"] == error_field
    assert decision.mode != "standard"


def test_valid_override_wins_over_floors_without_contradictory_simple_intent():
    decision = route(
        _facts(
            intent_category="analysis",
            need_risk=True,
            symbol_count=4,
            user_mode_override="quick",
        )
    )
    assert decision.mode == "quick"
    assert decision.reason_code == REASON_EXPLICIT_OVERRIDE
    assert decision.explain["override_present"] is True
    assert decision.explain["override_valid"] is True
    assert decision.explain["override_mode"] == "quick"


@pytest.mark.parametrize("override", ["full", "FULL", " specialist ", "strategy", "skill"])
def test_valid_override_including_specialist_and_aliases(override):
    decision = route(_facts(user_mode_override=override))
    assert decision.accepted is True
    assert decision.reason_code == REASON_EXPLICIT_OVERRIDE
    expected = "specialist" if override.strip().lower() in {"specialist", "strategy", "skill"} else "full"
    assert decision.mode == expected


def test_specialist_is_available_only_through_explicit_override():
    inferred = route(_facts(need_risk=True, intent_category="compare", symbol_count=3))
    assert inferred.mode == "full"
    assert inferred.mode != "specialist"
    explicit = route(_facts(user_mode_override="specialist"))
    assert explicit.mode == "specialist"
    assert explicit.reason_code == REASON_EXPLICIT_OVERRIDE


@pytest.mark.parametrize("override", ["", "   ", "nonsense", "chat", "auto", True, 1, 0.5])
def test_invalid_or_blank_override_fails_closed_and_never_maps_to_standard(override):
    decision = route(_facts(user_mode_override=override))
    assert decision.accepted is False
    assert decision.reason_code == REASON_INVALID_OVERRIDE
    assert decision.mode is None
    assert decision.chat_path is None
    assert decision.error
    assert decision.explain["override_present"] is True
    assert decision.explain["override_valid"] is False
    dumped = decision.to_dict()
    assert dumped["mode"] is None
    assert "nonsense" not in str(dumped)
    assert "user_mode_override" not in dumped["explain"]


def test_omitted_override_is_not_invalid():
    decision = route(_facts())
    assert decision.accepted is True
    assert decision.explain["override_present"] is False


def test_chat_same_symbol_follow_up_may_choose_incremental_tool():
    decision = route(
        _facts(
            entry_kind="chat",
            is_follow_up=True,
            same_symbol=True,
            tool_suitable=True,
        )
    )
    assert decision.mode == "standard"
    assert decision.chat_path == "incremental_tool"


@pytest.mark.parametrize(
    "overrides",
    [
        {"is_follow_up": False, "same_symbol": False},
        {"same_symbol": False},
        {"tool_suitable": False},
        {"need_news": True},
        {"need_risk": True},
    ],
)
def test_chat_re_pipeline_when_incremental_conditions_fail(overrides):
    payload = _facts(
        entry_kind="chat",
        is_follow_up=True,
        same_symbol=True,
        tool_suitable=True,
    )
    payload.update(overrides)
    decision = route(payload)
    assert decision.accepted is True
    assert decision.chat_path == "full_repipeline"


@pytest.mark.parametrize(
    "flag",
    ["is_follow_up", "same_symbol", "tool_suitable"],
)
def test_run_rejects_chat_only_flags(flag):
    payload = _facts(entry_kind="run")
    if flag == "same_symbol":
        payload["is_follow_up"] = True
    payload[flag] = True
    decision = route(payload)
    assert decision.accepted is False
    assert decision.reason_code == REASON_INCONSISTENT_FACTS
    assert decision.mode is None
    assert decision.explain["error_field"] == "entry_kind"


def test_same_symbol_without_follow_up_is_inconsistent():
    decision = route(
        _facts(
            entry_kind="chat",
            is_follow_up=False,
            same_symbol=True,
            tool_suitable=True,
        )
    )
    assert decision.accepted is False
    assert decision.reason_code == REASON_INCONSISTENT_FACTS
    assert decision.explain["error_field"] == "same_symbol"
    assert decision.mode is None


def test_explicit_full_or_specialist_override_forces_chat_re_pipeline():
    eligible = _facts(
        entry_kind="chat",
        is_follow_up=True,
        same_symbol=True,
        tool_suitable=True,
    )
    assert route(eligible).chat_path == "incremental_tool"
    assert route({**eligible, "user_mode_override": "full"}).chat_path == "full_repipeline"
    assert route({**eligible, "user_mode_override": "specialist"}).chat_path == "full_repipeline"
    quick = route({**eligible, "user_mode_override": "quick"})
    assert quick.mode == "quick"
    assert quick.chat_path == "incremental_tool"


def test_two_valid_miss_rates_have_zero_routing_influence():
    base = _facts(intent_category="simple")
    low = route({**base, "miss_rate": 0.05})
    high = route({**base, "miss_rate": 0.95})
    omitted = route(base)
    assert low.accepted and high.accepted and omitted.accepted
    assert low.mode == high.mode == omitted.mode == "quick"
    assert low.chat_path == high.chat_path == omitted.chat_path
    assert low.reason_code == high.reason_code == omitted.reason_code
    assert low.explain["miss_rate_applied"] is False
    assert high.explain["miss_rate_applied"] is False
    assert omitted.explain["miss_rate_applied"] is False
    assert low.explain["miss_rate_present"] is True
    assert high.explain["miss_rate_present"] is True
    assert omitted.explain["miss_rate_present"] is False


@pytest.mark.parametrize(
    "value",
    [
        True,
        False,
        "0.5",
        "0",
        float("nan"),
        float("inf"),
        float("-inf"),
        -0.01,
        1.01,
        2,
        {},
        [],
        object(),
    ],
)
def test_malformed_miss_rate_is_rejected_not_swallowed(value):
    decision = route(_facts(miss_rate=value))
    assert decision.accepted is False
    assert decision.reason_code == REASON_INVALID_MISS_RATE
    assert decision.mode is None
    assert decision.chat_path is None
    assert decision.explain["error_field"] == "miss_rate"


def test_boundary_integer_miss_rates_are_valid_and_neutral():
    zero = route(_facts(miss_rate=0))
    one = route(_facts(miss_rate=1))
    assert zero.accepted is True
    assert one.accepted is True
    assert zero.mode == one.mode
    assert zero.reason_code == one.reason_code


@pytest.mark.parametrize("field", ["need_news", "need_risk", "is_follow_up", "same_symbol", "tool_suitable"])
@pytest.mark.parametrize("value", [1, 0, "true", "false", 1.0, None, "yes"])
def test_non_strict_booleans_are_rejected(field, value):
    payload = _facts(entry_kind="chat")
    payload[field] = value
    decision = route(payload)
    assert decision.accepted is False
    assert decision.reason_code == REASON_INVALID_FLAG
    assert decision.mode is None
    assert decision.explain["error_field"] == field


@pytest.mark.parametrize("value", [-1, True, False, 1.0, "1", None, 1.5])
def test_invalid_symbol_count_types_and_negative_are_rejected(value):
    decision = route(_facts(symbol_count=value))
    assert decision.accepted is False
    assert decision.reason_code == REASON_INVALID_SYMBOL_COUNT
    assert decision.mode is None


def test_zero_symbol_count_is_valid_and_does_not_trigger_multi_symbol_floor():
    decision = route(_facts(symbol_count=0))
    assert decision.accepted is True
    assert decision.mode == "standard"
    assert decision.reason_code == REASON_DEFAULT_STANDARD


@pytest.mark.parametrize("value", ["", "not-an-intent", "full", True, None, 1])
def test_invalid_intent_category_is_rejected(value):
    payload = _facts()
    payload["intent_category"] = value
    decision = route(payload)
    assert decision.accepted is False
    assert decision.reason_code == REASON_INVALID_INTENT
    assert decision.mode is None


@pytest.mark.parametrize("value", ["research", "dashboard", "", True, None, "RUNN"])
def test_invalid_entry_kind_is_rejected(value):
    payload = _facts()
    payload["entry_kind"] = value
    decision = route(payload)
    assert decision.accepted is False
    assert decision.reason_code == REASON_INVALID_ENTRY_KIND


def test_non_mapping_request_is_rejected():
    decision = route("analyze 600519")  # type: ignore[arg-type]
    assert decision.accepted is False
    assert decision.reason_code == REASON_INVALID_REQUEST
    assert decision.mode is None
    assert "analyze 600519" not in _dumped(decision)


def test_decisions_are_deterministic_and_immutable():
    payload = _facts(intent_category="simple")
    first = route(payload)
    second = route(payload)
    third = AgentRouter().route(AgentRouterRequest(**payload))
    assert first == second == third
    assert first.to_dict() == second.to_dict()
    with pytest.raises(Exception):
        first.mode = "full"  # type: ignore[misc]
    with pytest.raises(TypeError):
        first.explain["chosen_mode"] = "full"  # type: ignore[index]


def test_router_does_not_mutate_valid_caller_input():
    payload = _facts(intent_category="simple")
    snapshot = dict(payload)
    decision = route(payload)
    assert payload == snapshot
    assert decision.accepted is True


def test_unknown_secret_fields_fail_closed_without_leakage_or_mutation():
    payload = _facts(intent_category="simple")
    payload["prompt"] = "SECRET_PROMPT analyze 600519"
    payload["api_key"] = "sk-secret"
    payload["message"] = "user message"
    snapshot = dict(payload)
    decision = route(payload)
    assert payload == snapshot
    assert decision.accepted is False
    assert decision.reason_code == REASON_UNKNOWN_FIELD
    assert decision.mode is None
    assert decision.chat_path is None
    dumped = _dumped(decision)
    for banned in (
        "prompt",
        "api_key",
        "message",
        "SECRET_PROMPT",
        "sk-secret",
        "user message",
        "metadata",
    ):
        assert banned not in dumped
        assert banned not in decision.explain
    assert decision.explain["error_field"] == "request"


def test_explain_is_bounded_to_whitelisted_derived_facts():
    decision = route(_facts(intent_category="simple", miss_rate=0.2))
    allowed = {
        "accepted",
        "intent_category",
        "symbol_count",
        "need_news",
        "need_risk",
        "entry_kind",
        "is_follow_up",
        "same_symbol",
        "tool_suitable",
        "override_present",
        "override_valid",
        "override_mode",
        "quick_eligible",
        "mode_floor",
        "miss_rate_present",
        "miss_rate_applied",
        "chosen_mode",
        "chosen_chat_path",
        "error_field",
    }
    assert decision.accepted is True
    assert set(decision.explain).issubset(allowed)
    assert "miss_rate" not in decision.explain
    assert 0.2 not in decision.explain.values()
    assert decision.explain["chosen_mode"] == "quick"
    assert decision.explain["chosen_chat_path"] == "full_repipeline"


def test_router_import_graph_stays_inside_runtime_mode_budget():
    imports = set(top_level_import_modules(ROOT, ROUTER_PATH))
    assert imports == ALLOWED_IMPORTS
    assert "src.agent.runtime.mode_budget" in imports
    for name in imports:
        for banned in BANNED_IMPORT_PREFIXES:
            assert name != banned
            assert not name.startswith(banned + ".")
    module_name = module_name_for_path(ROOT, ROUTER_PATH)
    assert package_of_module(module_name) == "src.agent"
    production_packages = {
        package_of_module(name)
        for name in imports
        if package_of_module(name) is not None
    }
    assert production_packages <= {"src.agent"}


def test_router_ast_does_not_call_or_bind_prefer_route():
    tree = ast.parse(ROUTER_PATH.read_text(encoding="utf-8"), filename=str(ROUTER_PATH))
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            assert node.id != "prefer_route"
        if isinstance(node, ast.Attribute):
            assert node.attr != "prefer_route"
        if isinstance(node, ast.ImportFrom):
            imported = {alias.name for alias in node.names}
            assert "prefer_route" not in imported
            module = node.module or ""
            for banned in BANNED_IMPORT_PREFIXES:
                assert module != banned
                assert not module.startswith(banned + ".")
        if isinstance(node, ast.Import):
            for alias in node.names:
                for banned in BANNED_IMPORT_PREFIXES:
                    assert alias.name != banned
                    assert not alias.name.startswith(banned + ".")
    assert "prefer_route" not in router_module.__dict__
    assert "evolution" not in router_module.__dict__
    assert getattr(router_module, "prefer_route", None) is None


def test_router_does_not_write_orchestrator_mode(monkeypatch):
    monkeypatch.delenv("AGENT_ORCHESTRATOR_MODE", raising=False)
    decision = route(_facts(intent_category="simple"))
    assert decision.accepted is True
    assert decision.mode == "quick"
    assert not hasattr(router_module, "AGENT_ORCHESTRATOR_MODE")
    assert "AGENT_ORCHESTRATOR_MODE" not in os.environ


def test_missing_required_classification_facts_fail_closed():
    decision = route(
        {
            "symbol_count": 1,
            "need_news": False,
            "need_risk": False,
            "entry_kind": "run",
        }
    )
    assert decision.accepted is False
    assert decision.reason_code == REASON_INVALID_INTENT


def test_docs_index_and_changelog_fragment_publish_the_library():
    index = (ROOT / "docs/INDEX.md").read_text(encoding="utf-8")
    index_en = (ROOT / "docs/INDEX_EN.md").read_text(encoding="utf-8")
    chinese = (ROOT / "docs/agent-router.md").read_text(encoding="utf-8")
    english = (ROOT / "docs/agent-router_EN.md").read_text(encoding="utf-8")
    fragment = (ROOT / "docs/changelog.d/1120-agent-router-rules.md").read_text(encoding="utf-8")
    assert "(agent-router.md)" in index
    assert "(agent-router_EN.md)" in index_en
    assert "unknown keys are dropped" not in english.lower()
    assert "未知键丢弃" not in chinese
    for document in (chinese, english):
        assert "invalid_override" in document
        assert "unknown_field" in document
        assert "inconsistent_facts" in document
        assert "incremental_tool" in document
        assert "full_repipeline" in document
        assert "[0.0, 1.0]" in document
        assert "#1120" in document
        assert "prefer_route" in document
        assert "not wired" in document.lower() or "未接线" in document
    assert "[Added]" in fragment
    assert "Refs #1120" in fragment
    assert "###" not in fragment


def test_intent_categories_are_bounded():
    matching_flags = {
        "simple": {},
        "technical": {},
        "news": {"need_news": True},
        "risk": {"need_risk": True},
        "compare": {},
        "analysis": {},
        "unknown": {},
    }
    for category in INTENT_CATEGORIES:
        decision = route(_facts(intent_category=category, **matching_flags[category]))
        assert decision.accepted is True
        assert decision.mode in ROUTER_MODES
    assert route(_facts(intent_category="simple")).mode == "quick"
    assert isinstance(route(_facts()), AgentRouterDecision)
