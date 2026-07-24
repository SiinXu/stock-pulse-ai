"""Guard the CLI compatibility facade exposed by :mod:`main`."""

import ast
import hashlib
import importlib
import inspect
import json
from pathlib import Path
import subprocess
import sys
import textwrap
from types import CodeType, SimpleNamespace
from unittest.mock import patch

import pytest

from tests.litellm_stub import ensure_litellm_stub


ensure_litellm_stub()

import main
from src.app import cli as cli_source


EXPECTED_PUBLIC_NAMES = (
    "Any",
    "ApplicationServices",
    "Callable",
    "Config",
    "Dict",
    "List",
    "Optional",
    "Path",
    "RelativePathFormatter",
    "TYPE_CHECKING",
    "Tuple",
    "Union",
    "annotations",
    "argparse",
    "date",
    "datetime",
    "dotenv_values",
    "get_config",
    "json",
    "log_safe_exception",
    "logger",
    "logging",
    "main",
    "multiprocessing",
    "os",
    "parse_arguments",
    "prepare_webui_frontend_assets",
    "resolve_index_stock_code_for_analysis",
    "run_full_analysis",
    "run_scheduled_analysis",
    "set_application_services",
    "setup_env",
    "setup_logging",
    "split_stock_list",
    "start_api_server",
    "start_bot_stream_clients",
    "sys",
    "time",
    "timedelta",
    "timezone",
    "uuid",
)
EXPECTED_PRIVATE_NAMES = (
    "_ACTIVE_ENV_FILE_VALUES",
    "_INITIAL_PROCESS_ENV",
    "_LazyPipelineDescriptor",
    "_ModuleExports",
    "_PUBLIC_BIND_HOSTS",
    "_RUNTIME_ENV_FILE_KEYS",
    "_bootstrap_environment",
    "_build_schedule_time_provider",
    "_build_schedule_times_provider",
    "_can_reuse_market_context_for_review",
    "_compute_trading_day_filter",
    "_env_bootstrapped",
    "_exports",
    "_get_active_env_path",
    "_get_stock_analysis_pipeline",
    "_is_multi_market_region",
    "_is_public_bind_host",
    "_is_truthy_env",
    "_market_review_report_text",
    "_packaged_import_probe",
    "_prime_daily_market_context",
    "_read_active_env_values",
    "_refresh_stock_index_cache_for_analysis",
    "_reload_env_file_values_preserving_overrides",
    "_reload_runtime_config",
    "_resolve_daily_market_context_market",
    "_resolve_daily_market_context_target_date",
    "_resolve_scheduled_stock_codes",
    "_resolve_web_service_bind",
    "_run_analysis_with_runtime_scheduler_lock",
    "_run_market_review_with_shared_lock",
    "_save_reused_market_review_report",
    "_setup_bootstrap_logging",
    "_setup_runtime_logging",
    "_warn_if_public_webui_without_auth",
)
EXPECTED_ARGUMENT_DEFAULTS = {
    "backtest": False,
    "backtest_code": None,
    "backtest_days": None,
    "backtest_force": False,
    "check_notify": False,
    "debug": False,
    "dry_run": False,
    "force_run": False,
    "host": None,
    "market_review": False,
    "no_context_snapshot": False,
    "no_market_review": False,
    "no_notify": False,
    "no_run_immediately": False,
    "port": None,
    "portfolio": None,
    "schedule": False,
    "serve": False,
    "serve_only": False,
    "single_notify": False,
    "stocks": None,
    "webui": False,
    "webui_only": False,
    "workers": None,
}


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


def test_main_module_preserves_legacy_export_names() -> None:
    """Keep the caller-facing main module namespace stable."""

    public_names = tuple(sorted(name for name in vars(main) if not name.startswith("_")))
    private_names = tuple(
        sorted(
            name
            for name in vars(main)
            if name.startswith("_") and not name.startswith("__")
        )
    )

    assert public_names == EXPECTED_PUBLIC_NAMES
    assert private_names == EXPECTED_PRIVATE_NAMES


def test_moved_cli_functions_keep_facade_metadata_and_globals() -> None:
    """Keep CLI parsing and dispatch bound to legacy main patch targets."""

    facade_globals = vars(main)
    dispatch = facade_globals["__dispatch_cli"]

    for facade_function, source_function, expected_qualname in (
        (main.parse_arguments, cli_source.parse_arguments, "parse_arguments"),
        (dispatch, cli_source._dispatch_cli, "_dispatch_cli"),
    ):
        _assert_code_matches(facade_function.__code__, source_function.__code__)
        assert facade_function.__globals__ is facade_globals
        assert facade_function.__defaults__ == source_function.__defaults__
        assert facade_function.__kwdefaults__ == source_function.__kwdefaults__
        assert facade_function.__annotations__ == source_function.__annotations__
        assert facade_function.__closure__ == source_function.__closure__
        assert facade_function.__dict__ == source_function.__dict__
        assert facade_function.__doc__ == source_function.__doc__
        assert facade_function.__module__ == "main"
        assert facade_function.__qualname__ == expected_qualname

    assert str(inspect.signature(main.parse_arguments)) == "() -> 'argparse.Namespace'"
    assert str(inspect.signature(main.main)) == "() -> 'int'"


