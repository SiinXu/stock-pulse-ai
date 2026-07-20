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

Only the singletons that actually exist in this codebase are held: Config,
DatabaseManager, SearchService and AnalysisTaskQueue. There is no process-wide
cache, auth rate limiter or shared thread pool singleton to own, so none is
invented here (thread pools are owned per-pipeline / per-queue instance).
``system_config_service`` is already composed in the FastAPI lifespan
(``api/app.py``) and keeps its app-scoped lifecycle; this root does not modify
or take over ``system_config_service.py``.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:  # import for typing only; avoids runtime import cycles
    from src.config import Config
    from src.search_service import SearchService
    from src.services.task_queue import AnalysisTaskQueue
    from src.storage import DatabaseManager


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
    ) -> None:
        self._config = config
        self._database = database
        self._search = search
        self._task_queue = task_queue

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


_services: Optional[ApplicationServices] = None
_services_lock = threading.Lock()


def get_application_services() -> ApplicationServices:
    """Return the installed composition root, creating a default one lazily."""
    global _services
    if _services is None:
        with _services_lock:
            if _services is None:
                _services = ApplicationServices()
    return _services


def set_application_services(services: Optional[ApplicationServices]) -> None:
    """Install a composition root. Pass ``None`` to clear the installed root.

    Intended for the startup layer and for tests that need isolated instances.
    """
    global _services
    with _services_lock:
        _services = services


def reset_application_services() -> None:
    """Clear the installed composition root (next access rebuilds a default)."""
    set_application_services(None)
