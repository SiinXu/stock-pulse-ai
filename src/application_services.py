"""Lightweight application composition root.

`ApplicationServices` owns the process-wide service singletons so that the
startup layer holds them in one place and tests can inject isolated instances.

Design notes:
- Each service defaults to the module's existing accessor
  (``get_config``, ``DatabaseManager.get_instance``,
  ``get_search_service``, ``get_task_queue``). A default composition root is a
  transparent pass-through: behaviour is identical to calling the accessor
  directly, and it never caches, so it always reflects the current singleton.
- Tests (or the startup layer) may construct an ``ApplicationServices`` with
  explicit instances to obtain isolation; only the provided instances are held.
- Imports are performed lazily inside the properties to avoid import cycles at
  module load time.
- Plugin composition starts only after the root is installed. Built-ins supplied
  by the composition caller are registered first, then an explicitly configured
  external directory is scanned, and the resulting snapshot is loaded with
  per-plugin fault isolation. The root-owned Analysis Strategy catalog and
  Notification Channel adapter registry are bound into that same manager and
  consumed by their existing runtimes.

Only the singletons that actually exist in this codebase are held: Config,
DatabaseManager, SearchService, AnalysisTaskQueue, the process plugin manager,
its Analysis Strategy catalog, and its Notification Channel adapter registry.
There is no process-wide cache, auth rate limiter or shared thread pool singleton
to own, so none is invented here (thread pools are owned per-pipeline /
per-queue instance).
``system_config_service`` is already composed in the FastAPI lifespan
(``api/app.py``) and keeps its app-scoped lifecycle; this root does not modify
or take over ``system_config_service.py``.
"""

from __future__ import annotations

import atexit
import logging
import os
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterable, Iterator, Optional

from src.plugins.constants import PLUGIN_APPLICATION_VERSION
from src.utils.sanitize import log_safe_exception


logger = logging.getLogger(__name__)

if TYPE_CHECKING:  # import for typing only; avoids runtime import cycles
    from src.config import Config
    from src.plugins import (
        AnalysisStrategyCatalogSnapshot,
        AnalysisStrategyRegistry,
        ExternalPluginResult,
        NotificationChannelRegistry,
        Plugin,
        PluginManager,
        PluginOperationResult,
    )
    from src.search_service import SearchService
    from src.services.task_queue import AnalysisTaskQueue
    from src.storage import DatabaseManager


def _get_process_agent_tool_registry():
    """Resolve the cached Agent ToolRegistry only when a plugin needs it."""

    from src.agent.runtime_assembly import get_tool_registry

    return get_tool_registry()


def _get_declarative_analysis_strategy_names(config: "Config") -> tuple[str, ...]:
    """Resolve the current built-in/custom names without reading plugin state."""

    from src.agent.runtime_assembly import build_declarative_skill_manager

    return tuple(
        skill.name for skill in build_declarative_skill_manager(config).list_skills()
    )


