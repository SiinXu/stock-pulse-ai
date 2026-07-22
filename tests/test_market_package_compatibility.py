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


@pytest.mark.parametrize("legacy_name", MODULES)
def test_market_facades_preserve_public_exports(legacy_name: str) -> None:
    implementation_name, expected_exports = MODULES[legacy_name]
    legacy = importlib.import_module(legacy_name)
    implementation = importlib.import_module(implementation_name)

    public_names = tuple(sorted(name for name in vars(legacy) if not name.startswith("_")))
    assert public_names == expected_exports
    assert legacy.__all__ == expected_exports
    assert implementation.__all__ == expected_exports
    for name in expected_exports:
        assert getattr(legacy, name) is getattr(implementation, name)


@pytest.mark.parametrize("legacy_name", MODULES)
def test_market_facades_preserve_callable_ownership(legacy_name: str) -> None:
    implementation_name, _ = MODULES[legacy_name]
    legacy = importlib.import_module(legacy_name)
    implementation = importlib.import_module(implementation_name)

    for name, node in _source_definitions(implementation).items():
        value = getattr(legacy, name)
        assert value is getattr(implementation, name)
        assert value.__module__ == legacy_name
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert value.__globals__ is vars(legacy)
            assert inspect.unwrap(value).__globals__ is vars(legacy)
            get_type_hints(value, globalns=vars(legacy), localns=vars(legacy))
            continue

        get_type_hints(value, globalns=vars(legacy), localns=vars(legacy))
        for descriptor_name, descriptor in vars(value).items():
            function = _descriptor_function(descriptor)
            if function is None:
                continue
            assert function.__module__ == legacy_name, descriptor_name
            unwrapped = inspect.unwrap(function)
            assert unwrapped.__module__ == legacy_name, descriptor_name
            assert unwrapped.__globals__ is vars(legacy), descriptor_name
            if unwrapped is function:
                assert function.__globals__ is vars(legacy), descriptor_name
            else:
                assert function.__globals__.get("__name__") == "dataclasses"
            get_type_hints(
                function,
                globalns=vars(legacy),
                localns={**vars(legacy), **vars(value)},
            )


def test_market_analyzer_legacy_patch_seams() -> None:
    legacy = importlib.import_module("src.market_analyzer")
    config = object()
    data_manager = object()
    profile = object()
    strategy = object()

    with (
        patch.object(legacy, "get_config", return_value=config) as get_config,
        patch.object(legacy, "DataFetcherManager", return_value=data_manager),
        patch.object(legacy, "get_profile", return_value=profile),
        patch.object(legacy, "get_market_strategy_blueprint", return_value=strategy),
    ):
        analyzer = legacy.MarketAnalyzer()

    get_config.assert_called_once_with()
    assert analyzer.config is config
    assert analyzer.data_manager is data_manager
    assert analyzer.profile is profile
    assert analyzer.strategy is strategy


def test_small_market_module_patch_seams() -> None:
    context = importlib.import_module("src.market_context")
    with patch.object(context, "get_suffix_market", return_value="jp"):
        assert context.detect_market("7203.T") == "jp"

    phase_prompt = importlib.import_module("src.market_phase_prompt")
    with patch.object(phase_prompt, "_format_en", return_value="patched\n"):
        assert phase_prompt.format_market_phase_prompt_section(
            {"phase": "intraday"},
            report_language="en",
        ) == "patched\n"

    phase_summary = importlib.import_module("src.market_phase_summary")
    rebuilt = {"phase": "postmarket", "market": "jp", "warnings": []}
    with (
        patch.object(phase_summary, "get_market_for_stock", return_value="jp"),
        patch.object(
            phase_summary,
            "build_market_phase_context",
            return_value=SimpleNamespace(to_dict=lambda: rebuilt),
        ),
    ):
        assert phase_summary.rebuild_market_phase_summary_for_stock_code(
            "7203.T",
            {"market_phase_summary": {"phase": "postmarket"}},
        ) == rebuilt

    structure_prompt = importlib.import_module("src.market_structure_prompt")
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


def test_market_facade_reload_contract_in_subprocess() -> None:
    code = textwrap.dedent(
        """
        import ast
        import importlib
        from pathlib import Path
        from types import FunctionType

        modules = {
            "src.market_analyzer": "src.market.analyzer",
            "src.market_context": "src.market.context",
            "src.market_phase_prompt": "src.market.phase_prompt",
            "src.market_phase_summary": "src.market.phase_summary",
            "src.market_structure_prompt": "src.market.structure_prompt",
        }

        for legacy_name, implementation_name in modules.items():
            legacy = importlib.import_module(legacy_name)
            implementation = importlib.import_module(implementation_name)
            tree = ast.parse(Path(implementation.__file__).read_text(encoding="utf-8"))
            owned_names = [
                node.name
                for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            ]
            previous = {name: getattr(legacy, name) for name in owned_names}
            for _ in range(2):
                importlib.reload(legacy)
                implementation = importlib.import_module(implementation_name)
                for name in owned_names:
                    value = getattr(legacy, name)
                    assert value is getattr(implementation, name)
                    assert value is not previous[name]
                    assert value.__module__ == legacy_name
                    if isinstance(value, FunctionType):
                        assert value.__globals__ is vars(legacy)
                    previous[name] = value
        """
    )
    subprocess.run([sys.executable, "-c", code], check=True)


@pytest.mark.parametrize("legacy_name", MODULES)
def test_legacy_market_modules_are_thin_facades(legacy_name: str) -> None:
    module = importlib.import_module(legacy_name)
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        for node in tree.body
    )
