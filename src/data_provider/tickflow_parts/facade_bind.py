# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""ADR-006 helpers to rebind TickFlowFetcher method bodies onto the facade.

Mirrors ``akshare_parts.facade_bind``. Each fetcher package keeps its own copy:
the two existing copies in the tree (``akshare_parts`` and ``manager_parts``)
have already diverged in ``_clone_facade_function``, so importing across
packages would couple this fetcher to another fetcher's private variant.
"""

from __future__ import annotations

from types import FunctionType
from typing import Any, Callable, Dict, Optional, Tuple, Type


def _clone_facade_function(
    function: FunctionType,
    global_namespace: Dict[str, Any],
    *,
    qualname: str,
) -> FunctionType:
    """Clone one method so free-name lookups keep ``tickflow_fetcher`` patch seams."""

    cloned = FunctionType(
        function.__code__,
        global_namespace,
        name=function.__name__,
        argdefs=function.__defaults__,
        closure=function.__closure__,
    )
    cloned.__annotations__ = dict(function.__annotations__)
    cloned.__dict__.update(function.__dict__)
    cloned.__doc__ = function.__doc__
    cloned.__kwdefaults__ = (
        dict(function.__kwdefaults__) if function.__kwdefaults__ else None
    )
    cloned.__module__ = str(global_namespace["__name__"])
    cloned.__qualname__ = qualname
    if hasattr(function, "__type_params__"):
        cloned.__type_params__ = function.__type_params__
    return cloned


def _descriptor_function(descriptor: Any) -> Optional[FunctionType]:
    if isinstance(descriptor, (staticmethod, classmethod)):
        return descriptor.__func__
    if isinstance(descriptor, property):
        return descriptor.fget
    if isinstance(descriptor, FunctionType):
        return descriptor
    return None


def _clone_facade_descriptor(
    descriptor: Any,
    global_namespace: Dict[str, Any],
    *,
    owner_qualname: str,
) -> Any:
    def clone(function: Optional[FunctionType]) -> Optional[FunctionType]:
        if function is None:
            return None
        return _clone_facade_function(
            function,
            global_namespace,
            qualname=f"{owner_qualname}.{function.__name__}",
        )

    if isinstance(descriptor, staticmethod):
        return staticmethod(clone(descriptor.__func__))
    if isinstance(descriptor, classmethod):
        return classmethod(clone(descriptor.__func__))
    if isinstance(descriptor, property):
        return property(
            clone(descriptor.fget),
            clone(descriptor.fset),
            clone(descriptor.fdel),
            descriptor.__doc__,
        )
    return clone(descriptor)


def bind_methods_from_class(
    source_class: Type[Any],
    target_class: Type[Any],
    global_namespace: Dict[str, Any],
    *,
    expected_names: Tuple[str, ...],
    post_bind: Optional[Callable[[str, Any], Any]] = None,
) -> Tuple[str, ...]:
    """Bind descriptors from *source_class* onto *target_class* with facade globals."""

    bound_names = []
    for name, descriptor in vars(source_class).items():
        if name.startswith("__") or _descriptor_function(descriptor) is None:
            continue
        bound = _clone_facade_descriptor(
            descriptor,
            global_namespace,
            owner_qualname=target_class.__qualname__,
        )
        if post_bind is not None:
            bound = post_bind(name, bound)
        setattr(target_class, name, bound)
        bound_names.append(name)
    result = tuple(bound_names)
    if result != expected_names:
        raise ImportError(
            f"Unexpected {source_class.__name__} methods: {result!r}, "
            f"expected {expected_names!r}"
        )
    return result
