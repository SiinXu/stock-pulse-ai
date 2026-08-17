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


def _alias_name_for(canonical_name: str) -> str:
    """Map ``src.bot`` / ``src.bot.*`` onto the legacy ``bot`` logger name."""

    return _ALIAS_PREFIX + canonical_name[len(_CANONICAL_PREFIX) :]


def _alias_loaded_submodules() -> None:
    """Point ``bot`` / ``bot.*`` at already-imported ``src.bot`` modules."""

    for name, module in list(sys.modules.items()):
        if name == _CANONICAL_PREFIX or name.startswith(_CANONICAL_PREFIX + "."):
            sys.modules.setdefault(_alias_name_for(name), module)


def _alias_logger(canonical_name: str, logger: logging.Logger) -> None:
    """Expose one ``src.bot*`` logger under the matching ``bot*`` name."""

    if canonical_name != _CANONICAL_PREFIX and not canonical_name.startswith(
        _CANONICAL_PREFIX + "."
    ):
        return
    logging.Logger.manager.loggerDict.setdefault(_alias_name_for(canonical_name), logger)


def _alias_loaded_loggers() -> None:
    """Point ``bot.*`` logger names at already-created ``src.bot.*`` loggers."""

    for name, logger in list(logging.Logger.manager.loggerDict.items()):
        if isinstance(logger, logging.Logger):
            _alias_logger(name, logger)


def _install_logger_alias() -> None:
    """Keep newly created ``src.bot.*`` loggers visible as ``bot.*``."""

    if getattr(logging.Manager.getLogger, _GETLOGGER_MARK, False):
        return

    original = logging.Manager.getLogger

    def getLogger(self, name):  # noqa: N802 - logging API
        logger = original(self, name)
        if isinstance(name, str):
            _alias_logger(name, logger)
        return logger

    setattr(getLogger, _GETLOGGER_MARK, True)
    logging.Manager.getLogger = getLogger


if not any(isinstance(finder, _LegacyBotAliasFinder) for finder in sys.meta_path):
    sys.meta_path.insert(0, _LegacyBotAliasFinder())

_install_logger_alias()
_alias_loaded_submodules()
_alias_loaded_loggers()
sys.modules[__name__] = _canonical
