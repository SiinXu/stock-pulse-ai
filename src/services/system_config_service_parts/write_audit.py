# -*- coding: utf-8 -*-
"""System-config write security-audit helpers.

DAG-5 (#1062) records ``system_config.write`` attempt before
``_update_validated`` and completion afterward. Consumers import
``src.services.system_config_service``, not this module.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any, Dict, Mapping, Optional, Sequence

# Facade-only helpers stay on ``system_config_service``. Rebound methods
# resolve them from that module's global namespace.
logger = None  # type: ignore[assignment,misc]
log_safe_exception = None  # type: ignore[assignment,misc]
ConfigValidationError = None  # type: ignore[assignment,misc]
ConfigConflictError = None  # type: ignore[assignment,misc]


SYSTEM_CONFIG_WRITE_EVENT_TYPE = "system_config.write"
SYSTEM_CONFIG_WRITE_TARGET_TYPE = "system_config"
SYSTEM_CONFIG_WRITE_TARGET_ID = "runtime"
DEFAULT_SYSTEM_CONFIG_WRITE_ACTOR_TYPE = "administrator"
DEFAULT_SYSTEM_CONFIG_WRITE_ACTOR_ID = "local_operator"
SYSTEM_CONFIG_WRITE_SOURCES = frozenset(
    {
        "http_put",
        "legacy_migration",
        "config_profile_preset",
        "config_profile_import",
        "onboarding_apply",
        "local_model",
        "system_config_update",
    }
)
_IDENTITY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,127}$")
_MAX_WRITE_METADATA_KEYS = 16


class SystemConfigWriteAuditCompletionUnavailable(RuntimeError):
    """Raised when the durable config write succeeded but audit completion failed."""

    def __init__(self, item: Dict[str, Any]) -> None:
        super().__init__("security_audit_unavailable")
        self.item = item


def _write_audit_actor() -> str:
    """Return the attributable operator class for the single-admin model."""
    if os.getenv("DSA_DESKTOP_MODE") == "true":
        return "desktop_operator"
    from src.auth import is_auth_enabled

    if is_auth_enabled():
        return "authenticated_admin"
    return DEFAULT_SYSTEM_CONFIG_WRITE_ACTOR_ID


def _bounded_write_identity(value: Any, *, fallback: str) -> str:
    candidate = value.strip() if type(value) is str else ""
    if candidate and _IDENTITY_PATTERN.fullmatch(candidate) is not None:
        return candidate[:128]
    return fallback


def _bounded_key_identity(value: str) -> str:
    from src.schemas.security_audit import SECURITY_AUDIT_MAX_METADATA_STRING_LENGTH

    if len(value) <= SECURITY_AUDIT_MAX_METADATA_STRING_LENGTH:
        return value
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _resolve_write_source(source: Any, *, actor: str) -> str:
    candidate = source.strip() if type(source) is str else ""
    if candidate in SYSTEM_CONFIG_WRITE_SOURCES and candidate != "system_config_update":
        return candidate
    if type(actor) is str and actor.startswith("local_model"):
        return "local_model"
    if candidate in SYSTEM_CONFIG_WRITE_SOURCES:
        return candidate
    return "system_config_update"


def _build_write_audit_metadata(
    items: Sequence[Mapping[str, Any]],
    *,
    config_version: str,
    reload_now: bool,
    source: str,
    applied_count: Optional[int] = None,
    skipped_masked_count: Optional[int] = None,
) -> Dict[str, Any]:
    from src.schemas.security_audit import SECURITY_AUDIT_MAX_METADATA_LIST_ITEMS

    canonical_keys = sorted(
        {
            str(item.get("key") or "")
            for item in items
            if isinstance(item, Mapping)
        }
    )
    canonical_payload = json.dumps(
        canonical_keys,
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    metadata: Dict[str, Any] = {
        "key_sample": [
            _bounded_key_identity(key)
            for key in canonical_keys[:SECURITY_AUDIT_MAX_METADATA_LIST_ITEMS]
        ],
        "key_count": len(canonical_keys),
        "item_count": len(items),
        "keys_sha256": hashlib.sha256(canonical_payload).hexdigest(),
        "keys_truncated": len(canonical_keys) > SECURITY_AUDIT_MAX_METADATA_LIST_ITEMS,
        "config_version": _bounded_key_identity(str(config_version or "")),
        "reload_now": bool(reload_now),
        "source": source,
    }
    if type(applied_count) is int:
        metadata["applied_count"] = applied_count
    if type(skipped_masked_count) is int:
        metadata["skipped_masked_count"] = skipped_masked_count
    return dict(list(metadata.items())[:_MAX_WRITE_METADATA_KEYS])


def _write_error_audit_fields(exc: BaseException) -> tuple[str, str]:
    name = type(exc).__name__
    if name == "ConfigValidationError":
        return "rejected", "validation_failed"
    if name == "ConfigConflictError":
        return "rejected", "config_version_conflict"
    return "failure", "config_update_failed"


def _persist_already_ran(exc: BaseException) -> bool:
    """True only when durable config stayed mutated after the exception.

    ``runtime_activation_failed`` is raised only after a successful restore
    that rewrites the previous ``.env`` snapshot, so reject-completion
    outages must keep the domain validation error instead of a post-persist
    ``503``.
    """
    return isinstance(exc, RuntimeError) and "activation and restoration failed" in str(exc)


def _completion_item(payload: Mapping[str, Any] | None) -> Dict[str, Any]:
    item: Dict[str, Any] = {}
    if not isinstance(payload, Mapping):
        return item
    config_version = payload.get("config_version")
    if type(config_version) is str:
        item["config_version"] = config_version
    applied_count = payload.get("applied_count")
    if type(applied_count) is int:
        item["applied_count"] = applied_count
    reload_triggered = payload.get("reload_triggered")
    if type(reload_triggered) is bool:
        item["reload_triggered"] = reload_triggered
    return item


class _SystemConfigWriteAuditMethods:
    """Source descriptors rebound onto ``SystemConfigService`` by its facade."""

    def _resolve_write_audit_recorder(self, recorder: Any = None):
        from src.services.security_audit_service import (
            get_security_audit_service,
            require_security_audit_recorder,
        )

        if recorder is not None:
            return require_security_audit_recorder(recorder)
        return require_security_audit_recorder(get_security_audit_service())

    def _record_system_config_write_audit(
        self,
        *,
        phase: str,
        correlation_id: str,
        metadata: Dict[str, Any],
        outcome: str = "pending",
        reason_code: str = "attempt_started",
        recorder: Any = None,
    ) -> None:
        from src.services.security_audit_service import SecurityAuditUnavailable
        from src.services.system_config_service_parts.write_audit import (
            DEFAULT_SYSTEM_CONFIG_WRITE_ACTOR_ID,
            DEFAULT_SYSTEM_CONFIG_WRITE_ACTOR_TYPE,
            SYSTEM_CONFIG_WRITE_EVENT_TYPE,
            SYSTEM_CONFIG_WRITE_TARGET_ID,
            SYSTEM_CONFIG_WRITE_TARGET_TYPE,
            _bounded_write_identity,
            _write_audit_actor,
        )

        actor_id = _bounded_write_identity(
            _write_audit_actor(),
            fallback=DEFAULT_SYSTEM_CONFIG_WRITE_ACTOR_ID,
        )
        payload = dict(metadata)
        try:
            service = self._resolve_write_audit_recorder(recorder)
            common = dict(
                event_type=SYSTEM_CONFIG_WRITE_EVENT_TYPE,
                actor_type=DEFAULT_SYSTEM_CONFIG_WRITE_ACTOR_TYPE,
                actor_id=actor_id,
                execution_id=correlation_id,
                action=SYSTEM_CONFIG_WRITE_EVENT_TYPE,
                target_type=SYSTEM_CONFIG_WRITE_TARGET_TYPE,
                target_id=SYSTEM_CONFIG_WRITE_TARGET_ID,
                correlation_id=correlation_id,
                metadata=payload,
            )
            if phase == "attempt":
                service.record_attempt(**common)
                return
            service.record_completion(
                **common,
                outcome=outcome,
                reason_code=reason_code,
            )
        except SecurityAuditUnavailable:
            raise
        except Exception as exc:  # broad-exception: fallback_recorded - write audit stays fail-closed.
            log_safe_exception(
                logger,
                "System config write audit unavailable",
                exc,
                error_code="security_audit_unavailable",
                context={"phase": phase},
            )
            raise SecurityAuditUnavailable() from None

    def _complete_system_config_write_success(
        self,
        *,
        correlation_id: str,
        metadata: Dict[str, Any],
        recorder: Any,
        item: Dict[str, Any],
    ) -> None:
        from src.services.security_audit_service import SecurityAuditUnavailable

        try:
            self._record_system_config_write_audit(
                phase="completion",
                correlation_id=correlation_id,
                metadata=metadata,
                outcome="success",
                reason_code="config_updated",
                recorder=recorder,
            )
        except SecurityAuditUnavailable as exc:
            log_safe_exception(
                logger,
                "System config write audit completion unavailable after persist",
                exc,
                error_code="system_config_write_audit_completion_unavailable",
            )
            raise SystemConfigWriteAuditCompletionUnavailable(item) from None

    def _complete_system_config_write_failure(
        self,
        *,
        correlation_id: str,
        metadata: Dict[str, Any],
        outcome: str,
        reason_code: str,
        recorder: Any,
    ) -> None:
        """Best-effort reject/failure completion; never mask the domain error."""
        from src.services.security_audit_service import SecurityAuditUnavailable

        try:
            self._record_system_config_write_audit(
                phase="completion",
                correlation_id=correlation_id,
                metadata=metadata,
                outcome=outcome,
                reason_code=reason_code,
                recorder=recorder,
            )
        except SecurityAuditUnavailable as exc:
            log_safe_exception(
                logger,
                "System config write failure audit completion unavailable",
                exc,
                error_code="system_config_write_failure_audit_unavailable",
            )

    def update(
        self,
        config_version: str,
        items: Sequence[Dict[str, str]],
        mask_token: str = "******",
        reload_now: bool = True,
        validate_connectivity: bool = False,
        connectivity_timeout_seconds: float = 20.0,
        actor: str = "system_config_service",
        security_audit: Any = None,
        source: str = "system_config_update",
    ) -> Dict[str, Any]:
        """Validate, persist, and audit one configuration write."""
        from src.services.security_audit_service import (
            SecurityAuditService,
            SecurityAuditUnavailable,
        )
        from src.services.system_config_service_parts.write_audit import (
            _build_write_audit_metadata,
            _completion_item,
            _persist_already_ran,
            _resolve_write_source,
            _write_error_audit_fields,
        )

        resolved_source = _resolve_write_source(source, actor=actor)
        metadata = _build_write_audit_metadata(
            items,
            config_version=config_version,
            reload_now=reload_now,
            source=resolved_source,
        )
        correlation_id = SecurityAuditService.new_correlation_id()
        self._resolve_write_audit_recorder(security_audit)
        self._record_system_config_write_audit(
            phase="attempt",
            correlation_id=correlation_id,
            metadata=metadata,
            recorder=security_audit,
        )
        try:
            payload = self._update_validated(
                config_version=config_version,
                items=items,
                mask_token=mask_token,
                reload_now=reload_now,
                validate_connectivity=validate_connectivity,
                connectivity_timeout_seconds=connectivity_timeout_seconds,
                actor=actor,
            )
        except SecurityAuditUnavailable:
            raise
        except SystemConfigWriteAuditCompletionUnavailable:
            raise
        except Exception as exc:  # broad-exception: fallback_recorded - complete the attempt before re-raising the mutation error.
            outcome, reason_code = _write_error_audit_fields(exc)
            persist_ran = _persist_already_ran(exc)
            log_safe_exception(
                logger,
                "System configuration update failed",
                exc,
                error_code=reason_code,
                context={"source": resolved_source},
            )
            try:
                self._record_system_config_write_audit(
                    phase="completion",
                    correlation_id=correlation_id,
                    metadata=metadata,
                    outcome=outcome,
                    reason_code=reason_code,
                    recorder=security_audit,
                )
            except SecurityAuditUnavailable as audit_exc:
                log_safe_exception(
                    logger,
                    "System config write failure audit completion unavailable",
                    audit_exc,
                    error_code="system_config_write_failure_audit_unavailable",
                )
                if persist_ran:
                    raise SystemConfigWriteAuditCompletionUnavailable(
                        _completion_item(
                            {
                                "config_version": config_version,
                                "applied_count": 0,
                                "reload_triggered": False,
                            }
                        )
                    ) from None
            raise
        success_metadata = _build_write_audit_metadata(
            items,
            config_version=str(payload.get("config_version") or config_version),
            reload_now=reload_now,
            source=resolved_source,
            applied_count=payload.get("applied_count"),
            skipped_masked_count=payload.get("skipped_masked_count"),
        )
        self._complete_system_config_write_success(
            correlation_id=correlation_id,
            metadata=success_metadata,
            recorder=security_audit,
            item=_completion_item(payload),
        )
        return payload
