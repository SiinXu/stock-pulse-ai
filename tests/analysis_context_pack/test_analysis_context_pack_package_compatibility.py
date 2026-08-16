"""Compatibility guards for analysis context pack package convergence."""

import ast
import hashlib
import importlib
import inspect
import json
from pathlib import Path
import subprocess
import sys
import textwrap
from types import FunctionType
from typing import get_type_hints
from unittest.mock import patch

import pytest


MODULES = {
    "src.analysis_context_pack.prompt": (
        "src.analysis_context_pack.prompt",
        (
            "Any",
            "BLOCK_LABELS_EN",
            "BLOCK_LABELS_ZH",
            "CONSERVATIVE_MARKET_PHASES",
            "CORE_DEGRADED_STATUSES",
            "Dict",
            "INTRADAY_MARKET_PHASES",
            "Iterable",
            "KNOWN_MARKET_PHASES",
            "List",
            "Mapping",
            "Optional",
            "QUALITY_LEVEL_LABELS_EN",
            "QUALITY_LEVEL_LABELS_ZH",
            "SENSITIVE_MARKERS",
            "STATUS_LABELS_EN",
            "STATUS_LABELS_ZH",
            "analysis_context_pack_to_dict",
            "annotations",
            "format_analysis_context_pack_prompt_section",
            "get_analysis_context_pack_block_labels",
            "iter_analysis_context_pack_block_keys",
            "normalize_analysis_context_pack_language",
        ),
    ),
    "src.analysis_context_pack.overview": (
        "src.analysis_context_pack.overview",
        (
            "ANALYSIS_CONTEXT_PACK_OVERVIEW_KEY",
            "Any",
            "ContextFieldStatus",
            "Dict",
            "List",
            "MARKET_PHASE_SUMMARY_KEY",
            "Mapping",
            "Optional",
            "SENSITIVE_MARKERS",
            "analysis_context_pack_to_dict",
            "annotations",
            "extract_analysis_context_pack_overview",
            "get_analysis_context_pack_block_labels",
            "iter_analysis_context_pack_block_keys",
            "json",
            "log_safe_exception",
            "logger",
            "logging",
            "render_analysis_context_pack_overview",
            "sanitize_context_snapshot_for_api",
        ),
    ),
}

EXPECTED_AST_DIGESTS = {
    "src.analysis_context_pack.prompt": (
        "9a7eb8269f8db041abb7cf3cbf6a8beddab927c663a63b450d61978621f7b251"
    ),
    "src.analysis_context_pack.overview": (
        "0e87c19dd6ba3c2a124f4b629aff29f70007e101a9b940db05d819016154513e"
    ),
}

_MODULE_METADATA = {
    "__all__",
    "__builtins__",
    "__cached__",
    "__file__",
    "__loader__",
    "__name__",
    "__package__",
    "__spec__",
}
_OVERVIEW_PROMPT_BINDINGS = (
    "SENSITIVE_MARKERS",
    "analysis_context_pack_to_dict",
    "get_analysis_context_pack_block_labels",
    "iter_analysis_context_pack_block_keys",
)


def _source_function_names(module) -> tuple[str, ...]:
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    return tuple(
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    )


def _owned_function(value, module_name: str) -> bool:
    return isinstance(value, FunctionType) and value.__module__ == module_name


def _stable_ast(value):
    if isinstance(value, ast.AST):
        return [
            type(value).__name__,
            [
                [field, _stable_ast(getattr(value, field))]
                for field in value._fields
                if field != "type_params"
            ],
        ]
    if isinstance(value, list):
        return [_stable_ast(item) for item in value]
    return value


def _ast_digest(module) -> str:
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    payload = json.dumps(
        _stable_ast(tree),
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


RETIRED_ACP_SHIMS = (
    "src.analysis_context_pack_overview",
    "src.analysis_context_pack_prompt",
)


def test_retired_analysis_context_pack_shims_are_not_importable() -> None:
    """Deleted root-level analysis-context-pack facades must not remain importable."""

    for legacy_name in RETIRED_ACP_SHIMS:
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(legacy_name)


@pytest.mark.parametrize("legacy_name", MODULES)
def test_canonical_analysis_context_pack_modules_keep_owned_exports(legacy_name: str) -> None:
    implementation_name, expected_exports = MODULES[legacy_name]
    implementation = importlib.import_module(implementation_name)
    for name in expected_exports:
        assert hasattr(implementation, name), name




@pytest.mark.parametrize(
    "module_name",
    ("src.analysis_context_pack.prompt", "src.analysis_context_pack.prompt"),
)
def test_prompt_patch_seam_works_through_both_paths(module_name: str) -> None:
    module = importlib.import_module(module_name)
    payload = {"subject": {"code": "AAPL"}, "blocks": {}}

    with patch.object(module, "_pack_to_dict", return_value=payload) as converter:
        with patch.object(module, "_format_en", return_value="patched") as formatter:
            assert module.format_analysis_context_pack_prompt_section(
                object(),
                report_language="en",
            ) == "patched"

    converter.assert_called_once()
    formatter.assert_called_once_with(payload, enforce_forced_conclusion=True)


@pytest.mark.parametrize(
    "module_name",
    ("src.analysis_context_pack.overview", "src.analysis_context_pack.overview"),
)
def test_overview_patch_seam_works_through_both_paths(module_name: str) -> None:
    module = importlib.import_module(module_name)
    payload = {
        "subject": {"code": "AAPL"},
        "blocks": {
            "quote": {
                "status": "available",
                "source": "fixture",
                "items": [],
            }
        },
        "metadata": {},
        "data_quality": {},
    }

    with patch.object(module, "analysis_context_pack_to_dict", return_value=payload) as converter:
        overview = module.render_analysis_context_pack_overview(object())

    converter.assert_called_once()
    assert overview is not None
    assert overview["subject"]["code"] == "AAPL"
    assert overview["counts"]["available"] == 1


def test_overview_prompt_bindings_preserve_each_path_owner() -> None:
    legacy_overview = importlib.import_module("src.analysis_context_pack.overview")
    legacy_prompt = importlib.import_module("src.analysis_context_pack.prompt")
    implementation_overview = importlib.import_module("src.analysis_context_pack.overview")
    implementation_prompt = importlib.import_module("src.analysis_context_pack.prompt")

    for name in _OVERVIEW_PROMPT_BINDINGS:
        assert getattr(legacy_overview, name) is getattr(legacy_prompt, name)
        assert getattr(implementation_overview, name) is getattr(implementation_prompt, name)










@pytest.mark.parametrize("implementation_name", EXPECTED_AST_DIGESTS)
def test_relocated_implementation_ast_matches_baseline(implementation_name: str) -> None:
    implementation = importlib.import_module(implementation_name)
    assert _ast_digest(implementation) == EXPECTED_AST_DIGESTS[implementation_name]


