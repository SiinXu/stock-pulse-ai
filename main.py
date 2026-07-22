# -*- coding: utf-8 -*-
"""
===================================
A股自选股智能分析系统 - 主调度程序
===================================

职责：
1. 协调各模块完成股票分析流程
2. 实现低并发的线程池调度
3. 全局异常处理，确保单股失败不影响整体
4. 提供命令行入口

使用方式：
    python main.py              # 正常运行
    python main.py --debug      # 调试模式
    python main.py --dry-run    # 仅获取数据不分析

交易理念（已融入分析）：
- 严进策略：不追高，乖离率 > 5% 不买入
- 趋势交易：只做 MA5>MA10>MA20 多头排列
- 效率优先：关注筹码集中度好的股票
- 买点偏好：缩量回踩 MA5/MA10 支撑
"""
from __future__ import annotations

import json
import multiprocessing
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple, Union

if TYPE_CHECKING:
    from src.notification import NotificationService

from dotenv import dotenv_values
from src.config import setup_env

_INITIAL_PROCESS_ENV = dict(os.environ)
setup_env()

# Proxy configuration - Controlled by the USE_PROXY environment variable, default is disabled
# GitHub Actions automatically skips proxy configuration
if os.getenv("GITHUB_ACTIONS") != "true" and os.getenv("USE_PROXY", "false").lower() == "true":
    # Local development environment, enable proxy (can be configured in .env with PROXY_HOST and PROXY_PORT).
    proxy_host = os.getenv("PROXY_HOST", "127.0.0.1")
    proxy_port = os.getenv("PROXY_PORT", "10809")
    proxy_url = f"http://{proxy_host}:{proxy_port}"
    os.environ["http_proxy"] = proxy_url
    os.environ["https_proxy"] = proxy_url

_packaged_import_probe = os.getenv("DSA_PACKAGED_IMPORT_PROBE")
if _packaged_import_probe:
    import importlib
    import sys

    try:
        probed_module = importlib.import_module(_packaged_import_probe)
        if _packaged_import_probe == "src.migrations.registry":
            target_version = probed_module.TARGET_VERSION
            migration_ids = [
                migration.id for migration in probed_module.get_migrations()
            ]
            if not migration_ids or migration_ids[-1] != target_version:
                raise RuntimeError("Migration registry target is inconsistent")
    except Exception as exc:
        print(
            f"ERROR: packaged import failed for {_packaged_import_probe}: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    if _packaged_import_probe == "src.migrations.registry":
        print(
            "OK: packaged migration registry import succeeded "
            f"target={target_version}"
        )
    else:
        print(f"OK: packaged import succeeded for {_packaged_import_probe}")
    sys.exit(0)

import importlib as __importlib
import argparse
import logging
import sys
import time
import uuid
from datetime import date, datetime, timezone, timedelta

from src.webui_frontend import prepare_webui_frontend_assets
from src.application_services import ApplicationServices, set_application_services
from src.config import get_config, Config
from src.logging_config import RelativePathFormatter, setup_logging
from src.services.stock_list_parser import split_stock_list
from src.services.stock_code_utils import resolve_index_stock_code_for_analysis
from src.utils.sanitize import log_safe_exception


logger = logging.getLogger(__name__)
_RUNTIME_ENV_FILE_KEYS = set()
_PUBLIC_BIND_HOSTS = frozenset({"0.0.0.0", "::", "[::]", "*"})


def _get_active_env_path() -> Path:
    env_file = os.getenv("ENV_FILE")
    if env_file:
        return Path(env_file)
    return Path(__file__).resolve().parent / ".env"


def _read_active_env_values() -> Optional[Dict[str, str]]:
    env_path = _get_active_env_path()
    if not env_path.exists():
        return {}

    try:
        values = dotenv_values(env_path)
    except Exception as exc:  # pragma: no cover - defensive branch
        log_safe_exception(
            logger,
            "Environment file read failed; keeping current process environment",
            exc,
            error_code="main_environment_file_read_failed",
            level=logging.WARNING,
        )
        return None

    return {
        str(key): "" if value is None else str(value)
        for key, value in values.items()
        if key is not None
    }


_ACTIVE_ENV_FILE_VALUES = _read_active_env_values() or {}
_RUNTIME_ENV_FILE_KEYS = {
    key for key in _ACTIVE_ENV_FILE_VALUES
    if key not in _INITIAL_PROCESS_ENV
}

# setup_env() already ran at import time above.
_env_bootstrapped = True


def _bootstrap_environment() -> None:
    """Load .env and apply optional local proxy settings.

    Guarded to be idempotent so it can safely be called from lazy-import
    paths used by API / bot consumers.
    """
    global _env_bootstrapped
    if _env_bootstrapped:
        return

    from src.config import setup_env

    setup_env()

    if os.getenv("GITHUB_ACTIONS") != "true" and os.getenv("USE_PROXY", "false").lower() == "true":
        proxy_host = os.getenv("PROXY_HOST", "127.0.0.1")
        proxy_port = os.getenv("PROXY_PORT", "10809")
        proxy_url = f"http://{proxy_host}:{proxy_port}"
        os.environ["http_proxy"] = proxy_url
        os.environ["https_proxy"] = proxy_url

    _env_bootstrapped = True


def _setup_bootstrap_logging(debug: bool = False) -> None:
    """Initialize stderr-only logging before config is loaded.

    File handlers are deferred until ``config.log_dir`` is known (via the
    subsequent ``setup_logging()`` call) so that healthy runs never create
    log files in a hard-coded directory.
    """
    level = logging.DEBUG if debug else logging.INFO
    root = logging.getLogger()
    root.setLevel(level)
    if not any(
        isinstance(h, logging.StreamHandler) and getattr(h, "stream", None) is sys.stderr
        for h in root.handlers
    ):
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(level)
        handler.setFormatter(
            RelativePathFormatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
            )
        )
        root.addHandler(handler)


