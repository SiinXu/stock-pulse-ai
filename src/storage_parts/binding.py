"""Compatibility binding helpers for the public :mod:`src.storage` facade."""

from contextlib import contextmanager
import inspect
from types import FunctionType
from typing import Any, Dict, Optional, Tuple, Type


def _make_cell(value: Any) -> Any:
    """Create one closure cell without mutating the source function."""

    return (lambda: value).__closure__[0]


def _clone_closure(
    function: FunctionType,
    source_owner: Type[Any],
    target_owner: Type[Any],
) -> Optional[Tuple[Any, ...]]:
    """Retarget zero-argument ``super()`` cells to the facade class."""

    if function.__closure__ is None:
        return None
    return tuple(
        _make_cell(target_owner) if cell.cell_contents is source_owner else cell
        for cell in function.__closure__
    )


def _clone_function(
    function: FunctionType,
    global_namespace: Dict[str, Any],
    *,
    source_owner: Type[Any],
    target_owner: Type[Any],
    qualname: str,
) -> FunctionType:
    """Clone a moved function with the exact facade runtime namespace."""

    if not isinstance(function, FunctionType):
        raise TypeError("Storage facade binding requires a Python function")

    cloned = FunctionType(
        function.__code__,
        global_namespace,
        name=function.__name__,
        argdefs=function.__defaults__,
        closure=_clone_closure(function, source_owner, target_owner),
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


def _clone_contextmanager(
    function: FunctionType,
    global_namespace: Dict[str, Any],
    *,
    source_owner: Type[Any],
    target_owner: Type[Any],
    qualname: str,
) -> FunctionType:
    """Rebuild a ``contextmanager`` wrapper around a facade-bound generator."""

    wrapped = inspect.unwrap(function)
    cloned_wrapped = _clone_function(
        wrapped,
        global_namespace,
        source_owner=source_owner,
        target_owner=target_owner,
        qualname=qualname,
    )
    cloned = contextmanager(cloned_wrapped)
    cloned.__dict__.update(
        {
            key: value
            for key, value in function.__dict__.items()
            if key != "__wrapped__"
        }
    )
    cloned.__wrapped__ = cloned_wrapped
    cloned.__module__ = str(global_namespace["__name__"])
    cloned.__qualname__ = qualname
    return cloned


def _descriptor_function(descriptor: Any) -> Optional[FunctionType]:
    if isinstance(descriptor, (staticmethod, classmethod)):
        return descriptor.__func__
    if isinstance(descriptor, FunctionType):
        return descriptor
    return None


def _clone_descriptor(
    descriptor: Any,
    global_namespace: Dict[str, Any],
    *,
    source_owner: Type[Any],
    target_owner: Type[Any],
    name: str,
) -> Any:
    function = _descriptor_function(descriptor)
    if function is None:
        raise TypeError("Storage facade binding requires a method descriptor")

    qualname = f"{target_owner.__qualname__}.{name}"
    wrapped = getattr(function, "__wrapped__", None)
    if isinstance(wrapped, FunctionType) and inspect.isgeneratorfunction(wrapped):
        cloned = _clone_contextmanager(
            function,
            global_namespace,
            source_owner=source_owner,
            target_owner=target_owner,
            qualname=qualname,
        )
    else:
        cloned = _clone_function(
            function,
            global_namespace,
            source_owner=source_owner,
            target_owner=target_owner,
            qualname=qualname,
        )

    if isinstance(descriptor, staticmethod):
        return staticmethod(cloned)
    if isinstance(descriptor, classmethod):
        return classmethod(cloned)
    return cloned


def bind_storage_facade_methods(
    target_class: Type[Any],
    source_container: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind source descriptors onto ``DatabaseManager`` in source order."""

    bound_names = []
    for name, descriptor in vars(source_container).items():
        if name.startswith("__") and name not in {"__new__", "__init__"}:
            continue
        if _descriptor_function(descriptor) is None:
            continue
        setattr(
            target_class,
            name,
            _clone_descriptor(
                descriptor,
                global_namespace,
                source_owner=source_container,
                target_owner=target_class,
                name=name,
            ),
        )
        bound_names.append(name)
    return tuple(bound_names)
