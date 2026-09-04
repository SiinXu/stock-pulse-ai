# -*- coding: utf-8 -*-
"""Runtime scheduler service for long-lived API/Web/Desktop processes."""

from __future__ import annotations

import logging
import multiprocessing
import os
import signal
import subprocess
import threading
import _thread
import time
import uuid
from datetime import datetime, timezone, tzinfo
from functools import partial
from pathlib import Path
from queue import Empty
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional, Set
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.config import Config, get_config
from src.scheduler import Scheduler, normalize_schedule_times
from src.utils.sanitize import log_safe_exception, sanitize_exception_chain

logger = logging.getLogger(__name__)
CLI_SCHEDULER_OWNER_ENV = "DSA_CLI_SCHEDULER_OWNS_SCHEDULE"
RUNTIME_SCHEDULER_FORCE_ENABLED_ENV = "DSA_RUNTIME_SCHEDULER_FORCE_ENABLED"
RUNTIME_SCHEDULER_RUN_IMMEDIATELY_ENV = "DSA_RUNTIME_SCHEDULER_RUN_IMMEDIATELY"
RUNTIME_SCHEDULER_SUPPRESS_START_ENV = "DSA_RUNTIME_SCHEDULER_SUPPRESS_START"
RUNTIME_SCHEDULER_ARGS_ENV = "DSA_RUNTIME_SCHEDULER_ARGS"
RUNTIME_SCHEDULER_TIMEOUT_ENV = "DSA_RUNTIME_SCHEDULER_TIMEOUT_SECONDS"
DEFAULT_RUNTIME_SCHEDULER_TIMEOUT_SECONDS = 45 * 60
SCHEDULED_TASK_OWNER_ENV = "DSA_SCHEDULED_TASK_OWNER"
DESKTOP_MODE_ENV = "DSA_DESKTOP_MODE"
_RUNTIME_ANALYSIS_LOCK = threading.Lock()
SCHEDULE_ARGS_OVERRIDE_KEYS = {
    "no_notify",
    "no_market_review",
    "dry_run",
    "force_run",
    "single_notify",
    "no_context_snapshot",
    "workers",
    "portfolio",
}


def _utc_now_iso() -> str:
    """Return an unambiguous timestamp for runtime status events."""
    return datetime.now(timezone.utc).isoformat()


def _env_flag_enabled(name: str) -> bool:
    """Return True when the named process env flag is an explicit truthy value."""
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def resolve_scheduler_process_mode(
    *,
    owns_schedule: bool,
    attached: bool,
    desktop_mode: bool | None = None,
) -> str:
    """Return the authoritative four-state process mode for this process.

    Vocabulary (design #869):
    - ``serve+schedule``: long-lived Web/API process with the legacy day-batch attached
    - ``desktop``: Desktop process with the legacy day-batch attached
    - ``cli-schedule``: this process does not own the schedule (CLI ownership handoff)
    - ``not_attached``: this process could own the schedule but the legacy day-batch is not attached
      (for example when ``DSA_RUNTIME_SCHEDULER_SUPPRESS_START`` is set)

    Values are derived only from ownership, attachment, and Desktop env — never guessed.
    """
    if desktop_mode is None:
        desktop_mode = _env_flag_enabled(DESKTOP_MODE_ENV)
    if not owns_schedule:
        return "cli-schedule"
    if attached and desktop_mode:
        return "desktop"
    if attached:
        return "serve+schedule"
    return "not_attached"


def _resolve_schedule_timezone(
    configured_name: Optional[str] = None,
) -> tuple[tzinfo, str]:
    """Resolve the process-local timezone used by the schedule library."""
    candidates: List[str] = []
    if configured_name:
        candidates.append(configured_name)
    env_name = os.getenv("TZ", "").strip().lstrip(":")
    if env_name:
        candidates.append(env_name)
    try:
        localtime_path = str(Path("/etc/localtime").resolve())
        marker = "/zoneinfo/"
        if marker in localtime_path:
            candidates.append(localtime_path.split(marker, 1)[1])
    except OSError:
        pass

    for name in candidates:
        try:
            return ZoneInfo(name), name
        except (ValueError, ZoneInfoNotFoundError):
            continue

    local_now = datetime.now().astimezone()
    local_tz = local_now.tzinfo or timezone.utc
    label = (
        getattr(local_tz, "key", None)
        or local_now.tzname()
        or str(local_tz)
        or "UTC"
    )
    return local_tz, label


def run_with_global_analysis_lock(
    task_runner: Callable[[Config, Any, Optional[List[str]]], Any],
    config: Config,
    args: Any,
    stock_codes: Optional[List[str]] = None,
    *,
    blocking: bool = True,
) -> bool:
    """Execute a task while holding the shared runtime analysis lock."""
    if not _RUNTIME_ANALYSIS_LOCK.acquire(blocking=blocking):
        return False
    try:
        task_runner(config, args, stock_codes)
    finally:
        _RUNTIME_ANALYSIS_LOCK.release()
    return True


