# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Manager-owned money-flow cache lookup, store, invalidate, and stats.

These descriptors are rebound onto ``DataFetcherManager`` by the compatibility
facade. Cache TTL/size class attributes, cache/circuit instance state, hit/miss
increments, and ``get_money_flow`` routing remain on the facade.
"""

from __future__ import annotations

import time
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
normalize_stock_code = None  # type: ignore[assignment,misc]

# ``importlib.reload`` retains a module dictionary. Preserve the callback
# installed by the loaded compatibility facade so an owner reload can
# atomically rebuild and rebind both sides of the seam.
_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get(
    "_FACADE_RELOAD_HOOK"
)


class _MoneyFlowCacheMethods:
    """Source descriptors rebound onto ``DataFetcherManager`` by its facade."""

    def _money_flow_cache_lookup(self, key, *, allow_stale: bool = False):
        now = time.time()
        with self._money_flow_cache_lock:
            entry = self._money_flow_cache.get(key)
            if entry is None and allow_stale:
                identity = (key[0], key[1], key[3], key[4])
                candidates = [
                    value
                    for cache_key, value in self._money_flow_cache.items()
                    if (
                        cache_key[0],
                        cache_key[1],
                        cache_key[3],
                        cache_key[4],
                    ) == identity
                ]
                entry = max(candidates, key=lambda item: item["stored_at"], default=None)
            if entry is None:
                return None
            age = now - entry["stored_at"]
            ttl = (
                self._MONEY_FLOW_STALE_TTL_SECONDS
                if allow_stale
                else self._MONEY_FLOW_CACHE_TTL_SECONDS
            )
            return entry["outcome"] if age <= ttl else None

    def _money_flow_cache_store(self, key, outcome) -> None:
        snapshot = getattr(outcome, "snapshot", None)
        with self._money_flow_cache_lock:
            self._money_flow_cache[key] = {
                "stored_at": time.time(),
                "outcome": outcome,
                "calibration_identity": (
                    getattr(snapshot, "source", None),
                    getattr(snapshot, "bucket_definition", None),
                    getattr(snapshot, "unit", None),
                    getattr(snapshot, "amount_scale", None),
                ),
            }
            while len(self._money_flow_cache) > self._MONEY_FLOW_CACHE_MAX_ENTRIES:
                oldest_key = min(
                    self._money_flow_cache,
                    key=lambda item: self._money_flow_cache[item]["stored_at"],
                )
                self._money_flow_cache.pop(oldest_key, None)

    def invalidate_money_flow_cache(self, stock_code: Optional[str] = None) -> int:
        """Invalidate all entries, or only entries for one normalized symbol."""
        normalized = normalize_stock_code(stock_code) if stock_code else None
        with self._money_flow_cache_lock:
            keys = [
                key for key in self._money_flow_cache
                if normalized is None or key[0] == normalized
            ]
            for key in keys:
                self._money_flow_cache.pop(key, None)
            return len(keys)

    def get_money_flow_cache_stats(self) -> Dict[str, Any]:
        with self._money_flow_cache_lock:
            return {
                "entries": len(self._money_flow_cache),
                "hits": self._money_flow_cache_hits,
                "misses": self._money_flow_cache_misses,
                "circuit": self._money_flow_circuit.get_snapshot(),
            }


EXPECTED_MONEY_FLOW_CACHE_METHOD_NAMES = (
    "_money_flow_cache_lookup",
    "_money_flow_cache_store",
    "invalidate_money_flow_cache",
    "get_money_flow_cache_stats",
)


def bind_money_flow_cache_methods_facade(
    target_class: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind money-flow cache descriptors without changing the manager API."""

    bound_names = []
    for name, descriptor in vars(_MoneyFlowCacheMethods).items():
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
