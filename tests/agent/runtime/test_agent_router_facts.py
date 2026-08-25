# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Deterministic contract tests for AgentRouter fact projection (#1120 slice 2)."""

from __future__ import annotations

import ast
import os
from pathlib import Path
from types import MappingProxyType

import pytest

from src.agent.runtime.agent_router import (
    REASON_DEFAULT_STANDARD,
    REASON_EXPLICIT_OVERRIDE,
    REASON_FLOOR_COMPARE,
    REASON_FLOOR_MULTI_SYMBOL,
    REASON_INCONSISTENT_FACTS,
    REASON_INVALID_ENTRY_KIND,
    REASON_INVALID_FLAG,
    REASON_INVALID_INTENT,
    REASON_INVALID_OVERRIDE,
    REASON_INVALID_REQUEST,
    REASON_UNKNOWN_FIELD,
    AgentRouterRequest,
    route,
)
from src.agent.runtime.agent_router_facts import (
    REASON_INVALID_SCOPE_MODE,
    REASON_INVALID_SYMBOL_CODES,
    RouterFactProjection,
    project_router_request,
)
from src.agent.runtime.contract import ExecutionMode
from scripts.check_import_layers import module_name_for_path, package_of_module, top_level_import_modules

ROOT = Path(__file__).resolve().parents[3]
FACTS_PATH = ROOT / "src/agent/runtime/agent_router_facts.py"
ALLOWED_IMPORTS = frozenset(
    {
        "__future__",
        "collections.abc",
        "dataclasses",
        "typing",
        "src.agent.runtime.agent_router",
    }
)
BANNED_IMPORT_PREFIXES = (
    "src.agent.evolution",
    "src.agent.orchestrator",
    "src.agent.factory",
    "src.agent.runtime.native_adapter",
    "src.agent.stock_scope",
    "src.api",
    "src.bot",
    "src.repositories",
    "src.config",
    "src.schemas",
    "os",
    "os.path",
)


def _facts(**overrides):
    payload = {"entry_kind": "run"}
    payload.update(overrides)
    return payload


def _dump(projection: RouterFactProjection) -> str:
    return str(
        {
            "accepted": projection.accepted,
            "request": projection.request,
            "reason_code": projection.reason_code,
            "error": projection.error,
            "error_field": projection.error_field,
        }
    )


def _must_request(facts) -> AgentRouterRequest:
    projection = project_router_request(facts)
    assert projection.accepted is True, _dump(projection)
    assert projection.request is not None
    return projection.request


@pytest.mark.parametrize(
    "scope_mode, allowed, symbols, expected, entry_kind, want",
    [
        (
            None,
            (),
            ("600519",),
            "",
            "run",
            {
                "intent_category": "unknown",
                "symbol_count": 1,
                "need_news": False,
                "need_risk": False,
                "entry_kind": "run",
                "is_follow_up": False,
                "same_symbol": False,
                "tool_suitable": False,
                "user_mode_override": None,
            },
        ),
        (
            "compare",
            ("600519", "000001"),
            (),
            "",
            "run",
            {
                "intent_category": "compare",
                "symbol_count": 2,
                "need_news": False,
                "need_risk": False,
                "entry_kind": "run",
                "is_follow_up": False,
                "same_symbol": False,
                "tool_suitable": False,
                "user_mode_override": None,
            },
        ),
        (
            "maintain",
            ("600519",),
            (),
            "600519",
            "chat",
            {
                "intent_category": "unknown",
                "symbol_count": 1,
                "need_news": False,
                "need_risk": False,
                "entry_kind": "chat",
                "is_follow_up": True,
                "same_symbol": True,
                "tool_suitable": False,
                "user_mode_override": None,
            },
        ),
        (
            "switch",
            ("000001",),
            (),
            "600519",
            "chat",
            {
                "intent_category": "unknown",
                "symbol_count": 1,
                "need_news": False,
                "need_risk": False,
                "entry_kind": "chat",
                "is_follow_up": True,
                "same_symbol": False,
                "tool_suitable": False,
                "user_mode_override": None,
            },
        ),
        (
            "compare",
            ("AAPL", "MSFT"),
            ("IGNORED",),
            "",
            "chat",
            {
                "intent_category": "compare",
                "symbol_count": 2,
                "need_news": False,
                "need_risk": False,
                "entry_kind": "chat",
                "is_follow_up": False,
                "same_symbol": False,
                "tool_suitable": False,
                "user_mode_override": None,
            },
        ),
        (
            "maintain",
            (),
            (),
            "",
            "chat",
            {
                "intent_category": "unknown",
                "symbol_count": 0,
                "need_news": False,
                "need_risk": False,
                "entry_kind": "chat",
                "is_follow_up": True,
                "same_symbol": False,
                "tool_suitable": False,
                "user_mode_override": None,
            },
        ),
    ],
)
def test_stock_scope_like_tuples_project_router_fields(
    scope_mode, allowed, symbols, expected, entry_kind, want
):
    payload = _facts(entry_kind=entry_kind)
    if scope_mode is not None:
        payload["scope_mode"] = scope_mode
    if allowed:
        payload["allowed_stock_codes"] = allowed
    if symbols:
        payload["symbol_codes"] = symbols
    if expected:
        payload["expected_stock_code"] = expected
    request = _must_request(payload)
    for key, value in want.items():
        assert getattr(request, key) == value


