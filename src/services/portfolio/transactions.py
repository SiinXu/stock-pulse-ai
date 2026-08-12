# -*- coding: utf-8 -*-
"""Trade, cash, corporate-action, and idempotency write/list paths."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.services.portfolio_service import (
        Any,
        Callable,
        Dict,
        DuplicateTradeDedupHashError,
        DuplicateTradeUidError,
        EPS,
        List,
        Optional,
        PORTFOLIO_IDEMPOTENCY_REPLAY_WINDOW_DAYS_DEFAULT,
        PortfolioConflictError,
        PortfolioIdempotencyConflictError,
        PortfolioOversellError,
        PortfolioService,
        Tuple,
        VALID_CASH_DIRECTIONS,
        VALID_CORPORATE_ACTIONS,
        VALID_SIDES,
        build_portfolio_idempotency_scope_key,
        build_portfolio_idempotency_storage_id,
        date,
        datetime,
        get_config,
        hashlib,
        json,
        timedelta,
    )

class _PortfolioTransactionMethods:
    """Method group bound onto the public facade class."""

    def record_trade(
        self,
        *,
        account_id: int,
        symbol: str,
        trade_date: date,
        side: str,
        quantity: float,
        price: float,
        fee: float = 0.0,
        tax: float = 0.0,
        market: Optional[str] = None,
        currency: Optional[str] = None,
        trade_uid: Optional[str] = None,
        dedup_hash: Optional[str] = None,
        note: Optional[str] = None,
        operation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        side_norm = (side or "").strip().lower()
        if side_norm not in VALID_SIDES:
            raise ValueError("side must be buy or sell")
        if quantity <= 0 or price <= 0:
            raise ValueError("quantity and price must be > 0")
        if fee < 0 or tax < 0:
            raise ValueError("fee and tax must be >= 0")
        symbol_norm = self._normalize_symbol_for_storage(symbol)
        if not symbol_norm:
            raise ValueError("symbol is required")
        trade_uid_norm = (trade_uid or "").strip() or None
        dedup_hash_norm = (dedup_hash or "").strip() or None
        operation_payload = {
            "account_id": int(account_id),
            "symbol": symbol_norm,
            "trade_date": trade_date.isoformat(),
            "side": side_norm,
            "quantity": float(quantity),
            "price": float(price),
            "fee": float(fee),
            "tax": float(tax),
            "market": self._normalize_market(market) if market else None,
            "currency": self._normalize_currency(currency) if currency else None,
            "trade_uid": trade_uid_norm,
            "dedup_hash": dedup_hash_norm,
            "note": (note or "").strip() or None,
        }
        with self.repo.portfolio_write_session() as session:
            replay = self.replay_operation_in_session(
                session=session,
                operation_id=operation_id,
                operation_type="trade.create",
                scope_account_id=account_id,
                payload=operation_payload,
            )
            if replay is not None:
                return replay
            result = self.record_trade_in_session(
                session=session,
                account_id=account_id,
                symbol=symbol_norm,
                trade_date=trade_date,
                side=side_norm,
                quantity=float(quantity),
                price=float(price),
                fee=float(fee),
                tax=float(tax),
                market=market,
                currency=currency,
                trade_uid=trade_uid_norm,
                dedup_hash=dedup_hash_norm,
                note=note,
            )
            self.store_operation_result_in_session(
                session=session,
                operation_id=operation_id,
                operation_type="trade.create",
                scope_account_id=account_id,
                payload=operation_payload,
                response=result,
            )
            return result

    def record_trade_in_session(
        self,
        *,
        session: Any,
        account_id: int,
        symbol: str,
        trade_date: date,
        side: str,
        quantity: float,
        price: float,
        fee: float = 0.0,
        tax: float = 0.0,
        market: Optional[str] = None,
        currency: Optional[str] = None,
        trade_uid: Optional[str] = None,
        dedup_hash: Optional[str] = None,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        side_norm = (side or "").strip().lower()
        if side_norm not in VALID_SIDES:
            raise ValueError("side must be buy or sell")
        if quantity <= 0 or price <= 0:
            raise ValueError("quantity and price must be > 0")
        if fee < 0 or tax < 0:
            raise ValueError("fee and tax must be >= 0")
        symbol_norm = self._normalize_symbol_for_storage(symbol)
        if not symbol_norm:
            raise ValueError("symbol is required")
        trade_uid_norm = (trade_uid or "").strip() or None
        dedup_hash_norm = (dedup_hash or "").strip() or None
        account = self._require_active_account_in_session(session=session, account_id=account_id)
        market_norm = self._normalize_market(market or account.market)
        currency_norm = self._normalize_currency(currency or self._default_currency_for_market(market_norm))
        self._validate_trade_identity(
            account_id=account_id,
            trade_uid=trade_uid_norm,
            dedup_hash=dedup_hash_norm,
            session=session,
        )
        if side_norm == "sell":
            self._validate_sell_quantity(
                account_id=account_id,
                symbol=symbol_norm,
                market=market_norm,
                currency=currency_norm,
                trade_date=trade_date,
                quantity=float(quantity),
                session=session,
            )
        try:
            row = self.repo.add_trade_in_session(
                session=session,
                account_id=account_id,
                trade_uid=trade_uid_norm,
                symbol=symbol_norm,
                market=market_norm,
                currency=currency_norm,
                trade_date=trade_date,
                side=side_norm,
                quantity=float(quantity),
                price=float(price),
                fee=float(fee),
                tax=float(tax),
                note=(note or "").strip() or None,
                dedup_hash=dedup_hash_norm,
            )
        except (DuplicateTradeUidError, DuplicateTradeDedupHashError) as exc:
            raise PortfolioConflictError(str(exc)) from exc
        return {"id": int(row.id)}

    def record_cash_ledger(
        self,
        *,
        account_id: int,
        event_date: date,
        direction: str,
        amount: float,
        currency: Optional[str] = None,
        note: Optional[str] = None,
        operation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        direction_norm = (direction or "").strip().lower()
        if direction_norm not in VALID_CASH_DIRECTIONS:
            raise ValueError("direction must be in or out")
        if amount <= 0:
            raise ValueError("amount must be > 0")
        operation_payload = {
            "account_id": int(account_id),
            "event_date": event_date.isoformat(),
            "direction": direction_norm,
            "amount": float(amount),
            "currency": self._normalize_currency(currency) if currency else None,
            "note": (note or "").strip() or None,
        }
        with self.repo.portfolio_write_session() as session:
            replay = self.replay_operation_in_session(
                session=session,
                operation_id=operation_id,
                operation_type="cash_ledger.create",
                scope_account_id=account_id,
                payload=operation_payload,
            )
            if replay is not None:
                return replay
            account = self._require_active_account_in_session(session=session, account_id=account_id)
            currency_norm = self._normalize_currency(currency or account.base_currency)
            row = self.repo.add_cash_ledger_in_session(
                session=session,
                account_id=account_id,
                event_date=event_date,
                direction=direction_norm,
                amount=float(amount),
                currency=currency_norm,
                note=(note or "").strip() or None,
            )
            result = {"id": int(row.id)}
            self.store_operation_result_in_session(
                session=session,
                operation_id=operation_id,
                operation_type="cash_ledger.create",
                scope_account_id=account_id,
                payload=operation_payload,
                response=result,
            )
            return result

    def record_corporate_action(
        self,
        *,
        account_id: int,
        symbol: str,
        effective_date: date,
        action_type: str,
        market: Optional[str] = None,
        currency: Optional[str] = None,
        cash_dividend_per_share: Optional[float] = None,
        split_ratio: Optional[float] = None,
        note: Optional[str] = None,
        operation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        action_type_norm = (action_type or "").strip().lower()
        if action_type_norm not in VALID_CORPORATE_ACTIONS:
            raise ValueError("action_type must be cash_dividend or split_adjustment")

        if action_type_norm == "cash_dividend":
            if cash_dividend_per_share is None or cash_dividend_per_share < 0:
                raise ValueError("cash_dividend_per_share must be >= 0 for cash_dividend")
        if action_type_norm == "split_adjustment":
            if split_ratio is None or split_ratio <= 0:
                raise ValueError("split_ratio must be > 0 for split_adjustment")
        symbol_norm = self._normalize_symbol_for_storage(symbol)
        if not symbol_norm:
            raise ValueError("symbol is required")
        operation_payload = {
            "account_id": int(account_id),
            "symbol": symbol_norm,
            "effective_date": effective_date.isoformat(),
            "action_type": action_type_norm,
            "market": self._normalize_market(market) if market else None,
            "currency": self._normalize_currency(currency) if currency else None,
            "cash_dividend_per_share": float(cash_dividend_per_share) if cash_dividend_per_share is not None else None,
            "split_ratio": float(split_ratio) if split_ratio is not None else None,
            "note": (note or "").strip() or None,
        }
        with self.repo.portfolio_write_session() as session:
            replay = self.replay_operation_in_session(
                session=session,
                operation_id=operation_id,
                operation_type="corporate_action.create",
                scope_account_id=account_id,
                payload=operation_payload,
            )
            if replay is not None:
                return replay
            account = self._require_active_account_in_session(session=session, account_id=account_id)
            market_norm = self._normalize_market(market or account.market)
            currency_norm = self._normalize_currency(currency or self._default_currency_for_market(market_norm))
            row = self.repo.add_corporate_action_in_session(
                session=session,
                account_id=account_id,
                symbol=symbol_norm,
                market=market_norm,
                currency=currency_norm,
                effective_date=effective_date,
                action_type=action_type_norm,
                cash_dividend_per_share=cash_dividend_per_share,
                split_ratio=split_ratio,
                note=(note or "").strip() or None,
            )
            result = {"id": int(row.id)}
            self.store_operation_result_in_session(
                session=session,
                operation_id=operation_id,
                operation_type="corporate_action.create",
                scope_account_id=account_id,
                payload=operation_payload,
                response=result,
            )
            return result

    def delete_trade_event(self, trade_id: int) -> bool:
        with self.repo.portfolio_write_session() as session:
            return self.repo.delete_trade_in_session(session=session, trade_id=trade_id)

    def delete_cash_ledger_event(self, entry_id: int) -> bool:
        with self.repo.portfolio_write_session() as session:
            return self.repo.delete_cash_ledger_in_session(session=session, entry_id=entry_id)

    def delete_corporate_action_event(self, action_id: int) -> bool:
        with self.repo.portfolio_write_session() as session:
            return self.repo.delete_corporate_action_in_session(session=session, action_id=action_id)

    def list_trade_events(
        self,
        *,
        account_id: Optional[int] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        symbol: Optional[str] = None,
        side: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        if account_id is not None:
            self._require_active_account(account_id)
        page, page_size = self._validate_paging(page=page, page_size=page_size)
        if date_from is not None and date_to is not None and date_from > date_to:
            raise ValueError("date_from must be <= date_to")

        symbol_filters: Optional[List[str]] = None
        if symbol is not None and symbol.strip():
            symbol_filters = self._build_symbol_filter_values(symbol)
            if not symbol_filters:
                raise ValueError("symbol is invalid")

        side_norm: Optional[str] = None
        if side is not None and side.strip():
            side_norm = side.strip().lower()
            if side_norm not in VALID_SIDES:
                raise ValueError("side must be buy or sell")

        rows, total = self.repo.query_trades(
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            symbols=symbol_filters,
            side=side_norm,
            page=page,
            page_size=page_size,
        )
        return {
            "items": [self._trade_row_to_dict(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def list_cash_ledger_events(
        self,
        *,
        account_id: Optional[int] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        direction: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        if account_id is not None:
            self._require_active_account(account_id)
        page, page_size = self._validate_paging(page=page, page_size=page_size)
        if date_from is not None and date_to is not None and date_from > date_to:
            raise ValueError("date_from must be <= date_to")

        direction_norm: Optional[str] = None
        if direction is not None and direction.strip():
            direction_norm = direction.strip().lower()
            if direction_norm not in VALID_CASH_DIRECTIONS:
                raise ValueError("direction must be in or out")

        rows, total = self.repo.query_cash_ledger(
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            direction=direction_norm,
            page=page,
            page_size=page_size,
        )
        return {
            "items": [self._cash_ledger_row_to_dict(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def list_corporate_action_events(
        self,
        *,
        account_id: Optional[int] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        symbol: Optional[str] = None,
        action_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        if account_id is not None:
            self._require_active_account(account_id)
        page, page_size = self._validate_paging(page=page, page_size=page_size)
        if date_from is not None and date_to is not None and date_from > date_to:
            raise ValueError("date_from must be <= date_to")

        symbol_filters: Optional[List[str]] = None
        if symbol is not None and symbol.strip():
            symbol_filters = self._build_symbol_filter_values(symbol)
            if not symbol_filters:
                raise ValueError("symbol is invalid")

        action_norm: Optional[str] = None
        if action_type is not None and action_type.strip():
            action_norm = action_type.strip().lower()
            if action_norm not in VALID_CORPORATE_ACTIONS:
                raise ValueError("action_type must be cash_dividend or split_adjustment")

        rows, total = self.repo.query_corporate_actions(
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            symbols=symbol_filters,
            action_type=action_norm,
            page=page,
            page_size=page_size,
        )
        return {
            "items": [self._corporate_action_row_to_dict(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    @staticmethod
    def normalize_operation_id(operation_id: Optional[str]) -> Optional[str]:
        if operation_id is None:
            return None
        value = str(operation_id).strip()
        if not value:
            raise ValueError("operation_id must not be blank")
        if len(value) > 128:
            raise ValueError("operation_id must be at most 128 characters")
        if any(char.isspace() or ord(char) < 32 for char in value):
            raise ValueError("operation_id must not contain whitespace or control characters")
        return value

    @staticmethod
    def _operation_request_hash(payload: Any) -> str:
        serialized = json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            default=PortfolioService._serialize_operation_value,
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def _serialize_operation_value(value: Any) -> Any:
        if isinstance(value, date):
            return value.isoformat()
        item = getattr(value, "item", None)
        if callable(item):
            return item()
        raise TypeError(f"Unsupported operation payload value: {type(value).__name__}")

    def replay_operation_in_session(
        self,
        *,
        session: Any,
        operation_id: Optional[str],
        operation_type: str,
        scope_account_id: int,
        payload: Any,
        compatible_payload_from_response: Optional[
            Callable[[Dict[str, Any]], Optional[Any]]
        ] = None,
    ) -> Optional[Dict[str, Any]]:
        operation_id_norm = self.normalize_operation_id(operation_id)
        if operation_id_norm is None:
            return None
        cutoff = self._idempotency_replay_cutoff()
        self.repo.delete_expired_idempotency_records_in_session(
            session=session,
            created_at_before=cutoff,
        )
        _scope_owner_id, scope_key = self._resolve_idempotency_scope_in_session(
            session=session,
            account_id=scope_account_id,
        )
        request_hash = self._operation_request_hash(payload)
        existing = self.repo.get_idempotency_record_in_session(
            session=session,
            operation_type=operation_type,
            scope_key=scope_key,
            client_operation_id=operation_id_norm,
            created_at_from=cutoff,
        )
        if existing is None:
            # Raw-key legacy rows cannot prove historical owner scope. Startup
            # migration preserves them unscoped, and this scoped query therefore
            # fails closed to a new operation without crossing owner boundaries.
            return None
        response = None
        if existing.request_hash != request_hash:
            compatible_payload = None
            if compatible_payload_from_response is not None:
                # Derive compatibility only from the already scope-checked
                # record; the reconstructed request must still match its hash.
                response = json.loads(existing.response_json)
                if isinstance(response, dict):
                    compatible_payload = compatible_payload_from_response(response)
            if (
                compatible_payload is None
                or existing.request_hash
                != self._operation_request_hash(compatible_payload)
            ):
                raise PortfolioIdempotencyConflictError(
                    "operation_id already used for a different request: "
                    f"{operation_id_norm}"
                )
        if response is None:
            response = json.loads(existing.response_json)
        if not isinstance(response, dict):
            raise RuntimeError(f"Invalid stored response for operation_id={operation_id_norm}")
        return response

    def store_operation_result_in_session(
        self,
        *,
        session: Any,
        operation_id: Optional[str],
        operation_type: str,
        scope_account_id: int,
        payload: Any,
        response: Dict[str, Any],
    ) -> None:
        operation_id_norm = self.normalize_operation_id(operation_id)
        if operation_id_norm is None:
            return
        scope_owner_id, scope_key = self._resolve_idempotency_scope_in_session(
            session=session,
            account_id=scope_account_id,
        )
        self.repo.add_idempotency_record_in_session(
            session=session,
            operation_id=build_portfolio_idempotency_storage_id(
                operation_type=operation_type,
                scope_key=scope_key,
                client_operation_id=operation_id_norm,
            ),
            client_operation_id=operation_id_norm,
            operation_type=operation_type,
            scope_key=scope_key,
            scope_account_id=int(scope_account_id),
            scope_owner_id=scope_owner_id,
            request_hash=self._operation_request_hash(payload),
            response_json=json.dumps(
                response,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ),
            created_at=self._now_provider(),
        )

    def _idempotency_replay_cutoff(self) -> datetime:
        """Return the inclusive lower bound for replayable operations."""

        config = get_config()
        replay_window_days = int(
            getattr(
                config,
                "portfolio_idempotency_replay_window_days",
                PORTFOLIO_IDEMPOTENCY_REPLAY_WINDOW_DAYS_DEFAULT,
            )
        )
        return self._now_provider() - timedelta(days=max(1, replay_window_days))

    def _resolve_idempotency_scope_in_session(
        self,
        *,
        session: Any,
        account_id: int,
    ) -> Tuple[Optional[str], str]:
        """Resolve the current owner and stable scope key for an account."""

        account = self.repo.get_account_in_session(
            session=session,
            account_id=int(account_id),
            include_inactive=True,
        )
        owner_id = None
        if account is not None and account.owner_id is not None:
            owner_id = str(account.owner_id).strip() or None
        return (
            owner_id,
            build_portfolio_idempotency_scope_key(
                account_id=int(account_id),
                owner_id=owner_id,
            ),
        )

    def _validate_trade_identity(
        self,
        *,
        account_id: int,
        trade_uid: Optional[str],
        dedup_hash: Optional[str],
        session: Optional[Any] = None,
    ) -> None:
        if trade_uid and self._has_trade_uid(account_id=account_id, trade_uid=trade_uid, session=session):
            raise PortfolioConflictError(f"Duplicate trade_uid for account_id={account_id}: {trade_uid}")
        if dedup_hash and self._has_trade_dedup_hash(account_id=account_id, dedup_hash=dedup_hash, session=session):
            raise PortfolioConflictError(f"Duplicate dedup_hash for account_id={account_id}: {dedup_hash}")

    def _validate_sell_quantity(
        self,
        *,
        account_id: int,
        symbol: str,
        market: str,
        currency: str,
        trade_date: date,
        quantity: float,
        session: Optional[Any] = None,
    ) -> None:
        key = (
            self._normalize_symbol_for_position(symbol),
            self._normalize_market(market),
            self._normalize_currency(currency),
        )
        available_quantity = self._calculate_available_quantity(
            account_id=account_id,
            key=key,
            as_of_date=trade_date,
            session=session,
        )
        if available_quantity + EPS < quantity:
            raise PortfolioOversellError(
                symbol=key[0],
                trade_date=trade_date,
                requested_quantity=quantity,
                available_quantity=available_quantity,
            )

    def _calculate_available_quantity(
        self,
        *,
        account_id: int,
        key: Tuple[str, str, str],
        as_of_date: date,
        session: Optional[Any] = None,
    ) -> float:
        if session is None:
            trades = self.repo.list_trades(account_id, as_of=as_of_date)
            corporate_actions = self.repo.list_corporate_actions(account_id, as_of=as_of_date)
        else:
            trades = self.repo.list_trades_in_session(session=session, account_id=account_id, as_of=as_of_date)
            corporate_actions = self.repo.list_corporate_actions_in_session(
                session=session,
                account_id=account_id,
                as_of=as_of_date,
            )

        events = []
        for row in corporate_actions:
            event_key = (
                self._normalize_symbol_for_position(row.symbol),
                self._normalize_market(row.market),
                self._normalize_currency(row.currency),
            )
            if event_key == key:
                events.append(("corp", row.effective_date, row.id, row))
        for row in trades:
            event_key = (
                self._normalize_symbol_for_position(row.symbol),
                self._normalize_market(row.market),
                self._normalize_currency(row.currency),
            )
            if event_key == key:
                events.append(("trade", row.trade_date, row.id, row))

        # Quantity validation only depends on position-changing events for one symbol.
        # Cash ledger entries do not affect shares held, so we keep the same corp->trade
        # ordering as full replay without pulling unrelated cash events into this path.
        event_priority = {"corp": 1, "trade": 2}
        events.sort(key=lambda item: (item[1], event_priority[item[0]], item[2]))

        quantity_held = 0.0
        for event_type, event_date, _, event in events:
            if event_type == "corp":
                action_type = (event.action_type or "").strip().lower()
                if action_type != "split_adjustment":
                    continue
                split_ratio = float(event.split_ratio or 0.0)
                if split_ratio <= 0:
                    raise ValueError(f"Invalid split_ratio for {key[0]}")
                if abs(split_ratio - 1.0) <= EPS:
                    continue
                quantity_held *= split_ratio
                continue

            qty = float(event.quantity or 0.0)
            if qty <= 0:
                raise ValueError(f"Invalid trade quantity for {key[0]}")
            side = (event.side or "").strip().lower()
            if side == "buy":
                quantity_held += qty
                continue
            if side != "sell":
                raise ValueError(f"Unsupported trade side: {event.side}")
            if quantity_held + EPS < qty:
                raise PortfolioOversellError(
                    symbol=key[0],
                    trade_date=event_date,
                    requested_quantity=qty,
                    available_quantity=quantity_held,
                )
            quantity_held -= qty
            if quantity_held <= EPS:
                quantity_held = 0.0

        return quantity_held

    def _has_trade_uid(self, *, account_id: int, trade_uid: str, session: Optional[Any] = None) -> bool:
        if session is None:
            return self.repo.has_trade_uid(account_id, trade_uid)
        return self.repo.has_trade_uid_in_session(session=session, account_id=account_id, trade_uid=trade_uid)

    def _has_trade_dedup_hash(
        self,
        *,
        account_id: int,
        dedup_hash: str,
        session: Optional[Any] = None,
    ) -> bool:
        if session is None:
            return self.repo.has_trade_dedup_hash(account_id, dedup_hash)
        return self.repo.has_trade_dedup_hash_in_session(
            session=session,
            account_id=account_id,
            dedup_hash=dedup_hash,
        )

    @staticmethod
    def _trade_row_to_dict(row: Any) -> Dict[str, Any]:
        return {
            "id": int(row.id),
            "account_id": int(row.account_id),
            "trade_uid": row.trade_uid,
            "symbol": row.symbol,
            "market": row.market,
            "currency": row.currency,
            "trade_date": row.trade_date.isoformat() if row.trade_date else "",
            "side": row.side,
            "quantity": float(row.quantity),
            "price": float(row.price),
            "fee": float(row.fee),
            "tax": float(row.tax),
            "note": row.note,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    @staticmethod
    def _cash_ledger_row_to_dict(row: Any) -> Dict[str, Any]:
        return {
            "id": int(row.id),
            "account_id": int(row.account_id),
            "event_date": row.event_date.isoformat() if row.event_date else "",
            "direction": row.direction,
            "amount": float(row.amount),
            "currency": row.currency,
            "note": row.note,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    @staticmethod
    def _corporate_action_row_to_dict(row: Any) -> Dict[str, Any]:
        return {
            "id": int(row.id),
            "account_id": int(row.account_id),
            "symbol": row.symbol,
            "market": row.market,
            "currency": row.currency,
            "effective_date": row.effective_date.isoformat() if row.effective_date else "",
            "action_type": row.action_type,
            "cash_dividend_per_share": (
                float(row.cash_dividend_per_share) if row.cash_dividend_per_share is not None else None
            ),
            "split_ratio": float(row.split_ratio) if row.split_ratio is not None else None,
            "note": row.note,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
