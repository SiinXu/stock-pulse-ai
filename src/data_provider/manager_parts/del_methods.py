# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Manager-owned destructor rebound onto DataFetcherManager.

Extracted from ``src.data_provider.base`` behind an ADR-006 compatibility
facade. The six-line body still best-effort calls rebound ``self.close()``
and swallows ``Exception``. Generic dunder binding skips ``__del__``, so
the bind helper attaches it explicitly. ``close``, ``__init__``, and
timeout-slot construction stay on their existing owners. ``DataFetcherManager``
remains the public import and patch surface.
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


class _DelMethods:
    """Source descriptors rebound onto ``DataFetcherManager`` by its facade."""

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:  # broad-exception: cleanup - Best-effort manager close during interpreter shutdown
            # Best-effort cleanup during interpreter shutdown.
            pass


EXPECTED_DEL_METHOD_NAMES: Tuple[str, ...] = (
    "__del__",
)


def bind_del_methods_facade(
    target_class: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind the destructor explicitly; generic dunder binding skips it."""

    bound_names = []
    for name, descriptor in vars(_DelMethods).items():
        if _descriptor_function(descriptor) is None:
            continue
        # Generic facade bind loops skip names that start with ``__``.
        # ``__del__`` must be rebound explicitly; other dunders stay skipped.
        if name.startswith("__") and name != "__del__":
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