def _setup_runtime_logging(log_dir: str, debug: bool = False) -> bool:
    """Switch to configured logging, falling back to console on file I/O errors."""
    try:
        setup_logging(log_prefix="stock_analysis", debug=debug, log_dir=log_dir)
        return True
    except OSError as exc:
        log_safe_exception(
            logger,
            "File logging initialization failed; using console output. Check Docker mount permissions, read-only mounts, rootless Docker, NFS, or --user restrictions",
            exc,
            error_code="main_file_logging_setup_failed",
            level=logging.WARNING,
            context={"log_dir": log_dir},
        )
        return False


def _get_stock_analysis_pipeline():
    """Lazily import StockAnalysisPipeline for external consumers.

    Also ensures env/proxy bootstrap has run so that API / bot consumers
    that never call ``main()`` still get ``USE_PROXY`` applied.
    """
    _bootstrap_environment()
    from src.core.pipeline import StockAnalysisPipeline as _Pipeline

    return _Pipeline


class _LazyPipelineDescriptor:
    """Descriptor that resolves StockAnalysisPipeline on first attribute access."""

    _resolved = None

    def __set_name__(self, owner, name):
        self._name = name

    def __get__(self, obj, objtype=None):
        if self._resolved is None:
            self._resolved = _get_stock_analysis_pipeline()
        return self._resolved


class _ModuleExports:
    StockAnalysisPipeline = _LazyPipelineDescriptor()


_exports = _ModuleExports()


def __getattr__(name: str):
    if name == "StockAnalysisPipeline":
        return _exports.StockAnalysisPipeline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _reload_env_file_values_preserving_overrides() -> None:
    """Refresh `.env`-managed env vars without clobbering process env overrides."""
    global _RUNTIME_ENV_FILE_KEYS

    latest_values = _read_active_env_values()
    if latest_values is None:
        return

    managed_keys = {
        key for key in latest_values
        if key not in _INITIAL_PROCESS_ENV
    }

    for key in _RUNTIME_ENV_FILE_KEYS - managed_keys:
        os.environ.pop(key, None)

    for key in managed_keys:
        os.environ[key] = latest_values[key]

    _RUNTIME_ENV_FILE_KEYS = managed_keys


