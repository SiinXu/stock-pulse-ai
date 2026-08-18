# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Canonical provider imports must not preload reverse-edge modules."""

from __future__ import annotations

import subprocess
import sys


def test_stock_code_utils_and_provider_modules_import_without_cycle() -> None:
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
                    "from src.data_provider.base import DataFetcherManager",
                    "from src.data_provider.futu_position_fetcher import FutuPosition",
                    "import src.data_provider.futu_position_fetcher as provider_module",
                    "assert callable(normalize_code)",
                    "assert callable(is_pydantic_ai_available)",
                    "assert DataFetcherManager is not None",
                    "assert FutuPosition is provider_module.FutuPosition",
                    "from unittest.mock import patch",
                    "from src.data_provider.tickflow_fetcher import TickFlowFetcher",
                    "import src.data_provider.tickflow_fetcher as tickflow_module",
                    "assert TickFlowFetcher is tickflow_module.TickFlowFetcher",
                    "with patch(",
                    "    'src.data_provider.tickflow_fetcher.monotonic',",
                    "    return_value=1.0,",
                    "):",
                    "    assert tickflow_module.monotonic() == 1.0",
                )
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
