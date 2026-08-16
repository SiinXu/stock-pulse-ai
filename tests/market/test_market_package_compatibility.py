"""Compatibility guards for the market package convergence."""

import ast
import importlib
import inspect
from pathlib import Path
import subprocess
import sys
import textwrap
from types import FunctionType, SimpleNamespace
from typing import Any, get_type_hints
from unittest.mock import patch

import pytest


MODULES = {
    "src.market_analyzer": (
        "src.market.analyzer",
        (
            "Any",
            "DataFetcherManager",
            "Dict",
            "GenerationError",
            "GenerationErrorCode",
            "IntelligenceService",
            "List",
            "MARKET_LIGHT_REGIONS",
            "MarketAnalyzer",
            "MarketIndex",
            "MarketLightReviewResult",
            "MarketLightSnapshot",
            "MarketOverview",
            "MarketProfile",
            "Optional",
            "SearchService",
            "build_sector_analysis_payload",
            "dataclass",
            "datetime",
            "exception_chain_redaction_values",
            "field",
            "get_config",
            "get_market_strategy_blueprint",
            "get_profile",
            "getattr_static",
            "has_matching_exception_snapshot",
            "log_safe_exception",
            "logger",
            "logging",
            "normalize_report_language",
            "pd",
            "re",
            "record_llm_run",
            "record_llm_run_started",
            "render_sector_analysis_markdown",
            "render_sector_analysis_prompt_context",
            "resolve_generation_backend_id",
            "resolve_generation_fallback_backend_id",
            "sanitize_diagnostic_text",
            "time",
        ),
    ),
    "src.market_context": (
        "src.market.context",
        (
            "Optional",
            "detect_market",
            "get_market_guidelines",
            "get_market_role",
            "get_suffix_market",
            "re",
        ),
    ),
    "src.market_phase_prompt": (
        "src.market.phase_prompt",
        (
            "Any",
            "Dict",
            "List",
            "Optional",
            "annotations",
            "format_market_phase_prompt_section",
        ),
    ),
    "src.market_phase_summary": (
        "src.market.phase_summary",
        (
            "Any",
            "Dict",
            "List",
            "MARKET_PHASE_SUMMARY_KEY",
            "Mapping",
            "MarketPhase",
            "Optional",
            "annotations",
            "build_market_phase_context",
            "datetime",
            "extract_market_phase_summary",
            "format_public_market_status_line",
            "format_public_phase_pack_excerpt",
            "get_market_for_stock",
            "json",
            "normalize_analysis_phase_bucket",
            "rebuild_market_phase_summary_for_stock_code",
            "render_market_phase_summary",
        ),
    ),
    "src.market_structure_prompt": (
        "src.market.structure_prompt",
        (
            "Any",
            "Iterable",
            "List",
            "MARKET_STRUCTURE_SCHEMA_VERSION",
            "annotations",
            "format_market_structure_prompt_section",
            "normalize_report_language",
        ),
    ),
}


def _descriptor_function(descriptor: Any):
    if isinstance(descriptor, (staticmethod, classmethod)):
        return descriptor.__func__
    if isinstance(descriptor, FunctionType):
        return descriptor
    if isinstance(descriptor, property):
        return descriptor.fget
    return None


def _source_definitions(module):
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }


RETIRED_MARKET_SHIMS = tuple(MODULES)


def test_retired_market_shims_are_not_importable() -> None:
    """Deleted root-level market facades must not remain importable."""

    for legacy_name in RETIRED_MARKET_SHIMS:
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(legacy_name)
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("src.market_regime_prompt")


@pytest.mark.parametrize("legacy_name", MODULES)
def test_canonical_market_modules_keep_owned_exports(legacy_name: str) -> None:
    implementation_name, expected_exports = MODULES[legacy_name]
    implementation = importlib.import_module(implementation_name)
    owned = set(_source_definitions(implementation))
    for name in expected_exports:
        if name not in owned:
            continue
        implementation_value = getattr(implementation, name)
        if isinstance(implementation_value, FunctionType):
            assert implementation_value.__module__ == implementation_name


@pytest.mark.parametrize("legacy_name", MODULES)
def test_canonical_market_modules_preserve_callable_ownership(legacy_name: str) -> None:
    implementation_name, _ = MODULES[legacy_name]
    implementation = importlib.import_module(implementation_name)

    for name, node in _source_definitions(implementation).items():
        value = getattr(implementation, name)
        assert value.__module__ == implementation_name
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert value.__globals__ is vars(implementation)
            get_type_hints(value, globalns=vars(implementation), localns=vars(implementation))


def test_market_analyzer_canonical_patch_seams() -> None:
    canonical = importlib.import_module("src.market.analyzer")
    config = object()
    data_manager = object()

    with (
        patch.object(canonical, "get_config", return_value=config) as get_config,
        patch.object(canonical, "DataFetcherManager", return_value=data_manager),
        patch(
            "src.core.market_profile.get_profile",
            return_value=object(),
        ) as get_profile,
        patch(
            "src.core.market_strategy.get_market_strategy_blueprint",
            return_value=object(),
        ) as get_strategy,
    ):
        analyzer = canonical.MarketAnalyzer()

    get_config.assert_called_once_with()
    get_profile.assert_called_once()
    get_strategy.assert_called_once()
    assert analyzer.config is config
    assert analyzer.data_manager is data_manager


def test_small_market_module_patch_seams() -> None:
    context = importlib.import_module("src.market.context")
    with patch.object(context, "get_suffix_market", return_value="jp"):
        assert context.detect_market("7203.T") == "jp"

    phase_prompt = importlib.import_module("src.market.phase_prompt")
    with patch.object(phase_prompt, "_format_en", return_value="patched\n"):
        assert phase_prompt.format_market_phase_prompt_section(
            {"phase": "intraday"},
            report_language="en",
        ) == "patched\n"

    phase_summary = importlib.import_module("src.market.phase_summary")
    rebuilt = {"phase": "postmarket", "market": "jp", "warnings": []}
    with (
        patch(
            "src.core.trading_calendar.get_market_for_stock",
            return_value="jp",
        ),
        patch(
            "src.core.trading_calendar.build_market_phase_context",
            return_value=SimpleNamespace(to_dict=lambda: rebuilt),
        ),
    ):
        assert phase_summary.rebuild_market_phase_summary_for_stock_code(
            "7203.T",
            {"market_phase_summary": {"phase": "postmarket"}},
        ) == rebuilt

    structure_prompt = importlib.import_module("src.market.structure_prompt")
    payload = {
        "schema_version": structure_prompt.MARKET_STRUCTURE_SCHEMA_VERSION,
        "status": "available",
        "market_theme_context": {},
        "stock_market_position": {},
    }
    with patch.object(structure_prompt, "normalize_report_language", return_value="en"):
        assert "Market Structure Context" in (
            structure_prompt.format_market_structure_prompt_section(payload)
        )
