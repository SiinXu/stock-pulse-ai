"""Compatibility binding helpers for the system-config service facade."""

from types import CodeType, FunctionType
from typing import Any, Dict


def clone_code_qualnames(
    code: CodeType,
    source_qualname: str,
    target_qualname: str,
) -> CodeType:
    """Clone logical code ownership without changing executable bytecode."""
    replacements = {}
    constants = []
    constants_changed = False
    for constant in code.co_consts:
        if isinstance(constant, CodeType):
            cloned_constant = clone_code_qualnames(
                constant,
                source_qualname,
                target_qualname,
            )
            constants_changed = constants_changed or cloned_constant is not constant
            constants.append(cloned_constant)
        else:
            constants.append(constant)

    if constants_changed:
        replacements["co_consts"] = tuple(constants)

    code_qualname = getattr(code, "co_qualname", None)
    if code_qualname == source_qualname:
        replacements["co_qualname"] = target_qualname
    elif code_qualname and code_qualname.startswith(f"{source_qualname}."):
        replacements["co_qualname"] = (
            f"{target_qualname}{code_qualname[len(source_qualname):]}"
        )

    if not replacements:
        return code
    return code.replace(**replacements)


def clone_function(
    function: FunctionType,
    global_namespace: Dict[str, Any],
    *,
    module_name: str,
    qualname: str,
) -> FunctionType:
    """Clone a moved function so global lookups retain facade semantics."""
    source_qualname = getattr(
        function.__code__,
        "co_qualname",
        function.__qualname__,
    )
    code = clone_code_qualnames(
        function.__code__,
        source_qualname,
        qualname,
    )
    cloned = FunctionType(
        code,
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
