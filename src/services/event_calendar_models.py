# -*- coding: utf-8 -*-
"""Event calendar domain model (issue #153 / T21).

Certainty grades are first-class: appointment/estimated dates must never be
presented as confirmed fixed dates.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

EVENT_TYPES: Tuple[str, ...] = (
    "earnings",
    "ex_dividend",
    "unlock",
    "index_rebalance",
    "macro",
)
EVENT_TYPE_SET = frozenset(EVENT_TYPES)

# confirmed  = official fixed date (announced ex-date, confirmed unlock batch)
# scheduled  = appointment / 预约披露 — can still move
# estimated  = inferred / model / incomplete source — lowest confidence
CERTAINTY_LEVELS: Tuple[str, ...] = (
    "confirmed",
    "scheduled",
    "estimated",
)
CERTAINTY_SET = frozenset(CERTAINTY_LEVELS)

# Map calendar event types onto event_alerts corporate categories for impact reuse.
EVENT_TYPE_TO_IMPACT_CATEGORY: Dict[str, str] = {
    "earnings": "earnings",
    "ex_dividend": "shareholder",
    "unlock": "shareholder",
    "index_rebalance": "analyst",
    "macro": "regulatory",
}


def normalize_event_type(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text not in EVENT_TYPE_SET:
        raise ValueError(
            "event_type must be one of: " + ", ".join(EVENT_TYPES)
        )
    return text


def normalize_certainty(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text not in CERTAINTY_SET:
        raise ValueError(
            "certainty must be one of: " + ", ".join(CERTAINTY_LEVELS)
        )
    return text


def normalize_event_types(raw: Any) -> List[str]:
    if raw is None:
        return list(EVENT_TYPES)
    if isinstance(raw, str):
        parts = [p.strip().lower() for p in raw.split(",") if p.strip()]
    elif isinstance(raw, Sequence):
        parts = [str(item or "").strip().lower() for item in raw if str(item or "").strip()]
    else:
        raise ValueError("event_types must be a list or comma-separated string")
    if not parts:
        raise ValueError("event_types must not be empty")
    out: List[str] = []
    for part in parts:
        if part not in EVENT_TYPE_SET:
            raise ValueError(
                "event_types only supports: " + ", ".join(EVENT_TYPES)
            )
        if part not in out:
            out.append(part)
    return out


@dataclass(frozen=True)
class CalendarEvent:
    """Single upcoming (or recent) calendar event for a watched/held symbol."""

    event_id: str
    event_type: str
    event_date: date
    certainty: str
    symbol: str
    title: str
    market: str = ""
    source: str = ""
    fetched_at: Optional[datetime] = None
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_type", normalize_event_type(self.event_type))
        object.__setattr__(self, "certainty", normalize_certainty(self.certainty))
        symbol = str(self.symbol or "").strip()
        if not symbol:
            raise ValueError("symbol is required")
        object.__setattr__(self, "symbol", symbol)
        title = str(self.title or "").strip()
        if not title:
            raise ValueError("title is required")
        object.__setattr__(self, "title", title)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["event_date"] = self.event_date.isoformat()
        if self.fetched_at is not None:
            payload["fetched_at"] = self.fetched_at.isoformat()
        else:
            payload["fetched_at"] = None
        return payload
