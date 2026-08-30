# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Re-export of the shared ADR-006 rebind helpers for the akshare parts package.

The implementation lives in ``src.data_provider._facade_bind``. This module is
kept so existing imports such as
``from .akshare_parts.facade_bind import bind_methods_from_class`` keep working.
"""

from __future__ import annotations

from .._facade_bind import (
    _clone_facade_descriptor,
    _clone_facade_function,
    _descriptor_function,
    bind_methods_from_class,
)

__all__ = (
    "_clone_facade_descriptor",
    "_clone_facade_function",
    "_descriptor_function",
    "bind_methods_from_class",
)
