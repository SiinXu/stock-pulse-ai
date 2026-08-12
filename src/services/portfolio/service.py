# -*- coding: utf-8 -*-
"""Account lifecycle and shared portfolio service helpers."""

from __future__ import annotations

from src.services.portfolio.models import DEFAULT_ACCOUNT_TYPE

class _PortfolioServiceCoreMethods:
    """Method group bound onto the public facade class."""

    @property
    def kind_repo(self) -> Any:
        if self._kind_repo is None:
            from src.repositories.portfolio_account_kind_repo import (
                PortfolioAccountKindRepository,
            )

            self._kind_repo = PortfolioAccountKindRepository()
        return self._kind_repo

    @staticmethod
    def _normalize_account_type(account_type: Optional[str]) -> str:
        value = (account_type or DEFAULT_ACCOUNT_TYPE).strip().lower()
        if value not in VALID_ACCOUNT_TYPES:
            raise ValueError("account_type must be real or paper")
        return value

    def create_account(
        self,
        *,
        name: str,
        broker: Optional[str],
        market: str,
        base_currency: str,
        owner_id: Optional[str] = None,
        account_type: str = DEFAULT_ACCOUNT_TYPE,
    ) -> Dict[str, Any]:
        name_norm = (name or "").strip()
        if not name_norm:
            raise ValueError("name is required")
        account_type_norm = self._normalize_account_type(account_type)
        market_norm = self._normalize_market(market)
        base_currency_norm = self._normalize_currency(base_currency)
        row = self.repo.create_account(
            name=name_norm,
            broker=(broker or "").strip() or None,
            market=market_norm,
            base_currency=base_currency_norm,
            owner_id=(owner_id or "").strip() or None,
        )
        result = self._account_to_dict(row)
        if account_type_norm == "paper":
            self.kind_repo.upsert(
                {"account_id": int(row.id), "account_type": "paper"}
            )
            self._seed_paper_cash(account_id=int(row.id), currency=base_currency_norm)
        result["account_type"] = account_type_norm
        return result

    def _seed_paper_cash(self, *, account_id: int, currency: str) -> None:
        """Seed a new paper account with the configurable initial cash balance."""
        initial_cash = float(
            getattr(get_config(), "paper_portfolio_initial_cash", 0.0) or 0.0
        )
        if initial_cash <= 0:
            return
        self.record_cash_ledger(
            account_id=account_id,
            event_date=self._now_provider().date(),
            direction="in",
            amount=initial_cash,
            currency=currency,
            note="Paper trading initial balance",
        )

    def list_accounts(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        rows = self.repo.list_accounts(include_inactive=include_inactive)
        result = [self._account_to_dict(r) for r in rows]
        if result:
            types = self.kind_repo.types_for(
                account_ids=[int(item["id"]) for item in result]
            )
            for item in result:
                item["account_type"] = types.get(int(item["id"]), DEFAULT_ACCOUNT_TYPE)
        return result

    def update_account(
        self,
        account_id: int,
        *,
        name: Optional[str] = None,
        broker: Optional[str] = None,
        market: Optional[str] = None,
        base_currency: Optional[str] = None,
        owner_id: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[Dict[str, Any]]:
        fields: Dict[str, Any] = {}
        if name is not None:
            name_norm = name.strip()
            if not name_norm:
                raise ValueError("name is required")
            fields["name"] = name_norm
        if broker is not None:
            fields["broker"] = broker.strip() or None
        if market is not None:
            fields["market"] = self._normalize_market(market)
        if base_currency is not None:
            fields["base_currency"] = self._normalize_currency(base_currency)
        if owner_id is not None:
            fields["owner_id"] = owner_id.strip() or None
        if is_active is not None:
            fields["is_active"] = bool(is_active)
        if not fields:
            raise ValueError("No fields provided for update")

        row = self.repo.update_account(account_id, fields)
        if row is None:
            return None
        result = self._account_to_dict(row)
        result["account_type"] = self.kind_repo.types_for(
            account_ids=[int(row.id)]
        ).get(int(row.id), DEFAULT_ACCOUNT_TYPE)
        return result

    def deactivate_account(self, account_id: int) -> bool:
        return self.repo.deactivate_account(account_id)

    def _require_active_account(self, account_id: int) -> Any:
        account = self.repo.get_account(account_id, include_inactive=False)
        if account is None:
            raise ValueError(f"Active account not found: {account_id}")
        return account

    def _require_active_account_in_session(self, *, session: Any, account_id: int) -> Any:
        account = self.repo.get_account_in_session(
            session=session,
            account_id=account_id,
            include_inactive=False,
        )
        if account is None:
            raise ValueError(f"Active account not found: {account_id}")
        return account

    @staticmethod
    def _account_to_dict(row: Any) -> Dict[str, Any]:
        return {
            "id": row.id,
            "owner_id": row.owner_id,
            "name": row.name,
            "broker": row.broker,
            "market": row.market,
            "base_currency": row.base_currency,
            "is_active": bool(row.is_active),
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def _validate_paging(*, page: int, page_size: int) -> Tuple[int, int]:
        if page < 1:
            raise ValueError("page must be >= 1")
        if page_size < 1 or page_size > 100:
            raise ValueError("page_size must be in [1, 100]")
        return page, page_size

    @staticmethod
    def _normalize_market(value: str) -> str:
        market = (value or "").strip().lower()
        if market not in VALID_MARKETS:
            raise ValueError("market must be one of: cn, hk, us, jp, kr, tw")
        return market

    @staticmethod
    def _normalize_currency(value: str) -> str:
        currency = (value or "").strip().upper()
        if not currency:
            raise ValueError("currency is required")
        return currency

    @staticmethod
    def _normalize_cost_method(value: str) -> str:
        method = (value or "").strip().lower()
        if method not in VALID_COST_METHODS:
            raise ValueError("cost_method must be fifo or avg")
        return method

    @staticmethod
    def _default_currency_for_market(market: str) -> str:
        if market == "hk":
            return "HKD"
        if market == "us":
            return "USD"
        return "CNY"
