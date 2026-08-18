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


def test_nested_children_are_bound_on_both_package_names() -> None:
    """Alias and canonical imports must expose children for attribute traversal."""

    script = """
import importlib
from unittest.mock import patch

import bot

legacy_child = importlib.import_module("bot.platforms.dingtalk_stream")
canonical_child = importlib.import_module("src.bot.platforms.dingtalk_stream")
legacy_parent = importlib.import_module("bot.platforms")
canonical_parent = importlib.import_module("src.bot.platforms")

assert legacy_child is canonical_child
assert legacy_parent is canonical_parent
assert legacy_parent.dingtalk_stream is canonical_child
assert canonical_parent.dingtalk_stream is canonical_child

with patch("bot.platforms.dingtalk_stream.DINGTALK_STREAM_AVAILABLE", False):
    assert canonical_child.DINGTALK_STREAM_AVAILABLE is False

canonical_first = importlib.import_module("src.bot.platforms.discord")
assert legacy_parent.discord is canonical_first
assert canonical_parent.discord is canonical_first
"""
    subprocess.run([sys.executable, "-c", script], check=True)
