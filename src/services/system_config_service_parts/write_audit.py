# -*- coding: utf-8 -*-
"""Service-level ``system_config.write`` audit wrapper.

DAG-5 (#1062) records attempt before ``_update_validated`` persist and
completion afterward. Production callers import
``src.services.system_config_service``, not this module.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

# Facade-only helpers stay on ``system_config_service``. Rebound methods
# resolve them from that module's global namespace.
logger = None  # type: ignore[assignment,misc]
log_safe_exception = None  # type: ignore[assignment,misc]
ConfigValidationError = None  # type: ignore[assignment,misc]
ConfigConflictError = None  # type: ignore[assignment,misc]


class SystemConfigWriteAuditCompletionUnavailable(RuntimeError):
    """Raised when config persist succeeded but audit completion failed."""

    def __init__(
        self,
        *,
        config_version: str,
        applied_count: int,
        reload_triggered: bool,
    ) -> None:
        super().__init__("security_audit_unavailable")
        self.config_version = config_version
        self.applied_count = applied_count
        self.reload_triggered = reload_triggered


class _SystemConfigWriteAuditMethods:
    _WRITE_EVENT_TYPE = "system_config.write"
    _WRITE_TARGET_TYPE = "system_config"
    _WRITE_TARGET_ID = "runtime"
    _WRITE_ACTOR_TYPE = "administrator"
    _DEFAULT_WRITE_SOURCE = "system_config_update"
    _WRITE_SOURCES = frozenset(
        {
            "http_put",
            "legacy_migration",
            "config_profile_preset",
            "config_profile_import",
            "onboarding_apply",
            "local_model",
            "watchlist",
            "system_config_update",
        }
    )
    _LOCAL_MODEL_ACTORS = frozenset(
        {
            "local_model_center",
            "local_model_registration_restore",
            "local_model_delete_rollback",
        }
    )
    _MAX_WRITE_METADATA_KEYS = 16

    def _resolve_write_source(self, source: Any, actor: Any) -> str:
        candidate = source if type(source) is str else ""
        if (
            candidate in self._WRITE_SOURCES
            and candidate != self._DEFAULT_WRITE_SOURCE
        ):
            return candidate
        actor_name = actor if type(actor) is str else ""
        if actor_name in self._LOCAL_MODEL_ACTORS:
            return "local_model"
        if candidate in self._WRITE_SOURCES:
            return candidate
        return self._DEFAULT_WRITE_SOURCE

    def _write_audit_actor(self) -> str:
        import os

        from src.auth import is_auth_enabled

        if os.getenv("DSA_DESKTOP_MODE") == "true":
            return "desktop_operator"
        if is_auth_enabled():
            return "authenticated_admin"
        return "local_operator"

    def _write_audit_metadata(
        self,
        items: Sequence[Dict[str, Any]],
        *,
        config_version: str,
        reload_now: bool,
        source: str,
        applied_count: Optional[int] = None,
        skipped_masked_count: Optional[int] = None,
    ) -> Dict[str, Any]:
        import hashlib
        import json

        from src.schemas.security_audit import (
            SECURITY_AUDIT_MAX_METADATA_LIST_ITEMS,
            SECURITY_AUDIT_MAX_METADATA_STRING_LENGTH,
        )
        from src.utils.sanitize import redact_sensitive_data

        def _bounded_identity(value: Any) -> str:
            candidate = value if type(value) is str else str(value or "")
            if len(candidate) <= SECURITY_AUDIT_MAX_METADATA_STRING_LENGTH:
                return candidate
            return f"sha256:{hashlib.sha256(candidate.encode('utf-8')).hexdigest()}"

        keys = []
        seen = set()
        for item in items:
            key = item.get("key") if isinstance(item, dict) else None
            if type(key) is not str or not key:
                continue
            normalized = key.upper()
            if normalized in seen:
                continue
            seen.add(normalized)
            keys.append(normalized)
        canonical_keys = sorted(keys)
        canonical_payload = json.dumps(
            canonical_keys,
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
        metadata: Dict[str, Any] = {
            "key_sample": [
                _bounded_identity(key)
                for key in canonical_keys[:SECURITY_AUDIT_MAX_METADATA_LIST_ITEMS]
            ],
            "key_count": len(canonical_keys),
            "item_count": len(items),
            "keys_sha256": hashlib.sha256(canonical_payload).hexdigest(),
            "keys_truncated": len(canonical_keys) > SECURITY_AUDIT_MAX_METADATA_LIST_ITEMS,
            "config_version": _bounded_identity(config_version),
            "reload_now": bool(reload_now),
            "source": source,
        }
        if type(applied_count) is int:
            metadata["applied_count"] = applied_count
        if type(skipped_masked_count) is int:
            metadata["skipped_masked_count"] = skipped_masked_count
        bounded = dict(list(metadata.items())[: self._MAX_WRITE_METADATA_KEYS])
        redacted = redact_sensitive_data(bounded)
        return redacted if isinstance(redacted, dict) else {}

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
        recorder: Any = None,
        outcome: str = "pending",
        reason_code: str = "attempt_started",
    ) -> None:
        from src.services.security_audit_service import SecurityAuditUnavailable

        try:
            service = self._resolve_write_audit_recorder(recorder)
            common = dict(
                event_type=self._WRITE_EVENT_TYPE,
                actor_type=self._WRITE_ACTOR_TYPE,
                actor_id=self._write_audit_actor(),
                execution_id=correlation_id,
                action=self._WRITE_EVENT_TYPE,
                target_type=self._WRITE_TARGET_TYPE,
                target_id=self._WRITE_TARGET_ID,
                correlation_id=correlation_id,
                metadata=dict(metadata),
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
        result: Dict[str, Any],
    ) -> None:
        from src.services.security_audit_service import SecurityAuditUnavailable

        success_metadata = dict(metadata)
        applied_count = result.get("applied_count")
        skipped_masked_count = result.get("skipped_masked_count")
        if type(applied_count) is int:
            success_metadata["applied_count"] = applied_count
        if type(skipped_masked_count) is int:
            success_metadata["skipped_masked_count"] = skipped_masked_count
        bounded = dict(list(success_metadata.items())[: self._MAX_WRITE_METADATA_KEYS])
        try:
            self._record_system_config_write_audit(
                phase="completion",
                correlation_id=correlation_id,
                metadata=bounded,
                recorder=recorder,
                outcome="success",
                reason_code="config_updated",
            )
        except SecurityAuditUnavailable as exc:
            log_safe_exception(
                logger,
                "System config write audit completion unavailable after persist",
                exc,
                error_code="system_config_write_audit_completion_unavailable",
            )
            raise SystemConfigWriteAuditCompletionUnavailable(
                config_version=str(result.get("config_version") or ""),
                applied_count=int(result.get("applied_count") or 0),
                reload_triggered=bool(result.get("reload_triggered")),
            ) from None

    def _complete_system_config_write_failure(
        self,
        *,
        correlation_id: str,
        metadata: Dict[str, Any],
        recorder: Any,
        outcome: str,
        reason_code: str,
    ) -> None:
        from src.services.security_audit_service import SecurityAuditUnavailable

        try:
            self._record_system_config_write_audit(
                phase="completion",
                correlation_id=correlation_id,
                metadata=metadata,
                recorder=recorder,
                outcome=outcome,
                reason_code=reason_code,
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
        """Validate, persist, and emit one ``system_config.write`` audit pair."""
        from src.services.security_audit_service import (
            SecurityAuditService,
            SecurityAuditUnavailable,
        )

        resolved_source = self._resolve_write_source(source, actor)
        correlation_id = SecurityAuditService.new_correlation_id()
        metadata = self._write_audit_metadata(
            items,
            config_version=config_version,
            reload_now=reload_now,
            source=resolved_source,
        )
        self._record_system_config_write_audit(
            phase="attempt",
            correlation_id=correlation_id,
            metadata=metadata,
            recorder=security_audit,
        )
        try:
            result = self._update_validated(
                config_version,
                items,
                mask_token=mask_token,
                reload_now=reload_now,
                validate_connectivity=validate_connectivity,
                connectivity_timeout_seconds=connectivity_timeout_seconds,
                actor=actor,
            )
        except SecurityAuditUnavailable:
            raise
        except ConfigValidationError:
            self._complete_system_config_write_failure(
                correlation_id=correlation_id,
                metadata=metadata,
                recorder=security_audit,
                outcome="rejected",
                reason_code="validation_failed",
            )
            raise
        except ConfigConflictError:
            self._complete_system_config_write_failure(
                correlation_id=correlation_id,
                metadata=metadata,
                recorder=security_audit,
                outcome="rejected",
                reason_code="config_version_conflict",
            )
            raise
        except Exception as exc:  # broad-exception: fallback_recorded - complete the attempt before re-raising.
            log_safe_exception(
                logger,
                "System configuration update failed",
                exc,
                error_code="config_update_failed",
            )
            self._complete_system_config_write_failure(
                correlation_id=correlation_id,
                metadata=metadata,
                recorder=security_audit,
                outcome="failure",
                reason_code="config_update_failed",
            )
            raise
        self._complete_system_config_write_success(
            correlation_id=correlation_id,
            metadata=metadata,
            recorder=security_audit,
            result=result,
        )
        return result
