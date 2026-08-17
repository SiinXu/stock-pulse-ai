# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""The data_provider alias must not preload reverse-edge provider modules."""

from __future__ import annotations

import subprocess
import sys


def test_stock_code_utils_can_import_through_alias_without_cycle() -> None:
    """CI native-gate counterexample: stock_code_utils → data_provider alias.

    Eager walk_packages of src.data_provider pulled in futu_position_fetcher,
    which imports stock_code_utils while that module is still initializing.
    """

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "\n".join(
                (
                    "from src.services.stock_code_utils import normalize_code",
                    "from src.agent.runtime.pydantic_ai_adapter import (",
                    "    is_pydantic_ai_available,",
                    ")",
                    "from data_provider.base import DataFetcherManager",
                    "from data_provider.futu_position_fetcher import FutuPosition",
                    "import src.data_provider.futu_position_fetcher as canon",
                    "import data_provider.futu_position_fetcher as alias",
                    "assert callable(normalize_code)",
                    "assert callable(is_pydantic_ai_available)",
                    "assert DataFetcherManager is not None",
                    "assert alias is canon",
                    "assert FutuPosition is canon.FutuPosition",
                )
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
