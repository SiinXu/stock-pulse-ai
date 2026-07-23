"""Guard analysis orchestration behind the legacy :mod:`main` facade."""

import ast
from datetime import datetime, timezone
import inspect
from pathlib import Path
import subprocess
import sys
import textwrap
from types import CodeType
import typing
from unittest.mock import patch

from tests.litellm_stub import ensure_litellm_stub


ensure_litellm_stub()

import main
from src.app import analysis as analysis_source


MOVED_ANALYSIS_FUNCTIONS = (
    "_compute_trading_day_filter",
    "_run_market_review_with_shared_lock",
    "_is_multi_market_region",
    "_refresh_stock_index_cache_for_analysis",
    "_prime_daily_market_context",
    "_can_reuse_market_context_for_review",
    "_resolve_daily_market_context_market",
    "_resolve_daily_market_context_target_date",
    "_market_review_report_text",
    "_save_reused_market_review_report",
    "run_full_analysis",
)


def _assert_code_matches(facade_code: CodeType, source_code: CodeType) -> None:
    """Compare executable metadata while excluding moved source locations."""

    assert facade_code.co_argcount == source_code.co_argcount
    assert facade_code.co_posonlyargcount == source_code.co_posonlyargcount
    assert facade_code.co_kwonlyargcount == source_code.co_kwonlyargcount
    assert facade_code.co_nlocals == source_code.co_nlocals
    assert facade_code.co_stacksize == source_code.co_stacksize
    assert facade_code.co_flags == source_code.co_flags
    assert facade_code.co_code == source_code.co_code
    assert facade_code.co_names == source_code.co_names
    assert facade_code.co_varnames == source_code.co_varnames
    assert facade_code.co_freevars == source_code.co_freevars
    assert facade_code.co_cellvars == source_code.co_cellvars
    assert facade_code.co_name == source_code.co_name
    for attribute in ("co_qualname", "co_exceptiontable"):
        if hasattr(facade_code, attribute):
            assert getattr(facade_code, attribute) == getattr(source_code, attribute)
    assert len(facade_code.co_consts) == len(source_code.co_consts)
    for facade_constant, source_constant in zip(
        facade_code.co_consts,
        source_code.co_consts,
    ):
        if isinstance(source_constant, CodeType):
            assert isinstance(facade_constant, CodeType)
            _assert_code_matches(facade_constant, source_constant)
        else:
            assert facade_constant == source_constant


def _assert_facade_function(facade_function, source_function, qualname: str) -> None:
    """Verify metadata and global lookup remain attached to ``main``."""

    _assert_code_matches(facade_function.__code__, source_function.__code__)
    assert facade_function.__globals__ is vars(main)
    assert facade_function.__defaults__ == source_function.__defaults__
    assert facade_function.__kwdefaults__ == source_function.__kwdefaults__
    assert facade_function.__annotations__ == source_function.__annotations__
    assert facade_function.__closure__ == source_function.__closure__
    assert facade_function.__dict__ == source_function.__dict__
    assert facade_function.__doc__ == source_function.__doc__
    assert facade_function.__module__ == "main"
    assert facade_function.__qualname__ == qualname
    assert inspect.signature(facade_function) == inspect.signature(source_function)


def test_moved_analysis_functions_keep_main_facade_contracts() -> None:
    """Keep all historical analysis imports and patch targets on ``main``."""

    for name in MOVED_ANALYSIS_FUNCTIONS:
        _assert_facade_function(
            getattr(main, name),
            getattr(analysis_source, name),
            name,
        )

    resolvable_names = set(MOVED_ANALYSIS_FUNCTIONS) - {
        "_save_reused_market_review_report",
    }
    for name in resolvable_names:
        assert typing.get_type_hints(getattr(main, name)) == typing.get_type_hints(
            getattr(analysis_source, name)
        )
    for function in (
        main._save_reused_market_review_report,
        analysis_source._save_reused_market_review_report,
    ):
        try:
            typing.get_type_hints(function)
        except NameError as exc:
            assert "NotificationService" in str(exc)
        else:
            raise AssertionError("NotificationService must remain typing-only")


