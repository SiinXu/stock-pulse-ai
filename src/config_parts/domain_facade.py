"""Flat-attribute facade helpers for composed Config domain sub-objects."""

from __future__ import annotations

import copy
from dataclasses import MISSING, fields, replace
from typing import Any, Dict, Mapping, Tuple, Type


def domain_field_names(domain_cls: Type[Any]) -> Tuple[str, ...]:
    """Return dataclass field names for a domain sub-config class."""
    return tuple(field.name for field in fields(domain_cls))


def peel_domain_kwargs(
    kwargs: Dict[str, Any],
    domain_cls: Type[Any],
    composed_key: str,
) -> Tuple[Any, Dict[str, Any]]:
    """Extract domain kwargs / composed object from Config construction kwargs.

    Accepts either a pre-built domain instance under ``composed_key`` or flat
    field kwargs that match ``domain_cls`` field names. Flat kwargs win over
    matching attributes on a provided instance (``dataclasses.replace``).
    """
    domain_names = set(domain_field_names(domain_cls))
    flat_kwargs = {
        name: kwargs.pop(name) for name in tuple(kwargs) if name in domain_names
    }
    provided = kwargs.pop(composed_key, MISSING)
    if provided is MISSING:
        return domain_cls(**flat_kwargs), flat_kwargs
    if flat_kwargs:
        return replace(provided, **flat_kwargs), flat_kwargs
    return provided, flat_kwargs


def install_flat_domain_facade(
    config_cls: Type[Any],
    composed_attr: str,
    domain_cls: Type[Any],
    *,
    inject_dataclass_fields: bool = True,
) -> Mapping[str, Any]:
    """Install flat property accessors that delegate to a composed domain object.

    When ``inject_dataclass_fields`` is true, mirror domain ``Field`` metadata
    onto ``config_cls.__dataclass_fields__`` (with ``init=False``) so reflection
    of historical flat attribute names and defaults remains stable.
    """
    installed: Dict[str, Any] = {}
    for domain_field in fields(domain_cls):
        name = domain_field.name

        def _getter(self: Any, _name: str = name, _attr: str = composed_attr) -> Any:
            return getattr(getattr(self, _attr), _name)

        def _setter(
            self: Any,
            value: Any,
            _name: str = name,
            _attr: str = composed_attr,
        ) -> None:
            setattr(getattr(self, _attr), _name, value)

        setattr(config_cls, name, property(_getter, _setter))
        installed[name] = domain_field

        if inject_dataclass_fields:
            mirrored = copy.copy(domain_field)
            mirrored.init = False
            mirrored.repr = False
            mirrored.compare = False
            mirrored.hash = False
            config_cls.__dataclass_fields__[name] = mirrored

    return installed


def wrap_config_init_for_domains(
    config_cls: Type[Any],
    domain_bindings: Mapping[str, Type[Any]],
) -> None:
    """Wrap generated ``Config.__init__`` so flat domain kwargs still construct.

    ``domain_bindings`` maps composed attribute name -> domain dataclass type,
    e.g. ``{"notification": NotificationConfig, "share_image": ShareImageConfig}``.

    The wrapper closes over helpers so facade rebinding of ``__init__`` globals
    (``src.config`` namespace) does not break domain peeling.
    """
    base_init = config_cls.__init__
    peel = peel_domain_kwargs
    bindings = dict(domain_bindings)

    def _init(self: Any, *args: Any, **kwargs: Any) -> None:
        for composed_attr, domain_cls in bindings.items():
            domain_value, _ = peel(kwargs, domain_cls, composed_attr)
            kwargs[composed_attr] = domain_value
        base_init(self, *args, **kwargs)

    _init.__name__ = base_init.__name__
    _init.__qualname__ = base_init.__qualname__
    _init.__module__ = base_init.__module__
    _init.__doc__ = base_init.__doc__
    _init.__annotations__ = dict(getattr(base_init, "__annotations__", {}))
    _init.__wrapped__ = getattr(base_init, "__wrapped__", base_init)  # type: ignore[attr-defined]
    config_cls.__init__ = _init  # type: ignore[method-assign]
