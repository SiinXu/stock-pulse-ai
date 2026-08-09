# -*- coding: utf-8 -*-
"""Idempotent daily portfolio health snapshot persistence (issue #151).

Key: (account_key, snapshot_date, cost_method) where account_key is
str(account_id) or ``all``. Recompute overwrites the same day rather than
appending history rows.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from src.repositories.base import BaseRepository, RepositoryError
from src.storage import DatabaseManager
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

_ACCOUNT_KEY_ALL = "all"
_BUSY_RETRY_DELAYS_SECONDS = (0.02, 0.05, 0.10)


def _is_missing_schema(exc: BaseException) -> bool:
    return "no such table: portfolio_health_snapshots" in str(exc).lower()


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is not allowed: {value}")


def account_key_for(account_id: Optional[int]) -> str:
    if account_id is None:
        return _ACCOUNT_KEY_ALL
    return str(int(account_id))


class PortfolioHealthRepository(BaseRepository):
    """SQLite-backed upsert/get for daily health snapshots."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None) -> None:
        super().__init__(db_manager)

    def upsert_snapshot(
        self,
        *,
        account_id: Optional[int],
        snapshot_date: date,
        cost_method: str,
        payload: Dict[str, Any],
    ) -> None:
        """Insert or overwrite the daily health snapshot."""
        key = account_key_for(account_id)
        method = str(cost_method or "fifo").strip().lower() or "fifo"
        score = payload.get("score")
        status = str(payload.get("status") or "unknown")
        band = payload.get("band")
        payload_json = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            default=str,
        )
        now = datetime.now().replace(microsecond=0)
        context = {"account_key": key, "snapshot_date": snapshot_date.isoformat()}
        parameters = {
            "account_key": key,
            "snapshot_date": snapshot_date.isoformat(),
            "cost_method": method,
            "score": score,
            "status": status,
            "band": band,
            "payload_json": payload_json,
            "snapshot_hash": str(payload.get("provenance", {}).get("snapshot_hash") or ""),
            "risk_hash": str(payload.get("provenance", {}).get("risk_hash") or ""),
            "config_hash": str(payload.get("provenance", {}).get("config_hash") or ""),
            "calculated_at": str(payload.get("provenance", {}).get("calculated_at") or ""),
            "created_at": now.isoformat(sep=" "),
            "updated_at": now.isoformat(sep=" "),
        }
        statement = text(
            """
            INSERT INTO portfolio_health_snapshots (
                account_key, snapshot_date, cost_method,
                score, status, band, payload_json,
                snapshot_hash, risk_hash, config_hash, calculated_at,
                created_at, updated_at
            ) VALUES (
                :account_key, :snapshot_date, :cost_method,
                :score, :status, :band, :payload_json,
                :snapshot_hash, :risk_hash, :config_hash, :calculated_at,
                :created_at, :updated_at
            )
            ON CONFLICT(account_key, snapshot_date, cost_method) DO UPDATE SET
                score = excluded.score,
                status = excluded.status,
                band = excluded.band,
                payload_json = excluded.payload_json,
                snapshot_hash = excluded.snapshot_hash,
                risk_hash = excluded.risk_hash,
                config_hash = excluded.config_hash,
                calculated_at = excluded.calculated_at,
                updated_at = excluded.updated_at
            """
        )
        for attempt, delay in enumerate(_BUSY_RETRY_DELAYS_SECONDS, start=1):
            try:
                with self.db.get_session() as session:
                    session.execute(
                        statement,
                        parameters,
                    )
                    session.commit()
                return
            except OperationalError as exc:
                if _is_missing_schema(exc):
                    raise RepositoryError(
                        "Portfolio health migration is required",
                        error_code="portfolio_health_migration_required",
                        context=context,
                    ) from exc
                if "database is locked" in str(exc).lower() and attempt < len(
                    _BUSY_RETRY_DELAYS_SECONDS
                ):
                    time.sleep(delay)
                    continue
                self._log_and_raise(
                    logger,
                    "upsert portfolio health snapshot failed",
                    exc,
                    error_code="portfolio_health_upsert_busy"
                    if "database is locked" in str(exc).lower()
                    else "portfolio_health_upsert_error",
                    context=context,
                )
            except Exception as exc:  # broad-exception: fallback_recorded - repository boundary
                self._log_and_raise(
                    logger,
                    "upsert portfolio health snapshot failed",
                    exc,
                    error_code="portfolio_health_upsert_error",
                    context=context,
                )

    def get_snapshot(
        self,
        *,
        account_id: Optional[int],
        snapshot_date: date,
        cost_method: str = "fifo",
    ) -> Optional[Dict[str, Any]]:
        """Return the stored payload for the day, or None."""
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
            data = json.loads(
                payload_json or "{}",
                parse_constant=_reject_json_constant,
            )
            if not isinstance(data, dict):
                return None
            return data
        except OperationalError as exc:
            if _is_missing_schema(exc):
                raise RepositoryError(
                    "Portfolio health migration is required",
                    error_code="portfolio_health_migration_required",
                    context=context,
                ) from exc
            self._log_and_raise(
                logger,
                "get portfolio health snapshot failed",
                exc,
                error_code="portfolio_health_get_error",
                context=context,
            )
        except Exception as exc:  # broad-exception: fallback_recorded - repository boundary
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