def _run_scheduled_analysis_process(
    result_queue: Any,
    stock_codes: Optional[List[str]],
    schedule_args_overrides: Dict[str, Any],
) -> None:
    """Run one analysis in a spawn-safe child process."""
    if os.name == "posix":
        try:
            os.setsid()
        except OSError:
            # Being a session leader already is equivalent to success. Any
            # other failure would make process-tree cleanup unsafe, so fail
            # before analysis can create descendants.
            if os.getsid(0) != os.getpid():
                raise
    service = RuntimeSchedulerService(schedule_args_overrides=schedule_args_overrides)
    run_id = str(uuid.uuid4())
    success = service._run_analysis_locked(stock_codes, run_id=run_id)
    result_queue.put({"success": success, "error": service._last_error})


def _posix_descendant_process_ids(root_pid: int) -> Set[int]:
    """Return a best-effort snapshot of descendants before the root exits."""
    try:
        completed = subprocess.run(
            ["ps", "-axo", "pid=,ppid="],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return set()

    children_by_parent: Dict[int, List[int]] = {}
    for line in completed.stdout.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        try:
            pid, parent_pid = (int(value) for value in parts)
        except ValueError:
            continue
        children_by_parent.setdefault(parent_pid, []).append(pid)

    descendants: Set[int] = set()
    pending = list(children_by_parent.get(root_pid, []))
    while pending:
        pid = pending.pop()
        if pid in descendants:
            continue
        descendants.add(pid)
        pending.extend(children_by_parent.get(pid, []))
    return descendants


def _terminate_analysis_process_tree(process: Any) -> None:
    """Stop an analysis worker and any descendants it created."""
    root_alive = process.is_alive()
    process_id = process.pid

    posix_process_groups: Set[int] = set()
    if os.name == "posix" and process_id:
        posix_process_groups.add(process_id)
        current_process_group = os.getpgrp()
        if root_alive:
            for descendant_pid in _posix_descendant_process_ids(process_id):
                try:
                    descendant_group = os.getpgid(descendant_pid)
                except ProcessLookupError:
                    continue
                if descendant_group != current_process_group:
                    posix_process_groups.add(descendant_group)

    try:
        if os.name == "posix" and process_id:
            for process_group in posix_process_groups:
                try:
                    os.killpg(process_group, signal.SIGTERM)
                except ProcessLookupError:
                    continue
            # The spawned worker calls setsid(), but stop/timeout can win the
            # race before that happens. In that window killpg(worker_pid, ...)
            # has no target, so also terminate the multiprocessing handle.
            if process.is_alive():
                process.terminate()
        elif os.name == "nt" and process_id:
            subprocess.run(
                ["taskkill", "/PID", str(process_id), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
        elif root_alive:
            process.terminate()
    except (OSError, subprocess.SubprocessError):
        if root_alive:
            process.terminate()

    process.join(2)
    if os.name == "posix" and process_id:
        remaining_process_groups: Set[int] = set()
        for process_group in posix_process_groups:
            try:
                os.killpg(process_group, 0)
            except ProcessLookupError:
                continue
            except PermissionError:
                pass
            remaining_process_groups.add(process_group)
        if not remaining_process_groups:
            return
    elif not process.is_alive():
        return

    try:
        if os.name == "posix" and process_id:
            for process_group in remaining_process_groups:
                try:
                    os.killpg(process_group, signal.SIGKILL)
                except ProcessLookupError:
                    continue
        else:
            process.kill()
    except (OSError, AttributeError):
        if process.is_alive():
            process.terminate()
    process.join(10)


def _agent_event_monitor_interval_seconds(config: Config) -> int:
    """Return the validated Event Monitor polling interval in seconds."""
    interval_minutes = getattr(config, "agent_event_monitor_interval_minutes", 5)
    try:
        interval_minutes = max(1, int(interval_minutes))
    except (TypeError, ValueError):  # pragma: no cover - defensive branch
        logger.warning(
            "Invalid AGENT_EVENT_MONITOR_INTERVAL_MINUTES=%r; use fallback 5",
            interval_minutes,
        )
        interval_minutes = 5
    return interval_minutes * 60


def build_agent_event_monitor_background_tasks(
    config: Config,
    *,
    config_provider: Callable[[], Config],
) -> List[Dict[str, Any]]:
    """Build scheduler background tasks used by the runtime scheduler."""
    if not getattr(config, "agent_event_monitor_enabled", False):
        return []

    from src.services.alert_worker import AlertWorker

    interval_seconds = _agent_event_monitor_interval_seconds(config)
    try:
        alert_worker = AlertWorker(config_provider=config_provider)
    except Exception as exc:  # broad-exception: fallback_recorded - isolate failure for sequential merge
        log_safe_exception(
            logger,
            "Event monitor alert worker initialization failed",
            exc,
            error_code="event_monitor_alert_worker_init_failed",
            level=logging.WARNING,
        )
        return []

    def event_monitor_task() -> None:
        stats = alert_worker.run_once()
        triggered_count = stats.get("triggered", 0)
        if triggered_count:
            logger.info("[EventMonitor] triggered %d alert(s)", triggered_count)

    return [{
        "task": event_monitor_task,
        "interval_seconds": interval_seconds,
        "run_immediately": True,
        "name": "agent_event_monitor",
    }]


def build_daily_brief_scheduler_background_tasks(
    config: Config,
    *,
    config_provider: Callable[[], Config],
) -> List[Dict[str, Any]]:
    """Build the config-gated daily brief background task (Issue #466 / #149)."""
    if not getattr(config, "daily_brief_enabled", False):
        return []
    try:
        from src.services.daily_brief_service import build_daily_brief_background_tasks

        return build_daily_brief_background_tasks(
            config,
            config_provider=config_provider,
        )
    except Exception as exc:  # broad-exception: fallback_recorded - isolate failure for sequential merge
        log_safe_exception(
            logger,
            "Daily brief background task initialization failed",
            exc,
            error_code="daily_brief_background_task_init_failed",
            level=logging.WARNING,
        )
        return []



def build_prediction_resolver_scheduler_background_tasks(
    config: Config,
    *,
    config_provider: Callable[[], Config],
) -> List[Dict[str, Any]]:
    """Build the config-gated prediction resolver background task (#1102 / #1116)."""
    if not getattr(config, "prediction_resolve_enabled", False):
        return []
    try:
        from src.services.prediction_resolver import (
            build_prediction_resolver_background_tasks,
        )

        return build_prediction_resolver_background_tasks(
            config,
            config_provider=config_provider,
        )
    except Exception as exc:  # broad-exception: fallback_recorded - isolate failure for sequential merge
        log_safe_exception(
            logger,
            "Prediction resolver background task initialization failed",
            exc,
            error_code="prediction_resolver_background_task_init_failed",
            level=logging.WARNING,
        )
        return []


def build_event_research_brief_scheduler_background_tasks(
    config: Config,
    *,
    config_provider: Callable[[], Config],
) -> List[Dict[str, Any]]:
    """Build the config-gated event research brief background task (#1131)."""
    if not getattr(config, "event_research_brief_enabled", False):
        return []
    try:
        from src.services.event_research_brief_service import (
            build_event_research_brief_background_tasks,
        )
        return build_event_research_brief_background_tasks(config, config_provider=config_provider)
    except Exception as exc:  # broad-exception: fallback_recorded - optional task does not block scheduler
        log_safe_exception(
            logger, "Event research brief background task initialization failed", exc,
            error_code="event_research_brief_background_task_init_failed", level=logging.WARNING,
        )
        return []


class RuntimeSchedulerService:
    """Manage scheduled analysis inside the current API/Web/Desktop process."""

    def __init__(
        self,
        *,
        config_provider: Callable[[], Config] = get_config,
        task_runner: Optional[Callable[[Config, Any, Optional[List[str]]], Any]] = None,
        owns_schedule: Optional[bool] = None,
        force_enabled: bool = False,
        run_immediately_in_background: bool = False,
        background_tasks_provider: Optional[Callable[[Config], List[Dict[str, Any]]]] = None,
        schedule_args_overrides: Optional[Dict[str, Any]] = None,
        scheduled_task_service: Any = None,
        personalized_schedule_enabled: bool = True,
        legacy_schedule_enabled: bool = True,
        schedule_timezone: Optional[str] = None,
    ) -> None:
        self._config_provider = config_provider
        self._task_runner = task_runner
        if owns_schedule is None:
            owns_schedule = os.getenv(CLI_SCHEDULER_OWNER_ENV, "").strip().lower() not in {
                "1",
                "true",
                "yes",
                "on",
            }
        self._owns_schedule = owns_schedule
        self._force_enabled = force_enabled
        self._run_immediately_in_background = run_immediately_in_background
        self._background_tasks_provider = background_tasks_provider
        self._scheduled_task_service = scheduled_task_service
        self._personalized_schedule_enabled = personalized_schedule_enabled
        self._legacy_schedule_enabled = legacy_schedule_enabled
        self._attached = bool(owns_schedule and legacy_schedule_enabled)
        desktop_mode = _env_flag_enabled(DESKTOP_MODE_ENV)
        self._process_mode = resolve_scheduler_process_mode(
            owns_schedule=self._owns_schedule,
            attached=self._attached,
            desktop_mode=desktop_mode,
        )
        self._schedule_tzinfo, self._schedule_timezone = _resolve_schedule_timezone(
            schedule_timezone,
        )
        self._schedule_args_overrides = {
            key: value
            for key, value in (schedule_args_overrides or {}).items()
            if key in SCHEDULE_ARGS_OVERRIDE_KEYS
        }
        self._background_task_cache: Dict[str, Dict[str, Any]] = {}
        self._background_task_registered_names: Set[str] = set()
        self._lock = threading.RLock()
        self._run_lock = _RUNTIME_ANALYSIS_LOCK
        self._scheduler: Optional[Scheduler] = None
        self._thread: Optional[threading.Thread] = None
        self._enabled = False
        self._legacy_enabled = False
        self._last_run_at: Optional[str] = None
        self._last_success_at: Optional[str] = None
        self._last_error: Optional[str] = None
        self._last_skipped_at: Optional[str] = None
        self._last_skip_reason: Optional[str] = None
        self._active_run_id: Optional[str] = None
        self._last_run_id: Optional[str] = None
        self._last_run_outcome: Optional[str] = None
        self._analysis_process_target = _run_scheduled_analysis_process
        self._analysis_process: Optional[Any] = None
        self._analysis_process_lock = threading.Lock()
        self._analysis_generation = 0

    def _make_schedule_args(self) -> SimpleNamespace:
        defaults = {
            "schedule": True,
            "no_run_immediately": True,
            "no_notify": False,
            "no_market_review": False,
            "dry_run": False,
            "force_run": False,
            "single_notify": False,
            "no_context_snapshot": False,
            "market_review": False,
            "serve": False,
            "serve_only": True,
            "stocks": None,
            "portfolio": None,
            "workers": None,
        }
        defaults.update(self._schedule_args_overrides)
        return SimpleNamespace(**defaults)

    def _reload_config(self) -> Config:
        from main import _reload_runtime_config

        return _reload_runtime_config()

    def _record_analysis_busy_skip(self) -> None:
        with self._lock:
            self._last_skipped_at = _utc_now_iso()
            self._last_skip_reason = "analysis_already_running"
        logger.warning("Runtime scheduler skipped run: analysis already running")

    def _begin_run(self, run_id: str, *, started_at: Optional[str] = None) -> str:
        started_at = started_at or _utc_now_iso()
        with self._lock:
            self._active_run_id = run_id
            self._last_run_at = started_at
        return started_at

    def _finish_run(self, run_id: str, *, succeeded: bool) -> None:
        with self._lock:
            if self._active_run_id == run_id:
                self._active_run_id = None
            self._last_run_id = run_id
            self._last_run_outcome = "succeeded" if succeeded else "failed"

    def _run_analysis_locked(
        self,
        stock_codes: Optional[List[str]],
        *,
        run_id: str,
    ) -> bool:
        succeeded = False
        try:
            config = self._reload_config()
            runner = self._task_runner
            if runner is None:
                from main import run_scheduled_analysis

                runner = run_scheduled_analysis
            result = runner(config, self._make_schedule_args(), stock_codes)
            if result is False:
                raise RuntimeError("runtime scheduled analysis reported failure")
            with self._lock:
                self._last_success_at = _utc_now_iso()
                self._last_error = None
            succeeded = True
        except Exception as exc:  # broad-exception: fallback_recorded - isolate failure for sequential merge
            with self._lock:
                self._last_error = sanitize_exception_chain(exc)
            log_safe_exception(
                logger,
                "Runtime scheduled analysis failed",
                exc,
                error_code="runtime_scheduled_analysis_failed",
            )
        finally:
            self._finish_run(run_id, succeeded=succeeded)
        return succeeded

    def _run_analysis_once(self, stock_codes: Optional[List[str]] = None) -> bool:
        if not self._run_lock.acquire(blocking=False):
            self._record_analysis_busy_skip()
            return False
        run_id = str(uuid.uuid4())
        started_at = self._begin_run(run_id)
        try:
            self._run_analysis_locked(
                stock_codes,
                run_id=run_id,
            )
        finally:
            self._run_lock.release()
        return True

    def _analysis_timeout_seconds(self) -> int:
        """Read the current process env timeout; invalid values use the default."""
        try:
            value = os.getenv(
                RUNTIME_SCHEDULER_TIMEOUT_ENV,
                str(DEFAULT_RUNTIME_SCHEDULER_TIMEOUT_SECONDS),
            )
            return max(60, int(value))
        except (TypeError, ValueError):
            logger.warning(
                "Invalid %s; using %ss",
                RUNTIME_SCHEDULER_TIMEOUT_ENV,
                DEFAULT_RUNTIME_SCHEDULER_TIMEOUT_SECONDS,
            )
            return DEFAULT_RUNTIME_SCHEDULER_TIMEOUT_SECONDS

    def _record_watchdog_outcome(
        self,
        run_id: str,
        generation: int,
        *,
        succeeded: bool,
        error: Optional[str] = None,
    ) -> bool:
        """Record a watchdog outcome unless stop() advanced the generation fence."""
        with self._lock:
            with self._analysis_process_lock:
                if generation != self._analysis_generation:
                    if self._active_run_id == run_id:
                        self._active_run_id = None
                    return False
                if succeeded:
                    self._last_success_at = _utc_now_iso()
                    self._last_error = None
                else:
                    self._last_error = error or "runtime scheduled analysis failed"
                if self._active_run_id == run_id:
                    self._active_run_id = None
                self._last_run_id = run_id
                self._last_run_outcome = "succeeded" if succeeded else "failed"
                return True

    def _run_analysis_with_watchdog(
        self,
        stock_codes: Optional[List[str]] = None,
        *,
        lock_held: bool = False,
        generation: Optional[int] = None,
        run_id: Optional[str] = None,
        started_at: Optional[str] = None,
    ) -> None:
        if not lock_held and not self._run_lock.acquire(blocking=False):
            self._record_analysis_busy_skip()
            return
        if generation is None:
            with self._analysis_process_lock:
                generation = self._analysis_generation
        if run_id is None:
            run_id = str(uuid.uuid4())
            started_at = self._begin_run(run_id, started_at=started_at)

        result_queue = None
        process: Optional[Any] = None
        try:
            context = multiprocessing.get_context("spawn")
            result_queue = context.Queue()
            process = context.Process(
                target=self._analysis_process_target,
                args=(result_queue, stock_codes, dict(self._schedule_args_overrides)),
                name="runtime-scheduled-analysis",
            )
            timeout = self._analysis_timeout_seconds()
            with self._lock:
                with self._analysis_process_lock:
                    if generation != self._analysis_generation:
                        if self._active_run_id == run_id:
                            self._active_run_id = None
                        return
                    process.start()
                    self._analysis_process = process
                    self._active_run_id = run_id
                    self._last_run_at = started_at or _utc_now_iso()

            result = None
            deadline = time.monotonic() + timeout
            while result is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    result = result_queue.get(timeout=min(0.2, remaining))
                except Empty:
                    if not process.is_alive():
                        deadline = min(deadline, time.monotonic() + 2)

            if result is None and process.is_alive():
                logger.error(
                    "Runtime scheduled analysis exceeded %ss; terminating worker",
                    timeout,
                )
                _terminate_analysis_process_tree(process)
                self._record_watchdog_outcome(
                    run_id,
                    generation,
                    succeeded=False,
                    error=f"runtime scheduled analysis timed out after {timeout}s",
                )
                return

            if result is None:
                exit_code = process.exitcode
                _terminate_analysis_process_tree(process)
                self._record_watchdog_outcome(
                    run_id,
                    generation,
                    succeeded=False,
                    error=(
                        "runtime scheduled analysis worker exited without a result "
                        f"(exit code {exit_code})"
                    ),
                )
                return

            process.join(2)
            if process.is_alive():
                _terminate_analysis_process_tree(process)
                self._record_watchdog_outcome(
                    run_id,
                    generation,
                    succeeded=False,
                    error="runtime scheduled analysis worker did not exit",
                )
                return

            if result.get("success"):
                self._record_watchdog_outcome(run_id, generation, succeeded=True)
            else:
                self._record_watchdog_outcome(
                    run_id,
                    generation,
                    succeeded=False,
                    error=result.get("error") or "runtime scheduled analysis failed",
                )
        except Exception as exc:  # broad-exception: fallback_recorded - watchdog must release the scheduler
            self._record_watchdog_outcome(
                run_id,
                generation,
                succeeded=False,
                error=sanitize_exception_chain(exc),
            )
            log_safe_exception(
                logger,
                "Runtime scheduler watchdog failed",
                exc,
                error_code="runtime_scheduler_watchdog_failed",
            )
        finally:
            self._run_lock.release()
            if process is not None:
                with self._analysis_process_lock:
                    if self._analysis_process is process:
                        self._analysis_process = None
            if result_queue is not None:
                result_queue.cancel_join_thread()
                result_queue.close()

    def _start_analysis_watchdog(
        self,
        stock_codes: Optional[List[str]] = None,
        *,
        generation: Optional[int] = None,
        run_id: Optional[str] = None,
        started_at: Optional[str] = None,
    ) -> bool:
        with self._analysis_process_lock:
            current_generation = self._analysis_generation
            if generation is not None and generation != current_generation:
                return False
            generation = current_generation
        if not self._run_lock.acquire(blocking=False):
            self._record_analysis_busy_skip()
            return False
        run_id = run_id or str(uuid.uuid4())
        started_at = self._begin_run(run_id, started_at=started_at)
        worker = threading.Thread(
            target=lambda: self._run_analysis_with_watchdog(
                stock_codes,
                lock_held=True,
                generation=generation,
                run_id=run_id,
                started_at=started_at,
            ),
            daemon=True,
            name="runtime-scheduler-watchdog",
        )
        try:
            worker.start()
        except Exception as exc:  # broad-exception: fallback_recorded - isolate failure for sequential merge
            log_safe_exception(
                logger,
                "Runtime scheduler watchdog thread failed to start",
                exc,
                error_code="runtime_scheduler_watchdog_start_failed",
                level=logging.WARNING,
            )
            with self._lock:
                self._last_error = sanitize_exception_chain(exc)
            self._finish_run(run_id, succeeded=False)
            self._run_lock.release()
            raise
        return True

    def _current_times(self) -> List[str]:
        config = self._config_provider()
        return normalize_schedule_times(
            getattr(config, "schedule_times", None),
            fallback_time=getattr(config, "schedule_time", "18:00"),
        )

    def _is_schedule_enabled(
        self,
        config: Config,
        *,
        include_legacy: bool = True,
    ) -> bool:
        return (include_legacy and self._is_legacy_schedule_enabled(config)) or (
            self._scheduled_task_service is not None
            and self._personalized_schedule_enabled
        )

    def _is_legacy_schedule_enabled(self, config: Config) -> bool:
        return self._legacy_schedule_enabled and (
            self._force_enabled
            or bool(getattr(config, "schedule_enabled", False))
        )

    def _current_background_tasks(self, config: Config) -> List[Dict[str, Any]]:
        if self._background_tasks_provider is not None:
            tasks = list(self._background_tasks_provider(config))
        else:
            tasks = self._current_agent_event_monitor_background_tasks(config)
            tasks.extend(self._current_daily_brief_background_tasks(config))
            tasks.extend(self._current_event_research_brief_background_tasks(config))
            tasks.extend(self._current_prediction_resolver_background_tasks(config))
        if self._scheduled_task_service is not None and self._personalized_schedule_enabled:
            from src.schemas.scheduled_task import SCHEDULED_TASK_POLL_INTERVAL_SECONDS

            tasks.append({
                "task": self._scheduled_task_service.tick,
                "interval_seconds": SCHEDULED_TASK_POLL_INTERVAL_SECONDS,
                "run_immediately": True,
                "name": "scheduled_tasks",
            })
        return tasks

    def _current_agent_event_monitor_background_tasks(self, config: Config) -> List[Dict[str, Any]]:
        name = "agent_event_monitor"
        if not getattr(config, "agent_event_monitor_enabled", False):
            self._background_task_cache.pop(name, None)
            self._background_task_registered_names.discard(name)
            return []

        cached = self._background_task_cache.get(name)
        if cached is None:
            entries = build_agent_event_monitor_background_tasks(
                config,
                config_provider=self._reload_config,
            )
            if not entries:
                self._background_task_cache.pop(name, None)
                self._background_task_registered_names.discard(name)
                return []
            cached = dict(entries[0])
            cached["name"] = name
            self._background_task_cache[name] = cached
            interval_seconds = int(cached["interval_seconds"])
        else:
            interval_seconds = _agent_event_monitor_interval_seconds(config)

        run_immediately = (
            bool(cached.get("run_immediately", False))
            and name not in self._background_task_registered_names
        )
        self._background_task_registered_names.add(name)
        return [{
            "task": cached["task"],
            "interval_seconds": interval_seconds,
            "run_immediately": run_immediately,
            "name": name,
        }]

    def _current_daily_brief_background_tasks(self, config: Config) -> List[Dict[str, Any]]:
        name = "daily_brief"
        if not getattr(config, "daily_brief_enabled", False):
            self._background_task_cache.pop(name, None)
            self._background_task_registered_names.discard(name)
            return []

        cached = self._background_task_cache.get(name)
        if cached is None:
            entries = build_daily_brief_scheduler_background_tasks(
                config,
                config_provider=self._reload_config,
            )
            if not entries:
                self._background_task_cache.pop(name, None)
                self._background_task_registered_names.discard(name)
                return []
            cached = dict(entries[0])
            cached["name"] = name
            self._background_task_cache[name] = cached
            interval_seconds = int(cached["interval_seconds"])
        else:
            from src.services.daily_brief_service import DAILY_BRIEF_POLL_INTERVAL_SECONDS

            interval_seconds = int(DAILY_BRIEF_POLL_INTERVAL_SECONDS)

        run_immediately = (
            bool(cached.get("run_immediately", False))
            and name not in self._background_task_registered_names
        )
        self._background_task_registered_names.add(name)
        return [{
            "task": cached["task"],
            "interval_seconds": interval_seconds,
            "run_immediately": run_immediately,
            "name": name,
        }]

    def _current_event_research_brief_background_tasks(
        self,
        config: Config,
    ) -> List[Dict[str, Any]]:
        name = "event_research_brief"
        if not getattr(config, "event_research_brief_enabled", False):
            self._background_task_cache.pop(name, None)
            self._background_task_registered_names.discard(name)
            return []

        cached = self._background_task_cache.get(name)
        if cached is None:
            entries = build_event_research_brief_scheduler_background_tasks(
                config,
                config_provider=self._reload_config,
            )
            if not entries:
                self._background_task_cache.pop(name, None)
                self._background_task_registered_names.discard(name)
                return []
            cached = dict(entries[0])
            cached["name"] = name
            self._background_task_cache[name] = cached
            interval_seconds = int(cached["interval_seconds"])
        else:
            from src.services.event_research_brief_service import (
                EVENT_RESEARCH_BRIEF_POLL_INTERVAL_SECONDS,
            )

            interval_seconds = int(EVENT_RESEARCH_BRIEF_POLL_INTERVAL_SECONDS)

        run_immediately = (
            bool(cached.get("run_immediately", False))
            and name not in self._background_task_registered_names
        )
        self._background_task_registered_names.add(name)
        return [{
            "task": cached["task"],
            "interval_seconds": interval_seconds,
            "run_immediately": run_immediately,
            "name": name,
        }]

    def _current_prediction_resolver_background_tasks(self, config: Config) -> List[Dict[str, Any]]:
        name = "prediction_resolver"
        if not getattr(config, "prediction_resolve_enabled", False):
            self._background_task_cache.pop(name, None)
            self._background_task_registered_names.discard(name)
            return []

        cached = self._background_task_cache.get(name)
        if cached is None:
            entries = build_prediction_resolver_scheduler_background_tasks(
                config,
                config_provider=self._reload_config,
            )
            if not entries:
                self._background_task_cache.pop(name, None)
                self._background_task_registered_names.discard(name)
                return []
            cached = dict(entries[0])
            cached["name"] = name
            self._background_task_cache[name] = cached
            interval_seconds = int(cached["interval_seconds"])
        else:
            from src.services.prediction_resolver import (
                PREDICTION_RESOLVER_DEFAULT_INTERVAL_SECONDS,
            )

            try:
                interval_seconds = int(
                    getattr(
                        config,
                        "prediction_resolve_interval_seconds",
                        PREDICTION_RESOLVER_DEFAULT_INTERVAL_SECONDS,
                    )
                )
            except (TypeError, ValueError):
                interval_seconds = int(PREDICTION_RESOLVER_DEFAULT_INTERVAL_SECONDS)
            interval_seconds = max(30, interval_seconds)

        run_immediately = (
            bool(cached.get("run_immediately", False))
            and name not in self._background_task_registered_names
        )
        self._background_task_registered_names.add(name)
        return [{
            "task": cached["task"],
            "interval_seconds": interval_seconds,
            "run_immediately": run_immediately,
            "name": name,
        }]

    @staticmethod
    def _run_in_background_thread(target: Callable[[], None]) -> None:
        """Run a callback in a background thread without blocking startup."""
        try:
            _thread.start_new_thread(target, ())
            return
        except Exception as exc:  # broad-exception: fallback_recorded - isolate failure for sequential merge
            log_safe_exception(logger, 'operation failed', exc, error_code='internal_error', level=logging.WARNING)
            # Best-effort fallback for environments where the low-level thread API
            # is unavailable or restricted.
            thread = threading.Thread(target=target, daemon=True)
            thread.start()

    def start(
        self,
        *,
        run_immediately: bool = False,
        include_legacy: bool = True,
    ) -> None:
        with self._lock:
            if not self._owns_schedule:
                self.stop()
                return
            config = self._config_provider()
            if not self._is_schedule_enabled(
                config,
                include_legacy=include_legacy,
            ):
                self.stop()
                return
            background_tasks = self._current_background_tasks(config)
            legacy_enabled = (
                include_legacy and self._is_legacy_schedule_enabled(config)
            )
            self.stop()
            with self._analysis_process_lock:
                generation = self._analysis_generation
            scheduled_analysis = partial(
                self._start_analysis_watchdog,
                generation=generation,
            )
            times = normalize_schedule_times(
                getattr(config, "schedule_times", None),
                fallback_time=getattr(config, "schedule_time", "18:00"),
            )
            scheduler = Scheduler(
                schedule_time=getattr(config, "schedule_time", "18:00"),
                schedule_times=times,
                schedule_times_provider=self._current_times,
                register_signals=False,
            )
            if legacy_enabled:
                if run_immediately and self._run_immediately_in_background:
                    scheduler.set_daily_task(scheduled_analysis, run_immediately=False)
                else:
                    scheduler.set_daily_task(
                        scheduled_analysis,
                        run_immediately=run_immediately,
                    )
            for entry in background_tasks:
                scheduler.add_background_task(
                    entry["task"],
                    interval_seconds=entry["interval_seconds"],
                    run_immediately=entry.get("run_immediately", False),
                    name=entry.get("name"),
                )
            if legacy_enabled and run_immediately and self._run_immediately_in_background:
                self._run_in_background_thread(scheduled_analysis)
            thread = threading.Thread(
                target=scheduler.run,
                daemon=True,
                name="runtime-scheduler",
            )
            self._scheduler = scheduler
            self._thread = thread
            self._enabled = True
            self._legacy_enabled = legacy_enabled
            thread.start()

    def stop(self) -> None:
        with self._lock:
            with self._analysis_process_lock:
                self._analysis_generation += 1
                process = self._analysis_process
                self._analysis_process = None
            scheduler = self._scheduler
            if scheduler is not None:
                scheduler.stop()
            if process is not None:
                _terminate_analysis_process_tree(process)
            self._scheduler = None
            self._thread = None
            self._enabled = False
            self._legacy_enabled = False

    def reconcile_from_config(
        self,
        *,
        run_immediately: bool = False,
        clear_enabled_override: bool = False,
        include_legacy: bool = True,
        refresh_background_tasks: Optional[Set[str]] = None,
    ) -> None:
        if clear_enabled_override:
            self._force_enabled = False
        for name in refresh_background_tasks or ():
            self._background_task_cache.pop(name, None)
            self._background_task_registered_names.discard(name)
        if not self._owns_schedule:
            self.stop()
            return
        config = self._config_provider()
        if self._is_schedule_enabled(config, include_legacy=include_legacy):
            self.start(
                run_immediately=run_immediately,
                include_legacy=include_legacy,
            )
        else:
            self.stop()

    def reconcile_scheduled_tasks(self) -> None:
        """Ensure the configured owner loop is running after a persisted mutation."""
        if not self._owns_schedule:
            self.stop()
            return
        if (
            self._scheduled_task_service is None
            or not self._personalized_schedule_enabled
        ):
            return
        if not self._enabled:
            self.start(run_immediately=False, include_legacy=False)

    def _run_now_block_reason(self) -> Optional[str]:
        if not self._attached:
            return "scheduler_not_attached"
        try:
            if not self._is_legacy_schedule_enabled(self._config_provider()):
                return "scheduler_disabled"
        except Exception as exc:  # broad-exception: fallback_recorded - status must fail closed
            log_safe_exception(
                logger,
                "Runtime scheduler configuration lookup failed",
                exc,
                error_code="runtime_scheduler_config_unavailable",
                level=logging.WARNING,
            )
            return "scheduler_state_unavailable"
        if self._run_lock.locked():
            return "analysis_already_running"
        return None

    def run_now(self) -> Dict[str, Any]:
        block_reason = self._run_now_block_reason()
        if block_reason is not None and block_reason != "analysis_already_running":
            return {
                "accepted": False,
                "running": self._run_lock.locked(),
                "reason": block_reason,
            }
        run_id = str(uuid.uuid4())
        started_at = _utc_now_iso()
        if not self._start_analysis_watchdog(run_id=run_id, started_at=started_at):
            return {
                "accepted": False,
                "running": True,
                "reason": "analysis_already_running",
            }
        return {
            "accepted": True,
            "running": True,
            "run_id": run_id,
            "started_at": started_at,
        }

    def has_registered_background_task(self, name: str) -> bool:
        """Return whether this process already registered ``name``.

        Cache-only: never constructs, starts, or reconciles background tasks.
        A missing name, a never-started scheduler, or an empty registration
        set all return False. This bit is this API process only and is not
        global worker health.
        """
        canonical = str(name or "").strip()
        if not canonical:
            return False
        return canonical in self._background_task_registered_names

    def status(self) -> Dict[str, Any]:
        scheduler = self._scheduler
        jobs = scheduler.schedule.get_jobs() if scheduler is not None else []
        next_run = None
        if jobs:
            next_run_value = min(job.next_run for job in jobs)
            if next_run_value.tzinfo is None:
                next_run_value = next_run_value.replace(tzinfo=self._schedule_tzinfo)
            next_run = next_run_value.isoformat()
        if scheduler is not None:
            schedule_times = list(getattr(scheduler, "schedule_times", []))
        else:
            try:
                schedule_times = self._current_times()
            except Exception as exc:  # broad-exception: fallback_recorded - isolate failure for sequential merge
                log_safe_exception(logger, 'operation failed', exc, error_code='internal_error', level=logging.WARNING)
                schedule_times = []
        running = self._run_lock.locked()
        run_now_block_reason = self._run_now_block_reason()
        with self._lock:
            runtime_details = {
                "last_run_at": self._last_run_at,
                "last_success_at": self._last_success_at,
                "last_error": self._last_error,
                "last_skipped_at": self._last_skipped_at,
                "last_skip_reason": self._last_skip_reason,
                "active_run_id": self._active_run_id,
                "last_run_id": self._last_run_id,
                "last_run_outcome": self._last_run_outcome,
            }
        return {
            "track": "legacy_day_batch",
            "enabled": self._legacy_enabled,
            "running": running,
            "attached": self._attached,
            "process_mode": self._process_mode,
            "schedule_timezone": self._schedule_timezone,
            "run_now_available": run_now_block_reason is None,
            "run_now_block_reason": run_now_block_reason,
            "schedule_times": schedule_times,
            "next_run_at": next_run,
            **runtime_details,
        }