def test_run_never_carries_chat_only_flags_even_with_maintain_scope():
    request = _must_request(
        _facts(
            entry_kind="run",
            scope_mode="maintain",
            allowed_stock_codes=["600519"],
            expected_stock_code="600519",
        )
    )
    assert request.entry_kind == "run"
    assert request.is_follow_up is False
    assert request.same_symbol is False
    assert request.tool_suitable is False


def test_allowed_codes_win_over_symbol_codes_when_nonempty():
    request = _must_request(
        _facts(
            allowed_stock_codes=["600519", "000001"],
            symbol_codes=["AAPL"],
        )
    )
    assert request.symbol_count == 2


def test_empty_allowed_falls_through_to_symbol_codes():
    request = _must_request(
        _facts(
            allowed_stock_codes=[],
            symbol_codes=["AAPL", "MSFT", "NVDA"],
        )
    )
    assert request.symbol_count == 3


def test_omitted_code_collections_yield_zero_symbols():
    request = _must_request(_facts())
    assert request.symbol_count == 0
    assert request.intent_category == "unknown"


@pytest.mark.parametrize(
    "value",
    ["research", "RESEARCH", ExecutionMode.RESEARCH, "dashboard", "", True, None, 1],
)
def test_research_entry_kind_is_rejected(value):
    projection = project_router_request(_facts(entry_kind=value))
    assert projection.accepted is False
    assert projection.reason_code == REASON_INVALID_ENTRY_KIND
    assert projection.request is None
    dumped = _dump(projection)
    assert "dashboard" not in dumped
    if isinstance(value, str) and value and value.lower() != "research":
        assert value not in dumped


def test_missing_entry_kind_fails_closed():
    projection = project_router_request({"symbol_codes": ["600519"]})
    assert projection.accepted is False
    assert projection.reason_code == REASON_INVALID_ENTRY_KIND
    assert projection.request is None


def test_execution_mode_run_and_chat_are_accepted():
    run_request = _must_request(_facts(entry_kind=ExecutionMode.RUN, symbol_codes=["600519"]))
    chat_request = _must_request(
        _facts(
            entry_kind=ExecutionMode.CHAT,
            scope_mode="maintain",
            expected_stock_code="600519",
            allowed_stock_codes=["600519"],
        )
    )
    assert run_request.entry_kind == "run"
    assert chat_request.entry_kind == "chat"
    assert chat_request.is_follow_up is True
    assert chat_request.same_symbol is True


@pytest.mark.parametrize("value", ["hold", "COMPAREX", "", True, 1, "follow"])
def test_unknown_scope_mode_is_rejected(value):
    projection = project_router_request(_facts(scope_mode=value))
    assert projection.accepted is False
    assert projection.reason_code == REASON_INVALID_SCOPE_MODE
    assert projection.request is None
    dumped = _dump(projection)
    if isinstance(value, str) and value:
        assert value not in dumped


@pytest.mark.parametrize(
    "field, value",
    [
        ("allowed_stock_codes", "600519"),
        ("symbol_codes", "AAPL"),
        ("allowed_stock_codes", {"600519": True}),
        ("symbol_codes", 1),
        ("allowed_stock_codes", ["600519", 1]),
        ("symbol_codes", ["", "AAPL"]),
        ("expected_stock_code", 600519),
        ("expected_stock_code", True),
        ("expected_stock_code", ["600519"]),
    ],
)
def test_malformed_symbol_collections_fail_closed(field, value):
    projection = project_router_request(_facts(**{field: value}))
    assert projection.accepted is False
    assert projection.reason_code == REASON_INVALID_SYMBOL_CODES
    assert projection.request is None
    dumped = _dump(projection)
    assert "600519" not in dumped
    assert "AAPL" not in dumped


