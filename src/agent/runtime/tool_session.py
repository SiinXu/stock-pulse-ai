# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
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

The native runner now dispatches through this same session too (RF-03):
there is a single tool authority for every runtime. Capability, argument,
scope and outbound-URL contracts are always enforced by ``ToolSurface``;
the session adds its frozen allowlist and lifecycle gates.
"""

from __future__ import annotations

import hashlib
import logging
import math
import threading
import time
import uuid
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Tuple

from src.agent.tool_surface import ToolSurface, build_tool_error_result
from src.agent.tools.execution import (
    ToolAccessContext,
    _build_tool_cache_key,
    _is_non_retriable_tool_result,
)
from src.agent.tools.registry import (
    ToolDefinition,
    ToolRegistry,
    validate_tool_capability_contract,
    validate_tool_schema_contract,
)
from src.services.security_audit_service import (
    SecurityAuditRecorder,
    SecurityAuditUnavailable,
    require_security_audit_recorder,
)

logger = logging.getLogger(__name__)


def _bounded_audit_identity(value: Any, *, fallback: str) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if (
        text
        and len(text) <= 128
        and text[0].isalnum()
        and all(character.isalnum() or character in "_.:@/-" for character in text)
    ):
        return text
    if not text:
        return fallback
    digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]
    return f"sha256:{digest}"


class ExecutionFenceRejected(Exception):
    """Internal signal carrying a structured execution-fence rejection."""

    def __init__(
        self,
        code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


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
        deadline_monotonic: Optional[float] = None,
        cancelled_check: Optional[Callable[[], bool]] = None,
        audit_context: Optional[Mapping[str, Any]] = None,
        enforce_access_policy: bool = True,
        security_audit: SecurityAuditRecorder,
    ) -> None:
        if not isinstance(execution_id, str) or not execution_id.strip():
            raise ValueError("BoundToolSession requires a non-empty execution_id")
        if enforce_access_policy is not True:
            raise ValueError("BoundToolSession access policy cannot be disabled")
        self._registry = registry
        self._surface = ToolSurface(registry)
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
        # Absolute ``time.monotonic()`` deadline supplied by the caller; the
        # session derives the remaining budget per call. An absolute contract
        # removes the ambiguity of the old relative ``deadline_seconds`` name.
        self._deadline_monotonic = (
            float(deadline_monotonic) if deadline_monotonic is not None else None
        )
        self._cancelled_check = cancelled_check
        self._security_audit = require_security_audit_recorder(security_audit)
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
    def granted_capabilities(self) -> frozenset:
        """Capability-named alias for the retained permission grant field."""
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

    def is_non_retriable_cached(self, cache_key: str) -> bool:
        """Return whether a non-retriable result is already memoized.

        Checked before dispatch by the native migration mapper to report the
        runner's ``cached`` flag with the same before-dispatch semantics as the
        legacy direct path.
        """
        with self._lock:
            return cache_key in self._non_retriable_results

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

    def execute(
        self,
        name: str,
        arguments: Any,
        *,
        dispatch_guard: Optional[Callable[[Callable[[], None]], None]] = None,
        completion_guard: Optional[Callable[[Callable[[], None]], None]] = None,
        call_deadline_monotonic: Optional[float] = None,
        on_dispatched: Optional[Callable[[], None]] = None,
    ) -> Dict[str, Any]:
        """Audit one attempt/completion around the real session permission layer."""
        correlation_id = uuid.uuid4().hex
        target_id = _bounded_audit_identity(name, fallback="invalid")
        common = dict(
            event_type="tool.execute",
            actor_type="runtime_principal",
            actor_id=_bounded_audit_identity(self._principal, fallback="unknown"),
            execution_id=self._execution_id,
            action="tool.execute",
            target_type="tool",
            target_id=target_id,
            correlation_id=correlation_id,
            metadata={"backend": self._backend or "unknown"},
        )
        try:
            self._security_audit.record_attempt(**common)
        except SecurityAuditUnavailable:
            return self._security_audit_unavailable_result(
                name=name,
                arguments=arguments,
                phase="attempt",
            )

        result = self._execute_tool_call(
            name,
            arguments,
            dispatch_guard=dispatch_guard,
            completion_guard=completion_guard,
            call_deadline_monotonic=call_deadline_monotonic,
            on_dispatched=on_dispatched,
        )
        error = result.get("error") if isinstance(result, dict) else None
        error_code = error.get("code") if isinstance(error, dict) else None
        denied_codes = {
            "capability_undeclared",
            "invalid_tool_name",
            "invalid_arguments",
            "outbound_url_denied",
            "tool_not_allowed",
            "tool_not_found",
            "policy_undeclared",
            "permission_denied",
            "schema_contract_violation",
            "scope_contract_violation",
            "stock_scope_violation",
            "unsupported_capability",
        }
        outcome = "success" if result.get("ok") is True else (
            "denied" if error_code in denied_codes else "failure"
        )
        reason_code = "tool_succeeded" if outcome == "success" else (
            error_code if isinstance(error_code, str) and error_code else "tool_failed"
        )
        completion_metadata: Dict[str, Any] = {
            "backend": self._backend or "unknown",
        }
        if outcome == "denied":
            completion_metadata["denial_code"] = reason_code
            details = error.get("details") if isinstance(error, dict) else None
            if isinstance(details, dict):
                for key in (
                    "required_capabilities",
                    "missing_capabilities",
                    "unsupported_capabilities",
                    "reason",
                    "correlation_id",
                ):
                    value = details.get(key)
                    if isinstance(value, str) or (
                        isinstance(value, list)
                        and all(isinstance(item, str) for item in value)
                    ):
                        completion_metadata[key] = value
        completion = dict(common)
        completion["metadata"] = completion_metadata
        try:
            self._security_audit.record_completion(
                **completion,
                outcome=outcome,
                reason_code=reason_code,
            )
        except SecurityAuditUnavailable:
            return self._security_audit_unavailable_result(
                name=name,
                arguments=arguments,
                phase="completion",
            )
        return result

    def _execute_tool_call(
        self,
        name: str,
        arguments: Any,
        *,
        dispatch_guard: Optional[Callable[[Callable[[], None]], None]] = None,
        completion_guard: Optional[Callable[[Callable[[], None]], None]] = None,
        call_deadline_monotonic: Optional[float] = None,
        on_dispatched: Optional[Callable[[], None]] = None,
    ) -> Dict[str, Any]:
        """Execute one allowed tool through the frozen session gates.

        ``dispatch_guard`` may linearize the dispatch claim with an owning
        execution's cancellation/deadline state. It runs under the session lock
        immediately before the call is counted as dispatched, but must not run
        the external tool itself. ``on_dispatched`` runs after the session and
        execution locks are released but before the external tool starts.
        ``completion_guard`` applies the same ordering when accepting the
        returned result so late cancellation/deadline results remain audited.
        """
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
                    completion_rejection = self._claim_completion_locked(
                        completion_guard,
                    )
                    if completion_rejection is not None:
                        return self._drop_late_result_locked(
                            tool_name=tool_name,
                            arguments=arguments,
                            started_at=started_at,
                            call_context=self._build_call_context(
                                tool_name,
                                call_deadline_monotonic=call_deadline_monotonic,
                            ),
                            completion_rejection=completion_rejection,
                        )
                    self._audit_trail.append(cached["audit"])
                    return cached
            call_context = self._build_call_context(
                tool_name,
                call_deadline_monotonic=call_deadline_monotonic,
            )
            if rejection is None and (
                call_context.deadline_monotonic is not None
                and call_context.timeout_seconds is not None
                and call_context.timeout_seconds <= 0
            ):
                # A runner call deadline can elapse while the mandatory attempt
                # audit is being persisted. Reject before surface preflight so
                # a non-positive relative timeout cannot disable the fence.
                rejection = (
                    "deadline_exceeded",
                    "Tool call deadline exceeded.",
                    {"handler_started": False},
                )
            if rejection is not None:
                completion_rejection = self._claim_completion_locked(
                    completion_guard,
                )
                # Preserve a terminal fence that already won during dispatch.
                if (
                    completion_rejection is not None
                    and completion_rejection.code != rejection[0]
                ):
                    return self._drop_late_result_locked(
                        tool_name=tool_name,
                        arguments=arguments,
                        started_at=started_at,
                        call_context=call_context,
                        completion_rejection=completion_rejection,
                    )
                return self._reject_locked(
                    tool_name=tool_name,
                    arguments=arguments,
                    started_at=started_at,
                    rejection=rejection,
                )

        def _claim_surface_dispatch(
            expected_tool_def: ToolDefinition,
        ) -> Optional[
            Tuple[str, str, Optional[Dict[str, Any]]]
        ]:
            with self._lock:
                dispatch_rejection = self._gate_locked(
                    tool_name,
                    expected_tool_def=expected_tool_def,
                )
                if (
                    dispatch_rejection is None
                    and self._max_tool_calls is not None
                    and self._dispatched_calls >= self._max_tool_calls
                ):
                    dispatch_rejection = (
                        "budget_exhausted",
                        "Session tool-call budget exhausted.",
                        {"max_tool_calls": self._max_tool_calls},
                    )
                if dispatch_rejection is not None:
                    return dispatch_rejection

                dispatch_claimed = False

                def _claim_dispatch() -> None:
                    nonlocal dispatch_claimed
                    if dispatch_claimed:
                        raise RuntimeError(
                            "dispatch_guard claimed one tool call more than once"
                        )
                    dispatch_claimed = True
                    self._dispatched_calls += 1

                if dispatch_guard is None:
                    _claim_dispatch()
                else:
                    dispatched_calls_before_guard = self._dispatched_calls
                    try:
                        dispatch_guard(_claim_dispatch)
                    except ExecutionFenceRejected as exc:
                        self._dispatched_calls = dispatched_calls_before_guard
                        return (exc.code, exc.message, exc.details)
                    except BaseException:
                        self._dispatched_calls = dispatched_calls_before_guard
                        raise
                    if not dispatch_claimed:
                        raise RuntimeError(
                            "dispatch_guard returned without claiming the tool call"
                        )
            if on_dispatched is not None:
                on_dispatched()
            return None

        result = self._surface.execute_tool(
            tool_name,
            arguments,
            call_context,
            dispatch_guard=_claim_surface_dispatch,
        )

        with self._lock:
            completion_rejection = self._claim_completion_locked(completion_guard)

            if (
                self._closed
                or self._cancel_requested()
                or completion_rejection is not None
            ):
                return self._drop_late_result_locked(
                    tool_name=tool_name,
                    arguments=arguments,
                    started_at=started_at,
                    call_context=call_context,
                    completion_rejection=completion_rejection,
                )
            if cache_key is not None and self._is_cacheable_non_retriable(result):
                self._non_retriable_results[cache_key] = result
            self._audit_trail.append(result["audit"])
            return result

    def _security_audit_unavailable_result(
        self,
        *,
        name: str,
        arguments: Any,
        phase: str,
    ) -> Dict[str, Any]:
        started_at = time.time()
        tool_name = name if isinstance(name, str) else ""
        completion_failed = phase == "completion"
        result = build_tool_error_result(
            tool_name=tool_name,
            code="security_audit_unavailable",
            message=(
                "Security audit completion could not be persisted; tool execution "
                "may already have occurred and must not be retried."
                if completion_failed
                else "Security audit storage is unavailable; tool execution was rejected."
            ),
            started_at=started_at,
            context=self._build_call_context(tool_name),
            retriable=not completion_failed,
            details={
                "phase": phase,
                "execution_may_have_occurred": completion_failed,
            },
            arguments=arguments,
        )
        cache_key = (
            _build_tool_cache_key(tool_name, arguments)
            if completion_failed and isinstance(arguments, dict)
            else None
        )
        with self._lock:
            if cache_key is not None:
                self._non_retriable_results[cache_key] = result
            self._audit_trail.append(result["audit"])
        return result

    # ----- Gates (called with lock held) -----

    @staticmethod
    def _claim_completion_locked(
        completion_guard: Optional[Callable[[Callable[[], None]], None]],
    ) -> Optional[ExecutionFenceRejected]:
        """Claim one terminal result through the caller's completion fence."""
        if completion_guard is None:
            return None

        completion_claimed = False

        def _claim_completion() -> None:
            nonlocal completion_claimed
            if completion_claimed:
                raise RuntimeError(
                    "completion_guard claimed one tool result more than once"
                )
            completion_claimed = True

        try:
            completion_guard(_claim_completion)
        except ExecutionFenceRejected as exc:
            return exc
        if not completion_claimed:
            raise RuntimeError(
                "completion_guard returned without claiming the tool result"
            )
        return None

    def _drop_late_result_locked(
        self,
        *,
        tool_name: str,
        arguments: Any,
        started_at: float,
        call_context: ToolAccessContext,
        completion_rejection: Optional[ExecutionFenceRejected],
    ) -> Dict[str, Any]:
        """Audit and return one result rejected at its terminal fence."""
        self._dropped_results += 1
        fenced = build_tool_error_result(
            tool_name=tool_name,
            code="late_result_dropped",
            message="Tool result arrived after the session terminal state and was dropped.",
            started_at=started_at,
            context=call_context,
            retriable=False,
            details={
                "fence": "session_terminal",
                "reason": (
                    completion_rejection.code
                    if completion_rejection is not None
                    else "session_terminal"
                ),
            },
            arguments=arguments,
        )
        self._audit_trail.append(fenced["audit"])
        logger.warning(
            "[ToolSession] dropped late tool result: execution_id=%s tool=%s",
            self._execution_id,
            tool_name,
        )
        return fenced

    def _gate_locked(
        self,
        tool_name: str,
        *,
        expected_tool_def: Optional[ToolDefinition] = None,
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
        if (
            (":" in tool_name or "." in tool_name)
            and self._registry.resolve(tool_name) is None
        ):
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
        if (
            expected_tool_def is not None
            and tool_def is not expected_tool_def
        ):
            return (
                "tool_not_found",
                "Tool definition changed before dispatch.",
                {"reason": "definition_changed"},
            )
        capability_error = validate_tool_capability_contract(tool_def)
        if capability_error is not None:
            return (
                capability_error["code"],
                capability_error["message"],
                capability_error["details"],
            )
        schema_error = validate_tool_schema_contract(tool_def)
        if schema_error is not None:
            return (
                schema_error["code"],
                schema_error["message"],
                schema_error["details"],
            )
        missing = set(tool_def.policy.permissions) - self._granted_permissions
        if missing:
            required = sorted(tool_def.policy.permissions)
            missing_capabilities = sorted(missing)
            return (
                "permission_denied",
                "Session lacks required tool capabilities.",
                {
                    "required_capabilities": required,
                    "missing_capabilities": missing_capabilities,
                    "required_permissions": required,
                    "missing_permissions": missing_capabilities,
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
            context=self._build_call_context(tool_name),
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

    def _build_call_context(
        self,
        tool_name: str = "",
        *,
        call_deadline_monotonic: Optional[float] = None,
    ) -> ToolAccessContext:
        del tool_name  # Retained for compatibility with existing call sites.
        timeout = self._call_timeout_seconds
        effective_deadline = self._deadline_monotonic
        if call_deadline_monotonic is not None:
            try:
                normalized_call_deadline = float(call_deadline_monotonic)
            except (TypeError, ValueError):
                normalized_call_deadline = time.monotonic()
            if not math.isfinite(normalized_call_deadline):
                normalized_call_deadline = time.monotonic()
            effective_deadline = (
                normalized_call_deadline
                if effective_deadline is None
                else min(effective_deadline, normalized_call_deadline)
            )
        if effective_deadline is not None:
            remaining = effective_deadline - time.monotonic()
            timeout = remaining if timeout is None else min(timeout, remaining)
        return ToolAccessContext(
            stock_scope=self._stock_scope,
            backend=self._backend,
            session_id=self._session_id,
            timeout_seconds=timeout,
            deadline_monotonic=effective_deadline,
            cancelled_check=self._cancelled_check,
            max_result_bytes=self._max_result_bytes,
            audit_context=dict(self._base_audit_context),
            granted_capabilities=self._granted_permissions,
            enforce_contract=True,
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
