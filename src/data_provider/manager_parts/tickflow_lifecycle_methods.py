# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Manager-owned TickFlow lifecycle methods rebound onto DataFetcherManager.

Extracted from ``src.data_provider.base`` behind an ADR-006 compatibility
facade. Prefetch, ``_init_default_fetchers``, timeout slot construction,
and remaining ``get_config()`` sites stay on the facade. These descriptors
own ``_get_tickflow_fetcher`` and ``close``. Rebound ``__del__`` lives in
``del_methods`` and still calls rebound ``self.close()``. Config is
resolved through rebound ``self._get_fundamental_config()`` (not bare
``get_config()``). ``DataFetcherManager`` remains the public import and
patch surface.
"""

from __future__ import annotations

from typing import (
    Any,
    Callable,
    Dict,
    Optional,
    Tuple,
    Type,
)

from .daily_cache_methods import _clone_facade_descriptor, _descriptor_function

# Facade-only symbols cannot be imported from ``src.data_provider.base`` while
# that module is still assembling this part (circular import). Declare anchors
# so flake8 F821 is clean; rebound methods resolve the real objects from the
# ``src.data_provider.base`` global namespace.
logger = None  # type: ignore[assignment,misc]
logging = None  # type: ignore[assignment,misc]
log_safe_exception = None  # type: ignore[assignment,misc]
RLock = None  # type: ignore[assignment,misc]

# ``importlib.reload`` retains a module dictionary. Preserve the callback
# installed by the loaded compatibility facade so an owner reload can
# atomically rebuild and rebind both sides of the seam.
_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get(
    "_FACADE_RELOAD_HOOK"
)


class _TickFlowLifecycleMethods:
    """Source descriptors rebound onto ``DataFetcherManager`` by its facade."""

    def _get_tickflow_fetcher(self):
        """Lazily create a TickFlow fetcher for market-review-only calls."""
        config = self._get_fundamental_config()
        api_key = (getattr(config, "tickflow_api_key", None) or "").strip()

        if not hasattr(self, "_tickflow_lock") or self._tickflow_lock is None:
            self._tickflow_lock = RLock()

        with self._tickflow_lock:
            current_fetcher = getattr(self, "_tickflow_fetcher", None)
            current_key = getattr(self, "_tickflow_api_key", None)

            if not api_key:
                if current_fetcher is not None and hasattr(current_fetcher, "close"):
                    try:
                        current_fetcher.close()
                    except Exception as exc:
                        log_safe_exception(
                            logger,
                            "TickFlow stale fetcher close failed",
                            exc,
                            error_code="tickflow_stale_fetcher_close_failed",
                            level=logging.DEBUG,
                        )
                self._tickflow_fetcher = None
                self._tickflow_api_key = None
                return None

            configured_fetcher = self._get_fetcher_by_name("TickFlowFetcher")
            if configured_fetcher is not None:
                return configured_fetcher

            if current_fetcher is not None and current_key == api_key:
                return current_fetcher

            if current_fetcher is not None and hasattr(current_fetcher, "close"):
                try:
                    current_fetcher.close()
                except Exception as exc:
                    log_safe_exception(
                        logger,
                        "TickFlow fetcher close during replacement failed",
                        exc,
                        error_code="tickflow_replaced_fetcher_close_failed",
                        level=logging.DEBUG,
                    )

            try:
                from .tickflow_fetcher import TickFlowFetcher

                fetcher = TickFlowFetcher(
                    api_key=api_key,
                    kline_adjust=getattr(config, "tickflow_kline_adjust", "none"),
                    batch_daily_enabled=getattr(config, "tickflow_batch_daily_enabled", True),
                    batch_size=getattr(config, "tickflow_batch_size", 100),
                    priority=getattr(config, "tickflow_priority", 2),
                )
                self._tickflow_fetcher = fetcher
                self._tickflow_api_key = api_key
                return fetcher
            except Exception as exc:
                log_safe_exception(
                    logger,
                    "TickFlow fetcher initialization failed",
                    exc,
                    error_code="tickflow_fetcher_initialization_failed",
                    level=logging.WARNING,
                )
                self._tickflow_fetcher = None
                self._tickflow_api_key = None
                return None

    def close(self) -> None:
        """Best-effort release of manager-owned resources."""
        if not hasattr(self, "_tickflow_lock") or self._tickflow_lock is None:
            self._tickflow_lock = RLock()

        with self._tickflow_lock:
            current_fetcher = getattr(self, "_tickflow_fetcher", None)
            self._tickflow_fetcher = None
            self._tickflow_api_key = None

        if current_fetcher is not None and hasattr(current_fetcher, "close"):
            try:
                current_fetcher.close()
            except Exception as exc:
                log_safe_exception(
                    logger,
                    "TickFlow manager resource close failed",
                    exc,
                    error_code="tickflow_manager_resource_close_failed",
                    level=logging.DEBUG,
                )


EXPECTED_TICKFLOW_LIFECYCLE_METHOD_NAMES: Tuple[str, ...] = (
    "_get_tickflow_fetcher",
    "close",
)


def bind_tickflow_lifecycle_methods_facade(
    target_class: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind TickFlow lifecycle descriptors without changing the manager API."""

    bound_names = []
    for name, descriptor in vars(_TickFlowLifecycleMethods).items():
        if name.startswith("__") or _descriptor_function(descriptor) is None:
            continue
        setattr(
            target_class,
            name,
            _clone_facade_descriptor(
                descriptor,
                global_namespace,
                owner_qualname=target_class.__qualname__,
            ),
        )
        bound_names.append(name)
    return tuple(bound_names)


def _install_facade_reload_hook(hook: Callable[[], None]) -> None:
    """Register the loaded facade assembly callback for owner reloads."""

    global _FACADE_RELOAD_HOOK
    _FACADE_RELOAD_HOOK = hook


def _rebind_loaded_facade() -> None:
    """Refresh a registered facade after this owner module is reloaded."""

    hook = _FACADE_RELOAD_HOOK
    if hook is not None:
        hook()


_rebind_loaded_facade()
