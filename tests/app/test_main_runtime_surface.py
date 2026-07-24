"""Guard runtime coordination behind the legacy :mod:`main` facade."""

import ast
import importlib
import inspect
from pathlib import Path
import subprocess
import sys
import textwrap
from types import CodeType, SimpleNamespace
import typing
from unittest.mock import patch

import pytest

from tests.litellm_stub import ensure_litellm_stub


ensure_litellm_stub()

import main
from src.app import runtime as runtime_source


MOVED_RUNTIME_FUNCTIONS = (
    "_is_public_bind_host",
    "_enforce_webui_bind_security",
    "_resolve_web_service_bind",
    "run_scheduled_analysis",
    "_run_analysis_with_runtime_scheduler_lock",
    "start_api_server",
    "_is_truthy_env",
    "start_bot_stream_clients",
    "_resolve_scheduled_stock_codes",
    "_reload_runtime_config",
    "_build_schedule_time_provider",
    "_build_schedule_times_provider",
)
INTERNAL_COORDINATORS = (
    (
        "__coordinate_service_runtime",
        "_coordinate_service_runtime",
    ),
    (
        "__run_service_only_mode",
        "_run_service_only_mode",
    ),
    (
        "__run_schedule_mode",
        "_run_schedule_mode",
    ),
    (
        "__keep_service_runtime_alive",
        "_keep_service_runtime_alive",
    ),
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
    assert typing.get_type_hints(facade_function) == typing.get_type_hints(
        source_function
    )


def _make_args(**overrides):
    """Build minimal CLI arguments for runtime routing tests."""

    values = {
        "backtest": False,
        "check_notify": False,
        "market_review": False,
        "no_notify": False,
        "schedule": False,
        "serve": False,
        "serve_only": False,
        "stocks": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _make_config(**overrides):
    """Build minimal runtime configuration for routing tests."""

    values = {
        "run_immediately": True,
        "schedule_enabled": False,
        "validate": lambda: [],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_moved_runtime_functions_keep_main_facade_contracts() -> None:
    """Keep all historical runtime imports and patch targets on ``main``."""

    for name in MOVED_RUNTIME_FUNCTIONS:
        _assert_facade_function(
            getattr(main, name),
            getattr(runtime_source, name),
            name,
        )


def test_internal_runtime_coordinators_use_main_globals() -> None:
    """Keep extracted coordination blocks bound to legacy patch seams."""

    for facade_name, source_name in INTERNAL_COORDINATORS:
        _assert_facade_function(
            vars(main)[facade_name],
            getattr(runtime_source, source_name),
            source_name,
        )


def test_runtime_implementations_leave_the_main_entrypoint_file() -> None:
    """Prevent the runtime implementation bodies from returning to ``main.py``."""

    main_tree = ast.parse(Path(main.__file__).read_text(encoding="utf-8"))
    runtime_tree = ast.parse(Path(runtime_source.__file__).read_text(encoding="utf-8"))
    main_definitions = {
        node.name for node in main_tree.body if isinstance(node, ast.FunctionDef)
    }
    runtime_definitions = {
        node.name for node in runtime_tree.body if isinstance(node, ast.FunctionDef)
    }

    assert main_definitions.isdisjoint(MOVED_RUNTIME_FUNCTIONS)
    assert set(MOVED_RUNTIME_FUNCTIONS).issubset(runtime_definitions)
    assert {
        source_name for _, source_name in INTERNAL_COORDINATORS
    }.issubset(runtime_definitions)


@pytest.mark.parametrize(
    ("mode", "args", "config", "start_serve"),
    (
        ("normal", _make_args(), _make_config(), False),
        ("schedule", _make_args(schedule=True), _make_config(), False),
        ("serve", _make_args(serve=True), _make_config(), True),
        ("serve_only", _make_args(serve_only=True), _make_config(), True),
    ),
)
def test_runtime_coordinator_routes_four_startup_modes(
    mode,
    args,
    config,
    start_serve,
) -> None:
    """Keep normal, schedule, serve, and serve-only dispatch boundaries stable."""

    dispatch = vars(main)["__dispatch_cli"]
    with patch(
        "main.__coordinate_service_runtime",
        return_value=(start_serve, None),
    ) as coordinate_service, patch(
        "main.__run_service_only_mode",
        return_value=0,
    ) as run_service_only, patch(
        "main.__run_schedule_mode",
        return_value=0,
    ) as run_schedule, patch(
        "main._run_analysis_with_runtime_scheduler_lock",
    ) as run_analysis, patch(
        "main.__keep_service_runtime_alive",
    ) as keep_service_alive:
        exit_code = dispatch(config, args)

    assert exit_code == 0
    coordinate_service.assert_called_once_with(config, args)
    if mode == "serve_only":
        run_service_only.assert_called_once_with(args)
        run_schedule.assert_not_called()
        run_analysis.assert_not_called()
        keep_service_alive.assert_not_called()
    elif mode == "schedule":
        run_service_only.assert_not_called()
        run_schedule.assert_called_once_with(config, args, None, start_serve)
        run_analysis.assert_not_called()
        keep_service_alive.assert_not_called()
    else:
        run_service_only.assert_not_called()
        run_schedule.assert_not_called()
        run_analysis.assert_called_once_with(config, args, None)
        keep_service_alive.assert_called_once_with(start_serve, args, config)


def test_futu_startup_failure_exits_standalone_but_keeps_started_service_alive() -> None:
    """Preserve explicit CLI failure without terminating an active API process."""
    dispatch = vars(main)["__dispatch_cli"]
    config = _make_config()

    for start_serve, expected_exit in ((False, 1), (True, 0)):
        args = _make_args(portfolio="futu")
        with patch(
            "main.__coordinate_service_runtime",
            return_value=(start_serve, None),
        ), patch(
            "main._run_analysis_with_runtime_scheduler_lock",
            return_value=False,
        ), patch("main.__keep_service_runtime_alive") as keep_service_alive:
            assert dispatch(config, args) == expected_exit

        if start_serve:
            keep_service_alive.assert_called_once_with(True, args, config)
        else:
            keep_service_alive.assert_not_called()


def test_runtime_lock_returns_the_underlying_analysis_outcome() -> None:
    """Let CLI dispatch distinguish a requested Futu import failure."""
    config = _make_config()
    args = _make_args(portfolio="futu")

    def run_immediately(*, task_runner, config, args, stock_codes, blocking):
        assert blocking is True
        task_runner(config, args, stock_codes)
        return True

    with patch("main.run_full_analysis", return_value=False), patch(
        "src.services.runtime_scheduler.run_with_global_analysis_lock",
        side_effect=run_immediately,
    ):
        assert main._run_analysis_with_runtime_scheduler_lock(config, args, None) is False


def test_source_first_import_and_reload_restore_runtime_bindings() -> None:
    """Reconstruct runtime facade functions after source or facade patching."""

    probe = textwrap.dedent(
        """
        import importlib

        source = importlib.import_module("src.app.runtime")
        facade = importlib.import_module("main")
        names = (
            "_reload_runtime_config",
            "run_scheduled_analysis",
            "start_api_server",
            "start_bot_stream_clients",
        )
        for name in names:
            assert getattr(facade, name).__globals__ is vars(facade)

        facade.start_api_server = lambda *_args, **_kwargs: None
        vars(facade)["__run_schedule_mode"] = lambda *_args: 99
        source.start_api_server = lambda *_args, **_kwargs: None
        source._run_schedule_mode = lambda *_args: 99

        facade = importlib.reload(facade)
        source = importlib.import_module("src.app.runtime")
        assert facade.start_api_server.__code__.co_code == source.start_api_server.__code__.co_code
        assert vars(facade)["__run_schedule_mode"].__code__.co_code == source._run_schedule_mode.__code__.co_code
        assert facade.start_api_server.__globals__ is vars(facade)
        assert vars(facade)["__run_schedule_mode"].__globals__ is vars(facade)
        assert facade.start_api_server.__module__ == "main"
        assert vars(facade)["__run_schedule_mode"].__module__ == "main"
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
