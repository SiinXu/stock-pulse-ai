"""Compatibility binding helpers for the AlphaSift service facade."""

from types import FunctionType
from typing import Any, Dict, Optional, Tuple, Type


def _make_cell(value: Any) -> Any:
    """Create one closure cell without mutating the source function."""
    return (lambda: value).__closure__[0]


def _clone_closure(
    function: FunctionType,
    source_owner: Optional[Type[Any]],
    target_owner: Optional[Type[Any]],
) -> Optional[Tuple[Any, ...]]:
    """Retarget zero-argument super() cells to the facade class."""
    if function.__closure__ is None or source_owner is None:
        return function.__closure__
    return tuple(
        _make_cell(target_owner) if cell.cell_contents is source_owner else cell
        for cell in function.__closure__
    )


def clone_facade_function(
    function: FunctionType,
    global_namespace: Dict[str, Any],
    *,
    qualname: Optional[str] = None,
    source_owner: Optional[Type[Any]] = None,
    target_owner: Optional[Type[Any]] = None,
) -> FunctionType:
    """Clone a moved function with the exact facade runtime namespace."""
    if not isinstance(function, FunctionType):
        raise TypeError("AlphaSift facade binding requires a Python function")
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
    cloned.__qualname__ = qualname or function.__qualname__
    if hasattr(function, "__type_params__"):
        cloned.__type_params__ = function.__type_params__
    return cloned


def bind_facade_functions(
    source_namespace: Dict[str, Any],
    target_namespace: Dict[str, Any],
    names: Tuple[str, ...],
) -> Tuple[str, ...]:
    """Bind selected source functions into a facade namespace in order."""
    for name in names:
        function = source_namespace.get(name)
        if not isinstance(function, FunctionType):
            raise TypeError(
                f"AlphaSift facade binding requires a Python function: {name}"
            )
        target_namespace[name] = clone_facade_function(
            function,
            target_namespace,
            qualname=name,
        )
    return names


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
        raise TypeError("AlphaSift facade binding requires a method descriptor")
    cloned = clone_facade_function(
        function,
        global_namespace,
        qualname=f"{target_owner.__qualname__}.{name}",
        source_owner=source_owner,
        target_owner=target_owner,
    )
    if isinstance(descriptor, staticmethod):
        return staticmethod(cloned)
    if isinstance(descriptor, classmethod):
        return classmethod(cloned)
    return cloned


def bind_facade_class_methods(
    target_class: Type[Any],
    source_class: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind source descriptors onto a facade class in source order."""
    bound_names = []
    for name, descriptor in vars(source_class).items():
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
                source_owner=source_class,
                target_owner=target_class,
                name=name,
            ),
        )
        bound_names.append(name)
    return tuple(bound_names)
