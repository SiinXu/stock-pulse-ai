# -*- coding: utf-8 -*-
"""Compatibility facade: ``import bot`` rebinds to :mod:`src.bot`.

The public contract is the module-object rebind already used for package
aliases: ``sys.modules[__name__] = _canonical``. A meta-path finder then
maps ``bot.*`` onto the same ``src.bot.*`` module objects so
``import bot.dispatcher`` and ``importlib.reload`` do not double-load.
"""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import sys

import src.bot as _canonical

_ALIAS_PREFIX = "bot"
_CANONICAL_PREFIX = "src.bot"


class _ExistingModuleLoader(importlib.abc.Loader):
    """Return an already-imported canonical module instead of executing again."""

    def __init__(self, module):
        self._module = module

    def create_module(self, spec):  # noqa: ARG002
        return self._module

    def exec_module(self, module):  # noqa: ARG002
        return None


class _LegacyBotAliasFinder(importlib.abc.MetaPathFinder):
    """Resolve ``bot.*`` to the canonical ``src.bot.*`` module objects."""

    def find_spec(self, fullname, path=None, target=None):  # noqa: ARG002
        if fullname != _ALIAS_PREFIX and not fullname.startswith(_ALIAS_PREFIX + "."):
            return None
        if fullname == _ALIAS_PREFIX:
            return None
        canonical_name = _CANONICAL_PREFIX + fullname[len(_ALIAS_PREFIX) :]
        module = importlib.import_module(canonical_name)
        spec = importlib.machinery.ModuleSpec(
            fullname,
            _ExistingModuleLoader(module),
            origin=getattr(module, "__file__", None),
            is_package=hasattr(module, "__path__"),
        )
        spec.submodule_search_locations = getattr(module, "__path__", None)
        return spec


def _alias_loaded_submodules() -> None:
    """Point ``bot`` / ``bot.*`` at already-imported ``src.bot`` modules."""

    for name, module in list(sys.modules.items()):
        if name == _CANONICAL_PREFIX or name.startswith(_CANONICAL_PREFIX + "."):
            sys.modules.setdefault(_ALIAS_PREFIX + name[len(_CANONICAL_PREFIX) :], module)


if not any(isinstance(finder, _LegacyBotAliasFinder) for finder in sys.meta_path):
    sys.meta_path.insert(0, _LegacyBotAliasFinder())

_alias_loaded_submodules()
sys.modules[__name__] = _canonical
