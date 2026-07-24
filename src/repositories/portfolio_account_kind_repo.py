# -*- coding: utf-8 -*-
"""Repository for the portfolio account-kind sidecar (Issue #370).

Keeps the paper/real classification in a dedicated table so paper trading is an
additive layer over the existing portfolio domain and never alters the frozen
``portfolio_accounts`` schema. A missing row means the account is ``real``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select

from src.storage import (
    DatabaseManager,
    PortfolioAccountKind,
    utc_naive_now,
)


class PortfolioAccountKindRepository:
    """DB access for the per-account paper/real sidecar table."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or DatabaseManager.get_instance()

    def get(self, *, account_id: int) -> Optional[PortfolioAccountKind]:
        with self.db.get_session() as session:
            return session.execute(
                select(PortfolioAccountKind)
                .where(PortfolioAccountKind.account_id == account_id)
                .limit(1)
            ).scalar_one_or_none()

    def list_for_accounts(
        self,
        *,
        account_ids: List[int],
    ) -> List[PortfolioAccountKind]:
        if not account_ids:
            return []
        with self.db.get_session() as session:
            rows = session.execute(
                select(PortfolioAccountKind).where(
                    PortfolioAccountKind.account_id.in_(account_ids)
                )
            ).scalars().all()
            return list(rows)

    def types_for(self, *, account_ids: List[int]) -> Dict[int, str]:
        """Map account_id -> account_type for the given ids (absent = 'real')."""
        rows = self.list_for_accounts(account_ids=account_ids)
        return {int(row.account_id): str(row.account_type) for row in rows}

    def upsert(self, fields: Dict[str, Any]) -> PortfolioAccountKind:
        now = utc_naive_now()
        with self.db.get_session() as session:
            existing = session.execute(
                select(PortfolioAccountKind)
                .where(PortfolioAccountKind.account_id == fields["account_id"])
                .limit(1)
            ).scalar_one_or_none()
            if existing is None:
                row = PortfolioAccountKind(**fields)
                session.add(row)
                session.commit()
                session.refresh(row)
                return row

            for key, value in fields.items():
                if key in {"id", "account_id", "created_at"}:
                    continue
                setattr(existing, key, value)
            existing.updated_at = now
            session.commit()
            session.refresh(existing)
            return existing
