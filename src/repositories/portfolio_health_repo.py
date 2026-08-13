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

    def list_recent_snapshots(
        self,
        *,
        updated_from: Optional[datetime] = None,
        limit: int = 500,
    ) -> list[Dict[str, Any]]:
        """Return newest durable health snapshots for inbox projection.

        Rows are ordered by ``updated_at`` descending, then ``id`` descending.
        Missing-schema failures raise ``RepositoryError`` with
        ``portfolio_health_migration_required`` so the inbox can mark the
        source temporarily unavailable without inventing occurrences.
        """
        safe_limit = max(1, min(int(limit), 5000))
        since_text: Optional[str] = None
        if updated_from is not None:
            value = updated_from
            if value.tzinfo is not None and value.utcoffset() is not None:
                value = value.astimezone().replace(tzinfo=None)
            since_text = value.replace(microsecond=0).isoformat(sep=" ")
        context = {"limit": safe_limit, "updated_from": since_text}
        try:
            with self.db.get_session() as session:
                if since_text is None:
                    rows = session.execute(
                        text(
                            """
                            SELECT
                                id, account_key, snapshot_date, cost_method,
                                score, status, band, calculated_at,
                                created_at, updated_at
                            FROM portfolio_health_snapshots
                            ORDER BY updated_at DESC, id DESC
                            LIMIT :limit
                            """
                        ),
                        {"limit": safe_limit},
                    ).fetchall()
                else:
                    rows = session.execute(
                        text(
                            """
                            SELECT
                                id, account_key, snapshot_date, cost_method,
                                score, status, band, calculated_at,
                                created_at, updated_at
                            FROM portfolio_health_snapshots
                            WHERE updated_at >= :updated_from
                            ORDER BY updated_at DESC, id DESC
                            LIMIT :limit
                            """
                        ),
                        {"limit": safe_limit, "updated_from": since_text},
                    ).fetchall()
            results: list[Dict[str, Any]] = []
            for row in rows:
                mapping = row._mapping if hasattr(row, "_mapping") else None
                if mapping is not None:
                    results.append({
                        "id": mapping["id"],
                        "account_key": mapping["account_key"],
                        "snapshot_date": mapping["snapshot_date"],
                        "cost_method": mapping["cost_method"],
                        "score": mapping["score"],
                        "status": mapping["status"],
                        "band": mapping["band"],
                        "calculated_at": mapping["calculated_at"],
                        "created_at": mapping["created_at"],
                        "updated_at": mapping["updated_at"],
                    })
                    continue
                results.append({
                    "id": row[0],
                    "account_key": row[1],
                    "snapshot_date": row[2],
                    "cost_method": row[3],
                    "score": row[4],
                    "status": row[5],
                    "band": row[6],
                    "calculated_at": row[7],
                    "created_at": row[8],
                    "updated_at": row[9],
                })
            return results
        except OperationalError as exc:
            if _is_missing_schema(exc):
                raise RepositoryError(
                    "Portfolio health migration is required",
                    error_code="portfolio_health_migration_required",
                    context=context,
                ) from exc
            self._log_and_raise(
                logger,
                "list portfolio health snapshots failed",
                exc,
                error_code="portfolio_health_list_error",
                context=context,
            )
        except Exception as exc:  # broad-exception: fallback_recorded - repository boundary
            log_safe_exception(
                logger,
                "list portfolio health snapshots failed",
                exc,
                error_code="portfolio_health_list_error",
                context=context,
            )
            raise RepositoryError(
                "list portfolio health snapshots failed",
                error_code="portfolio_health_list_error",
                context=context,
            ) from exc

