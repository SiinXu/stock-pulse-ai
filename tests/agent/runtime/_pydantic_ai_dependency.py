# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Dependency-state guard for the experimental PydanticAI runtime tests (RF-01).

The default CI gate installs no optional dependency, so ``pydantic-ai-slim`` is
absent and these tests skip. That is correct for the native gate, but a green
result must never *hide* a broken installed matrix: when the installed-matrix
job sets ``STOCKPULSE_REQUIRE_PYDANTIC_AI=1``, a missing or unimportable
``pydantic_ai`` is a hard failure, not a skip (AR-RF-09).
"""

from __future__ import annotations

import os

import pytest

REQUIRE_ENV_VAR = "STOCKPULSE_REQUIRE_PYDANTIC_AI"


def require_pydantic_ai():
    """Return the ``pydantic_ai`` module, or skip/fail per dependency state.

    - Absent + ``STOCKPULSE_REQUIRE_PYDANTIC_AI`` unset: ``pytest.skip`` (native
      gate; the experimental path is genuinely not installed).
    - Absent + ``STOCKPULSE_REQUIRE_PYDANTIC_AI=1``: ``pytest.fail`` (the
      installed matrix must exercise the adapter, never pass by skipping).
    """
    required = os.environ.get(REQUIRE_ENV_VAR) == "1"
    try:
        import pydantic_ai
    except ImportError as exc:
        if required:
            pytest.fail(
                f"{REQUIRE_ENV_VAR}=1 but pydantic_ai is not importable: {exc}. "
                "The installed matrix must not pass by skipping (AR-RF-09)."
            )
        pytest.skip("pydantic-ai-slim not installed; experimental runtime tests skipped")
    return pydantic_ai
