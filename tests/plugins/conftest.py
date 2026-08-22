# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Isolate process ToolRegistry cache for plugin tests.

Predecessor tests can restore a stale ``_TOOL_REGISTRY`` pointer while a live
composition root still owns an orphaned registry. The next
``get_tool_registry()`` then safety-net-registers always-on search tools
without plugin ownership, and ``builtin.web_search`` onload fails with
``native_registration_conflict``.
"""

from __future__ import annotations

import pytest

from src.agent.runtime_assembly import reset_process_tool_registry_for_tests
from src.application_services import reset_application_services


@pytest.fixture(autouse=True)
def _isolate_process_tool_registry_and_application_root():
    reset_application_services()
    reset_process_tool_registry_for_tests()
    yield
    reset_application_services()
    reset_process_tool_registry_for_tests()
