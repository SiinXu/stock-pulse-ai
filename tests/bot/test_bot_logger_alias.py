# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Legacy ``bot.*`` logger names must be the same objects as ``src.bot.*``."""

from __future__ import annotations

import logging

import bot  # noqa: F401  — install the alias shim


def test_legacy_logger_created_before_canonical_is_the_same_object() -> None:
    """Counterexample: getLogger('bot.X') before getLogger('src.bot.X')."""

    legacy = logging.getLogger("bot._review_probe_before")
    canonical = logging.getLogger("src.bot._review_probe_before")
    assert legacy is canonical
    assert canonical.name == "src.bot._review_probe_before"


def test_canonical_logger_created_first_is_visible_as_legacy_name() -> None:
    canonical = logging.getLogger("src.bot._review_probe_after")
    legacy = logging.getLogger("bot._review_probe_after")
    assert legacy is canonical
    assert canonical.name == "src.bot._review_probe_after"