def test_omitted_news_risk_and_tool_suitable_stay_false():
    request = _must_request(_facts(symbol_codes=["600519"]))
    assert request.need_news is False
    assert request.need_risk is False
    assert request.tool_suitable is False


def test_omitted_intent_is_unknown_never_simple():
    request = _must_request(_facts(symbol_codes=["600519"]))
    assert request.intent_category == "unknown"
    assert request.intent_category != "simple"
    decision = route(request)
    assert decision.mode == "standard"
    assert decision.mode != "quick"
    assert decision.reason_code == REASON_DEFAULT_STANDARD


def test_omitted_intent_with_compare_scope_is_compare():
    request = _must_request(_facts(scope_mode="compare", symbol_codes=["600519", "000001"]))
    assert request.intent_category == "compare"
    assert request.intent_category != "simple"


def test_explicit_simple_intent_is_preserved_when_legal():
    request = _must_request(
        _facts(intent_category="simple", symbol_codes=["600519"])
    )
    assert request.intent_category == "simple"
    assert request.symbol_count == 1


@pytest.mark.parametrize("field, value", [
    ("need_news", 1),
    ("need_risk", 0),
    ("tool_suitable", "true"),
    ("need_news", "false"),
    ("need_risk", None),
    ("tool_suitable", 1.0),
])
def test_non_strict_booleans_fail_closed(field, value):
    projection = project_router_request(_facts(entry_kind="chat", **{field: value}))
    assert projection.accepted is False
    assert projection.reason_code == REASON_INVALID_FLAG
    assert projection.error_field == field
    assert projection.request is None


def test_mapping_api_rejects_unknown_keys_without_echoing_them():
    payload = _facts(
        symbol_codes=["600519"],
        report_type="simple",
        skills=["momentum"],
        selected_skill_ids=["s1"],
        prompt="SECRET_PROMPT analyze 600519",
        api_key="sk-secret",
        miss_rate=0.4,
        is_follow_up=True,
        same_symbol=True,
        AGENT_ORCHESTRATOR_MODE="full",
    )
    snapshot = dict(payload)
    projection = project_router_request(payload)
    assert payload == snapshot
    assert projection.accepted is False
    assert projection.reason_code == REASON_UNKNOWN_FIELD
    assert projection.request is None
    dumped = _dump(projection)
    for banned in (
        "report_type",
        "simple",
        "skills",
        "selected_skill_ids",
        "momentum",
        "prompt",
        "SECRET_PROMPT",
        "api_key",
        "sk-secret",
        "miss_rate",
        "is_follow_up",
        "same_symbol",
        "AGENT_ORCHESTRATOR_MODE",
        "full",
    ):
        assert banned not in dumped
        assert banned not in (projection.error or "")
        assert banned != projection.error_field
    assert projection.error_field == "request"


def test_non_mapping_facts_fail_closed_without_echo():
    projection = project_router_request("analyze 600519")
    assert projection.accepted is False
    assert projection.reason_code == REASON_INVALID_REQUEST
    assert "analyze 600519" not in _dump(projection)


def test_run_one_symbol_unknown_intent_routes_default_standard_not_quick():
    request = _must_request(_facts(symbol_codes=["600519"]))
    decision = route(request)
    assert decision.accepted is True
    assert decision.mode == "standard"
    assert decision.chat_path == "full_repipeline"
    assert decision.reason_code == REASON_DEFAULT_STANDARD
    assert decision.mode != "quick"


def test_run_compare_scope_routes_full_repipeline():
    request = _must_request(_facts(scope_mode="compare", symbol_codes=["600519"]))
    decision = route(request)
    assert decision.mode == "full"
    assert decision.chat_path == "full_repipeline"
    assert decision.reason_code == REASON_FLOOR_COMPARE


def test_run_multi_symbol_routes_full_repipeline():
    request = _must_request(_facts(symbol_codes=["600519", "000001"]))
    decision = route(request)
    assert request.intent_category == "unknown"
    assert request.symbol_count == 2
    assert decision.mode == "full"
    assert decision.chat_path == "full_repipeline"
    assert decision.reason_code == REASON_FLOOR_MULTI_SYMBOL


def test_chat_maintain_same_symbol_default_tool_suitable_is_not_incremental():
    request = _must_request(
        _facts(
            entry_kind="chat",
            scope_mode="maintain",
            expected_stock_code="600519",
            allowed_stock_codes=["600519"],
        )
    )
    assert request.tool_suitable is False
    assert request.is_follow_up is True
    assert request.same_symbol is True
    decision = route(request)
    assert decision.chat_path == "full_repipeline"
    assert decision.chat_path != "incremental_tool"