if "__runtime_source" in globals():
    __runtime_source = __importlib.reload(globals()["__runtime_source"])
else:
    from src.app import runtime as __runtime_source

if "__cli_source" in globals():
    __cli_source = __importlib.reload(globals()["__cli_source"])
else:
    from src.app import cli as __cli_source

_is_public_bind_host = __cli_source.clone_facade_function(
    __runtime_source._is_public_bind_host,
    globals(),
    module_name=__name__,
    qualname="_is_public_bind_host",
)
_warn_if_public_webui_without_auth = __cli_source.clone_facade_function(
    __runtime_source._warn_if_public_webui_without_auth,
    globals(),
    module_name=__name__,
    qualname="_warn_if_public_webui_without_auth",
)
_resolve_web_service_bind = __cli_source.clone_facade_function(
    __runtime_source._resolve_web_service_bind,
    globals(),
    module_name=__name__,
    qualname="_resolve_web_service_bind",
)
run_scheduled_analysis = __cli_source.clone_facade_function(
    __runtime_source.run_scheduled_analysis,
    globals(),
    module_name=__name__,
    qualname="run_scheduled_analysis",
)
_run_analysis_with_runtime_scheduler_lock = __cli_source.clone_facade_function(
    __runtime_source._run_analysis_with_runtime_scheduler_lock,
    globals(),
    module_name=__name__,
    qualname="_run_analysis_with_runtime_scheduler_lock",
)
start_api_server = __cli_source.clone_facade_function(
    __runtime_source.start_api_server,
    globals(),
    module_name=__name__,
    qualname="start_api_server",
)
_is_truthy_env = __cli_source.clone_facade_function(
    __runtime_source._is_truthy_env,
    globals(),
    module_name=__name__,
    qualname="_is_truthy_env",
)
start_bot_stream_clients = __cli_source.clone_facade_function(
    __runtime_source.start_bot_stream_clients,
    globals(),
    module_name=__name__,
    qualname="start_bot_stream_clients",
)
_resolve_scheduled_stock_codes = __cli_source.clone_facade_function(
    __runtime_source._resolve_scheduled_stock_codes,
    globals(),
    module_name=__name__,
    qualname="_resolve_scheduled_stock_codes",
)
_reload_runtime_config = __cli_source.clone_facade_function(
    __runtime_source._reload_runtime_config,
    globals(),
    module_name=__name__,
    qualname="_reload_runtime_config",
)
_build_schedule_time_provider = __cli_source.clone_facade_function(
    __runtime_source._build_schedule_time_provider,
    globals(),
    module_name=__name__,
    qualname="_build_schedule_time_provider",
)
_build_schedule_times_provider = __cli_source.clone_facade_function(
    __runtime_source._build_schedule_times_provider,
    globals(),
    module_name=__name__,
    qualname="_build_schedule_times_provider",
)
__coordinate_service_runtime = __cli_source.clone_facade_function(
    __runtime_source._coordinate_service_runtime,
    globals(),
    module_name=__name__,
    qualname="_coordinate_service_runtime",
)
__run_service_only_mode = __cli_source.clone_facade_function(
    __runtime_source._run_service_only_mode,
    globals(),
    module_name=__name__,
    qualname="_run_service_only_mode",
)
__run_schedule_mode = __cli_source.clone_facade_function(
    __runtime_source._run_schedule_mode,
    globals(),
    module_name=__name__,
    qualname="_run_schedule_mode",
)
__keep_service_runtime_alive = __cli_source.clone_facade_function(
    __runtime_source._keep_service_runtime_alive,
    globals(),
    module_name=__name__,
    qualname="_keep_service_runtime_alive",
)

parse_arguments = __cli_source.clone_facade_function(
    __cli_source.parse_arguments,
    globals(),
    module_name=__name__,
    qualname="parse_arguments",
)
__dispatch_cli = __cli_source.clone_facade_function(
    __cli_source._dispatch_cli,
    globals(),
    module_name=__name__,
    qualname="_dispatch_cli",
)


if "__analysis_source" in globals():
    __analysis_source = __importlib.reload(globals()["__analysis_source"])
else:
    from src.app import analysis as __analysis_source

