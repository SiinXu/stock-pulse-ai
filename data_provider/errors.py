# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Typed data-provider failures and exception summary helpers.

Extracted from :mod:`data_provider.base` behind an ADR-006 compatibility facade.
Public imports and patch targets remain on ``data_provider.base``; this module
owns the implementation bodies only.
"""

from __future__ import annotations

from typing import Tuple

from src.utils.sanitize import sanitize_diagnostic_text


def unwrap_exception(exc: Exception) -> Exception:
    """
    Follow chained exceptions and return the deepest non-cyclic cause.
    """
    current = exc
    visited = set()

    while current is not None and id(current) not in visited:
        visited.add(id(current))
        next_exc = current.__cause__ or current.__context__
        if next_exc is None:
            break
        current = next_exc

    return current


def summarize_exception(exc: Exception) -> Tuple[str, str]:
    """
    Build a stable summary for logs while preserving the application-layer message.
    """
    root = unwrap_exception(exc)
    error_type = type(root).__name__
    message = str(exc).strip() or str(root).strip() or error_type
    return error_type, sanitize_diagnostic_text(" ".join(message.split()))


class DataFetchError(Exception):
    """数据获取异常基类"""

    def __init__(self, message: str, *, provider_failure_count: int = 0) -> None:
        self.provider_failure_count = provider_failure_count
        super().__init__(message)


class RateLimitError(DataFetchError):
    """API 速率限制异常"""
    pass


class DataSourceUnavailableError(DataFetchError):
    """数据源不可用异常"""
    pass


class CircuitOpenError(DataSourceUnavailableError):
    """A provider call was skipped because its circuit is in cooldown."""
    pass
