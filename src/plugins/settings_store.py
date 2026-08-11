# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Atomic local persistence for validated per-plugin settings."""

from __future__ import annotations

import json
import logging
import math
import os
import threading
from pathlib import Path
from typing import Mapping

from src.utils.sanitize import log_safe_exception, sanitize_diagnostic_text

from .manifest import PLUGIN_ID_PATTERN, PLUGIN_SETTING_KEY_PATTERN, PluginSettingScalar


SETTINGS_SCHEMA_VERSION = 1
DEFAULT_SETTINGS_FILENAME = "plugin_settings.json"
logger = logging.getLogger(__name__)


class PluginSettingsPersistenceError(RuntimeError):
    """Raised when a settings mutation cannot be durably persisted."""

    code = "plugin_settings_write_failed"


def _is_scalar(value: object) -> bool:
    if type(value) in {str, bool, int}:
        return True
    return type(value) is float and math.isfinite(value)


class PluginSettingsStore:
    """Thread-safe JSON store containing only explicit plugin overrides."""

    def __init__(self, path: str | Path | None = None, *, persist: bool = True) -> None:
        self._path = None if path is None else Path(path).expanduser()
        self._persist = bool(persist) and self._path is not None
        self._lock = threading.RLock()
        self._values: dict[str, dict[str, PluginSettingScalar]] = {}
        if self._persist:
            self._load_from_disk()

    @classmethod
    def beside_lifecycle_state(cls, lifecycle_path: Path | None) -> "PluginSettingsStore":
        """Use the lifecycle state directory without introducing another env key."""

        if lifecycle_path is None:
            return cls.memory()
        return cls(lifecycle_path.with_name(DEFAULT_SETTINGS_FILENAME), persist=True)

    @classmethod
    def memory(cls) -> "PluginSettingsStore":
        return cls(path=None, persist=False)

    @property
    def path(self) -> Path | None:
        return self._path

    def values_for(self, plugin_id: str) -> dict[str, PluginSettingScalar]:
        """Return an isolated snapshot of explicit overrides."""

        with self._lock:
            return dict(self._values.get(plugin_id, {}))

    def replace(
        self,
        plugin_id: str,
        values: Mapping[str, PluginSettingScalar],
    ) -> None:
        """Atomically replace one plugin's validated explicit values."""

        if type(plugin_id) is not str or PLUGIN_ID_PATTERN.fullmatch(plugin_id) is None:
            raise ValueError("plugin_id is invalid")
        normalized: dict[str, PluginSettingScalar] = {}
        for key, value in values.items():
            if type(key) is not str or PLUGIN_SETTING_KEY_PATTERN.fullmatch(key) is None:
                raise ValueError("plugin setting key is invalid")
            if not _is_scalar(value):
                raise ValueError("plugin setting values must be finite JSON scalars")
            normalized[key] = value

        with self._lock:
            before = self._values.get(plugin_id)
            if normalized:
                self._values[plugin_id] = normalized
            else:
                self._values.pop(plugin_id, None)
            try:
                if self._persist:
                    self._write_to_disk()
            except Exception:
                if before is None:
                    self._values.pop(plugin_id, None)
                else:
                    self._values[plugin_id] = before
                raise

    def _load_from_disk(self) -> None:
        path = self._path
        if path is None or not path.is_file():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, Mapping):
                raise ValueError("plugin settings payload must be an object")
            if payload.get("version") != SETTINGS_SCHEMA_VERSION:
                raise ValueError("plugin settings version is unsupported")
            plugins = payload.get("plugins")
            if not isinstance(plugins, Mapping):
                raise ValueError("plugin settings plugins must be an object")
            loaded: dict[str, dict[str, PluginSettingScalar]] = {}
            for plugin_id, raw_values in plugins.items():
                if (
                    type(plugin_id) is not str
                    or PLUGIN_ID_PATTERN.fullmatch(plugin_id) is None
                    or not isinstance(raw_values, Mapping)
                ):
                    raise ValueError("plugin settings entry is invalid")
                values: dict[str, PluginSettingScalar] = {}
                for key, value in raw_values.items():
                    if (
                        type(key) is not str
                        or PLUGIN_SETTING_KEY_PATTERN.fullmatch(key) is None
                        or not _is_scalar(value)
                    ):
                        raise ValueError("plugin setting value is invalid")
                    values[key] = value
                if values:
                    loaded[plugin_id] = values
            self._values = loaded
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            log_safe_exception(
                logger,
                "Plugin settings could not be read; ignoring persisted values",
                exc,
                error_code="plugin_settings_unavailable",
                context={
                    "path": sanitize_diagnostic_text(str(path), max_length=256) or "settings",
                },
            )
            self._values = {}

    def _write_to_disk(self) -> None:
        path = self._path
        if path is None:
            return
        payload = {
            "version": SETTINGS_SCHEMA_VERSION,
            "plugins": {
                plugin_id: dict(sorted(values.items()))
                for plugin_id, values in sorted(self._values.items())
            },
        }
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
                + "\n",
                encoding="utf-8",
            )
            try:
                tmp_path.chmod(0o600)
            except OSError:
                pass
            os.replace(tmp_path, path)
        except (OSError, TypeError, ValueError) as exc:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise PluginSettingsPersistenceError(self._safe_path(path)) from exc

    @staticmethod
    def _safe_path(path: Path) -> str:
        return sanitize_diagnostic_text(str(path), max_length=256) or "plugin settings"
