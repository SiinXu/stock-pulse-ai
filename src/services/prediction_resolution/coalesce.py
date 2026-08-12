# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Group claimed predictions so one actuals fetch serves many scores."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import date
from typing import Iterable, List, Sequence, Tuple

from src.services.prediction_resolution.contracts import PredictionWorkItem


def coalesce_key(
    *,
    symbol: str,
    market: str,
    as_of_date: date,
) -> Tuple[str, str, str]:
    """Stable group key for actuals fetch coalesce."""
    return (
        str(symbol or "").strip().upper(),
        str(market or "").strip().lower(),
        as_of_date.isoformat() if isinstance(as_of_date, date) else str(as_of_date),
    )


@dataclass(frozen=True)
class CoalesceGroup:
    """One (symbol, market, as_of) bucket with all claimed predictions in it."""

    key: Tuple[str, str, str]
    symbol: str
    market: str
    as_of_date: date
    items: Tuple[PredictionWorkItem, ...]

    @property
    def size(self) -> int:
        return len(self.items)


def group_by_actuals_key(
    items: Sequence[PredictionWorkItem],
) -> List[CoalesceGroup]:
    """Partition claimed work by coalesce key, preserving first-seen order."""
    buckets: "OrderedDict[Tuple[str, str, str], List[PredictionWorkItem]]" = OrderedDict()
    for item in items:
        key = coalesce_key(
            symbol=item.symbol,
            market=item.market,
            as_of_date=item.as_of_date,
        )
        buckets.setdefault(key, []).append(item)

    groups: List[CoalesceGroup] = []
    for key, grouped in buckets.items():
        first = grouped[0]
        groups.append(
            CoalesceGroup(
                key=key,
                symbol=first.symbol,
                market=first.market,
                as_of_date=first.as_of_date,
                items=tuple(grouped),
            )
        )
    return groups


def iter_prediction_ids(groups: Iterable[CoalesceGroup]) -> List[str]:
    """Flatten group membership for diagnostics."""
    out: List[str] = []
    for group in groups:
        for item in group.items:
            out.append(item.prediction_id)
    return out
