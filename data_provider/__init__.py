# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Compatibility alias for :mod:`src.data_provider`.

The implementation lives at ``src/data_provider``. This package keeps the
historical ``data_provider`` import root working after the physical move so
existing callers (``import data_provider``, ``from data_provider.base import
...``, and ``patch("data_provider.X.attr")``) do not need to change.

Do **not** eagerly import every implementation submodule. The historical
package ``__init__`` only loaded its public surface. Preloading the rest
(for example ``futu_position_fetcher``) reintroduces a circular import with
``src.services.stock_code_utils``.
"""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import logging
import sys
from types import ModuleType


_CANONICAL_PREFIX = "src.data_provider"
_ALIAS_PREFIX = "data_provider"


def _alias_logger(alias_name: str, canonical_name: str) -> None:
    """Make ``logging.getLogger(alias)`` return the canonical module logger."""

    if alias_name == canonical_name:
        return
    manager = logging.Logger.manager
    canonical_logger = manager.loggerDict.get(canonical_name)
    if canonical_logger is None:
        canonical_logger = logging.getLogger(canonical_name)
    manager.loggerDict[alias_name] = canonical_logger


def _bind_alias(alias_name: str, canonical: ModuleType) -> ModuleType:
    sys.modules[alias_name] = canonical
    canonical_name = getattr(canonical, "__name__", "")
    if isinstance(canonical_name, str) and canonical_name:
        _alias_logger(alias_name, canonical_name)
    return canonical


class _ExistingModuleLoader(importlib.abc.Loader):
    """Reuse an already-imported canonical module under the alias name."""

    def __init__(self, module: ModuleType) -> None:
        self._module = module

    def create_module(self, spec: importlib.machinery.ModuleSpec) -> ModuleType:
        return self._module

    def exec_module(self, module: ModuleType) -> None:
        return None


class _BindAliasAfterLoad(importlib.abc.Loader):
    """Load a canonical module, then register the historical import name."""

    def __init__(self, loader: importlib.abc.Loader | None, alias_name: str) -> None:
        self._loader = loader
        self._alias_name = alias_name

    def create_module(self, spec: importlib.machinery.ModuleSpec) -> ModuleType | None:
        if self._loader is not None and hasattr(self._loader, "create_module"):
            return self._loader.create_module(spec)
        return None

    def exec_module(self, module: ModuleType) -> None:
        if self._loader is not None:
            self._loader.exec_module(module)
        _bind_alias(self._alias_name, module)


class _DataProviderAliasFinder(importlib.abc.MetaPathFinder):
    """Keep ``data_provider.*`` and ``src.data_provider.*`` on one module object."""

    def find_spec(
        self,
        fullname: str,
        path: object | None,
        target: ModuleType | None = None,
    ) -> importlib.machinery.ModuleSpec | None:
        if fullname == _CANONICAL_PREFIX or fullname.startswith(_CANONICAL_PREFIX + "."):
            spec = importlib.machinery.PathFinder.find_spec(fullname, path, target)
            if spec is None:
                return None
            alias_name = _ALIAS_PREFIX + fullname[len(_CANONICAL_PREFIX) :]
            spec.loader = _BindAliasAfterLoad(spec.loader, alias_name)
            return spec
        if fullname != _ALIAS_PREFIX and not fullname.startswith(_ALIAS_PREFIX + "."):
            return None
        if fullname in sys.modules:
            module = sys.modules[fullname]
            if isinstance(module, ModuleType):
                return self._spec_for(fullname, module)
        canonical_name = (
            _CANONICAL_PREFIX
            if fullname == _ALIAS_PREFIX
            else _CANONICAL_PREFIX + fullname[len(_ALIAS_PREFIX) :]
        )
        module = importlib.import_module(canonical_name)
        _bind_alias(fullname, module)
        return self._spec_for(fullname, module)

    @staticmethod
    def _spec_for(fullname: str, module: ModuleType) -> importlib.machinery.ModuleSpec:
        origin = None
        module_spec = getattr(module, "__spec__", None)
        if module_spec is not None:
            origin = module_spec.origin
        spec = importlib.util.spec_from_loader(
            fullname,
            _ExistingModuleLoader(module),
            origin=origin,
            is_package=hasattr(module, "__path__"),
        )
        return spec


def _bind_loaded_submodules() -> None:
    prefix = _CANONICAL_PREFIX + "."
    for name, module in list(sys.modules.items()):
        if name.startswith(prefix) and isinstance(module, ModuleType):
            _bind_alias(_ALIAS_PREFIX + name[len(_CANONICAL_PREFIX) :], module)


def _install() -> ModuleType:
    if not any(isinstance(finder, _DataProviderAliasFinder) for finder in sys.meta_path):
        sys.meta_path.insert(0, _DataProviderAliasFinder())
    canonical = importlib.import_module(_CANONICAL_PREFIX)
    _bind_alias(_ALIAS_PREFIX, canonical)
    _bind_loaded_submodules()
    return canonical


_canonical = _install()

# Re-export the public surface onto this module object for any importer that
# bound the original shim object before sys.modules replacement.
from src.data_provider import *  # noqa: E402,F403
from src.data_provider import __all__ as __all__  # noqa: E402