def test_chat_maintain_with_explicit_tool_suitable_may_compose_incremental():
    request = _must_request(
        _facts(
            entry_kind="chat",
            scope_mode="maintain",
            expected_stock_code="600519",
            allowed_stock_codes=["600519"],
            tool_suitable=True,
        )
    )
    decision = route(request)
    assert decision.chat_path == "incremental_tool"


def test_chat_compare_is_not_incremental():
    request = _must_request(
        _facts(
            entry_kind="chat",
            scope_mode="compare",
            allowed_stock_codes=["600519", "000001"],
            tool_suitable=True,
        )
    )
    assert request.is_follow_up is False
    assert request.same_symbol is False
    decision = route(request)
    assert decision.chat_path == "full_repipeline"


def test_valid_explicit_override_is_passed_through_and_wins():
    request = _must_request(
        _facts(
            symbol_codes=["600519", "000001"],
            user_mode_override="quick",
        )
    )
    assert request.user_mode_override == "quick"
    decision = route(request)
    assert decision.mode == "quick"
    assert decision.reason_code == REASON_EXPLICIT_OVERRIDE


@pytest.mark.parametrize("override", ["", "   ", "nonsense", "chat", "auto"])
def test_invalid_or_blank_override_is_not_rewritten_to_standard(override):
    request = _must_request(_facts(symbol_codes=["600519"], user_mode_override=override))
    assert request.user_mode_override == override
    decision = route(request)
    assert decision.accepted is False
    assert decision.reason_code == REASON_INVALID_OVERRIDE
    assert decision.mode is None
    assert decision.mode != "standard"


def test_omitted_override_is_not_read_from_env_or_settings(monkeypatch):
    monkeypatch.setenv("AGENT_ORCHESTRATOR_MODE", "full")
    monkeypatch.setenv("agent_orchestrator_mode", "specialist")
    projection = project_router_request(_facts(symbol_codes=["600519"]))
    assert projection.accepted is True
    assert projection.request is not None
    assert projection.request.user_mode_override is None
    decision = route(projection.request)
    assert decision.mode == "standard"
    assert decision.mode != "full"
    assert os.environ["AGENT_ORCHESTRATOR_MODE"] == "full"


def test_non_string_override_fails_closed_without_coercion():
    projection = project_router_request(_facts(user_mode_override=True))
    assert projection.accepted is False
    assert projection.reason_code == REASON_INVALID_OVERRIDE
    assert projection.request is None


def test_explicit_none_override_means_not_provided():
    request = _must_request(_facts(user_mode_override=None, symbol_codes=["600519"]))
    assert request.user_mode_override is None


def test_run_with_tool_suitable_true_fails_closed_at_projector():
    projection = project_router_request(_facts(tool_suitable=True, symbol_codes=["600519"]))
    assert projection.accepted is False
    assert projection.reason_code == REASON_INCONSISTENT_FACTS
    assert projection.error_field == "entry_kind"
    assert projection.request is None


def test_simple_intent_with_multi_symbol_fails_closed_at_projector():
    projection = project_router_request(
        _facts(intent_category="simple", symbol_codes=["600519", "000001"])
    )
    assert projection.accepted is False
    assert projection.reason_code == REASON_INCONSISTENT_FACTS
    assert projection.error_field == "symbol_count"


def test_risk_intent_without_need_risk_fails_closed_at_projector():
    projection = project_router_request(_facts(intent_category="risk"))
    assert projection.accepted is False
    assert projection.reason_code == REASON_INCONSISTENT_FACTS
    assert projection.error_field == "need_risk"


def test_news_intent_without_need_news_fails_closed_at_projector():
    projection = project_router_request(_facts(intent_category="news"))
    assert projection.accepted is False
    assert projection.reason_code == REASON_INCONSISTENT_FACTS
    assert projection.error_field == "need_news"


@pytest.mark.parametrize("value", ["", "not-an-intent", "full", True, 1])
def test_invalid_intent_category_is_rejected(value):
    projection = project_router_request(_facts(intent_category=value))
    assert projection.accepted is False
    assert projection.reason_code == REASON_INVALID_INTENT
    assert projection.request is None


def test_projection_and_request_are_immutable():
    payload = _facts(symbol_codes=["600519"])
    projection = project_router_request(payload)
    assert projection.accepted is True
    with pytest.raises(Exception):
        projection.accepted = False  # type: ignore[misc]
    with pytest.raises(Exception):
        projection.request.symbol_count = 9  # type: ignore[union-attr]


