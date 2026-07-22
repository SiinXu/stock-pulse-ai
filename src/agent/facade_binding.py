"""Compatibility binding helpers for legacy Agent module facades."""

import inspect
from types import FunctionType
from typing import Any, Dict, Optional, Tuple, Type


def clone_facade_function(
    function: FunctionType,
    global_namespace: Dict[str, Any],
    *,
    module_name: str,
    qualname: str,
    evaluate_annotations: bool = False,
) -> FunctionType:
    """Clone a moved function so global lookups retain facade semantics."""

    if not isinstance(function, FunctionType):
        raise TypeError("Facade binding requires a Python function")

    cloned = FunctionType(
        function.__code__,
        global_namespace,
        name=function.__name__,
        argdefs=function.__defaults__,
        closure=function.__closure__,
    )
    annotations = function.__annotations__
    if evaluate_annotations:
        annotations = inspect.get_annotations(
            function,
            globals=global_namespace,
            locals=global_namespace,
            eval_str=True,
        )
    cloned.__annotations__ = dict(annotations)
    cloned.__dict__.update(function.__dict__)
    cloned.__doc__ = function.__doc__
    cloned.__kwdefaults__ = (
        dict(function.__kwdefaults__) if function.__kwdefaults__ else None
    )
    cloned.__module__ = module_name
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
    module_name: str,
    owner_qualname: str,
    evaluate_annotations: bool,
) -> Any:
    """Clone a method descriptor with the legacy facade as its globals."""

    def clone(function: Optional[FunctionType]) -> Optional[FunctionType]:
        if function is None:
            return None
        return clone_facade_function(
            function,
            global_namespace,
            module_name=module_name,
            qualname=f"{owner_qualname}.{function.__name__}",
            evaluate_annotations=evaluate_annotations,
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


def bind_facade_methods(
    target_class: Type[Any],
    source_container: Type[Any],
    global_namespace: Dict[str, Any],
    *,
    evaluate_annotations: bool = False,
) -> Tuple[str, ...]:
    """Bind source descriptors onto a legacy class without changing its API."""

    bound_names = []
    rebound_descriptors: Dict[int, Any] = {}
    module_name = str(global_namespace["__name__"])
    for name, descriptor in vars(source_container).items():
        if name.startswith("__") or _descriptor_function(descriptor) is None:
            continue
        descriptor_id = id(descriptor)
        if descriptor_id not in rebound_descriptors:
            rebound_descriptors[descriptor_id] = _clone_facade_descriptor(
                descriptor,
                global_namespace,
                module_name=module_name,
                owner_qualname=target_class.__qualname__,
                evaluate_annotations=evaluate_annotations,
            )
        setattr(target_class, name, rebound_descriptors[descriptor_id])
        bound_names.append(name)
    return tuple(bound_names)
