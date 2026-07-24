# -*- coding: utf-8 -*-
"""Paper trading portfolio service (Issue #370).

Forward simulation on top of the existing portfolio domain: simulated trades are
recorded through the authoritative ``PortfolioService.record_trade`` path, so
positions, cash, and P&L reuse the same replay/snapshot machinery as real
accounts. This layer only adds paper-specific rules:

- account classification (``paper`` via the ``PortfolioAccountKind`` sidecar),
- an execution model that fills at the latest available quote when no explicit
  price is given, and
- available-cash validation on buys.

Fees and slippage are intentionally ignored in the MVP (documented) so simulated
P&L stays interpretable and comparable.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional

from data_provider.base import canonical_stock_code
from src.services.portfolio_service import (
    EPS,
    VALID_SIDES,
    PortfolioService,
)


class PaperAccountRequiredError(ValueError):
    """Raised when a paper-trading operation targets a non-paper account."""


class PaperQuoteUnavailableError(ValueError):
    """Raised when no explicit price is given and no quote can be resolved."""


class PaperInsufficientCashError(ValueError):
    """Raised when a simulated buy would exceed the account's available cash."""

    def __init__(self, *, required: float, available: float) -> None:
        self.required = float(required)
        self.available = max(0.0, float(available))
        super().__init__(
            "Insufficient paper cash: "
            f"required={round(self.required, 6)}, available={round(self.available, 6)}"
        )


class PaperPortfolioService:
    """Paper-specific rules layered over :class:`PortfolioService`."""

    def __init__(
        self,
        portfolio_service: Optional[PortfolioService] = None,
        *,
        kind_repo: Any = None,
    ):
        self.portfolio = portfolio_service or PortfolioService()
        self._kind_repo = kind_repo

    @property
    def kind_repo(self) -> Any:
        if self._kind_repo is None:
            self._kind_repo = self.portfolio.kind_repo
        return self._kind_repo

    def _require_paper_account(self, account_id: int) -> None:
        row = self.kind_repo.get(account_id=int(account_id))
        if row is None or str(getattr(row, "account_type", "")) != "paper":
            raise PaperAccountRequiredError(
                f"Account {account_id} is not a paper trading account"
            )

    def _resolve_fill_price(
        self,
        *,
        symbol: str,
        trade_date: date,
        price: Optional[float],
    ) -> Dict[str, Any]:
        """Return the fill price and its source.

        When ``price`` is provided it is used verbatim (manual fill). Otherwise
        the latest available daily close at/at-before ``trade_date`` is used, so
        there is no next-open lookahead ambiguity.
        """
        if price is not None:
            if float(price) <= 0:
                raise ValueError("price must be > 0")
            return {"price": float(price), "price_source": "manual"}
        canonical = canonical_stock_code(symbol)
        close = self.portfolio.repo.get_latest_close(canonical, trade_date)
        if close is None or float(close) <= 0:
            raise PaperQuoteUnavailableError(
                f"No quote available for {symbol} as of {trade_date.isoformat()}"
            )
        return {"price": float(close), "price_source": "latest_close"}

    def _available_cash(self, *, account_id: int, as_of: date) -> float:
        snapshot = self.portfolio.get_portfolio_snapshot(
            account_id=int(account_id),
            as_of=as_of,
            include_realtime=False,
        )
        for entry in snapshot.get("accounts", []):
            if int(entry.get("account_id")) == int(account_id):
                return float(entry.get("total_cash", 0.0))
        return 0.0

    def record_paper_trade(
        self,
        *,
        account_id: int,
        symbol: str,
        trade_date: date,
        side: str,
        quantity: float,
        price: Optional[float] = None,
        note: Optional[str] = None,
        operation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record a simulated buy/sell on a paper account.

        Reuses ``PortfolioService.record_trade`` for persistence and replay;
        fees/slippage are fixed to zero in the MVP.
        """
        side_norm = (side or "").strip().lower()
        if side_norm not in VALID_SIDES:
            raise ValueError("side must be buy or sell")
        if quantity <= 0:
            raise ValueError("quantity must be > 0")
        if not (symbol or "").strip():
            raise ValueError("symbol is required")

        self._require_paper_account(account_id)
        fill = self._resolve_fill_price(
            symbol=symbol, trade_date=trade_date, price=price
        )
        fill_price = fill["price"]

        if side_norm == "buy":
            available = self._available_cash(account_id=account_id, as_of=trade_date)
            required = float(quantity) * fill_price
            if required > available + EPS:
                raise PaperInsufficientCashError(
                    required=required, available=available
                )

        result = self.portfolio.record_trade(
            account_id=int(account_id),
            symbol=symbol,
            trade_date=trade_date,
            side=side_norm,
            quantity=float(quantity),
            price=fill_price,
            fee=0.0,
            tax=0.0,
            note=note,
            operation_id=operation_id,
        )
        result["price"] = fill_price
        result["price_source"] = fill["price_source"]
        return result
