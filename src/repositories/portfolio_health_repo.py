# -*- coding: utf-8 -*-
"""Idempotent daily portfolio health snapshot persistence (issue #151).

Key: (account_key, snapshot_date, cost_method) where account_key is
str(account_id) or ``all``. Recompute overwrites the same day rather than
appending history rows.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Any, Dict, Optional

from sqlalchemy import text

from src.repositories.base import BaseRepository, RepositoryError
from src.storage import DatabaseManager
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

_ACCOUNT_KEY_ALL = "all"


def account_key_for(account_id: Optional[int]) -> str:
    if account_id is None:
        return _ACCOUNT_KEY_ALL
    return str(int(account_id))


class PortfolioHealthRepository(BaseRepository):
    """SQLite-backed upsert/get for daily health snapshots."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None) -> None:
        super().__init__(db_manager)
        self._ensured = False

    def ensure_schema(self) -> None:
        """Create the snapshot table if missing (restart-idempotent)."""
        if self._ensured:
            return
        try:
            with self.db.get_session() as session:
                session.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS portfolio_health_snapshots (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            account_key VARCHAR(32) NOT NULL,
                            snapshot_date DATE NOT NULL,
                            cost_method VARCHAR(8) NOT NULL DEFAULT 'fifo',
                            score FLOAT,
                            status VARCHAR(32) NOT NULL,
                            band VARCHAR(16),
                            payload_json TEXT NOT NULL,
                            created_at DATETIME NOT NULL,
                            updated_at DATETIME NOT NULL
                        )
                        """
                    )
                )
                session.execute(
                    text(
                        """
                        CREATE UNIQUE INDEX IF NOT EXISTS
                        uix_portfolio_health_account_date_method
                        ON portfolio_health_snapshots
                        (account_key, snapshot_date, cost_method)
                        """
                    )
                )
                session.commit()
            self._ensured = True
        except Exception as exc:  # broad-exception: fallback_recorded - surface as repository error
            log_safe_exception(
                logger,
                "ensure portfolio_health_snapshots schema failed",
                exc,
                error_code="portfolio_health_schema_error",
            )
            raise RepositoryError(
                "ensure portfolio_health_snapshots schema failed",
                error_code="portfolio_health_schema_error",
            ) from exc

    def upsert_snapshot(
        self,
        *,
        account_id: Optional[int],
        snapshot_date: date,
        cost_method: str,
        payload: Dict[str, Any],
    ) -> None:
        """Insert or overwrite the daily health snapshot."""
        self.ensure_schema()
        key = account_key_for(account_id)
        method = str(cost_method or "fifo").strip().lower() or "fifo"
        score = payload.get("score")
        status = str(payload.get("status") or "unknown")
        band = payload.get("band")
        payload_json = json.dumps(payload, ensure_ascii=False, default=str)
        now = datetime.now().replace(microsecond=0)
        context = {"account_key": key, "snapshot_date": snapshot_date.isoformat()}
        try:
            with self.db.get_session() as session:
                existing = session.execute(
                    text(
                        """
                        SELECT id FROM portfolio_health_snapshots
                        WHERE account_key = :account_key
                          AND snapshot_date = :snapshot_date
                          AND cost_method = :cost_method
                        LIMIT 1
                        """
                    ),
                    {
                        "account_key": key,
                        "snapshot_date": snapshot_date.isoformat(),
                        "cost_method": method,
                    },
                ).fetchone()
                if existing is None:
                    session.execute(
                        text(
                            """
                            INSERT INTO portfolio_health_snapshots (
                                account_key, snapshot_date, cost_method,
                                score, status, band, payload_json,
                                created_at, updated_at
                            ) VALUES (
                                :account_key, :snapshot_date, :cost_method,
                                :score, :status, :band, :payload_json,
                                :created_at, :updated_at
                            )
                            """
                        ),
                        {
                            "account_key": key,
                            "snapshot_date": snapshot_date.isoformat(),
                            "cost_method": method,
                            "score": score,
                            "status": status,
                            "band": band,
                            "payload_json": payload_json,
                            "created_at": now.isoformat(sep=" "),
                            "updated_at": now.isoformat(sep=" "),
                        },
                    )
                else:
                    session.execute(
                        text(
                            """
                            UPDATE portfolio_health_snapshots
                            SET score = :score,
                                status = :status,
                                band = :band,
                                payload_json = :payload_json,
                                updated_at = :updated_at
                            WHERE account_key = :account_key
                              AND snapshot_date = :snapshot_date
                              AND cost_method = :cost_method
                            """
                        ),
                        {
                            "account_key": key,
                            "snapshot_date": snapshot_date.isoformat(),
                            "cost_method": method,
                            "score": score,
                            "status": status,
                            "band": band,
                            "payload_json": payload_json,
                            "updated_at": now.isoformat(sep=" "),
                        },
                    )
                session.commit()
        except Exception as exc:  # broad-exception: fallback_recorded - surface as repository error
            log_safe_exception(
                logger,
                "upsert portfolio health snapshot failed",
                exc,
                error_code="portfolio_health_upsert_error",
                context=context,
            )
            raise RepositoryError(
                "upsert portfolio health snapshot failed",
                error_code="portfolio_health_upsert_error",
                context=context,
            ) from exc

    def get_snapshot(
        self,
        *,
        account_id: Optional[int],
        snapshot_date: date,
        cost_method: str = "fifo",
    ) -> Optional[Dict[str, Any]]:
        """Return the stored payload for the day, or None."""
        self.ensure_schema()
        key = account_key_for(account_id)
        method = str(cost_method or "fifo").strip().lower() or "fifo"
        context = {"account_key": key, "snapshot_date": snapshot_date.isoformat()}
        try:
            with self.db.get_session() as session:
                row = session.execute(
                    text(
                        """
                        SELECT payload_json FROM portfolio_health_snapshots
                        WHERE account_key = :account_key
                          AND snapshot_date = :snapshot_date
                          AND cost_method = :cost_method
                        LIMIT 1
                        """
                    ),
                    {
                        "account_key": key,
                        "snapshot_date": snapshot_date.isoformat(),
                        "cost_method": method,
                    },
                ).fetchone()
            if row is None:
                return None
            payload_json = row[0] if not hasattr(row, "payload_json") else row.payload_json
            data = json.loads(payload_json or "{}")
            if not isinstance(data, dict):
                return None
            return data
        except Exception as exc:  # broad-exception: fallback_recorded - surface as repository error
            log_safe_exception(
                logger,
                "get portfolio health snapshot failed",
                exc,
                error_code="portfolio_health_get_error",
                context=context,
            )
            raise RepositoryError(
                "get portfolio health snapshot failed",
                error_code="portfolio_health_get_error",
                context=context,
            ) from exc
