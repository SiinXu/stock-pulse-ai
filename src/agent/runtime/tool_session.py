# -*- coding: utf-8 -*-
"""Execution-bound tool session (AR-PY-02).

``BoundToolSession`` is the only supported path for a runtime to call
financial tools. Everything that shapes an execution's tool access is
frozen at construction time: session identity, the tool allowlist,
principal and permission grants, stock scope, per-call limits, the
session-wide budget, the deadline and the cancellation token.

Every gate fails closed: rejected calls return the shared structured
error contract (same shape as ``ToolSurface`` results), are audited and
never silently degrade. Results that land after the session was closed
or cancelled are dropped behind a late-result fence.

The native runner keeps its direct, replay-frozen tool path: its
byte-exact behaviour is the characterization gate, so it is deliberately
*not* rewired through this session. ``BoundToolSession`` is instead the
tool bridge for external runtime adapters (AR-PY-04+), which have no
legacy tool path of their own to preserve.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Tuple

from src.agent.tool_surface import ToolSurface, build_tool_error_result
from src.agent.tools.execution import (
    ToolAccessContext,
    _build_tool_cache_key,
    _is_non_retriable_tool_result,
)
from src.agent.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class BoundToolSession:
    """Frozen per-execution tool session with fail-closed gates."""

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        execution_id: str,
        allowed_tools: Iterable[str],
        granted_permissions: Iterable[str] = (),
        principal: Optional[str] = None,
        stage: Optional[str] = None,
        attempt: Optional[int] = None,
        stock_scope: Any = None,
        backend: Optional[str] = None,
        session_id: Optional[str] = None,
        call_timeout_seconds: Optional[float] = None,
        max_result_bytes: Optional[int] = None,
        max_tool_calls: Optional[int] = None,
        deadline_seconds: Optional[float] = None,
        cancelled_check: Optional[Callable[[], bool]] = None,
        audit_context: Optional[Mapping[str, Any]] = None,
        surface: Optional[ToolSurface] = None,
    ) -> None:
        if not isinstance(execution_id, str) or not execution_id.strip():
            raise ValueError("BoundToolSession requires a non-empty execution_id")
        self._registry = registry
        self._surface = surface if surface is not None else ToolSurface(registry)
        self._execution_id = execution_id
        self._stage = stage
        self._attempt = attempt
        self._principal = principal
        self._allowed_tools = frozenset(
            name for name in allowed_tools if isinstance(name, str) and name.strip()
        )
        self._granted_permissions = frozenset(granted_permissions)
        self._stock_scope = stock_scope
        self._backend = backend
        self._session_id = session_id
        self._call_timeout_seconds = call_timeout_seconds
        self._max_result_bytes = max_result_bytes
        self._max_tool_calls = max_tool_calls
        self._deadline_monotonic = (
            time.monotonic() + float(deadline_seconds)
            if deadline_seconds is not None
            else None
        )
        self._cancelled_check = cancelled_check
        base_audit_context: Dict[str, Any] = {"execution_id": execution_id}
        if stage is not None:
            base_audit_context["stage"] = stage
        if attempt is not None:
            base_audit_context["attempt"] = attempt
        if principal is not None:
            base_audit_context["principal"] = principal
        if audit_context:
            base_audit_context.update(dict(audit_context))
        self._base_audit_context = base_audit_context

        self._lock = threading.Lock()
        self._closed = False
        self._dispatched_calls = 0
        self._dropped_results = 0
        self._audit_trail: List[Dict[str, Any]] = []
        self._non_retriable_results: Dict[str, Dict[str, Any]] = {}

    # ----- Frozen identity and observability -----

    @property
    def execution_id(self) -> str:
        return self._execution_id

    @property
    def stage(self) -> Optional[str]:
        return self._stage

    @property
    def attempt(self) -> Optional[int]:
        return self._attempt

    @property
    def principal(self) -> Optional[str]:
        return self._principal

    @property
    def allowed_tools(self) -> frozenset:
        return self._allowed_tools

    @property
    def granted_permissions(self) -> frozenset:
        return self._granted_permissions

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._closed

    @property
    def dispatched_calls(self) -> int:
        with self._lock:
            return self._dispatched_calls

    @property
    def dropped_results(self) -> int:
        with self._lock:
            return self._dropped_results

    @property
    def audit_trail(self) -> Tuple[Dict[str, Any], ...]:
        with self._lock:
            return tuple(self._audit_trail)

    def close(self) -> None:
        """Close the session. Idempotent; later calls and late results are dropped."""
        with self._lock:
            self._closed = True

    def describe_tools(self) -> List[dict]:
        """Neutral descriptors for allowed tools only; never exposes handlers."""
        descriptors = []
        for name in sorted(self._allowed_tools):
            tool_def = self._registry.resolve(name)
            if tool_def is None:
                continue
            descriptors.append(tool_def.to_public_descriptor())
        return descriptors

    # ----- Execution -----

    def execute(self, name: str, arguments: Any) -> Dict[str, Any]:
        """Execute one allowed tool through the frozen session gates."""
        started_at = time.time()
        tool_name = name if isinstance(name, str) else ""
        cache_key = (
            _build_tool_cache_key(tool_name, arguments)
            if isinstance(arguments, dict)
            else None
        )

        with self._lock:
            rejection = self._gate_locked(tool_name)
            if rejection is None and cache_key is not None:
                cached = self._non_retriable_results.get(cache_key)
                if cached is not None:
                    self._audit_trail.append(cached["audit"])
                    return cached
            call_context = self._build_call_context()
            if rejection is None and (
                self._deadline_monotonic is not None
                and call_context.timeout_seconds is not None
                and call_context.timeout_seconds <= 0
            ):
                # Deadline elapsed between the gate check and dispatch; a
                # non-positive timeout would disable the surface timeout guard.
                rejection = ("deadline_exceeded", "Session deadline exceeded.", None)
            if rejection is None:
                if (
                    self._max_tool_calls is not None
                    and self._dispatched_calls >= self._max_tool_calls
                ):
                    rejection = (
                        "budget_exhausted",
                        "Session tool-call budget exhausted.",
                        {"max_tool_calls": self._max_tool_calls},
                    )
                else:
                    self._dispatched_calls += 1
            if rejection is not None:
                return self._reject_locked(
                    tool_name=tool_name,
                    arguments=arguments,
                    started_at=started_at,
                    rejection=rejection,
                )

        result = self._surface.execute_tool(tool_name, arguments, call_context)

        with self._lock:
            if self._closed or self._cancel_requested():
                self._dropped_results += 1
                fenced = build_tool_error_result(
                    tool_name=tool_name,
                    code="late_result_dropped",
                    message="Tool result arrived after the session terminal state and was dropped.",
                    started_at=started_at,
                    context=call_context,
                    retriable=False,
                    details={"fence": "session_terminal"},
                    arguments=arguments,
                )
                self._audit_trail.append(fenced["audit"])
                logger.warning(
                    "[ToolSession] dropped late tool result: execution_id=%s tool=%s",
                    self._execution_id,
                    tool_name,
                )
                return fenced
            if cache_key is not None and self._is_cacheable_non_retriable(result):
                self._non_retriable_results[cache_key] = result
            self._audit_trail.append(result["audit"])
            return result

    # ----- Gates (called with lock held) -----

    def _gate_locked(
        self, tool_name: str
    ) -> Optional[Tuple[str, str, Optional[Dict[str, Any]]]]:
        if self._closed:
            return ("session_closed", "Tool session is closed.", None)
        if self._cancel_requested():
            return (
                "cancelled",
                "Execution cancellation was requested; tool call rejected.",
                None,
            )
        if self._deadline_exceeded():
            return ("deadline_exceeded", "Session deadline exceeded.", None)
        if not tool_name.strip():
            return (
                "invalid_tool_name",
                "Tool name must exactly match a registered StockPulse tool.",
                None,
            )
        if tool_name not in self._allowed_tools:
            return (
                "tool_not_allowed",
                "Tool is not in the session allowlist.",
                None,
            )
        tool_def = self._registry.resolve(tool_name)
        if tool_def is None:
            return ("tool_not_found", "Tool not found.", None)
        if tool_def.policy.policy_status != "declared":
            return (
                "policy_undeclared",
                "Tool policy is not declared; the session requires declared policies.",
                {"policy_status": tool_def.policy.policy_status},
            )
        missing = set(tool_def.policy.permissions) - self._granted_permissions
        if missing:
            return (
                "permission_denied",
                "Session lacks required tool permissions.",
                {
                    "required_permissions": sorted(tool_def.policy.permissions),
                    "missing_permissions": sorted(missing),
                },
            )
        return None

    def _reject_locked(
        self,
        *,
        tool_name: str,
        arguments: Any,
        started_at: float,
        rejection: Tuple[str, str, Optional[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        code, message, details = rejection
        result = build_tool_error_result(
            tool_name=tool_name,
            code=code,
            message=message,
            started_at=started_at,
            context=self._build_call_context(),
            retriable=False,
            details=details,
            arguments=arguments,
        )
        self._audit_trail.append(result["audit"])
        logger.warning(
            "[ToolSession] rejected tool call: execution_id=%s tool=%s code=%s",
            self._execution_id,
            tool_name,
            code,
        )
        return result

    # ----- Helpers -----

    def _cancel_requested(self) -> bool:
        if self._cancelled_check is None:
            return False
        return bool(self._cancelled_check())

    def _deadline_exceeded(self) -> bool:
        return (
            self._deadline_monotonic is not None
            and time.monotonic() >= self._deadline_monotonic
        )

    def _build_call_context(self) -> ToolAccessContext:
        timeout = self._call_timeout_seconds
        if self._deadline_monotonic is not None:
            remaining = self._deadline_monotonic - time.monotonic()
            timeout = remaining if timeout is None else min(timeout, remaining)
        return ToolAccessContext(
            stock_scope=self._stock_scope,
            backend=self._backend,
            session_id=self._session_id,
            timeout_seconds=timeout,
            max_result_bytes=self._max_result_bytes,
            audit_context=dict(self._base_audit_context),
        )

    @staticmethod
    def _is_cacheable_non_retriable(result: Dict[str, Any]) -> bool:
        """Mirror the runner's non-retriable memoization semantics."""
        if result.get("ok"):
            return _is_non_retriable_tool_result(result.get("result"))
        error = result.get("error") or {}
        return (
            error.get("retriable") is False
            and error.get("code") == "stock_scope_violation"
        )