def test_analysis_implementations_leave_the_main_entrypoint_file() -> None:
    """Prevent analysis implementation bodies from returning to ``main.py``."""

    main_tree = ast.parse(Path(main.__file__).read_text(encoding="utf-8"))
    analysis_tree = ast.parse(
        Path(analysis_source.__file__).read_text(encoding="utf-8")
    )
    main_definitions = {
        node.name for node in main_tree.body if isinstance(node, ast.FunctionDef)
    }
    analysis_definitions = {
        node.name for node in analysis_tree.body if isinstance(node, ast.FunctionDef)
    }

    assert main_definitions.isdisjoint(MOVED_ANALYSIS_FUNCTIONS)
    assert set(MOVED_ANALYSIS_FUNCTIONS).issubset(analysis_definitions)


def test_source_first_import_and_reload_restore_analysis_bindings() -> None:
    """Reconstruct analysis facade functions after source or facade patching."""

    probe = textwrap.dedent(
        """
        import importlib

        source = importlib.import_module("src.app.analysis")
        facade = importlib.import_module("main")
        names = (
            "_compute_trading_day_filter",
            "_prime_daily_market_context",
            "_run_market_review_with_shared_lock",
            "run_full_analysis",
        )
        for name in names:
            assert getattr(facade, name).__globals__ is vars(facade)

        facade._compute_trading_day_filter = lambda *_args: ([], None, False)
        facade.run_full_analysis = lambda *_args, **_kwargs: False
        source._compute_trading_day_filter = lambda *_args: ([], None, False)
        source.run_full_analysis = lambda *_args, **_kwargs: False

        facade = importlib.reload(facade)
        source = importlib.import_module("src.app.analysis")
        for name in names:
            facade_function = getattr(facade, name)
            source_function = getattr(source, name)
            assert facade_function.__code__.co_code == source_function.__code__.co_code
            assert facade_function.__globals__ is vars(facade)
            assert facade_function.__module__ == "main"
            assert facade_function.__qualname__ == name
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_facade_patch_reaches_moved_analysis_helper() -> None:
    """Keep nested helper lookup on the legacy ``main`` monkeypatch seam."""

    current_time = datetime(2026, 7, 22, tzinfo=timezone.utc)
    expected = current_time.date()
    with patch(
        "main._resolve_daily_market_context_market",
        return_value="jp",
    ) as resolve_market, patch(
        "src.core.trading_calendar.get_effective_trading_date",
        return_value=expected,
    ) as resolve_date:
        result = main._resolve_daily_market_context_target_date(
            "jp,kr",
            current_time,
        )

    assert result == expected
    resolve_market.assert_called_once_with("cn", "jp,kr")
    resolve_date.assert_called_once_with("jp", current_time=current_time)


def test_application_services_remains_the_only_entrypoint_composition_root() -> None:
    """Keep dependency assembly in ``main()`` and out of analysis orchestration."""

    main_tree = ast.parse(Path(main.__file__).read_text(encoding="utf-8"))
    analysis_tree = ast.parse(
        Path(analysis_source.__file__).read_text(encoding="utf-8")
    )
    main_node = next(
        node
        for node in main_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "main"
    )
    installation_calls = [
        node
        for node in ast.walk(main_node)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "set_application_services"
    ]

    assert len(installation_calls) == 1
    installation = installation_calls[0]
    assert len(installation.args) == 1
    services = installation.args[0]
    assert isinstance(services, ast.Call)
    assert isinstance(services.func, ast.Name)
    assert services.func.id == "ApplicationServices"
    assert not any(
        isinstance(node, ast.ImportFrom)
        and node.module == "src.application_services"
        for node in analysis_tree.body
    )