class ApplicationServices:
    """Composition root holding process-wide service singletons.

    A field left as ``None`` is resolved lazily from its existing accessor on
    access; a field supplied explicitly is returned as-is (isolation for tests
    and the startup layer).
    """

    def __init__(
        self,
        *,
        config: Optional["Config"] = None,
        database: Optional["DatabaseManager"] = None,
        search: Optional["SearchService"] = None,
        task_queue: Optional["AnalysisTaskQueue"] = None,
        plugin_manager: Optional["PluginManager"] = None,
        analysis_strategy_registry: Optional[
            "AnalysisStrategyRegistry"
        ] = None,
        notification_channel_registry: Optional[
            "NotificationChannelRegistry"
        ] = None,
        builtin_plugins: Optional[Iterable["Plugin"]] = None,
        plugins_dir: str | Path | None = None,
        plugin_application_version: str = PLUGIN_APPLICATION_VERSION,
    ) -> None:
        self._config = config
        self._database = database
        self._search = search
        self._task_queue = task_queue
        from src.plugins import (
            AnalysisStrategyRegistry,
            NotificationChannelRegistry,
        )

        if (
            analysis_strategy_registry is not None
            and not isinstance(analysis_strategy_registry, AnalysisStrategyRegistry)
        ):
            raise TypeError("analysis strategy registry is invalid")
        if notification_channel_registry is not None and not isinstance(
            notification_channel_registry,
            NotificationChannelRegistry,
        ):
            raise TypeError("notification channel registry is invalid")
        plugin_manager_was_provided = plugin_manager is not None
        if plugin_manager is None:
            from src.plugins import (
                PluginManager,
                build_analysis_strategy_extension_contract,
                build_application_extension_registry,
                build_notification_channel_extension_contract,
            )

            if analysis_strategy_registry is None:
                analysis_strategy_registry = AnalysisStrategyRegistry(
                    lambda: _get_declarative_analysis_strategy_names(self.config)
                )
            if notification_channel_registry is None:
                notification_channel_registry = NotificationChannelRegistry(
                    lambda: self.config
                )
            plugin_manager = PluginManager(
                application_version=plugin_application_version,
                registry=build_application_extension_registry(
                    _get_process_agent_tool_registry,
                    additional_contracts={
                        "analysis_strategy": (
                            build_analysis_strategy_extension_contract(
                                analysis_strategy_registry
                            )
                        ),
                        "notification_channel": (
                            build_notification_channel_extension_contract(
                                notification_channel_registry
                            )
                        ),
                    },
                ),
            )
        else:
            configured_backend = plugin_manager.registry.native_backend(
                "analysis_strategy"
            )
            if analysis_strategy_registry is None:
                if isinstance(configured_backend, AnalysisStrategyRegistry):
                    analysis_strategy_registry = configured_backend
                elif configured_backend is not None:
                    raise TypeError(
                        "plugin manager uses an unsupported analysis strategy backend"
                    )
            elif configured_backend is not analysis_strategy_registry:
                raise ValueError(
                    "plugin manager and analysis strategy registry must be paired"
                )
            configured_backend = plugin_manager.registry.native_backend(
                "notification_channel"
            )
            if notification_channel_registry is None:
                if isinstance(configured_backend, NotificationChannelRegistry):
                    notification_channel_registry = configured_backend
                elif configured_backend is not None:
                    raise TypeError(
                        "plugin manager uses an unsupported notification channel backend"
                    )
                else:
                    notification_channel_registry = NotificationChannelRegistry(
                        lambda: self.config
                    )
            elif configured_backend is not notification_channel_registry:
                raise ValueError(
                    "plugin manager and notification channel registry must be paired"
                )
        if (
            notification_channel_registry is not None
            and self._config is not None
            and notification_channel_registry.config_snapshot() is not self._config
        ):
            raise ValueError(
                "notification channel registry and application Config must be paired"
            )
        self._plugin_manager = plugin_manager
        self._analysis_strategy_registry = analysis_strategy_registry
        self._analysis_strategy_catalog_token = object()
        self._notification_channel_registry = notification_channel_registry
        if builtin_plugins is None and not plugin_manager_was_provided:
            from src.plugins.builtin import get_configured_builtin_plugins

            builtin_plugins = get_configured_builtin_plugins(config)
        self._builtin_plugins = tuple(builtin_plugins or ())
        self._plugins_dir = plugins_dir
        self._builtin_plugin_results: tuple["PluginOperationResult", ...] = ()
        self._external_plugin_results: tuple["ExternalPluginResult", ...] = ()
        self._plugin_load_results: tuple["PluginOperationResult", ...] = ()
        self._plugin_shutdown_results: tuple["PluginOperationResult", ...] = ()
        self._plugin_lifecycle_lock = threading.RLock()
        self._local_lifecycle_ops = 0
        self._local_close_requested = False
        self._plugins_starting = False
        self._plugins_started = False
        self._plugin_close_requested = False
        self._plugins_closed = False
        self._notification_dispatch_condition = threading.Condition(
            threading.RLock()
        )
        self._notification_dispatch_count = 0
        self._notification_dispatch_state = threading.local()
        self._notification_writer_owner: int | None = None
        self._notification_writer_reservations = 0
        self._notification_transition_reservations = 0
        self._deferred_notification_lifecycle: list[Callable[[], Any]] = []
        self._plugin_manager._bind_lifecycle_boundary(
            self._run_plugin_manager_lifecycle,
            self._plugin_activation_allowed,
            self._run_plugin_disable_lifecycle,
        )

    @property
    def config(self) -> "Config":
        if self._config is not None:
            return self._config
        from src.config import get_config

        return get_config()

    @property
    def database(self) -> "DatabaseManager":
        if self._database is not None:
            return self._database
        from src.storage import DatabaseManager

        return DatabaseManager.get_instance()

    @property
    def search(self) -> "SearchService":
        if self._search is not None:
            return self._search
        from src.search_service import get_search_service

        return get_search_service()

    @property
    def task_queue(self) -> "AnalysisTaskQueue":
        if self._task_queue is not None:
            return self._task_queue
        from src.services.task_queue import get_task_queue

        return get_task_queue()

    @property
    def plugin_manager(self) -> "PluginManager":
        """Return the process plugin lifecycle and registration authority."""

        return self._plugin_manager

    @property
    def analysis_strategy_registry(self) -> Optional["AnalysisStrategyRegistry"]:
        """Return the paired plugin Skill snapshot authority when configured."""

        return self._analysis_strategy_registry

    def analysis_strategy_snapshot(self) -> "AnalysisStrategyCatalogSnapshot":
        """Return one registry/native generation without a partial transition."""

        if self._analysis_strategy_registry is None:
            from src.plugins import AnalysisStrategyCatalogSnapshot

            return AnalysisStrategyCatalogSnapshot(
                catalog_token=self._analysis_strategy_catalog_token,
                generation=0,
                registrations=(),
            )
        while True:
            generation = self._analysis_strategy_registry.generation
            registrations = self._plugin_manager.registrations(
                "analysis_strategy"
            )
            snapshot = self._analysis_strategy_registry.snapshot(registrations)
            if (
                snapshot.generation == generation
                and self._analysis_strategy_registry.generation == generation
            ):
                return snapshot

    @property
    def notification_channel_registry(
        self,
    ) -> Optional["NotificationChannelRegistry"]:
        """Return the paired notification adapter authority when configured."""

        return self._notification_channel_registry

    @contextmanager
    def notification_dispatch(self) -> Iterator[None]:
        """Protect one complete notification adapter snapshot from unload."""

        thread_id = threading.get_ident()
        condition = self._notification_dispatch_condition
        with condition:
            depth = getattr(self._notification_dispatch_state, "depth", 0)
            if self._notification_writer_owner == thread_id:
                raise RuntimeError(
                    "notification dispatch is unavailable during plugin unload"
                )
            if depth == 0:
                while (
                    self._notification_writer_owner is not None
                    or self._notification_writer_reservations
                ):
                    condition.wait()
            self._notification_dispatch_count += 1
            self._notification_dispatch_state.depth = depth + 1

        try:
            yield
        finally:
            callbacks: tuple[Callable[[], Any], ...] = ()
            with condition:
                depth = getattr(self._notification_dispatch_state, "depth", 1)
                self._notification_dispatch_state.depth = max(0, depth - 1)
                self._notification_dispatch_count -= 1
                if self._notification_dispatch_count == 0:
                    if (
                        self._notification_writer_owner is None
                        and self._notification_transition_reservations == 0
                    ):
                        callbacks = tuple(
                            self._deferred_notification_lifecycle
                        )
                        self._deferred_notification_lifecycle.clear()
                    condition.notify_all()
            self._run_deferred_notification_lifecycle(callbacks)

    def _run_deferred_notification_lifecycle(
        self,
        callbacks: tuple[Callable[[], Any], ...],
    ) -> None:
        """Run accepted same-thread requests and release their writer claims."""

        for callback in callbacks:
            try:
                callback()
            except Exception as exc:  # broad-exception: fallback_recorded - deferred lifecycle failures are recorded without replacing the completed delivery result
                log_safe_exception(
                    logger,
                    "Deferred plugin lifecycle operation failed",
                    exc,
                    error_code="deferred_plugin_lifecycle_failed",
                )
            finally:
                with self._notification_dispatch_condition:
                    self._notification_writer_reservations -= 1
                    self._notification_dispatch_condition.notify_all()

    def _defer_notification_lifecycle_if_dispatching(
        self,
        operation: Callable[[], Any],
    ) -> bool:
        """Queue a same-thread read-to-write request without deadlocking."""

        if getattr(self._notification_dispatch_state, "depth", 0) <= 0:
            return False
        with self._notification_dispatch_condition:
            self._deferred_notification_lifecycle.append(operation)
            self._notification_writer_reservations += 1
        return True

    def _reserve_notification_transition_writer(self) -> None:
        """Prevent the last reader from taking over a root transition."""

        with self._notification_dispatch_condition:
            self._notification_transition_reservations += 1
            self._notification_writer_reservations += 1

    def _release_notification_transition_writer(self) -> None:
        """Release a transition claim and drain any otherwise orphaned work."""

        callbacks: tuple[Callable[[], Any], ...] = ()
        with self._notification_dispatch_condition:
            self._notification_transition_reservations -= 1
            self._notification_writer_reservations -= 1
            if (
                self._notification_transition_reservations == 0
                and self._notification_writer_owner is None
                and self._notification_dispatch_count == 0
            ):
                callbacks = tuple(self._deferred_notification_lifecycle)
                self._deferred_notification_lifecycle.clear()
            self._notification_dispatch_condition.notify_all()
        self._run_deferred_notification_lifecycle(callbacks)

    def _run_after_notification_dispatches(
        self,
        operation: Callable[[], Any],
    ) -> Any:
        """Run destructive lifecycle work with writer preference."""

        thread_id = threading.get_ident()
        condition = self._notification_dispatch_condition
        with condition:
            if self._notification_writer_owner == thread_id:
                return operation()
            self._notification_writer_reservations += 1
            while self._notification_writer_owner is not None:
                condition.wait()
            self._notification_writer_owner = thread_id
            while self._notification_dispatch_count:
                condition.wait()
        try:
            return operation()
        finally:
            callbacks: tuple[Callable[[], Any], ...] = ()
            with condition:
                if self._notification_dispatch_count == 0:
                    callbacks = tuple(self._deferred_notification_lifecycle)
                    self._deferred_notification_lifecycle.clear()
            self._run_deferred_notification_lifecycle(callbacks)
            with condition:
                self._notification_writer_owner = None
                self._notification_writer_reservations -= 1
                condition.notify_all()

    def _run_plugin_disable_lifecycle(
        self,
        plugin_id: str,
        operation: Callable[[], "PluginOperationResult"],
    ) -> "PluginOperationResult":
        """Delay ``onunload`` until every active notification snapshot exits."""

        if self._defer_notification_lifecycle_if_dispatching(
            lambda: self._plugin_manager.disable(plugin_id)
        ):
            from src.plugins import PluginOperationResult

            snapshot = self._plugin_manager.snapshot(plugin_id)
            return PluginOperationResult(
                plugin_id=plugin_id,
                operation="disable",
                success=False,
                state=snapshot.state if snapshot is not None else "failed",
                error_code="plugin_lifecycle_deferred",
                deferred=True,
            )
        return self._run_after_notification_dispatches(operation)

    @property
    def builtin_plugin_results(self) -> tuple["PluginOperationResult", ...]:
        """Return startup registration results for caller-supplied built-ins."""

        return self._builtin_plugin_results

    @property
    def external_plugin_results(self) -> tuple["ExternalPluginResult", ...]:
        """Return external discovery results from the configured directory."""

        return self._external_plugin_results

    @property
    def plugin_load_results(self) -> tuple["PluginOperationResult", ...]:
        """Return isolated lifecycle results for the startup plugin snapshot."""

        return self._plugin_load_results

    @property
    def plugin_shutdown_results(self) -> tuple["PluginOperationResult", ...]:
        """Return reverse-order lifecycle results after root shutdown."""

        return self._plugin_shutdown_results

    @property
    def is_closed(self) -> bool:
        """Return whether this one-shot root has entered terminal shutdown.

        The flag is monotonic and intentionally lock-free so callback-owned
        workers can reject a closing root without waiting on its lifecycle lock.
        """

        return self._plugins_closed

    def start_plugins(self) -> tuple["PluginOperationResult", ...]:
        """Compose and load plugins once after this root becomes discoverable."""

        with self._plugin_lifecycle_lock:
            if (
                self._plugins_started
                or self._plugins_starting
                or self._plugin_close_requested
                or self._plugins_closed
            ):
                return self._plugin_load_results
            with _services_lock:
                self._plugins_starting = True
            try:
                if (
                    self._notification_channel_registry is not None
                    and self._notification_channel_registry.config_snapshot()
                    is not self.config
                ):
                    raise ValueError(
                        "notification channel registry and application Config "
                        "must be paired"
                    )
                self._builtin_plugin_results = tuple(
                    self._plugin_manager.register(plugin, source="builtin")
                    for plugin in self._builtin_plugins
                )

                plugins_dir = self._plugins_dir
                if plugins_dir is None:
                    plugins_dir = os.getenv("PLUGINS_DIR")
                directory_is_configured = plugins_dir is not None and not (
                    isinstance(plugins_dir, str) and not plugins_dir.strip()
                )
                if directory_is_configured:
                    from src.plugins import ExternalPluginLoader

                    self._external_plugin_results = (
                        ExternalPluginLoader(
                            self._plugin_manager,
                        ).register_from_directory(plugins_dir)
                    )

                self._plugin_load_results = self._plugin_manager.load_all()
                self._plugins_started = True
                if self._plugins_closed:
                    shutdown_ids = self._plugin_manager._shutdown_plugin_ids()
                    if shutdown_ids:
                        self._plugin_shutdown_results = (
                            self._plugin_manager.disable_all(shutdown_ids)
                        )
                return self._plugin_load_results
            finally:
                close_after_start = False
                with _services_lock:
                    if (
                        self._local_close_requested
                        and not self._local_lifecycle_ops
                    ):
                        self._local_close_requested = False
                        self._local_lifecycle_ops += 1
                        close_after_start = True
                    self._plugins_starting = False
                    if not close_after_start:
                        _services_local_ops.notify_all()
                if close_after_start:
                    try:
                        self._close_plugins()
                    finally:
                        with _services_lock:
                            self._local_lifecycle_ops -= 1
                            _services_local_ops.notify_all()

    def close(self) -> tuple["PluginOperationResult", ...]:
        """Disable the owned plugin snapshot once in reverse registration order.

        Closing the installed process root enters the same transition authority
        as replacement and reset. This keeps the owning root discoverable until
        its complete unload finishes and defers callback-requested successors.
        A request made while that transition is active is queued without waiting
        so a lifecycle callback may safely join its requesting worker; the
        transition owner completes shutdown through ``_close_plugins()``. A
        root that is not installed shuts down outside the transition authority
        so its callback-owned workers can keep using the module accessors; the
        lifecycle boundary around the unload re-checks installation and rescues
        the race with a concurrent install of this root.
        """

        if self._defer_notification_lifecycle_if_dispatching(self.close):
            return self._plugin_shutdown_results

        with _services_lock:
            self._plugin_close_requested = True
            if _services is self and _services_transition_active:
                _services_transition_pending.append(None)
                return self._plugin_shutdown_results
            installed = _services is self
            if not installed and (
                self._plugins_starting or self._local_lifecycle_ops
            ):
                self._local_close_requested = True
                return self._plugin_shutdown_results

        if not installed:
            # A root that is not installed must never wait on the transition
            # authority: a lifecycle callback running while another root's
            # installation drains local operations may close this root, and
            # taking the transition lock here would deadlock that drain.
            return self._close_plugins()

        with _services_transition_lock:
            with _services_lock:
                close_installed_root = _services is self
            if close_installed_root:
                set_application_services(None)
                return self._plugin_shutdown_results

        return self._close_plugins()

    def _run_plugin_manager_lifecycle(
        self,
        operation: Callable[[], Any],
    ) -> Any:
        """Serialize public manager callbacks with process-root transitions.

        The installed root outside an active transition runs the operation as
        the transition owner, so overlapping install, replace, and close
        requests defer into the pending queue until the operation completes.
        Any other operation -- on a root that is not installed, or on the
        installed root while its transition is already active -- runs without
        holding any module lock and is only tracked in a drain counter;
        callback-owned workers can therefore use the module accessors without
        deadlocking, while an installer waits for in-flight tracked
        operations to finish before starting the root's plugins.
        """
        global _services_transition_active, _services_transition_target

        with _services_lock:
            # Operations inside an already-active transition must not
            # re-enter the authority, and operation() must never run while
            # this non-reentrant lock is held: its callbacks may call the
            # module accessors, which take the lock again.
            run_local = _services is not self or _services_transition_active
            if run_local:
                self._local_lifecycle_ops += 1

        if not run_local:
            with _services_transition_lock:
                with _services_lock:
                    owns_installed_root = _services is self
                    if owns_installed_root:
                        _services_transition_target = self
                        _services_transition_active = True
                        _services_transition_pending.clear()
                    else:
                        # Lost the root between the unlocked check and the
                        # transition lock; fall back to a local operation.
                        self._local_lifecycle_ops += 1

                if owns_installed_root:
                    try:
                        return operation()
                    finally:
                        with _services_lock:
                            (
                                has_pending,
                                pending_target,
                                superseded_targets,
                            ) = (
                                _take_latest_installable_pending_services()
                            )
                            if (
                                not has_pending
                                and self._plugin_close_requested
                                and _services is self
                            ):
                                # A root with shutdown requested must not remain
                                # published once its transition ends.
                                has_pending, pending_target = True, None
                            _services_transition_target = None
                            _services_transition_active = False
                        if has_pending or superseded_targets:
                            _set_application_services(
                                pending_target if has_pending else self,
                                validate_direct_target=False,
                                superseded_services=superseded_targets,
                            )

        try:
            return operation()
        finally:
            close_after_operation = False
            with _services_lock:
                if self._local_lifecycle_ops == 1 and self._local_close_requested:
                    self._local_close_requested = False
                    close_after_operation = True
                else:
                    self._local_lifecycle_ops -= 1
                    _services_local_ops.notify_all()
            if close_after_operation:
                try:
                    self._close_plugins()
                finally:
                    with _services_lock:
                        self._local_lifecycle_ops -= 1
                        _services_local_ops.notify_all()

    def _plugin_activation_allowed(self) -> bool:
        """Reject activation after this one-shot root begins shutdown."""

        return not self._plugin_close_requested

    def _close_plugins(self) -> tuple["PluginOperationResult", ...]:
        """Perform root-local shutdown for the global transition owner."""

        return self._run_after_notification_dispatches(
            self._close_plugins_after_dispatches
        )

    def _close_plugins_after_dispatches(
        self,
    ) -> tuple["PluginOperationResult", ...]:
        """Close plugins while holding the notification lifecycle writer."""

        self._plugin_close_requested = True
        with self._plugin_lifecycle_lock:
            if self._plugins_closed:
                return self._plugin_shutdown_results
            self._plugins_closed = True
            if not self._plugins_starting:
                shutdown_ids = self._plugin_manager._shutdown_plugin_ids()
                if shutdown_ids:
                    self._plugin_shutdown_results = self._plugin_manager.disable_all(
                        shutdown_ids,
                    )
                if self._notification_channel_registry is not None:
                    self._notification_channel_registry.mark_unloaded()
            return self._plugin_shutdown_results


