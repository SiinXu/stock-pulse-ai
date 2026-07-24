# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Read-only investment framework adapter for analysis context assembly."""

from __future__ import annotations

from typing import Optional

from src.schemas.investment_framework import InvestmentFrameworkAnalysisContext
from src.services.investment_framework_service import InvestmentFrameworkService
from src.storage import DatabaseManager


class InvestmentFrameworkContextReader:
    """Stable boundary that does not mutate or inject prompt state."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self._service = InvestmentFrameworkService(db_manager)

    def read(self) -> Optional[InvestmentFrameworkAnalysisContext]:
        return self._service.read_active_context()


__all__ = ["InvestmentFrameworkContextReader"]
