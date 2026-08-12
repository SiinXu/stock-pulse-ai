# -*- coding: utf-8 -*-
"""FX conversion and account risk/valuation helpers for portfolio snapshots."""

from __future__ import annotations

class _PortfolioRiskMethods:
    """Method group bound onto the public facade class."""

    def refresh_fx_rates(
        self,
        *,
        account_id: Optional[int] = None,
        as_of: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Refresh account FX pairs online with stale fallback when fetch fails."""
        as_of_date = as_of or date.today()
        config = get_config()
        refresh_enabled = bool(getattr(config, "portfolio_fx_update_enabled", True))
        if account_id is not None:
            account_rows = [self._require_active_account(account_id)]
        else:
            account_rows = self.repo.list_accounts(include_inactive=False)

        summary = {
            "as_of": as_of_date.isoformat(),
            "account_count": len(account_rows),
            "refresh_enabled": refresh_enabled,
            "disabled_reason": None if refresh_enabled else PORTFOLIO_FX_REFRESH_DISABLED_REASON,
            "pair_count": 0,
            "updated_count": 0,
            "stale_count": 0,
            "error_count": 0,
        }
        for account in account_rows:
            item = self._refresh_account_fx_rates(
                account=account,
                as_of_date=as_of_date,
                refresh_enabled=refresh_enabled,
            )
            summary["pair_count"] += item["pair_count"]
            summary["updated_count"] += item["updated_count"]
            summary["stale_count"] += item["stale_count"]
            summary["error_count"] += item["error_count"]
        return summary

    def _convert_amount(
        self,
        *,
        amount: float,
        from_currency: str,
        to_currency: str,
        as_of_date: date,
    ) -> Tuple[float, bool, str]:
        provenance = self._convert_amount_with_provenance(
            amount=amount,
            from_currency=from_currency,
            to_currency=to_currency,
            as_of_date=as_of_date,
        )
        return (
            float(provenance["converted_amount"]),
            bool(provenance["is_stale"]),
            str(provenance["method"]),
        )

    def _convert_amount_with_provenance(
        self,
        *,
        amount: float,
        from_currency: str,
        to_currency: str,
        as_of_date: date,
    ) -> Dict[str, Any]:
        """Convert an amount and retain the exact cached-rate provenance."""
        from_norm = self._normalize_currency(from_currency)
        to_norm = self._normalize_currency(to_currency)
        if abs(amount) <= EPS:
            return {
                "converted_amount": 0.0,
                "rate": 1.0,
                "is_stale": False,
                "method": "zero",
                "source": "not_applicable",
                "rate_date": None,
            }
        if from_norm == to_norm:
            return {
                "converted_amount": float(amount),
                "rate": 1.0,
                "is_stale": False,
                "method": "identity",
                "source": "identity",
                "rate_date": None,
            }

        direct = self.repo.get_latest_fx_rate(
            from_currency=from_norm,
            to_currency=to_norm,
            as_of=as_of_date,
        )
        if direct is not None and direct.rate > 0:
            rate = float(direct.rate)
            return {
                "converted_amount": float(amount) * rate,
                "rate": rate,
                "is_stale": bool(direct.is_stale),
                "method": "direct_rate",
                "source": str(direct.source or "unknown"),
                "rate_date": direct.rate_date,
            }

        inverse = self.repo.get_latest_fx_rate(
            from_currency=to_norm,
            to_currency=from_norm,
            as_of=as_of_date,
        )
        if inverse is not None and inverse.rate > 0:
            rate = 1.0 / float(inverse.rate)
            return {
                "converted_amount": float(amount) * rate,
                "rate": rate,
                "is_stale": bool(inverse.is_stale),
                "method": "inverse_rate",
                "source": str(inverse.source or "unknown"),
                "rate_date": inverse.rate_date,
            }

        # P0 fallback: keep pipeline available even when FX cache is missing.
        return {
            "converted_amount": float(amount),
            "rate": 1.0,
            "is_stale": True,
            "method": "fallback_1_to_1",
            "source": "fallback",
            "rate_date": None,
        }

    def convert_amount(
        self,
        *,
        amount: float,
        from_currency: str,
        to_currency: str,
        as_of_date: date,
    ) -> Tuple[float, bool, str]:
        """Public conversion entry for cross-service consumers."""
        return self._convert_amount(
            amount=amount,
            from_currency=from_currency,
            to_currency=to_currency,
            as_of_date=as_of_date,
        )

    def convert_amount_with_provenance(
        self,
        *,
        amount: float,
        from_currency: str,
        to_currency: str,
        as_of_date: date,
    ) -> Dict[str, Any]:
        """Public conversion entry with rate source, date, method, and quality."""
        return self._convert_amount_with_provenance(
            amount=amount,
            from_currency=from_currency,
            to_currency=to_currency,
            as_of_date=as_of_date,
        )

    def _list_account_refresh_fx_currencies(
        self,
        *,
        account: PortfolioAccount,
        as_of_date: date,
        strict: bool = True,
    ) -> List[str]:
        """Return distinct non-base currencies participating in refresh for one account."""
        base_currency = self._normalize_currency(account.base_currency)
        currencies: Set[str] = set()
        rows = list(self.repo.list_trades(account.id, as_of=as_of_date))
        rows.extend(self.repo.list_cash_ledger(account.id, as_of=as_of_date))
        for row in rows:
            try:
                currency = self._normalize_currency(row.currency)
            except ValueError:
                if strict:
                    raise
                logger.warning(
                    "Skip invalid FX refresh currency for account %s on %s: %r",
                    account.id,
                    as_of_date.isoformat(),
                    getattr(row, "currency", None),
                )
                continue
            if currency != base_currency:
                currencies.add(currency)
        return sorted(currencies)

    def _refresh_account_fx_rates(
        self,
        *,
        account: PortfolioAccount,
        as_of_date: date,
        refresh_enabled: bool,
    ) -> Dict[str, int]:
        """Refresh FX pairs for one account and keep stale fallback on failures."""
        refresh_currencies = self._list_account_refresh_fx_currencies(
            account=account,
            as_of_date=as_of_date,
            strict=refresh_enabled,
        )
        if not refresh_enabled:
            return {
                "pair_count": len(refresh_currencies),
                "updated_count": 0,
                "stale_count": 0,
                "error_count": 0,
            }

        base_currency = self._normalize_currency(account.base_currency)
        summary = {
            "pair_count": len(refresh_currencies),
            "updated_count": 0,
            "stale_count": 0,
            "error_count": 0,
        }
        for from_currency in refresh_currencies:
            try:
                rate = self._fetch_fx_rate_from_yfinance(
                    from_currency=from_currency,
                    to_currency=base_currency,
                    as_of_date=as_of_date,
                )
                if rate is not None and rate > 0:
                    self.repo.save_fx_rate(
                        from_currency=from_currency,
                        to_currency=base_currency,
                        rate_date=as_of_date,
                        rate=rate,
                        source="yfinance",
                        is_stale=False,
                    )
                    summary["updated_count"] += 1
                    continue
            except Exception as exc:
                log_safe_exception(
                    logger,
                    "Portfolio FX online lookup failed",
                    exc,
                    error_code="portfolio_fx_online_lookup_failed",
                    level=logging.WARNING,
                    context={
                        "from_currency": from_currency,
                        "to_currency": base_currency,
                        "as_of": as_of_date.isoformat(),
                    },
                )

            fallback = self.repo.get_latest_fx_rate(
                from_currency=from_currency,
                to_currency=base_currency,
                as_of=as_of_date,
            )
            if fallback is not None and float(fallback.rate or 0.0) > 0:
                self.repo.save_fx_rate(
                    from_currency=from_currency,
                    to_currency=base_currency,
                    rate_date=as_of_date,
                    rate=float(fallback.rate),
                    source=(fallback.source or "cache_fallback"),
                    is_stale=True,
                )
                summary["stale_count"] += 1
            else:
                summary["error_count"] += 1
        return summary

    @staticmethod
    def _fetch_fx_rate_from_yfinance(
        *,
        from_currency: str,
        to_currency: str,
        as_of_date: date,
    ) -> Optional[float]:
        """Fetch latest available FX close rate around as_of date."""
        if yf is None:
            return None
        symbol = f"{from_currency}{to_currency}=X"
        ticker = yf.Ticker(symbol)
        history = ticker.history(
            start=(as_of_date - timedelta(days=7)).isoformat(),
            end=(as_of_date + timedelta(days=1)).isoformat(),
            interval="1d",
            auto_adjust=False,
        )
        if history is None or history.empty or "Close" not in history:
            return None
        close = history["Close"].dropna()
        if close.empty:
            return None
        value = float(close.iloc[-1])
        if value <= 0:
            return None
        return value