_services: Optional[ApplicationServices] = None
_services_lock = threading.Lock()
_services_local_ops = threading.Condition(_services_lock)
_services_transition_lock = threading.RLock()
_services_transition_active = False
_services_transition_target: Optional[ApplicationServices] = None
_services_transition_pending: list[Optional[ApplicationServices]] = []
_services_shutdown = False


def _take_latest_installable_pending_services() -> tuple[
    bool,
    Optional[ApplicationServices],
    tuple[ApplicationServices, ...],
]:
    """Select the latest installable target and retain superseded cleanup debt.

    The caller must hold ``_services_lock``.
    """

    candidates = tuple(_services_transition_pending)
    _services_transition_pending.clear()
    has_target = False
    target: Optional[ApplicationServices] = None
    for candidate in reversed(candidates):
        if candidate is None or not candidate._plugin_close_requested:
            has_target = True
            target = candidate
            break

    superseded: list[ApplicationServices] = []
    for candidate in candidates:
        if (
            candidate is None
            or candidate is target
            or candidate is _services
            or candidate is _services_transition_target
            or any(candidate is retained for retained in superseded)
        ):
            continue
        superseded.append(candidate)
    return has_target, target, tuple(superseded)


def _validate_direct_install_target(
    services: Optional[ApplicationServices],
) -> None:
    """Reject terminal or locally active roots before starting a transition.

    The caller must hold ``_services_lock``.
    """

    if services is None:
        return
    if services.is_closed:
        raise RuntimeError("Cannot install closed application services")
    if services._plugin_close_requested:
        raise RuntimeError(
            "Cannot install application services after shutdown begins"
        )
    if services._plugins_starting or services._local_lifecycle_ops:
        raise RuntimeError(
            "Cannot install application services during local plugin lifecycle"
        )


