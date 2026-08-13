# -*- coding: utf-8 -*-
"""Fake / fixed clock for sandbox runs (Issue #247 batch-1).

Sandbox time is fully controlled so agent variants see a reproducible clock
without depending on wall time. The clock never mutates the system clock.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Union


def _as_utc_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@dataclass
class FakeClock:
    """Deterministic clock used only inside an active sandbox context."""

    now: datetime
    tick_step: timedelta = timedelta(seconds=1)

    def __post_init__(self) -> None:
        object.__setattr__(self, "now", _as_utc_aware(self.now))
        if self.tick_step.total_seconds() < 0:
            raise ValueError("tick_step must be non-negative")

    @classmethod
    def fixed(
        cls,
        at: Union[datetime, str],
        *,
        tick_step: timedelta = timedelta(seconds=1),
    ) -> "FakeClock":
        """Build a clock pinned to ``at`` (datetime or ISO-8601 string)."""
        if isinstance(at, str):
            text = at.strip()
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            parsed = datetime.fromisoformat(text)
        else:
            parsed = at
        return cls(now=parsed, tick_step=tick_step)

    def utcnow(self) -> datetime:
        """Return the current sandbox instant (UTC-aware)."""
        return self.now

    def isoformat(self) -> str:
        return self.now.isoformat().replace("+00:00", "Z")

    def advance(
        self,
        delta: Optional[timedelta] = None,
        *,
        seconds: Optional[float] = None,
    ) -> datetime:
        """Advance the fake clock and return the new instant."""
        if delta is not None and seconds is not None:
            raise ValueError("pass either delta or seconds, not both")
        step = self.tick_step if delta is None and seconds is None else None
        if delta is not None:
            step = delta
        elif seconds is not None:
            step = timedelta(seconds=float(seconds))
        assert step is not None
        if step.total_seconds() < 0:
            raise ValueError("clock cannot move backwards")
        self.now = self.now + step
        return self.now

    def snapshot(self) -> "FakeClock":
        """Return an independent copy at the same instant."""
        return FakeClock(now=self.now, tick_step=self.tick_step)
