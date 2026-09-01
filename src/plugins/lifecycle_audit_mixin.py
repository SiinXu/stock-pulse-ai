# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Lifecycle audit begin/complete bookkeeping extracted from PluginLifecycleMixin.

Issue #1080. ``PluginLifecycleMixin`` inherits this mixin, so ``PluginManager``
composition and MRO are unchanged and every method keeps its original name and
signature.

This mixin owns only the audit envelope: metadata capture, begin/complete
records, and the two audited-operation wrappers. The transitions themselves
(``_enable`` / ``_disable`` / ``_reload`` / ``_forget``) and the auditor
attributes (``_lifecycle_auditor``, ``_lifecycle_audit_disabled``) stay on
``PluginLifecycleMixin`` and are reached through ``self``.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from .manager_types import (
    PluginLifecycleAuditCompletionUnavailable,
    PluginOperationResult,
    PluginReloadResult,
    _ManagedPlugin,
)


logger = logging.getLogger("src.plugins.manager")


class PluginLifecycleAuditMixin:
    """Audit envelope for operator-driven lifecycle mutations."""

    def _audit_metadata_for(self, record: _ManagedPlugin) -> dict[str, Any]:
        return {
            "plugin_version": record.manifest.version,
            "plugin_source": record.source,
            "permissions": list(record.manifest.permissions),
            "extension_points": [
                handle.extension_point
                for handle in record.handles
                if handle.active
            ],
        }

    def _audit_begin(
        self,
        record: _ManagedPlugin | None,
        *,
        plugin_id: str,
        operation: str,
        required: bool = False,
        actor_type: str | None = None,
        actor_id: str | None = None,
    ) -> str | None:
        if self._lifecycle_audit_disabled:
            if required:
                from src.services.security_audit_service import (
                    SecurityAuditUnavailable,
                )

                raise SecurityAuditUnavailable()
            return None
        metadata = None if record is None else self._audit_metadata_for(record)
        return self._lifecycle_auditor.begin(
            plugin_id=plugin_id,
            operation=operation,
            metadata=metadata,
            required=required,
            actor_type=actor_type,
            actor_id=actor_id,
        )

    def _audit_complete(
        self,
        record: _ManagedPlugin | None,
        *,
        plugin_id: str,
        operation: str,
        success: bool,
        correlation_id: str | None,
        error_code: str | None,
        required: bool = False,
        actor_type: str | None = None,
        actor_id: str | None = None,
    ) -> None:
        if self._lifecycle_audit_disabled or correlation_id is None:
            if required:
                from src.services.security_audit_service import (
                    SecurityAuditUnavailable,
                )

                raise SecurityAuditUnavailable()
            return
        metadata = None if record is None else self._audit_metadata_for(record)
        self._lifecycle_auditor.complete(
            plugin_id=plugin_id,
            operation=operation,
            success=success,
            correlation_id=correlation_id,
            error_code=error_code,
            metadata=metadata,
            required=required,
            actor_type=actor_type,
            actor_id=actor_id,
        )

    def _audited_operation(
        self,
        plugin_id: str,
        operation: str,
        run: Callable[[], PluginOperationResult],
        *,
        require_audit: bool = False,
        actor_type: str | None = None,
        actor_id: str | None = None,
    ) -> PluginOperationResult:
        """Run one lifecycle operation with selected audit strictness."""

        with self._lock:
            record = self._plugins.get(plugin_id)
            starting_state = None if record is None else record.state
        correlation_id = self._audit_begin(
            record,
            plugin_id=plugin_id,
            operation=operation,
            required=require_audit,
            actor_type=actor_type,
            actor_id=actor_id,
        )
        result = run()
        with self._lock:
            record = self._plugins.get(plugin_id)
            if record is not None:
                if (
                    operation in {"load", "enable"}
                    and result.success
                    and result.error_code is None
                    and starting_state != "enabled"
                ):
                    self._set_last_error(record, None)
                elif result.error_code is not None:
                    self._set_last_error(record, result.error_code)
        from src.services.security_audit_service import SecurityAuditUnavailable

        try:
            self._audit_complete(
                record,
                plugin_id=plugin_id,
                operation=operation,
                success=result.success,
                correlation_id=correlation_id,
                error_code=result.error_code,
                required=require_audit,
                actor_type=actor_type,
                actor_id=actor_id,
            )
        except SecurityAuditUnavailable:
            raise PluginLifecycleAuditCompletionUnavailable(result) from None
        return result

    def _audited_reload(
        self,
        plugin_id: str,
        *,
        require_audit: bool,
        actor_type: str | None,
        actor_id: str | None,
    ) -> PluginReloadResult:
        with self._lock:
            record = self._plugins.get(plugin_id)
        correlation_id = self._audit_begin(
            record,
            plugin_id=plugin_id,
            operation="reload",
            required=require_audit,
            actor_type=actor_type,
            actor_id=actor_id,
        )
        result = self._reload(plugin_id)
        with self._lock:
            record = self._plugins.get(plugin_id)
            if record is not None:
                if result.success and result.error_code is None:
                    self._set_last_error(record, None)
                elif result.error_code is not None:
                    self._set_last_error(record, result.error_code)
        from src.services.security_audit_service import SecurityAuditUnavailable

        try:
            self._audit_complete(
                record,
                plugin_id=plugin_id,
                operation="reload",
                success=result.success,
                correlation_id=correlation_id,
                error_code=result.error_code,
                required=require_audit,
                actor_type=actor_type,
                actor_id=actor_id,
            )
        except SecurityAuditUnavailable:
            raise PluginLifecycleAuditCompletionUnavailable(result) from None
        return result
