# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Manager-owned fundamental Config accessor rebound onto DataFetcherManager.

Extracted from ``src.data_provider.base`` behind an ADR-006 compatibility
facade. This owner holds only ``_get_fundamental_config``. CN/offshore
loaders stay in ``fundamental_loader_methods``. Cache TTL helpers stay in
``fundamental_cache_methods``. Chip, realtime, and retry callers stay on
their existing owners and keep calling ``self._get_fundamental_config``.
``DataFetcherManager`` remains the public import and patch surface.
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

# ``importlib.reload`` retains a module dictionary. Preserve the callback
# installed by the loaded compatibility facade so an owner reload can
# atomically rebuild and rebind both sides of the seam.
_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get(
    "_FACADE_RELOAD_HOOK"
)


class _FundamentalContextMethods:
    """Source descriptors rebound onto ``DataFetcherManager`` by its facade."""

    def _get_fundamental_config(self):
        """Return process Config for fundamental timeouts, retries, and cache TTL.

        The default composition root still resolves ``src.config.get_config``
        on each call, so tests can keep patching that accessor. An injected
        ``ApplicationServices.config`` is authoritative and ignores that patch.
        """
        from src.application_services import get_application_services

        return get_application_services().config


EXPECTED_FUNDAMENTAL_CONTEXT_METHOD_NAMES: Tuple[str, ...] = (
    "_get_fundamental_config",
)


def bind_fundamental_context_methods_facade(
    target_class: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind the fundamental-config accessor without changing the manager API."""

    bound_names = []
    for name, descriptor in vars(_FundamentalContextMethods).items():
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
