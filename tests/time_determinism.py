# -*- coding: utf-8 -*-
"""Repo-local fake clock for deterministic offline tests (phase 1).

Why not freezegun
-----------------
``freezegun`` is not in the dependency lock. Adding it requires the reviewed
lock-refresh process (``uv`` resolve, ``constraints.txt`` regeneration, and
supply-chain review per ``docs/supply-chain-maintenance.md``). Phase 1 only
needs an opt-in seam for a handful of wall-clock-sensitive suites, so a
monkeypatch-based :class:`FakeClock` is the smaller, lock-neutral choice.

What it controls
----------------
* ``time.time`` / ``time.monotonic`` / optional ``time.sleep`` (sleep advances
  the fake clock without blocking the wall clock)
* ``datetime.datetime.now`` / ``utcnow`` when rebound on modules that bind the
  ``datetime`` name (``from datetime import datetime`` or facade re-exports)

What it does **not** control
----------------------------
OS-level waits such as ``concurrent.futures`` / ``threading`` join timeouts,
subprocess timeouts, and real I/O. Those still need short real budgets or
mocked wait APIs. Prefer explicit :meth:`FakeClock.tick` over global sleep
patching when a suite mixes cache-TTL advances with real worker-drain loops.

Usage
-----

**Pytest assertion rewriting:** test methods may keep a *separate* globals dict
from ``sys.modules[module].__dict__``. Rebinding ``datetime`` on the module
object alone will not affect bare ``datetime.now()`` inside rewritten tests.
Rebind ``type(self).setUp.__globals__["datetime"]`` (or use ``self.clock``)
in addition to ``datetime_modules=...`` for production code.

Pytest::

    def test_x(monkeypatch):
        clock = install_fake_clock(monkeypatch, at="2026-06-15T12:00:00+00:00")
        clock.tick(30)
        ...

    def test_news_window(monkeypatch):
        clock = install_fake_clock(
            monkeypatch,
            at="2026-06-15T12:00:00",
            datetime_modules=["src.search_service", "tests.search.test_search_news_freshness"],
        )
        ...

Unittest / context manager::

    with frozen_time(at="2026-06-15T12:00:00", datetime_modules=[...]) as clock:
        clock.tick(1.0)
"""

from __future__ import annotations

import datetime as datetime_module
import importlib
import time as time_module
from contextlib import contextmanager
from datetime import datetime, timezone
from types import ModuleType
from typing import Iterator, Sequence, Union
from unittest import mock

import pytest

# Fixed anchor used when callers omit ``at=``. Chosen as a mid-week, mid-day UTC
# instant so local-date window math is stable across CI runners and DST edges.
DEFAULT_FAKE_NOW = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

ModuleRef = Union[str, ModuleType]


def _resolve_module(module: ModuleRef) -> ModuleType:
    if isinstance(module, ModuleType):
        return module
    return importlib.import_module(module)


def _parse_at(at: datetime | str | float | None) -> datetime:
    if at is None:
        return DEFAULT_FAKE_NOW
    if isinstance(at, datetime):
        if at.tzinfo is None:
            return at.replace(tzinfo=timezone.utc)
        return at
    if isinstance(at, (int, float)):
        return datetime.fromtimestamp(float(at), tz=timezone.utc)
    text = str(at).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


