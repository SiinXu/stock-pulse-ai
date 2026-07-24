"""Runtime coordination for CLI scheduling and service startup."""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from typing import TYPE_CHECKING, List, Optional, Tuple

from src.config import Config, get_config
from src.utils.sanitize import log_safe_exception
from src.webui_frontend import prepare_webui_frontend_assets

if TYPE_CHECKING:
    from main import (
        _INITIAL_PROCESS_ENV,
        _PUBLIC_BIND_HOSTS,
        _reload_env_file_values_preserving_overrides,
        run_full_analysis,
    )


logger = logging.getLogger(__name__)


def _is_public_bind_host(host: str) -> bool:
    return (host or "").strip().lower() in _PUBLIC_BIND_HOSTS


def _warn_if_public_webui_without_auth(host: str) -> None:
    if not _is_public_bind_host(host):
        return

    from src.auth import is_auth_enabled

    if is_auth_enabled():
        return
    logger.warning(
        "WEBUI_HOST=%s binds the Web UI to a public interface while "
        "ADMIN_AUTH_ENABLED=false. Keep this service behind a trusted network "
        "boundary or enable admin authentication before exposing it.",
        host,
    )


def _resolve_web_service_bind(args: argparse.Namespace, config: Config) -> Tuple[str, int]:
    """Resolve the effective Web/API bind address from CLI first, then config."""
    host = args.host if args.host is not None else (config.webui_host or "127.0.0.1")
    port = args.port if args.port is not None else config.webui_port
    return host, port


def run_scheduled_analysis(
    config: Config,
    args: argparse.Namespace,
    stock_codes: Optional[List[str]] = None,
) -> bool:
    """Run scheduled analysis with failures propagated to the scheduler."""
    return run_full_analysis(config, args, stock_codes, raise_errors=True)


def _run_analysis_with_runtime_scheduler_lock(
    config: Config,
    args: argparse.Namespace,
    stock_codes: Optional[List[str]] = None,
) -> bool:
    from src.services.runtime_scheduler import run_with_global_analysis_lock

    analysis_succeeded = False

    def _run_locked(runtime_config, runtime_args, runtime_stock_codes):
        nonlocal analysis_succeeded
        analysis_succeeded = bool(
            run_full_analysis(runtime_config, runtime_args, runtime_stock_codes)
        )

    # Keep startup/triggered analysis in sync with API runtime scheduler and
    # run-now entrypoint. Blocking is expected here because startup paths should
    # wait for an in-flight job before returning a response.
    lock_acquired = run_with_global_analysis_lock(
        task_runner=_run_locked,
        config=config,
        args=args,
        stock_codes=stock_codes,
        blocking=True,
    )
    return bool(lock_acquired and analysis_succeeded)


