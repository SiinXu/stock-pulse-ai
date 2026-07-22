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
    "src.analysis_context_pack_prompt": (
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
    "src.analysis_context_pack_overview": (
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
        "4709f84df1b70f757f2d8a7790cf0f0bcdb62bdfe4983820f0355efe307e14e8"
    ),
    "src.analysis_context_pack.overview": (
        "1e3cb8ec2c40430df7f1aeaa61ca6c85f38399a12d211de7a46d62f6504cc64a"
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


@pytest.mark.parametrize("legacy_name", MODULES)
def test_facades_preserve_complete_module_surface(legacy_name: str) -> None:
    implementation_name, expected_exports = MODULES[legacy_name]
    implementation = importlib.import_module(implementation_name)
    legacy = importlib.import_module(legacy_name)

    assert tuple(sorted(name for name in vars(legacy) if not name.startswith("_"))) == (
        expected_exports
    )
    assert legacy.__all__ == expected_exports
    assert implementation.__all__ == expected_exports

    for name, implementation_value in vars(implementation).items():
        if name in _MODULE_METADATA:
            continue
        assert name in vars(legacy), name
        legacy_value = getattr(legacy, name)
        if _owned_function(implementation_value, implementation_name):
            assert legacy_value is not implementation_value, name
        elif (
            legacy_name == "src.analysis_context_pack_overview"
            and name in _OVERVIEW_PROMPT_BINDINGS
        ):
            legacy_prompt = importlib.import_module("src.analysis_context_pack_prompt")
            assert legacy_value is getattr(legacy_prompt, name), name
        elif name == "logger":
            assert legacy_value.name == legacy_name
            assert implementation_value.name == implementation_name
        else:
            assert legacy_value is implementation_value, name


@pytest.mark.parametrize("legacy_name", MODULES)
def test_facades_preserve_callable_contracts(legacy_name: str) -> None:
    implementation_name, _ = MODULES[legacy_name]
    implementation = importlib.import_module(implementation_name)
    legacy = importlib.import_module(legacy_name)

    implementation_aliases = {}
    legacy_aliases = {}
    for name, implementation_value in vars(implementation).items():
        if not _owned_function(implementation_value, implementation_name):
            continue
        legacy_value = getattr(legacy, name)
        assert legacy_value.__module__ == legacy_name
        assert legacy_value.__qualname__ == implementation_value.__qualname__
        assert legacy_value.__globals__ is vars(legacy)
        assert inspect.unwrap(legacy_value).__globals__ is vars(legacy)
        assert inspect.signature(legacy_value) == inspect.signature(implementation_value)
        assert legacy_value.__annotations__ == implementation_value.__annotations__
        assert get_type_hints(
            legacy_value,
            globalns=vars(legacy),
            localns=vars(legacy),
        ) == get_type_hints(
            implementation_value,
            globalns=vars(implementation),
            localns=vars(implementation),
        )
        implementation_aliases.setdefault(id(implementation_value), []).append(name)
        legacy_aliases.setdefault(id(legacy_value), []).append(name)

    assert sorted(sorted(names) for names in implementation_aliases.values()) == sorted(
        sorted(names) for names in legacy_aliases.values()
    )


@pytest.mark.parametrize(
    "module_name",
    ("src.analysis_context_pack_prompt", "src.analysis_context_pack.prompt"),
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
    formatter.assert_called_once_with(payload)


@pytest.mark.parametrize(
    "module_name",
    ("src.analysis_context_pack_overview", "src.analysis_context_pack.overview"),
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
    legacy_overview = importlib.import_module("src.analysis_context_pack_overview")
    legacy_prompt = importlib.import_module("src.analysis_context_pack_prompt")
    implementation_overview = importlib.import_module("src.analysis_context_pack.overview")
    implementation_prompt = importlib.import_module("src.analysis_context_pack.prompt")

    for name in _OVERVIEW_PROMPT_BINDINGS:
        assert getattr(legacy_overview, name) is getattr(legacy_prompt, name)
        assert getattr(implementation_overview, name) is getattr(implementation_prompt, name)


def test_legacy_overview_first_import_preserves_prompt_owners() -> None:
    code = textwrap.dedent(
        """
        import importlib

        legacy_overview = importlib.import_module("src.analysis_context_pack_overview")
        legacy_prompt = importlib.import_module("src.analysis_context_pack_prompt")
        implementation_overview = importlib.import_module("src.analysis_context_pack.overview")
        implementation_prompt = importlib.import_module("src.analysis_context_pack.prompt")
        names = (
            "SENSITIVE_MARKERS",
            "analysis_context_pack_to_dict",
            "get_analysis_context_pack_block_labels",
            "iter_analysis_context_pack_block_keys",
        )
        for name in names:
            assert getattr(legacy_overview, name) is getattr(legacy_prompt, name)
            assert getattr(implementation_overview, name) is getattr(
                implementation_prompt,
                name,
            )
        """
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_legacy_reload_rebinds_fresh_functions_in_subprocess() -> None:
    code = textwrap.dedent(
        """
        import ast
        import importlib
        from pathlib import Path

        modules = {
            "src.analysis_context_pack_prompt": "src.analysis_context_pack.prompt",
            "src.analysis_context_pack_overview": "src.analysis_context_pack.overview",
        }
        for legacy_name, implementation_name in modules.items():
            legacy = importlib.import_module(legacy_name)
            implementation = importlib.import_module(implementation_name)
            tree = ast.parse(Path(implementation.__file__).read_text(encoding="utf-8"))
            names = [
                node.name
                for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            previous_legacy = {name: getattr(legacy, name) for name in names}
            previous_implementation = {
                name: getattr(implementation, name) for name in names
            }
            for _ in range(2):
                importlib.reload(legacy)
                implementation = importlib.import_module(implementation_name)
                for name in names:
                    legacy_value = getattr(legacy, name)
                    implementation_value = getattr(implementation, name)
                    assert legacy_value is not previous_legacy[name]
                    assert implementation_value is not previous_implementation[name]
                    assert legacy_value is not implementation_value
                    assert legacy_value.__module__ == legacy_name
                    assert legacy_value.__globals__ is vars(legacy)
                    assert implementation_value.__module__ == implementation_name
                    assert implementation_value.__globals__ is vars(implementation)
                    previous_legacy[name] = legacy_value
                    previous_implementation[name] = implementation_value
            if legacy_name.endswith("_prompt"):
                assert legacy._pack_to_dict is legacy.analysis_context_pack_to_dict
                assert implementation._pack_to_dict is implementation.analysis_context_pack_to_dict

        legacy_prompt = importlib.import_module("src.analysis_context_pack_prompt")
        legacy_overview = importlib.import_module("src.analysis_context_pack_overview")
        implementation_prompt = importlib.import_module("src.analysis_context_pack.prompt")
        implementation_overview = importlib.import_module("src.analysis_context_pack.overview")
        names = (
            "SENSITIVE_MARKERS",
            "analysis_context_pack_to_dict",
            "get_analysis_context_pack_block_labels",
            "iter_analysis_context_pack_block_keys",
        )
        for name in names:
            assert getattr(legacy_overview, name) is getattr(legacy_prompt, name)
            assert getattr(implementation_overview, name) is getattr(
                implementation_prompt,
                name,
            )
        """
    )
    subprocess.run([sys.executable, "-c", code], check=True)


@pytest.mark.parametrize("legacy_name", MODULES)
def test_new_path_first_import_does_not_reload_implementation(legacy_name: str) -> None:
    implementation_name, _ = MODULES[legacy_name]
    code = textwrap.dedent(
        f"""
        import ast
        import importlib
        from pathlib import Path

        implementation = importlib.import_module({implementation_name!r})
        tree = ast.parse(Path(implementation.__file__).read_text(encoding="utf-8"))
        names = [
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        before = {{name: getattr(implementation, name) for name in names}}
        legacy = importlib.import_module({legacy_name!r})
        for name in names:
            implementation_value = getattr(implementation, name)
            legacy_value = getattr(legacy, name)
            assert implementation_value is before[name]
            assert implementation_value.__module__ == {implementation_name!r}
            assert implementation_value.__globals__ is vars(implementation)
            assert legacy_value is not implementation_value
            assert legacy_value.__module__ == {legacy_name!r}
            assert legacy_value.__globals__ is vars(legacy)
        """
    )
    subprocess.run([sys.executable, "-c", code], check=True)


@pytest.mark.parametrize("legacy_name", MODULES)
def test_legacy_modules_are_thin_facades(legacy_name: str) -> None:
    module = importlib.import_module(legacy_name)
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        for node in tree.body
    )


@pytest.mark.parametrize("implementation_name", EXPECTED_AST_DIGESTS)
def test_relocated_implementation_ast_matches_baseline(implementation_name: str) -> None:
    implementation = importlib.import_module(implementation_name)
    assert _ast_digest(implementation) == EXPECTED_AST_DIGESTS[implementation_name]


@pytest.mark.parametrize("legacy_name", MODULES)
def test_every_source_function_is_bound_by_facade(legacy_name: str) -> None:
    implementation_name, _ = MODULES[legacy_name]
    implementation = importlib.import_module(implementation_name)
    legacy = importlib.import_module(legacy_name)
    for name in _source_function_names(implementation):
        assert getattr(legacy, name).__globals__ is vars(legacy)