def get_installed_application_services() -> Optional[ApplicationServices]:
    """Return the transition-visible composition root without installing one."""

    with _services_lock:
        if _services_transition_active:
            return (
                _services
                if _services is not None
                else _services_transition_target
            )
        return _services


def get_application_services() -> ApplicationServices:
    """Return the installed composition root, creating a default one lazily."""
    while True:
        with _services_lock:
            if _services_transition_active:
                visible_services = (
                    _services
                    if _services is not None
                    else _services_transition_target
                )
                if visible_services is not None:
                    # Lifecycle callbacks must resolve their transition's
                    # visible root without waiting on that same transition.
                    return visible_services
            if _services_shutdown:
                raise RuntimeError("Application services are shutting down")

        with _services_transition_lock:
            with _services_lock:
                if _services_shutdown:
                    raise RuntimeError("Application services are shutting down")
                services = _services
            if services is None or services._plugin_close_requested:
                services = ApplicationServices()
            set_application_services(services)
            with _services_lock:
                if _services is services:
                    return services


def set_application_services(services: Optional[ApplicationServices]) -> None:
    """Install a root after fully shutting down the previous root.

    Pass ``None`` to clear the installed root. Overlapping replacement requests
    from plugin callbacks are deferred until the active lifecycle transition
    finishes, with the most recent request winning.
    """

    _set_application_services(services, validate_direct_target=True)


