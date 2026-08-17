# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Legacy ``bot.*`` logger names must be the same objects as ``src.bot.*``."""

from __future__ import annotations

import logging
import subprocess
import sys

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


def test_unloaded_legacy_child_keeps_canonical_metadata_and_reloads_source() -> None:
    """Alias-first imports must not replace the canonical module spec."""

    script = """
import importlib
import sys

import bot

assert "bot.handler" not in sys.modules
assert "src.bot.handler" not in sys.modules

legacy = importlib.import_module("bot.handler")
canonical = importlib.import_module("src.bot.handler")
assert legacy is canonical
assert legacy.__name__ == "src.bot.handler"
assert legacy.__package__ == "src.bot"
assert legacy.__spec__.name == "src.bot.handler"

old_handle_webhook = legacy.handle_webhook
reloaded = importlib.reload(legacy)
assert reloaded is canonical
assert reloaded.handle_webhook is not old_handle_webhook
assert reloaded.__name__ == "src.bot.handler"
assert reloaded.__package__ == "src.bot"
assert reloaded.__spec__.name == "src.bot.handler"
assert sys.modules["bot.handler"] is sys.modules["src.bot.handler"]
"""
    subprocess.run([sys.executable, "-c", script], check=True)
