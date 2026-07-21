"""Compatibility binding helpers for the public ``src.config`` facade."""

from types import FunctionType
from typing import Any, Dict


def clone_function(function: FunctionType, global_namespace: Dict[str, Any]) -> FunctionType:
    """Clone a moved function so global lookups retain facade semantics."""
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
    cloned.__kwdefaults__ = function.__kwdefaults__
    cloned.__module__ = "src.config"
    cloned.__qualname__ = function.__qualname__
    return cloned


def clone_descriptor(descriptor: Any, global_namespace: Dict[str, Any]) -> Any:
    """Clone a method descriptor with facade-backed function globals."""
    if isinstance(descriptor, classmethod):
        return classmethod(clone_function(descriptor.__func__, global_namespace))
    if isinstance(descriptor, staticmethod):
        return staticmethod(clone_function(descriptor.__func__, global_namespace))
    return clone_function(descriptor, global_namespace)


def replace_closure_reference(
    function: FunctionType,
    previous: Any,
    replacement: Any,
) -> None:
    """Replace a generated function's captured compatibility reference."""
    for cell in function.__closure__ or ():
        if cell.cell_contents is previous:
            cell.cell_contents = replacement


def bind_wrapped_function(
    function: FunctionType,
    global_namespace: Dict[str, Any],
) -> None:
    """Bind a generated function hidden behind a standard-library wrapper."""
    wrapped = getattr(function, "__wrapped__", None)
    if not isinstance(wrapped, FunctionType):
        return
    cloned = clone_function(wrapped, global_namespace)
    replace_closure_reference(function, wrapped, cloned)
    function.__wrapped__ = cloned