_compute_trading_day_filter = __cli_source.clone_facade_function(
    __analysis_source._compute_trading_day_filter,
    globals(),
    module_name=__name__,
    qualname="_compute_trading_day_filter",
)
_run_market_review_with_shared_lock = __cli_source.clone_facade_function(
    __analysis_source._run_market_review_with_shared_lock,
    globals(),
    module_name=__name__,
    qualname="_run_market_review_with_shared_lock",
)
_is_multi_market_region = __cli_source.clone_facade_function(
    __analysis_source._is_multi_market_region,
    globals(),
    module_name=__name__,
    qualname="_is_multi_market_region",
)
_refresh_stock_index_cache_for_analysis = __cli_source.clone_facade_function(
    __analysis_source._refresh_stock_index_cache_for_analysis,
    globals(),
    module_name=__name__,
    qualname="_refresh_stock_index_cache_for_analysis",
)
_prime_daily_market_context = __cli_source.clone_facade_function(
    __analysis_source._prime_daily_market_context,
    globals(),
    module_name=__name__,
    qualname="_prime_daily_market_context",
)
_can_reuse_market_context_for_review = __cli_source.clone_facade_function(
    __analysis_source._can_reuse_market_context_for_review,
    globals(),
    module_name=__name__,
    qualname="_can_reuse_market_context_for_review",
)
_resolve_daily_market_context_market = __cli_source.clone_facade_function(
    __analysis_source._resolve_daily_market_context_market,
    globals(),
    module_name=__name__,
    qualname="_resolve_daily_market_context_market",
)
_resolve_daily_market_context_target_date = __cli_source.clone_facade_function(
    __analysis_source._resolve_daily_market_context_target_date,
    globals(),
    module_name=__name__,
    qualname="_resolve_daily_market_context_target_date",
)
_market_review_report_text = __cli_source.clone_facade_function(
    __analysis_source._market_review_report_text,
    globals(),
    module_name=__name__,
    qualname="_market_review_report_text",
)
_save_reused_market_review_report = __cli_source.clone_facade_function(
    __analysis_source._save_reused_market_review_report,
    globals(),
    module_name=__name__,
    qualname="_save_reused_market_review_report",
)
run_full_analysis = __cli_source.clone_facade_function(
    __analysis_source.run_full_analysis,
    globals(),
    module_name=__name__,
    qualname="run_full_analysis",
)

def main() -> int:
    """
    主入口函数

    Returns:
        退出码（0 表示成功）
    """
    # Parse command-line arguments
    args = parse_arguments()

    # Initialize bootstrap logs before loading, ensuring early failures are logged.
    try:
        _setup_bootstrap_logging(debug=args.debug)
    except Exception as exc:
        logging.basicConfig(
            level=logging.DEBUG if getattr(args, "debug", False) else logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            stream=sys.stderr,
        )
        for handler in logging.getLogger().handlers:
            handler.setFormatter(
                RelativePathFormatter(
                    "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
                )
            )
        log_safe_exception(
            logger,
            "Bootstrap logging initialization failed; using stderr",
            exc,
            error_code="main_bootstrap_logging_setup_failed",
            level=logging.WARNING,
        )

    # Load configuration (execute after bootstrap logging, ensure exceptions are logged)
    try:
        config = get_config()
    except Exception as exc:
        log_safe_exception(
            logger,
            "Configuration loading failed",
            exc,
            error_code="main_configuration_load_failed",
        )
        return 1

    # Establish the application composition root at the CLI startup layer, once
    # config is available and before config-dependent services are used.
    set_application_services(ApplicationServices())

    # Configure logging (output to console and file)
    try:
        _setup_runtime_logging(config.log_dir, debug=args.debug)
    except Exception as exc:
        log_safe_exception(
            logger,
            "Configured runtime logging setup failed",
            exc,
            error_code="main_runtime_logging_setup_failed",
        )
        return 1

    logger.info("=" * 60)
    logger.info("StockPulse analysis service starting")
    logger.info("Start time: %s", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    logger.info("=" * 60)

    return __dispatch_cli(config, args)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