@pytest.mark.parametrize(
    ("argv", "overrides"),
    (
        (["main.py"], {}),
        (["main.py", "--dry-run"], {"dry_run": True}),
        (["main.py", "--portfolio", "futu"], {"portfolio": "futu"}),
        (
            ["main.py", "--serve-only", "--host", "0.0.0.0", "--port", "9000"],
            {"serve_only": True, "host": "0.0.0.0", "port": 9000},
        ),
        (
            ["main.py", "--schedule", "--no-run-immediately"],
            {"schedule": True, "no_run_immediately": True},
        ),
        (
            [
                "main.py",
                "--backtest",
                "--backtest-code",
                "AAPL",
                "--backtest-days",
                "7",
                "--backtest-force",
            ],
            {
                "backtest": True,
                "backtest_code": "AAPL",
                "backtest_days": 7,
                "backtest_force": True,
            },
        ),
    ),
)
def test_parse_arguments_preserves_namespace_contract(argv, overrides) -> None:
    """Preserve defaults and representative mode-selection arguments."""

    expected = {**EXPECTED_ARGUMENT_DEFAULTS, **overrides}
    with patch.object(sys, "argv", argv):
        assert vars(main.parse_arguments()) == expected


def test_help_output_remains_byte_identical() -> None:
    """Freeze the complete public help output from the pre-split entrypoint."""

    result = subprocess.run(
        [sys.executable, str(Path(main.__file__).resolve()), "--help"],
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr.decode()
    assert len(result.stdout.decode()) == 2284
    assert len(result.stdout) == 3208
    assert hashlib.sha256(result.stdout).hexdigest() == (
        "f11311a6d51d8170fb8637984c8f5c585299ba98f770ec3aebf5d2707d8dcef2"
    )


def test_dry_run_flag_reaches_the_existing_analysis_dispatch() -> None:
    """Keep the real dry-run CLI flag on the one-shot analysis path."""

    config = SimpleNamespace(
        log_dir="logs",
        webui_enabled=False,
        schedule_enabled=False,
        run_immediately=True,
        validate=lambda: [],
    )
    observed = []

    def record_dispatch(runtime_config, args, stock_codes) -> None:
        observed.append((runtime_config, args, stock_codes))

    with patch.object(sys, "argv", ["main.py", "--dry-run"]), \
         patch("main.get_config", return_value=config), \
         patch("main._setup_bootstrap_logging"), \
         patch("main._setup_runtime_logging", return_value=True), \
         patch("main.set_application_services"), \
         patch(
             "main._run_analysis_with_runtime_scheduler_lock",
             side_effect=record_dispatch,
         ):
        exit_code = main.main()

    assert exit_code == 0
    assert len(observed) == 1
    runtime_config, args, stock_codes = observed[0]
    assert runtime_config is config
    assert args.dry_run is True
    assert stock_codes is None


def test_main_is_a_thin_bootstrap_and_dispatch_entrypoint() -> None:
    """Keep mode selection out of the public entrypoint body."""

    tree = ast.parse(Path(main.__file__).read_text(encoding="utf-8"))
    main_node = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "main"
    )
    return_node = main_node.body[-1]

    assert isinstance(return_node, ast.Return)
    assert isinstance(return_node.value, ast.Call)
    assert isinstance(return_node.value.func, ast.Name)
    assert return_node.value.func.id == "__dispatch_cli"
    assert [argument.id for argument in return_node.value.args] == ["config", "args"]
    mode_attributes = {
        node.attr
        for node in ast.walk(main_node)
        if isinstance(node, ast.Attribute)
    }
    assert mode_attributes.isdisjoint(
        {"backtest", "market_review", "schedule", "serve", "serve_only", "webui"}
    )


def test_source_first_import_and_reload_restore_cli_bindings() -> None:
    """Reconstruct both facade functions after source or facade patching."""

    probe = textwrap.dedent(
        """
        import importlib

        source = importlib.import_module("src.app.cli")
        facade = importlib.import_module("main")
        assert facade.parse_arguments.__globals__ is vars(facade)
        assert vars(facade)["__dispatch_cli"].__globals__ is vars(facade)

        facade.parse_arguments = lambda: None
        vars(facade)["__dispatch_cli"] = lambda *_args: 99
        source.parse_arguments = lambda: None
        source._dispatch_cli = lambda *_args: 99

        facade = importlib.reload(facade)
        source = importlib.import_module("src.app.cli")
        assert facade.parse_arguments.__code__.co_code == source.parse_arguments.__code__.co_code
        assert vars(facade)["__dispatch_cli"].__code__.co_code == source._dispatch_cli.__code__.co_code
        assert facade.parse_arguments.__globals__ is vars(facade)
        assert vars(facade)["__dispatch_cli"].__globals__ is vars(facade)
        assert facade.parse_arguments.__module__ == "main"
        assert vars(facade)["__dispatch_cli"].__module__ == "main"
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
