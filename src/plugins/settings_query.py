# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Plugin settings query extracted from PluginManager."""

from __future__ import annotations

import logging

from .manifest import (
    PluginSettingDefinition,
    PluginSettingScalar,
    validate_plugin_setting_value,
)


logger = logging.getLogger(__name__)


class PluginSettingsQueryMixin:
    """Read one plugin's declarative schema and effective setting values."""

    def settings_schema(self, plugin_id: str) -> tuple[PluginSettingDefinition, ...] | None:
        """Return one registered plugin's immutable declarative field schema."""

        with self._lock:
            record = self._plugins.get(plugin_id)
            return None if record is None else record.manifest.settings

    def settings_values(self, plugin_id: str) -> dict[str, PluginSettingScalar] | None:
        """Return validated effective values (defaults plus explicit overrides)."""

        with self._lock:
            record = self._plugins.get(plugin_id)
            if record is None:
                return None
            definitions = record.manifest.settings
        stored = self._settings_store.values_for(plugin_id)
        effective: dict[str, PluginSettingScalar] = {}
        for definition in definitions:
            persisted = definition.key in stored
            candidate: object = (
                stored[definition.key] if persisted else definition.default_value
            )
            if candidate is None:
                continue
            try:
                validated = validate_plugin_setting_value(
                    definition,
                    candidate,
                    allow_none=False,
                )
            except ValueError:
                logger.warning(
                    "Ignoring invalid persisted plugin setting id=%s key=%s",
                    plugin_id,
                    definition.key,
                    extra={"error_code": "plugin_setting_persisted_value_invalid"},
                )
                if not persisted or definition.default_value is None:
                    continue
                validated = validate_plugin_setting_value(
                    definition,
                    definition.default_value,
                    allow_none=False,
                )
            if validated is not None:
                effective[definition.key] = validated
        return effective