class FakeClock:
    """Process-local clock that can be advanced without wall-clock waiting."""

    def __init__(self, at: datetime | str | float | None = None) -> None:
        start = _parse_at(at)
        self._epoch = start.timestamp()
        self._mono = 0.0
        self._offset = 0.0

    @property
    def epoch(self) -> float:
        """Unix timestamp at construction (before ticks)."""
        return self._epoch

    def time(self) -> float:
        """Stand-in for ``time.time``."""
        return self._epoch + self._offset

    def monotonic(self) -> float:
        """Stand-in for ``time.monotonic`` (starts at 0.0, advances with ticks)."""
        return self._mono + self._offset

    def sleep(self, seconds: float) -> None:
        """Stand-in for ``time.sleep``: advance the fake clock, never block."""
        self.tick(seconds)

    def tick(self, seconds: float) -> None:
        """Advance both wall and monotonic domains by ``seconds``."""
        delta = float(seconds)
        if delta < 0:
            raise ValueError("FakeClock.tick does not support negative deltas")
        self._offset += delta

    def now(self, tz: timezone | None = None) -> datetime:
        """Stand-in for ``datetime.now`` / ``datetime.now(tz)``."""
        current = datetime.fromtimestamp(self.time(), tz=timezone.utc)
        if tz is None:
            # Match naive ``datetime.now()`` (local wall). CI is typically UTC;
            # using the fake UTC instant as a naive local keeps suite math stable.
            return current.replace(tzinfo=None)
        return current.astimezone(tz)

    def utcnow(self) -> datetime:
        """Stand-in for ``datetime.utcnow`` (naive UTC)."""
        return datetime.fromtimestamp(self.time(), tz=timezone.utc).replace(tzinfo=None)

    def datetime_type(self) -> type:
        """Return a ``datetime`` subclass whose ``now``/``utcnow`` read this clock."""
        clock = self
        real_datetime = datetime_module.datetime

        class FakeDateTime(real_datetime):
            """datetime subclass that reads the enclosing FakeClock."""

            @classmethod
            def now(cls, tz=None):  # noqa: ANN001 - mirrors datetime.now signature
                current = clock.now(tz)
                if tz is not None and current.tzinfo is not None:
                    return cls.fromtimestamp(current.timestamp(), tz=tz)
                if tz is None:
                    return cls(
                        current.year,
                        current.month,
                        current.day,
                        current.hour,
                        current.minute,
                        current.second,
                        current.microsecond,
                    )
                return cls.fromtimestamp(clock.time(), tz=tz)

            @classmethod
            def utcnow(cls):
                current = clock.utcnow()
                return cls(
                    current.year,
                    current.month,
                    current.day,
                    current.hour,
                    current.minute,
                    current.second,
                    current.microsecond,
                )

        FakeDateTime.__name__ = "datetime"
        FakeDateTime.__qualname__ = "datetime"
        return FakeDateTime


def install_fake_clock(
    monkeypatch: pytest.MonkeyPatch,
    *,
    at: datetime | str | float | None = None,
    datetime_modules: Sequence[ModuleRef] = (),
    patch_sleep: bool = True,
) -> FakeClock:
    """Install a :class:`FakeClock` via pytest's ``monkeypatch`` fixture.

    Parameters
    ----------
    monkeypatch:
        Pytest monkeypatch fixture (auto-reverts after the test).
    at:
        Frozen start instant (datetime, ISO string, or unix timestamp).
    datetime_modules:
        Modules whose bound ``datetime`` name should be replaced with a
        FakeDateTime subclass (needed for ``from datetime import datetime``).
    patch_sleep:
        When True, ``time.sleep`` advances the fake clock without blocking.
        Set False when the suite also relies on real short sleeps (for example
        worker-drain loops).
    """
    clock = FakeClock(at=at)
    monkeypatch.setattr(time_module, "time", clock.time)
    monkeypatch.setattr(time_module, "monotonic", clock.monotonic)
    if patch_sleep:
        monkeypatch.setattr(time_module, "sleep", clock.sleep)

    fake_datetime = clock.datetime_type()
    for module_ref in datetime_modules:
        module = _resolve_module(module_ref)
        if not hasattr(module, "datetime"):
            raise AttributeError(
                f"Module {module_ref!r} has no 'datetime' attribute to rebind"
            )
        monkeypatch.setattr(module, "datetime", fake_datetime)
    return clock


@contextmanager
def frozen_time(
    *,
    at: datetime | str | float | None = None,
    datetime_modules: Sequence[ModuleRef] = (),
    patch_sleep: bool = True,
) -> Iterator[FakeClock]:
    """Context-manager form for unittest.TestCase and non-pytest callers."""
    clock = FakeClock(at=at)
    patches: list[mock._patch] = [
        mock.patch.object(time_module, "time", clock.time),
        mock.patch.object(time_module, "monotonic", clock.monotonic),
    ]
    if patch_sleep:
        patches.append(mock.patch.object(time_module, "sleep", clock.sleep))

    fake_datetime = clock.datetime_type()
    for module_ref in datetime_modules:
        module = _resolve_module(module_ref)
        if not hasattr(module, "datetime"):
            raise AttributeError(
                f"Module {module_ref!r} has no 'datetime' attribute to rebind"
            )
        patches.append(mock.patch.object(module, "datetime", fake_datetime))

    for patcher in patches:
        patcher.start()
    try:
        yield clock
    finally:
        for patcher in reversed(patches):
            patcher.stop()


@pytest.fixture
def fake_clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    """Default opt-in fixture: freezes time at :data:`DEFAULT_FAKE_NOW`.

    Does not rebind module-level ``datetime`` names; pass
    :func:`install_fake_clock` with ``datetime_modules=...`` when needed.
    """
    return install_fake_clock(monkeypatch)


__all__ = [
    "DEFAULT_FAKE_NOW",
    "FakeClock",
    "fake_clock",
    "frozen_time",
    "install_fake_clock",
]
