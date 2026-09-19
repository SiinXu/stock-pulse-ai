"""Pin ``main.py`` / ``server.py`` as bootstrap-only entry facades (Issue #1084)."""

from __future__ import annotations

import ast
from pathlib import Path

from tests.app.test_main_analysis_surface import MOVED_ANALYSIS_FUNCTIONS
from tests.app.test_main_runtime_surface import MOVED_RUNTIME_FUNCTIONS

REPO_ROOT = Path(__file__).resolve().parents[2]
MAIN_PATH = REPO_ROOT / "main.py"
SERVER_PATH = REPO_ROOT / "server.py"

MAIN_LIVE_FUNCTION_DEFS = frozenset(
    {
        "_get_active_env_path",
        "_read_active_env_values",
        "_bootstrap_environment",
        "_setup_bootstrap_logging",
        "_setup_runtime_logging",
        "_get_stock_analysis_pipeline",
        "__getattr__",
        "_reload_env_file_values_preserving_overrides",
        "main",
    }
)
MAIN_LIVE_CLASS_DEFS = frozenset(
    {
        "_LazyPipelineDescriptor",
        "_ModuleExports",
    }
)
SERVER_LIVE_FUNCTION_DEFS = frozenset(
    {
        "_resolved_existing_path",
        "_is_uvicorn_cli",
        "_is_direct_server_launch",
        "_uvicorn_env",
        "_parse_server_bind",
        "_enforce_server_bind",
    }
)
MOVED_CLI_NAMES = frozenset({"parse_arguments", "_dispatch_cli"})


def _top_level_defs(path: Path) -> tuple[set[str], set[str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    functions = {
        node.name for node in tree.body if isinstance(node, ast.FunctionDef)
    }
    classes = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}
    return functions, classes


def test_main_live_defs_match_bootstrap_allowlist() -> None:
    """Freeze live FunctionDef/ClassDef names in ``main.py`` (AST, not clones)."""

    functions, classes = _top_level_defs(MAIN_PATH)
    assert functions == MAIN_LIVE_FUNCTION_DEFS
    assert classes == MAIN_LIVE_CLASS_DEFS


def test_server_live_defs_match_bootstrap_allowlist() -> None:
    """Freeze live FunctionDef names in ``server.py``."""

    functions, classes = _top_level_defs(SERVER_PATH)
    assert functions == SERVER_LIVE_FUNCTION_DEFS
    assert classes == set()


def test_entry_facades_declare_bootstrap_only_issue_1084() -> None:
    """Both entry modules keep the Issue #1084 bootstrap/wiring marker."""

    main_source = MAIN_PATH.read_text(encoding="utf-8")
    server_source = SERVER_PATH.read_text(encoding="utf-8")
    assert "Issue #1084" in main_source
    assert "Issue #1084" in server_source
    assert "bootstrap-only" in main_source
    assert "bootstrap-only" in server_source


def test_entry_facade_line_budgets() -> None:
    """Keep entry facades thin; budgets leave room for the Issue #1084 header."""

    assert MAIN_PATH.read_text(encoding="utf-8").count("\n") < 580
    assert SERVER_PATH.read_text(encoding="utf-8").count("\n") < 220


def test_moved_owners_are_not_live_function_defs_in_main() -> None:
    """Analysis/runtime/CLI bodies must not return as live defs in ``main.py``."""

    functions, _classes = _top_level_defs(MAIN_PATH)
    moved = (
        set(MOVED_ANALYSIS_FUNCTIONS)
        | set(MOVED_RUNTIME_FUNCTIONS)
        | MOVED_CLI_NAMES
    )
    assert functions.isdisjoint(moved)
