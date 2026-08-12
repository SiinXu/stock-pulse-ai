# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Ports for PredictionResolver (store / actuals / scorer / audit)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Mapping, Optional, Protocol, Sequence


class PredictionStorePort(Protocol):
    """Persistence surface required by one resolver tick."""

    def list_due(
        self,
        *,
        as_of: datetime,
        limit: int,
        statuses: Optional[Sequence[str]] = None,
    ) -> List[Any]:
        ...

    def claim_for_resolve(
        self,
        *,
        prediction_id: str,
        lease_owner: str,
        lease_token: str,
        lease_ttl_seconds: int = 120,
        as_of: Optional[datetime] = None,
    ) -> Optional[Any]:
        ...

    def resolve(
        self,
        *,
        prediction_id: str,
        outcome: Mapping[str, Any],
        expected_lease_token: Optional[str] = None,
        as_of: Optional[datetime] = None,
    ) -> tuple[bool, Optional[Any]]:
        ...

    def mark_data_unavailable(
        self,
        *,
        prediction_id: str,
        reason: str,
        expected_lease_token: Optional[str] = None,
        as_of: Optional[datetime] = None,
        outcome: Optional[Mapping[str, Any]] = None,
    ) -> tuple[bool, Optional[Any]]:
        ...

    def requeue_pending(
        self,
        *,
        prediction_id: str,
        as_of: Optional[datetime] = None,
    ) -> tuple[bool, Optional[Any]]:
        ...


class ActualsFetcherPort(Protocol):
    def fetch(self, **kwargs: Any) -> Any:
        ...


class ClaimScorerPort(Protocol):
    def score(self, claims: Sequence[Any], actuals: Any, config: Any = None) -> Any:
        ...


class EvolutionEventSink(Protocol):
    def emit(self, event_type: str, payload: Mapping[str, Any]) -> None:
        ...
