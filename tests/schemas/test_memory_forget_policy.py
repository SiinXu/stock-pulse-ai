# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Counterexample tests for the #1119 Slice 2 episode forget policy."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import inspect

import pytest

from src.schemas.memory_forget_policy import (
    ERROR_FORGET_AMBIGUOUS_CUTOFF,
    ERROR_FORGET_INVALID_CUTOFF,
    ERROR_FORGET_INVALID_DRY_RUN,
    ERROR_FORGET_INVALID_MAX_ROWS,
    ERROR_FORGET_INVALID_NOW,
    ERROR_FORGET_INVALID_RETENTION_DAYS,
    ERROR_FORGET_INVALID_SYMBOL,
    ERROR_FORGET_UNSCOPED,
    MemoryForgetError,
    require_episode_forget_policy,
    resolve_episode_forget_policy,
)


NOW = datetime(2026, 8, 26, 12, 0, 0, tzinfo=timezone.utc)


def test_no_policy_does_not_apply() -> None:
    empty = resolve_episode_forget_policy()
    assert empty.apply is False
    assert empty.error_code is None
    symbol_only = resolve_episode_forget_policy(symbol="AAPL")
    assert symbol_only.apply is False
    assert symbol_only.symbol == "AAPL"
    assert symbol_only.error_code is None


def test_cutoff_without_symbol_is_unscoped() -> None:
    decision = resolve_episode_forget_policy(cutoff=NOW)
    assert decision.apply is False
    assert decision.error_code == ERROR_FORGET_UNSCOPED
    with pytest.raises(MemoryForgetError) as raised:
        require_episode_forget_policy(symbol="  ", cutoff=NOW, max_rows=2)
    assert raised.value.error_code == ERROR_FORGET_UNSCOPED


def test_valid_symbol_cutoff_and_count_apply() -> None:
    decision = require_episode_forget_policy(
        symbol=" AAPL ",
        cutoff=NOW,
        max_rows=2,
        dry_run=True,
    )
    assert decision.apply is True
    assert decision.symbol == "AAPL"
    assert decision.cutoff == datetime(2026, 8, 26, 12, 0, 0)
    assert decision.max_rows == 2
    assert decision.dry_run is True
    assert decision.error_code is None


def test_retention_days_uses_injected_clock() -> None:
    decision = require_episode_forget_policy(
        symbol="600519",
        retention_days=90,
        now=NOW,
    )
    assert decision.apply is True
    assert decision.cutoff == datetime(2026, 5, 28, 12, 0, 0)
    assert decision.cutoff == _as_expected_cutoff(NOW, 90)


def _as_expected_cutoff(now: datetime, days: int) -> datetime:
    return (now - timedelta(days=days)).astimezone(timezone.utc).replace(tzinfo=None)


def test_invalid_inputs_fail_closed() -> None:
    cases = [
        ({"symbol": 600519, "cutoff": NOW}, ERROR_FORGET_INVALID_SYMBOL),
        ({"symbol": "AAPL", "cutoff": True}, ERROR_FORGET_INVALID_CUTOFF),
        ({"symbol": "AAPL", "retention_days": 90}, ERROR_FORGET_INVALID_NOW),
        ({"symbol": "AAPL", "retention_days": True, "now": NOW}, ERROR_FORGET_INVALID_RETENTION_DAYS),
        ({"symbol": "AAPL", "max_rows": True}, ERROR_FORGET_INVALID_MAX_ROWS),
        ({"symbol": "AAPL", "max_rows": 0}, ERROR_FORGET_INVALID_MAX_ROWS),
        (
            {"symbol": "AAPL", "cutoff": NOW, "retention_days": 90, "now": NOW},
            ERROR_FORGET_AMBIGUOUS_CUTOFF,
        ),
        ({"symbol": "AAPL", "cutoff": NOW, "dry_run": "true"}, ERROR_FORGET_INVALID_DRY_RUN),
    ]
    for kwargs, code in cases:
        decision = resolve_episode_forget_policy(**kwargs)
        assert decision.apply is False, kwargs
        assert decision.error_code == code, kwargs


def test_resolver_stays_library_only() -> None:
    import src.schemas.memory_forget_policy as module

    source = inspect.getsource(module)
    assert "src.repositories" not in source
    assert "src.services" not in source
    assert "src.agent" not in source
    assert "def resolve_episode_forget_policy" in source
