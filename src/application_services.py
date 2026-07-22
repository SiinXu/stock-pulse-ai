"""Lightweight application composition root.

`ApplicationServices` owns the process-wide service singletons so that the
startup layer holds them in one place and tests can inject isolated instances.

Design notes:
- Each service defaults to the module's existing accessor
  (``Config.get_instance``, ``DatabaseManager.get_instance``,
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
  per-plugin fault isolation.

Only the singletons that actually exist in this codebase are held: Config,
DatabaseManager, SearchService, AnalysisTaskQueue, and the process plugin
manager. There is no process-wide cache, auth rate limiter or shared thread pool
singleton to own, so none is invented here (thread pools are owned per-pipeline /
per-queue instance).
``system_config_service`` is already composed in the FastAPI lifespan
(``api/app.py``) and keeps its app-scoped lifecycle; this root does not modify
or take over ``system_config_service.py``.
"""

from __future__ import annotations

import atexit
import os
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Iterable, Optional

if TYPE_CHECKING:  # import for typing only; avoids runtime import cycles
    from src.config import Config
    from src.plugins import (
        ExternalPluginResult,
        Plugin,
        PluginManager,
        PluginOperationResult,
    )
    from src.search_service import SearchService
    from src.services.task_queue import AnalysisTaskQueue
    from src.storage import DatabaseManager


PLUGIN_APPLICATION_VERSION = "3.26.3"


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
        builtin_plugins: Iterable["Plugin"] = (),
        plugins_dir: str | Path | None = None,
        plugin_application_version: str = PLUGIN_APPLICATION_VERSION,
    ) -> None:
        self._config = config
        self._database = database
        self._search = search
        self._task_queue = task_queue
        if plugin_manager is None:
            from src.plugins import PluginManager

            plugin_manager = PluginManager(
                application_version=plugin_application_version,
            )
        self._plugin_manager = plugin_manager
        self._builtin_plugins = tuple(builtin_plugins)
        self._plugins_dir = plugins_dir
        self._builtin_plugin_results: tuple["PluginOperationResult", ...] = ()
        self._external_plugin_results: tuple["ExternalPluginResult", ...] = ()
        self._plugin_load_results: tuple["PluginOperationResult", ...] = ()
        self._plugin_shutdown_results: tuple["PluginOperationResult", ...] = ()
        self._plugin_lifecycle_lock = threading.RLock()
        self._plugins_starting = False
        self._plugins_started = False
        self._plugins_closed = False

    @property
    def config(self) -> "Config":
        if self._config is not None:
            return self._config
        from src.config import Config

        return Config.get_instance()

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
            if self._plugins_started or self._plugins_starting or self._plugins_closed:
                return self._plugin_load_results
            self._plugins_starting = True
            try:
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
                    self._plugin_shutdown_results = self._plugin_manager.disable_all()
                return self._plugin_load_results
            finally:
                self._plugins_starting = False

    def close(self) -> tuple["PluginOperationResult", ...]:
        """Disable the owned plugin snapshot once in reverse registration order.

        Closing the installed process root enters the same transition authority
        as replacement and reset. This keeps the owning root discoverable until
        its complete unload finishes and defers callback-requested successors.
        A request made while that transition is active is queued without waiting
        so a lifecycle callback may safely join its requesting worker; the
        transition owner completes shutdown through ``_close_plugins()``.
        """

        with _services_lock:
            close_installed_root = _services is self
        if close_installed_root:
            set_application_services(None)
            return self._plugin_shutdown_results

        return self._close_plugins()

    def _close_plugins(self) -> tuple["PluginOperationResult", ...]:
        """Perform root-local shutdown for the global transition owner."""

        with self._plugin_lifecycle_lock:
            if self._plugins_closed:
                return self._plugin_shutdown_results
            self._plugins_closed = True
            if self._plugins_started and not self._plugins_starting:
                self._plugin_shutdown_results = self._plugin_manager.disable_all()
            return self._plugin_shutdown_results


_services: Optional[ApplicationServices] = None
_services_lock = threading.Lock()
_services_transition_lock = threading.RLock()
_services_transition_active = False
_services_transition_pending: list[Optional[ApplicationServices]] = []
_services_shutdown = False


def _take_latest_installable_pending_services() -> tuple[
    bool,
    Optional[ApplicationServices],
]:
    """Consume the latest pending target that has not already been closed.

    The caller must hold ``_services_lock``.
    """

    while _services_transition_pending:
        candidate = _services_transition_pending.pop()
        if candidate is None or not candidate.is_closed:
            _services_transition_pending.clear()
            return True, candidate
    return False, None


def get_application_services() -> ApplicationServices:
    """Return the installed composition root, creating a default one lazily."""
    while True:
        with _services_lock:
            if _services_transition_active and _services is not None:
                # Lifecycle callbacks must resolve the root whose transition
                # they belong to without starting or resurrecting a successor.
                return _services
            if _services_shutdown:
                raise RuntimeError("Application services are shutting down")

        with _services_transition_lock:
            with _services_lock:
                if _services_shutdown:
                    raise RuntimeError("Application services are shutting down")
                services = _services
            if services is None or services.is_closed:
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
    global _services, _services_transition_active

    with _services_lock:
        if _services_shutdown and services is not None:
            raise RuntimeError("Application services are shutting down")
        if _services_transition_active:
            _services_transition_pending.append(services)
            return
        if services is not None and services.is_closed:
            raise RuntimeError("Cannot install closed application services")

    with _services_transition_lock:
        with _services_lock:
            if _services_shutdown and services is not None:
                raise RuntimeError("Application services are shutting down")
            if _services_transition_active:
                _services_transition_pending.append(services)
                return
            if services is not None and services.is_closed:
                raise RuntimeError("Cannot install closed application services")
            _services_transition_active = True
            _services_transition_pending.clear()

        target = services
        try:
            while True:
                with _services_lock:
                    previous = _services

                if previous is not None and previous is not target:
                    previous._close_plugins()

                with _services_lock:
                    has_pending, pending_target = (
                        _take_latest_installable_pending_services()
                    )
                    if has_pending:
                        target = pending_target
                    _services = target

                if target is not None:
                    target.start_plugins()

                with _services_lock:
                    has_pending, pending_target = (
                        _take_latest_installable_pending_services()
                    )
                    if not has_pending:
                        if target is not None and target.is_closed:
                            _services = None
                        _services_transition_active = False
                        return
                    target = pending_target
        finally:
            with _services_lock:
                _services_transition_active = False
                _services_transition_pending.clear()


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