def _set_application_services(
    services: Optional[ApplicationServices],
    *,
    validate_direct_target: bool,
    superseded_services: Iterable[ApplicationServices] = (),
) -> None:
    """Install a target while draining every superseded root accepted earlier."""

    global _services, _services_transition_active, _services_transition_target

    deferred_cleanup_targets = tuple(superseded_services)
    with _services_lock:
        visible_services = _services
    if visible_services is not None and (
        visible_services._defer_notification_lifecycle_if_dispatching(
            lambda: _set_application_services(
                services,
                validate_direct_target=validate_direct_target,
                superseded_services=deferred_cleanup_targets,
            )
        )
    ):
        return

    with _services_lock:
        if _services_shutdown and services is not None:
            raise RuntimeError("Application services are shutting down")
        if _services_transition_active:
            _services_transition_pending.append(services)
            return
        if validate_direct_target:
            _validate_direct_install_target(services)

    with _services_transition_lock:
        transition_writer: Optional[ApplicationServices] = None
        with _services_lock:
            if _services_shutdown and services is not None:
                raise RuntimeError("Application services are shutting down")
            if _services_transition_active:
                _services_transition_pending.append(services)
                return
            if validate_direct_target:
                _validate_direct_install_target(services)
            _services_transition_target = services
            _services_transition_active = True
            _services_transition_pending.clear()
            if _services is not None and _services is not services:
                transition_writer = _services
                transition_writer._reserve_notification_transition_writer()

        target = services
        cleanup_targets = deferred_cleanup_targets
        try:
            while True:
                restart_transition = False
                drained_target_to_close: Optional[ApplicationServices] = None
                cleanup_batch = cleanup_targets
                cleanup_targets = ()
                with _services_lock:
                    previous = _services

                if previous is not None and previous is not target:
                    previous._close_plugins()
                for cleanup_target in cleanup_batch:
                    if cleanup_target is previous or cleanup_target is target:
                        continue
                    cleanup_target._close_plugins()

                with _services_lock:
                    _services_transition_target = target
                    retain_visibility_anchor = (
                        target is None and previous is not None
                    )
                    if not retain_visibility_anchor:
                        _services = target
                    while (
                        target is not None
                        and (
                            target._plugins_starting
                            or target._local_lifecycle_ops
                        )
                    ):
                        # An in-flight local lifecycle operation must fully
                        # complete before this root's plugins may start.
                        _services_local_ops.wait()
                    if target is not None and target._plugin_close_requested:
                        drained_target_to_close = target
                    else:
                        (
                            has_pending,
                            pending_target,
                            cleanup_targets,
                        ) = (
                            _take_latest_installable_pending_services()
                        )
                        if has_pending:
                            target = pending_target
                            _services_transition_target = target
                            restart_transition = True
                        elif cleanup_targets:
                            restart_transition = True

                if drained_target_to_close is not None:
                    drained_target_to_close._close_plugins()
                    with _services_lock:
                        (
                            has_pending,
                            pending_target,
                            cleanup_targets,
                        ) = (
                            _take_latest_installable_pending_services()
                        )
                        target = pending_target if has_pending else None
                        _services_transition_target = target
                        restart_transition = has_pending or bool(cleanup_targets)
                        if (
                            not restart_transition
                            and _services is drained_target_to_close
                        ):
                            _services = None

                if restart_transition:
                    continue

                if target is not None:
                    target.start_plugins()

                with _services_lock:
                    (
                        has_pending,
                        pending_target,
                        cleanup_targets,
                    ) = (
                        _take_latest_installable_pending_services()
                    )
                    if (
                        not has_pending
                        and target is not None
                        and target._plugin_close_requested
                    ):
                        has_pending, pending_target = True, None
                    if not has_pending and not cleanup_targets:
                        if target is None:
                            _services = None
                        _services_transition_active = False
                        _services_transition_target = None
                        return
                    if has_pending:
                        target = pending_target
                    _services_transition_target = target
        finally:
            with _services_lock:
                _services_transition_active = False
                _services_transition_target = None
                _services_transition_pending.clear()
            if transition_writer is not None:
                transition_writer._release_notification_transition_writer()


def reset_application_services() -> None:
    """Clear the installed composition root (next access rebuilds a default)."""
    set_application_services(None)


def _shutdown_application_services() -> None:
    """Enter terminal process shutdown and close the installed root."""
    global _services_shutdown
    with _services_lock:
        _services_shutdown = True
    set_application_services(None)
    # A concurrent transition queues the terminal reset without waiting so its
    # callback-owned workers cannot deadlock. The exit handler itself must wait
    # until that transition consumes the reset before later atexit handlers run.
    with _services_transition_lock:
        pass


atexit.register(_shutdown_application_services)
