# -*- coding: utf-8 -*-
"""Portfolio service for P0 account/events/snapshot workflow.

Implementation is split under ``src.services.portfolio``:
``models`` / ``service`` / ``positions`` / ``transactions`` / ``risk``.
This module remains the stable import facade.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

from src.data_provider.base import canonical_stock_code, normalize_stock_code
from src.config import (
    PORTFOLIO_IDEMPOTENCY_REPLAY_WINDOW_DAYS_DEFAULT,
    get_config,
)
from src.portfolio_idempotency import (
    build_portfolio_idempotency_scope_key,
    build_portfolio_idempotency_storage_id,
)
from src.repositories.portfolio_repo import (
    DuplicateTradeDedupHashError,
    DuplicateTradeUidError,
    PortfolioBusyError as RepoPortfolioBusyError,
    PortfolioRepository,
)
from src.utils.sanitize import log_safe_exception

from src.services.portfolio.models import (
    DEFAULT_ACCOUNT_TYPE,
    EPS,
    PARTIAL_VALUATION_MARKETS,
    PORTFOLIO_FX_REFRESH_DISABLED_REASON,
    PORTFOLIO_REALTIME_QUOTE_MAX_WORKERS,
    PortfolioConflictError,
    PortfolioIdempotencyConflictError,
    PortfolioOversellError,
    VALID_ACCOUNT_TYPES,
    VALID_CASH_DIRECTIONS,
    VALID_CORPORATE_ACTIONS,
    VALID_COST_METHODS,
    VALID_MARKETS,
    VALID_SIDES,
    _AvgState,
    _ResolvedPositionPrice,
    _merge_portfolio_limitations,
    _portfolio_limitations_for_market,
)

if TYPE_CHECKING:
    from src.storage import PortfolioAccount

logger = logging.getLogger(__name__)

# Preserve the historical alias assignment on this facade module.
PortfolioBusyError = RepoPortfolioBusyError


def _get_config():
    """Keep legacy facade monkeypatches effective for split service methods."""

    return get_config()


try:
    import yfinance as yf
except Exception:  # pragma: no cover - broad-exception: optional_metadata - yfinance is optional for FX refresh
    yf = None


class PortfolioService:
    """Business logic for account CRUD, event writes, and snapshot replay."""

    def __init__(
        self,
        repo: Optional[PortfolioRepository] = None,
        *,
        now_provider: Optional[Callable[[], datetime]] = None,
    ):
        self.repo = repo or PortfolioRepository()
        self._now_provider = now_provider or datetime.now
        self._kind_repo: Any = None


from src.services.portfolio.binding import bind_part_class as _bind_part_class
from src.services.portfolio.service import _PortfolioServiceCoreMethods as _PSCore
from src.services.portfolio.transactions import _PortfolioTransactionMethods as _PSTxn
from src.services.portfolio.positions import _PortfolioPositionMethods as _PSPos
from src.services.portfolio.risk import _PortfolioRiskMethods as _PSRisk

for _part in (_PSCore, _PSTxn, _PSPos, _PSRisk):
    _bind_part_class(
        _part,
        PortfolioService,
        globals(),
        module_name=__name__,
        owner_name="PortfolioService",
    )

del _bind_part_class, _PSCore, _PSTxn, _PSPos, _PSRisk, _part
