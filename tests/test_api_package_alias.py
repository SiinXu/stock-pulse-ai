# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Compatibility: ``api`` and ``src.api`` are the same import tree."""

from __future__ import annotations

import importlib


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