def test_projector_does_not_mutate_caller_input():
    payload = _facts(
        symbol_codes=["600519"],
        allowed_stock_codes=["000001"],
        scope_mode="compare",
    )
    snapshot = {
        "entry_kind": payload["entry_kind"],
        "symbol_codes": list(payload["symbol_codes"]),
        "allowed_stock_codes": list(payload["allowed_stock_codes"]),
        "scope_mode": payload["scope_mode"],
    }
    projection = project_router_request(payload)
    assert projection.accepted is True
    assert payload["symbol_codes"] == snapshot["symbol_codes"]
    assert payload["allowed_stock_codes"] == snapshot["allowed_stock_codes"]
    assert payload["scope_mode"] == snapshot["scope_mode"]
    payload["symbol_codes"].append("MSFT")
    assert projection.request is not None
    assert projection.request.symbol_count == 1


def test_mapping_proxy_input_is_accepted():
    request = _must_request(MappingProxyType(_facts(symbol_codes=("600519",))))
    assert request.symbol_count == 1
    assert request.entry_kind == "run"


def test_set_of_allowed_codes_counts_unique_membership():
    request = _must_request(_facts(allowed_stock_codes={"600519", "000001"}))
    assert request.symbol_count == 2


def test_skills_do_not_become_specialist():
    projection = project_router_request(
        _facts(symbol_codes=["600519"], selected_skill_ids=["skill-a"], skills=["x"])
    )
    assert projection.accepted is False
    assert projection.reason_code == REASON_UNKNOWN_FIELD
    request = _must_request(_facts(symbol_codes=["600519"]))
    decision = route(request)
    assert decision.mode != "specialist"


def test_projector_import_graph_stays_on_router_types():
    imports = set(top_level_import_modules(ROOT, FACTS_PATH))
    assert imports == ALLOWED_IMPORTS
    for name in imports:
        for banned in BANNED_IMPORT_PREFIXES:
            assert name != banned
            assert not name.startswith(banned + ".")
    module_name = module_name_for_path(ROOT, FACTS_PATH)
    assert package_of_module(module_name) == "src.agent"
    production_packages = {
        package_of_module(name)
        for name in imports
        if package_of_module(name) is not None
    }
    assert production_packages <= {"src.agent"}


def test_projector_ast_has_no_route_config_or_prompt_parse():
    source = FACTS_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(FACTS_PATH))
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            assert node.id not in {
                "prefer_route",
                "get_config",
                "route",
                "AgentRouter",
                "resolve_stock_scope",
                "getenv",
                "environ",
            }
        if isinstance(node, ast.Attribute):
            assert node.attr not in {
                "prefer_route",
                "route",
                "get_config",
                "resolve_stock_scope",
                "agent_orchestrator_mode",
                "environ",
                "getenv",
            }
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imported = {alias.name for alias in node.names}
            assert "prefer_route" not in imported
            assert "route" not in imported
            assert "AgentRouter" not in imported
            assert "resolve_stock_scope" not in imported
            assert "get_config" not in imported
            for banned in BANNED_IMPORT_PREFIXES:
                assert module != banned
                assert not module.startswith(banned + ".")
        if isinstance(node, ast.Import):
            for alias in node.names:
                for banned in BANNED_IMPORT_PREFIXES:
                    assert alias.name != banned
                    assert not alias.name.startswith(banned + ".")
    assert "os.environ" not in source
    assert "get_config" not in source
    assert "resolve_stock_scope" not in source
    assert "AGENT_ORCHESTRATOR_MODE" not in source


def test_docs_and_changelog_publish_the_projector():
    index = (ROOT / "docs/INDEX.md").read_text(encoding="utf-8")
    index_en = (ROOT / "docs/INDEX_EN.md").read_text(encoding="utf-8")
    chinese = (ROOT / "docs/agent-router.md").read_text(encoding="utf-8")
    english = (ROOT / "docs/agent-router_EN.md").read_text(encoding="utf-8")
    fragment = (ROOT / "docs/changelog.d/1120-router-fact-projection.md").read_text(
        encoding="utf-8"
    )
    assert "(agent-router.md)" in index
    assert "(agent-router_EN.md)" in index_en
    for document in (chinese, english, index, index_en):
        assert "project_router_request" in document or "fact projection" in document.lower() or "事实投影" in document
    for document in (chinese, english):
        assert "project_router_request" in document
        assert "unknown" in document
        assert "simple" in document
        assert "AGENT_ORCHESTRATOR_MODE" in document
        assert "report_type" in document
        assert "#1120" in document
        assert "not wired" in document.lower() or "未接线" in document
        assert "incremental_tool" in document
    assert "[Added]" in fragment
    assert "Refs #1120" in fragment
    assert "###" not in fragment
