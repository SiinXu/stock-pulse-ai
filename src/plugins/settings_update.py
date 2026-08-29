# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Plugin settings mutation extracted from PluginManager."""

from __future__ import annotations

from typing import Mapping

from .manifest import PluginSettingScalar, validate_plugin_setting_value
from .manager_types import (
    PluginLifecycleAuditCompletionUnavailable,
    PluginSettingsUpdateResult,
    PluginSettingsValidationError,
)
from .settings_store import PluginSettingsPersistenceError


class PluginSettingsUpdateMixin:
    """Validate, persist, and audit one plugin's explicit settings replacement."""

    def update_settings(
        self,
        plugin_id: str,
        values: Mapping[str, object],
        *,
        mask_token: str = "******",
        require_audit: bool = False,
        actor_type: str | None = None,
        actor_id: str | None = None,
    ) -> PluginSettingsUpdateResult:
        """Validate and durably replace explicit values for one plugin."""

        with self._lock:
            record = self._plugins.get(plugin_id)
            if record is None:
                raise KeyError(plugin_id)
            definitions = record.manifest.settings
            state = record.state
        if not definitions:
            raise PluginSettingsValidationError(
                ({"key": "", "code": "plugin_settings_not_declared", "message": "Plugin does not declare settings"},)
            )
        if not isinstance(values, Mapping):
            raise PluginSettingsValidationError(
                ({"key": "", "code": "invalid_settings_payload", "message": "Settings values must be an object"},)
            )

        by_key = {definition.key: definition for definition in definitions}
        issues: list[dict[str, str]] = []
        for key in values:
            if type(key) is not str or key not in by_key:
                issues.append(
                    {
                        "key": str(key),
                        "code": "unknown_plugin_setting",
                        "message": "Setting is not declared by the plugin manifest",
                    }
                )
        existing = self._settings_store.values_for(plugin_id)
        normalized: dict[str, PluginSettingScalar] = {}
        for definition in definitions:
            if definition.key not in values:
                continue
            submitted = values[definition.key]
            if definition.is_sensitive and submitted == mask_token:
                if definition.key in existing:
                    normalized[definition.key] = existing[definition.key]
                continue
            if submitted is None:
                continue
            try:
                validated = validate_plugin_setting_value(
                    definition,
                    submitted,
                    allow_none=False,
                )
            except ValueError as exc:
                issues.append(
                    {
                        "key": definition.key,
                        "code": "invalid_plugin_setting",
                        "message": str(exc),
                    }
                )
                continue
            if validated is not None:
                normalized[definition.key] = validated

        for definition in definitions:
            if not definition.is_required:
                continue
            candidate = normalized.get(definition.key, definition.default_value)
            try:
                validate_plugin_setting_value(
                    definition,
                    candidate,
                    allow_none=False,
                )
            except ValueError:
                issues.append(
                    {
                        "key": definition.key,
                        "code": "required_plugin_setting_missing",
                        "message": "Required plugin setting is missing",
                    }
                )
        if issues:
            raise PluginSettingsValidationError(tuple(issues))

        changed_keys = tuple(
            sorted(
                key
                for key in set(existing) | set(normalized)
                if existing.get(key) != normalized.get(key)
                or (key in existing) != (key in normalized)
            )
        )
        correlation_id = self._audit_begin(
            record,
            plugin_id=plugin_id,
            operation="settings_update",
            required=require_audit,
            actor_type=actor_type,
            actor_id=actor_id,
        )
        try:
            if changed_keys:
                self._settings_store.replace(plugin_id, normalized)
            result = PluginSettingsUpdateResult(
                plugin_id=plugin_id,
                success=True,
                changed_keys=changed_keys,
                restart_required=bool(changed_keys) and state == "enabled",
            )
        except PluginSettingsPersistenceError:
            result = PluginSettingsUpdateResult(
                plugin_id=plugin_id,
                success=False,
                changed_keys=(),
                restart_required=False,
                error_code="plugin_settings_write_failed",
            )
            self._audit_complete(
                record,
                plugin_id=plugin_id,
                operation="settings_update",
                success=False,
                correlation_id=correlation_id,
                error_code=result.error_code,
                required=require_audit,
                actor_type=actor_type,
                actor_id=actor_id,
            )
            raise

        from src.services.security_audit_service import SecurityAuditUnavailable

        try:
            self._audit_complete(
                record,
                plugin_id=plugin_id,
                operation="settings_update",
                success=True,
                correlation_id=correlation_id,
                error_code=None,
                required=require_audit,
                actor_type=actor_type,
                actor_id=actor_id,
            )
        except SecurityAuditUnavailable:
            raise PluginLifecycleAuditCompletionUnavailable(result) from None
        return result
