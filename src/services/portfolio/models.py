# -*- coding: utf-8 -*-
"""Portfolio service for P0 account/events/snapshot workflow."""

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

if TYPE_CHECKING:
    from src.storage import PortfolioAccount

logger = logging.getLogger(__name__)

PortfolioBusyError = RepoPortfolioBusyError

try:
    import yfinance as yf
except Exception:  # pragma: no cover - broad-exception: optional_metadata - yfinance is optional for FX refresh
    yf = None

EPS = 1e-8
VALID_MARKETS = {"cn", "hk", "us", "jp", "kr", "tw"}
PARTIAL_VALUATION_MARKETS = {"jp", "kr", "tw"}
VALID_COST_METHODS = {"fifo", "avg"}
VALID_SIDES = {"buy", "sell"}
VALID_ACCOUNT_TYPES = {"real", "paper"}
DEFAULT_ACCOUNT_TYPE = "real"
VALID_CASH_DIRECTIONS = {"in", "out"}
VALID_CORPORATE_ACTIONS = {"cash_dividend", "split_adjustment"}
PORTFOLIO_FX_REFRESH_DISABLED_REASON = "portfolio_fx_update_disabled"
PORTFOLIO_REALTIME_QUOTE_MAX_WORKERS = 4


def _portfolio_limitations_for_market(market: str) -> List[str]:
    """Return explicit snapshot limitations for markets with partial valuation semantics."""

    if market not in PARTIAL_VALUATION_MARKETS:
        return []
    return [
        "realtime_quote_best_effort",
        "fx_and_cost_basis_partial",
        "sector_and_risk_metrics_limited",
    ]


def _merge_portfolio_limitations(*groups: Iterable[str]) -> List[str]:
    merged: List[str] = []
    seen: Set[str] = set()
    for group in groups:
        for item in group:
            if item and item not in seen:
                seen.add(item)
                merged.append(item)
    return merged


class PortfolioConflictError(Exception):
    """Raised when request conflicts with existing portfolio state."""


class PortfolioIdempotencyConflictError(PortfolioConflictError):
    """Raised when an operation ID is reused for a different mutation."""


class PortfolioOversellError(ValueError):
    """Raised when a sell would exceed the available position quantity."""

    def __init__(
        self,
        *,
        symbol: str,
        trade_date: Optional[date],
        requested_quantity: float,
        available_quantity: float,
    ) -> None:
        self.symbol = symbol
        self.trade_date = trade_date
        self.requested_quantity = float(requested_quantity)
        self.available_quantity = max(0.0, float(available_quantity))
        date_hint = f" on {trade_date.isoformat()}" if trade_date is not None else ""
        super().__init__(
            "Oversell detected for "
            f"{symbol}{date_hint}: requested={round(self.requested_quantity, 8)}, "
            f"available={round(self.available_quantity, 8)}"
        )


@dataclass
class _AvgState:
    quantity: float = 0.0
    total_cost: float = 0.0


@dataclass(frozen=True)
class _ResolvedPositionPrice:
    price: float
    source: str
    price_date: Optional[date]
    is_stale: bool
    is_available: bool
    provider: Optional[str] = None


# Preserve the legacy facade identities used by introspection and pickle.
for _legacy_facade_member in (
    PortfolioConflictError,
    PortfolioIdempotencyConflictError,
    PortfolioOversellError,
    _AvgState,
    _ResolvedPositionPrice,
    _merge_portfolio_limitations,
    _portfolio_limitations_for_market,
):
    _legacy_facade_member.__module__ = "src.services.portfolio_service"

del _legacy_facade_member
