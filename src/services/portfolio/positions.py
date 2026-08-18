# -*- coding: utf-8 -*-
"""Position replay, snapshot construction, and price resolution."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.services.portfolio_service import (
        Any,
        Dict,
        EPS,
        Iterable,
        List,
        Optional,
        PORTFOLIO_REALTIME_QUOTE_MAX_WORKERS,
        PortfolioAccount,
        PortfolioOversellError,
        Set,
        ThreadPoolExecutor,
        Tuple,
        _AvgState,
        _ResolvedPositionPrice,
        _merge_portfolio_limitations,
        _portfolio_limitations_for_market,
        as_completed,
        canonical_stock_code,
        date,
        defaultdict,
        json,
        log_safe_exception,
        logger,
        logging,
        normalize_stock_code,
    )

class _PortfolioPositionMethods:
    """Method group bound onto the public facade class."""

    def get_portfolio_snapshot(
        self,
        *,
        account_id: Optional[int] = None,
        as_of: Optional[date] = None,
        cost_method: str = "fifo",
        include_realtime: bool = True,
    ) -> Dict[str, Any]:
        """Build and materialize the canonical portfolio snapshot."""
        return self._build_portfolio_snapshot(
            account_id=account_id,
            as_of=as_of,
            cost_method=cost_method,
            include_realtime=include_realtime,
            materialize=True,
        )

    def preview_portfolio_snapshot(
        self,
        *,
        account_id: Optional[int] = None,
        as_of: Optional[date] = None,
        cost_method: str = "fifo",
        include_realtime: bool = False,
    ) -> Dict[str, Any]:
        """Replay the canonical snapshot without writing derived cache rows."""
        return self._build_portfolio_snapshot(
            account_id=account_id,
            as_of=as_of,
            cost_method=cost_method,
            include_realtime=include_realtime,
            materialize=False,
        )

    def _build_portfolio_snapshot(
        self,
        *,
        account_id: Optional[int],
        as_of: Optional[date],
        cost_method: str,
        include_realtime: bool,
        materialize: bool,
    ) -> Dict[str, Any]:
        as_of_date = as_of or date.today()
        method = self._normalize_cost_method(cost_method)

        if account_id is not None:
            account = self._require_active_account(account_id)
            account_rows = [account]
        else:
            account_rows = self.repo.list_accounts(include_inactive=False)

        accounts_payload: List[Dict[str, Any]] = []
        aggregate_currency = "CNY"
        aggregate = {
            "total_cash": 0.0,
            "total_market_value": 0.0,
            "total_equity": 0.0,
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
            "fee_total": 0.0,
            "tax_total": 0.0,
            "fx_stale": False,
            "limitations": [],
        }

        for account in account_rows:
            account_snapshot = self._replay_account(
                account=account,
                as_of_date=as_of_date,
                cost_method=method,
                include_realtime=include_realtime,
            )

            if materialize:
                self.repo.replace_positions_lots_and_snapshot(
                    account_id=account.id,
                    snapshot_date=as_of_date,
                    cost_method=method,
                    base_currency=account.base_currency,
                    total_cash=account_snapshot["total_cash"],
                    total_market_value=account_snapshot["total_market_value"],
                    total_equity=account_snapshot["total_equity"],
                    unrealized_pnl=account_snapshot["unrealized_pnl"],
                    realized_pnl=account_snapshot["realized_pnl"],
                    fee_total=account_snapshot["fee_total"],
                    tax_total=account_snapshot["tax_total"],
                    fx_stale=account_snapshot["fx_stale"],
                    payload=json.dumps(account_snapshot["payload"], ensure_ascii=False),
                    positions=account_snapshot["positions_cache"],
                    lots=account_snapshot["lots_cache"],
                    valuation_currency=account.base_currency,
                )

            accounts_payload.append(account_snapshot["public"])
            aggregate["limitations"] = _merge_portfolio_limitations(
                aggregate["limitations"],
                account_snapshot["public"].get("limitations", []),
            )

            cash_cny, stale_cash, _ = self._convert_amount(
                amount=account_snapshot["total_cash"],
                from_currency=account.base_currency,
                to_currency=aggregate_currency,
                as_of_date=as_of_date,
            )
            mv_cny, stale_mv, _ = self._convert_amount(
                amount=account_snapshot["total_market_value"],
                from_currency=account.base_currency,
                to_currency=aggregate_currency,
                as_of_date=as_of_date,
            )
            eq_cny, stale_eq, _ = self._convert_amount(
                amount=account_snapshot["total_equity"],
                from_currency=account.base_currency,
                to_currency=aggregate_currency,
                as_of_date=as_of_date,
            )
            realized_cny, stale_realized, _ = self._convert_amount(
                amount=account_snapshot["realized_pnl"],
                from_currency=account.base_currency,
                to_currency=aggregate_currency,
                as_of_date=as_of_date,
            )
            unrealized_cny, stale_unrealized, _ = self._convert_amount(
                amount=account_snapshot["unrealized_pnl"],
                from_currency=account.base_currency,
                to_currency=aggregate_currency,
                as_of_date=as_of_date,
            )
            fee_cny, stale_fee, _ = self._convert_amount(
                amount=account_snapshot["fee_total"],
                from_currency=account.base_currency,
                to_currency=aggregate_currency,
                as_of_date=as_of_date,
            )
            tax_cny, stale_tax, _ = self._convert_amount(
                amount=account_snapshot["tax_total"],
                from_currency=account.base_currency,
                to_currency=aggregate_currency,
                as_of_date=as_of_date,
            )

            aggregate["total_cash"] += cash_cny
            aggregate["total_market_value"] += mv_cny
            aggregate["total_equity"] += eq_cny
            aggregate["realized_pnl"] += realized_cny
            aggregate["unrealized_pnl"] += unrealized_cny
            aggregate["fee_total"] += fee_cny
            aggregate["tax_total"] += tax_cny
            aggregate["fx_stale"] = aggregate["fx_stale"] or any(
                [
                    stale_cash,
                    stale_mv,
                    stale_eq,
                    stale_realized,
                    stale_unrealized,
                    stale_fee,
                    stale_tax,
                ]
            )

        return {
            "as_of": as_of_date.isoformat(),
            "cost_method": method,
            "currency": aggregate_currency,
            "account_count": len(account_rows),
            "total_cash": round(aggregate["total_cash"], 6),
            "total_market_value": round(aggregate["total_market_value"], 6),
            "total_equity": round(aggregate["total_equity"], 6),
            "realized_pnl": round(aggregate["realized_pnl"], 6),
            "unrealized_pnl": round(aggregate["unrealized_pnl"], 6),
            "fee_total": round(aggregate["fee_total"], 6),
            "tax_total": round(aggregate["tax_total"], 6),
            "fx_stale": aggregate["fx_stale"],
            "data_quality": "partial" if aggregate["limitations"] else "ok",
            "limitations": aggregate["limitations"],
            "accounts": accounts_payload,
        }

    def get_available_cash_in_session(
        self,
        *,
        session: Any,
        account_id: int,
        as_of: date,
    ) -> float:
        """Replay an account in the caller's transaction and return its cash."""

        account = self._require_active_account_in_session(
            session=session,
            account_id=int(account_id),
        )
        replay = self._replay_account(
            account=account,
            as_of_date=as_of,
            cost_method="fifo",
            include_realtime=False,
            session=session,
        )
        return float(replay["total_cash"])

    def _replay_account(
        self,
        *,
        account: PortfolioAccount,
        as_of_date: date,
        cost_method: str,
        include_realtime: bool,
        session: Optional[Any] = None,
    ) -> Dict[str, Any]:
        if session is None:
            trades = self.repo.list_trades(account.id, as_of=as_of_date)
            cash_ledger = self.repo.list_cash_ledger(account.id, as_of=as_of_date)
            corporate_actions = self.repo.list_corporate_actions(
                account.id,
                as_of=as_of_date,
            )
        else:
            trades = self.repo.list_trades_in_session(
                session=session,
                account_id=account.id,
                as_of=as_of_date,
            )
            cash_ledger = self.repo.list_cash_ledger_in_session(
                session=session,
                account_id=account.id,
                as_of=as_of_date,
            )
            corporate_actions = self.repo.list_corporate_actions_in_session(
                session=session,
                account_id=account.id,
                as_of=as_of_date,
            )

        events = []
        for row in cash_ledger:
            events.append(("cash", row.event_date, row.id, row))
        for row in trades:
            events.append(("trade", row.trade_date, row.id, row))
        for row in corporate_actions:
            events.append(("corp", row.effective_date, row.id, row))

        # Same-day deterministic ordering: cash -> corporate action -> trade.
        event_priority = {"cash": 0, "corp": 1, "trade": 2}
        events.sort(key=lambda item: (item[1], event_priority[item[0]], item[2]))

        cash_balances: Dict[str, float] = defaultdict(float)
        fees_total_base = 0.0
        taxes_total_base = 0.0
        realized_pnl_base = 0.0
        fx_stale = False

        fifo_lots: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)
        avg_state: Dict[Tuple[str, str, str], _AvgState] = defaultdict(_AvgState)

        for event_type, event_date, _, event in events:
            if event_type == "cash":
                currency = self._normalize_currency(event.currency)
                amount = float(event.amount or 0.0)
                if event.direction == "in":
                    cash_balances[currency] += amount
                elif event.direction == "out":
                    cash_balances[currency] -= amount
                else:
                    raise ValueError(f"Unsupported cash direction: {event.direction}")
                continue

            if event_type == "trade":
                key = (
                    self._normalize_symbol_for_position(event.symbol),
                    self._normalize_market(event.market),
                    self._normalize_currency(event.currency),
                )
                qty = float(event.quantity or 0.0)
                price = float(event.price or 0.0)
                fee = float(event.fee or 0.0)
                tax = float(event.tax or 0.0)
                if qty <= 0 or price <= 0:
                    raise ValueError(f"Invalid trade quantity or price for {event.symbol}")

                gross = qty * price
                side = (event.side or "").lower().strip()
                if side == "buy":
                    cash_balances[key[2]] -= (gross + fee + tax)
                    if cost_method == "fifo":
                        unit_cost = (gross + fee + tax) / qty
                        fifo_lots[key].append(
                            {
                                "symbol": key[0],
                                "market": key[1],
                                "currency": key[2],
                                "open_date": event_date,
                                "remaining_quantity": qty,
                                "unit_cost": unit_cost,
                                "source_trade_id": event.id,
                            }
                        )
                    else:
                        state = avg_state[key]
                        state.quantity += qty
                        state.total_cost += (gross + fee + tax)
                elif side == "sell":
                    cash_balances[key[2]] += (gross - fee - tax)
                    proceeds_net = gross - fee - tax
                    if cost_method == "fifo":
                        cost_basis = self._consume_fifo_lots(
                            fifo_lots[key],
                            qty,
                            key[0],
                            event_date,
                        )
                    else:
                        cost_basis = self._consume_avg_position(
                            avg_state[key],
                            qty,
                            key[0],
                            event_date,
                        )
                    realized_local = proceeds_net - cost_basis
                    realized_base, stale_realized, _ = self._convert_amount(
                        amount=realized_local,
                        from_currency=key[2],
                        to_currency=account.base_currency,
                        as_of_date=event_date,
                    )
                    realized_pnl_base += realized_base
                    fx_stale = fx_stale or stale_realized
                else:
                    raise ValueError(f"Unsupported trade side: {event.side}")

                fee_base, stale_fee, _ = self._convert_amount(
                    amount=fee,
                    from_currency=key[2],
                    to_currency=account.base_currency,
                    as_of_date=event_date,
                )
                tax_base, stale_tax, _ = self._convert_amount(
                    amount=tax,
                    from_currency=key[2],
                    to_currency=account.base_currency,
                    as_of_date=event_date,
                )
                fees_total_base += fee_base
                taxes_total_base += tax_base
                fx_stale = fx_stale or stale_fee or stale_tax
                continue

            if event_type == "corp":
                key = (
                    self._normalize_symbol_for_position(event.symbol),
                    self._normalize_market(event.market),
                    self._normalize_currency(event.currency),
                )
                action_type = (event.action_type or "").strip().lower()
                if action_type == "cash_dividend":
                    per_share = float(event.cash_dividend_per_share or 0.0)
                    if per_share <= 0:
                        continue
                    qty_held = self._held_quantity(
                        key=key,
                        cost_method=cost_method,
                        fifo_lots=fifo_lots,
                        avg_state=avg_state,
                    )
                    if qty_held > EPS:
                        cash_balances[key[2]] += qty_held * per_share
                elif action_type == "split_adjustment":
                    split_ratio = float(event.split_ratio or 0.0)
                    if split_ratio <= 0:
                        raise ValueError(f"Invalid split_ratio for {event.symbol}")
                    if abs(split_ratio - 1.0) <= EPS:
                        continue
                    if cost_method == "fifo":
                        for lot in fifo_lots[key]:
                            lot["remaining_quantity"] *= split_ratio
                            lot["unit_cost"] /= split_ratio
                    else:
                        state = avg_state[key]
                        state.quantity *= split_ratio
                else:
                    raise ValueError(f"Unsupported corporate action type: {event.action_type}")

        position_rows, lot_rows, market_value_base, total_cost_base, stale_pos = self._build_positions(
            account=account,
            as_of_date=as_of_date,
            cost_method=cost_method,
            fifo_lots=fifo_lots,
            avg_state=avg_state,
            include_realtime=include_realtime,
        )
        fx_stale = fx_stale or stale_pos

        total_cash_base = 0.0
        for currency, amount in cash_balances.items():
            converted, stale, _ = self._convert_amount(
                amount=amount,
                from_currency=currency,
                to_currency=account.base_currency,
                as_of_date=as_of_date,
            )
            total_cash_base += converted
            fx_stale = fx_stale or stale

        unrealized_pnl_base = market_value_base - total_cost_base
        total_equity_base = total_cash_base + market_value_base
        position_limitations = [
            limitation
            for position in position_rows
            for limitation in position.get("limitations", [])
        ]
        limitations = _merge_portfolio_limitations(
            _portfolio_limitations_for_market(account.market),
            position_limitations,
        )

        account_payload = {
            "account_id": account.id,
            "account_name": account.name,
            "owner_id": account.owner_id,
            "broker": account.broker,
            "market": account.market,
            "base_currency": account.base_currency,
            "as_of": as_of_date.isoformat(),
            "cost_method": cost_method,
            "total_cash": round(total_cash_base, 6),
            "total_market_value": round(market_value_base, 6),
            "total_equity": round(total_equity_base, 6),
            "realized_pnl": round(realized_pnl_base, 6),
            "unrealized_pnl": round(unrealized_pnl_base, 6),
            "fee_total": round(fees_total_base, 6),
            "tax_total": round(taxes_total_base, 6),
            "fx_stale": fx_stale,
            "data_quality": "partial" if limitations else "ok",
            "limitations": limitations,
            "positions": position_rows,
        }

        return {
            "public": account_payload,
            "payload": account_payload,
            "positions_cache": position_rows,
            "lots_cache": lot_rows,
            "total_cash": float(total_cash_base),
            "total_market_value": float(market_value_base),
            "total_equity": float(total_equity_base),
            "realized_pnl": float(realized_pnl_base),
            "unrealized_pnl": float(unrealized_pnl_base),
            "fee_total": float(fees_total_base),
            "tax_total": float(taxes_total_base),
            "fx_stale": fx_stale,
        }

    def _build_positions(
        self,
        *,
        account: PortfolioAccount,
        as_of_date: date,
        cost_method: str,
        fifo_lots: Dict[Tuple[str, str, str], List[Dict[str, Any]]],
        avg_state: Dict[Tuple[str, str, str], _AvgState],
        include_realtime: bool = True,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], float, float, bool]:
        position_rows: List[Dict[str, Any]] = []
        lot_rows: List[Dict[str, Any]] = []
        market_value_base = 0.0
        total_cost_base = 0.0
        fx_stale = False

        keys: Iterable[Tuple[str, str, str]]
        if cost_method == "fifo":
            keys = list(fifo_lots.keys())
        else:
            keys = list(avg_state.keys())

        active_symbols: List[str] = []
        if include_realtime and as_of_date == date.today():
            for key in sorted(keys):
                symbol, _, _ = key
                if cost_method == "fifo":
                    qty = sum(
                        float(lot["remaining_quantity"])
                        for lot in fifo_lots[key]
                        if lot["remaining_quantity"] > EPS
                    )
                else:
                    qty = float(avg_state[key].quantity)
                if qty > EPS:
                    active_symbols.append(symbol)
        realtime_prices = (
            self._prefetch_realtime_position_prices(active_symbols)
            if active_symbols
            else None
        )

        for key in sorted(keys):
            symbol, market, currency = key

            if cost_method == "fifo":
                active_lots = [lot for lot in fifo_lots[key] if lot["remaining_quantity"] > EPS]
                qty = sum(float(lot["remaining_quantity"]) for lot in active_lots)
                if qty <= EPS:
                    continue
                total_cost = sum(float(lot["remaining_quantity"]) * float(lot["unit_cost"]) for lot in active_lots)
                avg_cost = total_cost / qty
                lot_rows.extend(active_lots)
            else:
                state = avg_state[key]
                qty = float(state.quantity)
                total_cost = float(state.total_cost)
                if qty <= EPS:
                    continue
                avg_cost = total_cost / qty
                lot_rows.append(
                    {
                        "symbol": symbol,
                        "market": market,
                        "currency": currency,
                        "open_date": as_of_date,
                        "remaining_quantity": qty,
                        "unit_cost": avg_cost,
                        "source_trade_id": None,
                    }
                )

            price_info = self._resolve_position_price(
                symbol=symbol,
                as_of_date=as_of_date,
                realtime_prices=realtime_prices,
                include_realtime=include_realtime,
            )
            last_price = price_info.price
            limitations = _portfolio_limitations_for_market(market)

            if price_info.is_available:
                local_market_value = qty * float(last_price)
                market_conversion = self._convert_amount_with_provenance(
                    amount=local_market_value,
                    from_currency=currency,
                    to_currency=account.base_currency,
                    as_of_date=as_of_date,
                )
                cost_conversion = self._convert_amount_with_provenance(
                    amount=total_cost,
                    from_currency=currency,
                    to_currency=account.base_currency,
                    as_of_date=as_of_date,
                )
                market_base = float(market_conversion["converted_amount"])
                cost_base = float(cost_conversion["converted_amount"])
                stale_market = bool(market_conversion["is_stale"])
                stale_cost = bool(cost_conversion["is_stale"])
                unrealized_base = market_base - cost_base
                fx_stale = fx_stale or stale_market or stale_cost
            else:
                market_base = 0.0
                cost_base = 0.0
                unrealized_base = 0.0
                market_conversion = None

            unrealized_pct = None
            if abs(cost_base) > EPS:
                unrealized_pct = unrealized_base / cost_base * 100.0

            position_rows.append(
                {
                    "symbol": symbol,
                    "market": market,
                    "currency": currency,
                    "quantity": round(qty, 8),
                    "avg_cost": round(avg_cost, 8),
                    "total_cost": round(total_cost, 8),
                    "last_price": round(float(last_price), 8),
                    "market_value_base": round(market_base, 8),
                    "valuation_fx_rate_to_account_base": (
                        round(float(market_conversion["rate"]), 12)
                        if market_conversion is not None
                        else None
                    ),
                    "valuation_fx_rate_source": (
                        str(market_conversion["source"])
                        if market_conversion is not None
                        else None
                    ),
                    "valuation_fx_rate_method": (
                        str(market_conversion["method"])
                        if market_conversion is not None
                        else None
                    ),
                    "valuation_fx_as_of": (
                        market_conversion["rate_date"].isoformat()
                        if (
                            market_conversion is not None
                            and market_conversion.get("rate_date") is not None
                        )
                        else None
                    ),
                    "valuation_fx_stale": (
                        bool(market_conversion["is_stale"])
                        if market_conversion is not None
                        else False
                    ),
                    "unrealized_pnl_base": round(unrealized_base, 8),
                    "unrealized_pnl_pct": round(unrealized_pct, 8) if unrealized_pct is not None else None,
                    "valuation_currency": account.base_currency,
                    "price_source": price_info.source,
                    "price_provider": price_info.provider,
                    "price_date": price_info.price_date.isoformat() if price_info.price_date else None,
                    "price_stale": price_info.is_stale,
                    "price_available": price_info.is_available,
                    "data_quality": "partial" if limitations else "ok",
                    "limitations": limitations,
                }
            )

            market_value_base += market_base
            total_cost_base += cost_base

        return position_rows, lot_rows, market_value_base, total_cost_base, fx_stale

    def _resolve_position_price(
        self,
        *,
        symbol: str,
        as_of_date: date,
        realtime_prices: Optional[Dict[str, Tuple[Optional[float], Optional[str]]]] = None,
        include_realtime: bool = True,
    ) -> _ResolvedPositionPrice:
        today = date.today()

        if include_realtime and as_of_date == today:
            if realtime_prices is None:
                realtime_price, provider = self._fetch_realtime_position_price(symbol)
            else:
                realtime_price, provider = realtime_prices.get(symbol, (None, None))
            if realtime_price is not None and realtime_price > 0:
                return _ResolvedPositionPrice(
                    price=float(realtime_price),
                    source="realtime_quote",
                    price_date=today,
                    is_stale=False,
                    is_available=True,
                    provider=provider,
                )

        close = self.repo.get_latest_close_with_date(symbol=symbol, as_of=as_of_date)
        if close is not None:
            close_price, close_date = close
            if close_price > 0:
                return _ResolvedPositionPrice(
                    price=float(close_price),
                    source="history_close",
                    price_date=close_date,
                    is_stale=close_date < as_of_date,
                    is_available=True,
                )

        return _ResolvedPositionPrice(
            price=0.0,
            source="missing",
            price_date=None,
            is_stale=True,
            is_available=False,
        )

    def _prefetch_realtime_position_prices(
        self,
        symbols: Iterable[str],
    ) -> Dict[str, Tuple[Optional[float], Optional[str]]]:
        unique_symbols = sorted({symbol for symbol in symbols if symbol})
        if not unique_symbols:
            return {}

        # Bulk prefetch (when applicable) only warms the fetcher-module-level realtime cache;
        # the manager itself is discarded so per-symbol workers cannot serialize through its
        # per-fetcher call locks when individual reads still need a live fetch (e.g. mixed
        # markets, cache miss, or bulk source returning fewer rows than requested).
        if len(unique_symbols) >= 5:
            try:
                from src.data_provider.base import DataFetcherManager

                DataFetcherManager().prefetch_realtime_quotes(unique_symbols)
            except Exception as exc:  # broad-exception: fallback_recorded - quote prefetch is best-effort for snapshots
                log_safe_exception(
                    logger,
                    "Portfolio realtime quote batch prefetch failed",
                    exc,
                    error_code="portfolio_realtime_quote_prefetch_failed",
                    level=logging.WARNING,
                    context={"symbol_count": len(unique_symbols)},
                )

        if len(unique_symbols) == 1:
            symbol = unique_symbols[0]
            return {symbol: self._fetch_realtime_position_price(symbol)}

        results: Dict[str, Tuple[Optional[float], Optional[str]]] = {}
        max_workers = min(PORTFOLIO_REALTIME_QUOTE_MAX_WORKERS, len(unique_symbols))
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="portfolio-quote") as executor:
            futures = {
                executor.submit(self._fetch_realtime_position_price, symbol): symbol
                for symbol in unique_symbols
            }
            for future in as_completed(futures):
                symbol = futures[future]
                try:
                    results[symbol] = future.result()
                except Exception as exc:  # pragma: no cover - broad-exception: fallback_recorded - worker failure is recorded and skipped
                    log_safe_exception(
                        logger,
                        "Portfolio realtime price worker failed",
                        exc,
                        error_code="portfolio_realtime_price_worker_failed",
                        level=logging.WARNING,
                        context={"stock_code": symbol},
                    )
                    results[symbol] = (None, None)

        return results

    @staticmethod
    def _fetch_realtime_position_price(symbol: str) -> Tuple[Optional[float], Optional[str]]:
        try:
            from src.data_provider.base import DataFetcherManager

            fetcher_manager = DataFetcherManager()
            quote = fetcher_manager.get_realtime_quote(symbol, log_final_failure=False)
        except Exception as exc:  # broad-exception: fallback_recorded - single-symbol quote failure degrades to unavailable price
            log_safe_exception(
                logger,
                "Portfolio realtime price lookup failed",
                exc,
                error_code="portfolio_realtime_price_lookup_failed",
                level=logging.WARNING,
                context={"stock_code": symbol},
            )
            return None, None

        if quote is None:
            return None, None

        price = getattr(quote, "price", None)
        try:
            numeric_price = float(price)
        except (TypeError, ValueError):
            return None, None

        if numeric_price <= 0:
            return None, None

        source = getattr(quote, "source", None)
        provider = getattr(source, "value", None) or (str(source) if source is not None else None)
        return numeric_price, provider

    @staticmethod
    def _normalize_symbol_for_storage(symbol: str) -> str:
        return canonical_stock_code(symbol)

    @staticmethod
    def _normalize_symbol_for_position(symbol: str) -> str:
        if not (symbol or "").strip():
            return ""

        raw = canonical_stock_code(symbol)
        if len(raw) >= 8 and raw[:2] in {"SH", "SZ", "BJ"} and raw[2:].isdigit():
            return raw

        if "." in raw:
            base, suffix = raw.rsplit(".", 1)
            if base.isdigit() and suffix in {"SH", "SS", "SZ", "BJ"}:
                exchange = "SH" if suffix == "SS" else suffix
                return f"{exchange}{base}"

        return canonical_stock_code(normalize_stock_code(symbol))

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        """
        Canonicalization for symbol filtering with exchange-qualified input preservation.

        Keep explicit A-share exchange annotations (SH/SZ/BJ) intact to avoid collapsing
        different exchange variants of the same 6-digit core code.
        """
        raw = canonical_stock_code(symbol)
        if not raw:
            return ""

        if len(raw) >= 8 and raw[:2] in {"SH", "SZ", "BJ"} and raw[2:].isdigit():
            return raw

        if "." in raw:
            base, suffix = raw.rsplit(".", 1)
            if base.isdigit() and suffix in {"SH", "SS", "SZ", "BJ"}:
                exchange = "SH" if suffix == "SS" else suffix
                return f"{exchange}{base}"

        return canonical_stock_code(normalize_stock_code(symbol))

    @classmethod
    def _build_symbol_filter_values(cls, symbol: str) -> List[str]:
        original = (symbol or "").strip().upper()
        normalized = cls._normalize_symbol(original)
        if not normalized:
            return []

        seen: Set[str] = set()
        values: List[str] = []

        def _add(value: Optional[str]) -> None:
            candidate = (value or "").strip().upper()
            if candidate and candidate not in seen:
                seen.add(candidate)
                values.append(candidate)

        _add(original)
        _add(normalized)

        if normalized.startswith("HK"):
            hk_digits = normalized[2:]
            if hk_digits.isdigit() and len(hk_digits) == 5:
                legacy_hk_digits = str(int(hk_digits))
                _add(f"HK{hk_digits}")
                _add(f"HK{legacy_hk_digits}")
                _add(f"{hk_digits}.HK")
                _add(f"{legacy_hk_digits}.HK")
            return values

        explicit_exchange: Optional[str] = None
        if len(original) >= 8 and original[:2] in {"SH", "SZ", "BJ"} and original[2:].isdigit():
            explicit_exchange = original[:2]
            explicit_code = original[2:]
        elif "." in original:
            base, suffix = original.rsplit(".", 1)
            if base.isdigit() and suffix in {"SH", "SS", "SZ", "BJ"}:
                explicit_exchange = "SH" if suffix == "SS" else suffix
                explicit_code = base
            else:
                explicit_code = None
        else:
            explicit_code = None

        if normalized.isdigit():
            if len(normalized) == 6:
                exchanges = [explicit_exchange] if explicit_exchange else ["SH", "SZ", "BJ"]
                for exchange in exchanges:
                    if exchange is None:
                        continue
                    _add(f"{exchange}{normalized}")
                    _add(f"{normalized}.{'SS' if exchange == 'SH' else exchange}")
                    if exchange == "SH":
                        _add(f"{normalized}.SH")
            return values

        if explicit_exchange is not None and explicit_code is not None and explicit_code.isdigit():
            if len(explicit_code) == 6:
                _add(f"{explicit_exchange}{explicit_code}")
                _add(f"{explicit_code}.{'SS' if explicit_exchange == 'SH' else explicit_exchange}")
                if explicit_exchange == "SH":
                    _add(f"{explicit_code}.SH")
            elif len(normalized) == 5:
                _add(f"HK{normalized}")
                _add(f"{normalized}.HK")

        return values

    @staticmethod
    def _consume_fifo_lots(
        lots: List[Dict[str, Any]],
        quantity: float,
        symbol: str,
        trade_date: Optional[date] = None,
    ) -> float:
        remaining = quantity
        cost_basis = 0.0
        while remaining > EPS:
            if not lots:
                raise PortfolioOversellError(
                    symbol=symbol,
                    trade_date=trade_date,
                    requested_quantity=quantity,
                    available_quantity=quantity - remaining,
                )
            head = lots[0]
            take = min(remaining, float(head["remaining_quantity"]))
            cost_basis += take * float(head["unit_cost"])
            head["remaining_quantity"] = float(head["remaining_quantity"]) - take
            remaining -= take
            if head["remaining_quantity"] <= EPS:
                lots.pop(0)
        return cost_basis

    @staticmethod
    def _consume_avg_position(
        state: _AvgState,
        quantity: float,
        symbol: str,
        trade_date: Optional[date] = None,
    ) -> float:
        if state.quantity + EPS < quantity:
            raise PortfolioOversellError(
                symbol=symbol,
                trade_date=trade_date,
                requested_quantity=quantity,
                available_quantity=state.quantity,
            )
        if state.quantity <= EPS:
            raise PortfolioOversellError(
                symbol=symbol,
                trade_date=trade_date,
                requested_quantity=quantity,
                available_quantity=0.0,
            )
        avg_cost = state.total_cost / state.quantity
        cost_basis = avg_cost * quantity
        state.quantity -= quantity
        state.total_cost -= cost_basis
        if state.quantity <= EPS:
            state.quantity = 0.0
            state.total_cost = 0.0
        return cost_basis

    @staticmethod
    def _held_quantity(
        *,
        key: Tuple[str, str, str],
        cost_method: str,
        fifo_lots: Dict[Tuple[str, str, str], List[Dict[str, Any]]],
        avg_state: Dict[Tuple[str, str, str], _AvgState],
    ) -> float:
        if cost_method == "fifo":
            return sum(float(lot["remaining_quantity"]) for lot in fifo_lots.get(key, []))
        return float(avg_state.get(key, _AvgState()).quantity)
