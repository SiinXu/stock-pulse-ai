# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Compatibility: ``api`` and ``src.api`` are the same import tree."""

from __future__ import annotations

import importlib
import subprocess
import sys


def test_api_package_is_the_src_api_module() -> None:
    alias = importlib.import_module("api")
    canonical = importlib.import_module("src.api")
    assert alias is canonical


def test_api_app_submodule_is_the_src_api_app_module() -> None:
    alias = importlib.import_module("api.app")
    canonical = importlib.import_module("src.api.app")
    assert alias is canonical
    assert alias.create_app is canonical.create_app

    from api.app import create_app as alias_factory
    from src.api.app import create_app as canonical_factory

    assert alias_factory is canonical_factory


def test_alias_first_child_keeps_canonical_metadata_and_reloads_source() -> None:
    """An initially unloaded alias child must retain the canonical import spec."""

    script = """
import importlib
import sys

import api

alias_name = "api.v1.schemas.common"
canonical_name = "src.api.v1.schemas.common"
assert alias_name not in sys.modules
assert canonical_name not in sys.modules

legacy = importlib.import_module(alias_name)
canonical = importlib.import_module(canonical_name)
assert legacy is canonical
assert legacy.__name__ == canonical_name
assert legacy.__package__ == "src.api.v1.schemas"
assert legacy.__spec__.name == canonical_name
assert sys.modules[alias_name] is sys.modules[canonical_name]

old_root_response = legacy.RootResponse
reloaded = importlib.reload(legacy)
assert reloaded is canonical
assert reloaded.RootResponse is not old_root_response
assert reloaded.__name__ == canonical_name
assert reloaded.__package__ == "src.api.v1.schemas"
assert reloaded.__spec__.name == canonical_name
assert sys.modules[alias_name] is sys.modules[canonical_name]
"""
    subprocess.run([sys.executable, "-c", script], check=True)
