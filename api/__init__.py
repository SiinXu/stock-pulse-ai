# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Compatibility alias: ``import api`` resolves to the ``src.api`` package.

The packaged-layout migration (issue #167) moved the HTTP package from
``api/`` to ``src/api/``. This shim keeps existing ``from api...`` importers
working by rebinding ``sys.modules`` so ``api`` and ``src.api`` (and their
submodules) are the same module objects. There is no second import tree.
"""

from __future__ import annotations

import importlib
import sys
from importlib.abc import Loader, MetaPathFinder
from importlib.machinery import ModuleSpec, PathFinder
from importlib.util import find_spec
from types import ModuleType


_ALIAS_ROOT = "api"
_CANONICAL_ROOT = "src.api"


def _canonical_name(fullname: str) -> str | None:
    """Return the ``src.api`` name for an ``api`` import request, or None."""

    if fullname == _ALIAS_ROOT:
        return _CANONICAL_ROOT
    if fullname.startswith(_ALIAS_ROOT + "."):
        return _CANONICAL_ROOT + fullname[len(_ALIAS_ROOT) :]
    return None


class _ApiAliasLoader(Loader):
    """Load an ``api*`` name by returning the already-executed canonical module."""

    def __init__(self, canonical: str) -> None:
        self.canonical = canonical

    def create_module(self, spec: ModuleSpec) -> ModuleType:
        return importlib.import_module(self.canonical)

    def exec_module(self, module: ModuleType) -> None:
        return None


class _BindAliasAfterLoad(Loader):
    """Execute a canonical module and bind its historical name afterwards."""

    def __init__(self, loader: Loader | None, alias: str) -> None:
        self.loader = loader
        self.alias = alias

    def create_module(self, spec: ModuleSpec) -> ModuleType | None:
        if self.loader is not None and hasattr(self.loader, "create_module"):
            return self.loader.create_module(spec)
        return None

    def exec_module(self, module: ModuleType) -> None:
        if self.loader is not None:
            self.loader.exec_module(module)
        sys.modules[self.alias] = module


class _ApiAliasFinder(MetaPathFinder):
    """Map ``api`` / ``api.*`` import requests onto ``src.api`` / ``src.api.*``."""

    def find_spec(self, fullname, path=None, target=None):  # type: ignore[no-untyped-def]
        if fullname == _CANONICAL_ROOT or fullname.startswith(_CANONICAL_ROOT + "."):
            spec = PathFinder.find_spec(fullname, path, target)
            if spec is None:
                return None
            alias = _ALIAS_ROOT + fullname[len(_CANONICAL_ROOT) :]
            spec.loader = _BindAliasAfterLoad(spec.loader, alias)
            return spec
        canonical = _canonical_name(fullname)
        if canonical is None:
            return None
        module = importlib.import_module(canonical)
        # Bind before returning the temporary alias spec. The canonical-side
        # loader above owns the durable metadata and reload behavior.
        sys.modules[fullname] = module
        canonical_spec = find_spec(canonical)
        is_package = bool(
            canonical_spec is not None
            and canonical_spec.submodule_search_locations is not None
        )
        return ModuleSpec(
            fullname,
            _ApiAliasLoader(canonical),
            is_package=is_package,
            origin=None if canonical_spec is None else canonical_spec.origin,
        )


def _install_finder() -> None:
    """Install the alias finder once so reloads do not stack copies."""

    if any(isinstance(finder, _ApiAliasFinder) for finder in sys.meta_path):
        return
    sys.meta_path.insert(0, _ApiAliasFinder())


def _bind_alias_tree() -> None:
    """Publish already-imported ``src.api*`` modules under the ``api`` name."""

    prefix = _CANONICAL_ROOT + "."
    for name, module in list(sys.modules.items()):
        if name == _CANONICAL_ROOT or name.startswith(prefix):
            alias = _ALIAS_ROOT + name[len(_CANONICAL_ROOT) :]
            sys.modules[alias] = module


_install_finder()
_canonical = importlib.import_module(_CANONICAL_ROOT)
sys.modules[_ALIAS_ROOT] = _canonical
_bind_alias_tree()
