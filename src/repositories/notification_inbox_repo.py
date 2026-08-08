# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Persistence for in-app notification inbox read markers."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Iterable, Optional, Sequence, Set

from sqlalchemy import delete, select

from src.repositories.base import BaseRepository
from src.storage import DatabaseManager, NotificationInboxReadStateRecord, utc_naive_now

logger = logging.getLogger(__name__)


class NotificationInboxRepository(BaseRepository):
    """DB access for durable inbox read markers only.

    Event bodies are projected from existing source tables by the service layer.
    """

    def __init__(self, db_manager: Optional[DatabaseManager] = None) -> None:
        super().__init__(db_manager)

    def list_read_item_ids(self, item_ids: Sequence[str]) -> Set[str]:
        """Return the subset of item_ids that are already marked read."""
        keys = [str(item_id).strip() for item_id in item_ids if str(item_id).strip()]
        if not keys:
            return set()
        try:
            with self.db.get_session() as session:
                rows = session.execute(
                    select(NotificationInboxReadStateRecord.item_id).where(
                        NotificationInboxReadStateRecord.item_id.in_(keys)
                    )
                ).scalars().all()
                return {str(item_id) for item_id in rows}
        except Exception as exc:
            self._log_and_raise(
                logger,
                "Notification inbox read-state lookup failed",
                exc,
                error_code="notification_inbox_read_lookup_failed",
                context={"item_count": len(keys)},
            )

    def mark_read(self, items: Iterable[tuple[str, str]]) -> int:
        """Upsert read markers for (item_id, kind) pairs. Returns newly written count."""
        pairs: list[tuple[str, str]] = []
        seen: set[str] = set()
        for item_id, kind in items:
            key = str(item_id).strip()
            kind_key = str(kind).strip()
            if not key or not kind_key or key in seen:
                continue
            seen.add(key)
            pairs.append((key, kind_key))
        if not pairs:
            return 0

        now = utc_naive_now()
        written = 0
        try:
            with self.db.get_session() as session:
                for item_id, kind in pairs:
                    existing = session.execute(
                        select(NotificationInboxReadStateRecord).where(
                            NotificationInboxReadStateRecord.item_id == item_id
                        ).limit(1)
                    ).scalar_one_or_none()
                    if existing is None:
                        session.add(
                            NotificationInboxReadStateRecord(
                                item_id=item_id,
                                kind=kind,
                                read_at=now,
                            )
                        )
                        written += 1
                    else:
                        existing.read_at = now
                        existing.kind = kind
                session.commit()
            return written
        except Exception as exc:
            self._log_and_raise(
                logger,
                "Notification inbox mark-read failed",
                exc,
                error_code="notification_inbox_mark_read_failed",
                context={"item_count": len(pairs)},
            )

    def delete_read_before(self, cutoff: datetime) -> int:
        """Delete read markers older than cutoff. Returns deleted row count."""
        cutoff_naive = cutoff.replace(tzinfo=None) if cutoff.tzinfo else cutoff
        try:
            with self.db.get_session() as session:
                result = session.execute(
                    delete(NotificationInboxReadStateRecord).where(
                        NotificationInboxReadStateRecord.read_at < cutoff_naive
                    )
                )
                session.commit()
                return int(result.rowcount or 0)
        except Exception as exc:
            self._log_and_raise(
                logger,
                "Notification inbox retention cleanup failed",
                exc,
                error_code="notification_inbox_retention_failed",
                context={"cutoff": cutoff_naive.isoformat()},
            )

    def delete_read_not_in(self, keep_item_ids: Sequence[str]) -> int:
        """Delete read markers whose item_id is not in keep_item_ids."""
        keep = {str(item_id).strip() for item_id in keep_item_ids if str(item_id).strip()}
        try:
            with self.db.get_session() as session:
                if not keep:
                    result = session.execute(delete(NotificationInboxReadStateRecord))
                else:
                    result = session.execute(
                        delete(NotificationInboxReadStateRecord).where(
                            NotificationInboxReadStateRecord.item_id.not_in(keep)
                        )
                    )
                session.commit()
                return int(result.rowcount or 0)
        except Exception as exc:
            self._log_and_raise(
                logger,
                "Notification inbox orphan cleanup failed",
                exc,
                error_code="notification_inbox_orphan_cleanup_failed",
                context={"keep_count": len(keep)},
            )
