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
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
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


def _install() -> ModuleType:
    canonical = importlib.import_module(_CANONICAL_PREFIX)
    _alias_module(_ALIAS_PREFIX, canonical)
    for info in pkgutil.walk_packages(canonical.__path__, _CANONICAL_PREFIX + "."):
        module = importlib.import_module(info.name)
        alias_name = _ALIAS_PREFIX + info.name[len(_CANONICAL_PREFIX) :]
        _alias_module(alias_name, module)
    return canonical


_canonical = _install()

# Re-export the public surface onto this module object for any importer that
# bound the original shim object before sys.modules replacement.
from src.data_provider import *  # noqa: E402,F403
from src.data_provider import __all__ as __all__  # noqa: E402
