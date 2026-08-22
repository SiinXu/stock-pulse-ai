# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Standard BoundToolSession test double (#1055 T2).

Native ``_execute_tools`` reads ``deadline_monotonic`` directly. Production
construction also freezes ``cancelled_check``. Hand-written ducks that omit
those fields stay green in a subset until a later shard reads them.

``make_bound_tool_session`` is the standard double: it constructs the real
class and always passes the production-required constructor fields. Adding a
required BoundToolSession field must update ``STANDARD_BOUND_TOOL_SESSION_FIELDS``
and this helper in the same PR.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from src.agent.runtime.tool_session import BoundToolSession
from src.agent.tools.registry import ToolRegistry
from tests.security_audit_test_utils import SecurityAuditRecorderStub

# Constructor kwargs the standard double must pass on every build. Native
# dispatch requires ``deadline_monotonic``; production construction also
# freezes the cancel probe. Do not drop a name here to keep a subset green.
STANDARD_BOUND_TOOL_SESSION_FIELDS = (
    "execution_id",
    "allowed_tools",
    "deadline_monotonic",
    "cancelled_check",
    "security_audit",
)

# Observer doubles used with ``_execute_tools`` are not BoundToolSession, but
# they must still carry the fields native dispatch and session gates require.
EXECUTE_TOOLS_OBSERVER_REQUIRED_FIELDS = (
    "execution_id",
    "deadline_monotonic",
    "cancelled_check",
)


def make_bound_tool_session(
    registry: ToolRegistry,
    **overrides: Any,
) -> BoundToolSession:
    """Build a real BoundToolSession with production-required fields set.

    Overrides replace defaults. ``derive_granted_permissions=True`` drops the
    default explicit grant list so it cannot combine with derived grants.
    """

    params: Dict[str, Any] = {
        "execution_id": "test-bound-session",
        "allowed_tools": registry.list_names(),
        "granted_permissions": list(registry.supported_declared_capabilities()),
        "deadline_monotonic": None,
        "cancelled_check": None,
        "security_audit": SecurityAuditRecorderStub(),
    }
    params.update(overrides)
    if params.get("derive_granted_permissions"):
        params.pop("granted_permissions", None)
    return BoundToolSession(registry, **params)


@dataclass
class ExecuteToolsObserverSession:
    """Contract-complete ``_execute_tools`` observer that is not BoundToolSession.

    Redaction tests must dispatch unregistered or secret tool names without
    ``canonical_tool_name`` skipping ``redact_sensitive_text``. Timeout and
    session-gate tests must use ``make_bound_tool_session`` instead.
    """

    execution_id: str
    execute_handler: Callable[[str, dict], dict]
    deadline_monotonic: Optional[float] = None
    cancelled_check: Optional[Callable[[], bool]] = None
    block_seconds: float = 0.0

    def is_non_retriable_cached(self, _cache_key: str) -> bool:
        return False

    def execute(self, name: str, arguments: dict, **_kwargs) -> dict:
        if self.block_seconds > 0:
            time.sleep(self.block_seconds)
        return self.execute_handler(name, arguments)