def start_api_server(host: str, port: int, config: Config) -> None:
    """
    在后台线程启动 FastAPI 服务

    Args:
        host: 监听地址
        port: 监听端口
        config: 配置对象
    """
    import socket
    import threading
    import uvicorn

    probe = socket.socket(socket.AF_INET6 if ":" in host else socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind((host, port))
    except OSError as exc:
        raise RuntimeError(f"FastAPI port is not available: {host}:{port}") from exc
    finally:
        probe.close()

    level_name = (config.log_level or "INFO").lower()
    use_config_signal_handlers = True
    uvicorn_kwargs = {
        "host": host,
        "port": port,
        "log_level": level_name,
        "log_config": None,
    }
    # Import the ASGI app object in the calling thread instead of handing uvicorn
    # the "api.app:app" import string. With the string, uvicorn imports the app
    # lazily inside the server thread, and that import (litellm + the full app
    # tree, ~10s+ on constrained hosts) runs inside the startup probe window
    # below, tripping the 3.0s timeout and causing a restart loop on slower
    # machines. Importing first keeps the heavy work out of the probe window;
    # genuine import failures still surface immediately to the caller.
    from api.app import app as fastapi_app

    try:
        uvicorn_config = uvicorn.Config(
            fastapi_app,
            install_signal_handlers=False,
            **uvicorn_kwargs,
        )
    except TypeError:
        # Older uvicorn versions do not accept install_signal_handlers in
        # Config; fall back and only disable signal handling via Server attribute
        # when it's a boolean flag.
        use_config_signal_handlers = False
        uvicorn_config = uvicorn.Config(
            fastapi_app,
            **uvicorn_kwargs,
        )
    uvicorn_server = uvicorn.Server(config=uvicorn_config)
    if not use_config_signal_handlers:
        install_signal_handlers = getattr(uvicorn_server, "install_signal_handlers", None)
        if isinstance(install_signal_handlers, bool):
            uvicorn_server.install_signal_handlers = False

    startup_error: list[BaseException] = []

    def run_server():
        try:
            uvicorn_server.run()
        except Exception as exc:  # broad-exception: cleanup - hand background startup failures to the caller probe for typed propagation
            startup_error.append(exc)

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()

    timeout_seconds = 3.0
    wait_deadline = time.time() + timeout_seconds
    while time.time() < wait_deadline:
        if startup_error:
            raise RuntimeError(
                f"FastAPI server failed to start: {host}:{port}; {startup_error[0]}"
            )
        if uvicorn_server.started:
            logger.info("FastAPI server started: http://%s:%s", host, port)
            return
        if not thread.is_alive():
            break
        time.sleep(0.05)

    if startup_error:
        raise RuntimeError(f"FastAPI server failed to start: {host}:{port}; {startup_error[0]}")
    if uvicorn_server.started:
        logger.info("FastAPI server started: http://%s:%s", host, port)
        return
    if not thread.is_alive():
        raise RuntimeError(f"FastAPI 服务器启动后立即退出: {host}:{port}")

    raise RuntimeError(f"FastAPI 服务在 {timeout_seconds:.1f}s 内未完成启动: {host}:{port}")


def _is_truthy_env(var_name: str, default: str = "true") -> bool:
    """Parse common truthy / falsy environment values."""
    value = os.getenv(var_name, default).strip().lower()
    return value not in {"0", "false", "no", "off"}


def start_bot_stream_clients(config: Config) -> None:
    """Start bot stream clients when enabled in config."""
    # Start the DingTalk Stream client.
    if config.dingtalk_stream_enabled:
        try:
            from bot.platforms import start_dingtalk_stream_background, DINGTALK_STREAM_AVAILABLE
            if DINGTALK_STREAM_AVAILABLE:
                if start_dingtalk_stream_background():
                    logger.info("[Main] Dingtalk Stream client started in background.")
                else:
                    logger.warning("[Main] Dingtalk Stream client failed to start.")
            else:
                logger.warning("[Main] Dingtalk Stream enabled but SDK is missing.")
                logger.warning("[Main] Run: pip install dingtalk-stream")
        except Exception as exc:  # broad-exception: fallback_recorded - preserve logged DingTalk startup degradation
            log_safe_exception(
                logger,
                "DingTalk Stream client failed to start",
                exc,
                error_code="main_dingtalk_stream_start_failed",
            )

    # Start the Feishu Stream client.
    if getattr(config, 'feishu_stream_enabled', False):
        try:
            from bot.platforms import start_feishu_stream_background, FEISHU_SDK_AVAILABLE
            if FEISHU_SDK_AVAILABLE:
                if start_feishu_stream_background():
                    logger.info("[Main] Feishu Stream client started in background.")
                else:
                    logger.warning("[Main] Feishu Stream client failed to start.")
            else:
                logger.warning("[Main] Feishu Stream enabled but SDK is missing.")
                logger.warning("[Main] Run: pip install lark-oapi")
        except Exception as exc:  # broad-exception: fallback_recorded - preserve logged Feishu startup degradation
            log_safe_exception(
                logger,
                "Feishu Stream client failed to start",
                exc,
                error_code="main_feishu_stream_start_failed",
            )


def _resolve_scheduled_stock_codes(stock_codes: Optional[List[str]]) -> Optional[List[str]]:
    """Scheduled runs should always read the latest persisted watchlist."""
    if stock_codes is not None:
        logger.warning(
            "Scheduled mode received --stocks; scheduled runs ignore the startup snapshot "
            "and reload the latest STOCK_LIST before each run"
        )
    return None


def _reload_runtime_config() -> Config:
    """Reload config from the latest persisted `.env` values for scheduled runs."""
    _reload_env_file_values_preserving_overrides()
    Config.reset_instance()
    return get_config()


def _build_schedule_time_provider(default_schedule_time: str):
    """Read the latest schedule time directly from the active config file.

    Fallback order:
    1. Process-level env override (set before launch) → honour it.
    2. Persisted config file value (written by WebUI) → use it.
    3. Documented system default ``"18:00"`` → always fall back here so
       that clearing SCHEDULE_TIME in WebUI correctly resets the schedule.
    """
    from src.core.config_manager import ConfigManager

    _SYSTEM_DEFAULT_SCHEDULE_TIME = "18:00"
    manager = ConfigManager()

    def _provider() -> str:
        if "SCHEDULE_TIME" in _INITIAL_PROCESS_ENV:
            return os.getenv("SCHEDULE_TIME", default_schedule_time)

        config_map = manager.read_config_map()
        schedule_time = (config_map.get("SCHEDULE_TIME", "") or "").strip()
        if schedule_time:
            return schedule_time
        return _SYSTEM_DEFAULT_SCHEDULE_TIME

    return _provider


def _build_schedule_times_provider(default_schedule_time: str):
    """Read the latest SCHEDULE_TIMES with SCHEDULE_TIME fallback."""
    from src.core.config_manager import ConfigManager
    from src.scheduler import normalize_schedule_times

    _SYSTEM_DEFAULT_SCHEDULE_TIME = "18:00"
    manager = ConfigManager()

    def _provider():
        if "SCHEDULE_TIMES" in _INITIAL_PROCESS_ENV:
            return normalize_schedule_times(
                os.getenv("SCHEDULE_TIMES", ""),
                fallback_time=os.getenv("SCHEDULE_TIME", default_schedule_time),
            )
        if "SCHEDULE_TIME" in _INITIAL_PROCESS_ENV:
            return normalize_schedule_times(
                os.getenv("SCHEDULE_TIMES", ""),
                fallback_time=os.getenv("SCHEDULE_TIME", default_schedule_time),
            )

        config_map = manager.read_config_map()
        schedule_time = (config_map.get("SCHEDULE_TIME", "") or "").strip() or _SYSTEM_DEFAULT_SCHEDULE_TIME
        return normalize_schedule_times(
            config_map.get("SCHEDULE_TIMES", ""),
            fallback_time=schedule_time,
        )

    return _provider


def _coordinate_service_runtime(
    config: Config,
    args: argparse.Namespace,
) -> Tuple[bool, Optional[int]]:
    """Prepare and start the optional Web/API runtime."""

    # === Handle --webui / --webui-only Parameters, Map To --serve / --serve-only ===
    if args.webui:
        args.serve = True
    if args.webui_only:
        args.serve_only = True

    # Compatible with the old WEBUI_ENABLED environment variable.
    if config.webui_enabled and not (args.serve or args.serve_only):
        args.serve = True

    # === Start Web Service (if enabled) ===
    start_serve = (args.serve or args.serve_only) and os.getenv("GITHUB_ACTIONS") != "true"

    if start_serve:
        args.host, args.port = _resolve_web_service_bind(args, config)
        _warn_if_public_webui_without_auth(args.host)

    bot_clients_started = False
    if start_serve:
        from src.services.runtime_scheduler import (
            CLI_SCHEDULER_OWNER_ENV,
            RUNTIME_SCHEDULER_ARGS_ENV,
            RUNTIME_SCHEDULER_FORCE_ENABLED_ENV,
            RUNTIME_SCHEDULER_RUN_IMMEDIATELY_ENV,
            RUNTIME_SCHEDULER_SUPPRESS_START_ENV,
        )

        # The API runtime scheduler owns schedules once the Web/API service starts.
        # This keeps Web settings, status, and run-now actions attached to the real
        # scheduler instead of a separate CLI loop.
        os.environ.pop(CLI_SCHEDULER_OWNER_ENV, None)
        if args.serve_only:
            os.environ[RUNTIME_SCHEDULER_SUPPRESS_START_ENV] = "true"
        else:
            os.environ.pop(RUNTIME_SCHEDULER_SUPPRESS_START_ENV, None)
        runtime_schedule_requested = not args.serve_only and (
            args.schedule or config.schedule_enabled
        )
        if not args.serve_only and args.schedule:
            os.environ[RUNTIME_SCHEDULER_FORCE_ENABLED_ENV] = "true"
        else:
            os.environ.pop(RUNTIME_SCHEDULER_FORCE_ENABLED_ENV, None)
        if runtime_schedule_requested:
            runtime_run_immediately = config.schedule_run_immediately
            if getattr(args, 'no_run_immediately', False):
                runtime_run_immediately = False
            os.environ[RUNTIME_SCHEDULER_RUN_IMMEDIATELY_ENV] = (
                "true" if runtime_run_immediately else "false"
            )
        else:
            os.environ.pop(RUNTIME_SCHEDULER_RUN_IMMEDIATELY_ENV, None)
        os.environ[RUNTIME_SCHEDULER_ARGS_ENV] = json.dumps({
            "no_notify": bool(getattr(args, "no_notify", False)),
            "no_market_review": bool(getattr(args, "no_market_review", False)),
            "dry_run": bool(getattr(args, "dry_run", False)),
            "force_run": bool(getattr(args, "force_run", False)),
            "single_notify": bool(getattr(args, "single_notify", False)),
            "no_context_snapshot": bool(getattr(args, "no_context_snapshot", False)),
            "workers": getattr(args, "workers", None),
            "portfolio": getattr(args, "portfolio", None),
        })
        if not prepare_webui_frontend_assets():
            logger.warning(
                "Frontend assets are not ready; starting FastAPI without a usable Web page"
            )
        try:
            start_api_server(host=args.host, port=args.port, config=config)
            bot_clients_started = True
        except Exception as exc:  # broad-exception: fallback_recorded - preserve service-start fallback and logged CLI failure behavior
            log_safe_exception(
                logger,
                "FastAPI service startup failed",
                exc,
                error_code="main_fastapi_start_failed",
            )
            if args.serve_only:
                return start_serve, 1
            start_serve = False

    if bot_clients_started:
        start_bot_stream_clients(config)

    return start_serve, None


def _run_service_only_mode(args: argparse.Namespace) -> int:
    """Keep a serve-only process alive until interrupted."""

    logger.info("Mode: Web service only")
    logger.info("Web service running at http://%s:%s", args.host, args.port)
    logger.info("Trigger analysis through /api/v1/analysis/analyze")
    logger.info("API documentation: http://%s:%s/docs", args.host, args.port)
    logger.info("Press Ctrl+C to exit")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("\nInterrupted by the user; exiting")
    return 0


def _run_schedule_mode(
    config: Config,
    args: argparse.Namespace,
    stock_codes: Optional[List[str]],
    start_serve: bool,
) -> int:
    """Run either the API-owned or standalone CLI scheduler."""

    if start_serve:
        logger.info("Mode: Web/API runtime scheduler")
        logger.info("Web service running at http://%s:%s", args.host, args.port)
        logger.info(
            "The Web/API runtime scheduler owns scheduled runs; "
            "saved settings apply to this process"
        )
        logger.info("Press Ctrl+C to exit")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("\nInterrupted by the user; exiting")
        return 0

    logger.info("Mode: scheduled analysis")
    logger.info("Daily run time: %s", config.schedule_time)

    # Determine whether to run immediately:
    # Command line arg --no-run-immediately overrides config if present.
    # Otherwise use config (defaults to True).
    should_run_immediately = config.schedule_run_immediately
    if getattr(args, 'no_run_immediately', False):
        should_run_immediately = False

    logger.info("Run immediately at startup: %s", should_run_immediately)

    from src.scheduler import run_with_schedule
    scheduled_stock_codes = _resolve_scheduled_stock_codes(stock_codes)
    schedule_time_provider = _build_schedule_time_provider(config.schedule_time)
    schedule_times_provider = _build_schedule_times_provider(config.schedule_time)

    def scheduled_task():
        runtime_config = _reload_runtime_config()
        run_full_analysis(runtime_config, args, scheduled_stock_codes)

    background_tasks = []
    if getattr(config, 'agent_event_monitor_enabled', False):
        from src.services.alert_worker import AlertWorker

        interval_minutes = max(1, getattr(config, 'agent_event_monitor_interval_minutes', 5))
        alert_worker = AlertWorker(config_provider=_reload_runtime_config)

        def event_monitor_task():
            stats = alert_worker.run_once()
            triggered_count = stats.get("triggered", 0)
            if triggered_count:
                logger.info("[EventMonitor] Triggered %d alerts in this run", triggered_count)

        background_tasks.append({
            "task": event_monitor_task,
            "interval_seconds": interval_minutes * 60,
            "run_immediately": True,
            "name": "agent_event_monitor",
        })

    schedule_kwargs = {
        "task": scheduled_task,
        "schedule_time": config.schedule_time,
        "run_immediately": should_run_immediately,
        "background_tasks": background_tasks,
        "schedule_time_provider": schedule_time_provider,
    }
    if hasattr(config, "schedule_times"):
        schedule_kwargs["schedule_times"] = config.schedule_times
        schedule_kwargs["schedule_times_provider"] = schedule_times_provider
    run_with_schedule(**schedule_kwargs)
    return 0


def _keep_service_runtime_alive(
    start_serve: bool,
    args: argparse.Namespace,
    config: Config,
) -> None:
    """Keep a non-scheduled API process alive after one-shot analysis."""

    # If the service is enabled and not in scheduled task mode, keep the program running.
    keep_running = start_serve and not (args.schedule or config.schedule_enabled)
    if keep_running:
        logger.info("API service is running (press Ctrl+C to exit)")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
