# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Compatibility alias for :mod:`src.data_provider`.

The implementation lives at ``src/data_provider``. This package keeps the
historical ``data_provider`` import root working after the physical move so
existing callers (``import data_provider``, ``from data_provider.base import
...``) do not need to change in this stage.

Submodule identity is shared: ``data_provider.base is src.data_provider.base``.
Logger names used by ``logging.getLogger(__name__)`` are aliased so
``data_provider.<module>`` still captures the same records.

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


def _alias_module(alias_name: str, canonical: ModuleType) -> None:
    sys.modules[alias_name] = canonical
    canonical_name = getattr(canonical, "__name__", "")
    if isinstance(canonical_name, str) and canonical_name:
        _alias_logger(alias_name, canonical_name)


class _ExistingModuleLoader(importlib.abc.Loader):
    """Return an already-imported canonical module under the alias name."""

    def __init__(self, module: ModuleType) -> None:
        self._module = module

    def create_module(self, spec: importlib.machinery.ModuleSpec) -> ModuleType:
        return self._module

    def exec_module(self, module: ModuleType) -> None:
        return None


class _DataProviderAliasFinder(importlib.abc.MetaPathFinder):
    """Resolve ``data_provider.*`` to ``src.data_provider.*`` on demand."""

    def find_spec(
        self,
        fullname: str,
        path: object | None,
        target: ModuleType | None = None,
    ) -> importlib.machinery.ModuleSpec | None:
        if fullname != _ALIAS_PREFIX and not fullname.startswith(_ALIAS_PREFIX + "."):
            return None
        if fullname in sys.modules:
            return importlib.util.spec_from_loader(
                fullname, _ExistingModuleLoader(sys.modules[fullname])
            )
        canonical_name = (
            _CANONICAL_PREFIX
            if fullname == _ALIAS_PREFIX
            else _CANONICAL_PREFIX + fullname[len(_ALIAS_PREFIX) :]
        )
        module = importlib.import_module(canonical_name)
        _alias_module(fullname, module)
        return importlib.util.spec_from_loader(
            fullname, _ExistingModuleLoader(module)
        )


def _alias_loaded_submodules() -> None:
    prefix = _CANONICAL_PREFIX + "."
    for name, module in list(sys.modules.items()):
        if name.startswith(prefix) and isinstance(module, ModuleType):
            _alias_module(_ALIAS_PREFIX + name[len(_CANONICAL_PREFIX) :], module)


def _install() -> ModuleType:
    if not any(isinstance(finder, _DataProviderAliasFinder) for finder in sys.meta_path):
        sys.meta_path.insert(0, _DataProviderAliasFinder())
    canonical = importlib.import_module(_CANONICAL_PREFIX)
    _alias_module(_ALIAS_PREFIX, canonical)
    _alias_loaded_submodules()
    return canonical


_canonical = _install()

# Re-export the public surface onto this module object for any importer that
# bound the original shim object before sys.modules replacement.
from src.data_provider import *  # noqa: E402,F403
from src.data_provider import __all__ as __all__  # noqa: E402
