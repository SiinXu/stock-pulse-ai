"""Compatibility binding for legacy analysis context pack module paths."""

from __future__ import annotations

import importlib
import logging
import sys
from types import FunctionType, ModuleType
from typing import Any, Dict, Iterable, MutableMapping


_MODULE_METADATA = frozenset(
    {
        "__name__",
        "__loader__",
        "__package__",
        "__spec__",
        "__file__",
        "__cached__",
        "__builtins__",
        "__all__",
    }
)
_INITIALIZED_KEY = "_analysis_context_pack_facade_initialized"


def _cell(value: Any):
    """Create a closure cell containing ``value``."""

    def capture() -> Any:
        return value

    return capture.__closure__[0]


def _clone_function(
    function: FunctionType,
    facade_globals: MutableMapping[str, Any],
    implementation_name: str,
    legacy_name: str,
    memo: Dict[int, FunctionType],
) -> FunctionType:
    """Clone an implementation function with the legacy module globals."""
    existing = memo.get(id(function))
    if existing is not None:
        return existing

    closure = function.__closure__
    if closure:
        rebound_cells = []
        for closure_cell in closure:
            try:
                value = closure_cell.cell_contents
            except ValueError:
                rebound_cells.append(closure_cell)
                continue
            if isinstance(value, FunctionType) and value.__module__ == implementation_name:
                value = _clone_function(
                    value,
                    facade_globals,
                    implementation_name,
                    legacy_name,
                    memo,
                )
                rebound_cells.append(_cell(value))
            else:
                rebound_cells.append(closure_cell)
        closure = tuple(rebound_cells)

    rebound = FunctionType(
        function.__code__,
        facade_globals,
        name=function.__name__,
        argdefs=function.__defaults__,
        closure=closure,
    )
    memo[id(function)] = rebound
    rebound.__annotations__ = dict(function.__annotations__)
    rebound.__dict__.update(function.__dict__)
    rebound.__doc__ = function.__doc__
    rebound.__kwdefaults__ = (
        dict(function.__kwdefaults__) if function.__kwdefaults__ else None
    )
    rebound.__module__ = legacy_name
    rebound.__qualname__ = function.__qualname__
    if hasattr(function, "__type_params__"):
        rebound.__type_params__ = function.__type_params__

    wrapped = getattr(function, "__wrapped__", None)
    if isinstance(wrapped, FunctionType) and wrapped.__module__ == implementation_name:
        rebound.__wrapped__ = _clone_function(
            wrapped,
            facade_globals,
            implementation_name,
            legacy_name,
            memo,
        )
    return rebound


def _load_implementation(module_name: str, *, reload_existing: bool) -> ModuleType:
    """Import an implementation, reloading it only for a facade reload."""
    module = sys.modules.get(module_name)
    if module is None:
        return importlib.import_module(module_name)
    if reload_existing:
        return importlib.reload(module)
    return module


def load_legacy_module(
    implementation_name: str,
    facade_globals: MutableMapping[str, Any],
    public_exports: Iterable[str],
) -> ModuleType:
    """Populate a legacy function module with facade-bound implementation objects."""
    reload_existing = bool(facade_globals.get(_INITIALIZED_KEY))
    implementation = _load_implementation(
        implementation_name,
        reload_existing=reload_existing,
    )
    implementation_globals = vars(implementation)
    legacy_name = str(facade_globals["__name__"])

    owned_classes = [
        name
        for name, value in implementation_globals.items()
        if isinstance(value, type) and value.__module__ == implementation_name
    ]
    if owned_classes:
        raise TypeError(
            f"{implementation_name} function facade cannot bind owned classes: "
            f"{', '.join(sorted(owned_classes))}"
        )

    for name, value in tuple(implementation_globals.items()):
        if name not in _MODULE_METADATA:
            facade_globals[name] = value

    memo: Dict[int, FunctionType] = {}
    for name, value in tuple(implementation_globals.items()):
        if isinstance(value, FunctionType) and value.__module__ == implementation_name:
            facade_globals[name] = _clone_function(
                value,
                facade_globals,
                implementation_name,
                legacy_name,
                memo,
            )

    logger = implementation_globals.get("logger")
    if isinstance(logger, logging.Logger):
        facade_globals["logger"] = logging.getLogger(legacy_name)

    exports = tuple(public_exports)
    missing = [name for name in exports if name not in facade_globals]
    if missing:
        raise ImportError(
            f"{legacy_name} compatibility exports missing from "
            f"{implementation_name}: {', '.join(missing)}"
        )
    facade_globals["__all__"] = exports
    implementation_globals["__all__"] = exports
    facade_globals[_INITIALIZED_KEY] = True
    return implementation


__all__ = ("load_legacy_module",)
