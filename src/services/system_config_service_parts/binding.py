"""Compatibility binding helpers for the system-config service facade."""

from types import FunctionType
from typing import Any, Dict


def clone_function(
    function: FunctionType,
    global_namespace: Dict[str, Any],
    *,
    module_name: str,
    qualname: str,
) -> FunctionType:
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
    cloned.__module__ = module_name
    cloned.__qualname__ = qualname
    if hasattr(function, "__type_params__"):
        cloned.__type_params__ = function.__type_params__
    return cloned


def clone_member(
    member: Any,
    global_namespace: Dict[str, Any],
    *,
    module_name: str,
    owner_name: str,
    member_name: str,
) -> Any:
    """Clone method descriptors and pass data attributes through unchanged."""
    qualname = f"{owner_name}.{member_name}"
    if isinstance(member, classmethod):
        return classmethod(
            clone_function(
                member.__func__,
                global_namespace,
                module_name=module_name,
                qualname=qualname,
            )
        )
    if isinstance(member, staticmethod):
        return staticmethod(
            clone_function(
                member.__func__,
                global_namespace,
                module_name=module_name,
                qualname=qualname,
            )
        )
    if isinstance(member, FunctionType):
        return clone_function(
            member,
            global_namespace,
            module_name=module_name,
            qualname=qualname,
        )
    return member
