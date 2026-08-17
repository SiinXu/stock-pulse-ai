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
import logging
import sys
from types import ModuleType

import src.bot as _canonical

_ALIAS_PREFIX = "bot"
_CANONICAL_PREFIX = "src.bot"
_GETLOGGER_MARK = "_stockpulse_bot_alias"


class _ExistingModuleLoader(importlib.abc.Loader):
    """Return an already-imported canonical module instead of executing again."""

    def __init__(self, module):
        self._module = module

    def create_module(self, spec):  # noqa: ARG002
        return self._module

    def exec_module(self, module):  # noqa: ARG002
        return None


class _BindAliasAfterLoad(importlib.abc.Loader):
    """Execute a canonical child and publish its legacy name afterwards."""

    def __init__(self, loader, alias_name: str) -> None:
        self._loader = loader
        self._alias_name = alias_name

    def create_module(self, spec):
        if self._loader is not None and hasattr(self._loader, "create_module"):
            return self._loader.create_module(spec)
        return None

    def exec_module(self, module: ModuleType) -> None:
        if self._loader is not None:
            self._loader.exec_module(module)
        sys.modules[self._alias_name] = module


class _LegacyBotAliasFinder(importlib.abc.MetaPathFinder):
    """Resolve ``bot.*`` to the canonical ``src.bot.*`` module objects."""

    def find_spec(self, fullname, path=None, target=None):  # noqa: ARG002
        if _is_canonical_name(fullname):
            spec = importlib.machinery.PathFinder.find_spec(fullname, path, target)
            if spec is None:
                return None
            spec.loader = _BindAliasAfterLoad(
                spec.loader,
                _alias_name_for(fullname),
            )
            return spec
        if fullname != _ALIAS_PREFIX and not fullname.startswith(_ALIAS_PREFIX + "."):
            return None
        if fullname == _ALIAS_PREFIX:
            return None
        canonical_name = _CANONICAL_PREFIX + fullname[len(_ALIAS_PREFIX) :]
        module = importlib.import_module(canonical_name)
        sys.modules[fullname] = module
        spec = importlib.machinery.ModuleSpec(
            fullname,
            _ExistingModuleLoader(module),
            origin=getattr(module, "__file__", None),
            is_package=hasattr(module, "__path__"),
        )
        spec.submodule_search_locations = getattr(module, "__path__", None)
        return spec


def _is_canonical_name(name: str) -> bool:
    return name == _CANONICAL_PREFIX or name.startswith(_CANONICAL_PREFIX + ".")


def _is_alias_name(name: str) -> bool:
    return name == _ALIAS_PREFIX or name.startswith(_ALIAS_PREFIX + ".")


def _alias_name_for(canonical_name: str) -> str:
    """Map ``src.bot`` / ``src.bot.*`` onto the legacy ``bot`` name."""

    return _ALIAS_PREFIX + canonical_name[len(_CANONICAL_PREFIX) :]


def _canonical_name_for(alias_name: str) -> str:
    """Map ``bot`` / ``bot.*`` onto the canonical ``src.bot`` name."""

    return _CANONICAL_PREFIX + alias_name[len(_ALIAS_PREFIX) :]


def _bind_logger_alias(manager: logging.Manager, alias: str, logger: logging.Logger) -> None:
    """Point ``bot.*`` at the same Logger object as ``src.bot.*``."""

    existing = manager.loggerDict.get(alias)
    if existing is logger:
        return
    if existing is not None and not isinstance(existing, logging.Logger):
        manager._fixupChildren(existing, logger)
    manager.loggerDict[alias] = logger


def _alias_loaded_submodules() -> None:
    """Point ``bot`` / ``bot.*`` at already-imported ``src.bot`` modules."""

    for name, module in list(sys.modules.items()):
        if _is_canonical_name(name):
            sys.modules[_alias_name_for(name)] = module


def _alias_loaded_loggers() -> None:
    """Point ``bot.*`` logger names at already-created ``src.bot.*`` loggers."""

    manager = logging.Logger.manager
    for name, logger in list(manager.loggerDict.items()):
        if isinstance(logger, logging.Logger) and _is_canonical_name(name):
            _bind_logger_alias(manager, _alias_name_for(name), logger)


def _install_logger_alias() -> None:
    """Make ``logging.getLogger("bot.X")`` return the ``src.bot.X`` logger.

    ``setdefault`` is not enough: if a caller creates ``bot.X`` before
    ``src.bot.X``, the two names must still resolve to one Logger object.
    """

    if getattr(logging.Manager.getLogger, _GETLOGGER_MARK, False):
        return

    original = logging.Manager.getLogger

    def getLogger(self, name):  # noqa: N802 - logging API
        if isinstance(name, str) and _is_alias_name(name):
            logger = original(self, _canonical_name_for(name))
            _bind_logger_alias(self, name, logger)
            return logger
        logger = original(self, name)
        if isinstance(name, str) and _is_canonical_name(name):
            _bind_logger_alias(self, _alias_name_for(name), logger)
        return logger

    setattr(getLogger, _GETLOGGER_MARK, True)
    logging.Manager.getLogger = getLogger


if not any(isinstance(finder, _LegacyBotAliasFinder) for finder in sys.meta_path):
    sys.meta_path.insert(0, _LegacyBotAliasFinder())

_install_logger_alias()
_alias_loaded_submodules()
_alias_loaded_loggers()
sys.modules[__name__] = _canonical
