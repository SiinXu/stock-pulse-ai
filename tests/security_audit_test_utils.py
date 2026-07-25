# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Explicit lightweight security-audit recorder for non-audit unit tests."""

from __future__ import annotations

from typing import Any


class SecurityAuditRecorderStub:
    """Record calls in memory while satisfying the mandatory runtime contract."""

    def __init__(self) -> None:
        self.attempts: list[dict[str, Any]] = []
        self.completions: list[dict[str, Any]] = []

    def record_attempt(self, **fields: Any) -> None:
        self.attempts.append(fields)

    def record_completion(self, **fields: Any) -> None:
        self.completions.append(fields)
