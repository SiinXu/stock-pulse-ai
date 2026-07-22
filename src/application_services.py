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
        """Disable the owned plugin snapshot once in reverse registration order."""

        with self._plugin_lifecycle_lock:
            if self._plugins_closed:
                return self._plugin_shutdown_results
            self._plugins_closed = True
            if self._plugins_started and not self._plugins_starting:
                self._plugin_shutdown_results = self._plugin_manager.disable_all()
            return self._plugin_shutdown_results


_services: Optional[ApplicationServices] = None
_services_lock = threading.Lock()


def get_application_services() -> ApplicationServices:
    """Return the installed composition root, creating a default one lazily."""
    global _services
    while True:
        with _services_lock:
            if _services is None:
                _services = ApplicationServices()
            services = _services
        services.start_plugins()
        with _services_lock:
            if _services is services:
                return services


def set_application_services(services: Optional[ApplicationServices]) -> None:
    """Install a composition root. Pass ``None`` to clear the installed root.

    Intended for the startup layer and for tests that need isolated instances.
    """
    global _services
    with _services_lock:
        previous = _services
        _services = services
    if previous is not None and previous is not services:
        previous.close()
    if services is not None:
        services.start_plugins()


def reset_application_services() -> None:
    """Clear the installed composition root (next access rebuilds a default)."""
    set_application_services(None)


atexit.register(reset_application_services)
