# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Stable plugin-system exceptions that never embed plugin error text."""

from __future__ import annotations


class PluginError(Exception):
    """Base class for typed plugin errors with a safe public code."""

    def __init__(self, error_code: str) -> None:
        self.error_code = error_code
        super().__init__(error_code)


class PluginRegistryError(PluginError):
    """Raised when an extension registration cannot be completed safely."""

    def __init__(
        self,
        error_code: str,
        *,
        recovery_handle: object | None = None,
    ) -> None:
        self.recovery_handle = recovery_handle
        super().__init__(error_code)


class PluginContextClosedError(PluginError):
    """Raised when a plugin uses its registration context outside ``onload``."""
